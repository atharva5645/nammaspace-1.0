from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
import cv2
import numpy as np


@dataclass
class CaptureFilterConfig:
    """Configuration for Stage 1: Capture Preprocessing (Video/Image Ingestion & Quality Filters)."""
    extraction_fps: Optional[float] = 2.0  # FPS to extract from video; None = extract all
    min_laplacian_var: float = 80.0       # Minimum Laplacian variance; frames below are blurred
    min_mean_luminance: float = 35.0      # Minimum grayscale mean (0-255); below is under-exposed
    max_mean_luminance: float = 225.0     # Maximum grayscale mean (0-255); above is over-exposed
    max_shadow_clip_ratio: float = 0.35   # Max allowed fraction of pixels in shadow ([0, 15])
    max_highlight_clip_ratio: float = 0.35 # Max allowed fraction of pixels in highlight ([240, 255])
    near_duplicate_threshold: float = 0.95 # Similarity threshold (0-1) against last kept frame
    max_frames_cap: Optional[int] = None  # Optional cap: evenly subsample if kept count exceeds this
    output_image_format: str = "jpg"      # "jpg" or "png"
    jpeg_quality: int = 95
    ffmpeg_binary: Optional[str] = None   # Explicit ffmpeg binary, or auto-detect


@dataclass
class Stage1CaptureResult:
    """Results and telemetry from Stage 1 Capture Preprocessing."""
    success: bool
    input_source: str
    stage1_dir: Path
    total_frames_extracted: int
    kept_frames_count: int
    dropped_counts: dict[str, int]
    drop_reasons: list[dict[str, Any]]
    output_image_paths: list[Path]
    duration_seconds: float
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "input_source": self.input_source,
            "stage1_dir": str(self.stage1_dir),
            "total_frames_extracted": self.total_frames_extracted,
            "kept_frames_count": self.kept_frames_count,
            "dropped_counts": self.dropped_counts,
            "drop_reasons": self.drop_reasons,
            "output_image_count": len(self.output_image_paths),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


def compute_laplacian_variance(image_bgr: np.ndarray) -> float:
    """Compute Laplacian variance for blur detection. Higher = sharper."""
    if len(image_bgr.shape) == 3:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_bgr
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return float(laplacian.var())


def compute_exposure_metrics(image_bgr: np.ndarray) -> dict[str, float]:
    """Compute histogram-based exposure metrics (mean luminance and clipping ratios)."""
    if len(image_bgr.shape) == 3:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_bgr

    total_pixels = float(gray.size)
    mean_lum = float(np.mean(gray))

    # Fast histogram calculation across 256 bins
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    shadow_pixels = float(np.sum(hist[:16]))      # [0, 15]
    highlight_pixels = float(np.sum(hist[240:]))  # [240, 255]

    return {
        "mean_luminance": mean_lum,
        "shadow_ratio": shadow_pixels / total_pixels if total_pixels > 0 else 0.0,
        "highlight_ratio": highlight_pixels / total_pixels if total_pixels > 0 else 0.0,
    }


def compute_frame_similarity(curr_bgr: np.ndarray, prev_bgr: np.ndarray) -> float:
    """Compute similarity score in [0, 1] between current and previous frame.
    
    Combines:
      1. Structural intensity similarity (thumbnail MSE)
      2. 3-channel color histogram correlation
    """
    # Downsample to 64x64 for fast, noise-tolerant spatial intensity comparison
    curr_small = cv2.resize(curr_bgr, (64, 64), interpolation=cv2.INTER_AREA)
    prev_small = cv2.resize(prev_bgr, (64, 64), interpolation=cv2.INTER_AREA)
    
    pixel_diff = np.mean(np.abs(curr_small.astype(float) - prev_small.astype(float)))
    pixel_sim = max(0.0, 1.0 - (pixel_diff / 255.0))

    # Color histogram correlation across B, G, R
    correlations = []
    for c in range(3):
        h_curr = cv2.calcHist([curr_small], [c], None, [32], [0, 256])
        h_prev = cv2.calcHist([prev_small], [c], None, [32], [0, 256])
        cv2.normalize(h_curr, h_curr)
        cv2.normalize(h_prev, h_prev)
        corr = cv2.compareHist(h_curr, h_prev, cv2.HISTCMP_CORREL)
        correlations.append(max(0.0, corr))

    hist_sim = float(np.mean(correlations))
    # Balanced ensemble similarity
    return float(0.5 * pixel_sim + 0.5 * hist_sim)


def find_ffmpeg_executable(custom_path: Optional[str] = None) -> Optional[str]:
    """Locate ffmpeg binary in PATH or specified path."""
    if custom_path and Path(custom_path).exists():
        return str(Path(custom_path).resolve())
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg
    return None


def extract_frames_from_video(
    video_path: Path,
    temp_dir: Path,
    fps: Optional[float] = None,
    ffmpeg_bin: Optional[str] = None,
) -> list[Path]:
    """Extract frames from a video file using FFmpeg with cv2.VideoCapture fallback."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = find_ffmpeg_executable(ffmpeg_bin)

    if ffmpeg_exe is not None:
        cmd = [ffmpeg_exe, "-v", "error", "-i", str(video_path)]
        if fps is not None and fps > 0:
            cmd.extend(["-vf", f"fps={fps}"])
        out_pattern = temp_dir / "extracted_%06d.jpg"
        cmd.extend(["-q:v", "2", str(out_pattern)])
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        extracted = sorted(temp_dir.glob("extracted_*.jpg"))
        if res.returncode == 0 and extracted:
            return extracted

    # Fallback to OpenCV VideoCapture (robust on all systems)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(1, int(round(native_fps / fps))) if (fps and fps > 0) else 1

    extracted_paths: list[Path] = []
    frame_idx = 0
    saved_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            saved_idx += 1
            frame_path = temp_dir / f"extracted_{saved_idx:06d}.jpg"
            cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            extracted_paths.append(frame_path)
        frame_idx += 1

    cap.release()
    return extracted_paths


def load_frames_from_dir(dir_path: Path) -> list[Path]:
    """Scan and sort valid image files from an input directory."""
    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    files = [p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in valid_exts]
    return sorted(files)


def run_stage1_capture(
    input_source: Path | str,
    output_dir: Path | str,
    config: Optional[CaptureFilterConfig] = None,
) -> Stage1CaptureResult:
    """Execute complete Stage 1 Capture Preprocessing.
    
    Filters:
      1. Laplacian-variance blur detection
      2. Histogram-based under/over-exposure detection
      3. Near-duplicate detection against last accepted frame
      4. Optional even frame-count decimation cap
    """
    start_time = time.time()
    cfg = config or CaptureFilterConfig()
    in_src = Path(input_source).resolve()
    out_base = Path(output_dir).resolve()
    stage1_dir = out_base / "stage1"
    stage1_dir.mkdir(parents=True, exist_ok=True)

    if not in_src.exists():
        return Stage1CaptureResult(
            success=False,
            input_source=str(in_src),
            stage1_dir=stage1_dir,
            total_frames_extracted=0,
            kept_frames_count=0,
            dropped_counts={},
            drop_reasons=[],
            output_image_paths=[],
            duration_seconds=time.time() - start_time,
            error=f"Input source does not exist: {in_src}",
        )

    # 1. Ingest input frames (either from video extraction or direct image directory)
    temp_extract_dir: Optional[Path] = None
    if in_src.is_file():
        temp_extract_dir = out_base / ".temp_extracted_frames"
        raw_frames = extract_frames_from_video(
            in_src,
            temp_extract_dir,
            fps=cfg.extraction_fps,
            ffmpeg_bin=cfg.ffmpeg_binary,
        )
    elif in_src.is_dir():
        raw_frames = load_frames_from_dir(in_src)
    else:
        return Stage1CaptureResult(
            success=False,
            input_source=str(in_src),
            stage1_dir=stage1_dir,
            total_frames_extracted=0,
            kept_frames_count=0,
            dropped_counts={},
            drop_reasons=[],
            output_image_paths=[],
            duration_seconds=time.time() - start_time,
            error=f"Input source is neither a file nor a directory: {in_src}",
        )

    total_extracted = len(raw_frames)
    if total_extracted == 0:
        return Stage1CaptureResult(
            success=False,
            input_source=str(in_src),
            stage1_dir=stage1_dir,
            total_frames_extracted=0,
            kept_frames_count=0,
            dropped_counts={"empty_input": 0},
            drop_reasons=[],
            output_image_paths=[],
            duration_seconds=time.time() - start_time,
            error="No frames extracted or found in input source",
        )

    # 2. Sequential frame filtering
    dropped_counts: dict[str, int] = {
        "blur_detected": 0,
        "under_exposed": 0,
        "over_exposed": 0,
        "near_duplicate": 0,
        "frame_cap_decimated": 0,
    }
    drop_reasons: list[dict[str, Any]] = []

    surviving_frames_data: list[tuple[Path, np.ndarray, dict[str, Any]]] = []
    last_kept_image: Optional[np.ndarray] = None

    for idx, frame_path in enumerate(raw_frames):
        img_bgr = cv2.imread(str(frame_path))
        if img_bgr is None:
            dropped_counts["blur_detected"] += 1
            drop_reasons.append({
                "frame_index": idx,
                "file_name": frame_path.name,
                "reason": "unreadable_image",
            })
            continue

        # A. Exposure Filter (Check first: pitch black or blown-out frames have no edges)
        exp_metrics = compute_exposure_metrics(img_bgr)
        mean_lum = exp_metrics["mean_luminance"]
        shadow_ratio = exp_metrics["shadow_ratio"]
        highlight_ratio = exp_metrics["highlight_ratio"]

        if mean_lum < cfg.min_mean_luminance or shadow_ratio > cfg.max_shadow_clip_ratio:
            dropped_counts["under_exposed"] += 1
            drop_reasons.append({
                "frame_index": idx,
                "file_name": frame_path.name,
                "reason": "under_exposed",
                "mean_luminance": round(mean_lum, 2),
                "shadow_ratio": round(shadow_ratio, 3),
            })
            continue

        if mean_lum > cfg.max_mean_luminance or highlight_ratio > cfg.max_highlight_clip_ratio:
            dropped_counts["over_exposed"] += 1
            drop_reasons.append({
                "frame_index": idx,
                "file_name": frame_path.name,
                "reason": "over_exposed",
                "mean_luminance": round(mean_lum, 2),
                "highlight_ratio": round(highlight_ratio, 3),
            })
            continue

        # B. Blur Filter (Laplacian variance on properly exposed frames)
        lap_var = compute_laplacian_variance(img_bgr)
        if lap_var < cfg.min_laplacian_var:
            dropped_counts["blur_detected"] += 1
            drop_reasons.append({
                "frame_index": idx,
                "file_name": frame_path.name,
                "reason": "blur_detected",
                "laplacian_variance": round(lap_var, 2),
                "threshold": cfg.min_laplacian_var,
            })
            continue

        # C. Near-Duplicate Filter (against last kept frame)
        similarity = 0.0
        if last_kept_image is not None:
            similarity = compute_frame_similarity(img_bgr, last_kept_image)
            if similarity > cfg.near_duplicate_threshold:
                dropped_counts["near_duplicate"] += 1
                drop_reasons.append({
                    "frame_index": idx,
                    "file_name": frame_path.name,
                    "reason": "near_duplicate",
                    "similarity": round(similarity, 4),
                    "threshold": cfg.near_duplicate_threshold,
                })
                continue

        # Frame passed all sequential gates
        last_kept_image = img_bgr.copy()
        frame_metrics = {
            "laplacian_variance": round(lap_var, 2),
            "mean_luminance": round(mean_lum, 2),
            "shadow_ratio": round(shadow_ratio, 3),
            "highlight_ratio": round(highlight_ratio, 3),
            "similarity_to_prev": round(similarity, 4),
        }
        surviving_frames_data.append((frame_path, img_bgr, frame_metrics))

    # 3. Optional Even Frame-Count Decimation Cap
    final_selected = surviving_frames_data
    if cfg.max_frames_cap is not None and len(surviving_frames_data) > cfg.max_frames_cap:
        cap_val = max(1, cfg.max_frames_cap)
        indices = np.linspace(0, len(surviving_frames_data) - 1, cap_val, dtype=int)
        indices_set = set(indices.tolist())

        decimated_retained = []
        for s_idx, item in enumerate(surviving_frames_data):
            if s_idx in indices_set:
                decimated_retained.append(item)
            else:
                dropped_counts["frame_cap_decimated"] += 1
                drop_reasons.append({
                    "frame_index": s_idx,
                    "file_name": item[0].name,
                    "reason": "frame_cap_decimated",
                })
        final_selected = decimated_retained

    # 4. Write surviving frames to stage1 folder
    output_image_paths: list[Path] = []
    frames_manifest: list[dict[str, Any]] = []

    ext = cfg.output_image_format.lower().lstrip(".")
    for out_idx, (orig_path, img_bgr, metrics) in enumerate(final_selected, start=1):
        target_name = f"frame_{out_idx:05d}.{ext}"
        target_path = stage1_dir / target_name

        if ext in {"jpg", "jpeg"}:
            cv2.imwrite(str(target_path), img_bgr, [cv2.IMWRITE_JPEG_QUALITY, cfg.jpeg_quality])
        elif ext == "png":
            cv2.imwrite(str(target_path), img_bgr, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        else:
            cv2.imwrite(str(target_path), img_bgr)

        output_image_paths.append(target_path)
        frames_manifest.append({
            "target_filename": target_name,
            "original_filename": orig_path.name,
            **metrics,
        })

    # Save metadata manifest inside stage1 folder
    manifest_path = stage1_dir / "frames_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(frames_manifest, f, indent=2)

    # Clean up temporary extraction folder if used
    if temp_extract_dir and temp_extract_dir.exists():
        shutil.rmtree(temp_extract_dir, ignore_errors=True)

    return Stage1CaptureResult(
        success=True,
        input_source=str(in_src),
        stage1_dir=stage1_dir,
        total_frames_extracted=total_extracted,
        kept_frames_count=len(output_image_paths),
        dropped_counts=dropped_counts,
        drop_reasons=drop_reasons,
        output_image_paths=output_image_paths,
        duration_seconds=time.time() - start_time,
    )
