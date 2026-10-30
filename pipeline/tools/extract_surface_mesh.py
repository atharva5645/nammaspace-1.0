#!/usr/bin/env python3
"""
NammaSpace 3D Surface Mesh Extraction Pipeline
==============================================
Converts 3D Gaussian Splats (.ply) or COLMAP sparse point clouds into
watertight, high-fidelity polygonal surface meshes (.glb, .obj, .ply)
using Screened Poisson Surface Reconstruction and Open3D.

Usage Examples:
    # Extract surface mesh from Gaussian Splat PLY and export as web-ready GLB
    python pipeline/tools/extract_surface_mesh.py \
        --input data/experiments/room001_filter65/splat/ply/point_cloud_998.ply \
        --output frontend/namma-space/public/room_surface_mesh.glb \
        --depth 9 \
        --target_faces 150000

    # Extract surface mesh from COLMAP sparse reconstruction
    python pipeline/tools/extract_surface_mesh.py \
        --input data/experiments/supermarket001_seq0_colmap_dense/sparse/0/points3D.txt \
        --output frontend/namma-space/public/supermarket_surface_mesh.glb \
        --depth 8
"""

import os
import sys
import time
import argparse
from pathlib import Path
import numpy as np
import open3d as o3d
import trimesh

SH_C0 = 0.28209479177387814

def parse_args():
    parser = argparse.ArgumentParser(
        description="NammaSpace Surface Mesh Reconstruction Tool (Point Cloud/Splat to Polygonal Mesh)"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="Path to input 3DGS PLY or COLMAP points3D.txt/points3D.bin"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        required=True,
        help="Path to output 3D mesh (.glb, .obj, .ply)"
    )
    parser.add_argument(
        "--depth", "-d",
        type=int,
        default=9,
        help="Octree depth for Poisson reconstruction (higher = finer detail, default: 9, max: 12)"
    )
    parser.add_argument(
        "--density_trim",
        type=float,
        default=5.0,
        help="Percentile threshold to prune low-density outlier surfaces (default: 5.0%%)"
    )
    parser.add_argument(
        "--target_faces",
        type=int,
        default=200000,
        help="Target number of triangular faces for mesh decimation (default: 200,000, 0 = no decimation)"
    )
    parser.add_argument(
        "--filter_outliers",
        action="store_true",
        default=True,
        help="Apply statistical outlier removal before normal estimation"
    )
    parser.add_argument(
        "--normals_radius",
        type=float,
        default=0.15,
        help="Search radius for normal estimation (in meters, default: 0.15)"
    )
    return parser.parse_args()


def load_points_and_colors(input_path: str):
    """
    Parses points and RGB colors from 3DGS PLY or COLMAP files.
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    print(f"Loading input spatial data from: {input_path}")
    t0 = time.time()

    # 1. Check if COLMAP points3D.txt
    if path.name == "points3D.txt":
        points, colors = [], []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 8:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    r, g, b = int(parts[4]), int(parts[5]), int(parts[6])
                    points.append([x, y, z])
                    colors.append([r / 255.0, g / 255.0, b / 255.0])
        pts_np = np.array(points, dtype=np.float32)
        cols_np = np.array(colors, dtype=np.float32)
        print(f"Loaded {len(pts_np):,} points from COLMAP points3D.txt in {time.time()-t0:.2f}s")
        return pts_np, cols_np

    # 2. Check if PLY (3D Gaussian Splatting or Standard Mesh/PCD)
    if path.suffix.lower() == ".ply":
        mesh_or_pcd = trimesh.load(str(path))
        if hasattr(mesh_or_pcd, "metadata") and "_ply_raw" in mesh_or_pcd.metadata:
            raw_data = mesh_or_pcd.metadata["_ply_raw"]["vertex"]["data"]
            x = raw_data["x"]
            y = raw_data["y"]
            z = raw_data["z"]
            pts_np = np.stack([x, y, z], axis=-1).astype(np.float32)

            # Colors from SH DC coefficients or standard RGB
            if "f_dc_0" in raw_data.dtype.names:
                r = np.clip(0.5 + SH_C0 * raw_data["f_dc_0"], 0.0, 1.0)
                g = np.clip(0.5 + SH_C0 * raw_data["f_dc_1"], 0.0, 1.0)
                b = np.clip(0.5 + SH_C0 * raw_data["f_dc_2"], 0.0, 1.0)
                cols_np = np.stack([r, g, b], axis=-1).astype(np.float32)
            elif "red" in raw_data.dtype.names:
                r = raw_data["red"].astype(np.float32) / 255.0
                g = raw_data["green"].astype(np.float32) / 255.0
                b = raw_data["blue"].astype(np.float32) / 255.0
                cols_np = np.stack([r, g, b], axis=-1)
            else:
                cols_np = np.ones((len(pts_np), 3), dtype=np.float32) * 0.75

            # Opacity filter if 3DGS
            if "opacity" in raw_data.dtype.names:
                opas = 1.0 / (1.0 + np.exp(-raw_data["opacity"]))
                valid_mask = opas > 0.05
                pts_np = pts_np[valid_mask]
                cols_np = cols_np[valid_mask]

            print(f"Loaded {len(pts_np):,} valid splat centroids from PLY in {time.time()-t0:.2f}s")
            return pts_np, cols_np
        elif hasattr(mesh_or_pcd, "vertices"):
            pts_np = np.array(mesh_or_pcd.vertices, dtype=np.float32)
            if hasattr(mesh_or_pcd, "visual") and hasattr(mesh_or_pcd.visual, "vertex_colors"):
                cols = np.array(mesh_or_pcd.visual.vertex_colors)[:, :3].astype(np.float32) / 255.0
            else:
                cols = np.ones((len(pts_np), 3), dtype=np.float32) * 0.75
            return pts_np, cols

    # 3. Fallback Open3D loader
    pcd = o3d.io.read_point_cloud(str(path))
    pts_np = np.asarray(pcd.points, dtype=np.float32)
    cols_np = np.asarray(pcd.colors, dtype=np.float32)
    if len(cols_np) == 0:
        cols_np = np.ones((len(pts_np), 3), dtype=np.float32) * 0.75
    return pts_np, cols_np


def reconstruct_surface_mesh(
    pts_np: np.ndarray,
    cols_np: np.ndarray,
    depth: int = 9,
    density_trim: float = 5.0,
    target_faces: int = 200000,
    filter_outliers: bool = True,
    normals_radius: float = 0.15,
):
    print("=" * 70)
    print("STARTING SURFACE RECONSTRUCTION PIPELINE")
    print("=" * 70)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts_np.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(cols_np.astype(np.float64))

    # 1. Statistical Outlier Removal
    if filter_outliers and len(pcd.points) > 100:
        print("Step 1: Removing statistical floaters and outliers...")
        pcd, ind = pcd.remove_statistical_outlier(nb_neighbors=25, std_ratio=2.0)
        print(f"   Retained {len(pcd.points):,} points after outlier pruning.")

    # 2. Normal Estimation
    print(f"Step 2: Estimating surface normals (search radius: {normals_radius}m)...")
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=normals_radius, max_nn=35)
    )
    pcd.orient_normals_consistent_tangent_plane(k=15)

    # 3. Screened Poisson Surface Reconstruction
    print(f"Step 3: Screened Poisson Surface Reconstruction (octree depth: {depth})...")
    t_rec = time.time()
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=depth, linear_fit=True
    )
    densities = np.asarray(densities)
    print(f"   Poisson generation completed in {time.time()-t_rec:.2f}s.")
    print(f"   Raw mesh: {len(mesh.vertices):,} vertices, {len(mesh.triangles):,} faces.")

    # 4. Trim Low-Density Outliers (removes the enclosing Poisson sphere bubble)
    if density_trim > 0 and len(densities) > 0:
        print(f"Step 4: Pruning unobserved volume bubble (bottom {density_trim}% density)...")
        threshold = np.percentile(densities, density_trim)
        vertices_to_remove = densities < threshold
        mesh.remove_vertices_by_mask(vertices_to_remove)
        print(f"   After density trim: {len(mesh.vertices):,} vertices, {len(mesh.triangles):,} faces.")

    # 5. Crop to Bounding Box of original point cloud with 10% safety margin
    bbox = pcd.get_axis_aligned_bounding_box()
    bbox.scale(1.10, bbox.get_center())
    mesh = mesh.crop(bbox)

    # 6. Transfer Point Cloud Colors to Mesh Vertices
    print("Step 5: Interpolating surface vertex colors from point cloud...")
    kdtree = o3d.geometry.KDTreeFlann(pcd)
    mesh_verts = np.asarray(mesh.vertices)
    mesh_colors = np.zeros_like(mesh_verts)

    for i in range(len(mesh_verts)):
        _, idxs, _ = kdtree.search_knn_vector_3d(mesh_verts[i], 3)
        colors_knn = np.asarray(pcd.colors)[idxs]
        mesh_colors[i] = np.mean(colors_knn, axis=0)

    mesh.vertex_colors = o3d.utility.Vector3dVector(mesh_colors)

    # 7. Mesh Simplification / Decimation
    if target_faces > 0 and len(mesh.triangles) > target_faces:
        print(f"Step 6: Decimating mesh to target {target_faces:,} triangular faces...")
        mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=target_faces)
        print(f"   Final decimated mesh: {len(mesh.vertices):,} vertices, {len(mesh.triangles):,} faces.")

    # 8. Clean mesh topology
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()

    return mesh


def export_mesh(mesh: o3d.geometry.TriangleMesh, output_path: str):
    """
    Exports the reconstructed TriangleMesh to GLB, OBJ, or PLY.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ext = out_path.suffix.lower()

    print(f"Step 7: Exporting reconstructed surface to: {output_path}")

    if ext == ".glb":
        # Convert Open3D mesh to Trimesh for high-efficiency GLB packaging
        v = np.asarray(mesh.vertices)
        f = np.asarray(mesh.triangles)
        c = (np.asarray(mesh.vertex_colors) * 255.0).astype(np.uint8) if mesh.has_vertex_colors() else None

        # Build vertex colors array with alpha
        if c is not None and len(c) == len(v):
            rgba = np.column_stack([c, np.full((len(c), 1), 255, dtype=np.uint8)])
            tri_mesh = trimesh.Trimesh(vertices=v, faces=f, vertex_colors=rgba)
        else:
            tri_mesh = trimesh.Trimesh(vertices=v, faces=f)

        glb_bytes = tri_mesh.export(file_type="glb")
        with open(out_path, "wb") as f_out:
            f_out.write(glb_bytes)
    else:
        o3d.io.write_triangle_mesh(str(out_path), mesh)

    file_size_mb = out_path.stat().st_size / (1024 * 1024)
    print("=" * 70)
    print(f"SURFACE EXTRACTION COMPLETE!")
    print(f"Output File: {output_path} ({file_size_mb:.2f} MB)")
    print(f"Vertices: {len(mesh.vertices):,} | Triangles: {len(mesh.triangles):,}")
    print("=" * 70)


def main():
    args = parse_args()
    pts, cols = load_points_and_colors(args.input)
    mesh = reconstruct_surface_mesh(
        pts_np=pts,
        cols_np=cols,
        depth=args.depth,
        density_trim=args.density_trim,
        target_faces=args.target_faces,
        filter_outliers=args.filter_outliers,
        normals_radius=args.normals_radius,
    )
    export_mesh(mesh, args.output)


if __name__ == "__main__":
    main()
