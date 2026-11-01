import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent, type MouseEvent } from 'react';
import './project-intake.css';
import './capture-uploads.css';
import './anchor-pick.css';
import './workspace-inspiration.css';
import './intake-typography.css';
import './lazy-loading.css';
import './demo-cta.css';
import { addPhotosAndRefreshPreflight, downloadSpatialArtifact, getSpatialArtifactUrl, getPreflightJob, getSpatialJob, submitIntake, submitSparseReconstruction, type AnchorPixelPick, type PreflightJob, type SpatialJob } from '../services/intakeApi';
import { ProjectLibrary } from './ProjectLibrary';

const WireframePreview3D = lazy(() => import('./WireframePreview3D').then((module) => ({ default: module.WireframePreview3D })));
const SurfacePreview3D = lazy(() => import('./SurfacePreview3D').then((module) => ({ default: module.SurfacePreview3D })));

type IntakeStep = 0 | 1 | 2;
type RoomSide = 'side1' | 'side2' | 'side3' | 'side4';
type OpeningDraft = { id: string; label: string; kind: 'door' | 'window' | 'other'; side: RoomSide; width: string; height: string; offset: string };

const steps = ['Project', 'Capture', 'Dimensions'];

export function ProjectIntake({ onOpenDemo }: { onOpenDemo: () => void }) {
    const [step, setStep] = useState<IntakeStep>(0);
    const [projectName, setProjectName] = useState('');
    const [roomName, setRoomName] = useState('Room 1');
    const [units, setUnits] = useState<'m' | 'ft'>('m');
    const [knownLength, setKnownLength] = useState('');
    const [anchorName, setAnchorName] = useState('Doorway width');
    const [anchorStartLabel, setAnchorStartLabel] = useState('Endpoint A');
    const [anchorEndLabel, setAnchorEndLabel] = useState('Endpoint B');
    const [anchorViewSide, setAnchorViewSide] = useState<RoomSide>('side1');
    const [anchorSource, setAnchorSource] = useState<'tape' | 'laser' | 'floor_plan' | 'sensor'>('tape');
    const [anchorConfidence, setAnchorConfidence] = useState<'high' | 'medium' | 'low'>('high');
    const [anchorPhotoIndex, setAnchorPhotoIndex] = useState('0');
    const [markingEndpoint, setMarkingEndpoint] = useState<'start' | 'end'>('start');
    const [anchorStartPick, setAnchorStartPick] = useState<AnchorPixelPick | null>(null);
    const [anchorEndPick, setAnchorEndPick] = useState<AnchorPixelPick | null>(null);
    const [anchorPhotoUrl, setAnchorPhotoUrl] = useState('');
    const [ceilingHeight, setCeilingHeight] = useState('');
    const [roomLength, setRoomLength] = useState('');
    const [roomWidth, setRoomWidth] = useState('');
    const [openings, setOpenings] = useState<OpeningDraft[]>([]);
    const [sidePhotos, setSidePhotos] = useState<Record<RoomSide, File[]>>({ side1: [], side2: [], side3: [], side4: [] });
    const [extraPhotos, setExtraPhotos] = useState<File[]>([]);
    const [videoFile, setVideoFile] = useState<File | null>(null);
    const [floorPlanFile, setFloorPlanFile] = useState<File | null>(null);
    const [sensorDataFile, setSensorDataFile] = useState<File | null>(null);
    const [checks, setChecks] = useState([false, false, false]);
    const [draftCreated, setDraftCreated] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [submitStatus, setSubmitStatus] = useState('');
    const [submitError, setSubmitError] = useState('');
    const [preflightJob, setPreflightJob] = useState<PreflightJob | null>(null);
    const [pendingProjectId, setPendingProjectId] = useState<string | undefined>();
    const [submittedProjectId, setSubmittedProjectId] = useState<string | undefined>();
    const [sparseJob, setSparseJob] = useState<SpatialJob | null>(null);
    const [surfacePreviewUrl, setSurfacePreviewUrl] = useState('');
    const [startingReconstruction, setStartingReconstruction] = useState(false);
    const [addingMorePhotos, setAddingMorePhotos] = useState(false);
    const [addedPhotoCount, setAddedPhotoCount] = useState(0);
    const [recoveryError, setRecoveryError] = useState('');
    const recoveryPhotoInput = useRef<HTMLInputElement>(null);
    const [showLibrary, setShowLibrary] = useState(false);

    const imageFiles = useMemo(() => [...Object.values(sidePhotos).flat(), ...extraPhotos], [sidePhotos, extraPhotos]);
    const anchorSidePhotos = sidePhotos[anchorViewSide];
    const anchorPhoto = anchorSidePhotos[Number(anchorPhotoIndex)] ?? anchorSidePhotos[0];
    useEffect(() => {
        if (!anchorPhoto) { setAnchorPhotoUrl(''); return; }
        const url = URL.createObjectURL(anchorPhoto);
        setAnchorPhotoUrl(url);
        return () => URL.revokeObjectURL(url);
    }, [anchorPhoto]);
    useEffect(() => { setAnchorPhotoIndex('0'); }, [anchorViewSide]);
    useEffect(() => { setAnchorStartPick(null); setAnchorEndPick(null); }, [anchorPhoto]);
    useEffect(() => {
        if (!draftCreated || !preflightJob || ['completed', 'failed', 'cancelled'].includes(preflightJob.status)) return;
        let stopped = false;
        let timer: number;
        const refresh = async () => {
            try {
                const updated = await getPreflightJob(preflightJob.job_id);
                if (!stopped) setPreflightJob(updated);
            } catch {
                // A temporary API interruption should not discard the queued job state.
            }
            if (!stopped) timer = window.setTimeout(refresh, 3000);
        };
        timer = window.setTimeout(refresh, 3000);
        return () => {
            stopped = true;
            window.clearTimeout(timer);
        };
    }, [draftCreated, preflightJob?.job_id, preflightJob?.status]);
    useEffect(() => {
        if (!sparseJob || !['queued', 'running'].includes(sparseJob.status)) return;
        let stopped = false;
        let timer: number;
        const refresh = async () => {
            try {
                const updated = await getSpatialJob(sparseJob.job_id);
                if (!stopped) setSparseJob(updated);
            } catch {
                if (!stopped) setRecoveryError('Could not refresh the reconstruction status. The job may still be running; check Saved projects.');
            }
            if (!stopped) timer = window.setTimeout(refresh, 3000);
        };
        timer = window.setTimeout(refresh, 1500);
        return () => { stopped = true; window.clearTimeout(timer); };
    }, [sparseJob?.job_id, sparseJob?.status]);
    useEffect(() => {
        const hasSurface = sparseJob?.status === 'completed' && sparseJob.result?.output?.surface_generated && sparseJob.result.artifacts?.some((artifact) => artifact.name === 'surface_mesh');
        if (!hasSurface || !sparseJob) { setSurfacePreviewUrl(''); return; }
        let stopped = false;
        let objectUrl = '';
        void getSpatialArtifactUrl(sparseJob.job_id, 'surface_mesh').then((url) => { objectUrl = url; if (!stopped) setSurfacePreviewUrl(url); else URL.revokeObjectURL(url); }).catch((error: unknown) => { if (!stopped) setRecoveryError(error instanceof Error ? error.message : 'Could not load the generated 3D surface.'); });
        return () => { stopped = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
    }, [sparseJob?.job_id, sparseJob?.status, sparseJob?.result?.output?.surface_generated]);

    const canContinue = step === 0
        ? projectName.trim().length > 1
        : step === 1
            ? Object.values(sidePhotos).every((side) => side.length > 0) && checks.every(Boolean)
            : Number(knownLength) > 0 && (!ceilingHeight || Number(ceilingHeight) > 0)
                && (!roomLength || Number(roomLength) > 0) && (!roomWidth || Number(roomWidth) > 0);

    const addSidePhotos = (side: RoomSide, event: ChangeEvent<HTMLInputElement>) => {
        const selected = Array.from(event.target.files ?? []);
        setSidePhotos((current) => ({ ...current, [side]: [...current[side], ...selected.filter((file) => !current[side].some((item) => item.name === file.name && item.size === file.size))] }));
        event.target.value = '';
    };

    const addExtraPhotos = (event: ChangeEvent<HTMLInputElement>) => {
        const selected = Array.from(event.target.files ?? []);
        setExtraPhotos((current) => [...current, ...selected.filter((file) => !current.some((item) => item.name === file.name && item.size === file.size))]);
        event.target.value = '';
    };

    const addOpening = () => {
        if (openings.length >= 50) return;
        setOpenings((current) => [...current, { id: crypto.randomUUID(), label: `Opening ${current.length + 1}`, kind: 'door', side: 'side1', width: '', height: '', offset: '' }]);
    };

    const updateOpening = (openingId: string, patch: Partial<OpeningDraft>) => {
        setOpenings((current) => current.map((opening) => opening.id === openingId ? { ...opening, ...patch } : opening));
    };

    const placeAnchorPick = (event: MouseEvent<HTMLButtonElement>) => {
        if (!anchorPhoto) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        const pick = {
            image_filename: anchorPhoto.name,
            x_normalized: Math.round(Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)) * 10000) / 10000,
            y_normalized: Math.round(Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)) * 10000) / 10000,
        };
        if (markingEndpoint === 'start') setAnchorStartPick(pick);
        else setAnchorEndPick(pick);
    };

    const nudgeAnchorPick = (event: KeyboardEvent<HTMLButtonElement>) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            if (!anchorPhoto) return;
            const center = { image_filename: anchorPhoto.name, x_normalized: 0.5, y_normalized: 0.5 };
            if (markingEndpoint === 'start') setAnchorStartPick(center);
            else setAnchorEndPick(center);
            return;
        }
        const deltas: Record<string, [number, number]> = { ArrowLeft: [-0.005, 0], ArrowRight: [0.005, 0], ArrowUp: [0, -0.005], ArrowDown: [0, 0.005] };
        const delta = deltas[event.key];
        if (!delta || !anchorPhoto) return;
        event.preventDefault();
        const update = (current: AnchorPixelPick | null): AnchorPixelPick => {
            const base = current ?? { image_filename: anchorPhoto.name, x_normalized: 0.5, y_normalized: 0.5 };
            return { ...base, x_normalized: Math.max(0, Math.min(1, base.x_normalized + delta[0])), y_normalized: Math.max(0, Math.min(1, base.y_normalized + delta[1])) };
        };
        if (markingEndpoint === 'start') setAnchorStartPick(update);
        else setAnchorEndPick(update);
    };

    const clearCapture = () => {
        setSidePhotos({ side1: [], side2: [], side3: [], side4: [] });
        setExtraPhotos([]);
        setVideoFile(null);
    };

    const submitDraft = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        if (!Number.isFinite(Number(knownLength)) || Number(knownLength) <= 0) {
            setSubmitError('Enter the measured distance to continue.');
            return;
        }
        const invalidOptionalDimension = [ceilingHeight, roomLength, roomWidth].find((value) => value !== '' && (!Number.isFinite(Number(value)) || Number(value) <= 0));
        if (invalidOptionalDimension !== undefined) {
            setSubmitError('Optional room dimensions must be positive numbers. Clear a field to leave it blank.');
            return;
        }
        if (!checks.every(Boolean)) {
            setSubmitError('Return to Capture and complete the three short capture checklist items.');
            return;
        }
        const incompleteOpening = openings.find((opening) => !opening.label.trim() || !opening.width || !opening.height || opening.offset === '');
        if (incompleteOpening) {
            setSubmitError(`Complete the label, width, height, and offset for “${incompleteOpening.label || 'each opening'}”, or remove that opening.`);
            return;
        }
        setSubmitting(true);
        setSubmitError('');
        try {
            const result = await submitIntake({
                projectId: pendingProjectId,
                onProjectCreated: setPendingProjectId,
                projectName, roomName, units, knownDistance: Number(knownLength),
                anchorName: anchorName.trim() || 'Measured span', anchorStartLabel: anchorStartLabel.trim() || 'Endpoint A', anchorEndLabel: anchorEndLabel.trim() || 'Endpoint B', anchorViewSide, anchorSource, anchorConfidence,
                anchorStartPick, anchorEndPick,
                roomLength: roomLength ? Number(roomLength) : undefined,
                roomWidth: roomWidth ? Number(roomWidth) : undefined,
                openings: openings.map((opening) => ({
                    id: opening.id, label: opening.label, kind: opening.kind, side: opening.side,
                    width: opening.width ? Number(opening.width) : undefined,
                    height: opening.height ? Number(opening.height) : undefined,
                    offset_from_corner: opening.offset !== '' ? Number(opening.offset) : undefined,
                })),
                ceilingHeight: ceilingHeight ? Number(ceilingHeight) : undefined,
                sopAcknowledgments: checks.flatMap((checked, index) => checked ? [['overlap', 'corners_openings', 'steady_lighting'][index]] : []),
                sidePhotos, extraPhotos, videoFile, floorPlanFile, sensorDataFile, onStatus: setSubmitStatus,
            });
            setPreflightJob(result.job);
            setSubmittedProjectId(result.projectId);
            setPendingProjectId(undefined);
            setDraftCreated(true);
        } catch (error) {
            setSubmitError(error instanceof Error ? error.message : 'Could not submit capture. Please retry.');
        } finally {
            setSubmitting(false);
            setSubmitStatus('');
        }
    };

    const startSparseReconstruction = async () => {
        if (!submittedProjectId) {
            setRecoveryError('Open Saved projects and select this capture to continue processing.');
            return;
        }
        setStartingReconstruction(true);
        setRecoveryError('');
        try { setSparseJob(await submitSparseReconstruction(submittedProjectId)); }
        catch (error) { setRecoveryError(error instanceof Error ? error.message : 'Could not start 3D processing.'); }
        finally { setStartingReconstruction(false); }
    };

    const addOverlappingPhotos = async (files: File[]) => {
        if (!submittedProjectId || files.length === 0) return;
        setAddingMorePhotos(true);
        setRecoveryError('');
        try {
            await addPhotosAndRefreshPreflight(submittedProjectId, files, setPreflightJob);
            setAddedPhotoCount((count) => count + files.length);
            setSparseJob(null);
        } catch (error) { setRecoveryError(error instanceof Error ? error.message : 'Could not add these photos.'); }
        finally {
            setAddingMorePhotos(false);
            if (recoveryPhotoInput.current) recoveryPhotoInput.current.value = '';
        }
    };

    const downloadSparseArtifact = async (jobId: string, name: string) => {
        try { await downloadSpatialArtifact(jobId, name); }
        catch (error) { setRecoveryError(error instanceof Error ? error.message : 'Could not download this reconstruction artifact.'); }
    };

    if (showLibrary) return <ProjectLibrary onClose={() => setShowLibrary(false)} />;

    return (
        <main className="ns-workbench">
            <header className="ns-workbench-header">
                <a className="ns-wordmark" href="/" aria-label="NammaSpace home"><span className="ns-mark">N</span> NammaSpace</a>
                <div className="ns-header-right"><span className="ns-secure-label"><span /> Capture intake</span><button className="ns-text-button" onClick={() => setShowLibrary(true)}>Saved projects</button><div className="ns-demo-cta"><span className="ns-demo-hint" aria-hidden="true">Click here to explore a 3D room →</span><button className="ns-text-button ns-demo-button" onClick={onOpenDemo} aria-label="Open demo viewer"><span className="ns-demo-label-long">Open demo viewer ↗</span><span className="ns-demo-label-short">Demo ↗</span></button></div></div>
            </header>

            <div className="ns-workbench-layout">
                <section className="ns-intake-main">
                    <div className="ns-eyebrow">SPATIAL MODEL WORKSPACE <span>•</span> NEW PROJECT</div>
                    <h1>Build a measured model<br />of your space.</h1>
                    <p className="ns-intro">Add room photos, follow the guided capture steps, and provide a few known measurements. We’ll use them to anchor the model to real-world scale.</p>

                    <nav className="ns-stepper" aria-label="Project setup progress">
                        {steps.map((label, index) => <div key={label} className={`ns-step ${index === step ? 'active' : ''} ${index < step ? 'complete' : ''}`}><span>{index < step ? '✓' : `0${index + 1}`}</span>{label}</div>)}
                    </nav>

                    {draftCreated ? (
                        <section className="ns-draft-state" aria-live="polite">
                            <div className="ns-draft-icon">✓</div>
                            <div className="ns-eyebrow">{preflightJob?.status === 'completed' ? 'CAPTURE PREFLIGHT COMPLETE' : 'CAPTURE SUBMITTED'}</div>
                            <h2>{projectName} is ready for processing setup</h2>
                            <p>{preflightJob?.status === 'completed' ? 'Your capture is stored in the project workspace and the background preflight checked the uploaded evidence. This result reviews image quality and side coverage; it has not generated a 3D reconstruction or validated dimensional accuracy.' : 'Your files have been uploaded and the preflight job is saved. The page will update when the background worker processes it.'}</p>
                            <div className="ns-draft-summary"><span>Room</span><strong>{roomName || 'Room 1'}</strong><span>Scale anchor</span><strong>{anchorName} · {knownLength} {units}</strong><span>Endpoints</span><strong>{anchorStartLabel} ↔ {anchorEndLabel} · Side {anchorViewSide.slice(-1)}</strong><span>Photo points</span><strong>{anchorStartPick && anchorEndPick ? `A and B marked in ${anchorStartPick.image_filename}` : 'Not marked'}</strong><span>Source / confidence</span><strong>{anchorSource.replaceAll('_', ' ')} · {anchorConfidence}</strong><span>Room size</span><strong>{roomLength || roomWidth ? `${roomLength || '—'} × ${roomWidth || '—'} ${units}` : 'Not provided'}</strong><span>Openings</span><strong>{openings.length ? openings.map((opening) => `${opening.label || opening.kind} (side ${opening.side.slice(-1)})`).join(', ') : 'None added'}</strong><span>Ceiling</span><strong>{ceilingHeight ? `${ceilingHeight} ${units}` : 'Estimate from images'}</strong><span>Capture images</span><strong>{imageFiles.length + addedPhotoCount}</strong><span>Video / plan / sensor</span><strong>{videoFile ? 'Video added' : 'No video'} · {floorPlanFile ? 'Plan added' : 'No plan'} · {sensorDataFile ? 'PLY added' : 'No sensor file'}</strong></div>
                            {preflightJob?.status === 'completed' && <div className="ns-preflight-result" aria-live="polite"><h3>Capture preflight</h3><p>{preflightJob.report?.summary.image_count ?? imageFiles.length} images reviewed · {preflightJob.report?.warnings.length ?? 0} finding(s)</p>{preflightJob.report?.warnings.map((warning, index) => <div className="ns-preflight-warning" key={`${warning.code}-${index}`}><strong>{warning.code.replaceAll('_', ' ')}</strong>{warning.sides?.length ? <span> — missing: {warning.sides.join(', ')}</span> : null}{warning.filenames?.length ? <span> — {warning.filenames.join(', ')}</span> : null}{warning.pairs?.map((pair) => <span key={`${pair.first}-${pair.second}`}> — similar views: {pair.first} / {pair.second}</span>)}{warning.message ? <span> — {warning.message}</span> : null}</div>)}{preflightJob.report?.images.filter((image) => image.findings.length > 0).map((image) => <div className="ns-preflight-warning" key={image.filename}><strong>{image.filename}</strong><span> — {image.findings.map((finding) => finding.replaceAll('_', ' ')).join(', ')}</span></div>)}{!preflightJob.report?.warnings.length && <p>All four sides are present and no basic quality flags were detected. This is not a guarantee of reconstruction quality.</p>}<small>This check reviews capture quality only; it does not create a 3D model.</small></div>}
                            {preflightJob && preflightJob.status !== 'completed' && <div className="ns-preflight-result"><h3>Preflight job {preflightJob.status}</h3><p>{preflightJob.status === 'failed' ? 'The worker could not finish this check. Contact your workspace administrator.' : 'The project and capture are saved. The worker will complete this check when available.'}</p></div>}
                            {preflightJob?.status === 'completed' && !sparseJob && <div className="ns-preflight-result ns-processing-action"><h3>Next: align the photos</h3><p>This step estimates camera positions and sparse points. It is a processing check, not yet the 3D room surface.</p><button type="button" className="ns-primary-button" onClick={() => void startSparseReconstruction()} disabled={startingReconstruction || addingMorePhotos}>{startingReconstruction ? 'Starting…' : 'Process photos'} <span>→</span></button></div>}
                            {sparseJob && <div className="ns-preflight-result" aria-live="polite"><h3>{sparseJob.status === 'completed' && sparseJob.result?.output?.surface_generated ? '3D surface ready for review' : sparseJob.status === 'completed' ? 'Photo alignment complete · surface generation needs attention' : `3D reconstruction · ${sparseJob.status}`}</h3><p>{sparseJob.result?.output?.message || (sparseJob.error_code === 'sfm_mapper_failed' ? 'COLMAP could not find a stable camera pair. Add several sharp photos with strong overlap between neighboring views, then retry.' : sparseJob.error_code === 'sfm_reject' ? 'COLMAP registered too few usable views to accept a model. Your photo check found duplicate or near-duplicate views; add new photos from different positions, keeping shared corners visible between shots.' : sparseJob.error_code ? `Processing stopped: ${sparseJob.error_code}` : 'The worker is aligning your photos, then it will build a dense surface. This can take several minutes.')}</p>{sparseJob.status === 'completed' && sparseJob.result?.output && <p>{sparseJob.result.output.registered_image_count ?? '—'} cameras aligned · {sparseJob.result.output.sparse_point_count ?? '—'} sparse points · {sparseJob.result.output.surface_generated ? 'surface mesh generated' : `surface not generated (${sparseJob.result.output.surface_error?.code || 'dense stage unavailable'})`} · metric scale {sparseJob.result.output.metric_scale_registered ? 'registered' : 'not registered'}</p>}{surfacePreviewUrl && <Suspense fallback={<div className="ns-preflight-result">Loading the generated 3D surface…</div>}><SurfacePreview3D src={surfacePreviewUrl} /></Suspense>}{sparseJob.status === 'completed' && sparseJob.result?.artifacts?.length ? <details className="ns-artifact-details"><summary>Advanced diagnostics</summary><div>{sparseJob.result.artifacts.filter((artifact) => artifact.name !== 'surface_mesh').map((artifact) => <button type="button" className="ns-secondary-button" key={artifact.name} onClick={() => void downloadSparseArtifact(sparseJob.job_id, artifact.name)}>Download {artifact.name.replaceAll('_', ' ')}</button>)}</div></details> : null}{sparseJob.status === 'failed' && ['sfm_mapper_failed', 'sfm_reject'].includes(sparseJob.error_code || '') && <><input ref={recoveryPhotoInput} type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" multiple hidden onChange={(event) => void addOverlappingPhotos(Array.from(event.currentTarget.files || []))} /><button type="button" className="ns-primary-button" onClick={() => recoveryPhotoInput.current?.click()} disabled={addingMorePhotos}>{addingMorePhotos ? 'Uploading photos and checking…' : 'Add overlapping photos'}</button></>}</div>}
                            {recoveryError && <div className="ns-submit-error" role="alert">{recoveryError}</div>}
                            <button className="ns-secondary-button" onClick={() => setDraftCreated(false)}>Review intake</button>
                        </section>
                    ) : (
                        <form onSubmit={submitDraft}>
                            {step === 0 && <div className="ns-form-panel">
                                <div className="ns-section-heading"><div><h2>Name your project</h2><p>Start with a project name. You can add more details after your first model is ready.</p></div><span className="ns-required-note">1 field required</span></div>
                                <div className="ns-fields-two">
                                    <label className="ns-field-label">Project name <span>*</span><input required minLength={2} value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="e.g. Green Street renovation" /></label>
                                    <label className="ns-field-label">Room or area<input minLength={2} value={roomName} onChange={(e) => setRoomName(e.target.value)} placeholder="Room 1" /></label>
                                </div>
                                <label className="ns-field-label">Measurement units <span>*</span><select value={units} onChange={(e) => setUnits(e.target.value as 'm' | 'ft')}><option value="m">Metric — metres (m)</option><option value="ft">Imperial — feet (ft)</option></select></label>
                            </div>}

                            {step === 1 && <div className="ns-form-panel">
                                <div className="ns-section-heading"><div><h2>Capture the room</h2><p>Starting at the entrance, move clockwise and add at least one original photo for each side. Take extra photos at corners and doorways to show how the walls connect.</p></div><span className="ns-required-note">4 side views required</span></div>
                                <div className="ns-side-upload-grid">{(['side1', 'side2', 'side3', 'side4'] as RoomSide[]).map((side, index) => <label className={`ns-side-upload ${sidePhotos[side].length ? 'has-files' : ''}`} key={side}><input type="file" accept="image/*" multiple onChange={(event) => addSidePhotos(side, event)} /><span className="ns-side-upload-icon">{sidePhotos[side].length ? '✓' : `0${index + 1}`}</span><strong>Side {index + 1}</strong><small>One or more clear views</small><em>{sidePhotos[side].length ? `${sidePhotos[side].length} selected · Add more` : 'Upload photo(s)'}</em></label>)}</div>
                                <div className="ns-optional-capture-grid">
                                    <label className="ns-optional-capture"><input type="file" accept="image/*" multiple onChange={addExtraPhotos} /><span>＋</span><div><strong>Extra photos <i>Optional</i></strong><small>Add corner, doorway, floor/ceiling or occluded views</small></div><b>{extraPhotos.length ? `${extraPhotos.length} added` : 'Add photos'}</b></label>
                                    <label className="ns-optional-capture"><input type="file" accept="video/*" onChange={(event) => setVideoFile(event.target.files?.[0] ?? null)} /><span>▷</span><div><strong>Room video <i>Optional</i></strong><small>A slow walk-through can add overlapping views</small></div><b>{videoFile ? 'Video added' : 'Add video'}</b></label>
                                </div>
                                <p className="ns-capture-note">Four side views are the minimum to start intake, not a guarantee of a complete or dimensionally accurate model. Preflight may request more photos. Video is optional and does not replace the measured dimensions on the next step.</p>
                                {(imageFiles.length > 0 || videoFile) && <div className="ns-file-list"><div className="ns-file-list-head"><strong>{imageFiles.length} photo{imageFiles.length === 1 ? '' : 's'}{videoFile ? ' · optional video selected' : ''}</strong><button type="button" className="ns-text-button" onClick={clearCapture}>Remove capture media</button></div>{imageFiles.map((file, index) => <div className="ns-file-row" key={`${file.name}-${index}`}><span className="ns-file-thumb">▧</span><span className="ns-file-name">{file.name}<small>{(file.size / 1024 / 1024).toFixed(1)} MB</small></span></div>)}{videoFile && <div className="ns-file-row"><span className="ns-file-thumb">▷</span><span className="ns-file-name">{videoFile.name}<small>{(videoFile.size / 1024 / 1024).toFixed(1)} MB · optional</small></span><button type="button" aria-label="Remove video" onClick={() => setVideoFile(null)}>×</button></div>}</div>}
                                <div className="ns-sop-box"><div className="ns-sop-title"><span>◎</span><div><strong>Guided capture checklist</strong><small>Complete each item before continuing</small></div></div>
                                    {['Walk slowly around the room; keep adjacent photos overlapping by roughly 70%.', 'Capture corners, floor and ceiling details, and both sides of each doorway.', 'Avoid blur, fast turns, moving people, and sudden changes in lighting.'].map((text, index) => <label className="ns-check-row" key={text}><input type="checkbox" checked={checks[index]} onChange={(e) => setChecks((current) => current.map((value, i) => i === index ? e.target.checked : value))} /><span>{text}</span></label>)}
                                    <p className="ns-sop-footnote">These are starting guidelines. Processing review will flag missing coverage; a reviewer may request additional captures.</p>
                                </div>
                            </div>}

                            {step === 2 && <div className="ns-form-panel">
                                <div className="ns-section-heading"><div><h2>Room measurements</h2><p>Only one measured distance is required. Add room details now or refine them later.</p></div><span className="ns-required-note">1 required measurement</span></div>
                                <div className="ns-measure-callout"><span>↔</span><div><strong>Choose a fixed, easy-to-measure distance</strong><p>For example, one wall corner-to-corner or a doorway width. Match the endpoints to visible points in your photos.</p></div></div>
                                <div className="ns-fields-two">
                                    <label className="ns-field-label">Known distance <span>*</span><div className="ns-input-unit"><input required type="number" min="0.1" step="0.01" value={knownLength} onChange={(e) => setKnownLength(e.target.value)} placeholder={units === 'm' ? 'e.g. 4.25' : 'e.g. 13.94'} /><span>{units}</span></div></label>
                                    <label className="ns-field-label">Ceiling height <small className="ns-field-help">Optional · improves vertical accuracy</small><div className="ns-input-unit"><input type="number" min="1" step="0.01" value={ceilingHeight} onChange={(e) => setCeilingHeight(e.target.value)} placeholder={units === 'm' ? 'Skip to estimate' : 'Skip to estimate'} /><span>{units}</span></div></label>
                                    <label className="ns-field-label">Room length <small className="ns-field-help">Optional</small><div className="ns-input-unit"><input type="number" min="0.1" step="0.01" value={roomLength} onChange={(e) => setRoomLength(e.target.value)} placeholder="Skip if unknown" /><span>{units}</span></div></label>
                                    <label className="ns-field-label">Room width <small className="ns-field-help">Optional</small><div className="ns-input-unit"><input type="number" min="0.1" step="0.01" value={roomWidth} onChange={(e) => setRoomWidth(e.target.value)} placeholder="Skip if unknown" /><span>{units}</span></div></label>
                                </div>
                                <details className="ns-optional-panel"><summary>Measurement labels and source <span>Optional</span></summary>
                                <label className="ns-field-label">Measurement description<input maxLength={120} value={anchorName} onChange={(e) => setAnchorName(e.target.value)} placeholder="e.g. Doorway clear width" /></label>
                                <div className="ns-fields-two">
                                    <label className="ns-field-label">Endpoint A<input maxLength={120} value={anchorStartLabel} onChange={(e) => setAnchorStartLabel(e.target.value)} placeholder="Endpoint A" /></label>
                                    <label className="ns-field-label">Endpoint B<input maxLength={120} value={anchorEndLabel} onChange={(e) => setAnchorEndLabel(e.target.value)} placeholder="Endpoint B" /></label>
                                </div>
                                <div className="ns-fields-two">
                                    <label className="ns-field-label">Best matching photo side <span>*</span><select value={anchorViewSide} onChange={(e) => setAnchorViewSide(e.target.value as RoomSide)}>{(['side1', 'side2', 'side3', 'side4'] as RoomSide[]).map((side, index) => <option key={side} value={side}>Side {index + 1}</option>)}</select></label>
                                    <label className="ns-field-label">Measured with <span>*</span><select value={anchorSource} onChange={(e) => setAnchorSource(e.target.value as typeof anchorSource)}><option value="tape">Tape measure</option><option value="laser">Laser measure</option><option value="floor_plan">Dimensioned floor plan</option><option value="sensor">Depth sensor</option></select></label>
                                </div>
                                <label className="ns-field-label">Confidence in this measurement <select value={anchorConfidence} onChange={(e) => setAnchorConfidence(e.target.value as typeof anchorConfidence)}><option value="high">High — measured directly</option><option value="medium">Medium — approximate measurement</option><option value="low">Low — estimated or unclear endpoints</option></select></label>
                                <p className="ns-capture-note">These labels preserve measurement provenance. Marking both endpoints on a photo helps reviewers locate the measured span; it does not yet match the points into reconstructed 3D space.</p>
                                </details>
                                <details className="ns-optional-panel"><summary>Mark measurement endpoints in a photo <span>{anchorStartPick && anchorEndPick ? 'A and B marked' : 'Optional'}</span></summary>
                                <section className="ns-anchor-mark-editor" aria-label="Mark measured endpoints in a photo">
                                    <div className="ns-section-subhead"><div><strong>Mark the measured span in a photo</strong><small>Optional · choose a photo from Side {anchorViewSide.slice(-1)}, then mark A and B</small></div></div>
                                    {anchorSidePhotos.length === 0 ? <p className="ns-anchor-no-photo">Add a photo for Side {anchorViewSide.slice(-1)} in the Capture step to mark endpoints.</p> : <>
                                        <label className="ns-field-label">Photo<select value={anchorPhotoIndex} onChange={(event) => setAnchorPhotoIndex(event.target.value)}>{anchorSidePhotos.map((file, index) => <option key={`${file.name}-${file.size}-${index}`} value={String(index)}>{file.name}</option>)}</select></label>
                                        <div className="ns-anchor-mark-actions"><button type="button" className={markingEndpoint === 'start' ? 'selected' : ''} onClick={() => setMarkingEndpoint('start')}>Mark A · {anchorStartLabel}</button><button type="button" className={markingEndpoint === 'end' ? 'selected' : ''} onClick={() => setMarkingEndpoint('end')}>Mark B · {anchorEndLabel}</button><button type="button" className="clear" onClick={() => { setAnchorStartPick(null); setAnchorEndPick(null); }}>Clear points</button></div>
                                        <button type="button" className="ns-anchor-photo" onClick={placeAnchorPick} onKeyDown={nudgeAnchorPick} aria-label={`Click photo to place endpoint ${markingEndpoint === 'start' ? 'A' : 'B'}. Use arrow keys to place or refine it`}>
                                            <img src={anchorPhotoUrl} alt="Selected room photo; click to place the active measured endpoint" />
                                            {anchorStartPick && anchorStartPick.image_filename === anchorPhoto.name && <span className="ns-anchor-point point-a" style={{ left: `${anchorStartPick.x_normalized * 100}%`, top: `${anchorStartPick.y_normalized * 100}%` }}>A</span>}
                                            {anchorEndPick && anchorEndPick.image_filename === anchorPhoto.name && <span className="ns-anchor-point point-b" style={{ left: `${anchorEndPick.x_normalized * 100}%`, top: `${anchorEndPick.y_normalized * 100}%` }}>B</span>}
                                        </button>
                                        <p className="ns-anchor-pick-state">{anchorStartPick ? `A marked at ${(anchorStartPick.x_normalized * 100).toFixed(1)}%, ${(anchorStartPick.y_normalized * 100).toFixed(1)}%` : 'A not marked'} · {anchorEndPick ? `B marked at ${(anchorEndPick.x_normalized * 100).toFixed(1)}%, ${(anchorEndPick.y_normalized * 100).toFixed(1)}%` : 'B not marked'} · Focus the photo and use arrow keys to adjust the active point.</p>
                                    </>}
                                </section>
                                </details>
                                <details className="ns-optional-panel"><summary>Doors and windows <span>{openings.length ? `${openings.length} added` : 'Optional'}</span></summary>
                                <section className="ns-opening-editor" aria-label="Optional room openings">
                                    <div className="ns-section-subhead"><div><strong>Doors and windows</strong><small>Optional · used in the provisional wireframe draft; positions are approximate</small></div><button type="button" className="ns-secondary-button" onClick={addOpening} disabled={openings.length >= 50}>+ Add opening</button></div>
                                    {openings.map((opening) => <div className="ns-opening-row" key={opening.id}>
                                        <label className="ns-field-label">Label<input value={opening.label} onChange={(e) => updateOpening(opening.id, { label: e.target.value })} placeholder="e.g. Main door" /></label>
                                        <label className="ns-field-label">Type<select value={opening.kind} onChange={(e) => updateOpening(opening.id, { kind: e.target.value as OpeningDraft['kind'] })}><option value="door">Door</option><option value="window">Window</option><option value="other">Other</option></select></label>
                                        <label className="ns-field-label">Wall side<select value={opening.side} onChange={(e) => updateOpening(opening.id, { side: e.target.value as RoomSide })}>{(['side1', 'side2', 'side3', 'side4'] as RoomSide[]).map((side, index) => <option key={side} value={side}>Side {index + 1}</option>)}</select></label>
                                        <label className="ns-field-label">Width<div className="ns-input-unit"><input type="number" min="0.1" step="0.01" value={opening.width} onChange={(e) => updateOpening(opening.id, { width: e.target.value })} placeholder="Optional" /><span>{units}</span></div></label>
                                        <label className="ns-field-label">Height<div className="ns-input-unit"><input type="number" min="0.1" step="0.01" value={opening.height} onChange={(e) => updateOpening(opening.id, { height: e.target.value })} placeholder="Optional" /><span>{units}</span></div></label>
                                        <label className="ns-field-label">Offset from corner<div className="ns-input-unit"><input type="number" min="0" step="0.01" value={opening.offset} onChange={(e) => updateOpening(opening.id, { offset: e.target.value })} placeholder="Optional" /><span>{units}</span></div></label>
                                        <button type="button" className="ns-opening-remove" onClick={() => setOpenings((current) => current.filter((item) => item.id !== opening.id))} aria-label={`Remove ${opening.label}`}>Remove</button>
                                    </div>)}
                                </section>
                                </details>
                                <details className="ns-optional-panel"><summary>Floor plan or depth scan <span>{floorPlanFile || sensorDataFile ? 'File selected' : 'Optional'}</span></summary>
                                <label className="ns-field-label">Optional: floor plan or sketch<input className="ns-optional-file" type="file" accept="image/*,.pdf" onChange={(e) => setFloorPlanFile(e.target.files?.[0] ?? null)} /><small className="ns-field-help">{floorPlanFile ? `Selected: ${floorPlanFile.name}. ` : ''}Stored with this capture; automatic floor-plan interpretation is not available yet.</small></label>
                                <label className="ns-field-label">Optional: depth sensor point cloud<input className="ns-optional-file" type="file" accept=".ply,application/vnd.ply,model/ply" onChange={(e) => setSensorDataFile(e.target.files?.[0] ?? null)} /><small className="ns-field-help">{sensorDataFile ? `Selected: ${sensorDataFile.name}. ` : ''}PLY point clouds only for now. This evidence is stored with the capture; reconstruction does not consume it yet.</small></label>
                                </details>
                                <div className="ns-precision-note"><strong>Start simple, improve when you’re ready</strong><p>The first model will use this scale anchor and label uncertain geometry. Add a ceiling measurement, floor plan, or more photos later to refine it. A reviewer must approve the wireframe before the solid and color stages.</p></div>
                            </div>}

                                {submitError && <div className="ns-submit-error" role="alert">{submitError}</div>}
                                <div className="ns-form-actions">
                                {step > 0 ? <button type="button" className="ns-secondary-button" disabled={submitting} onClick={() => setStep((step - 1) as IntakeStep)}>← Back</button> : <span className="ns-encrypted-note">Secure project upload</span>}
                                {step < 2 ? <button type="button" className="ns-primary-button" disabled={!canContinue || submitting} onClick={() => setStep((step + 1) as IntakeStep)}>Continue <span>→</span></button> : <button type="submit" className="ns-primary-button" disabled={submitting}>{submitting ? submitStatus || 'Submitting…' : 'Upload & check capture'} {!submitting && <span>→</span>}</button>}
                            </div>
                        </form>
                    )}
                    <footer className="ns-workbench-footer">NammaSpace <span>·</span> Spatial modelling workspace <span>·</span> Intake preview</footer>
                </section>

                <aside className="ns-side-panel">
                    <div className="ns-preview-card ns-preview-card-interactive" onClick={onOpenDemo} role="button" tabIndex={0} title="Click to open interactive 3D demo viewer" style={{ cursor: "pointer" }}><div className="ns-preview-top"><span>INTERACTIVE 3D PREVIEW</span><span className="ns-beta-pill">3 REVIEW STAGES</span></div><Suspense fallback={<div className="ns-preview-loading">Preparing interactive room…</div>}><WireframePreview3D /></Suspense><div className="ns-preview-caption"><strong>Explore a sample room wireframe</strong><span>Drag to orbit and scroll to zoom · dimensions are added from your measurements</span></div></div>
                    <div className="ns-stage-list"><div className="ns-aside-eyebrow">YOU REVIEW EVERY STAGE</div><div className={`ns-stage-row ${step >= 2 ? 'current' : 'current'}`}><span className="ns-stage-number">01</span><div><strong>Precision wireframe</strong><p>Dimensions, corners, walls, openings and confidence metrics</p></div><span className="ns-stage-lock">◉</span></div><div className="ns-stage-row"><span className="ns-stage-number">02</span><div><strong>Solid geometry</strong><p>Clean surfaces with simple glossy materials</p></div><span className="ns-stage-lock">◌</span></div><div className="ns-stage-row"><span className="ns-stage-number">03</span><div><strong>Color & objects</strong><p>Surface colors and editable object placeholders</p></div><span className="ns-stage-lock">◌</span></div></div>
                    <div className="ns-trust-note"><span>◈</span><p><strong>Human-approved at every step</strong><br />The next stage starts only when you approve the current one. You can return to edit the wireframe later.</p></div>
                </aside>
            </div>
        </main>
    );
}
