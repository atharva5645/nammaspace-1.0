"""
Level + clean the 25k-step MCMC supermarket model (supermarket001_hq_mcmc).

Why this script exists
----------------------
The currently deployed asset (supermarket_hq_leveled_v2.sog) was built from the
15k-step *gradient* checkpoint. A strictly better checkpoint exists:
supermarket001_hq_mcmc/splat/ply/point_cloud_24999.ply
  - 25,000 steps (vs 15k)
  - MCMCStrategy (cap 1.2M, relocation instead of clone/split split-scatter)
  - trained on supermarket001_full_rectified_sharp (451 rectified sharp frames)
  - LPIPS(alex) + SSIM 0.3, opacity_reg 0.01, scale_reg 0.01

The MCMC run uses ITS OWN COLMAP reconstruction
(supermarket001_full_rectified_sharp/sparse/0), so the leveling matrix and the
centering shifts must be recomputed from that reconstruction - the constants
hardcoded for the seq0_colmap_dense frame (1.35, 1.18, -3.60) DO NOT transfer.

This script:
  1. recomputes the ground-plane rotation from the rectified COLMAP cameras,
  2. levels the MCMC Gaussians,
  3. auto-derives centering shifts (aisle center, floor, spawn camera),
  4. applies the same shrink-only anti-needle clamp as v2,
  5. writes the leveled PLY and prints a manifest JSON snippet
     (spawn pose, waypoint poses, bounds, vertical FOV) for sceneConfig.ts.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation as R

GSPLAT_EXAMPLES = Path("E:/Nammaspace-1.0/pipeline-capture-splat/external/gsplat-v1.5.3/examples")
sys.path.insert(0, str(GSPLAT_EXAMPLES))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from datasets.colmap import Parser  # noqa: E402
from ply_io import read_ply_gaussian, write_ply_gaussian  # noqa: E402

parser = argparse.ArgumentParser(description="Level the 25k MCMC supermarket model for web export.")
parser.add_argument("--package", type=Path,
                    default=Path("E:/Nammaspace-1.0/data/experiments/supermarket001_full_rectified_sharp"))
parser.add_argument("--input", type=Path,
                    default=Path("E:/Nammaspace-1.0/data/experiments/supermarket001_hq_mcmc/splat/ply/point_cloud_24999.ply"))
parser.add_argument("--output", type=Path,
                    default=Path("E:/Nammaspace-1.0/data/experiments/supermarket001_hq_mcmc/splat/ply/supermarket_mcmc25k_leveled.ply"))
parser.add_argument("--level-frame", type=int, default=49, help="Camera index used to derive the ground plane.")
parser.add_argument("--spawn-frame", type=int, default=20, help="Camera index used as the viewer spawn pose.")
parser.add_argument("--min-opacity", type=float, default=0.04)
parser.add_argument("--max-splat-scale", type=float, default=0.06)
parser.add_argument("--bbox", type=float, nargs=6, default=[-4.5, 2.8, -1.6, 3.4, -8.5, 6.5],
                    metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"),
                    help="Leveled-space crop applied BEFORE shift derivation.")
parser.add_argument("--waypoint-frames", type=int, nargs="*", default=[20, 100, 200])
args = parser.parse_args()

# ---------------------------------------------------------------- 1. rotation
print("Loading rectified COLMAP cameras to extract ground plane normal...")
p = Parser(str(args.package), factor=1, normalize=True)

idx = int(args.level_frame)
c2w = p.camtoworlds[idx]
u = -c2w[:3, 1]
u = u / np.linalg.norm(u)
f = c2w[:3, 2]
f = f - np.dot(f, u) * u
f = f / np.linalg.norm(f)
r = np.cross(f, u)
r = r / np.linalg.norm(r)

# R_mat: aisle right -> +X, ground normal -> +Y, walking direction -> -Z
R_mat = np.stack([r, u, -f], axis=0)
rot_R = R.from_matrix(R_mat)

cam_centers = p.camtoworlds[:, :3, 3]
cam_centers_leveled = cam_centers @ R_mat.T

# Vertical FOV from the rectified pinhole intrinsics (spawn camera).
cam_id = p.camera_ids[idx]
K = p.Ks_dict[cam_id]
W_img, H_img = p.imsize_dict[cam_id]
fy = float(K[1, 1])
vfov_deg = float(np.degrees(2.0 * np.arctan(H_img / (2.0 * fy))))
print(f"Image {W_img}x{H_img}, fy={fy:.1f} -> vertical FOV = {vfov_deg:.1f} deg")

# ------------------------------------------------------------------ 2. load
print(f"Loading MCMC 25k model: {args.input}")
t0 = time.time()
data, _ = read_ply_gaussian(args.input)
N_orig = len(data)
print(f"Loaded {N_orig:,} Gaussians in {time.time() - t0:.2f}s")

xyz = np.stack([data["x"], data["y"], data["z"]], axis=-1)
xyz_leveled = xyz @ R_mat.T

# ------------------------------------------------------- 3. shift derivation
xmin, xmax, ymin, ymax, zmin, zmax = args.bbox
pre_mask = (
    (xyz_leveled[:, 0] >= xmin) & (xyz_leveled[:, 0] <= xmax) &
    (xyz_leveled[:, 1] >= ymin) & (xyz_leveled[:, 1] <= ymax) &
    (xyz_leveled[:, 2] >= zmin) & (xyz_leveled[:, 2] <= zmax)
)
xyz_pre = xyz_leveled[pre_mask]

aisle_x = float(np.median(cam_centers_leveled[:, 0]))

# Floor estimate: low percentile of splat height near the camera corridor.
corridor = xyz_pre[np.abs(xyz_pre[:, 0] - aisle_x) < 1.5]
floor_candidates = corridor[:, 1]
floor_y = float(np.percentile(floor_candidates, 2.0))
print(f"Camera leveled Y range: [{cam_centers_leveled[:, 1].min():.3f}, {cam_centers_leveled[:, 1].max():.3f}]")
print(f"Estimated floor Y (2nd pct of corridor splats): {floor_y:.3f}")

spawn_idx = int(args.spawn_frame)
spawn_cam = cam_centers_leveled[spawn_idx]
img_names = getattr(p, "image_names", None)
spawn_img = img_names[spawn_idx] if img_names is not None else f"idx {spawn_idx}"
print(f"Spawn camera idx {spawn_idx} ({spawn_img}): leveled {np.round(spawn_cam, 3).tolist()}")

shift = np.array([-aisle_x, -floor_y, -spawn_cam[2]], dtype=np.float64)
xyz_centered = xyz_pre + shift
cams_centered = cam_centers_leveled + shift
spawn_centered = cams_centered[spawn_idx]
print(f"Shifts: aisle_x={aisle_x:.3f} floor_y={floor_y:.3f} spawn_z={spawn_cam[2]:.3f}")
print(f"Spawn after shift: {np.round(spawn_centered, 3).tolist()}  (eye height {spawn_centered[1]:.3f} m)")

# ---------------------------------------------------------------- 4. filter
opacities = 1.0 / (1.0 + np.exp(-data["opacity"].astype(np.float64)))[pre_mask]
s = np.exp(np.stack([data["scale_0"], data["scale_1"], data["scale_2"]], axis=-1))[pre_mask]
s_sorted = np.sort(s, axis=-1)
s_max = s_sorted[:, 2]

keep = (opacities >= args.min_opacity) & (s_max <= args.max_splat_scale)
print(f"Retained {keep.sum():,} / {len(xyz_pre):,} ({keep.sum() / max(len(xyz_pre), 1) * 100:.1f}%) after opacity/scale filters")

filtered = data[pre_mask][keep].copy()
xyz_filt = xyz_centered[keep]
s_filt = s[keep].copy()
opa_filt = opacities[keep]

# ------------------------------------------- 5. shrink-only anti-needle clamp
s_sorted_f = np.sort(s_filt, axis=-1)
s_mid_f = s_sorted_f[:, 1]
max_allowed = np.minimum(s_mid_f * 3.5, 0.035)
needle_ratio = np.minimum(1.0, max_allowed / (s_sorted_f[:, 2] + 1e-7))
max_idx = np.argmax(s_filt, axis=-1)
for i in range(3):
    cond = max_idx == i
    s_filt[cond, i] *= needle_ratio[cond]

filtered["x"] = xyz_filt[:, 0].astype(np.float32)
filtered["y"] = xyz_filt[:, 1].astype(np.float32)
filtered["z"] = xyz_filt[:, 2].astype(np.float32)
filtered["scale_0"] = np.log(s_filt[:, 0]).astype(np.float32)
filtered["scale_1"] = np.log(s_filt[:, 1]).astype(np.float32)
filtered["scale_2"] = np.log(s_filt[:, 2]).astype(np.float32)

# --------------------------------------------------------- 6. rotate quats
q_orig = np.stack([
    filtered["rot_1"], filtered["rot_2"], filtered["rot_3"], filtered["rot_0"],
], axis=-1)
q_new = (rot_R * R.from_quat(q_orig)).as_quat()
filtered["rot_0"] = q_new[:, 3].astype(np.float32)
filtered["rot_1"] = q_new[:, 0].astype(np.float32)
filtered["rot_2"] = q_new[:, 1].astype(np.float32)
filtered["rot_3"] = q_new[:, 2].astype(np.float32)

# ------------------------------------------------------------------ 7. write
print(f"Writing leveled PLY: {args.output}")
t1 = time.time()
write_ply_gaussian(
    args.output,
    filtered,
    comments=[
        "Supermarket MCMC 25k leveled: full_rectified_sharp COLMAP, shrink-only clamp",
        f"source={args.input}",
    ],
)
print(f"Exported {len(filtered):,} Gaussians in {time.time() - t1:.2f}s! "
      f"Size: {args.output.stat().st_size / (1024 * 1024):.2f} MB")

# ------------------------------------------------------- 8. manifest snippet
def cam_pose(i: int) -> dict:
    pos = cams_centered[i]
    fwd_world = p.camtoworlds[i][:3, :3] @ np.array([0.0, 0.0, 1.0])
    fwd_lvl = R_mat @ fwd_world
    tgt = pos + fwd_lvl * 1.5
    return {
        "img": img_names[i] if img_names is not None else f"idx {i}",
        "pos": [round(float(v), 3) for v in pos],
        "lookAt": [round(float(v), 3) for v in tgt],
    }

lo = np.percentile(xyz_filt, 0.5, axis=0)
hi = np.percentile(xyz_filt, 99.5, axis=0)
bounds = {
    "min": [round(float(max(v, -6.0)), 2) for v in lo],
    "max": [round(float(min(v, 6.0)), 2) for v in hi],
}

manifest = {
    "asset": args.output.name.replace(".ply", ".sog"),
    "fov": round(vfov_deg, 1),
    "camera": {"position": [round(float(v), 3) for v in spawn_centered], "lookAt": cam_pose(spawn_idx)["lookAt"]},
    "bounds": bounds,
    "gaussians": int(len(filtered)),
    "waypoints": [cam_pose(i) for i in args.waypoint_frames],
}
print("\n---------------- MANIFEST SNIPPET (paste into sceneConfig.ts) ----------------")
print(json.dumps(manifest, indent=2))
print("------------------------------------------------------------------------------")
