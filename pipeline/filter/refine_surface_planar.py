"""Planar surface *shrink* regularization for a 3DGS PLY.

The original version of this script grew the thin axes of every splat
(``s2 = max(s2, s1/3)``, ``s3 = max(s3, s1/8)``). That is a blur filter: it
turns a 1D needle into a 3D blob and thickens the whole surface, which is why
planarized exports look soft from every angle.

Default mode (``shrink``) keeps the disk idea but shrinks the major axis down
to ``3 * s2`` instead of growing the minor axes, so splat coverage never grows.

Usage:
    python pipeline/filter/refine_surface_planar.py --input raw.ply --output planar.ply
    # exact legacy behaviour, for reproducing an old asset:
    python pipeline/filter/refine_surface_planar.py --input raw.ply --output old.ply --mode inflate-legacy
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ply_io import read_ply_gaussian, write_ply_gaussian  # noqa: E402

BASE_DIR = Path("E:/Nammaspace-1.0")
DEFAULT_INPUT = BASE_DIR / "data/experiments/supermarket001_3dgs_gradient/splat/ply/point_cloud_14999.ply"
DEFAULT_OUTPUT = BASE_DIR / "data/experiments/supermarket001_3dgs_gradient/splat/ply/supermarket_planar_surface.ply"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shrink-only planar regularization for a 3DGS PLY.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-opacity", type=float, default=0.05, help="Drop splats below this sigmoid opacity.")
    parser.add_argument("--max-major-scale", type=float, default=0.075, help="Absolute cap on the major axis (metres).")
    parser.add_argument("--surface-aspect", type=float, default=3.0, help="Largest allowed major/intermediate ratio.")
    parser.add_argument(
        "--mode",
        choices=("shrink", "inflate-legacy"),
        default="shrink",
        help="'shrink' (default) never grows an axis; 'inflate-legacy' reproduces the old blur-inducing behaviour.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.surface_aspect <= 1.0:
        raise ValueError("--surface-aspect must be greater than 1.0")

    print(f"Loading raw model: {args.input}...")
    t0 = time.time()
    data, _ = read_ply_gaussian(args.input)
    original_count = len(data)
    print(f"Loaded {original_count:,} Gaussians in {time.time() - t0:.2f}s.")

    opacities = 1.0 / (1.0 + np.exp(-data["opacity"]))
    keep = opacities >= args.min_opacity
    print(f"Retained {int(keep.sum()):,} Gaussians ({keep.sum() / original_count * 100:.1f}%) for solid surfaces.")

    filtered_data = data[keep].copy()
    scales = np.exp(
        np.stack([filtered_data["scale_0"], filtered_data["scale_1"], filtered_data["scale_2"]], axis=1)
    )

    # Sort per Gaussian: s3 (min) <= s2 (mid) <= s1 (max).
    order = np.argsort(scales, axis=1)
    s_sorted = np.take_along_axis(scales, order, axis=1)
    s3, s2, s1 = s_sorted[:, 0], s_sorted[:, 1], s_sorted[:, 2]

    max_major = np.minimum(s1, args.max_major_scale)

    if args.mode == "inflate-legacy":
        s1_reg = max_major
        s2_reg = np.clip(np.maximum(s2, s1_reg / 3.0), a_min=None, a_max=args.max_major_scale)
        s3_reg = np.clip(np.maximum(s3, s1_reg / 8.0), a_min=None, a_max=args.max_major_scale)
    else:
        # Shrink-only: every axis is capped, and the major axis is additionally
        # reduced so major/intermediate <= surface_aspect. Nothing is ever grown.
        s3_reg = np.minimum(s3, args.max_major_scale)
        s2_reg = np.minimum(s2, args.max_major_scale)
        s1_reg = np.minimum(max_major, s2_reg * args.surface_aspect)

    new_sorted = np.stack([s3_reg, s2_reg, s1_reg], axis=1)
    new_scales = np.empty_like(scales)
    np.put_along_axis(new_scales, order, new_sorted, axis=1)

    if np.any(new_scales > scales + 1e-12):
        raise RuntimeError("internal error: scale regularization grew a splat axis")

    filtered_data["scale_0"] = np.log(new_scales[:, 0]).astype(np.float32)
    filtered_data["scale_1"] = np.log(new_scales[:, 1]).astype(np.float32)
    filtered_data["scale_2"] = np.log(new_scales[:, 2]).astype(np.float32)

    ordered = np.sort(new_scales, axis=1)
    thickness, intermediate, major = ordered[:, 0], ordered[:, 1], ordered[:, 2]
    surface_aspect = major / (intermediate + 1e-9)
    thickness_aspect = major / (thickness + 1e-9)
    print("Planar regularization metrics:")
    print(
        "  Major scale (m): "
        f"median={np.median(major):.4f}, 90%={np.percentile(major, 90):.4f}, max={np.max(major):.4f}"
    )
    print(f"  Surface aspect (major/intermediate): median={np.median(surface_aspect):.2f}, max={np.max(surface_aspect):.2f}")
    print(f"  Thickness aspect: median={np.median(thickness_aspect):.2f}, max={np.max(thickness_aspect):.2f}")

    print(f"Writing planar surface PLY to: {args.output}...")
    t1 = time.time()
    write_ply_gaussian(
        args.output,
        filtered_data,
        comments=[f"Planar surface regularization ({args.mode}): major axis cap {args.max_major_scale}m"],
    )
    print(f"Exported in {time.time() - t1:.2f}s! Size: {args.output.stat().st_size / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()
