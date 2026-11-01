# Phone video → walkable scene

Training can only be as sharp as the video it learns from, so how you record matters more than any training setting.

## 1. Record (any phone)

- **Camera:** 4K at 30 fps, or 1080p at 60 fps. Use the main lens, not ultra-wide.
- **Lock focus and exposure:** long-press the screen until you see AE/AF LOCK (iPhone), or use Pro mode on Android.
- **Light:** bright and even. Turn the room lights on and avoid strong sunlight patches.
- **Move slowly:** take about one step every 2 seconds and turn slowly. If a paused frame looks blurry, you are moving too fast.
- **Path:** walk 2–3 loops around the room, once at chest height, once higher pointing slightly down, and once lower pointing slightly up. Then walk through the middle.
- **Avoid** people walking around, mirrors, TV screens that are on, and pointing the camera at a bare white wall.
- **Length:** 2–4 minutes per room.

## 2. Set up the tools once

These steps are already done on this machine. Run them again on a new Windows PC (Python 3.10, NVIDIA driver 550 or newer):

```powershell
# COLMAP 4.2.1 with CUDA, unpacked to tools\colmap-4.2.1 (found automatically)
curl -L -o colmap.zip https://github.com/colmap/colmap/releases/download/4.2.1/colmap-x64-windows-cuda.zip
tar -xf colmap.zip -C tools; ren tools\colmap-x64-windows-cuda colmap-4.2.1   # folder name may differ

# Training environment in .venv (found automatically)
py -3.10 -m venv .venv
.venv\Scripts\pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu124
.venv\Scripts\pip install "gsplat==1.5.3+pt24cu124" --extra-index-url https://docs.gsplat.studio/whl/pt24cu124
.venv\Scripts\pip install -r tools\requirements-gsplat-windows.txt
.venv\Scripts\python tools\patch_pycolmap_windows.py
git clone --depth 1 --branch v1.5.3 https://github.com/nerfstudio-project/gsplat external\gsplat
```

gsplat publishes only one prebuilt Windows build: torch 2.4 + CUDA 12.4 + Python 3.10, which is why those versions are pinned. No C++ or CUDA compiler is needed, because `tools/fused-ssim-torch` replaces the one compiled add-on.

Check everything with:

```powershell
python pipeline/video_to_scene.py --check
```

**GPU:** a 4 GB laptop GPU can run the `draft` preset. The `final` preset needs about 16–24 GB of GPU memory. Rent a cloud GPU (RTX 4090 or A100) for that step; `pipeline-capture-splat/scripts/setup_cloud_nvidia.sh` sets one up.

## 3. Run

```powershell
# Quick check of the capture (about 20–40 min on a laptop GPU)
python pipeline/video_to_scene.py --video room.mp4 --name my-room --preset draft

# Best quality (cloud GPU, about 30–60 min)
python pipeline/video_to_scene.py --video room.mp4 --name my-room --preset final
```

Each step is skipped if its output already exists, so you can re-run after a failure. Use `--stop-after colmap` to check that the camera positions solved before paying for GPU time. If COLMAP warns that fewer than 70% of frames registered, re-record rather than train.

## 4. View

The script copies the scene into `frontend/namma-space/public/scenes/<name>/` and writes `scene-config.ts.txt` next to it. Paste that config into `src/config/sceneConfig.ts`, add it to the scene list, then run `npm run dev` in `frontend/namma-space`. Use the Editor panel in the viewer to set the starting camera and room bounds.
