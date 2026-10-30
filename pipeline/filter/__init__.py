"""NammaSpace 3DGS Filter Pipeline.

An independent, non-destructive filtering and asset transformation module
supporting multi-stage Gaussian Splat cleaning and phone-capture preprocessing:
  - Stage 1 (Capture): Video/image frame extraction, blur filtering, exposure filtering,
                       near-duplicate culling, and even frame-count capping.
  - Stage 2 (Splat Cleaning): Statistical, NaN/Inf, Bounding-Box, Scale, and Opacity filtering (Pure Python + NumPy).
  - Stage 3 (Transform): Floater removal, cluster filtering, Morton ordering, and SOG compression via splat-transform.
"""

from .config import FilterConfig, Stage1Config, Stage2Config, CaptureFilterConfig, Stage1CaptureConfig
from .stage1_capture import (
    run_stage1_capture,
    Stage1CaptureResult,
    compute_laplacian_variance,
    compute_exposure_metrics,
    compute_frame_similarity,
)
from .ply_io import read_ply_gaussian, write_ply_gaussian
from .stage1_filter import run_stage1_filter, Stage1Result
from .stage2_transform import run_stage2_transform, Stage2Result, find_splat_transform_cli
from .pipeline import FilterPipeline, PipelineReport

__all__ = [
    "FilterConfig",
    "Stage1Config",
    "Stage2Config",
    "CaptureFilterConfig",
    "Stage1CaptureConfig",
    "run_stage1_capture",
    "Stage1CaptureResult",
    "compute_laplacian_variance",
    "compute_exposure_metrics",
    "compute_frame_similarity",
    "read_ply_gaussian",
    "write_ply_gaussian",
    "run_stage1_filter",
    "Stage1Result",
    "run_stage2_transform",
    "Stage2Result",
    "find_splat_transform_cli",
    "FilterPipeline",
    "PipelineReport",
]
