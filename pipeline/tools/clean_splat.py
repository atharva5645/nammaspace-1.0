"""Remove smoke / floaters from a 3D Gaussian Splat.

WHEN TO USE THE FULL CLEANUP: only on badly trained splats with visible haze (trained
without depth loss, poor coverage, e.g. the old room_hq.sog). On a well-trained splat
(depth loss + bilateral grid, as pipeline/video_to_scene.py now trains) plain white
walls, doors and cabinets are painted by faint and large blobs, and the opacity / size
rules below punch black holes in them (verified on the Inria playroom scene, Nov 2026).
For those, use --safe (broken + far-away blobs only) and tools/carve_splat.py, which
uses measured photogrammetry depth instead of guesses.

Removes:
  - broken blobs (NaN / Inf values),
  - blobs far outside the scene (outside the 1st-99th percentile box, padded),
  - nearly invisible blobs (they stack up into grey/black haze),
  - dark, faint blobs,
  - huge blobs (default: wider than 3% of the scene) that hang in mid-air like a curtain.

It cannot fix wrong colours baked into wall/floor surfaces; that needs a better
capture or training (see the training options in pipeline/video_to_scene.py).

Input and output can be .ply or .sog (.sog is converted with @playcanvas/splat-transform,
which needs Node.js). A JSON report is written next to the output.

  python pipeline/tools/clean_splat.py room.sog room_clean.sog
  python pipeline/tools/clean_splat.py point_cloud_29999.ply clean.ply --max-size 0.4

Runs in seconds on ~1M blobs (NumPy only), unlike splat-transform's --filter-floaters,
which runs mostly on one CPU core and can take 20+ minutes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SPLAT_TRANSFORM = "@playcanvas/splat-transform@3.10.1"
# max_size / pad of None mean RELATIVE x the scene's box diagonal
DEFAULTS = {"min_opacity": 0.02, "dark_opacity": 0.10, "max_size": None, "pad": None}
RELATIVE = 0.03
# For well-trained splats: keep faint and large blobs, only drop broken ones and ones
# more than half the scene size beyond the 1st-99th percentile box.
SAFE = {"min_opacity": 0.0, "dark_opacity": 0.0, "max_size": float("inf"), "pad": None, "pad_frac": 0.5}


def read_ply(path: Path):
    with open(path, "rb") as f:
        header, names, count = [], [], 0
        while True:
            raw = f.readline()
            if not raw:
                raise ValueError(f"{path}: no end_header, not a PLY file")
            header.append(raw)
            line = raw.decode().strip()
            if line.startswith("format") and "binary_little_endian" not in line:
                raise ValueError(f"{path}: only binary_little_endian PLY is supported")
            if line.startswith("element vertex"):
                count = int(line.split()[-1])
            elif line.startswith("property"):
                if line.split()[1] != "float":
                    raise ValueError(f"{path}: only float properties are supported ({line})")
                names.append(line.split()[-1])
            elif line == "end_header":
                break
        data = np.fromfile(f, dtype=np.float32, count=count * len(names))
    return header, names, data.reshape(count, len(names))


def write_ply(path: Path, header, data) -> None:
    with open(path, "wb") as f:
        for raw in header:
            if raw.decode().startswith("element vertex"):
                raw = f"element vertex {len(data)}\n".encode()
            f.write(raw)
        data.astype(np.float32).tofile(f)


def clean_ply(src: Path, dst: Path, min_opacity=DEFAULTS["min_opacity"],
              dark_opacity=DEFAULTS["dark_opacity"], max_size=DEFAULTS["max_size"],
              pad=DEFAULTS["pad"], pad_frac=RELATIVE) -> dict:
    """Filter one .ply into another and return counts of what was removed."""
    header, names, d = read_ply(src)
    c = {n: i for i, n in enumerate(names)}
    for need in ("x", "opacity", "scale_0", "f_dc_0"):
        if need not in c:
            raise ValueError(f"{src}: missing '{need}', not a Gaussian splat PLY")

    finite = np.all(np.isfinite(d), axis=1)
    safe = np.where(finite[:, None], d, 0.0)
    xyz = safe[:, [c["x"], c["y"], c["z"]]]
    opacity = 1 / (1 + np.exp(-np.clip(safe[:, c["opacity"]], -50, 50)))
    size = np.exp(np.clip(safe[:, [c["scale_0"], c["scale_1"], c["scale_2"]]], -30, 30)).max(axis=1)
    bright = (safe[:, [c["f_dc_0"], c["f_dc_1"], c["f_dc_2"]]] * 0.28209479 + 0.5).mean(axis=1)

    lo = np.percentile(xyz[finite], 1, axis=0)
    hi = np.percentile(xyz[finite], 99, axis=0)
    # COLMAP scenes have no fixed scale, so default limits follow the scene size
    diag = float(np.linalg.norm(hi - lo))
    max_size = RELATIVE * diag if max_size is None else max_size
    pad = pad_frac * diag if pad is None else pad
    lo, hi = lo - pad, hi + pad
    checks = {
        "broken (NaN/Inf)": ~finite,
        "outside scene": ~np.all((xyz >= lo) & (xyz <= hi), axis=1),
        "nearly invisible": opacity < min_opacity,
        "dark and faint": (bright < 0.05) & (opacity < dark_opacity),
        "huge": size > max_size,
    }
    drop = np.zeros(len(d), bool)
    removed = {}
    for label, m in checks.items():
        removed[label] = int((m & ~drop).sum())
        drop |= m
    write_ply(dst, header, d[~drop])
    return {
        "input": str(src), "output": str(dst),
        "settings": {"min_opacity": min_opacity, "dark_opacity": dark_opacity,
                     "max_size": round(max_size, 4), "pad": round(pad, 4),
                     "scene_diagonal": round(diag, 3)},
        "scene_box": {"min": np.round(lo, 3).tolist(), "max": np.round(hi, 3).tolist()},
        "blobs_in": int(len(d)), "blobs_out": int((~drop).sum()), "removed": removed,
    }


def _splat_transform(args: list) -> None:
    npx = shutil.which("npx.cmd" if sys.platform == "win32" else "npx") or "npx"
    # -g 0 uses the first GPU for .sog compression (seconds instead of minutes)
    cmd = [npx, "-y", SPLAT_TRANSFORM, "-w", "-q"] + [str(a) for a in args]
    subprocess.run(cmd, check=True)


def clean_any(src: Path, dst: Path, **settings) -> dict:
    """Clean a .ply or .sog into a .ply or .sog, and write <dst>.clean_report.json."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ply_in = src
        if src.suffix.lower() != ".ply":
            ply_in = tmp / "in.ply"
            _splat_transform([src, ply_in])
        ply_out = dst if dst.suffix.lower() == ".ply" else tmp / "out.ply"
        report = clean_ply(ply_in, ply_out, **settings)
        if ply_out != dst:
            _splat_transform(["-g", "0", ply_out, dst])
    report["input"], report["output"] = str(src), str(dst)
    dst.with_name(dst.name + ".clean_report.json").write_text(json.dumps(report, indent=2))
    return report


def print_report(report: dict) -> None:
    for label, n in report["removed"].items():
        print(f"  {label:18s} {n:9d}")
    pct = report["blobs_out"] / max(report["blobs_in"], 1)
    print(f"  kept {report['blobs_out']} of {report['blobs_in']} blobs ({pct:.0%}) -> {report['output']}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src", type=Path, help="input .ply or .sog")
    p.add_argument("dst", type=Path, help="output .ply or .sog")
    p.add_argument("--min-opacity", type=float, default=DEFAULTS["min_opacity"],
                   help="drop blobs below this opacity (default %(default)s)")
    p.add_argument("--dark-opacity", type=float, default=DEFAULTS["dark_opacity"],
                   help="drop dark blobs below this opacity (default %(default)s)")
    p.add_argument("--max-size", type=float, default=DEFAULTS["max_size"],
                   help="drop blobs larger than this, in scene units (default: 3%% of scene size)")
    p.add_argument("--pad", type=float, default=DEFAULTS["pad"],
                   help="padding around the scene box, in scene units (default: 3%% of scene size)")
    p.add_argument("--safe", action="store_true",
                   help="only remove broken blobs and ones far outside the scene (for well-trained splats)")
    a = p.parse_args()
    print(f"cleaning {a.src}")
    settings = SAFE if a.safe else dict(min_opacity=a.min_opacity, dark_opacity=a.dark_opacity,
                                        max_size=a.max_size, pad=a.pad)
    print_report(clean_any(a.src, a.dst, **settings))


if __name__ == "__main__":
    main()
