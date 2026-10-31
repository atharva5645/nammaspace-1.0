"""Isolated adapter to the existing Capture Splat/COLMAP sparse-SfM runner."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SfMToolchainUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SfMRun:
    summary: dict[str, Any]
    summary_path: Path
    sparse_model_dir: Path
    camera_poses_path: Path
    sparse_points_path: Path


def run_sparse_sfm(
    images_dir: Path,
    output_dir: Path,
    capture_splat_binary: str = "capture-splat",
    colmap_binary: str = "colmap",
    timeout_seconds: int = 3600,
) -> SfMRun:
    """Run the existing CPU-capable SIFT/exhaustive COLMAP pipeline.

    This returns sparse camera/point evidence, not a watertight architecture
    mesh. Dense reconstruction and room-surface extraction are separate stages.
    """
    executable = shutil.which(capture_splat_binary)
    if executable is None and capture_splat_binary == "capture-splat":
        # Editable installs on Windows commonly put console scripts in the
        # interpreter's Scripts directory without adding it to PATH.
        script_name = "capture-splat.exe" if os.name == "nt" else "capture-splat"
        candidate = Path(sysconfig.get_path("scripts") or "") / script_name
        executable = str(candidate) if candidate.is_file() else None
    if executable is None:
        raise SfMToolchainUnavailable(
            "capture_splat_cli_missing",
            f"Install pipeline-capture-splat in the API worker environment; executable {capture_splat_binary!r} was not found.",
        )
    colmap_executable = shutil.which(colmap_binary)
    if colmap_executable is None and Path(colmap_binary).is_file():
        colmap_executable = str(Path(colmap_binary).resolve())
    if colmap_executable is None and colmap_binary == "colmap":
        bundled = Path(__file__).resolve().parents[2] / "tools" / "colmap-4.2.1" / "bin" / ("colmap.exe" if os.name == "nt" else "colmap")
        if bundled.is_file():
            colmap_executable = str(bundled.resolve())
    if colmap_executable is None:
        raise SfMToolchainUnavailable("colmap_binary_missing", f"COLMAP executable {colmap_binary!r} was not found.")
    if not images_dir.is_dir():
        raise ValueError("Prepared image directory does not exist")
    output_dir.mkdir(parents=True, exist_ok=False)
    command = [
        executable, "sfm",
        "--images", str(images_dir.resolve()),
        "--out", str(output_dir.resolve()),
        "--method", "incremental",
        "--matcher", "exhaustive",
        "--features", "sift",
        "--camera-policy", "single",
        "--masks", "off",
        "--allow-cpu-matching",
    ]
    try:
        # Capture Splat invokes COLMAP subcommands by name. Prepend the binary's
        # directory so Windows can also resolve its adjacent runtime DLLs.
        environment = os.environ.copy()
        colmap_directory = str(Path(colmap_executable).resolve().parent)
        environment["PATH"] = colmap_directory + os.pathsep + environment.get("PATH", "")
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds,
                                   check=False, env=environment)
    except subprocess.TimeoutExpired as error:
        raise SfMToolchainUnavailable("sfm_timeout", "Sparse reconstruction exceeded its configured time limit.") from error
    except OSError as error:
        raise SfMToolchainUnavailable("sfm_process_start_failed", "Could not start the configured SfM process.") from error

    summary_path = output_dir / "capture_splat_sfm_summary.json"
    if not summary_path.is_file():
        raise SfMToolchainUnavailable("sfm_summary_missing", "SfM runner did not produce its required summary artifact.")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SfMToolchainUnavailable("sfm_summary_invalid", "SfM summary artifact is unreadable.") from error
    if completed.returncode != 0 or summary.get("decision") not in {"promote", "hold"}:
        decision = summary.get("decision", "failed")
        failed_command = summary.get("failed_command") or []
        if len(failed_command) > 1 and failed_command[1] == "mapper":
            raise SfMToolchainUnavailable(
                "sfm_mapper_failed",
                "COLMAP could not form a stable camera pair from these views. Add more sharply focused photos with substantial overlap between adjacent viewpoints.",
            )
        raise SfMToolchainUnavailable(f"sfm_{decision}", "SfM did not produce an accepted sparse reconstruction.")

    sparse_model_dir = output_dir / "sparse" / "0"
    camera_poses_path = sparse_model_dir / "images.txt"
    sparse_points_path = sparse_model_dir / "points3D.txt"
    if not camera_poses_path.is_file() or not sparse_points_path.is_file():
        raise SfMToolchainUnavailable("sfm_sparse_artifacts_missing", "COLMAP sparse model is missing camera or point artifacts.")
    return SfMRun(summary, summary_path, sparse_model_dir, camera_poses_path, sparse_points_path)
