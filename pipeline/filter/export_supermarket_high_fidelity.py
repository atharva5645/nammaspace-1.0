import argparse
import sys
import time
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation as R

GSPLAT_EXAMPLES = Path("E:/Nammaspace-1.0/pipeline-capture-splat/external/gsplat-v1.5.3/examples")
sys.path.insert(0, str(GSPLAT_EXAMPLES))
from datasets.colmap import Parser

# Thresholds used to be hardcoded. They are exposed so a run can keep faint
# coverage (which is what actually holds fine detail) instead of deleting it.
_parser = argparse.ArgumentParser(description="Level and clean a 3DGS supermarket model for web export.")
_parser.add_argument("--package", type=Path, default=Path("E:/Nammaspace-1.0/data/experiments/supermarket001_seq0_colmap_dense"))
_parser.add_argument("--frame-index", type=int, default=49, help="Camera used to derive the ground plane normal.")
_parser.add_argument("--input", type=Path, default=Path("E:/Nammaspace-1.0/data/experiments/supermarket001_3dgs_gradient/splat/ply/point_cloud_14999.ply"))
_parser.add_argument("--output", type=Path, default=Path("E:/Nammaspace-1.0/data/experiments/supermarket001_3dgs_gradient/splat/ply/supermarket_hq_leveled.ply"))
_parser.add_argument("--min-opacity", type=float, default=0.05, help="Sigmoid opacity floor (default: 0.05, was 0.10).")
_parser.add_argument("--max-splat-scale", type=float, default=0.05, help="Drop splats whose major axis exceeds this (default: 0.05).")
_parser.add_argument("--bbox", type=float, nargs=6, default=[-4.0, 2.5, -0.2, 3.2, -8.0, 6.0], metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"), help="Centered-space crop.")
_args = _parser.parse_args()

# 1. Compute exact leveling matrix from COLMAP aisle cameras
print("Loading COLMAP camera poses to extract ground plane normal...")
p = Parser(str(_args.package), factor=1, normalize=True)
idx = int(_args.frame_index)
c2w = p.camtoworlds[idx]

u = -c2w[:3, 1]
u = u / np.linalg.norm(u)
f = c2w[:3, 2]
f = f - np.dot(f, u) * u
f = f / np.linalg.norm(f)
r = np.cross(f, u)
r = r / np.linalg.norm(r)

# R_mat: maps aisle right -> +X, upright ground normal -> +Y, walking direction -> -Z
R_mat = np.stack([r, u, -f], axis=0)
rot_R = R.from_matrix(R_mat)

# 2. Load RAW 15,000-step gradient model
ply_in = _args.input
ply_out = _args.output

print(f"Loading raw 15k model: {ply_in}...")
t0 = time.time()
mesh = trimesh.load(str(ply_in))
data = mesh.metadata["_ply_raw"]["vertex"]["data"]
N_orig = len(data)
print(f"Loaded {N_orig:,} Gaussians in {time.time()-t0:.2f}s.")

# Level positions
xyz = np.stack([data["x"], data["y"], data["z"]], axis=-1)
xyz_leveled = xyz @ R_mat.T

# Shift coordinates so:
# Floor (originally -1.18) -> Y = 0.0
# Aisle center (originally -1.35) -> X = 0.0
# Spawn point (originally 3.60) -> Z = 0.0
shift = np.array([1.35, 1.18, -3.60], dtype=np.float32)
xyz_centered = xyz_leveled + shift

# Opacities
opacities = 1.0 / (1.0 + np.exp(-data["opacity"]))

# Scales
s = np.exp(np.stack([data["scale_0"], data["scale_1"], data["scale_2"]], axis=-1))
s_sorted = np.sort(s, axis=-1)  # s_min, s_mid, s_max
s_min = s_sorted[:, 0]
s_mid = s_sorted[:, 1]
s_max = s_sorted[:, 2]

# Filter criteria:
# 1. Bounding box in centered space (override with --bbox):
# Keep corridor and shelves, prune distant runaway floaters from COLMAP pose jumps
xmin, xmax, ymin, ymax, zmin, zmax = _args.bbox
spatial_mask = (
    (xyz_centered[:, 0] >= xmin) & (xyz_centered[:, 0] <= xmax) &
    (xyz_centered[:, 1] >= ymin) & (xyz_centered[:, 1] <= ymax) &
    (xyz_centered[:, 2] >= zmin) & (xyz_centered[:, 2] <= zmax)
)

# 2. Opacity threshold: remove invisible/faint ghost floaters
opacity_mask = opacities >= _args.min_opacity

# 3. Scale threshold: prune giant fog bubbles
scale_mask = s_max <= _args.max_splat_scale

keep_mask = spatial_mask & opacity_mask & scale_mask
print(f"Retained {keep_mask.sum():,} / {N_orig:,} Gaussians ({keep_mask.sum()/N_orig*100:.1f}%)")

filtered_data = data[keep_mask].copy()
xyz_filt = xyz_centered[keep_mask]
s_filt = s[keep_mask]
opas_filt = opacities[keep_mask]

# 4. Anti-needle clamp:
# Rather than inflating small splats, SHRNK the elongated axis of needles
# so they don't form streaks or rays, while preserving fine details!
s_sorted_filt = np.sort(s_filt, axis=-1)
s_mid_filt = s_sorted_filt[:, 1]
s_max_filt = s_sorted_filt[:, 2]

# If s_max > 3.5 * s_mid, clamp s_max to 3.5 * s_mid
max_allowed = s_mid_filt * 3.5
# Also clamp absolute max scale to 0.035m (3.5 cm)
max_allowed = np.minimum(max_allowed, 0.035)

needle_ratio = np.minimum(1.0, max_allowed / (s_max_filt + 1e-7))
max_idx = np.argmax(s_filt, axis=-1)

for i in range(3):
    cond = (max_idx == i)
    s_filt[cond, i] = s_filt[cond, i] * needle_ratio[cond]

# Store updated scales and positions
filtered_data["x"] = xyz_filt[:, 0].astype(np.float32)
filtered_data["y"] = xyz_filt[:, 1].astype(np.float32)
filtered_data["z"] = xyz_filt[:, 2].astype(np.float32)

filtered_data["scale_0"] = np.log(s_filt[:, 0]).astype(np.float32)
filtered_data["scale_1"] = np.log(s_filt[:, 1]).astype(np.float32)
filtered_data["scale_2"] = np.log(s_filt[:, 2]).astype(np.float32)

# 5. Rotate quaternions: q_new = R_mat * q_old
q_orig = np.stack([
    filtered_data["rot_1"],  # x
    filtered_data["rot_2"],  # y
    filtered_data["rot_3"],  # z
    filtered_data["rot_0"]   # w
], axis=-1)

rot_orig = R.from_quat(q_orig)
rot_new = rot_R * rot_orig
q_new = rot_new.as_quat()  # [x, y, z, w]

filtered_data["rot_0"] = q_new[:, 3].astype(np.float32)  # w
filtered_data["rot_1"] = q_new[:, 0].astype(np.float32)  # x
filtered_data["rot_2"] = q_new[:, 1].astype(np.float32)  # y
filtered_data["rot_3"] = q_new[:, 2].astype(np.float32)  # z

print(f"Writing High-Fidelity Leveled PLY: {ply_out}...")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ply_io import write_ply_gaussian

t1 = time.time()
write_ply_gaussian(
    ply_out,
    filtered_data,
    comments=["Supermarket High-Fidelity Leveled Model: raw 15k gradients, leveled R_mat, anti-needle clamp"]
)
print(f"Exported {len(filtered_data):,} Gaussians in {time.time()-t1:.2f}s! Size: {ply_out.stat().st_size / (1024*1024):.2f} MB")

