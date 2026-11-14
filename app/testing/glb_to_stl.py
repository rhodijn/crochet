#!/usr/bin/env python3
"""
Convert GLB files to STL format using trimesh.

Usage:
    python glb_to_stl.py input.glb -o output.stl
    python glb_to_stl.py input.glb -o output.stl --no-repair
"""

import numpy as np
import trimesh
from scipy import ndimage as ndi
from skimage import measure   # pip install scikit-image


def load_as_single_mesh(path):
    loaded = trimesh.load(path)

    if isinstance(loaded, trimesh.Scene):
        # dump() applies each node's transform and returns the list of meshes
        meshes = [g for g in loaded.dump() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("No triangle meshes found in the file")
        return trimesh.util.concatenate(meshes)

    return loaded


def close_by_voxels(mesh, resolution=100):
    """Return a watertight solid built from `mesh`, even if `mesh` is open.

    The mesh is voxelized, then every enclosed region is filled slice by slice
    along each axis (so an open bottom or roof cannot leak), and the filled
    volume is turned back into a triangle mesh. Detail is limited to
    1/`resolution` of the largest dimension.
    """
    pitch = float(mesh.extents.max()) / resolution
    vox = mesh.voxelized(pitch)
    pad = 4
    occ = np.pad(vox.matrix, pad)
    occ = ndi.binary_closing(occ, iterations=1)          # seal pin-holes

    solid = occ.copy()
    for ax in range(3):
        for i in range(occ.shape[ax]):
            sl = [slice(None)] * 3
            sl[ax] = i
            sl = tuple(sl)
            solid[sl] |= ndi.binary_fill_holes(occ[sl])
    solid = ndi.binary_fill_holes(solid)

    verts, faces, _, _ = measure.marching_cubes(solid.astype(np.uint8), 0.5)
    out = trimesh.Trimesh(verts - pad, faces)             # index coordinates
    out.apply_transform(vox.transform)                    # back to model space
    trimesh.repair.fix_normals(out)
    return out


def convert_glb_to_stl(input_path, output_path, repair=True):
    try:
        mesh = load_as_single_mesh(input_path)

        # Report the state before optional repair
        print(f"Before: watertight={mesh.is_watertight}, "
              f"faces={len(mesh.faces)}")

        if repair:
            # Repair
            mesh.merge_vertices()                       # weld duplicate vertices first
            mesh.update_faces(mesh.nondegenerate_faces())
            mesh.update_faces(mesh.unique_faces())
            mesh.remove_unreferenced_vertices()
            trimesh.repair.fix_inversion(mesh)          # flip if the mesh is inside-out
            trimesh.repair.fix_normals(mesh)            # consistent winding, outward normals
            trimesh.repair.fill_holes(mesh)             # fill simple holes

            # If simple repairs were not enough, rebuild a closed solid
            if not mesh.is_watertight:
                print("Still open after simple repairs: closing with voxels...")
                mesh = close_by_voxels(mesh)
        else:
            print("Skipping repair step (--no-repair).")

        print(f"After:  watertight={mesh.is_watertight}, "
              f"faces={len(mesh.faces)}")
        if not mesh.is_watertight:
            print("Warning: mesh is still not watertight "
                  "(try a higher resolution in close_by_voxels).")

        mesh.export(output_path)
        print(f"Successfully converted {input_path} to {output_path}")

    except Exception as e:
        print(f"Error converting {input_path}: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert GLB to STL")
    parser.add_argument("input", help="Input GLB file")
    parser.add_argument("-o", "--output", help="Output STL file", required=True)
    parser.add_argument(
        "--repair",
        dest="repair",
        action="store_true",
        help="Run mesh repair before export (default)",
    )
    parser.add_argument(
        "--no-repair",
        dest="repair",
        action="store_false",
        help="Skip mesh repair and export geometry as loaded",
    )
    parser.set_defaults(repair=True)
    args = parser.parse_args()

    convert_glb_to_stl(args.input, args.output, repair=args.repair)