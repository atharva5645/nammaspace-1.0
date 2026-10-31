import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { addPhotosAndRefreshPreflight, downloadSpatialArtifact, getSavedProject, getSavedProjects, getSpatialJob, getWireframeDraft, saveWireframeDraft, submitSparseReconstruction, type OpeningInput, type SavedProject, type SavedProjectWorkspace, type SpatialJob, type WireframeDraft } from '../services/intakeApi';
import './project-library.css';
import './wireframe-draft.css';

const WireframeDraft3D = lazy(() => import('./WireframeDraft3D').then((module) => ({ default: module.WireframeDraft3D })));

function jobErrorMessage(job: SpatialJob) {
    if (job.error_code === 'sfm_mapper_failed') return 'COLMAP could not find a stable camera pair. Add more sharp photos with strong overlap between neighboring views, then run processing again.';
    if (job.error_code === 'sfm_reject') return 'COLMAP rejected the sparse model because too few photos registered as stable views. Add distinct viewpoints with strong overlap; duplicate photos do not add coverage.';
    if (job.error_code === 'colmap_binary_missing') return 'The COLMAP tool is not available to the worker. Check its configured executable path and restart the worker.';
    return `Worker status: ${job.status}${job.error_code ? ` · ${job.error_code}` : ''}`;
}

export function ProjectLibrary({ onClose }: { onClose: () => void }) {
    const [projects, setProjects] = useState<SavedProject[]>([]);
    const [selected, setSelected] = useState<SavedProjectWorkspace | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [wireframe, setWireframe] = useState<WireframeDraft | null>(null);
    const [wireframeLoading, setWireframeLoading] = useState(false);
    const [draftDimensions, setDraftDimensions] = useState<{ length: number; width: number; height: number } | null>(null);
    const [draftOpenings, setDraftOpenings] = useState<OpeningInput[] | null>(null);
    const [reconstructionBusy, setReconstructionBusy] = useState(false);
    const [addingPhotos, setAddingPhotos] = useState(false);
    const photoInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        let active = true;
        getSavedProjects().then((items) => { if (active) setProjects(items); })
            .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : 'Could not load saved projects.'); })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, []);

    const openProject = async (projectId: string) => {
        setLoading(true);
        setError('');
        setWireframe(null);
        setDraftDimensions(null);
        setDraftOpenings(null);
        try { setSelected(await getSavedProject(projectId)); }
        catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not reopen this project.'); }
        finally { setLoading(false); }
    };

    const showDimensionedDraft = async () => {
        if (!selected) return;
        setWireframeLoading(true);
        setError('');
        try {
            const draft = await getWireframeDraft(selected.project_id);
            setWireframe(draft);
            setDraftDimensions(draft.inputDimensions);
            setDraftOpenings(draft.inputOpenings);
        }
        catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not build the provisional wireframe.'); }
        finally { setWireframeLoading(false); }
    };

    const persistWireframeDraft = async () => {
        if (!selected) return;
        const dimensions = draftDimensions || wireframe?.inputDimensions;
        const openings = draftOpenings || wireframe?.inputOpenings;
        if (!dimensions || !openings) return;
        setWireframeLoading(true);
        setError('');
        try {
            const saved = await saveWireframeDraft(selected.project_id, dimensions, openings);
            setWireframe(saved);
            setDraftDimensions(saved.inputDimensions);
            setDraftOpenings(saved.inputOpenings);
        }
        catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not save this wireframe revision.'); }
        finally { setWireframeLoading(false); }
    };

    const startSparseReconstruction = async () => {
        if (!selected) return;
        setReconstructionBusy(true);
        setError('');
        try {
            let job: SpatialJob = await submitSparseReconstruction(selected.project_id);
            setSelected((current) => current ? { ...current, latest_job: job } : current);
            for (let attempt = 0; attempt < 90 && ['queued', 'running'].includes(job.status); attempt++) {
                await new Promise((resolve) => window.setTimeout(resolve, 2000));
                job = await getSpatialJob(job.job_id);
                setSelected((current) => current ? { ...current, latest_job: job } : current);
            }
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : 'Could not start sparse reconstruction.');
        } finally {
            setReconstructionBusy(false);
        }
    };

    const refreshWorkspace = async () => {
        if (!selected) return;
        try { setSelected(await getSavedProject(selected.project_id)); }
        catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not refresh this project.'); }
    };

    const downloadArtifact = async (jobId: string, name: string) => {
        try { await downloadSpatialArtifact(jobId, name); }
        catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not download this artifact.'); }
    };

    const addMorePhotos = async (files: File[]) => {
        if (!selected || files.length === 0) return;
        setAddingPhotos(true);
        setError('');
        try {
            const job = await addPhotosAndRefreshPreflight(selected.project_id, files, (nextJob) => {
                setSelected((current) => current ? { ...current, latest_job: nextJob } : current);
            });
            setSelected((current) => current ? { ...current, latest_job: job } : current);
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : 'Could not add these photos.');
        } finally {
            setAddingPhotos(false);
            if (photoInputRef.current) photoInputRef.current.value = '';
        }
    };

    return <main className="ns-project-library">
        <header className="ns-library-header"><a className="ns-wordmark" href="/" aria-label="NammaSpace home"><span className="ns-mark">N</span> NammaSpace</a><button type="button" className="ns-secondary-button" onClick={onClose}>← Back to capture</button></header>
        <div className="ns-library-shell">
            <section className="ns-library-list"><div className="ns-eyebrow">PROJECT WORKSPACE</div><h1>Saved projects</h1><p>Reopen a capture to review its saved details, files, and latest processing status.</p>
                {loading && <div className="ns-library-message">Loading projects…</div>}{error && <div className="ns-submit-error" role="alert">{error}</div>}
                {!loading && !error && projects.length === 0 && <div className="ns-library-empty">No saved projects yet. Start a capture to create your first workspace.</div>}
                <div className="ns-library-items">{projects.map((project) => <button type="button" className={`ns-library-item ${selected?.project_id === project.project_id ? 'selected' : ''}`} key={project.project_id} onClick={() => void openProject(project.project_id)}>
                    <span className="ns-library-icon">⌂</span><span className="ns-library-copy"><strong>{project.project_name}</strong><small>{project.room_name} · {project.image_count} photos · {project.evidence_count} files</small></span><span className="ns-library-status">{project.latest_job_status || 'Draft'}</span>
                </button>)}</div>
            </section>
            <section className="ns-library-detail" aria-live="polite">
                {!selected ? <div className="ns-library-placeholder"><span>↖</span><strong>Select a saved project</strong><p>Its capture metadata and latest worker status will appear here.</p></div> : <>
                    <div className="ns-eyebrow">SAVED WORKSPACE · {selected.sop_version}</div><h2>{selected.project_name}</h2><p className="ns-library-subtitle">{selected.room_name} · Created {new Date(selected.created_at.replace(' ', 'T') + 'Z').toLocaleString()}</p>
                    <div className="ns-library-status-card"><strong>{selected.latest_job ? `${selected.latest_job.kind.replaceAll('_', ' ')} ${selected.latest_job.status}` : 'No processing job yet'}</strong><p>{selected.latest_job?.report ? `${selected.latest_job.report.summary.image_count} images reviewed · ${selected.latest_job.report.summary.warning_count} finding(s).` : selected.latest_job?.result?.output?.message || (selected.latest_job ? jobErrorMessage(selected.latest_job) : 'This saved capture has not completed preflight.')}</p></div>
                    {selected.latest_job?.kind === 'capture_preflight' && selected.latest_job.status === 'completed' && <div className="ns-draft-action"><div><strong>Generate sparse reconstruction</strong><small>Estimate camera poses and a sparse point cloud from uploaded photos. Room surfaces and metric scale are later steps.</small></div><button type="button" className="ns-primary-button" onClick={() => void startSparseReconstruction()} disabled={reconstructionBusy}>{reconstructionBusy ? 'Processing…' : 'Start 3D processing'}</button></div>}
                    {selected.latest_job?.kind === 'sparse_reconstruction' && <section className="ns-library-status-card"><strong>Sparse image reconstruction</strong><p>{selected.latest_job.result?.output?.message || jobErrorMessage(selected.latest_job)}</p>{selected.latest_job.status === 'completed' && selected.latest_job.result?.output && <p>{selected.latest_job.result.output.registered_image_count ?? '—'} registered cameras · {selected.latest_job.result.output.sparse_point_count ?? '—'} sparse points · metric scale: {selected.latest_job.result.output.metric_scale_registered ? 'registered' : 'not registered'}</p>}{selected.latest_job.status === 'completed' && selected.latest_job.result?.artifacts?.map((artifact) => <button type="button" key={artifact.name} className="ns-secondary-button" onClick={() => void downloadArtifact(selected.latest_job!.job_id, artifact.name)}>Download {artifact.name.replaceAll('_', ' ')}</button>)}{['queued', 'running'].includes(selected.latest_job.status) && <button type="button" className="ns-secondary-button" onClick={() => void refreshWorkspace()} disabled={reconstructionBusy}>Refresh status</button>}</section>}
                    {selected.latest_job?.kind === 'sparse_reconstruction' && selected.latest_job.status === 'failed' && ['sfm_mapper_failed', 'sfm_reject'].includes(selected.latest_job.error_code || '') && <section className="ns-library-status-card"><strong>Improve photo overlap</strong><p>Take several extra photos while moving slowly between the four sides. Keep the same corners or objects visible in neighboring photos. Repeating the same view will not add useful coverage.</p><input ref={photoInputRef} type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" multiple hidden onChange={(event) => void addMorePhotos(Array.from(event.currentTarget.files || []))} /><button type="button" className="ns-primary-button" onClick={() => photoInputRef.current?.click()} disabled={addingPhotos}>{addingPhotos ? 'Uploading and checking…' : 'Add overlapping photos'}</button></section>}
                    <div className="ns-library-facts"><span>Scale anchor</span><strong>{selected.anchor_name} · {selected.known_distance} {selected.units}</strong><span>Endpoints</span><strong>{selected.anchor_start_label} ↔ {selected.anchor_end_label} · Side {selected.anchor_view_side.slice(-1)}</strong><span>Room dimensions</span><strong>{selected.room_length || selected.room_width ? `${selected.room_length || '—'} × ${selected.room_width || '—'} ${selected.units}` : 'Not provided'}</strong><span>Openings</span><strong>{selected.openings.length ? selected.openings.map((opening) => opening.label).join(', ') : 'None listed'}</strong></div>
                    {selected.room_length && selected.room_width && selected.ceiling_height && <div className="ns-draft-action"><div><strong>Dimension-driven wireframe draft</strong><small>Uses your room dimensions and rectangular outline assumption. Review it before relying on it.</small></div><button type="button" className="ns-primary-button" onClick={() => void showDimensionedDraft()} disabled={wireframeLoading}>{wireframeLoading ? 'Building…' : wireframe ? 'Refresh draft' : 'Create 3D draft'}</button></div>}
                    {error && <div className="ns-submit-error" role="alert">{error}</div>}
                    {wireframe && <section className="ns-wireframe-draft-card">
                        <div className="ns-wireframe-draft-header"><strong>Provisional wireframe · needs review</strong><span>{wireframe.revision ? `Revision ${wireframe.revision}` : 'Unsaved draft'} · {wireframe.metrics.constraintsFailed} constraint issues · {Math.round(wireframe.metrics.coverage * 100)}% image coverage</span></div>
                        <Suspense fallback={<div className="ns-library-message">Loading 3D workspace…</div>}><WireframeDraft3D model={wireframe} /></Suspense>
                        <p>This room outline is generated from entered dimensions. Uploaded images were not used to infer walls. Change a dimension below and save a revision to update the preview. Missing or unpositioned openings are listed below.</p>
                        <div className="ns-wireframe-dimension-editor">{([
                            ['length', 'Room length'], ['width', 'Room width'], ['height', 'Ceiling height'],
                        ] as const).map(([key, label]) => <label key={key}>{label}<span><input aria-label={label} type="number" min="0.01" step="0.01" value={draftDimensions?.[key] ?? wireframe.inputDimensions[key]} onChange={(event) => setDraftDimensions((current) => ({ ...(current || wireframe.inputDimensions), [key]: Number(event.target.value) }))} /><i>{wireframe.units}</i></span></label>)}</div>
                        <div className="ns-wireframe-openings-editor"><div className="ns-wireframe-openings-title"><strong>Doors and windows</strong><button type="button" onClick={() => setDraftOpenings((current) => [...(current || wireframe.inputOpenings), { id: crypto.randomUUID(), label: 'New opening', kind: 'door', side: 'side1', width: 0.9, height: 2.1, offset_from_corner: 0.5 }])}>+ Add opening</button></div>
                            {(draftOpenings || wireframe.inputOpenings).map((opening) => <div className="ns-wireframe-opening-row" key={opening.id}>
                                <input aria-label="Opening name" value={opening.label} onChange={(event) => setDraftOpenings((current) => (current || wireframe.inputOpenings).map((item) => item.id === opening.id ? { ...item, label: event.target.value } : item))} />
                                <select aria-label="Opening type" value={opening.kind} onChange={(event) => setDraftOpenings((current) => (current || wireframe.inputOpenings).map((item) => item.id === opening.id ? { ...item, kind: event.target.value as OpeningInput['kind'] } : item))}><option value="door">Door</option><option value="window">Window</option><option value="other">Other</option></select>
                                <select aria-label="Opening wall" value={opening.side} onChange={(event) => setDraftOpenings((current) => (current || wireframe.inputOpenings).map((item) => item.id === opening.id ? { ...item, side: event.target.value as OpeningInput['side'] } : item))}>{(['side1', 'side2', 'side3', 'side4'] as const).map((side) => <option key={side} value={side}>Wall {side.slice(-1)}</option>)}</select>
                                {(['width', 'height', 'offset_from_corner'] as const).map((field) => <input key={field} aria-label={`${opening.label} ${field.replaceAll('_', ' ')}`} type="number" min="0" step="0.01" placeholder={field.replaceAll('_', ' ')} value={opening[field] ?? ''} onChange={(event) => setDraftOpenings((current) => (current || wireframe.inputOpenings).map((item) => item.id === opening.id ? { ...item, [field]: event.target.value === '' ? undefined : Number(event.target.value) } : item))} />)}
                                <button type="button" aria-label={`Remove ${opening.label}`} onClick={() => setDraftOpenings((current) => (current || wireframe.inputOpenings).filter((item) => item.id !== opening.id))}>Remove</button>
                            </div>)}
                            {!(draftOpenings || wireframe.inputOpenings).length && <p>No openings added. Add a door or window to place a measured frame on the draft wall.</p>}
                        </div>
                        {wireframe.metrics.unresolvedOpenings.map((opening, index) => <small key={`${opening.label}-${index}`}>{opening.label}: {opening.reason.replaceAll('_', ' ')}</small>)}
                        <button type="button" className="ns-primary-button" onClick={() => void persistWireframeDraft()} disabled={wireframeLoading}>{wireframeLoading ? 'Saving…' : wireframe.revision ? 'Save new revision' : 'Save draft revision'}</button>
                    </section>}
                    <h3>Capture files</h3><div className="ns-library-files">{selected.uploads.map((upload, index) => <div key={`${upload.filename}-${upload.category}-${index}`}><span>{upload.filename}</span><small>{upload.category.replaceAll('_', ' ')}{upload.side ? ` · side ${upload.side.slice(-1)}` : ''} · {(upload.byte_size / 1024 / 1024).toFixed(1)} MB · {upload.status}</small></div>)}{!selected.uploads.length && <p>No uploaded files are saved for this project.</p>}</div>
                    {selected.latest_job?.report?.images.some((image) => image.findings.length) && <><h3>Preflight image findings</h3><div className="ns-library-files">{selected.latest_job.report.images.filter((image) => image.findings.length).map((image) => <div key={image.filename}><span>{image.filename}</span><small>{image.findings.map((finding) => finding.replaceAll('_', ' ')).join(', ')}</small></div>)}</div></>}
                </>}
            </section>
        </div>
    </main>;
}
