"""Find the floor and compute how to stand a splat upright for the viewer.

Fits the floor plane in the photogrammetry point cloud (fused.ply), then works out a
rotation + shift so that: up is +Y, the floor is at Y = 0, the average camera spot is
at X = Z = 0 and the average view direction is -Z (what the PlayCanvas viewer expects).

Writes level.json with:
  - splat_transform_args: pass to @playcanvas/splat-transform (rotates positions,
    orientations AND view-dependent colour correctly),
  - matrix: the same 4x4 for meshes,
  - viewer: suggested camera spawn, eye height and bounds for sceneConfig.ts.

  python pipeline/tools/level_splat.py dense_workspace/ level.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from carve_splat import _parser  # noqa: E402


def read_points(path: Path) -> np.ndarray:
    import trimesh
    return np.asarray(trimesh.load(path, process=False).vertices, dtype=np.float64)


def fit_floor(pts: np.ndarray, approx_up: np.ndarray, tol: float, rng) -> tuple[np.ndarray, float]:
    """RANSAC plane among the lowest points whose normal is near approx_up."""
    h = pts @ approx_up
    low = pts[h < np.percentile(h, 25)]
    best, best_n, best_d = 0, approx_up, float(np.median(low @ approx_up))
    for _ in range(3000):
        a, b, c = low[rng.choice(len(low), 3, replace=False)]
        n = np.cross(b - a, c - a)
        if np.linalg.norm(n) < 1e-9:
            continue
        n /= np.linalg.norm(n)
        if n @ approx_up < 0:
            n = -n
        if n @ approx_up < np.cos(np.radians(35)):
            continue
        count = int((np.abs(low @ n - a @ n) < tol).sum())
        if count > best:
            best, best_n, best_d = count, n, float(a @ n)
    # refine with a least-squares fit on the inliers
    inl = low[np.abs(low @ best_n - best_d) < tol]
    centre = inl.mean(0)
    n = np.linalg.eigh(np.cov((inl - centre).T))[1][:, 0]  # smallest-variance direction
    n = n if n @ best_n > 0 else -n
    return n, float(centre @ n)


def level(workspace: Path, normalized: bool = True, ceiling_m: float = 2.5) -> dict:
    p = _parser(workspace, normalized)
    pts = read_points(workspace / "fused.ply")
    pts = pts @ p.transform[:3, :3].T + p.transform[:3, 3]  # COLMAP -> splat coordinates
    c2w = p.camtoworlds
    approx_up = -c2w[:, :3, 1].mean(0)
    approx_up /= np.linalg.norm(approx_up)
    diag = float(np.linalg.norm(np.percentile(pts, 98, 0) - np.percentile(pts, 2, 0)))
    up, floor_d = fit_floor(pts, approx_up, 0.005 * diag, np.random.default_rng(0))

    fwd = np.median(c2w[:, :3, 2], 0)
    fwd -= (fwd @ up) * up
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    rot = np.stack([right, up, -fwd])  # rows: new X, Y, Z axes
    cam_xz = np.median(c2w[:, :3, 3] @ rot.T, 0)
    shift = np.array([-cam_xz[0], -floor_d, -cam_xz[2]])
    lv = pts @ rot.T + shift
    ceiling = float(np.percentile(lv[:, 1], 98))
    eye = 1.6 / ceiling_m * ceiling  # assume a ~2.5 m ceiling to get human eye height
    lo, hi = np.percentile(lv, 1, 0), np.percentile(lv, 99, 0)

    m = np.eye(4)
    m[:3, :3], m[:3, 3] = rot, shift
    # splat-transform -r a,b,c applies Rotation.from_euler('XYZ', [a,b,c]).T
    euler = Rotation.from_matrix(rot.T).as_euler("XYZ", degrees=True)
    return {
        "splat_transform_args": ["-r", ",".join(f"{a:.4f}" for a in euler),
                                 "-t", ",".join(f"{t:.5f}" for t in shift)],
        "matrix": np.round(m, 6).tolist(),
        "floor_fit": {"normal_vs_camera_up_deg": round(float(np.degrees(np.arccos(up @ approx_up))), 1)},
        "viewer": {
            "spawn": [0.0, round(eye, 3), 0.0],
            "look_at": [0.0, round(eye * 0.8, 3), -1.0],
            "eye_height": round(eye, 3),
            "ceiling_height": round(ceiling, 3),
            "bounds_min": np.round(lo, 2).tolist(),
            "bounds_max": np.round(hi, 2).tolist(),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path, help="COLMAP dense workspace with fused.ply (gsplat --data-dir)")
    ap.add_argument("out", type=Path, help="level.json to write")
    ap.add_argument("--no-gsplat-normalized", dest="normalized", action="store_false")
    a = ap.parse_args()
    r = level(a.workspace, a.normalized)
    a.out.write_text(json.dumps(r, indent=2))
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
