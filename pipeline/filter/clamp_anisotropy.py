"""Shrink-only anisotropy clamp for a trained 3DGS checkpoint.

Why this exists
---------------
Long thin splats ("needles") are training artifacts: they are what a Gaussian
learns when its depth is poorly constrained. They render as radial streaks.

The previous version of this script forced every splat up to a minimum
thickness (``torch.maximum(scales, max_axis / 2.5)``). That turns a needle into
a fat disc instead of removing it, inflates splat volume, and is a direct cause
of "the model renders but looks soft". This version only ever *shrinks* the
major axis, so streaks are removed without smearing the surface.

It also no longer crops the scene by default: the old ``dist <= 4.8`` filter
deleted everything more than 4.8 units from the origin, which silently cut
rooms apart. Pass ``--max-radius`` if you actually want that crop.

Usage:
    python pipeline/filter/clamp_anisotropy.py \
        --ckpt data/experiments/<run>/splat/ckpts/ckpt_2499_rank0.pt \
        --output data/experiments/<run>/splat/ply/<run>_isotropic.ply
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch

GSPLAT_ROOT = Path("E:/Nammaspace-1.0/pipeline-capture-splat/external/gsplat-v1.5.3")
if str(GSPLAT_ROOT) not in sys.path:
    sys.path.insert(0, str(GSPLAT_ROOT))

from gsplat import export_splats  # noqa: E402

BASE_DIR = Path("E:/Nammaspace-1.0")
DEFAULT_CKPT = BASE_DIR / "data/experiments/supermarket001_chunk50_rectified_sharp/splat/ckpts/ckpt_2499_rank0.pt"
DEFAULT_OUT = BASE_DIR / "data/experiments/supermarket001_chunk50_rectified_sharp/splat/ply/supermarket_chunk50_isotropic.ply"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Shrink-only anisotropy clamp for a trained 3DGS checkpoint (removes ray streaks without inflating splats)."
    )
    parser.add_argument("--ckpt", type=Path, default=DEFAULT_CKPT, help="gsplat checkpoint (.pt).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output .ply path.")
    parser.add_argument(
        "--max-aspect",
        type=float,
        default=3.5,
        help="Largest allowed major/intermediate axis ratio. The major axis is shrunk to meet it (default: 3.5).",
    )
    parser.add_argument(
        "--max-scale",
        type=float,
        default=0.030,
        help="Absolute cap on the major axis in world units (default: 0.030).",
    )
    parser.add_argument(
        "--min-opacity",
        type=float,
        default=0.05,
        help="Drop splats below this sigmoid opacity (default: 0.05).",
    )
    parser.add_argument(
        "--prune-scale-above",
        type=float,
        default=0.045,
        help="Drop splats whose major axis already exceeds this before clamping (default: 0.045).",
    )
    parser.add_argument(
        "--max-radius",
        type=float,
        default=None,
        help="Optional distance cutoff from the origin. Disabled by default because it crops the scene.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_aspect <= 1.0:
        raise ValueError("--max-aspect must be greater than 1.0")

    print(f"Loading checkpoint: {args.ckpt}")
    checkpoint = torch.load(args.ckpt, map_location="cpu")
    splats = checkpoint["splats"]

    means = splats["means"]
    scales = torch.exp(splats["scales"])
    quats = splats["quats"]
    opacities = torch.sigmoid(splats["opacities"]).squeeze(-1)
    sh0 = splats["sh0"]
    shN = splats["shN"]

    original_count = len(means)
    print(f"Original Gaussians: {original_count:,}")

    # 1. Prune floaters, oversized splats and needles before clamping.
    max_axis_before = scales.max(dim=1).values
    distance = torch.norm(means, dim=1)
    keep = (max_axis_before <= args.prune_scale_above) & (opacities >= args.min_opacity)
    if args.max_radius is not None:
        keep &= distance <= args.max_radius
    print(f"Kept after outlier prune: {keep.sum().item():,} ({keep.sum().item() / original_count * 100:.1f}%)")

    k_means = means[keep]
    k_scales = scales[keep].clone()
    k_quats = quats[keep]
    k_opacities = splats["opacities"][keep]
    k_sh0 = sh0[keep]
    k_shN = shN[keep]

    # 2. Shrink-only aspect regulation.
    #    Aspect is measured against the *intermediate* axis, not the thickness
    #    axis: a legitimate surface disk is wide, thin, and has a huge
    #    major/thickness ratio. Only when the intermediate axis is also tiny
    #    (a true needle) does capping the major axis remove real extent.
    #    cap = min(intermediate_axis * max_aspect, max_scale); every axis is
    #    reduced to at most cap, so no splat is ever grown by this step.
    sorted_scales, _ = torch.sort(k_scales, dim=1)
    intermediate_axis = sorted_scales[:, 1:2]
    cap = torch.clamp(intermediate_axis * args.max_aspect, max=args.max_scale)
    clamped_scales = torch.minimum(k_scales, cap)

    grown = int((clamped_scales > k_scales + 1e-8).sum().item())
    if grown:
        raise RuntimeError(f"internal error: shrink-only clamp grew {grown} axes")

    ordered = torch.sort(clamped_scales, dim=1).values
    surface_aspect = ordered[:, 2] / ordered[:, 1].clamp_min(1e-9)
    thickness_aspect = ordered[:, 2] / ordered[:, 0].clamp_min(1e-9)
    print(
        "New surface aspect (major/intermediate): "
        f"max={surface_aspect.max().item():.2f}, "
        f"99%={np.percentile(surface_aspect.numpy(), 99):.2f}, "
        f"median={surface_aspect.median().item():.2f}"
    )
    print(
        "New thickness aspect (major/thickness): "
        f"max={thickness_aspect.max().item():.2f}, "
        f"median={thickness_aspect.median().item():.2f}"
    )
    print(
        "New Max Scale: "
        f"max={clamped_scales.max().item():.4f}, "
        f"median={clamped_scales.median().item():.4f}"
    )

    log_scales = torch.log(clamped_scales)

    # 3. Export to PLY.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Exporting isotropic PLY to: {args.output}...")
    t0 = time.time()
    export_splats(
        means=k_means,
        scales=log_scales,
        quats=k_quats,
        opacities=k_opacities,
        sh0=k_sh0,
        shN=k_shN,
        format="ply",
        save_to=str(args.output),
    )
    print(f"Exported in {time.time() - t0:.2f}s! File size: {args.output.stat().st_size / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()
