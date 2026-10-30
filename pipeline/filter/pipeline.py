from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import FilterConfig, CaptureFilterConfig
from .stage1_capture import run_stage1_capture, Stage1CaptureResult
from .ply_io import read_ply_gaussian, write_ply_gaussian
from .stage1_filter import run_stage1_filter, Stage1Result
from .stage2_transform import run_stage2_transform, Stage2Result


@dataclass
class PipelineReport:
    """Comprehensive execution telemetry and audit report."""
    schema: str
    status: str
    timestamp: str
    input_file: str
    output_dir: str
    config: dict[str, Any]
    stage1_stats: dict[str, Any]
    stage2_stats: dict[str, Any]
    final_outputs: dict[str, Any]
    total_duration_seconds: float
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


class FilterPipeline:
    """Independent multi-stage filter and asset transformation pipeline."""

    def __init__(self, config: Optional[FilterConfig] = None):
        self.config = config or FilterConfig()

    def run_capture(
        self,
        input_source: Path | str,
        output_dir: Path | str,
        capture_config: Optional[CaptureFilterConfig] = None,
    ) -> PipelineReport:
        """Execute Stage 1: Phone-video / image-directory capture preprocessing."""
        start_time = time.time()
        in_src = Path(input_source).resolve()
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        cfg = capture_config or self.config.capture
        iso_now = datetime.now(timezone.utc).isoformat()

        res: Stage1CaptureResult = run_stage1_capture(
            input_source=in_src,
            output_dir=out_dir,
            config=cfg,
        )

        stage1_stats = {
            "total_frames_extracted": res.total_frames_extracted,
            "kept_frames_count": res.kept_frames_count,
            "dropped_counts": res.dropped_counts,
            "drop_reasons": res.drop_reasons,
        }
        final_outputs = {
            "stage1_folder": str(res.stage1_dir),
            "kept_images": [str(p) for p in res.output_image_paths],
            "manifest_file": str(res.stage1_dir / "frames_manifest.json"),
        }

        report = PipelineReport(
            schema="nammaspace.filter_pipeline.capture_report.v1.0",
            status="SUCCESS" if res.success else "FAILED",
            timestamp=iso_now,
            input_file=str(in_src),
            output_dir=str(out_dir),
            config={"capture": asdict(cfg)},
            stage1_stats=stage1_stats,
            stage2_stats={},
            final_outputs=final_outputs,
            total_duration_seconds=time.time() - start_time,
            error=res.error,
        )
        report.save_json(out_dir / "filter_report.json")
        return report

    def run_splat(
        self,
        input_ply: Path | str,
        output_dir: Path | str,
        base_name: str = "scene_filtered",
    ) -> PipelineReport:
        """Execute 3DGS PLY cleaning and Stage 2 splat-transform integration."""
        start_time = time.time()
        in_path = Path(input_ply).resolve()
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        iso_now = datetime.now(timezone.utc).isoformat()

        if not in_path.exists():
            report = PipelineReport(
                schema="nammaspace.filter_pipeline.report.v1.0",
                status="FAILED",
                timestamp=iso_now,
                input_file=str(in_path),
                output_dir=str(out_dir),
                config=self.config.to_dict(),
                stage1_stats={},
                stage2_stats={},
                final_outputs={},
                total_duration_seconds=time.time() - start_time,
                error=f"Input file does not exist: {in_path}",
            )
            report.save_json(out_dir / "filter_report.json")
            return report

        try:
            # Stage 1: In-memory Statistical & Numerical Filtering on PLY
            raw_data, header_meta = read_ply_gaussian(in_path)
            stage1_res = run_stage1_filter(raw_data, self.config.stage1)

            stage1_ply_path = out_dir / f"{base_name}_stage1.ply"
            write_ply_gaussian(stage1_ply_path, stage1_res.data, comments=["Stage 1 Filtered"])

            # Stage 2: splat-transform Native Tooling Integration
            stage2_stats: dict[str, Any] = {}
            final_outputs: dict[str, Any] = {
                "stage1_ply": str(stage1_ply_path),
                "stage1_ply_size_bytes": stage1_ply_path.stat().st_size,
                "stage1_gaussian_count": stage1_res.stats.get("surviving_count", 0),
            }

            if self.config.stage2.enabled:
                stage2_res = run_stage2_transform(
                    input_ply=stage1_ply_path,
                    output_dir=out_dir,
                    config=self.config.stage2,
                    base_name=base_name,
                )
                stage2_stats = {
                    "success": stage2_res.success,
                    "duration_seconds": stage2_res.duration_seconds,
                    "command_executed": stage2_res.command_executed,
                    "error": stage2_res.error,
                }
                if stage2_res.output_ply and stage2_res.output_ply.exists():
                    final_outputs["final_ply"] = str(stage2_res.output_ply)
                    final_outputs["final_ply_size_bytes"] = stage2_res.ply_size_bytes
                if stage2_res.output_sog and stage2_res.output_sog.exists():
                    final_outputs["final_sog"] = str(stage2_res.output_sog)
                    final_outputs["final_sog_size_bytes"] = stage2_res.sog_size_bytes

                if not stage2_res.success:
                    report = PipelineReport(
                        schema="nammaspace.filter_pipeline.report.v1.0",
                        status="STAGE2_FAILED",
                        timestamp=iso_now,
                        input_file=str(in_path),
                        output_dir=str(out_dir),
                        config=self.config.to_dict(),
                        stage1_stats=stage1_res.stats,
                        stage2_stats=stage2_stats,
                        final_outputs=final_outputs,
                        total_duration_seconds=time.time() - start_time,
                        error=stage2_res.error,
                    )
                    report.save_json(out_dir / "filter_report.json")
                    return report

            total_duration = time.time() - start_time
            report = PipelineReport(
                schema="nammaspace.filter_pipeline.report.v1.0",
                status="SUCCESS",
                timestamp=iso_now,
                input_file=str(in_path),
                output_dir=str(out_dir),
                config=self.config.to_dict(),
                stage1_stats=stage1_res.stats,
                stage2_stats=stage2_stats,
                final_outputs=final_outputs,
                total_duration_seconds=total_duration,
            )
            report.save_json(out_dir / "filter_report.json")
            return report

        except Exception as exc:
            total_duration = time.time() - start_time
            report = PipelineReport(
                schema="nammaspace.filter_pipeline.report.v1.0",
                status="ERROR",
                timestamp=iso_now,
                input_file=str(in_path),
                output_dir=str(out_dir),
                config=self.config.to_dict(),
                stage1_stats={},
                stage2_stats={},
                final_outputs={},
                total_duration_seconds=total_duration,
                error=str(exc),
            )
            report.save_json(out_dir / "filter_report.json")
            return report

    def run(
        self,
        input_path: Path | str | None = None,
        output_dir: Path | str | None = None,
        base_name: str = "scene_filtered",
        input_ply: Path | str | None = None,
    ) -> PipelineReport:
        """Unified dispatch: automatically chooses capture preprocessing or splat cleaning."""
        target_input = input_path if input_path is not None else input_ply
        if target_input is None:
            raise ValueError("FilterPipeline.run requires either input_path or input_ply")
        if output_dir is None:
            raise ValueError("FilterPipeline.run requires output_dir")
        p = Path(target_input)
        if p.is_dir() or p.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}:
            return self.run_capture(input_source=p, output_dir=output_dir)
        else:
            return self.run_splat(input_ply=p, output_dir=output_dir, base_name=base_name)
