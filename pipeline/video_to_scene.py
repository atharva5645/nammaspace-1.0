"""Phone video -> walkable NammaSpace scene, in one command.

Steps (each one is skipped if its output already exists, so a failed run can be resumed):

  1. frames  - pick the sharpest frame in each time window of the video (OpenCV, no ffmpeg needed)
  2. colmap  - estimate camera positions (COLMAP feature extraction, matching, mapping, undistortion)
  3. train   - train the Gaussian splat with gsplat (needs an NVIDIA GPU with CUDA)
  2b. dense  - only with --hybrid: photogrammetry depth maps + mesh (COLMAP dense, GPU)
  4. export  - with --hybrid, carve away blobs floating in front of measured surfaces
               (tools/carve_splat.py); then remove smoke/floaters (tools/clean_splat.py),
               compress to .sog plus LOD streaming files (splat-transform)
  5. publish - copy the result into frontend/namma-space/public/scenes/<name>/ and write a
               ready-to-paste scene config

Usage:
  python pipeline/video_to_scene.py --check
  python pipeline/video_to_scene.py --video room.mp4 --name my-room --preset draft
  python pipeline/video_to_scene.py --video room.mp4 --name my-room --preset final --gsplat-root external/gsplat

Presets:
  draft  - half resolution, 7k steps, 600k splats. Fits a 4 GB laptop GPU; good for checking a capture.
  final  - full resolution, 30k steps, 1.5M splats. Needs ~16-24 GB VRAM (use a cloud GPU).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = REPO_ROOT / "frontend" / "namma-space" / "public"
SPLAT_TRANSFORM = "@playcanvas/splat-transform@3.10.1"

PRESETS = {
    # packed rasterization trades a little speed for less GPU memory (needed on 4 GB cards)
    "draft": {"data_factor": 2, "steps": 7000, "cap_max": 600_000, "packed": True},
    "final": {"data_factor": 1, "steps": 30000, "cap_max": 1_500_000, "packed": False},
}


def default_colmap() -> str:
    """COLMAP on PATH, else the copy unpacked under tools/colmap-*/ by the setup steps."""
    if shutil.which("colmap"):
        return "colmap"
    for candidate in sorted(REPO_ROOT.glob("tools/colmap-*/**/colmap.exe"), reverse=True):
        return str(candidate)
    for candidate in sorted(REPO_ROOT.glob("tools/colmap-*/**/COLMAP.bat"), reverse=True):
        return str(candidate)
    return "colmap"


def training_python() -> str:
    """The repo's .venv Python (where torch+gsplat are installed), else the current one."""
    venv = REPO_ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return str(venv) if venv.exists() else sys.executable


# --------------------------------------------------------------------------- helpers

def log(msg: str) -> None:
    print(f"[video_to_scene] {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> int:
    log("$ " + " ".join(str(c) for c in cmd))
    started = time.time()
    result = subprocess.run([str(c) for c in cmd], cwd=cwd)
    if result.returncode != 0:
        if check:
            sys.exit(f"Command failed (exit {result.returncode}): {cmd[0]}")
        return result.returncode
    log(f"  done in {time.time() - started:.0f}s")
    return 0


def run_colmap_threaded(cmd: list[str], threads_flag: str, threads: int) -> None:
    """Runs a COLMAP step, retrying with fewer threads if it crashes.

    The COLMAP 4.2.1 Windows build crashes intermittently (0xC0000409) when several
    threads run at once. Feature extraction and matching store finished work in the
    database and skip it on the next run, so a retry continues where the crash happened.
    """
    while True:
        if run(cmd + [threads_flag, str(threads)], check=False) == 0:
            return
        if threads == 1:
            sys.exit(f"COLMAP {cmd[1]} kept crashing even on a single thread.")
        threads = max(1, threads // 2)
        log(f"  COLMAP crashed; resuming with {threads} thread(s)")


def npx() -> str:
    return "npx.cmd" if sys.platform == "win32" else "npx"


def count_registered_images(model_dir: Path) -> int:
    """Number of images COLMAP placed in a sparse model (first 8 bytes of images.bin)."""
    images_bin = model_dir / "images.bin"
    if images_bin.exists():
        with images_bin.open("rb") as f:
            return struct.unpack("<Q", f.read(8))[0]
    images_txt = model_dir / "images.txt"
    if images_txt.exists():
        # Two lines per image; the second (2D points) can be empty, so count only the
        # first lines, which start with the numeric IMAGE_ID followed by 9 more fields.
        lines = [l for l in images_txt.read_text().splitlines() if l and not l.startswith("#")]
        return sum(1 for l in lines if len(l.split()) == 10)
    return 0


# --------------------------------------------------------------------------- tool check

def check_tools(colmap: str, gsplat_root: Path | None) -> bool:
    ok = True

    def report(name: str, good: bool, detail: str, fix: str = "") -> None:
        nonlocal ok
        ok = ok and good
        print(f"  [{'OK ' if good else 'MISSING'}] {name:<14} {detail}")
        if not good and fix:
            print(f"                     fix: {fix}")

    print("Tool check")
    try:
        import cv2  # noqa: F401
        report("opencv", True, "frame extraction")
    except ImportError:
        report("opencv", False, "frame extraction", "pip install opencv-python numpy")

    colmap_path = shutil.which(colmap) or (colmap if Path(colmap).exists() else None)
    report("colmap", bool(colmap_path), colmap_path or "camera pose estimation",
           "download COLMAP 4.x (CUDA build) from https://github.com/colmap/colmap/releases "
           "and pass --colmap <path-to-colmap.exe> or add it to PATH")

    # Training libraries are checked inside the training interpreter (usually .venv)
    py = training_python()
    probe = (
        "import torch, gsplat\n"
        "c = torch.cuda.is_available()\n"
        "d = torch.cuda.get_device_properties(0) if c else None\n"
        "print(torch.__version__, gsplat.__version__, c, d.name if d else '', round(d.total_memory / 2**30, 1) if d else 0)\n"
    )
    setup_hint = "see tools/requirements-gsplat-windows.txt for the install commands"
    result = subprocess.run([py, "-c", probe], capture_output=True, text=True)
    if result.returncode == 0:
        torch_v, gsplat_v, cuda, *gpu = result.stdout.strip().split(" ")
        report("pytorch+cuda", cuda == "True", f"torch {torch_v}, CUDA {cuda}, {' '.join(gpu)} GB ({py})", setup_hint)
        report("gsplat", True, f"gsplat {gsplat_v}")
    else:
        report("pytorch+gsplat", False, f"not importable in {py}", setup_hint)

    result = subprocess.run([py, "-c", "import fused_ssim, pycolmap, viser, nerfview, tyro"], capture_output=True)
    report("trainer deps", result.returncode == 0, "fused_ssim, pycolmap, viser, nerfview, tyro", setup_hint)
    if sys.platform == "win32" and result.returncode == 0:
        probe = ("import inspect, pycolmap.scene_manager as m; "
                 "print(\"struct.unpack('L',\" not in inspect.getsource(m))")
        ok = subprocess.run([py, "-c", probe], capture_output=True, text=True).stdout.strip() == "True"
        report("pycolmap fix", ok, "reads COLMAP .bin files on Windows",
               f"{py} tools/patch_pycolmap_windows.py")

    trainer = gsplat_root / "examples" / "simple_trainer.py" if gsplat_root else None
    report("gsplat repo", bool(trainer and trainer.exists()),
           str(trainer) if trainer else "examples/simple_trainer.py",
           "git clone --depth 1 --branch v1.5.3 https://github.com/nerfstudio-project/gsplat external/gsplat")

    report("node/npx", bool(shutil.which(npx())), "splat-transform (compression + LOD)",
           "install Node.js 20+ from https://nodejs.org")
    return ok


# --------------------------------------------------------------------------- step 1: frames

def extract_frames(video: Path, out_dir: Path, fps: float, max_frames: int,
                   min_sharpness: float, max_width: int) -> int:
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        sys.exit(f"Could not open video: {video}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / src_fps if total else 0
    # Never ask for more frames than max_frames over the whole video
    if duration:
        fps = min(fps, max_frames / duration)
    window = max(1, round(src_fps / fps))
    log(f"video: {total} frames @ {src_fps:.1f} fps ({duration:.0f}s); keeping the sharpest of every {window} frames")

    out_dir.mkdir(parents=True, exist_ok=True)
    kept = rejected = 0
    best = None  # (sharpness, frame)
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        small = frame
        if frame.shape[1] > 960:
            scale = 960 / frame.shape[1]
            small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        if best is None or sharpness > best[0]:
            best = (sharpness, frame)
        index += 1
        if index % window == 0 and best is not None:
            if best[0] >= min_sharpness and 15 < gray.mean() < 240:
                img = best[1]
                if img.shape[1] > max_width:
                    scale = max_width / img.shape[1]
                    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                cv2.imwrite(str(out_dir / f"frame_{kept:05d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                kept += 1
            else:
                rejected += 1
            best = None
    cap.release()
    log(f"kept {kept} frames, rejected {rejected} as blurry/too dark")
    if kept < 50:
        log("WARNING: fewer than 50 usable frames. Recapture more slowly, with better light, for good results.")
    return kept


# --------------------------------------------------------------------------- step 2: colmap

def run_colmap(colmap: str, images: Path, work: Path, frame_count: int, use_gpu: bool) -> Path:
    """Returns a folder laid out as gsplat expects: images/ + sparse/0/."""
    db = work / "database.db"
    sparse = work / "sparse"
    dataset = work / "dataset"
    sparse.mkdir(parents=True, exist_ok=True)
    db.unlink(missing_ok=True)  # a crashed earlier run can leave a half-written database

    # The COLMAP 4.2.1 CUDA build crashes on GPU SIFT with NVIDIA driver 566 (CUDA 12.7),
    # so the CPU is the default. Multi-threaded runs also crash now and then, which
    # run_colmap_threaded handles by resuming with fewer threads.
    gpu = "1" if use_gpu else "0"
    threads = min(6, os.cpu_count() or 4)
    run_colmap_threaded([colmap, "feature_extractor", "--database_path", db, "--image_path", images,
                         "--ImageReader.single_camera", "1", "--ImageReader.camera_model", "OPENCV",
                         "--FeatureExtraction.use_gpu", gpu], "--FeatureExtraction.num_threads", threads)
    if frame_count <= 250:
        match_cmd = [colmap, "exhaustive_matcher", "--database_path", db, "--FeatureMatching.use_gpu", gpu]
    else:
        # Video frames are in order: match each frame with its neighbours (much faster)
        match_cmd = [colmap, "sequential_matcher", "--database_path", db, "--FeatureMatching.use_gpu", gpu,
                     "--SequentialMatching.overlap", "20", "--SequentialMatching.quadratic_overlap", "1"]
    run_colmap_threaded(match_cmd, "--FeatureMatching.num_threads", threads)
    run([colmap, "mapper", "--database_path", db, "--image_path", images, "--output_path", sparse])

    models = [d for d in sparse.iterdir() if d.is_dir()]
    if not models:
        sys.exit("COLMAP could not reconstruct any cameras. The capture needs more overlap/texture.")
    best = max(models, key=count_registered_images)
    registered = count_registered_images(best)
    ratio = registered / max(1, frame_count)
    log(f"COLMAP registered {registered}/{frame_count} frames ({ratio:.0%}) in model {best.name}")
    if ratio < 0.7:
        log("WARNING: under 70% of frames registered. Expect holes; consider recapturing more slowly.")

    run([colmap, "image_undistorter", "--image_path", images, "--input_path", best,
         "--output_path", dataset, "--output_type", "COLMAP"])
    # image_undistorter writes sparse/*.bin; gsplat wants sparse/0/*.bin, and COLMAP's
    # dense step (--hybrid) still needs them in sparse/, so copy rather than move.
    # (on Windows, gsplat's pycolmap needs tools/patch_pycolmap_windows.py to read them)
    target = dataset / "sparse" / "0"
    target.mkdir(parents=True, exist_ok=True)
    for f in (dataset / "sparse").glob("*.bin"):
        shutil.copy2(f, target / f.name)
    return dataset


# --------------------------------------------------------------------------- step 2b: photogrammetry

def find_gpu_colmap(preferred: str) -> str:
    """A COLMAP whose CUDA actually runs here; the dense step has no CPU fallback.

    COLMAP 4.2.1 is built with CUDA 13 and aborts (0xC0000409) on NVIDIA drivers older
    than 580; the 4.0.4 build (CUDA 12.9) runs on driver 566. Each candidate is tested
    with a GPU feature extraction on one small image.
    """
    import cv2
    import numpy as np
    import tempfile
    candidates = [preferred] + [str(p) for p in sorted(REPO_ROOT.glob("tools/colmap-*/COLMAP.bat"))]
    with tempfile.TemporaryDirectory() as tmp:
        img_dir = Path(tmp) / "img"
        img_dir.mkdir()
        rng = np.random.default_rng(0)
        cv2.imwrite(str(img_dir / "a.png"), (rng.random((256, 256)) * 255).astype("uint8"))
        for i, exe in enumerate(dict.fromkeys(candidates)):
            db = Path(tmp) / f"t{i}.db"
            ok = subprocess.run([exe, "feature_extractor", "--database_path", str(db),
                                 "--image_path", str(img_dir), "--FeatureExtraction.use_gpu", "1"],
                                capture_output=True).returncode == 0
            log(f"  GPU test {'passed' if ok else 'failed'}: {exe}")
            if ok:
                return exe
    sys.exit("No COLMAP with working CUDA found. Update the NVIDIA driver, or put a COLMAP build "
             "made with an older CUDA (e.g. 4.0.4) under tools/colmap-*/.")


def run_dense(colmap: str, dataset: Path, max_size: int) -> Path:
    """Photogrammetry: per-photo depth maps, a dense point cloud and a mesh (all on the GPU).

    The depth maps let carve_splat.py delete splat blobs floating in front of real
    surfaces; the mesh is the base for collision and navigation.
    """
    sparse = dataset / "sparse"
    if not list(sparse.glob("*.bin")):  # older runs moved them into sparse/0
        for f in (sparse / "0").glob("*.bin"):
            shutil.copy2(f, sparse / f.name)
    colmap = find_gpu_colmap(colmap)
    run([colmap, "patch_match_stereo", "--workspace_path", dataset, "--workspace_format", "COLMAP",
         "--PatchMatchStereo.max_image_size", str(max_size),
         "--PatchMatchStereo.geom_consistency", "true"])
    run([colmap, "stereo_fusion", "--workspace_path", dataset, "--workspace_format", "COLMAP",
         "--input_type", "geometric", "--output_path", dataset / "fused.ply"])
    run([colmap, "poisson_mesher", "--input_path", dataset / "fused.ply",
         "--output_path", dataset / "mesh.ply"])
    return dataset / "mesh.ply"


# --------------------------------------------------------------------------- step 3: train

def train_gsplat(gsplat_root: Path, dataset: Path, out: Path, preset: dict, bilateral: bool) -> Path:
    trainer = gsplat_root / "examples" / "simple_trainer.py"
    if not trainer.exists():
        sys.exit(f"gsplat trainer not found at {trainer}. Run with --check for setup steps.")
    factor = preset["data_factor"]
    if factor > 1:
        # gsplat's loader requires images_<factor>/ to exist before it will train at reduced size
        import cv2
        small_dir = dataset / f"images_{factor}"
        if not small_dir.exists():
            small_dir.mkdir()
            for src in sorted((dataset / "images").iterdir()):
                img = cv2.imread(str(src))
                if img is None:
                    continue
                size = (round(img.shape[1] / factor), round(img.shape[0] / factor))
                cv2.imwrite(str(small_dir / src.name), cv2.resize(img, size, interpolation=cv2.INTER_AREA),
                            [cv2.IMWRITE_JPEG_QUALITY, 95])
    steps = preset["steps"]
    # gsplat_train.py runs the trainer unchanged but with fewer DataLoader processes (see its docstring)
    cmd = [training_python(), Path(__file__).with_name("gsplat_train.py"), trainer, "mcmc",
           "--data-dir", dataset, "--result-dir", out,
           "--data-factor", str(preset["data_factor"]),
           "--max-steps", str(steps),
           "--eval-steps", str(steps), "--save-steps", str(steps),
           "--save-ply", "--ply-steps", str(steps),
           "--strategy.cap-max", str(preset["cap_max"]),
           "--antialiased",          # removes shimmer/aliasing when viewed at other distances
           "--random-bkgd",          # discourages floaters baked against a fixed background
           "--depth-loss",           # pulls splats onto the COLMAP 3D points instead of mid-air
           "--disable-viewer", "--disable-video"]
    if preset.get("packed"):
        cmd.append("--packed")
    if bilateral:
        # evens out exposure changes between frames, which otherwise bake in as blotchy walls
        cmd.append("--use-bilateral-grid")
    run(cmd, cwd=gsplat_root / "examples")
    plys = sorted((out / "ply").glob("point_cloud_*.ply"), key=lambda p: p.stat().st_mtime)
    if not plys:
        sys.exit("Training finished but no point_cloud_*.ply was written.")
    return plys[-1]


# --------------------------------------------------------------------------- step 4: export

def export_web(ply: Path, out: Path, dense_dataset: Path | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    st = [npx(), "-y", SPLAT_TRANSFORM, "-w"]
    clean = out / "clean.ply"
    half = out / "half.ply"
    sys.path.insert(0, str(Path(__file__).with_name("tools")))
    from clean_splat import SAFE, clean_any, print_report
    if dense_dataset is not None:
        # Hybrid: delete blobs floating in front of surfaces photogrammetry measured.
        # Blobs behind surfaces (reflections) and where there is no depth are kept.
        from carve_splat import carve, export_mesh
        log("carving smoke with photogrammetry depth maps")
        r = carve(ply, dense_dataset, out / "carved.ply")
        log(f"  removed {r['removed_free_space']} floating blobs; "
            f"{r['never_checked_no_depth']} had no depth and were kept")
        ply = out / "carved.ply"
        export_mesh(dense_dataset / "mesh.ply", dense_dataset, out / "mesh.ply")
        log(f"  mesh for collision/navigation (splat coordinates): {out / 'mesh.ply'}")
    # Safe cleanup only: broken blobs and ones far outside the scene. The aggressive
    # opacity/size rules punch holes in white walls of splats trained with depth loss
    # (see tools/clean_splat.py); run that tool by hand on badly trained splats instead.
    # This replaces splat-transform's -F filter, which took 20+ minutes on one CPU core.
    log("removing broken and far-away blobs")
    print_report(clean_any(ply, clean, **SAFE))
    # Single-file version for simple loading (-g 0: compress on the GPU)
    run(st + ["-g", "0", clean, out / "scene.sog"])
    # 50% version for the far-away LOD level
    run(st + [clean, "-d", "50%", half])
    # Streamed LOD bundle: full detail near the camera, half detail further away
    run(st + [clean, "-l", "0", half, "-l", "1", out / "lod" / "lod-meta.json"])
    half.unlink(missing_ok=True)


# --------------------------------------------------------------------------- step 5: publish

def publish(name: str, export_dir: Path, preset_name: str, frames: int) -> None:
    dest = PUBLIC_DIR / "scenes" / name
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(export_dir / "scene.sog", dest / "scene.sog")
    if (dest / "lod").exists():
        shutil.rmtree(dest / "lod")
    shutil.copytree(export_dir / "lod", dest / "lod")

    lod_meta = json.loads((dest / "lod" / "lod-meta.json").read_text())
    lod0 = (lod_meta.get("counts") or [lod_meta.get("count", 500_000)])[0]
    budget = int(lod0 * 1.05)
    ident = "".join(p.capitalize() for p in name.replace("_", "-").split("-"))
    snippet = f"""import type {{ SceneConfig }} from '../types/scene';

// Generated by pipeline/video_to_scene.py ({preset_name} preset, {frames} frames).
// Add it to src/config/sceneConfig.ts and the scene list in App.tsx / NavigationBar.tsx.
// Adjust camera, bounds and transform after a first look in the viewer (the Editor panel helps).
export const {ident[0].lower() + ident[1:]}SceneConfig: SceneConfig = {{
    id: '{name}',
    name: '{name}',
    asset: '/scenes/{name}/scene.sog',
    lodAsset: '/scenes/{name}/lod/lod-meta.json',
    useLod: true,
    splatBudget: {budget},
    splatBudgetMode: 'limit',
    // COLMAP is Y-down; this flips the scene upright for PlayCanvas
    transform: {{ position: [0, 0, 0], rotation: [180, 0, 0], scale: [1, 1, 1] }},
    camera: {{ position: [0, 0, 0], lookAt: [0, 0, -1], fov: 70, clearColor: '#0c0d12' }},
    navigation: {{
        mode: 'first-person',
        eyeHeight: 0,
        movementSpeed: 0.6,
        fastMovementSpeed: 1.5,
        lookSensitivity: 0.12,
        lookSmoothing: 20,
        pitchRange: [-85, 85],
        boundaryMargin: 0.2,
    }},
    bounds: {{ min: [-10, -10, -10], max: [10, 10, 10] }},
    waypoints: [],
    metadata: {{
        splatFormat: 'SOG + streamed LOD',
        gaussianCount: {lod0},
        coordinateConvention: 'COLMAP Y-down / PlayCanvas Y-up',
        captureSource: 'Phone video via video_to_scene.py ({preset_name})',
        graphicsEngine: 'PlayCanvas 2.x WebGL/WebGPU',
        fidelity: '{preset_name}',
    }},
}};
"""
    (dest / "scene-config.ts.txt").write_text(snippet, encoding="utf-8")
    log(f"published to {dest}")
    log(f"scene config to paste: {dest / 'scene-config.ts.txt'}")


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only check which tools are installed")
    ap.add_argument("--video", type=Path, help="input video from the phone (.mp4/.mov)")
    ap.add_argument("--name", help="scene id, e.g. my-room")
    ap.add_argument("--preset", choices=PRESETS, default="draft")
    ap.add_argument("--work-dir", type=Path, help="working folder (default: data/scenes/<name>)")
    ap.add_argument("--colmap", default=default_colmap(), help="colmap executable (default: PATH or tools/colmap-*)")
    ap.add_argument("--colmap-gpu", action="store_true",
                    help="run COLMAP feature extraction/matching on the GPU (needs NVIDIA driver 570+)")
    ap.add_argument("--gsplat-root", type=Path, default=REPO_ROOT / "external" / "gsplat")
    ap.add_argument("--fps", type=float, default=3.0, help="frames kept per second of video")
    ap.add_argument("--max-frames", type=int, default=400)
    ap.add_argument("--min-sharpness", type=float, default=60.0, help="Laplacian variance below this = blurry")
    ap.add_argument("--max-width", type=int, default=1920, help="downscale frames wider than this")
    ap.add_argument("--no-bilateral-grid", dest="bilateral_grid", action="store_false",
                    help="turn off exposure compensation between frames (on by default)")
    ap.add_argument("--steps", type=int, help="override the preset's training steps (e.g. 500 for a quick test)")
    ap.add_argument("--hybrid", action="store_true",
                    help="also run photogrammetry (COLMAP dense) and use its depth maps to carve "
                         "smoke out of the splat; writes a mesh for collision (needs a CUDA COLMAP)")
    ap.add_argument("--dense-size", type=int, default=1000,
                    help="max image size for photogrammetry depth maps (lower = faster, less VRAM)")
    ap.add_argument("--stop-after", choices=["frames", "colmap", "dense", "train", "export", "publish"],
                    default="publish")
    args = ap.parse_args()

    if args.check:
        sys.exit(0 if check_tools(args.colmap, args.gsplat_root) else 1)
    if not args.video or not args.name:
        ap.error("--video and --name are required (or use --check)")

    work = args.work_dir or REPO_ROOT / "data" / "scenes" / args.name
    work.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(work).free / 2**30
    if free_gb < 10:
        # COLMAP crashed repeatedly (0xC0000409, then "SQLite disk I/O error") on a 99% full drive
        log(f"WARNING: only {free_gb:.1f} GB free on the drive holding {work}. COLMAP and training "
            "need ~10 GB of room and crash on a nearly full disk; use --work-dir on another drive.")
    preset = dict(PRESETS[args.preset])
    if args.steps:
        preset["steps"] = args.steps
    frames_dir = work / "frames"
    log(f"working folder: {work}  preset: {args.preset} {preset}")

    # 1. frames
    frames = sorted(frames_dir.glob("*.jpg")) if frames_dir.exists() else []
    if frames:
        log(f"step 1 skipped: {len(frames)} frames already extracted")
        frame_count = len(frames)
    else:
        log("step 1/5: extracting sharp frames")
        frame_count = extract_frames(args.video, frames_dir, args.fps, args.max_frames,
                                     args.min_sharpness, args.max_width)
    if args.stop_after == "frames":
        return

    # 2. colmap
    dataset = work / "colmap" / "dataset"
    if (dataset / "sparse" / "0" / "images.bin").exists():
        log("step 2 skipped: camera poses already computed")
    else:
        log("step 2/5: estimating camera poses with COLMAP")
        dataset = run_colmap(args.colmap, frames_dir, work / "colmap", frame_count, args.colmap_gpu)
    if args.stop_after == "colmap":
        return

    # 2b. photogrammetry (only with --hybrid)
    if args.hybrid:
        if (dataset / "mesh.ply").exists():
            log("step 2b skipped: photogrammetry already done")
        else:
            log("step 2b: photogrammetry depth maps + mesh (COLMAP dense, GPU)")
            run_dense(args.colmap, dataset, args.dense_size)
    if args.stop_after == "dense":
        return

    # 3. train
    train_dir = work / f"train_{args.preset}"
    existing = sorted((train_dir / "ply").glob("point_cloud_*.ply")) if train_dir.exists() else []
    if existing:
        ply = existing[-1]
        log(f"step 3 skipped: using {ply}")
    else:
        log("step 3/5: training the Gaussian splat (this is the long step)")
        ply = train_gsplat(args.gsplat_root, dataset, train_dir, preset, args.bilateral_grid)
    if args.stop_after == "train":
        return

    # 4. export
    export_dir = work / f"web_{args.preset}"
    if (export_dir / "lod" / "lod-meta.json").exists():
        log("step 4 skipped: web files already exported")
    else:
        log("step 4/5: cleaning and compressing for the web")
        export_web(ply, export_dir, dataset if args.hybrid else None)
    if args.stop_after == "export":
        return

    # 5. publish
    log("step 5/5: publishing to the viewer")
    publish(args.name, export_dir, args.preset, frame_count)
    log("finished. Start the viewer with: cd frontend/namma-space && npm run dev")


if __name__ == "__main__":
    main()
