from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .database import connect, transaction
from .settings import get_settings

logger = logging.getLogger(__name__)


class EvidenceAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    category: Literal["room_image", "extra_image", "video", "floor_plan", "sensor_data"]
    side: Literal["side1", "side2", "side3", "side4"] | None
    content_type: str
    storage_key: str


class ProjectSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str
    room_name: str
    units: Literal["m", "ft"]
    known_distance: float = Field(gt=0)
    anchor_name: str = "Measured span"
    anchor_start_label: str = "Endpoint A"
    anchor_end_label: str = "Endpoint B"
    anchor_view_side: Literal["side1", "side2", "side3", "side4"] = "side1"
    anchor_source: Literal["tape", "laser", "floor_plan", "sensor"] = "tape"
    anchor_confidence: Literal["high", "medium", "low"] = "medium"
    anchor_start_pick: dict[str, Any] | None = None
    anchor_end_pick: dict[str, Any] | None = None
    room_length: float | None = None
    room_width: float | None = None
    openings: list[dict[str, Any]] = Field(default_factory=list)
    ceiling_height: float | None
    sop_version: str
    sop_acknowledgments: list[str]


class CaptureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_version: Literal["capture-input.v1"]
    project: ProjectSnapshot
    evidence: list[EvidenceAsset]


class JobEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["spatial-job.v1"]
    job_id: str
    job_type: Literal["capture_preflight", "sparse_reconstruction"]
    tenant_id: str
    project_id: str
    input: CaptureInput


class JobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_version: Literal["spatial-result.v1"] = "spatial-result.v1"
    job_id: str
    job_type: Literal["capture_preflight", "sparse_reconstruction"]
    status: Literal["succeeded"] = "succeeded"
    output: dict[str, Any]
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class JobHandler(Protocol):
    def __call__(self, envelope: JobEnvelope) -> JobResult: ...


def _capture_preflight(envelope: JobEnvelope) -> JobResult:
    from .preflight import build_report

    report = build_report(
        envelope.project_id,
        envelope.tenant_id,
        upload_ids=[asset.upload_id for asset in envelope.input.evidence],
        project_snapshot={
            **envelope.input.project.model_dump(),
            "evidence": [asset.model_dump() for asset in envelope.input.evidence],
        },
    )
    return JobResult(job_id=envelope.job_id, job_type=envelope.job_type, output={"report": report})


def _sparse_reconstruction(envelope: JobEnvelope) -> JobResult:
    import sys
    from pathlib import Path

    engine_root = Path(__file__).resolve().parents[3] / "spatial-engine"
    if str(engine_root) not in sys.path:
        sys.path.insert(0, str(engine_root))
    from reconstruction.ingest import prepare_capture_images
    from reconstruction.dense_adapter import run_dense_surface
    from reconstruction.sfm_adapter import run_sparse_sfm

    settings = get_settings()
    root = settings.reconstruction_root.resolve()
    workspace = (root / envelope.project_id / envelope.job_id).resolve()
    if not workspace.is_relative_to(root):
        raise ValueError("reconstruction_workspace_path_invalid")
    workspace.mkdir(parents=True, exist_ok=True)
    prepared = prepare_capture_images(
        [asset.model_dump() for asset in envelope.input.evidence], settings.storage_root, workspace,
    )
    run = run_sparse_sfm(
        prepared.images_dir, workspace / "sfm", colmap_binary=settings.colmap_binary,
    )
    points = sum(1 for line in run.sparse_points_path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#"))
    base_url = f"/v1/jobs/{envelope.job_id}/artifacts"
    surface_path = None
    surface_error = None
    try:
        surface_path = run_dense_surface(
            run.sparse_model_dir, run.sparse_model_dir.parents[1] / "images", workspace / "dense",
            image=settings.dense_colmap_image, docker_binary=settings.docker_binary,
        )
    except Exception as error:
        surface_error = {
            "code": getattr(error, "code", "dense_reconstruction_failed"),
            "message": str(error) if getattr(error, "code", None) else "Dense reconstruction did not complete.",
        }
    artifacts = [
        {"name": "capture_manifest", "url": f"{base_url}/capture_manifest", "media_type": "application/json"},
        {"name": "sfm_summary", "url": f"{base_url}/sfm_summary", "media_type": "application/json"},
        {"name": "camera_poses", "url": f"{base_url}/camera_poses", "media_type": "text/plain"},
        {"name": "sparse_points", "url": f"{base_url}/sparse_points", "media_type": "text/plain"},
    ]
    if surface_path:
        artifacts.append({"name": "surface_mesh", "url": f"{base_url}/surface_mesh", "media_type": "application/ply"})
    return JobResult(
        job_id=envelope.job_id,
        job_type=envelope.job_type,
        output={
            "stage": "dense_surface" if surface_path else "sparse_reconstruction",
            "registered_image_count": (run.summary.get("model") or {}).get("registered_images"),
            "sparse_point_count": points,
            "surface_generated": surface_path is not None,
            "surface_error": surface_error,
            "surface_format": "PLY" if surface_path else None,
            "metric_scale_registered": False,
            "architectural_wireframe_generated": False,
            "message": "A dense surface mesh was generated from the uploaded images. It remains in reconstruction-relative scale and needs human review." if surface_path else f"Photo alignment succeeded, but surface generation failed: {surface_error['message']}",
        },
        artifacts=artifacts,
    )


HANDLERS: dict[str, JobHandler] = {
    "capture_preflight": _capture_preflight,
    "sparse_reconstruction": _sparse_reconstruction,
}


def migrate_legacy_queued_jobs() -> int:
    """Snapshot queued v0 development jobs created before versioned envelopes existed."""
    migrated = 0
    with transaction(immediate=True) as db:
        legacy_jobs = db.execute(
            "SELECT * FROM jobs WHERE status='queued' AND (input_json='{}' OR input_json IS NULL)"
        ).fetchall()
        for job in legacy_jobs:
            if job["kind"] not in HANDLERS:
                db.execute("UPDATE jobs SET status='failed',error_code='unsupported_legacy_job_type',finished_at=datetime('now'),updated_at=datetime('now') WHERE id=?", (job["id"],))
                continue
            project = db.execute("SELECT * FROM projects WHERE id=? AND tenant_id=?", (job["project_id"], job["tenant_id"])).fetchone()
            evidence_rows = db.execute(
                "SELECT * FROM uploads WHERE project_id=? AND tenant_id=? AND status='complete' ORDER BY created_at,id",
                (job["project_id"], job["tenant_id"]),
            ).fetchall()
            if project is None or any(not upload["actual_sha256"] or not upload["storage_key"] for upload in evidence_rows):
                db.execute("UPDATE jobs SET status='failed',error_code='legacy_job_snapshot_unavailable',finished_at=datetime('now'),updated_at=datetime('now') WHERE id=?", (job["id"],))
                continue
            envelope = JobEnvelope(
                contract_version="spatial-job.v1", job_id=job["id"], job_type="capture_preflight",
                tenant_id=job["tenant_id"], project_id=job["project_id"],
                input=CaptureInput(
                    snapshot_version="capture-input.v1",
                    project=ProjectSnapshot(
                        project_name=project["project_name"], room_name=project["room_name"], units=project["units"],
                        known_distance=project["known_distance"], anchor_name=project["anchor_name"],
                        anchor_start_label=project["anchor_start_label"], anchor_end_label=project["anchor_end_label"],
                        anchor_view_side=project["anchor_view_side"], anchor_source=project["anchor_source"],
                        anchor_confidence=project["anchor_confidence"],
                        anchor_start_pick=json.loads(project["anchor_picks_json"]).get("start"),
                        anchor_end_pick=json.loads(project["anchor_picks_json"]).get("end"), ceiling_height=project["ceiling_height"],
                        room_length=project["room_length"], room_width=project["room_width"], openings=json.loads(project["openings_json"]),
                        sop_version=project["sop_version"], sop_acknowledgments=json.loads(project["sop_acknowledgments_json"]),
                    ),
                    evidence=[EvidenceAsset(upload_id=upload["id"], sha256=upload["actual_sha256"], category=upload["category"],
                                            side=upload["side"], content_type=upload["content_type"], storage_key=upload["storage_key"])
                              for upload in evidence_rows],
                ),
            )
            db.execute("UPDATE jobs SET contract_version=?,input_json=?,updated_at=datetime('now') WHERE id=?",
                       (envelope.contract_version, envelope.model_dump_json(), job["id"]))
            migrated += 1
    return migrated


def process_one_job() -> bool:
    worker_id = str(uuid.uuid4())
    with transaction(immediate=True) as db:
        row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at, id LIMIT 1").fetchone()
        if row is None:
            return False
        updated = db.execute(
            """UPDATE jobs SET status='running', attempt_count=attempt_count+1, worker_id=?,
               started_at=datetime('now'), updated_at=datetime('now') WHERE id=? AND status='queued'""",
            (worker_id, row["id"]),
        ).rowcount
        if updated != 1:
            return False
        logger.info("Claimed %s job %s (attempt %s)", row["kind"], row["id"], row["attempt_count"] + 1)

    try:
        envelope = JobEnvelope.model_validate_json(row["input_json"])
        if envelope.job_id != row["id"] or envelope.tenant_id != row["tenant_id"] or envelope.project_id != row["project_id"]:
            raise ValueError("job_envelope_identity_mismatch")
        if envelope.contract_version != row["contract_version"] or envelope.job_type != row["kind"]:
            raise ValueError("job_envelope_contract_mismatch")
        handler = HANDLERS.get(envelope.job_type)
        if handler is None:
            raise LookupError("unsupported_job_type")
        result = handler(envelope)
        result_json = result.model_dump_json()
        report = result.output.get("report")
        with transaction(immediate=True) as db:
            db.execute(
                """UPDATE jobs SET status='completed', output_json=?, report_json=?, error_code=NULL,
                   finished_at=datetime('now'), updated_at=datetime('now') WHERE id=? AND status='running' AND worker_id=?""",
                (result_json, json.dumps(report, separators=(",", ":")) if report is not None else None, row["id"], worker_id),
            )
        logger.info("Completed job %s", row["id"])
    except ValidationError:
        _fail_job(row["id"], worker_id, "invalid_job_contract")
    except LookupError:
        _fail_job(row["id"], worker_id, "unsupported_job_type")
    except ValueError as exc:
        code = str(exc) if str(exc).startswith("job_envelope_") else "worker_processing_failed"
        logger.exception("Spatial worker rejected job %s", row["id"])
        _fail_job(row["id"], worker_id, code)
    except Exception as exc:
        logger.exception("Spatial worker failed job %s", row["id"])
        error_code = getattr(exc, "code", "worker_processing_failed")
        _fail_job(row["id"], worker_id, error_code if isinstance(error_code, str) else "worker_processing_failed")
    return True


def _fail_job(job_id: str, worker_id: str, error_code: str) -> None:
    with transaction(immediate=True) as db:
        db.execute(
            """UPDATE jobs SET status='failed', error_code=?, finished_at=datetime('now'), updated_at=datetime('now')
               WHERE id=? AND status='running' AND worker_id=?""",
            (error_code, job_id, worker_id),
        )
    logger.error("Job %s failed: %s", job_id, error_code)
