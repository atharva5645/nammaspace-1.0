from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .config import Stage2Config


@dataclass
class Stage2Result:
    """Result of Stage 2 transformation."""
    success: bool
    output_ply: Optional[Path] = None
    output_sog: Optional[Path] = None
    ply_size_bytes: int = 0
    sog_size_bytes: int = 0
    duration_seconds: float = 0.0
    command_executed: list[str] = None  # type: ignore
    logs: str = ""
    error: Optional[str] = None


def find_splat_transform_cli(custom_path: Optional[str] = None) -> Optional[Path]:
    """Locate the existing splat-transform cli.mjs installation in NammaSpace."""
    if custom_path:
        p = Path(custom_path)
        if p.exists() and p.is_file():
            return p.resolve()

    # Environment variable check
    env_path = os.environ.get("SPLAT_TRANSFORM_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists() and p.is_file():
            return p.resolve()

    # Search known candidate paths relative to this module and repo root
    current_dir = Path(__file__).resolve().parent
    repo_root = current_dir.parent.parent  # e:\Nammaspace-1.0
    candidates = [
        repo_root / "pipeline" / "tools" / "tool-splat-transform" / "bin" / "cli.mjs",
        repo_root / "tool-splat-transform" / "bin" / "cli.mjs",
        repo_root / "pipeline" / "tools" / "tool-splat-transform" / "dist" / "bin" / "cli.mjs",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    return None


def verify_splat_transform_tool(
    cli_path: Optional[Path] = None,
    node_binary: str = "node",
) -> dict[str, Any]:
    """Verify splat-transform execution by running --version and --help."""
    resolved_cli = cli_path or find_splat_transform_cli()
    if not resolved_cli or not resolved_cli.exists():
        return {
            "available": False,
            "path": None,
            "error": "splat-transform cli.mjs not found in project workspace",
        }

    try:
        ver_proc = subprocess.run(
            [node_binary, str(resolved_cli), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        version_output = (ver_proc.stdout.strip() or ver_proc.stderr.strip())
        version_str = version_output if ver_proc.returncode == 0 else "unknown"

        help_proc = subprocess.run(
            [node_binary, str(resolved_cli), "--help"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        help_ok = help_proc.returncode == 0 and ("splat-transform" in help_proc.stdout or "Transform" in help_proc.stdout)

        return {
            "available": help_ok,
            "path": str(resolved_cli),
            "version": version_str,
            "error": None if help_ok else help_proc.stderr.strip(),
        }
    except Exception as exc:
        return {
            "available": False,
            "path": str(resolved_cli),
            "error": str(exc),
        }


def build_actions_list(config: Stage2Config) -> list[str]:
    """Build list of splat-transform action flags based on verified --help options."""
    actions: list[str] = []

    # --seed-pos if provided
    if config.seed_pos is not None:
        x, y, z = config.seed_pos
        actions.extend(["--seed-pos", f"{x},{y},{z}"])

    # --filter-floaters [size,op,min]
    if config.filter_floaters:
        actions.append(f"--filter-floaters={config.filter_floaters}")

    # --filter-cluster [res,op,min]
    if config.filter_cluster:
        actions.append(f"--filter-cluster={config.filter_cluster}")

    # -H, --filter-harmonics <0|1|2|3>
    if config.filter_harmonics is not None:
        actions.extend(["-H", str(config.filter_harmonics)])

    # -m, --morton-order
    if config.morton_order:
        actions.append("-m")

    return actions


def run_stage2_transform(
    input_ply: Path | str,
    output_dir: Path | str,
    config: Stage2Config,
    base_name: str = "scene_filtered",
) -> Stage2Result:
    """Execute Stage 2 transformation and compression using existing splat-transform."""
    input_path = Path(input_ply).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        return Stage2Result(
            success=False,
            error=f"Stage 2 input file does not exist: {input_path}",
        )

    cli_path = find_splat_transform_cli(config.splat_transform_cli)
    if not cli_path or not cli_path.exists():
        return Stage2Result(
            success=False,
            error=f"splat-transform executable cli.mjs could not be located (config={config.splat_transform_cli})",
        )

    start_time = time.time()
    out_ply = out_dir / f"{base_name}.ply" if config.output_ply else None
    out_sog = out_dir / f"{base_name}.sog" if config.output_sog else None

    actions = build_actions_list(config)
    commands_run: list[list[str]] = []
    accumulated_logs: list[str] = []

    try:
        # Step A: Generate filtered PLY if requested
        if out_ply:
            cmd = [
                config.node_binary,
                str(cli_path),
                "-w",  # Overwrite
                "-q",  # Quiet
                str(input_path),
                *actions,
                str(out_ply),
            ]
            commands_run.append(cmd)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
            accumulated_logs.append(f"PLY step: {proc.stdout}\n{proc.stderr}")
            if proc.returncode != 0:
                return Stage2Result(
                    success=False,
                    command_executed=cmd,
                    logs="\n".join(accumulated_logs),
                    error=f"splat-transform PLY stage failed with code {proc.returncode}: {proc.stderr}",
                    duration_seconds=time.time() - start_time,
                )

        # Step B: Generate SOG if requested (from output PLY if exists, else from input PLY)
        if out_sog:
            sog_input = out_ply if (out_ply and out_ply.exists()) else input_path
            cmd_sog = [
                config.node_binary,
                str(cli_path),
                "-w",  # Overwrite
                "-q",
                str(sog_input),
                "-i",
                str(config.sh_iterations),
                str(out_sog),
            ]
            commands_run.append(cmd_sog)
            proc_sog = subprocess.run(
                cmd_sog,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
            accumulated_logs.append(f"SOG step: {proc_sog.stdout}\n{proc_sog.stderr}")
            if proc_sog.returncode != 0:
                return Stage2Result(
                    success=False,
                    command_executed=cmd_sog,
                    logs="\n".join(accumulated_logs),
                    error=f"splat-transform SOG stage failed with code {proc_sog.returncode}: {proc_sog.stderr}",
                    duration_seconds=time.time() - start_time,
                )

        total_duration = time.time() - start_time
        ply_size = out_ply.stat().st_size if (out_ply and out_ply.exists()) else 0
        sog_size = out_sog.stat().st_size if (out_sog and out_sog.exists()) else 0

        return Stage2Result(
            success=True,
            output_ply=out_ply,
            output_sog=out_sog,
            ply_size_bytes=ply_size,
            sog_size_bytes=sog_size,
            duration_seconds=total_duration,
            command_executed=commands_run[-1] if commands_run else [],
            logs="\n".join(accumulated_logs),
        )

    except Exception as exc:
        return Stage2Result(
            success=False,
            duration_seconds=time.time() - start_time,
            error=str(exc),
            logs="\n".join(accumulated_logs),
        )
