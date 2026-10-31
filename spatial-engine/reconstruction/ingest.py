"""Create a checksum-bound, COLMAP-compatible image workspace from uploaded assets."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

IMAGE_CATEGORIES = {"room_image", "extra_image"}


@dataclass(frozen=True)
class PreparedCapture:
    images_dir: Path
    manifest_path: Path
    image_count: int
    manifest: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_capture_images(
    assets: Sequence[Mapping[str, Any]],
    storage_root: Path,
    workspace: Path,
) -> PreparedCapture:
    """Safely stage still photos and normalize EXIF/HEIC for a COLMAP image directory.

    Original files remain immutable. Output paths are generated from sequence
    numbers, not user-supplied names, and the manifest binds each output image
    back to its upload ID, side assignment, and original checksum.
    """
    root = storage_root.resolve(strict=True)
    job_workspace = workspace.resolve()
    image_assets = sorted(
        (asset for asset in assets if asset.get("category") in IMAGE_CATEGORIES),
        key=lambda asset: (asset.get("side") or "side5", str(asset.get("upload_id", ""))),
    )
    if not image_assets:
        raise ValueError("No still images are available for SfM")

    validated_assets: list[tuple[Mapping[str, Any], Path, str, int, int]] = []
    for asset in image_assets:
        relative_key = Path(str(asset.get("storage_key", "")))
        source = (root / relative_key).resolve(strict=True)
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("Capture asset path escapes the configured storage root")
        expected_hash = str(asset.get("sha256", "")).lower()
        actual_hash = _sha256(source)
        if len(expected_hash) != 64 or actual_hash != expected_hash:
            raise ValueError(f"Capture asset checksum mismatch for upload {asset.get('upload_id', 'unknown')}")
        try:
            with Image.open(source) as image:
                normalized = ImageOps.exif_transpose(image)
                width, height = normalized.size
                if width < 64 or height < 64:
                    raise ValueError("Image dimensions are too small for feature matching")
        except Exception as error:
            raise ValueError(f"Could not inspect capture image {asset.get('upload_id', 'unknown')}") from error
        validated_assets.append((asset, source, actual_hash, width, height))

    # COLMAP's single-camera mode rejects images with different dimensions.
    # Center-crop only the small edge difference, preserving scale and the
    # immutable originals while keeping every staged frame the same size.
    common_width = min(item[3] for item in validated_assets)
    common_height = min(item[4] for item in validated_assets)
    images_dir = job_workspace / "images"
    images_dir.mkdir(parents=True, exist_ok=False)
    prepared_assets: list[dict[str, Any]] = []
    for index, (asset, source, actual_hash, source_width, source_height) in enumerate(validated_assets, start=1):
        output_name = f"{index:04d}.jpg"
        output_path = images_dir / output_name
        try:
            with Image.open(source) as image:
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                left = (normalized.width - common_width) // 2
                top = (normalized.height - common_height) // 2
                normalized = normalized.crop((left, top, left + common_width, top + common_height))
                normalized.save(output_path, format="JPEG", quality=95, optimize=True)
        except Exception as error:
            output_path.unlink(missing_ok=True)
            raise ValueError(f"Could not normalize capture image {asset.get('upload_id', 'unknown')}") from error

        prepared_assets.append({
            "upload_id": str(asset["upload_id"]),
            "source_sha256": actual_hash,
            "source_content_type": str(asset.get("content_type", "")),
            "source_width_px": source_width,
            "source_height_px": source_height,
            "category": str(asset.get("category", "")),
            "side": asset.get("side"),
            "image_name": output_name,
            "image_sha256": _sha256(output_path),
            "width_px": normalized.width,
            "height_px": normalized.height,
            "exif_orientation_applied": True,
            "common_center_crop_applied": source_width != common_width or source_height != common_height,
        })

    manifest = {
        "schema": "nammaspace.capture-ingest.v1",
        "image_count": len(prepared_assets),
        "images": prepared_assets,
        "camera_intrinsics": "unavailable_from_intake",
        "capture_pose_priors": "unavailable_from_intake",
        "metric_scale": "unregistered",
    }
    manifest_path = job_workspace / "capture-ingest.json"
    temporary = manifest_path.with_suffix(".partial")
    temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, manifest_path)
    return PreparedCapture(images_dir, manifest_path, len(prepared_assets), manifest)
