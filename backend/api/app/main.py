from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .auth import Identity, current_identity
from .database import connect, initialize_database, transaction
from .geometry_room import build_dimensioned_room_draft
from .orchestration import EvidenceAsset, JobEnvelope, CaptureInput, ProjectSnapshot
from .schemas import JobResponse, ProjectCreate, ProjectListItem, ProjectResponse, ProjectWorkspaceResponse, UploadCreate, WireframeRevisionInput
from .settings import get_settings
from .uploads import complete_upload, create_upload, receive_part


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="NammaSpace Capture API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().origin_list, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Chunk-SHA256"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "capture-api"}


@app.get("/v1/projects", response_model=list[ProjectListItem])
def list_projects(identity: Identity = Depends(current_identity)):
    with connect() as db:
        rows = db.execute("""SELECT p.id,p.project_name,p.room_name,p.units,p.created_at,
                            (SELECT COUNT(*) FROM uploads u WHERE u.project_id=p.id AND u.tenant_id=p.tenant_id AND u.category='room_image' AND u.status='complete') AS image_count,
                            (SELECT COUNT(*) FROM uploads u WHERE u.project_id=p.id AND u.tenant_id=p.tenant_id AND u.status='complete') AS evidence_count,
                            (SELECT j.status FROM jobs j WHERE j.project_id=p.id AND j.tenant_id=p.tenant_id ORDER BY j.created_at DESC,j.id DESC LIMIT 1) AS latest_job_status
                            FROM projects p WHERE p.tenant_id=? ORDER BY p.created_at DESC,p.id DESC LIMIT 100""",
                          (identity.tenant_id,)).fetchall()
    return [ProjectListItem(project_id=row["id"], project_name=row["project_name"], room_name=row["room_name"],
                            units=row["units"], created_at=row["created_at"], image_count=row["image_count"],
                            evidence_count=row["evidence_count"], latest_job_status=row["latest_job_status"])
            for row in rows]


@app.get("/v1/projects/{project_id}", response_model=ProjectWorkspaceResponse)
def get_project(project_id: str, identity: Identity = Depends(current_identity)):
    with connect() as db:
        project = db.execute("SELECT * FROM projects WHERE id=? AND tenant_id=?", (project_id, identity.tenant_id)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        uploads = db.execute("SELECT original_name,category,side,byte_size,status FROM uploads WHERE project_id=? AND tenant_id=? ORDER BY created_at,id",
                             (project_id, identity.tenant_id)).fetchall()
        job = db.execute("SELECT * FROM jobs WHERE project_id=? AND tenant_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
                         (project_id, identity.tenant_id)).fetchone()
    result = ProjectResponse(project_id=project["id"], project_name=project["project_name"], room_name=project["room_name"], units=project["units"],
                             known_distance=project["known_distance"], anchor_name=project["anchor_name"],
                             anchor_start_label=project["anchor_start_label"], anchor_end_label=project["anchor_end_label"],
                             anchor_view_side=project["anchor_view_side"], anchor_source=project["anchor_source"], anchor_confidence=project["anchor_confidence"],
                             anchor_start_pick=json.loads(project["anchor_picks_json"]).get("start"), anchor_end_pick=json.loads(project["anchor_picks_json"]).get("end"),
                             room_length=project["room_length"], room_width=project["room_width"], openings=json.loads(project["openings_json"]),
                             ceiling_height=project["ceiling_height"], created_at=project["created_at"])
    return ProjectWorkspaceResponse(**result.model_dump(), sop_version=project["sop_version"],
                                    sop_acknowledgments=json.loads(project["sop_acknowledgments_json"]),
                                    uploads=[{"filename": row["original_name"], "category": row["category"], "side": row["side"],
                                              "byte_size": row["byte_size"], "status": row["status"]} for row in uploads],
                                    latest_job=_job_response(job) if job else None)


@app.get("/v1/projects/{project_id}/wireframe-draft")
def get_dimensioned_wireframe_draft(project_id: str, identity: Identity = Depends(current_identity)):
    with connect() as db:
        project = db.execute("SELECT * FROM projects WHERE id=? AND tenant_id=?", (project_id, identity.tenant_id)).fetchone()
        saved = db.execute("SELECT model_json FROM wireframe_revisions WHERE project_id=? AND tenant_id=? ORDER BY revision DESC LIMIT 1",
                           (project_id, identity.tenant_id)).fetchone()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if saved:
        model = json.loads(saved["model_json"])
        model.setdefault("inputDimensions", {"length": project["room_length"], "width": project["room_width"], "height": project["ceiling_height"]})
        model.setdefault("inputOpenings", json.loads(project["openings_json"]))
        return model
    return _build_project_wireframe(project)


@app.post("/v1/projects/{project_id}/wireframe-revisions", status_code=201)
def save_dimensioned_wireframe_revision(project_id: str, data: WireframeRevisionInput, identity: Identity = Depends(current_identity)):
    with transaction(immediate=True) as db:
        project = db.execute("SELECT * FROM projects WHERE id=? AND tenant_id=?", (project_id, identity.tenant_id)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if not project["room_length"] or not project["room_width"] or not project["ceiling_height"]:
            raise HTTPException(status_code=409, detail="Room length, width, and ceiling height are required for a dimensioned wireframe draft")
        previous = db.execute("SELECT revision FROM wireframe_revisions WHERE project_id=? AND tenant_id=? ORDER BY revision DESC LIMIT 1",
                              (project_id, identity.tenant_id)).fetchone()
        revision = (previous["revision"] if previous else 0) + 1
        model = _build_project_wireframe(project, length=data.length, width=data.width, height=data.height, openings=data.openings)
        model["revision"] = revision
        model["parentRevision"] = previous["revision"] if previous else None
        revision_id = str(uuid.uuid4())
        db.execute("""INSERT INTO wireframe_revisions(id,project_id,tenant_id,revision,parent_revision,review_state,model_json,created_by,created_at)
                      VALUES(?,?,?,?,?,'needs_review',?,?,datetime('now'))""",
                   (revision_id, project_id, identity.tenant_id, revision, model["parentRevision"], json.dumps(model), identity.user_id))
    return model


def _build_project_wireframe(project, *, length=None, width=None, height=None, openings=None):
    length = length if length is not None else project["room_length"]
    width = width if width is not None else project["room_width"]
    height = height if height is not None else project["ceiling_height"]
    if not length or not width or not height:
        raise HTTPException(status_code=409, detail="Room length, width, and ceiling height are required for a dimensioned wireframe draft")
    model = build_dimensioned_room_draft(
        scene_id=project["id"], length=length, width=width,
        height=height, units=project["units"], openings=([opening.model_dump() for opening in openings] if openings is not None else json.loads(project["openings_json"])),
    )
    model["inputDimensions"] = {"length": length, "width": width, "height": height}
    model["inputOpenings"] = [opening.model_dump() for opening in openings] if openings is not None else json.loads(project["openings_json"])
    model["revision"] = 0
    return model


@app.post("/v1/projects", response_model=ProjectResponse, status_code=201)
def create_project(data: ProjectCreate, identity: Identity = Depends(current_identity)):
    project_id = str(uuid.uuid4())
    with transaction(immediate=True) as db:
        db.execute("""INSERT INTO projects(
                       id,tenant_id,owner_id,project_name,room_name,units,known_distance,anchor_name,anchor_start_label,
                       anchor_end_label,anchor_view_side,anchor_source,anchor_confidence,anchor_picks_json,room_length,
                       room_width,openings_json,ceiling_height,sop_version,sop_acknowledgments_json,created_at)
                    VALUES(
                       ?,?,?,?,?,?,?,?,?,?,
                       ?,?,?,?,?,?,?,?,?,?,
                       datetime('now'))""",
                   (project_id, identity.tenant_id, identity.user_id, data.project_name, data.room_name, data.units, data.known_distance,
                    data.anchor_name, data.anchor_start_label, data.anchor_end_label, data.anchor_view_side, data.anchor_source, data.anchor_confidence,
                    json.dumps({"start": data.anchor_start_pick.model_dump() if data.anchor_start_pick else None,
                                "end": data.anchor_end_pick.model_dump() if data.anchor_end_pick else None}),
                    data.room_length, data.room_width, json.dumps([opening.model_dump() for opening in data.openings]),
                    data.ceiling_height, data.sop_version, json.dumps(data.sop_acknowledgments)))
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return ProjectResponse(project_id=row["id"], project_name=row["project_name"], room_name=row["room_name"], units=row["units"],
                           known_distance=row["known_distance"], anchor_name=row["anchor_name"], anchor_start_label=row["anchor_start_label"],
                           anchor_end_label=row["anchor_end_label"], anchor_view_side=row["anchor_view_side"], anchor_source=row["anchor_source"],
                           anchor_confidence=row["anchor_confidence"],
                           anchor_start_pick=json.loads(row["anchor_picks_json"]).get("start"),
                           anchor_end_pick=json.loads(row["anchor_picks_json"]).get("end"),
                           room_length=row["room_length"], room_width=row["room_width"],
                           openings=json.loads(row["openings_json"]), ceiling_height=row["ceiling_height"], created_at=row["created_at"])


@app.post("/v1/projects/{project_id}/uploads", status_code=201)
def init_upload(project_id: str, data: UploadCreate, identity: Identity = Depends(current_identity)):
    return create_upload(project_id, data, identity)


@app.put("/v1/uploads/{upload_id}/parts/{part_number}")
async def upload_part(upload_id: str, part_number: int, request: Request,
                      identity: Identity = Depends(current_identity), chunk_sha256: str | None = Header(default=None, alias="X-Chunk-SHA256")):
    return await receive_part(upload_id, part_number, request, identity, chunk_sha256)


@app.post("/v1/uploads/{upload_id}/complete")
def finish_upload(upload_id: str, identity: Identity = Depends(current_identity)):
    return complete_upload(upload_id, identity)


@app.post("/v1/projects/{project_id}/preflight-jobs", response_model=JobResponse, status_code=202)
def submit_preflight(project_id: str, identity: Identity = Depends(current_identity)):
    with transaction(immediate=True) as db:
        project = db.execute("SELECT * FROM projects WHERE id=? AND tenant_id=?", (project_id, identity.tenant_id)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        uploads = db.execute("SELECT * FROM uploads WHERE project_id=? AND tenant_id=? ORDER BY created_at,id", (project_id, identity.tenant_id)).fetchall()
        complete = [upload for upload in uploads if upload["status"] == "complete"]
        sides = {upload["side"] for upload in complete if upload["category"] == "room_image"}
        missing_sides = [f"side{i}" for i in range(1, 5) if f"side{i}" not in sides]
        if missing_sides:
            raise HTTPException(status_code=409, detail={"message": "Required room-side photos are missing", "missing_sides": missing_sides})
        anchor_picks = json.loads(project["anchor_picks_json"])
        start_pick = anchor_picks.get("start")
        if start_pick:
            matched_source = any(upload["category"] == "room_image" and upload["side"] == project["anchor_view_side"]
                                 and upload["original_name"] == start_pick["image_filename"] for upload in complete)
            if not matched_source:
                raise HTTPException(status_code=409, detail="The marked anchor photo must be uploaded under the selected room side")
        queued = db.execute("SELECT id FROM jobs WHERE project_id=? AND tenant_id=? AND status IN ('queued','running')", (project_id, identity.tenant_id)).fetchone()
        if queued:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (queued["id"],)).fetchone()
        else:
            job_id = str(uuid.uuid4())
            envelope = JobEnvelope(
                contract_version="spatial-job.v1", job_id=job_id, job_type="capture_preflight",
                tenant_id=identity.tenant_id, project_id=project_id,
                input=CaptureInput(
                    snapshot_version="capture-input.v1",
                    project=ProjectSnapshot(
                        project_name=project["project_name"], room_name=project["room_name"], units=project["units"],
                        known_distance=project["known_distance"], anchor_name=project["anchor_name"],
                        anchor_start_label=project["anchor_start_label"], anchor_end_label=project["anchor_end_label"],
                        anchor_view_side=project["anchor_view_side"], anchor_source=project["anchor_source"],
                        anchor_confidence=project["anchor_confidence"],
                        anchor_start_pick=start_pick,
                        anchor_end_pick=anchor_picks.get("end"),
                        room_length=project["room_length"], room_width=project["room_width"],
                        openings=json.loads(project["openings_json"]), ceiling_height=project["ceiling_height"],
                        sop_version=project["sop_version"], sop_acknowledgments=json.loads(project["sop_acknowledgments_json"]),
                    ),
                    evidence=[EvidenceAsset(upload_id=upload["id"], sha256=upload["actual_sha256"], category=upload["category"],
                                            side=upload["side"], content_type=upload["content_type"], storage_key=upload["storage_key"])
                              for upload in complete],
                ),
            )
            db.execute("""INSERT INTO jobs(id,project_id,tenant_id,kind,contract_version,input_json,status,created_at,updated_at)
                         VALUES(?,?,?,'capture_preflight',?,?,'queued',datetime('now'),datetime('now'))""",
                       (job_id, project_id, identity.tenant_id, envelope.contract_version, envelope.model_dump_json()))
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _job_response(row)


@app.post("/v1/projects/{project_id}/reconstruction-jobs", response_model=JobResponse, status_code=202)
def submit_sparse_reconstruction(project_id: str, identity: Identity = Depends(current_identity)):
    with transaction(immediate=True) as db:
        project = db.execute("SELECT * FROM projects WHERE id=? AND tenant_id=?", (project_id, identity.tenant_id)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        uploads = db.execute("SELECT * FROM uploads WHERE project_id=? AND tenant_id=? ORDER BY created_at,id",
                             (project_id, identity.tenant_id)).fetchall()
        complete = [upload for upload in uploads if upload["status"] == "complete"]
        sides = {upload["side"] for upload in complete if upload["category"] == "room_image"}
        missing_sides = [f"side{i}" for i in range(1, 5) if f"side{i}" not in sides]
        if missing_sides:
            raise HTTPException(status_code=409, detail={"message": "Required room-side photos are missing", "missing_sides": missing_sides})
        latest_preflight = db.execute("SELECT * FROM jobs WHERE project_id=? AND tenant_id=? AND kind='capture_preflight' ORDER BY created_at DESC,id DESC LIMIT 1",
                                      (project_id, identity.tenant_id)).fetchone()
        if latest_preflight is None or latest_preflight["status"] != "completed":
            raise HTTPException(status_code=409, detail="Complete capture preflight before starting sparse reconstruction")
        active = db.execute("SELECT id FROM jobs WHERE project_id=? AND tenant_id=? AND status IN ('queued','running')",
                            (project_id, identity.tenant_id)).fetchone()
        if active:
            raise HTTPException(status_code=409, detail="Another processing job is already queued or running")
        job_id = str(uuid.uuid4())
        anchor_picks = json.loads(project["anchor_picks_json"])
        envelope = JobEnvelope(
            contract_version="spatial-job.v1", job_id=job_id, job_type="sparse_reconstruction",
            tenant_id=identity.tenant_id, project_id=project_id,
            input=CaptureInput(
                snapshot_version="capture-input.v1",
                project=ProjectSnapshot(
                    project_name=project["project_name"], room_name=project["room_name"], units=project["units"],
                    known_distance=project["known_distance"], anchor_name=project["anchor_name"],
                    anchor_start_label=project["anchor_start_label"], anchor_end_label=project["anchor_end_label"],
                    anchor_view_side=project["anchor_view_side"], anchor_source=project["anchor_source"],
                    anchor_confidence=project["anchor_confidence"], anchor_start_pick=anchor_picks.get("start"),
                    anchor_end_pick=anchor_picks.get("end"), room_length=project["room_length"],
                    room_width=project["room_width"], openings=json.loads(project["openings_json"]),
                    ceiling_height=project["ceiling_height"], sop_version=project["sop_version"],
                    sop_acknowledgments=json.loads(project["sop_acknowledgments_json"]),
                ),
                evidence=[EvidenceAsset(upload_id=upload["id"], sha256=upload["actual_sha256"], category=upload["category"],
                                        side=upload["side"], content_type=upload["content_type"], storage_key=upload["storage_key"])
                          for upload in complete],
            ),
        )
        db.execute("""INSERT INTO jobs(id,project_id,tenant_id,kind,contract_version,input_json,status,created_at,updated_at)
                      VALUES(?,?,?,'sparse_reconstruction',?,?,'queued',datetime('now'),datetime('now'))""",
                   (job_id, project_id, identity.tenant_id, envelope.contract_version, envelope.model_dump_json()))
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _job_response(row)


def _job_response(row) -> JobResponse:
    return JobResponse(job_id=row["id"], project_id=row["project_id"], kind=row["kind"], contract_version=row["contract_version"], status=row["status"],
                       report=json.loads(row["report_json"]) if row["report_json"] else None, error_code=row["error_code"],
                       result=json.loads(row["output_json"]) if row["output_json"] else None,
                       created_at=row["created_at"], updated_at=row["updated_at"])


@app.get("/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, identity: Identity = Depends(current_identity)):
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=? AND tenant_id=?", (job_id, identity.tenant_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(row)


@app.get("/v1/jobs/{job_id}/artifacts/{artifact_name}")
def get_job_artifact(job_id: str, artifact_name: str, identity: Identity = Depends(current_identity)):
    artifact_files = {
        "capture_manifest": ("capture-ingest.json", "application/json"),
        "sfm_summary": ("sfm/capture_splat_sfm_summary.json", "application/json"),
        "camera_poses": ("sfm/sparse/0/images.txt", "text/plain"),
        "sparse_points": ("sfm/sparse/0/points3D.txt", "text/plain"),
        "surface_mesh": ("dense/surface.ply", "application/ply"),
    }
    if artifact_name not in artifact_files:
        raise HTTPException(status_code=404, detail="Artifact not found")
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=? AND tenant_id=? AND kind='sparse_reconstruction'",
                         (job_id, identity.tenant_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    result = json.loads(row["output_json"]) if row["output_json"] else None
    if row["status"] != "completed" or not result or not any(item.get("name") == artifact_name for item in result.get("artifacts", [])):
        raise HTTPException(status_code=404, detail="Artifact is not available")
    root = get_settings().reconstruction_root.resolve()
    path = (root / row["project_id"] / row["id"] / artifact_files[artifact_name][0]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact is not available")
    return FileResponse(path, media_type=artifact_files[artifact_name][1], filename=path.name)
