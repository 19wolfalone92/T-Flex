"""Offline technical mesh audit. NOT a visual likeness or print-safety guarantee."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

from .cli import load_geometry, write_json


def mesh_quality_report(mesh: trimesh.Trimesh, *, max_component_faces: int = 500_000) -> dict:
    if not np.all(np.isfinite(mesh.vertices)):
        raise ValueError("Nonfinite vertex coordinates")
    extents = np.asarray(mesh.extents, dtype=float)
    bounds = np.asarray(mesh.bounds, dtype=float)
    if not np.all(np.isfinite(extents)) or not np.all(np.isfinite(bounds)):
        raise ValueError("Invalid bounding box")
    face_areas = np.asarray(mesh.area_faces, dtype=float)
    scale = max(float(np.max(extents)), 1e-9)
    tiny_area = max(scale * scale * 1e-13, 1e-20)
    degenerate_faces = int(np.count_nonzero(face_areas <= tiny_area))
    is_watertight = bool(mesh.is_watertight)
    winding = bool(mesh.is_winding_consistent)
    positive_volume = bool(is_watertight and abs(float(mesh.volume)) > 1e-12 * scale**3)
    messages = []
    if not is_watertight:
        messages.append("Mesh has open/nonmanifold boundaries")
    if not winding:
        messages.append("Some face orientations are inconsistent")
    if degenerate_faces:
        messages.append(f"{degenerate_faces} near-zero-area faces detected")
    if not positive_volume:
        messages.append("Solid volume not validated")
    components = None
    small_components = None
    if len(mesh.faces) <= max_component_faces:
        pieces = mesh.split(only_watertight=False)
        components = len(pieces)
        if components > 1:
            areas = [float(p.area) for p in pieces]
            whole = max(sum(areas), 1e-20)
            small_components = sum(1 for area in areas if area / whole < 0.001)
            messages.append(
                f"{components} separate shells; inspect intentional parts vs. floating fragments"
            )
    else:
        messages.append("Component analysis skipped for huge mesh; use Blender")
    # This is deliberately called a preliminary geometry gate, NOT print_ready.
    topology_gate = bool(
        is_watertight and winding and positive_volume and
        degenerate_faces == 0 and np.all(extents > 0) and
        (components is None or components == 1)
    )
    return {
        "schema_version": 1,
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.faces)),
        "bounds": bounds.tolist(),
        "size_in_source_units": extents.tolist(),
        "watertight": is_watertight,
        "consistent_winding": winding,
        "degenerate_faces": degenerate_faces,
        "volume_in_source_units_cubed": float(abs(mesh.volume)) if is_watertight else None,
        "separate_shells": components,
        "tiny_shells": small_components,
        "topology_gate": topology_gate,
        "needs_review": messages,
        "verified_print_ready": False,
        "not_verified": [
            "visual fidelity and reference likeness", "wall thickness", "self-intersections",
            "mechanical strength", "base stability", "overhangs and supports",
            "material and printer resolution",
        ],
    }


def audit(path: Path) -> dict:
    return {"file": str(path), **mesh_quality_report(load_geometry(path))}


def compare(paths: list[Path]) -> dict:
    if len(paths) < 2:
        raise ValueError("Comparison requires at least two meshes")
    reports = [audit(path) for path in paths]
    valid = [r for r in reports if r["topology_gate"]]
    return {
        "candidates": reports,
        "topology_pass_count": len(valid),
        "note": (
            "Passing topology gate is not a ranking of artistic quality. "
            "Choose visually after four-view renders and verify wall thickness in slicer."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("meshes", type=Path, nargs="+")
    parser.add_argument("--report", type=Path)
    options = parser.parse_args(argv)
    try:
        result = compare(options.meshes) if len(options.meshes) > 1 else audit(options.meshes[0])
        if options.report:
            write_json(options.report, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if len(options.meshes) > 1 or result["topology_gate"] else 3
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
