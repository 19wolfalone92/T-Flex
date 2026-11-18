"""Run Blender's verified 2-part FDM assembly script; require complete STL QA evidence."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import trimesh


def split(
    source: Path, dest: Path, *,
    blender: str = "blender", ratio: float = 0.5,
    clearance: float = 0.20, pin_mm: float = 3.0, depth_mm: float = 5.5,
    script: Path | None = None, timeout: int = 900,
) -> dict:
    if not source.is_file() or source.suffix.lower() != ".stl":
        raise ValueError("A prepared STL in millimeters is required")
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("Output directory already has files")
    if script is None:
        script = Path(__file__).resolve().parents[2] / "scripts" / "blender_split_assembly.py"
    if not script.is_file():
        raise ValueError("Blender splitter script unavailable")
    executable = shutil.which(blender) or (blender if Path(blender).is_file() else None)
    if not executable:
        raise ValueError("Blender executable not installed or not found")
    cmd = [
        str(executable), "-b", "--python", str(script.resolve()),
        "--", "--input", str(source.resolve()), "--output-dir", str(dest.resolve()),
        "--cut-ratio", str(ratio), "--pin-diameter-mm", str(pin_mm),
        "--radial-clearance-mm", str(clearance), "--hole-depth-mm", str(depth_mm),
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Blender failed or timed out; examine output folder") from exc
    manifest = dest / "assembly.json"
    if result.returncode != 0 or not manifest.is_file():
        # Never treat Blender 'returncode=0' alone as sufficient.
        raise RuntimeError(
            f"Blender split failed (exit {result.returncode}); no validated assembly produced"
        )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("print_ready_certified") is not False:
        raise RuntimeError("Invalid split manifest: unverified model must not claim print ready")
    expected = [
        dest / "assembly" / (p + ".stl") for p in ("lower", "upper", "pin_1", "pin_2")
    ] + [
        dest / "print" / (p + ".stl") for p in
        ("lower", "upper", "pin_1", "pin_2", "test_socket")
    ]
    for output in expected:
        if not output.is_file():
            raise RuntimeError(f"Split output missing {output.name}")
        mesh = trimesh.load(str(output), force="mesh")
        if not (mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0):
            raise RuntimeError(f"Invalid split mesh {output.name}")
        if output.parent.name == "print" and abs(float(mesh.bounds[0][2])) > 0.05:
            raise RuntimeError(f"STL not placed on print bed: {output.name}")
    payload["python_post_export_qa"] = {
        "closed_and_positive_volume_parts": len(expected),
        "all_parts_passed": True,
        "printer_test_passed": False,
    }
    # Keep Blender evidence and add an independent Python verifier, never overwrite blindly.
    verified = dest / "python_audit.json"
    if verified.exists():
        raise RuntimeError("Refusing to overwrite existing Python audit")
    verified.write_text(json.dumps(payload["python_post_export_qa"], indent=2), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--blender", default="blender")
    p.add_argument("--cut-ratio", type=float, default=0.50)
    p.add_argument("--pin-diameter-mm", type=float, default=3.0)
    p.add_argument("--clearance-mm", type=float, default=0.20)
    p.add_argument("--hole-depth-mm", type=float, default=5.5)
    a = p.parse_args(argv)
    try:
        result = split(
            a.source, a.output_dir, blender=a.blender, ratio=a.cut_ratio,
            clearance=a.clearance_mm, pin_mm=a.pin_diameter_mm, depth_mm=a.hole_depth_mm,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
