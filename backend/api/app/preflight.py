from __future__ import annotations

import json
import hashlib

from PIL import Image, ImageFilter, ImageOps, ImageStat
from pillow_heif import register_heif_opener

from .database import connect
from .settings import get_settings

register_heif_opener()


def build_report(project_id: str, tenant_id: str, upload_ids: list[str] | None = None,
                 project_snapshot: dict | None = None) -> dict:
    """Inspect capture files and report evidence-quality signals; this is not reconstruction."""
    with connect() as db:
        project = db.execute("SELECT * FROM projects WHERE id=? AND tenant_id=?", (project_id, tenant_id)).fetchone()
        if upload_ids is None:
            uploads = db.execute(
                "SELECT * FROM uploads WHERE project_id=? AND tenant_id=? AND status='complete' ORDER BY created_at, id",
                (project_id, tenant_id),
            ).fetchall()
        elif upload_ids:
            placeholders = ",".join("?" for _ in upload_ids)
            uploads = db.execute(
                f"SELECT * FROM uploads WHERE project_id=? AND tenant_id=? AND status='complete' AND id IN ({placeholders}) ORDER BY created_at, id",
                (project_id, tenant_id, *upload_ids),
            ).fetchall()
        else:
            uploads = []
    if project is None:
        raise ValueError("project_missing")

    images: list[dict] = []
    side_counts = {f"side{i}": 0 for i in range(1, 5)}
    seen_hashes: dict[str, str] = {}
    duplicate_names: list[str] = []
    perceptual_hashes: list[tuple[str, str, int]] = []
    near_duplicate_pairs: list[dict[str, str | int]] = []
    evidence_hashes = {asset["upload_id"]: asset["sha256"] for asset in (project_snapshot or {}).get("evidence", [])}
    for upload in uploads:
        if not upload["content_type"].startswith("image/"):
            continue
        if upload["id"] in evidence_hashes and upload["actual_sha256"] != evidence_hashes[upload["id"]]:
            images.append({"upload_id": upload["id"], "filename": upload["original_name"], "category": upload["category"],
                           "side": upload["side"], "findings": ["evidence_hash_mismatch"]})
            continue
        path = get_settings().storage_root / upload["storage_key"]
        try:
            with Image.open(path) as source:
                source.verify()
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                width, height = image.size
                small = image.copy()
                small.thumbnail((512, 512))
                gray = small.convert("L")
                brightness = round(ImageStat.Stat(gray).mean[0], 1)
                edge_mean = round(ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0], 2)
                laplacian = gray.filter(ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128))
                laplacian_variance = round(ImageStat.Stat(laplacian).var[0], 2)
                tiny = gray.resize((9, 8), Image.Resampling.LANCZOS)
                pixels = list(tiny.getdata())
                image_hash = 0
                for row in range(8):
                    for column in range(8):
                        image_hash = (image_hash << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
            digest = upload["actual_sha256"] or hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen_hashes:
                duplicate_names.append(upload["original_name"])
            seen_hashes[digest] = upload["original_name"]
            for previous_name, _previous_side, previous_hash in perceptual_hashes:
                distance = (image_hash ^ previous_hash).bit_count()
                if distance <= 3:
                    near_duplicate_pairs.append({"first": previous_name, "second": upload["original_name"], "hash_distance": distance})
            perceptual_hashes.append((upload["original_name"], upload["side"] or "", image_hash))
            if upload["category"] == "room_image" and upload["side"] in side_counts:
                side_counts[upload["side"]] += 1
            findings = []
            if min(width, height) < 720:
                findings.append("low_resolution")
            if brightness < 28:
                findings.append("very_dark")
            elif brightness > 245:
                findings.append("overexposed")
            if edge_mean < 3.0:
                findings.append("low_detail_possible")
            if laplacian_variance < 24.0:
                findings.append("blur_possible")
            images.append({
                "upload_id": upload["id"], "filename": upload["original_name"], "category": upload["category"],
                "side": upload["side"], "width_px": width, "height_px": height,
                "brightness_mean": brightness, "edge_detail_mean": edge_mean,
                "laplacian_variance": laplacian_variance, "exif_orientation_applied": True, "findings": findings,
            })
        except Exception:
            images.append({"upload_id": upload["id"], "filename": upload["original_name"], "category": upload["category"],
                           "side": upload["side"], "findings": ["image_decode_failed"]})

    required_sides = [side for side, count in side_counts.items() if count == 0]
    image_count = len(images)
    warnings = []
    if required_sides:
        warnings.append({"code": "missing_side_coverage", "sides": required_sides})
    if duplicate_names:
        warnings.append({"code": "duplicate_images", "filenames": sorted(set(duplicate_names))})
    if near_duplicate_pairs:
        warnings.append({"code": "near_duplicate_images", "pairs": near_duplicate_pairs,
                         "message": "Perceptual hash similarity is a review hint; verify that viewpoints add useful coverage."})
    if any(image.get("findings") for image in images):
        warnings.append({"code": "image_quality_review", "message": "Review image-level findings before reconstruction."})
    if image_count < 4:
        warnings.append({"code": "few_images", "count": image_count})
    return {
        "report_version": "capture-preflight.v1",
        "scope": "media_quality_and_coverage_only",
        "reconstruction_started": False,
        "metric_accuracy_validated": False,
        "project": {"name": (project_snapshot or {}).get("project_name", project["project_name"]),
                    "room": (project_snapshot or {}).get("room_name", project["room_name"]),
                    "units": (project_snapshot or {}).get("units", project["units"]),
                    "known_distance": (project_snapshot or {}).get("known_distance", project["known_distance"]),
                    "anchor": {
                        "name": (project_snapshot or {}).get("anchor_name", project["anchor_name"]),
                        "start_label": (project_snapshot or {}).get("anchor_start_label", project["anchor_start_label"]),
                        "end_label": (project_snapshot or {}).get("anchor_end_label", project["anchor_end_label"]),
                        "view_side": (project_snapshot or {}).get("anchor_view_side", project["anchor_view_side"]),
                        "source": (project_snapshot or {}).get("anchor_source", project["anchor_source"]),
                        "confidence": (project_snapshot or {}).get("anchor_confidence", project["anchor_confidence"]),
                        "start_pick": (project_snapshot or {}).get("anchor_start_pick", json.loads(project["anchor_picks_json"]).get("start")),
                        "end_pick": (project_snapshot or {}).get("anchor_end_pick", json.loads(project["anchor_picks_json"]).get("end")),
                    },
                    "room_length": (project_snapshot or {}).get("room_length", project["room_length"]),
                    "room_width": (project_snapshot or {}).get("room_width", project["room_width"]),
                    "openings": (project_snapshot or {}).get("openings", json.loads(project["openings_json"])),
                    "ceiling_height": (project_snapshot or {}).get("ceiling_height", project["ceiling_height"]),
                    "sop_version": (project_snapshot or {}).get("sop_version", project["sop_version"]),
                    "sop_acknowledgments": (project_snapshot or {}).get("sop_acknowledgments", json.loads(project["sop_acknowledgments_json"]))},
        "summary": {"image_count": image_count, "side_counts": side_counts, "video_count": sum(u["category"] == "video" for u in uploads),
                    "floor_plan_count": sum(u["category"] == "floor_plan" for u in uploads),
                    "sensor_data_count": sum(u["category"] == "sensor_data" for u in uploads),
                    "near_duplicate_pair_count": len(near_duplicate_pairs), "warning_count": len(warnings)},
        "images": images, "warnings": warnings,
        "next_step": "review_capture_and_submit_for_reconstruction_when_pipeline_is_configured",
    }
