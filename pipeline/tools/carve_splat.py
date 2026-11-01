"""Remove smoke from a splat using photogrammetry depth maps ("free-space carving").

For every photo, COLMAP's dense step records how far away the first real surface is
at each pixel. A splat blob that sits clearly *in front of* that surface in several
photos is floating in air the camera saw straight through, so it is smoke.

Kept on purpose:
  - blobs on or near a surface,
  - blobs *behind* a surface (splats fake reflections on shiny floors, TVs and glass
    by placing blobs behind them),
  - blobs where photogrammetry has no reliable depth (shiny, blank or unseen areas):
    those pixels are simply not used, so the splat is trusted there.

Needs the COLMAP dense workspace the splat was trained on (images/, sparse/,
stereo/depth_maps/*.geometric.bin). gsplat moves and scales the scene during
training ("normalize world space"); --gsplat-normalized (default on) applies the same
transform, so pass the same folder that was given to gsplat as --data-dir.

  python pipeline/tools/carve_splat.py splat.ply dense_workspace/ carved.ply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_splat import read_ply, write_ply  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def read_colmap_array(path: Path) -> np.ndarray:
    """Read a COLMAP depth map (.bin) into an (H, W) float32 array."""
    with open(path, "rb") as f:
        header = b""
        while header.count(b"&") < 3:
            header += f.read(1)
        w, h, c = (int(x) for x in header.decode().split("&")[:3])
        data = np.fromfile(f, np.float32)
    return data.reshape((c, h, w)).transpose(1, 2, 0)[:, :, 0] if c > 1 else data.reshape(h, w)


def _parser(workspace: Path, normalized: bool):
    sys.path.insert(0, str(REPO / "external" / "gsplat" / "examples"))
    from datasets.colmap import Parser  # gsplat's own loader, so the transform matches training

    return Parser(data_dir=str(workspace), factor=1, normalize=normalized, test_every=10**9)


def export_mesh(mesh_in: Path, workspace: Path, mesh_out: Path, normalized: bool = True) -> None:
    """Copy a COLMAP-space mesh into the splat's coordinates (for collision / navmesh)."""
    import trimesh

    mesh = trimesh.load(mesh_in, process=False)
    mesh.apply_transform(_parser(workspace, normalized).transform)
    mesh.export(mesh_out)


def load_cameras(workspace: Path, normalized: bool):
    """Camera-to-world matrices, intrinsics and image names, in the splat's coordinates."""
    parser = _parser(workspace, normalized)
    scale = float(np.cbrt(np.linalg.det(parser.transform[:3, :3])))
    cams = []
    for name, c2w, cid in zip(parser.image_names, parser.camtoworlds, parser.camera_ids):
        cams.append((name, c2w, parser.Ks_dict[cid].copy(), parser.imsize_dict[cid]))
    return cams, scale


def carve(splat: Path, workspace: Path, dst: Path, rel_margin=0.05, min_votes=3,
          min_ratio=0.5, normalized=True) -> dict:
    header, names, d = read_ply(splat)
    c = {n: i for i, n in enumerate(names)}
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    xyz = torch.tensor(d[:, [c["x"], c["y"], c["z"]]], device=dev)
    ones = torch.ones((len(xyz), 1), device=dev)
    xyz_h = torch.cat([xyz, ones], 1)

    cams, scale = load_cameras(workspace, normalized)
    depth_dir = workspace / "stereo" / "depth_maps"
    front = torch.zeros(len(xyz), dtype=torch.int32, device=dev)  # photos seeing it in free space
    seen = torch.zeros(len(xyz), dtype=torch.int32, device=dev)   # photos with valid depth there
    used = 0
    for name, c2w, K, (w, h) in cams:
        dm_path = depth_dir / f"{name}.geometric.bin"
        if not dm_path.exists():
            continue
        dm = read_colmap_array(dm_path)
        dh, dw = dm.shape
        K = K.copy()
        K[0] *= dw / w  # depth maps can be smaller than the image
        K[1] *= dh / h
        depth = torch.tensor(dm * scale, device=dev)  # COLMAP units -> splat units
        w2c = torch.tensor(np.linalg.inv(c2w), dtype=torch.float32, device=dev)
        p = (xyz_h @ w2c.T)[:, :3]
        z = p[:, 2]
        Kt = torch.tensor(K, dtype=torch.float32, device=dev)
        u = (Kt[0, 0] * p[:, 0] / z + Kt[0, 2]).floor().long()
        v = (Kt[1, 1] * p[:, 1] / z + Kt[1, 2]).floor().long()
        inside = (z > 1e-3) & (u >= 0) & (u < dw) & (v >= 0) & (v < dh)
        idx = torch.nonzero(inside).squeeze(1)
        surf = depth[v[idx], u[idx]]
        valid = surf > 0  # 0 = no reliable depth (shiny / blank / unseen): trust the splat
        idx, surf, zi = idx[valid], surf[valid], z[idx][valid]
        seen[idx] += 1
        front[idx[zi < surf * (1 - rel_margin)]] += 1
        used += 1

    ratio = front.float() / seen.clamp(min=1).float()
    smoke = ((front >= min_votes) & (ratio >= min_ratio)).cpu().numpy()
    write_ply(dst, header, d[~smoke])
    report = {
        "input": str(splat), "workspace": str(workspace), "output": str(dst),
        "photos_used": used, "blobs_in": int(len(d)), "blobs_out": int((~smoke).sum()),
        "removed_free_space": int(smoke.sum()),
        "never_checked_no_depth": int((seen == 0).sum().item()),
        "settings": {"rel_margin": rel_margin, "min_votes": min_votes, "min_ratio": min_ratio,
                     "gsplat_normalized": normalized, "colmap_to_splat_scale": round(scale, 5)},
    }
    dst.with_name(dst.name + ".carve_report.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("splat", type=Path, help="input splat .ply")
    p.add_argument("workspace", type=Path, help="COLMAP dense workspace (the gsplat --data-dir)")
    p.add_argument("dst", type=Path, help="output .ply")
    p.add_argument("--margin", type=float, default=0.05,
                   help="a blob counts as 'in front' if closer than the surface by this fraction")
    p.add_argument("--min-votes", type=int, default=3, help="photos that must see the blob in free space")
    p.add_argument("--min-ratio", type=float, default=0.5,
                   help="share of photos (with depth there) that must see it in free space")
    p.add_argument("--no-gsplat-normalized", dest="normalized", action="store_false",
                   help="splat is in raw COLMAP coordinates (not gsplat's normalized space)")
    a = p.parse_args()
    r = carve(a.splat, a.workspace, a.dst, a.margin, a.min_votes, a.min_ratio, a.normalized)
    print(f"photos used: {r['photos_used']}")
    print(f"removed {r['removed_free_space']} floating blobs, kept {r['blobs_out']} of {r['blobs_in']}")
    print(f"{r['never_checked_no_depth']} blobs had no depth in any photo and were left alone")


if __name__ == "__main__":
    main()
