#!/usr/bin/env python3
"""
Convert GLB files to STL format using trimesh.

Usage:
    python glb_to_stl.py input.glb -o output.stl
"""

import os
import trimesh

def convert_glb_to_stl(input_path, output_path):
    try:
        # Load the GLB file
        mesh = trimesh.load(input_path)

        # Export as STL
        mesh.export(output_path)
        print(f"Successfully converted {input_path} to {output_path}")

    except Exception as e:
        print(f"Error converting {input_path}: {str(e)}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert GLB to STL")
    parser.add_argument("input", help="Input GLB file")
    parser.add_argument("-o", "--output", help="Output STL file", required=True)
    args = parser.parse_args()

    convert_glb_to_stl(args.input, args.output)