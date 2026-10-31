from __future__ import annotations

import hashlib
import hmac
import math
import os
from pathlib import Path
import re
import uuid

from fastapi import HTTPException, Request, status
from PIL import Image
from pillow_heif import register_heif_opener

from .auth import Identity
from .database import connect, transaction
from .schemas import UploadCreate, UploadCreated
from .settings import get_settings

register_heif_opener()

SUPPORTED_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif",
    "video/mp4", "video/quicktime", "video/webm", "application/pdf",
    "application/vnd.ply", "model/ply", "application/octet-stream",
}
SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


def _upload_row(upload_id: str, identity: Identity):
    with connect() as db:
        row = db.execute("SELECT * FROM uploads WHERE id=? AND tenant_id=?", (upload_id, identity.tenant_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return row


def _validate_declared_type(content_type: str, category: str) -> str:
    normalized = content_type.lower().split(";", 1)[0].strip()
    if normalized not in SUPPORTED_TYPES:
        raise HTTPException(status_code=415, detail="Supported files are JPEG, PNG, WebP, HEIC/HEIF, MP4, MOV, WebM, or PDF")
    if category in {"room_image", "extra_image"} and not normalized.startswith("image/"):
        raise HTTPException(status_code=415, detail="Photo uploads must use an image format")
    if category == "video" and not normalized.startswith("video/"):
        raise HTTPException(status_code=415, detail="Video upload must use a supported video format")
    if category == "floor_plan" and normalized not in {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}:
        raise HTTPException(status_code=415, detail="Floor plans must be PDF or a supported image")
    if category == "sensor_data" and normalized not in {"application/vnd.ply", "model/ply", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Sensor evidence currently supports PLY point clouds only")
    return normalized


def create_upload(project_id: str, data: UploadCreate, identity: Identity) -> UploadCreated:
    settings = get_settings()
    if data.byte_size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the configured upload limit")
    content_type = _validate_declared_type(data.content_type, data.category)
    upload_id = str(uuid.uuid4())
    expected_parts = math.ceil(data.byte_size / settings.upload_chunk_bytes)
    with transaction(immediate=True) as db:
        project = db.execute("SELECT id FROM projects WHERE id=? AND tenant_id=?", (project_id, identity.tenant_id)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        existing = db.execute(
            """SELECT * FROM uploads WHERE project_id=? AND tenant_id=? AND original_name=?
               AND category=? AND COALESCE(side,'')=COALESCE(?,'') AND byte_size=? ORDER BY created_at DESC LIMIT 1""",
            (project_id, identity.tenant_id, data.filename, data.category, data.side, data.byte_size),
        ).fetchone()
        if existing and existing["status"] in {"receiving", "complete"}:
            part_rows = db.execute("SELECT part_number FROM upload_parts WHERE upload_id=? ORDER BY part_number", (existing["id"],)).fetchall()
            return UploadCreated(upload_id=existing["id"], chunk_size=settings.upload_chunk_bytes, expected_parts=expected_parts,
                                 uploaded_parts=[row["part_number"] for row in part_rows], status=existing["status"])
        db.execute(
            """INSERT INTO uploads(id, project_id, tenant_id, original_name, content_type, category, side,
               byte_size, expected_sha256, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,'receiving',datetime('now'))""",
            (upload_id, project_id, identity.tenant_id, data.filename, content_type, data.category, data.side,
             data.byte_size, data.sha256.lower() if data.sha256 else None),
        )
    return UploadCreated(upload_id=upload_id, chunk_size=settings.upload_chunk_bytes, expected_parts=expected_parts, uploaded_parts=[], status="receiving")


async def receive_part(upload_id: str, part_number: int, request: Request, identity: Identity, declared_sha256: str | None) -> dict:
    settings = get_settings()
    row = _upload_row(upload_id, identity)
    if row["status"] != "receiving":
        if row["status"] == "complete":
            return {"upload_id": upload_id, "part_number": part_number, "status": "already_complete"}
        raise HTTPException(status_code=409, detail="Upload is not accepting parts")
    expected_parts = math.ceil(row["byte_size"] / settings.upload_chunk_bytes)
    if part_number < 0 or part_number >= expected_parts:
        raise HTTPException(status_code=416, detail="Chunk number is outside the expected upload range")

    buffer = bytearray()
    async for chunk in request.stream():
        if len(buffer) + len(chunk) > settings.upload_chunk_bytes:
            raise HTTPException(status_code=413, detail="Chunk exceeds the configured chunk size")
        buffer.extend(chunk)
    expected_size = min(settings.upload_chunk_bytes, row["byte_size"] - part_number * settings.upload_chunk_bytes)
    if len(buffer) != expected_size:
        raise HTTPException(status_code=400, detail="Chunk size does not match the expected range")
    digest = hashlib.sha256(buffer).hexdigest()
    if declared_sha256 and (not SHA256_PATTERN.fullmatch(declared_sha256) or not hmac.compare_digest(digest, declared_sha256.lower())):
        raise HTTPException(status_code=400, detail="Chunk checksum mismatch")

    settings.storage_root.mkdir(parents=True, exist_ok=True)
    part_dir = settings.storage_root / "tmp" / upload_id
    part_dir.mkdir(parents=True, exist_ok=True)
    key = str(Path("tmp") / upload_id / f"part-{part_number:08d}-{digest}.bin")
    destination = settings.storage_root / key

    with transaction(immediate=True) as db:
        current = db.execute("SELECT status FROM uploads WHERE id=? AND tenant_id=?", (upload_id, identity.tenant_id)).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Upload not found")
        if current["status"] != "receiving":
            raise HTTPException(status_code=409, detail="Upload is no longer receiving parts")
        existing = db.execute("SELECT * FROM upload_parts WHERE upload_id=? AND part_number=?", (upload_id, part_number)).fetchone()
        if existing:
            if existing["sha256"] != digest:
                raise HTTPException(status_code=409, detail="A different chunk is already stored at this position")
            return {"upload_id": upload_id, "part_number": part_number, "status": "already_received"}
        temporary = destination.with_suffix(f".tmp-{uuid.uuid4().hex}")
        temporary.write_bytes(buffer)
        os.replace(temporary, destination)
        db.execute("INSERT INTO upload_parts(upload_id, part_number, byte_size, sha256, storage_key) VALUES(?,?,?,?,?)",
                   (upload_id, part_number, len(buffer), digest, key))
    return {"upload_id": upload_id, "part_number": part_number, "status": "received"}


def _validate_file(path: Path, content_type: str) -> None:
    try:
        if content_type.startswith("image/"):
            with Image.open(path) as image:
                image.verify()
                if image.format not in {"JPEG", "PNG", "WEBP", "HEIF", "HEIC"}:
                    raise ValueError("Image format does not match the supported set")
        elif content_type == "application/pdf":
            with path.open("rb") as source:
                if source.read(5) != b"%PDF-":
                    raise ValueError("Invalid PDF signature")
        elif content_type in {"video/mp4", "video/quicktime"}:
            with path.open("rb") as source:
                header = source.read(16)
                if len(header) < 12 or header[4:8] != b"ftyp":
                    raise ValueError("Invalid MP4/MOV file signature")
        elif content_type == "video/webm":
            with path.open("rb") as source:
                if source.read(4) != bytes.fromhex("1a45dfa3"):
                    raise ValueError("Invalid WebM file signature")
        elif content_type in {"application/vnd.ply", "model/ply", "application/octet-stream"}:
            with path.open("rb") as source:
                header = source.read(65536)
            if not _is_valid_ply_header(header):
                raise ValueError("Invalid PLY point-cloud header")
    except Exception as exc:
        raise HTTPException(status_code=415, detail="File content could not be validated for its declared type") from exc


def _is_valid_ply_header(data: bytes) -> bool:
    """Accept standard ASCII or binary PLY files with a declared vertex element."""
    if not data.startswith((b"ply\n", b"ply\r\n")):
        return False
    endings = (b"end_header\n", b"end_header\r\n")
    header_end = next((index for ending in endings if (index := data.find(ending)) >= 0), -1)
    if header_end < 0:
        return False
    try:
        lines = data[:header_end].decode("ascii").replace("\r", "").splitlines()
    except UnicodeDecodeError:
        return False
    formats = {"format ascii 1.0", "format binary_little_endian 1.0", "format binary_big_endian 1.0"}
    has_format = any(line.strip() in formats for line in lines)
    has_vertices = False
    for line in lines:
        parts = line.strip().split()
        if len(parts) == 3 and parts[:2] == ["element", "vertex"] and parts[2].isdigit():
            has_vertices = int(parts[2]) > 0
            break
    return has_format and has_vertices


def complete_upload(upload_id: str, identity: Identity) -> dict:
    settings = get_settings()
    row = _upload_row(upload_id, identity)
    if row["status"] == "complete":
        return {"upload_id": upload_id, "status": "complete", "sha256": row["actual_sha256"]}
    if row["status"] != "receiving":
        raise HTTPException(status_code=409, detail="Upload cannot be completed")
    expected_parts = math.ceil(row["byte_size"] / settings.upload_chunk_bytes)
    with connect() as db:
        parts = db.execute("SELECT * FROM upload_parts WHERE upload_id=? ORDER BY part_number", (upload_id,)).fetchall()
    if len(parts) != expected_parts or [part["part_number"] for part in parts] != list(range(expected_parts)):
        raise HTTPException(status_code=409, detail="Upload is incomplete; resume missing chunks first")

    project_dir = settings.storage_root / "objects" / row["project_id"]
    project_dir.mkdir(parents=True, exist_ok=True)
    final_key = str(Path("objects") / row["project_id"] / f"{upload_id}.bin")
    final_path = settings.storage_root / final_key
    temporary = final_path.with_suffix(".partial")
    digest = hashlib.sha256()
    total = 0
    try:
        with temporary.open("wb") as output:
            for part in parts:
                part_path = settings.storage_root / part["storage_key"]
                with part_path.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        total += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total != row["byte_size"]:
            raise HTTPException(status_code=400, detail="Uploaded file size does not match its declaration")
        actual_sha256 = digest.hexdigest()
        if row["expected_sha256"] and not hmac.compare_digest(actual_sha256, row["expected_sha256"].lower()):
            raise HTTPException(status_code=400, detail="Uploaded file checksum does not match")
        _validate_file(temporary, row["content_type"])
        os.replace(temporary, final_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    with transaction(immediate=True) as db:
        db.execute("UPDATE uploads SET status='complete', actual_sha256=?, storage_key=? WHERE id=? AND tenant_id=? AND status='receiving'",
                   (actual_sha256, final_key, upload_id, identity.tenant_id))
    return {"upload_id": upload_id, "status": "complete", "sha256": actual_sha256}
