import sys
import os
import time
from pathlib import Path
import torch
import numpy as np
from scipy.spatial.transform import Rotation as R

sys.path.insert(0, "E:/Nammaspace-1.0/pipeline-capture-splat/external/gsplat-v1.5.3")
from gsplat import export_splats

BASE_DIR = Path("E:/Nammaspace-1.0")
CKPT_PATH = BASE_DIR / "data/experiments/supermarket001_chunk50_rectified_sharp/splat/ckpts/ckpt_2499_rank0.pt"
SPARSE_DIR = BASE_DIR / "data/experiments/supermarket001_chunk50_rectified/sparse/0"
OUT_PLY = BASE_DIR / "data/experiments/supermarket001_chunk50_rectified_sharp/splat/ply/supermarket_chunk50_aligned_clean.ply"
OUT_PLY.parent.mkdir(parents=True, exist_ok=True)

print(f"Loading checkpoint: {CKPT_PATH}")
ckpt = torch.load(CKPT_PATH, map_location="cpu")
splats = ckpt["splats"]

means = splats["means"].numpy()
scales_tensor = torch.exp(splats["scales"])
scales = scales_tensor.numpy()
quats = splats["quats"].numpy()  # [w, x, y, z] in gsplat
opacities = torch.sigmoid(splats["opacities"]).squeeze(-1).numpy()
sh0 = splats["sh0"].numpy()
shN = splats["shN"].numpy()

# 1. Parse COLMAP camera poses to find exact ground plane and aisle alignment
with open(SPARSE_DIR / "images.txt", "r") as f:
    lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

cams = []
for i in range(0, len(lines), 2):
    p = lines[i].split()
    qw, qx, qy, qz = float(p[1]), float(p[2]), float(p[3]), float(p[4])
    tx, ty, tz = float(p[5]), float(p[6]), float(p[7])
    rot = R.from_quat([qx, qy, qz, qw]).as_matrix()
    c = -rot.T @ np.array([tx, ty, tz])
    fwd = rot.T @ np.array([0, 0, 1])
    up = -rot.T @ np.array([0, 1, 0])
    cams.append((c, fwd, up))

cam_pos = np.array([c[0] for c in cams])
cam_fwd = np.array([c[1] for c in cams])
cam_up = np.array([c[2] for c in cams])

mid_idx = len(cams) // 2
c0 = cam_pos[mid_idx]

# World UP vector (averaged from physical upright camera positions)
up_vec = cam_up.mean(axis=0)
up_vec = up_vec / np.linalg.norm(up_vec)

# World Forward vector down aisle
fwd_vec = cam_fwd.mean(axis=0)
fwd_vec = fwd_vec - np.dot(fwd_vec, up_vec) * up_vec
fwd_vec = fwd_vec / np.linalg.norm(fwd_vec)

# Right vector
right_vec = np.cross(fwd_vec, up_vec)

# Alignment rotation matrix:
# X -> right_vec
# Y -> up_vec (upright ground normal)
# Z -> -fwd_vec (down aisle is -Z in PlayCanvas convention)
R_align = np.column_stack([right_vec, up_vec, -fwd_vec]).T
rot_align = R.from_matrix(R_align)

print("Computed R_align determinant:", np.linalg.det(R_align))

# Transform positions: center around mid camera and align
means_aligned = (means - c0) @ R_align.T

# Shift Y so the physical floor is at Y = 0.0
# The floor sits at roughly Y = -0.90 in aligned space
floor_y = -0.90
means_aligned[:, 1] -= floor_y

# 2. Comprehensive Spatial & Floater Filter
max_s = scales.max(axis=1)
min_s = scales.min(axis=1)
aspect = max_s / (min_s + 1e-7)

# Culling masks:
# - Y in [0.0, 2.6]: strictly between ground floor and ceiling (removes floor mirror reflections and ceiling floaters)
# - X in [-1.5, 3.0]: covers aisle path and product shelves
# - Z in [-3.0, 3.0]: covers chunk length
# - max_scale <= 0.035m: no giant blurry floaters
# - aspect <= 5.0: prune extreme ray-elongated needles
# - opacity >= 0.12: prune faint haze
mask = (
    (means_aligned[:, 1] >= 0.01) & (means_aligned[:, 1] <= 2.5) &
    (means_aligned[:, 0] >= -1.5) & (means_aligned[:, 0] <= 3.0) &
    (means_aligned[:, 2] >= -3.0) & (means_aligned[:, 2] <= 3.0) &
    (max_s <= 0.035) &
    (aspect <= 5.0) &
    (opacities >= 0.12)
)

N_kept = mask.sum()
print(f"Total: {len(means):,}, Kept after alignment + floater filter: {N_kept:,} ({N_kept/len(means)*100:.1f}%)")

k_means = means_aligned[mask]
k_scales = scales[mask].copy()
k_quats = quats[mask]
k_opacities = splats["opacities"].numpy()[mask]
k_sh0 = sh0[mask]
k_shN = shN[mask]

# 3. Anisotropy Clamping: force aspect ratio <= 2.2:1
# This converts needle-like Gaussians into smooth, compact disks/pebbles
k_max = k_scales.max(axis=1, keepdims=True)
target_min = k_max / 2.2
k_scales = np.maximum(k_scales, target_min)
# Cap upper scale at 2.5cm
k_scales = np.clip(k_scales, a_min=None, a_max=0.025)

# 4. Transform Quaternions: q_new = R_align * q_orig
# gsplat quaternions are stored as [w, x, y, z]
# scipy uses [x, y, z, w]
q_scipy = k_quats[:, [1, 2, 3, 0]]
r_orig = R.from_quat(q_scipy)
r_new = rot_align * r_orig
q_new_scipy = r_new.as_quat()
# Convert back to [w, x, y, z] for gsplat
k_quats_aligned = q_new_scipy[:, [3, 0, 1, 2]]

# 5. Export to PLY
print(f"Exporting upright, needle-free PLY to: {OUT_PLY}...")
t0 = time.time()
export_splats(
    means=torch.from_numpy(k_means).float(),
    scales=torch.from_numpy(np.log(k_scales)).float(),
    quats=torch.from_numpy(k_quats_aligned).float(),
    opacities=torch.from_numpy(k_opacities).float(),
    sh0=torch.from_numpy(k_sh0).float(),
    shN=torch.from_numpy(k_shN).float(),
    format="ply",
    save_to=str(OUT_PLY),
)
print(f"Done in {time.time() - t0:.2f}s! File size: {OUT_PLY.stat().st_size / (1024*1024):.2f} MB")
