from __future__ import annotations

import math
from pathlib import Path
from typing import Optional
import numpy as np

from .ply_io import write_ply_gaussian


def create_synthetic_3dgs_data(
    num_valid: int = 200,
    num_nan: int = 5,
    num_bbox_outliers: int = 10,
    num_scale_outliers: int = 5,
    num_low_opacity: int = 10,
    seed: int = 42,
) -> tuple[np.ndarray, dict[str, int]]:
    """Generate structured synthetic 3DGS Gaussian data with controlled anomalies."""
    rng = np.random.default_rng(seed)
    total_count = num_valid + num_nan + num_bbox_outliers + num_scale_outliers + num_low_opacity

    # Standard 3DGS property list
    fields = [
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
        ("f_dc_0", "<f4"), ("f_dc_1", "<f4"), ("f_dc_2", "<f4"),
        ("opacity", "<f4"),
        ("scale_0", "<f4"), ("scale_1", "<f4"), ("scale_2", "<f4"),
        ("rot_0", "<f4"), ("rot_1", "<f4"), ("rot_2", "<f4"), ("rot_3", "<f4"),
    ]
    dtype = np.dtype(fields)
    data = np.zeros(total_count, dtype=dtype)

    # 1. Valid points around origin (box [-2, 2])
    idx = 0
    if num_valid > 0:
        data["x"][idx:idx+num_valid] = rng.uniform(-1.5, 1.5, num_valid)
        data["y"][idx:idx+num_valid] = rng.uniform(-1.5, 1.5, num_valid)
        data["z"][idx:idx+num_valid] = rng.uniform(-1.5, 1.5, num_valid)
        data["opacity"][idx:idx+num_valid] = rng.uniform(0.5, 3.0, num_valid)  # Good opacity
        data["scale_0"][idx:idx+num_valid] = rng.uniform(-3.0, -1.0, num_valid)  # ~0.05 - 0.36m
        data["scale_1"][idx:idx+num_valid] = rng.uniform(-3.0, -1.0, num_valid)
        data["scale_2"][idx:idx+num_valid] = rng.uniform(-3.0, -1.0, num_valid)
        data["rot_0"][idx:idx+num_valid] = 1.0  # Unit quaternion
        idx += num_valid

    # 2. NaN / Inf points
    if num_nan > 0:
        data["x"][idx:idx+num_nan] = np.nan
        data["y"][idx:idx+num_nan] = 0.0
        data["z"][idx:idx+num_nan] = np.inf
        data["opacity"][idx:idx+num_nan] = 1.0
        data["scale_0"][idx:idx+num_nan] = -2.0
        data["scale_1"][idx:idx+num_nan] = -2.0
        data["scale_2"][idx:idx+num_nan] = -2.0
        data["rot_0"][idx:idx+num_nan] = 1.0
        idx += num_nan

    # 3. Bounding box outliers (far away at ~50.0m)
    if num_bbox_outliers > 0:
        data["x"][idx:idx+num_bbox_outliers] = rng.uniform(40.0, 60.0, num_bbox_outliers)
        data["y"][idx:idx+num_bbox_outliers] = rng.uniform(40.0, 60.0, num_bbox_outliers)
        data["z"][idx:idx+num_bbox_outliers] = rng.uniform(40.0, 60.0, num_bbox_outliers)
        data["opacity"][idx:idx+num_bbox_outliers] = 1.5
        data["scale_0"][idx:idx+num_bbox_outliers] = -2.0
        data["scale_1"][idx:idx+num_bbox_outliers] = -2.0
        data["scale_2"][idx:idx+num_bbox_outliers] = -2.0
        data["rot_0"][idx:idx+num_bbox_outliers] = 1.0
        idx += num_bbox_outliers

    # 4. Massive scale floaters (scale_0 = 10.0, exp(10) > 22,000m)
    if num_scale_outliers > 0:
        data["x"][idx:idx+num_scale_outliers] = rng.uniform(-1.0, 1.0, num_scale_outliers)
        data["y"][idx:idx+num_scale_outliers] = rng.uniform(-1.0, 1.0, num_scale_outliers)
        data["z"][idx:idx+num_scale_outliers] = rng.uniform(-1.0, 1.0, num_scale_outliers)
        data["opacity"][idx:idx+num_scale_outliers] = 1.0
        data["scale_0"][idx:idx+num_scale_outliers] = 10.0  # Exp is > 22000
        data["scale_1"][idx:idx+num_scale_outliers] = -2.0
        data["scale_2"][idx:idx+num_scale_outliers] = -2.0
        data["rot_0"][idx:idx+num_scale_outliers] = 1.0
        idx += num_scale_outliers

    # 5. Low opacity degenerate points (opacity = -15.0, sigma ~ 3e-7)
    if num_low_opacity > 0:
        data["x"][idx:idx+num_low_opacity] = rng.uniform(-1.0, 1.0, num_low_opacity)
        data["y"][idx:idx+num_low_opacity] = rng.uniform(-1.0, 1.0, num_low_opacity)
        data["z"][idx:idx+num_low_opacity] = rng.uniform(-1.0, 1.0, num_low_opacity)
        data["opacity"][idx:idx+num_low_opacity] = -15.0
        data["scale_0"][idx:idx+num_low_opacity] = -2.0
        data["scale_1"][idx:idx+num_low_opacity] = -2.0
        data["scale_2"][idx:idx+num_low_opacity] = -2.0
        data["rot_0"][idx:idx+num_low_opacity] = 1.0
        idx += num_low_opacity

    # Fill base colors (normalized spherical harmonic DC)
    data["f_dc_0"] = rng.uniform(0.1, 0.9, total_count)
    data["f_dc_1"] = rng.uniform(0.1, 0.9, total_count)
    data["f_dc_2"] = rng.uniform(0.1, 0.9, total_count)

    counts = {
        "total": total_count,
        "valid": num_valid,
        "nan": num_nan,
        "bbox_outliers": num_bbox_outliers,
        "scale_outliers": num_scale_outliers,
        "low_opacity": num_low_opacity,
    }
    return data, counts


def generate_synthetic_ply_file(
    out_path: Path | str,
    num_valid: int = 200,
    num_nan: int = 5,
    num_bbox_outliers: int = 10,
    num_scale_outliers: int = 5,
    num_low_opacity: int = 10,
    seed: int = 42,
) -> tuple[Path, dict[str, int]]:
    """Generate and write a synthetic binary 3DGS PLY file for testing."""
    p = Path(out_path)
    data, counts = create_synthetic_3dgs_data(
        num_valid=num_valid,
        num_nan=num_nan,
        num_bbox_outliers=num_bbox_outliers,
        num_scale_outliers=num_scale_outliers,
        num_low_opacity=num_low_opacity,
        seed=seed,
    )
    write_ply_gaussian(p, data, comments=["Synthetic 3DGS Test Asset"])
    return p, counts
