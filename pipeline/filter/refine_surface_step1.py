"""Step 1 surface cleanup for a 3DGS PLY.

Keeps the original intent (drop ghost haze, tame ray streaks, cap giant blur
bubbles) but never grows a splat axis. The previous version raised every axis to
at least ``max_axis / 8``, which thickened surfaces and softened the render.

Usage:
    python pipeline/filter/refine_surface_step1.py --input raw.ply --output step1.ply
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
DEFAULT_OUTPUT = BASE_DIR / "data/experiments/supermarket001_3dgs_gradient/splat/ply/supermarket_surface_step1.ply"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 1 surface cleanup (shrink-only) for a 3DGS PLY.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-opacity", type=float, default=0.03, help="Drop splats below this sigmoid opacity.")
    parser.add_argument("--max-aspect", type=float, default=8.0, help="Largest allowed major/intermediate ratio.")
    parser.add_argument("--max-scale", type=float, default=0.12, help="Absolute cap on the major axis (metres).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_aspect <= 1.0:
        raise ValueError("--max-aspect must be greater than 1.0")

    print(f"Loading raw model from: {args.input}...")
    t0 = time.time()
    data, _ = read_ply_gaussian(args.input)
    original_count = len(data)
    print(f"Loaded {original_count:,} Gaussians in {time.time() - t0:.2f}s.")

    scales = np.exp(np.stack([data["scale_0"], data["scale_1"], data["scale_2"]], axis=1))
    max_axis = scales.max(axis=1)
    mid_axis = np.sort(scales, axis=1)[:, 1]
    # Needles are long *and* thin in both minor axes. Comparing major to the
    # thickness axis would flag every legitimate surface disk, so use the
    # intermediate axis here.
    needle_aspect = max_axis / (mid_axis + 1e-9)
    opacities = 1.0 / (1.0 + np.exp(-data["opacity"]))

    # Prune only invisible haze and true air needles; keep solid coverage.
    keep = (opacities >= args.min_opacity) & ~((needle_aspect > 30.0) & (opacities < 0.25))
    print(f"Retained {int(keep.sum()):,} Gaussians ({keep.sum() / original_count * 100:.1f}%) for solid continuous surfaces.")

    filtered_data = data[keep].copy()
    k_scales = scales[keep].copy()

    # Shrink-only aspect + scale caps: no axis is ever enlarged.
    # Aspect is measured against the intermediate axis so that legitimate thin
    # surface disks are preserved; only true needles lose their long axis.
    sorted_scales = np.sort(k_scales, axis=1)
    intermediate = sorted_scales[:, 1:2]
    cap = np.clip(intermediate * args.max_aspect, a_min=None, a_max=args.max_scale)
    k_scales = np.minimum(k_scales, cap)

    if np.any(k_scales > scales[keep] + 1e-12):
        raise RuntimeError("internal error: step 1 refinement grew a splat axis")

    filtered_data["scale_0"] = np.log(k_scales[:, 0]).astype(np.float32)
    filtered_data["scale_1"] = np.log(k_scales[:, 1]).astype(np.float32)
    filtered_data["scale_2"] = np.log(k_scales[:, 2]).astype(np.float32)

    new_max = k_scales.max(axis=1)
    new_aspect = new_max / (np.sort(k_scales, axis=1)[:, 1] + 1e-9)
    print("Step 1 refined metrics:")
    print(f"  Scales (m): median={np.median(new_max):.4f}, 90%={np.percentile(new_max, 90):.4f}, max={np.max(new_max):.4f}")
    print(f"  Needle aspect (major/intermediate): median={np.median(new_aspect):.2f}, 90%={np.percentile(new_aspect, 90):.2f}, max={np.max(new_aspect):.2f}")

    print(f"Exporting refined PLY to: {args.output}...")
    t1 = time.time()
    write_ply_gaussian(
        args.output,
        filtered_data,
        comments=[
            f"Step 1 surface refinement (shrink-only): max aspect {args.max_aspect}, max scale {args.max_scale}m"
        ],
    )
    print(f"Export complete in {time.time() - t1:.2f}s! Output size: {args.output.stat().st_size / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()
