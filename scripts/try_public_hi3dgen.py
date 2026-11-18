"""Independent non-billable 3D reproduction from public reference art.

The original paid Meshy geometry is not accessed or downloaded.
"""
import os
import json
import shutil
from pathlib import Path

import numpy as np
import requests
import trimesh
from PIL import Image
from gradio_client import Client, handle_file

out = Path("/tmp/figurine-replica")
out.mkdir(exist_ok=True)
response = requests.get(os.environ["SOURCE_URL"], timeout=40)
response.raise_for_status()
if not 0 < len(response.content) <= 20_000_000:
    raise ValueError("Reference exceeds image size budget")
source = out / "source_reference.png"
source.write_bytes(response.content)
with Image.open(source) as im:
    im.verify()

print("Preparing image for FREE Hi3DGen API", flush=True)
client = Client("Stable-X/Hi3DGen", verbose=False)
processed = client.predict(handle_file(str(source)), api_name="/preprocess_image")
path = processed if isinstance(processed, str) else processed.get("path") if isinstance(processed, dict) else None
if not path or not Path(path).is_file():
    raise RuntimeError("Hi3DGen did not deliver processed image")
print("Starting FREE geometry inference; NO billing API", flush=True)
result = client.predict(
    handle_file(str(path)), 0, 3.0, 50, 3.0, 6, api_name="/generate_3d"
)
print("Returned types:", [type(x).__name__ for x in result], flush=True)
file_value = result[-1]
if isinstance(file_value, dict):
    file_value = file_value.get("path")
if not isinstance(file_value, str) or not Path(file_value).is_file():
    raise RuntimeError("Provider did not deliver a downloadable mesh")
generated = out / ("original" + Path(file_value).suffix.lower())
shutil.copy2(file_value, generated)
scene = trimesh.load(str(generated), force="scene")
mesh = scene.dump(concatenate=True) if isinstance(scene, trimesh.Scene) else scene
if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) < 1000:
    raise RuntimeError("Generator output lacks usable triangle geometry")
raw = mesh.copy()
dims = np.asarray(raw.extents)
axis = int(np.argmax(dims))
if axis == 1:
    raw.apply_transform([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
if axis == 0:
    raw.apply_transform([[0,0,-1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]])
raw.apply_scale(150 / float(raw.extents[2]))
raw.apply_translation([-raw.centroid[0], -raw.centroid[1], -raw.bounds[0][2]])
stl = out / "figurine_150mm_NEEDS_SLICER_REVIEW.stl"
raw.export(str(stl))
report = {
    "provenance": "new open-source AI reconstruction, NOT exact Meshy 7.1 mesh",
    "generator": "Stable-X/Hi3DGen on public HuggingFace Space",
    "triangles": len(raw.faces),
    "watertight": bool(raw.is_watertight),
    "normals_consistent": bool(raw.is_winding_consistent),
    "bounds_mm": raw.bounds.tolist(),
    "height_mm": float(raw.extents[2]),
    "print_ready_certified": False,
    "review_required": [
        "Manual likeness comparison from 4 sides",
        "Wing thickness, facial detail and minimum wall thickness",
        "Slicer support and actual nozzle/filament/bed-fit verification",
    ],
}
(out/"qa_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("REPLICA_READY_FOR_REVIEW", json.dumps(report), flush=True)
