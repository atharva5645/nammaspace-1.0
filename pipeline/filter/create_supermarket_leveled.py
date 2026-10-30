import sys
import time
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation as R

GSPLAT_EXAMPLES = Path("E:/Nammaspace-1.0/pipeline-capture-splat/external/gsplat-v1.5.3/examples")
sys.path.insert(0, str(GSPLAT_EXAMPLES))
from datasets.colmap import Parser

# 1. Compute exact leveling matrix from COLMAP aisle cameras
print("Loading COLMAP camera poses to extract ground plane normal...")
p = Parser("E:/Nammaspace-1.0/data/experiments/supermarket001_seq0_colmap_dense", factor=1, normalize=True)
idx = 49  # frame 50
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

# 2. Load planar surface model
ply_in = Path("E:/Nammaspace-1.0/data/experiments/supermarket001_3dgs_gradient/splat/ply/supermarket_planar_surface.ply")
ply_out = Path("E:/Nammaspace-1.0/data/experiments/supermarket001_3dgs_gradient/splat/ply/supermarket_leveled_clean.ply")

print(f"Loading {ply_in}...")
mesh = trimesh.load(str(ply_in))
data = mesh.metadata["_ply_raw"]["vertex"]["data"]
N = len(data)
print(f"Loaded {N:,} Gaussians.")

xyz = np.stack([data["x"], data["y"], data["z"]], axis=-1)
xyz_leveled = xyz @ R_mat.T

# Bounding box filter in leveled space:
# Keep supermarket corridor and shelves, pruning the 214k runaway floaters
mask = (
    (xyz_leveled[:, 0] >= -4.0) & (xyz_leveled[:, 0] <= 2.0) &
    (xyz_leveled[:, 1] >= -1.4) & (xyz_leveled[:, 1] <= 3.0) &
    (xyz_leveled[:, 2] >= -7.5) & (xyz_leveled[:, 2] <= 6.0)
)
print(f"Retained {mask.sum():,} Gaussians ({mask.sum()/N*100:.1f}%) within supermarket bounding box.")

filtered_data = data[mask].copy()
xyz_filt = xyz_leveled[mask]

# 3. Rotate quaternions: q_new = R_mat * q_old
q_orig = np.stack([filtered_data["rot_1"], filtered_data["rot_2"], filtered_data["rot_3"], filtered_data["rot_0"]], axis=-1)
rot_orig = R.from_quat(q_orig)
rot_new = rot_R * rot_orig
q_new = rot_new.as_quat()  # [x, y, z, w]

filtered_data["rot_0"] = q_new[:, 3].astype(np.float32)  # w
filtered_data["rot_1"] = q_new[:, 0].astype(np.float32)  # x
filtered_data["rot_2"] = q_new[:, 1].astype(np.float32)  # y
filtered_data["rot_3"] = q_new[:, 2].astype(np.float32)  # z

# 4. Center coordinates:
# Shift X so aisle center (originally -1.35) is at X = 0.0
# Shift Y so floor (originally -1.18) is at Y = 0.0
# Shift Z so spawn point (originally 3.60) is at Z = 0.0
shift_x = 1.35
shift_y = 1.18
shift_z = -3.60

filtered_data["x"] = (xyz_filt[:, 0] + shift_x).astype(np.float32)
filtered_data["y"] = (xyz_filt[:, 1] + shift_y).astype(np.float32)
filtered_data["z"] = (xyz_filt[:, 2] + shift_z).astype(np.float32)

x_arr = filtered_data["x"]
y_arr = filtered_data["y"]
z_arr = filtered_data["z"]
print(f"Centered bounds:")
print(f"  X: [{x_arr.min():.3f}, {x_arr.max():.3f}]")
print(f"  Y: [{y_arr.min():.3f}, {y_arr.max():.3f}]")
print(f"  Z: [{z_arr.min():.3f}, {z_arr.max():.3f}]")

sys.path.insert(0, "E:/Nammaspace-1.0/pipeline/filter")
from ply_io import write_ply_gaussian

print(f"Exporting leveled PLY to: {ply_out}...")
t0 = time.time()
write_ply_gaussian(
    ply_out,
    filtered_data,
    comments=["Supermarket leveled & centered: floor Y=0, aisle along -Z, shelves at +/-X"]
)
print(f"Exported {len(filtered_data):,} Gaussians in {time.time()-t0:.2f}s! Size: {ply_out.stat().st_size / (1024*1024):.2f} MB")

