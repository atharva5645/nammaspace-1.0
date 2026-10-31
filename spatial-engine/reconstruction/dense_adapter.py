"""GPU dense multi-view stereo and Poisson surface reconstruction via COLMAP Docker."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .sfm_adapter import SfMToolchainUnavailable


def _run(command: list[str], timeout_seconds: int, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as error:
        raise SfMToolchainUnavailable("dense_reconstruction_timeout", "Dense reconstruction exceeded its configured time limit.") from error
    except OSError as error:
        raise SfMToolchainUnavailable("dense_runtime_unavailable", "Could not start Docker for dense reconstruction.") from error
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").lower()
        if "could not select device driver" in detail or "nvidia" in detail or "gpu" in detail:
            code, message = "dense_gpu_unavailable", "Docker cannot access the NVIDIA GPU. Enable GPU support in Docker Desktop and retry."
        elif "not compiled with cuda" in detail or "cuda support" in detail:
            code, message = "dense_cuda_unavailable", "The selected COLMAP container does not include CUDA PatchMatch support."
        else:
            code, message = "dense_reconstruction_failed", "Dense stereo or surface meshing failed. Review capture overlap and image quality, then retry."
        raise SfMToolchainUnavailable(code, message)
    return result


def run_dense_surface(
    sparse_model_dir: Path,
    images_dir: Path,
    output_dir: Path,
    *,
    image: str = "colmap/colmap:latest",
    docker_binary: str = "docker",
    max_image_size: int = 1400,
    timeout_seconds: int = 7200,
) -> Path:
    """Run undistortion, GPU PatchMatch, stereo fusion, and Poisson meshing.

    Source and output directories are mounted into a short-lived CUDA-enabled
    COLMAP container. The resulting PLY is still in SfM-relative units until
    measured endpoint correspondences are registered.
    """
    executable = shutil.which(docker_binary)
    if executable is None:
        raise SfMToolchainUnavailable("dense_runtime_unavailable", "Docker is not installed or is not available on the worker PATH.")
    sparse_model_dir = sparse_model_dir.resolve()
    images_dir = images_dir.resolve()
    output_dir = output_dir.resolve()
    workspace = sparse_model_dir.parents[2]
    if not (sparse_model_dir / "images.bin").is_file() or not images_dir.is_dir():
        raise SfMToolchainUnavailable("dense_sparse_model_missing", "Dense reconstruction needs a completed COLMAP sparse model and source images.")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        mount = f"type=bind,source={workspace},target=/workspace"
        image_check = _run([executable, "image", "inspect", image], 30, check=False)
        if image_check.returncode != 0:
            raise SfMToolchainUnavailable("dense_image_missing", f"CUDA COLMAP image {image!r} is not downloaded. Pull it in Docker before retrying.")
        gpu = _run([executable, "run", "--rm", "--gpus", "all", "--mount", mount, image, "nvidia-smi"], 90, check=False)
        if gpu.returncode != 0:
            raise SfMToolchainUnavailable("dense_gpu_unavailable", "Docker cannot access the NVIDIA GPU. Enable GPU support in Docker Desktop and retry.")
        commands = [
            ["image_undistorter", "--image_path", "/workspace/sfm/images", "--input_path", "/workspace/sfm/sparse/0", "--output_path", "/workspace/dense", "--output_type", "COLMAP", "--max_image_size", str(max_image_size)],
            ["patch_match_stereo", "--workspace_path", "/workspace/dense", "--workspace_format", "COLMAP", "--PatchMatchStereo.gpu_index", "0", "--PatchMatchStereo.geom_consistency", "true", "--PatchMatchStereo.max_image_size", str(max_image_size)],
            ["stereo_fusion", "--workspace_path", "/workspace/dense", "--workspace_format", "COLMAP", "--input_type", "geometric", "--output_path", "/workspace/dense/fused.ply"],
            # A lower trim threshold retains more of the reconstructed surface.
            # COLMAP's default can trim almost all faces on sparse/noisy indoor captures.
            ["poisson_mesher", "--input_path", "/workspace/dense/fused.ply", "--output_path", "/workspace/dense/surface.ply", "--PoissonMeshing.trim", "1"],
        ]
        for args in commands:
            _run([executable, "run", "--rm", "--gpus", "all", "--mount", mount, "-e", "QT_QPA_PLATFORM=offscreen", image, "colmap", *args], timeout_seconds)
    except SfMToolchainUnavailable:
        raise
    mesh = output_dir / "surface.ply"
    if not mesh.is_file() or mesh.stat().st_size <= 128:
        raise SfMToolchainUnavailable("dense_surface_missing", "COLMAP finished without producing a usable surface mesh.")
    vertex_count, face_count = _ply_element_counts(mesh)
    if vertex_count < 100 or face_count < 100:
        raise SfMToolchainUnavailable(
            "dense_surface_insufficient",
            f"Dense reconstruction produced only {vertex_count} vertices and {face_count} faces. Add sharper, overlapping views of the room and retry.",
        )
    return mesh


def _ply_element_counts(path: Path) -> tuple[int, int]:
    """Read element counts from an ASCII or binary PLY header without loading the mesh."""
    try:
        with path.open("rb") as stream:
            header = bytearray()
            while len(header) < 64 * 1024:
                line = stream.readline()
                if not line:
                    break
                header.extend(line)
                if line.strip() == b"end_header":
                    break
        text = bytes(header).decode("ascii")
    except (OSError, UnicodeDecodeError):
        return 0, 0
    counts: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "element":
            try:
                counts[parts[1]] = int(parts[2])
            except ValueError:
                continue
    return counts.get("vertex", 0), counts.get("face", 0)
