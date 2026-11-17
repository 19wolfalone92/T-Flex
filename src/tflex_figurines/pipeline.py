"""One-command, safe, local path from GLB/STL to T-FLEX mesh exports + QA.

NO generation API calls, no paid credits, no automatic Blender geometry editing.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from .cli import prepare, write_json
from .quality import audit


def prepare_figurine(
    source: Path,
    output: Path,
    height_mm: float,
    axis: str = "y",
    *,
    blender_executable: Path | None = None,
    blender_script: Path | None = None,
) -> dict:
    if not source.is_file():
        raise ValueError("No source 3D model supplied")
    if not math.isfinite(height_mm) or height_mm <= 0:
        raise ValueError("Height must be positive and finite")
    output.mkdir(parents=True, exist_ok=True)
    evidence = output / "evidence"
    evidence.mkdir(exist_ok=True)
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        raise ValueError("Output manifest already exists; use a new folder")
    before = audit(source)
    write_json(evidence / "source_mesh_audit.json", before)
    manifest = {
        "source": str(source),
        "height_mm": height_mm,
        "up_axis": axis,
        "source_topology_pass": before["topology_gate"],
        "status": "BLOCKED_PENDING_MESH_REPAIR",
        "provider": "imported_model",
        "technical_review_only": True,
        "verified_print_ready": False,
        "review_required": [
            "Front/side/back visual comparison with real reference photographs",
            "Slicer wall thickness and printer/material checks",
            "Undercuts/overhangs, supports, base stability and real T-FLEX import",
        ],
    }
    if not before["topology_gate"]:
        write_json(manifest_path, manifest)
        return manifest
    exports = output / "exports"
    result = prepare(source, exports, height_mm=height_mm, up_axis=axis)
    after = audit(Path(result["outputs"]["stl"]))
    write_json(evidence / "prepared_mesh_audit.json", after)
    if not after["topology_gate"]:
        manifest["status"] = "BLOCKED_AFTER_EXPORT"
        write_json(manifest_path, manifest)
        return manifest
    actual_height = after["size_in_source_units"][2]
    if abs(actual_height - height_mm) > max(0.05, height_mm * 0.0005):
        manifest["status"] = "BLOCKED_SCALE_MISMATCH"
        write_json(manifest_path, manifest)
        return manifest
    manifest["exports"] = result["outputs"]
    manifest["source_mesh_audit"] = str(evidence / "source_mesh_audit.json")
    manifest["prepared_mesh_audit"] = str(evidence / "prepared_mesh_audit.json")
    manifest["status"] = "GEOMETRY_REVIEW_PASSED_MANUAL_PRINT_QA_PENDING"

    if blender_executable is not None:
        script = blender_script or Path(__file__).resolve().parents[2] / "scripts" / "blender_review.py"
        if not script.is_file():
            raise ValueError("Blender review script missing; provide --blender-script")
        previews = output / "turntable"
        previews.mkdir(exist_ok=True)
        cmd = [
            str(blender_executable), "--background", "--python", str(script.resolve()),
            "--", "--input", str(Path(result["outputs"]["obj"]).resolve()),
            "--output-dir", str(previews.resolve()),
        ]
        # No shell: injection-safe; render is local, not a paid remote service.
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=360)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            manifest["status"] = "BLENDER_REVIEW_FAILED"
            manifest["blender_error_type"] = type(exc).__name__
        else:
            manifest["renders"] = [str(previews / f"{label}.png") for label in ("front", "left", "back", "right")]
            manifest["blender_report"] = str(previews / "blender_review.json")
    write_json(manifest_path, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--height-mm", type=float, required=True)
    p.add_argument("--up-axis", choices=("x", "y", "z"), default="y")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--blender", type=Path, help="Optional local Blender executable for four-view renders")
    p.add_argument("--blender-script", type=Path)
    args = p.parse_args(argv)
    try:
        result = prepare_figurine(
            args.input, args.output_dir, args.height_mm, args.up_axis,
            blender_executable=args.blender, blender_script=args.blender_script,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "GEOMETRY_REVIEW_PASSED_MANUAL_PRINT_QA_PENDING" else 3
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
