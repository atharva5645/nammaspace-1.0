from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class CaptureFilterConfig:
    """Configuration for Stage 1 Capture Preprocessing (Video/Image Ingestion & Quality Filters)."""
    extraction_fps: Optional[float] = 2.0  # FPS to extract from video; None = extract all
    min_laplacian_var: float = 80.0       # Minimum Laplacian variance; frames below are blurred
    min_mean_luminance: float = 35.0      # Minimum grayscale mean (0-255); below is under-exposed
    max_mean_luminance: float = 225.0     # Maximum grayscale mean (0-255); above is over-exposed
    max_shadow_clip_ratio: float = 0.35   # Max allowed fraction of pixels in shadow ([0, 15])
    max_highlight_clip_ratio: float = 0.35 # Max allowed fraction of pixels in highlight ([240, 255])
    near_duplicate_threshold: float = 0.95 # Similarity threshold (0-1) against last kept frame
    max_frames_cap: Optional[int] = None  # Optional cap: evenly subsample if kept count exceeds this
    output_image_format: str = "jpg"      # "jpg" or "png"
    jpeg_quality: int = 95
    ffmpeg_binary: Optional[str] = None   # Explicit ffmpeg binary, or auto-detect


# Alias for explicit naming
Stage1CaptureConfig = CaptureFilterConfig


@dataclass
class Stage1Config:
    """Configuration for 3DGS PLY Cleaning (Numerical & Statistical In-Memory Filtering)."""
    remove_nan_inf: bool = True
    bbox_min: Optional[list[float]] = None  # [min_x, min_y, min_z]
    bbox_max: Optional[list[float]] = None  # [max_x, max_y, max_z]
    statistical_filter_enabled: bool = False
    statistical_std_ratio: float = 3.0
    max_scale_exp: Optional[float] = 10.0  # Exp of scale property (in meters/units)
    min_opacity_raw: Optional[float] = -5.0  # Logit space (-5.0 ~ 0.0067 linear)
    min_opacity_linear: Optional[float] = None  # Optional explicit linear opacity in [0, 1]


@dataclass
class Stage2Config:
    """Configuration for Stage 2: splat-transform Native Tooling Integration."""
    enabled: bool = True
    filter_floaters: Optional[str] = None  # e.g., "0.05,0.1,0.004"
    filter_cluster: Optional[str] = None  # e.g., "1.0,0.999,0.1"
    seed_pos: Optional[list[float]] = None  # [x, y, z] for cluster filtering
    filter_harmonics: Optional[int] = None  # 0, 1, 2, 3
    morton_order: bool = True
    output_ply: bool = True
    output_sog: bool = True
    sh_iterations: int = 10
    splat_transform_cli: Optional[str] = None  # Path to cli.mjs (auto-located if None)
    node_binary: str = "node"


@dataclass
class FilterConfig:
    """Master configuration for NammaSpace Filter Pipeline."""
    name: str = "nammaspace-filter-pipeline"
    version: str = "1.0.0"
    capture: CaptureFilterConfig = field(default_factory=CaptureFilterConfig)
    stage1: Stage1Config = field(default_factory=Stage1Config)  # Preserved PLY cleaning config
    stage2: Stage2Config = field(default_factory=Stage2Config)  # splat-transform config

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterConfig:
        capture_data = data.get("capture", {})
        stage1_data = data.get("stage1", {})
        stage2_data = data.get("stage2", {})
        return cls(
            name=data.get("name", "nammaspace-filter-pipeline"),
            version=data.get("version", "1.0.0"),
            capture=CaptureFilterConfig(**capture_data),
            stage1=Stage1Config(**stage1_data),
            stage2=Stage2Config(**stage2_data),
        )

    def save_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, path: Path | str) -> FilterConfig:
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save_yaml(self, path: Path | str) -> None:
        import yaml
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, sort_keys=False)

    @classmethod
    def load_yaml(cls, path: Path | str) -> FilterConfig:
        import yaml
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f))

    @classmethod
    def load_file(cls, path: Path | str) -> FilterConfig:
        p = Path(path)
        if p.suffix.lower() in {".yaml", ".yml"}:
            return cls.load_yaml(p)
        return cls.load_json(p)
