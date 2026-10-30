"""Camera Lens Undistortion and Geometric Calibration Module.

Converts non-linear camera models (e.g. SIMPLE_RADIAL, RADIAL, OPENCV) into
calibrated, distortion-free PINHOLE camera models for 3D Gaussian Splatting,
preventing multi-view ray divergence and edge blurring.
"""

from __future__ import annotations

import struct
import shutil
import time
from pathlib import Path
from typing import Any, Optional
import cv2
import numpy as np


def rectify_colmap_model_and_images(
    src_sparse_dir: Path | str,
    src_images_dir: Path | str,
    dst_dir: Path | str,
    # Sharpening and CLAHE are lossy. They raise a frame's Laplacian variance
    # without adding information, bake halos into the training targets, and make
    # a splat model look crisp only at the exact training view. Keep both OFF
    # for reconstruction input; enable them only for human-facing previews.
    apply_sharpening: bool = False,
    apply_clahe: bool = False,
    unsharp_strength: float = 0.20,
    unsharp_radius: float = 1.2,
    clahe_clip_limit: float = 1.2,
) -> dict[str, Any]:
    """Batch undistort camera distortion and synchronize COLMAP sparse tracks."""
    src_sparse = Path(src_sparse_dir).resolve()
    src_images = Path(src_images_dir).resolve()
    dst = Path(dst_dir).resolve()
    
    dst_sparse = dst / "sparse" / "0"
    dst_images = dst / "images"
    dst_sparse.mkdir(parents=True, exist_ok=True)
    dst_images.mkdir(parents=True, exist_ok=True)
    
    t0 = time.time()
    
    # 1. Parse cameras.txt
    cameras = {}
    cameras_txt = src_sparse / "cameras.txt"
    if not cameras_txt.exists():
        raise FileNotFoundError(f"Missing {cameras_txt}")
        
    with open(cameras_txt, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            cam_id = int(parts[0])
            model = parts[1]
            width = int(parts[2])
            height = int(parts[3])
            params = [float(p) for p in parts[4:]]
            cameras[cam_id] = {
                "model": model,
                "width": width,
                "height": height,
                "params": params,
            }

    rect_maps = {}
    new_cameras = {}
    for cam_id, cam in cameras.items():
        w, h = cam["width"], cam["height"]
        model = cam["model"]
        params = cam["params"]
        
        if model == "SIMPLE_RADIAL":
            f, cx, cy, k1 = params[0], params[1], params[2], params[3]
            K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]], dtype=np.float64)
            dist = np.array([k1, 0, 0, 0, 0], dtype=np.float64)
        elif model == "RADIAL":
            f, cx, cy, k1, k2 = params[0], params[1], params[2], params[3], params[4]
            K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]], dtype=np.float64)
            dist = np.array([k1, k2, 0, 0, 0], dtype=np.float64)
        elif model == "PINHOLE":
            fx, fy, cx, cy = params[0], params[1], params[2], params[3]
            K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]], dtype=np.float64)
            dist = np.zeros(5, dtype=np.float64)
        else:
            # Fallback
            f = params[0]
            cx, cy = (params[1], params[2]) if len(params) > 2 else (w / 2.0, h / 2.0)
            K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]], dtype=np.float64)
            dist = np.zeros(5, dtype=np.float64)

        new_K, roi = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), 0, (w, h))
        mapx, mapy = cv2.initUndistortRectifyMap(K, dist, None, new_K, (w, h), cv2.CV_32FC1)

        rect_maps[cam_id] = {
            "K": K,
            "dist": dist,
            "new_K": new_K,
            "mapx": mapx,
            "mapy": mapy,
        }
        new_cameras[cam_id] = {
            "width": w,
            "height": h,
            "fx": new_K[0, 0],
            "fy": new_K[1, 1],
            "cx": new_K[0, 2],
            "cy": new_K[1, 2],
        }

    # 2. Map images to cameras
    image_cam_map = {}
    images_txt = src_sparse / "images.txt"
    with open(images_txt, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 9 and ("jpg" in parts[-1].lower() or "png" in parts[-1].lower()):
                img_id = int(parts[0])
                cam_id = int(parts[8])
                img_name = parts[9]
                image_cam_map[img_name] = (img_id, cam_id)

    # 3. Batch rectify and optionally sharpen images
    all_imgs = sorted(list(src_images.glob("*.jpg")) + list(src_images.glob("*.png")))
    clahe_obj = cv2.createCLAHE(clipLimit=clahe_clip_limit, tileGridSize=(8, 8)) if apply_clahe else None
    
    processed_images = 0
    for img_p in all_imgs:
        cam_id = image_cam_map.get(img_p.name, (None, 1))[1]
        if cam_id not in rect_maps:
            cam_id = 1
        maps = rect_maps[cam_id]
        
        im = cv2.imread(str(img_p))
        if im is None:
            continue
            
        undist = cv2.remap(im, maps["mapx"], maps["mapy"], cv2.INTER_LANCZOS4)
        
        out_im = undist
        if apply_sharpening:
            blur = cv2.GaussianBlur(undist, (0, 0), unsharp_radius)
            out_im = cv2.addWeighted(undist, 1.0 + unsharp_strength, blur, -unsharp_strength, 0)
            
        if clahe_obj is not None:
            lab = cv2.cvtColor(out_im, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            cl = clahe_obj.apply(l)
            out_im = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
            
        cv2.imwrite(str(dst_images / img_p.name), out_im, [cv2.IMWRITE_JPEG_QUALITY, 98])
        processed_images += 1

    # 4. Write new PINHOLE cameras
    with open(dst_sparse / "cameras.txt", "w", encoding="utf-8") as f:
        f.write("# Camera list with one line of data per camera:\n")
        f.write("#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
        f.write(f"# Number of cameras: {len(new_cameras)}\n")
        for cam_id, nc in new_cameras.items():
            f.write(f"{cam_id} PINHOLE {nc['width']} {nc['height']} {nc['fx']} {nc['fy']} {nc['cx']} {nc['cy']}\n")

    with open(dst_sparse / "cameras.bin", "wb") as f:
        f.write(struct.pack("<Q", len(new_cameras)))
        for cam_id, nc in new_cameras.items():
            # PINHOLE model ID is 1
            f.write(struct.pack("<iiQQ", cam_id, 1, nc["width"], nc["height"]))
            f.write(struct.pack("<dddd", nc["fx"], nc["fy"], nc["cx"], nc["cy"]))

    # 5. Transform 2D feature observations in images.txt and images.bin
    new_image_lines = []
    with open(images_txt, "r", encoding="utf-8") as f:
        img_lines = f.readlines()

    i = 0
    header_lines = []
    while i < len(img_lines):
        line = img_lines[i].strip()
        if not line or line.startswith("#"):
            header_lines.append(img_lines[i])
            i += 1
            continue

        parts = line.split()
        cam_id = int(parts[8])
        maps = rect_maps.get(cam_id, rect_maps[1])

        i += 1
        pts_line = img_lines[i].strip() if i < len(img_lines) else ""
        pts_parts = pts_line.split()

        if len(pts_parts) >= 3:
            n_pts = len(pts_parts) // 3
            coords = np.zeros((n_pts, 1, 2), dtype=np.float64)
            p3d_ids = []
            for p_idx in range(n_pts):
                coords[p_idx, 0, 0] = float(pts_parts[p_idx * 3])
                coords[p_idx, 0, 1] = float(pts_parts[p_idx * 3 + 1])
                p3d_ids.append(int(pts_parts[p_idx * 3 + 2]))

            undist_pts = cv2.undistortPoints(coords, maps["K"], maps["dist"], P=maps["new_K"])
            undist_pts = undist_pts.reshape(-1, 2)

            new_pts_tokens = []
            for p_idx in range(n_pts):
                new_pts_tokens.append(f"{undist_pts[p_idx, 0]:.4f}")
                new_pts_tokens.append(f"{undist_pts[p_idx, 1]:.4f}")
                new_pts_tokens.append(str(p3d_ids[p_idx]))
            new_pts_line = " ".join(new_pts_tokens)
        else:
            new_pts_line = ""

        new_image_lines.append(line + "\n")
        new_image_lines.append(new_pts_line + "\n")
        i += 1

    with open(dst_sparse / "images.txt", "w", encoding="utf-8") as f:
        f.writelines(header_lines)
        f.writelines(new_image_lines)

    with open(dst_sparse / "images.bin", "wb") as f:
        n_imgs = len(new_image_lines) // 2
        f.write(struct.pack("<Q", n_imgs))
        for k in range(0, len(new_image_lines), 2):
            header = new_image_lines[k].strip().split()
            img_id = int(header[0])
            qw, qx, qy, qz = float(header[1]), float(header[2]), float(header[3]), float(header[4])
            tx, ty, tz = float(header[5]), float(header[6]), float(header[7])
            cam_id = int(header[8])
            name_bytes = header[9].encode("utf-8") + b"\x00"

            pts = new_image_lines[k + 1].strip().split()
            n_pts = len(pts) // 3

            f.write(struct.pack("<i4d3di", img_id, qw, qx, qy, qz, tx, ty, tz, cam_id))
            f.write(name_bytes)
            f.write(struct.pack("<Q", n_pts))
            for p_idx in range(n_pts):
                x = float(pts[p_idx * 3])
                y = float(pts[p_idx * 3 + 1])
                pid = int(pts[p_idx * 3 + 2])
                f.write(struct.pack("<ddq", x, y, pid))

    # 6. Copy 3D points
    if (src_sparse / "points3D.txt").exists():
        shutil.copy2(src_sparse / "points3D.txt", dst_sparse / "points3D.txt")
    if (src_sparse / "points3D.bin").exists():
        shutil.copy2(src_sparse / "points3D.bin", dst_sparse / "points3D.bin")

    duration = time.time() - t0
    return {
        "success": True,
        "processed_images": processed_images,
        "camera_count": len(new_cameras),
        "duration_seconds": duration,
        "dst_dir": str(dst),
    }
