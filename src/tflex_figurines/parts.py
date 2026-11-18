"""Turn Hi3D semantic split GLB into independently printable STL components.

Preserves common coordinates in assembly/*.stl and translates each standalone
print/*.stl down to Z=0. Never implies connectors fit or part is printable.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

from .cli import write_json


def extract(source: Path, output: Path, *, height_mm: float) -> dict:
    if not source.is_file() or source.suffix.lower() not in (".glb", ".gltf"):
        raise ValueError("Hi3D semantic split requires an existing GLB/GLTF scene")
    if not math.isfinite(height_mm) or not 20 <= height_mm <= 1000:
        raise ValueError("Requested assembly height must be 20..1000 mm")
    if output.exists() and any(output.iterdir()):
        raise ValueError("New empty output directory required; existing results preserved")
    scene = trimesh.load(str(source), force="scene", process=False)
    if not isinstance(scene, trimesh.Scene):
        raise ValueError("Model has no scene graph")
    pieces = []
    for node in sorted(scene.graph.nodes_geometry):
        transform, geom_name = scene.graph[node]
        original = scene.geometry.get(geom_name)
        if not isinstance(original, trimesh.Trimesh) or len(original.faces) == 0:
            continue
        mesh = original.copy()
        mesh.apply_transform(transform)
        mesh.remove_unreferenced_vertices()
        mesh.merge_vertices()
        # One scene node may contain multiple disconnected solid bodies.
        # Separate only closed connected shells, never guessing semantics.
        shells = list(mesh.split(only_watertight=False))
        for n, shell in enumerate(shells):
            if len(shell.faces) == 0:
                continue
            if not (
                shell.is_watertight and shell.is_winding_consistent
                and shell.volume > 0
            ):
                raise ValueError(f"Hi3D split shell {node}/{n} not a closed positive solid")
            pieces.append((f"{node}/{n}", shell))
    if not 2 <= len(pieces) <= 64:
        raise ValueError(
            f"Expected 2..64 independently closed pieces, found {len(pieces)}; "
            "check vendor GLB and manual separation in Blender."
        )

    all_bounds = np.array([mesh.bounds for _, mesh in pieces], dtype=float)
    mins = all_bounds[:, 0, :].min(axis=0)
    maxs = all_bounds[:, 1, :].max(axis=0)
    extent = maxs-mins
    if not np.isfinite(extent).all() or extent[2] <= 1e-9:
        raise ValueError("Invalid assembly bounding box")
    factor = height_mm / float(extent[2])
    centre_x = float((mins[0]+maxs[0])/2)
    centre_y = float((mins[1]+maxs[1])/2)
    output.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": 1, "input": str(source), "height_mm": height_mm,
        "provider": "Hi3D semantic split GLB (not independently validated live)",
        "target_cad": "T-FLEX CAD 18 mesh import",
        "print_ready_certified": False,
        "scale_from_input_units": factor,
        "parts": [],
        "warnings": [
            "Confirm true anatomical separation and no duplicate/superimposed geometry",
            "Confirm vendor joints fit with test coupons on actual single-colour printer",
            "Review wall thickness, print orientation and supports in slicer",
            "Print each part separately and allow filament changes between batches",
            "Assembly STLs are polygonal representations, not CAD parametric solids",
        ],
    }
    for i, (node, mesh) in enumerate(pieces, start=1):
        assembled = mesh.copy()
        assembled.apply_translation([-centre_x, -centre_y, -float(mins[2])])
        assembled.apply_scale(factor)
        if not (
            assembled.is_watertight and assembled.is_winding_consistent
            and assembled.volume > 0
        ):
            raise ValueError(f"Part became invalid after coordinate normalization: {node}")
        printed = assembled.copy()
        printed.apply_translation([0, 0, -float(printed.bounds[0][2])])
        label = f"part_{i:02d}.stl"
        a_path, p_path = output/"assembly"/label, output/"print"/label
        a_path.parent.mkdir(parents=True, exist_ok=True)
        p_path.parent.mkdir(parents=True, exist_ok=True)
        assembled.export(str(a_path))
        printed.export(str(p_path))
        manifest["parts"].append({
            "number": i, "source_node": node, "assembly": str(a_path.relative_to(output)),
            "print": str(p_path.relative_to(output)),
            "faces": len(assembled.faces),
            "volume_mm3": round(float(assembled.volume), 3),
            "assembly_bounds_mm": assembled.bounds.round(3).tolist(),
            "print_bounds_mm": printed.bounds.round(3).tolist(),
        })
    with (output/"parts.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["part_number", "quantity", "print_stl", "assembly_stl", "suggested_colour"])
        for p in manifest["parts"]:
            writer.writerow([p["number"], 1, p["print"], p["assembly"], "choose one filament / batch"])
    write_json(output/"assembly.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--height-mm", type=float, required=True)
    options = p.parse_args(argv)
    try:
        result = extract(options.source, options.output_dir, height_mm=options.height_mm)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
