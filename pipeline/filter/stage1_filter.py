from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
import numpy as np

from .config import Stage1Config


@dataclass
class Stage1Result:
    """Result of Stage 1 in-memory filtering."""
    data: np.ndarray
    stats: dict[str, Any]


def run_stage1_filter(data: np.ndarray, config: Stage1Config) -> Stage1Result:
    """Execute Stage 1 in-memory statistical and numerical filtering on 3DGS data.
    
    Filters evaluated sequentially:
      1. NaN / Inf culling
      2. Bounding box volume culling
      3. Scale anomaly / floater culling (exp(scale) > threshold)
      4. Low-opacity degenerate splat culling
      5. Statistical radial outlier culling (optional)
    """
    initial_count = len(data)
    if initial_count == 0:
        return Stage1Result(
            data=data,
            stats={
                "initial_count": 0,
                "nan_inf_culled": 0,
                "bbox_culled": 0,
                "scale_culled": 0,
                "opacity_culled": 0,
                "statistical_culled": 0,
                "surviving_count": 0,
                "cull_ratio": 0.0,
            },
        )

    active_mask = np.ones(initial_count, dtype=bool)
    stats: dict[str, Any] = {"initial_count": initial_count}

    # 1. NaN / Inf check across all vertex attributes
    if config.remove_nan_inf:
        finite_mask = np.ones(initial_count, dtype=bool)
        for name in data.dtype.names or []:
            col = data[name]
            if np.issubdtype(col.dtype, np.floating):
                finite_mask &= np.isfinite(col)
        nan_culled = int(np.count_nonzero(~finite_mask & active_mask))
        active_mask &= finite_mask
        stats["nan_inf_culled"] = nan_culled
    else:
        stats["nan_inf_culled"] = 0

    # 2. Bounding Box Filter
    if config.bbox_min is not None and config.bbox_max is not None:
        min_x, min_y, min_z = config.bbox_min
        max_x, max_y, max_z = config.bbox_max
        x = data["x"]
        y = data["y"]
        z = data["z"]
        bbox_mask = (
            (x >= min_x) & (x <= max_x) &
            (y >= min_y) & (y <= max_y) &
            (z >= min_z) & (z <= max_z)
        )
        bbox_culled = int(np.count_nonzero(~bbox_mask & active_mask))
        active_mask &= bbox_mask
        stats["bbox_culled"] = bbox_culled
    else:
        stats["bbox_culled"] = 0

    # 3. Scale Anomaly Filter (culls massive billboard floaters)
    if config.max_scale_exp is not None and all(f"scale_{i}" in data.dtype.names for i in range(3)):
        max_scale_log = math.log(config.max_scale_exp)
        s0 = data["scale_0"]
        s1 = data["scale_1"]
        s2 = data["scale_2"]
        scale_ok = (s0 <= max_scale_log) & (s1 <= max_scale_log) & (s2 <= max_scale_log)
        scale_culled = int(np.count_nonzero(~scale_ok & active_mask))
        active_mask &= scale_ok
        stats["scale_culled"] = scale_culled
    else:
        stats["scale_culled"] = 0

    # 4. Opacity Filter (culls completely transparent / degenerate splats)
    if "opacity" in data.dtype.names:
        op = data["opacity"]
        op_mask = np.ones(initial_count, dtype=bool)
        if config.min_opacity_raw is not None:
            op_mask &= (op >= config.min_opacity_raw)
        if config.min_opacity_linear is not None:
            # Linear opacity: sigma = 1 / (1 + exp(-op))
            # sigma >= min_lin => -op <= ln(1/min_lin - 1) => op >= -ln(1/min_lin - 1)
            min_lin = max(1e-6, min(1.0 - 1e-6, config.min_opacity_linear))
            raw_thresh = -math.log((1.0 / min_lin) - 1.0)
            op_mask &= (op >= raw_thresh)
        opacity_culled = int(np.count_nonzero(~op_mask & active_mask))
        active_mask &= op_mask
        stats["opacity_culled"] = opacity_culled
    else:
        stats["opacity_culled"] = 0

    # 5. Statistical Radial Outlier Filter (distance from scene centroid)
    if config.statistical_filter_enabled and np.any(active_mask):
        surv_indices = np.where(active_mask)[0]
        pts = np.column_stack([data["x"][surv_indices], data["y"][surv_indices], data["z"][surv_indices]])
        centroid = np.mean(pts, axis=0)
        dists = np.linalg.norm(pts - centroid, axis=1)
        mean_d = float(np.mean(dists))
        std_d = float(np.std(dists))
        thresh = mean_d + config.statistical_std_ratio * std_d
        stat_ok_subset = dists <= thresh

        stat_mask = np.ones(initial_count, dtype=bool)
        stat_mask[surv_indices[~stat_ok_subset]] = False
        stat_culled = int(np.count_nonzero(~stat_ok_subset))
        active_mask &= stat_mask
        stats["statistical_culled"] = stat_culled
    else:
        stats["statistical_culled"] = 0

    surviving = data[active_mask]
    surviving_count = len(surviving)
    stats["surviving_count"] = surviving_count
    stats["cull_ratio"] = float((initial_count - surviving_count) / initial_count) if initial_count > 0 else 0.0

    return Stage1Result(data=surviving, stats=stats)
