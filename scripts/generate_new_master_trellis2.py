"""Attempt genuinely new master mesh via official Microsoft TRELLIS.2 public ZeroGPU.

This is a candidate, never automatically replaces the previous model.
Source is the previously-approved front studio reference, *not* the
original game 3D mesh. Do not assert likeness without multi-angle inspection.
No paid provider API is used.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

import numpy as np
import requests
import trimesh
from PIL import Image
from gradio_client import Client, handle_file

MAX_DOWNLOAD = 120 * 1024 * 1024
ROOT = Path("/tmp/new-master-trellis2")
ROOT.mkdir(parents=True, exist_ok=True)
url = os.environ.get("SOURCE_URL")
if not url or not url.startswith("https://"):
    raise ValueError("Missing allowed HTTPS source reference")
resp = requests.get(url, timeout=55, allow_redirects=False)
resp.raise_for_status()
if not 1000 < len(resp.content) < 20_000_000:
    raise ValueError("Reference data too large/empty")
ref = ROOT / "source_front_reference.png"
ref.write_bytes(resp.content)
with Image.open(ref) as im:
    im.verify()
with Image.open(ref) as im:
    if min(im.size) < 256:
        raise ValueError("Reference resolution too low")
    print("SOURCE_DIMENSIONS", im.size, "SHA256", hashlib.sha256(resp.content).hexdigest(), flush=True)

client = Client("microsoft/TRELLIS.2", verbose=False)
print("START_TRELLIS2_PREPROCESS", flush=True)
prepped = client.predict(handle_file(str(ref)), api_name="/preprocess_image")
print("PREPPED_TYPE", type(prepped).__name__, flush=True)
# Official Gradio endpoint signature is recorded in preflight run 44503049290.
print("START_TRELLIS2_GPU_SHAPE_1024_NO_CREDITS", flush=True)
preview = client.predict(
    prepped, 20261119, "1024",
    7.5, 0.7, 12, 5.0,
    7.5, 0.5, 12, 3.0,
    1.0, 0.0, 12, 3.0,
    api_name="/image_to_3d",
)
print("GPU_SHAPE_COMPLETED", isinstance(preview, str), flush=True)
# The TRELLIS.2 space extracts this model from the same session.
out = client.predict(400000, 2048, api_name="/extract_glb")
path = out[-1] if isinstance(out, (tuple, list)) else out
if isinstance(path, dict):
    path = path.get("path")
if not isinstance(path, str) or not Path(path).is_file():
    raise RuntimeError("TRELLIS.2 did not return the actual downloadable GLB")
if not 1000 < Path(path).stat().st_size < MAX_DOWNLOAD:
    raise ValueError("Result GLB size invalid")
target = ROOT / "new_master_raw_trellis2.glb"
shutil.copy2(path, target)
scene = trimesh.load(target, force="scene")
mesh = scene.dump(concatenate=True)
if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) < 10000:
    raise RuntimeError("Trellis2 returned no usable 3D mesh")
if not np.isfinite(mesh.vertices).all():
    raise ValueError("Nonfinite 3D vertices")
# For later CAD reconstruction, preserve exact original GLB including materials.
raw = mesh.copy()
# Determine vertical dimension by longest axis, but label uncertainty.
axis = int(np.argmax(raw.extents))
if axis == 1:
    raw.apply_transform([[1,0,0,0], [0,0,1,0], [0,-1,0,0], [0,0,0,1]])
elif axis == 0:
    raw.apply_transform([[0,0,-1,0], [0,1,0,0], [1,0,0,0], [0,0,0,1]])
if not raw.extents[2] > 0:
    raise ValueError("Missing model height")
raw.apply_scale(150.0/float(raw.extents[2]))
raw.apply_translation([-float(raw.centroid[0]), -float(raw.centroid[1]), -float(raw.bounds[0,2])])
candidate = ROOT / "new_master_geometry_150mm_REVIEW_ONLY.stl"
raw.export(str(candidate))
metrics = {
    "model": "Microsoft TRELLIS.2 public ZeroGPU NEW candidate from studio front",
    "source_image": ref.name,
    "original_game_mesh": False,
    "faces": int(len(raw.faces)),
    "height_mm": float(raw.extents[2]),
    "watertight": bool(raw.is_watertight),
    "winding_consistent": bool(raw.is_winding_consistent),
    "connected_components": int(len(raw.split(only_watertight=False))),
    "print_ready_certified": False,
    "comparison_approved": False,
    "colour_splitting_status": "not started: pending geometry fidelity review",
    "limitations": ["Only the previously generated front studio reference is accessible to this cloud generator",
                    "Multi-view original game screenshots need direct transfer to generator for best correspondence",
                    "Topology, eye details, masked face, sleeve length and wings require manual comparison"],
}
(ROOT/"geometry_qa.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
print("NEW_MASTER_REAL_GEOMETRY",json.dumps(metrics),flush=True)
