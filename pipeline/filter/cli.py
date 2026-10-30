from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import FilterConfig, Stage1Config, Stage2Config, CaptureFilterConfig
from .stage2_transform import verify_splat_transform_tool, find_splat_transform_cli
from .synthetic import generate_synthetic_ply_file
from .pipeline import FilterPipeline


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.filter.cli",
        description="NammaSpace Independent Filter Pipeline (Capture Preprocessing & 3DGS Splat Transformation)",
    )
    parser.add_argument(
        "--check-tools",
        action="store_true",
        help="Check availability and health of splat-transform installation and exit",
    )
    parser.add_argument(
        "--generate-synthetic",
        type=str,
        default=None,
        metavar="PATH",
        help="Generate a small synthetic 3DGS test PLY at PATH and exit",
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        help="Path to input (video file, image folder, or 3DGS .ply file)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        help="Directory to save outputs and filter_report.json",
    )
    parser.add_argument(
        "--stage",
        choices=["auto", "capture", "splat"],
        default="auto",
        help="Execution target: 'capture' (video/image preprocessing), 'splat' (PLY cleaning/transformation), or 'auto' (detect from input)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON configuration file for FilterConfig",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="scene_filtered",
        help="Base name for output files (default: scene_filtered)",
    )

    # Capture stage flags (Stage 1)
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Frame rate to extract from input video (default: 2.0 fps)",
    )
    parser.add_argument(
        "--min-blur",
        type=float,
        default=None,
        help="Minimum Laplacian variance threshold (default: 80.0; lower is dropped as blur)",
    )
    parser.add_argument(
        "--min-lum",
        type=float,
        default=None,
        help="Minimum mean luminance threshold (default: 35.0; lower is dropped as under-exposed)",
    )
    parser.add_argument(
        "--max-lum",
        type=float,
        default=None,
        help="Maximum mean luminance threshold (default: 225.0; higher is dropped as over-exposed)",
    )
    parser.add_argument(
        "--dup-thresh",
        type=float,
        default=None,
        help="Near-duplicate similarity threshold against last kept frame (default: 0.95)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Optional even frame-count cap to subsample after filtering",
    )
    parser.add_argument(
        "--out-format",
        type=str,
        default="jpg",
        choices=["jpg", "png"],
        help="Output format for filtered stage1 images (default: jpg)",
    )

    # Splat stage flags (Stages 2 & 3)
    parser.add_argument(
        "--bbox-min",
        type=float,
        nargs=3,
        default=None,
        metavar=("X", "Y", "Z"),
        help="Minimum bounding box corner for PLY spatial filtering",
    )
    parser.add_argument(
        "--bbox-max",
        type=float,
        nargs=3,
        default=None,
        metavar=("X", "Y", "Z"),
        help="Maximum bounding box corner for PLY spatial filtering",
    )
    parser.add_argument(
        "--filter-floaters",
        type=str,
        default=None,
        help="splat-transform floater filter spec, e.g., '0.05,0.1,0.004'",
    )
    parser.add_argument(
        "--filter-cluster",
        type=str,
        default=None,
        help="splat-transform cluster filter spec, e.g., '1.0,0.999,0.1'",
    )
    parser.add_argument(
        "--disable-stage2",
        action="store_true",
        help="Execute Stage 1 in-memory filtering only, skipping splat-transform",
    )
    parser.add_argument(
        "--no-sog",
        action="store_true",
        help="Skip .sog compression in Stage 2",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and check input file existence without writing outputs",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # 1. Tool check mode
    if args.check_tools:
        print("=== NammaSpace Filter Pipeline Tool Verification ===")
        cli_loc = find_splat_transform_cli()
        print(f"Discovered splat-transform cli: {cli_loc}")
        check = verify_splat_transform_tool(cli_loc)
        print(json.dumps(check, indent=2))
        return 0 if check["available"] else 1

    # 2. Synthetic asset generation mode
    if args.generate_synthetic:
        out_p = Path(args.generate_synthetic)
        print(f"Generating synthetic 3DGS test asset at {out_p}...")
        p, counts = generate_synthetic_ply_file(out_p)
        print(f"Created synthetic PLY ({p.stat().st_size} bytes):")
        print(json.dumps(counts, indent=2))
        return 0

    # 3. Pipeline execution mode
    if not args.input or not args.output_dir:
        print("Error: Both --input (-i) and --output-dir (-o) are required for pipeline execution.", file=sys.stderr)
        print("Use --check-tools to audit installed tooling or --help for instructions.", file=sys.stderr)
        return 2

    # Load or construct config
    if args.config:
        config = FilterConfig.load_file(args.config)
    else:
        config = FilterConfig()

    # Apply capture CLI overrides
    if args.fps is not None:
        config.capture.extraction_fps = args.fps
    if args.min_blur is not None:
        config.capture.min_laplacian_var = args.min_blur
    if args.min_lum is not None:
        config.capture.min_mean_luminance = args.min_lum
    if args.max_lum is not None:
        config.capture.max_mean_luminance = args.max_lum
    if args.dup_thresh is not None:
        config.capture.near_duplicate_threshold = args.dup_thresh
    if args.max_frames is not None:
        config.capture.max_frames_cap = args.max_frames
    if args.out_format:
        config.capture.output_image_format = args.out_format

    # Apply splat CLI overrides
    if args.bbox_min and args.bbox_max:
        config.stage1.bbox_min = list(args.bbox_min)
        config.stage1.bbox_max = list(args.bbox_max)
    if args.filter_floaters:
        config.stage2.filter_floaters = args.filter_floaters
    if args.filter_cluster:
        config.stage2.filter_cluster = args.filter_cluster
    if args.disable_stage2:
        config.stage2.enabled = False
    if args.no_sog:
        config.stage2.output_sog = False

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    is_capture_input = input_path.is_dir() or input_path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}
    target_stage = args.stage
    if target_stage == "auto":
        target_stage = "capture" if is_capture_input else "splat"

    if args.dry_run:
        print(f"=== NammaSpace Filter Pipeline DRY RUN [Stage: {target_stage}] ===")
        print(f"Input:      {input_path.resolve()} (exists={input_path.exists()})")
        print(f"Output Dir: {output_dir.resolve()}")
        print("Configuration:")
        print(json.dumps(config.to_dict(), indent=2))
        return 0 if input_path.exists() else 1

    pipeline = FilterPipeline(config=config)
    if target_stage == "capture":
        report = pipeline.run_capture(
            input_source=input_path,
            output_dir=output_dir,
            capture_config=config.capture,
        )
    else:
        report = pipeline.run_splat(
            input_ply=input_path,
            output_dir=output_dir,
            base_name=args.name,
        )

    print(f"\n=== Pipeline Execution Summary [{target_stage.upper()}] ===")
    print(f"Status:   {report.status}")
    print(f"Duration: {report.total_duration_seconds:.2f}s")
    print(f"Report:   {output_dir / 'filter_report.json'}")
    if report.status == "SUCCESS":
        if target_stage == "capture":
            extracted = report.stage1_stats.get("total_frames_extracted", 0)
            kept = report.stage1_stats.get("kept_frames_count", 0)
            print(f"Extracted Frames: {extracted}")
            print(f"Kept Frames:      {kept}")
            print(f"Dropped Breakdown: {report.stage1_stats.get('dropped_counts', {})}")
            print(f"Stage 1 Output:   {report.final_outputs.get('stage1_folder', '')}")
        else:
            print(f"Stage 1 Culled: {report.stage1_stats.get('cull_ratio', 0.0)*100:.1f}%")
            print(f"Final Outputs:  {list(report.final_outputs.keys())}")
        return 0
    else:
        print(f"Error: {report.error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
