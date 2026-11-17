"""Inspect, orient and scale triangulated figurines for CAD/printing workflows."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

SUPPORTED = {".glb", ".gltf", ".obj", ".stl", ".ply"}


def load_geometry(source: Path) -> trimesh.Trimesh:
    if not source.is_file():
        raise ValueError(f"Input file not found: {source}")
    if source.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported extension {source.suffix}; use {sorted(SUPPORTED)}")
    loaded = trimesh.load(str(source), force="scene", process=False)
    if isinstance(loaded, trimesh.Scene):
        parts = [
            item
            for item in loaded.dump(concatenate=False)
            if isinstance(item, trimesh.Trimesh) and len(item.faces) > 0
        ]
        if not parts:
            raise ValueError("No triangular geometry found in model")
        mesh = trimesh.util.concatenate(parts)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded.copy()
    else:
        raise ValueError("Input does not contain a supported triangle mesh")
    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("Model contains no triangles")
    if not np.all(np.isfinite(mesh.vertices)):
        raise ValueError("Model contains non-finite coordinates")
    mesh.remove_unreferenced_vertices()
    return mesh


def mesh_report(mesh: trimesh.Trimesh) -> dict:
    bounds = np.asarray(mesh.bounds, dtype=float)
    extents = np.asarray(mesh.extents, dtype=float)
    if not np.all(np.isfinite(bounds)):
        raise ValueError("Non-finite geometry bounds")
    warnings = []
    if not mesh.is_watertight:
        warnings.append("OPEN_MESH: the surface is not watertight; repair before printing")
    if not mesh.is_winding_consistent:
        warnings.append("INCONSISTENT_WINDING: inspect normals / face orientation")
    if np.any(extents <= 0):
        warnings.append("ZERO_EXTENT: model is flat along at least one axis")
    return {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "bounds": bounds.tolist(),
        "extents": extents.tolist(),
        "warnings": warnings,
        "print_ready": bool(mesh.is_watertight and mesh.is_winding_consistent and np.all(extents > 0)),
        "note": "Preflight only: thickness, stability, support structures and slicer checks still required.",
    }


def oriented_scaled_mesh(
    mesh: trimesh.Trimesh, height_mm: float, up_axis: str = "z"
) -> trimesh.Trimesh:
    if not math.isfinite(height_mm) or height_mm <= 0:
        raise ValueError("height_mm must be a finite positive number")
    if up_axis not in {"x", "y", "z"}:
        raise ValueError("up_axis must be x, y, or z")
    prepared = mesh.copy()
    if up_axis == "y":
        transform = trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0])
        prepared.apply_transform(transform)
    elif up_axis == "x":
        transform = trimesh.transformations.rotation_matrix(-math.pi / 2, [0, 1, 0])
        prepared.apply_transform(transform)

    current_height = float(prepared.extents[2])
    if not math.isfinite(current_height) or current_height <= 0:
        raise ValueError("Model has zero height along the selected up axis")
    prepared.apply_scale(height_mm / current_height)
    bounds = prepared.bounds
    prepared.apply_translation(
        [
            -float((bounds[0][0] + bounds[1][0]) / 2),
            -float((bounds[0][1] + bounds[1][1]) / 2),
            -float(bounds[0][2]),
        ]
    )
    return prepared


def write_json(target: Path, document: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def inspect(source: Path, report_file: Path | None = None) -> dict:
    mesh = load_geometry(source)
    report = {"source": str(source), "analysis": mesh_report(mesh)}
    if report_file is not None:
        write_json(report_file, report)
    return report


def prepare(
    source: Path,
    output_dir: Path,
    height_mm: float,
    up_axis: str = "z",
    allow_open: bool = False,
) -> dict:
    mesh = oriented_scaled_mesh(load_geometry(source), height_mm, up_axis)
    # Fix inverted normals only on a copy; no automatic hole-filling or topology mutation.
    trimesh.repair.fix_normals(mesh, multibody=True)
    analysis = mesh_report(mesh)
    report = {
        "source": str(source),
        "requested_height_mm": float(height_mm),
        "up_axis_in_source": up_axis,
        "coordinate_units_in_output": "mm (STL/OBJ do not encode physical units)",
        "analysis": analysis,
        "status": "READY_FOR_MANUAL_REVIEW" if analysis["print_ready"] else "NEEDS_MESH_REPAIR",
        "outputs": {},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{source.stem}.report.json"
    if not analysis["print_ready"] and not allow_open:
        write_json(report_path, report)
        raise ValueError(f"Mesh did not pass preflight; see {report_path}")
    stl = output_dir / f"{source.stem}.stl"
    obj = output_dir / f"{source.stem}.obj"
    mesh.export(str(stl), file_type="stl")
    mesh.export(str(obj), file_type="obj")
    report["outputs"] = {"stl": str(stl), "obj": str(obj)}
    if not analysis["print_ready"]:
        report["status"] = "EXPORTED_WITH_WARNINGS_NOT_PRINT_READY"
    write_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="Inspect mesh without changing files")
    inspect_parser.add_argument("source", type=Path)
    inspect_parser.add_argument("--report", type=Path)
    prep = subparsers.add_parser("prepare", help="Orient, scale and export STL + OBJ")
    prep.add_argument("source", type=Path)
    prep.add_argument("--height-mm", type=float, required=True)
    prep.add_argument("--up-axis", choices=["x", "y", "z"], default="z")
    prep.add_argument("--output-dir", type=Path, default=Path("exports"))
    prep.add_argument("--allow-open", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect(args.source, args.report)
        else:
            result = prepare(args.source, args.output_dir, args.height_mm, args.up_axis, args.allow_open)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
