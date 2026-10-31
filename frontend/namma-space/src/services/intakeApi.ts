type Side = 'side1' | 'side2' | 'side3' | 'side4';
type UploadCategory = 'room_image' | 'extra_image' | 'video' | 'floor_plan' | 'sensor_data';

export type PreflightJob = {
    job_id: string;
    project_id: string;
    kind: string;
    status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
    report: {
        scope: string;
        reconstruction_started: boolean;
        metric_accuracy_validated: boolean;
        summary: { image_count: number; side_counts: Record<string, number>; video_count: number; floor_plan_count: number; sensor_data_count: number; warning_count: number };
        images: Array<{ filename: string; width_px?: number; height_px?: number; findings: string[]; side?: string }>;
        warnings: Array<{ code: string; message?: string; sides?: string[]; filenames?: string[]; pairs?: Array<{ first: string; second: string; hash_distance: number }> }>;
        next_step: string;
    } | null;
        result: { output?: { stage?: string; registered_image_count?: number | null; sparse_point_count?: number; surface_generated?: boolean; surface_error?: { code: string; message: string } | null; surface_format?: string | null; metric_scale_registered?: boolean; architectural_wireframe_generated?: boolean; message?: string }; artifacts?: Array<{ name: string; url: string; media_type: string }> } | null;
    error_code: string | null;
    created_at: string;
    updated_at: string;
};

export type SpatialJob = PreflightJob;

export type IntakeSubmission = { projectId: string; job: PreflightJob; workerPending: boolean };
export type OpeningInput = { id: string; label: string; kind: 'door' | 'window' | 'other'; side: Side; width?: number; height?: number; offset_from_corner?: number };
export type AnchorPixelPick = { image_filename: string; x_normalized: number; y_normalized: number };
export type SavedProject = { project_id: string; project_name: string; room_name: string; units: string; created_at: string; image_count: number; evidence_count: number; latest_job_status: string | null };
export type SavedProjectWorkspace = {
    project_id: string; project_name: string; room_name: string; units: 'm' | 'ft'; known_distance: number;
    anchor_name: string; anchor_start_label: string; anchor_end_label: string; anchor_view_side: Side;
    anchor_source: string; anchor_confidence: string; anchor_start_pick: AnchorPixelPick | null; anchor_end_pick: AnchorPixelPick | null;
    room_length: number | null; room_width: number | null; openings: OpeningInput[]; ceiling_height: number | null;
    created_at: string; sop_version: string; sop_acknowledgments: string[];
    uploads: Array<{ filename: string; category: UploadCategory; side: Side | null; byte_size: number; status: string }>;
    latest_job: PreflightJob | null;
};

export type WireframeDraft = {
    schemaVersion: string; sceneId: string; revision: number; units: 'm' | 'ft'; reviewState: string;
    inputDimensions: { length: number; width: number; height: number };
    inputOpenings: OpeningInput[];
    nodes: Array<{ id: string; position: [number, number, number]; source: string }>;
    edges: Array<{ id: string; start: string; end: string; kind: string; expectedLength: number | null }>;
    metrics: { coverage: number; connectedComponents: number; constraintsFailed: number; provisionalGeometry: string; unresolvedOpenings: Array<{ label: string; reason: string }> };
    provenance: { source: string; photogrammetryUsed: boolean; openings: Array<{ label: string; kind: string; side: string }> };
};

export function getSavedProjects() { return api<SavedProject[]>('/v1/projects'); }
export function getSavedProject(projectId: string) { return api<SavedProjectWorkspace>(`/v1/projects/${projectId}`); }
export function submitSparseReconstruction(projectId: string) { return api<SpatialJob>(`/v1/projects/${projectId}/reconstruction-jobs`, { method: 'POST', body: '{}' }); }
export function getSpatialJob(jobId: string) { return api<SpatialJob>(`/v1/jobs/${jobId}`); }
export async function addPhotosAndRefreshPreflight(projectId: string, files: File[], onJob: (job: SpatialJob) => void) {
    for (let index = 0; index < files.length; index++) {
        await uploadFile(projectId, files[index], 'extra_image');
    }
    let job = await api<SpatialJob>(`/v1/projects/${projectId}/preflight-jobs`, { method: 'POST', body: '{}' });
    onJob(job);
    for (let attempt = 0; attempt < 90 && ['queued', 'running'].includes(job.status); attempt++) {
        await delay(2000);
        job = await getSpatialJob(job.job_id);
        onJob(job);
    }
    return job;
}
export async function downloadSpatialArtifact(jobId: string, name: string) {
    const url = await getSpatialArtifactUrl(jobId, name);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
}
export async function getSpatialArtifactUrl(jobId: string, name: string) {
    const token = await accessToken();
    const response = await fetch(`${API_BASE}/v1/jobs/${jobId}/artifacts/${name}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error(`Could not download reconstruction artifact (${response.status}).`);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
}
export function getWireframeDraft(projectId: string) { return api<WireframeDraft>(`/v1/projects/${projectId}/wireframe-draft`); }
export function saveWireframeDraft(projectId: string, dimensions: WireframeDraft['inputDimensions'], openings: OpeningInput[]) { return api<WireframeDraft>(`/v1/projects/${projectId}/wireframe-revisions`, { method: 'POST', body: JSON.stringify({ ...dimensions, openings }) }); }

export function getPreflightJob(jobId: string) {
    return api<PreflightJob>(`/v1/jobs/${jobId}`);
}

const API_BASE = (import.meta.env.VITE_NAMMASPACE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

declare global {
    interface Window {
        nammaAuth?: { getAccessToken: () => Promise<string> };
    }
}

async function accessToken() {
    if (import.meta.env.DEV) return import.meta.env.VITE_DEV_API_TOKEN || 'local-dev-only-change-me';
    if (window.nammaAuth) return window.nammaAuth.getAccessToken();
    throw new Error('Your organization sign-in is not connected to the capture API yet.');
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await accessToken();
    let response: Response;
    try {
        response = await fetch(`${API_BASE}${path}`, {
            ...init,
            headers: { Authorization: `Bearer ${token}`, ...(init.body instanceof Blob ? {} : { 'Content-Type': 'application/json' }), ...init.headers },
        });
    } catch {
        throw new Error(`Cannot reach the capture service at ${API_BASE}. Start the FastAPI server in backend/api and check that this URL matches VITE_NAMMASPACE_API_URL. If the server is running, check its CORS allowed origins.`);
    }
    if (!response.ok) {
        let detail = `Capture service returned ${response.status}`;
        try {
            const payload = await response.json();
            detail = typeof payload.detail === 'string' ? payload.detail : payload.detail?.message || detail;
        } catch { /* Keep the HTTP status message. */ }
        throw new Error(detail);
    }
    return response.json() as Promise<T>;
}

async function sha256(blob: Blob) {
    const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function uploadFile(projectId: string, file: File, category: UploadCategory, side?: Side) {
    const extension = file.name.toLowerCase().split('.').pop();
    const mime = file.type || ({ jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', heic: 'image/heic', heif: 'image/heif', mp4: 'video/mp4', mov: 'video/quicktime', webm: 'video/webm', pdf: 'application/pdf', ply: 'application/vnd.ply' } as Record<string, string>)[extension || ''] || 'application/octet-stream';
    const upload = await api<{ upload_id: string; chunk_size: number; expected_parts: number; uploaded_parts: number[]; status: string }>(`/v1/projects/${projectId}/uploads`, {
        method: 'POST', body: JSON.stringify({ filename: file.name, content_type: mime, byte_size: file.size, category, side }),
    });
    if (upload.status !== 'complete') {
        const done = new Set(upload.uploaded_parts);
        for (let part = 0; part < upload.expected_parts; part++) {
            if (done.has(part)) continue;
            const chunk = file.slice(part * upload.chunk_size, Math.min(file.size, (part + 1) * upload.chunk_size));
            const digest = await sha256(chunk);
            await api(`/v1/uploads/${upload.upload_id}/parts/${part}`, {
                method: 'PUT', body: chunk,
                headers: { 'Content-Type': 'application/octet-stream', 'X-Chunk-SHA256': digest },
            });
        }
        await api(`/v1/uploads/${upload.upload_id}/complete`, { method: 'POST', body: '{}' });
    }
}

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export async function submitIntake(input: {
    projectId?: string;
    onProjectCreated: (projectId: string) => void;
    projectName: string;
    roomName: string;
    units: 'm' | 'ft';
    knownDistance: number;
    anchorName: string;
    anchorStartLabel: string;
    anchorEndLabel: string;
    anchorViewSide: Side;
    anchorSource: 'tape' | 'laser' | 'floor_plan' | 'sensor';
    anchorConfidence: 'high' | 'medium' | 'low';
    anchorStartPick: AnchorPixelPick | null;
    anchorEndPick: AnchorPixelPick | null;
    roomLength?: number;
    roomWidth?: number;
    openings: OpeningInput[];
    ceilingHeight?: number;
    sopAcknowledgments: string[];
    sidePhotos: Record<Side, File[]>;
    extraPhotos: File[];
    videoFile: File | null;
    floorPlanFile: File | null;
    sensorDataFile: File | null;
    onStatus: (message: string) => void;
}): Promise<IntakeSubmission> {
    const project = input.projectId ? { project_id: input.projectId } : await api<{ project_id: string }>('/v1/projects', {
        method: 'POST', body: JSON.stringify({ project_name: input.projectName.trim(), room_name: input.roomName.trim() || 'Room 1', units: input.units,
            known_distance: input.knownDistance, anchor_name: input.anchorName.trim(), anchor_start_label: input.anchorStartLabel.trim(),
            anchor_end_label: input.anchorEndLabel.trim(), anchor_view_side: input.anchorViewSide, anchor_source: input.anchorSource,
            anchor_confidence: input.anchorConfidence, anchor_start_pick: input.anchorStartPick, anchor_end_pick: input.anchorEndPick,
            room_length: input.roomLength, room_width: input.roomWidth, openings: input.openings,
            ceiling_height: input.ceilingHeight, sop_version: 'capture-v1', sop_acknowledgments: input.sopAcknowledgments }),
    });
    if (!input.projectId) input.onProjectCreated(project.project_id);
    const files: Array<{ file: File; category: UploadCategory; side?: Side }> = [];
    (['side1', 'side2', 'side3', 'side4'] as Side[]).forEach((side) => input.sidePhotos[side].forEach((file) => files.push({ file, category: 'room_image', side })));
    input.extraPhotos.forEach((file) => files.push({ file, category: 'extra_image' }));
    if (input.videoFile) files.push({ file: input.videoFile, category: 'video' });
    if (input.floorPlanFile) files.push({ file: input.floorPlanFile, category: 'floor_plan' });
    if (input.sensorDataFile) files.push({ file: input.sensorDataFile, category: 'sensor_data' });

    for (let i = 0; i < files.length; i++) {
        const item = files[i];
        input.onStatus(`Uploading ${i + 1} of ${files.length}: ${item.file.name}`);
        await uploadFile(project.project_id, item.file, item.category, item.side);
    }
    input.onStatus('Submitting capture preflight…');
    const queued = await api<PreflightJob>(`/v1/projects/${project.project_id}/preflight-jobs`, { method: 'POST', body: '{}' });
    let job = queued;
    for (let attempt = 0; attempt < 90 && job.status !== 'completed' && job.status !== 'failed' && job.status !== 'cancelled'; attempt++) {
        input.onStatus(job.status === 'running' ? 'Checking image quality and room-side coverage…' : 'Capture preflight is queued…');
        await delay(2000);
        job = await getPreflightJob(job.job_id);
    }
    return { projectId: project.project_id, job, workerPending: !['completed', 'failed', 'cancelled'].includes(job.status) };
}
