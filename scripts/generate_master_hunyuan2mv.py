"""Hunyuan3D-2mv independent candidate from a reference front (free HF demo).

This *does not* claim true 4-view reconstruction: only the single available
reference front is submitted. The model is never considered print-ready
until multi-angle likeness, sleeves, wings, and supports are reviewed.
"""
from pathlib import Path
from PIL import Image
from gradio_client import Client, handle_file
import hashlib, json, os, shutil
import requests, numpy as np, trimesh

root=Path("/tmp/new-master-hunyuan");root.mkdir(exist_ok=True)
url=os.environ["SOURCE_URL"]
assert url.startswith("https://")
r=requests.get(url,timeout=60,allow_redirects=False);r.raise_for_status()
assert 1000 < len(r.content) < 20_000_000
img=root/"source_front_reference.png";img.write_bytes(r.content)
with Image.open(img) as a:a.verify()
print("START_FREE_HUNYUAN_2MV_MASTER",flush=True)
api=Client("tencent/Hunyuan3D-2mv",verbose=False)
# API signature verified from official HF Space by read-only preflight.
result=api.predict(
    None, None, handle_file(str(img)), None, None, None,
    8, 5.0, 271828, 384, True, 8000, False,
    api_name="/shape_generation",
)
if not isinstance(result,(tuple,list)) or len(result)<1:
    raise RuntimeError("Hunyuan returned no 3D object")
path=result[0]
if isinstance(path,dict): path=path.get("path")
if not isinstance(path,str) or not Path(path).is_file():
    raise RuntimeError("Hunyuan did not provide an actual 3D model file")
original=Path(path)
raw=root/("new_master_hunyuan_raw"+original.suffix.lower())
shutil.copy2(original,raw)
scene=trimesh.load(raw,force="scene")
m=scene.dump(concatenate=True)
if not isinstance(m,trimesh.Trimesh) or len(m.faces)<10000:
    raise RuntimeError("Model too small/no actual triangle surface")
if not np.isfinite(m.vertices).all():
    raise ValueError("Nonfinite vertices")
candidate=m.copy()
axis=int(np.argmax(candidate.extents))
if axis==1:
    candidate.apply_transform([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
elif axis==0:
    candidate.apply_transform([[0,0,-1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]])
candidate.apply_scale(150/float(candidate.extents[2]))
candidate.apply_translation([-candidate.centroid[0],-candidate.centroid[1],-candidate.bounds[0,2]])
stl=root/"new_master_hunyuan_150mm_REVIEW_ONLY.stl"
candidate.export(stl)
stats={
    "engine":"Tencent Hunyuan3D-2mv official public Space",
    "input":"previously generated studio front reference ONLY",
    "original_game_views_uploaded":False,
    "faces":len(candidate.faces),"height_mm":float(candidate.extents[2]),
    "watertight":bool(candidate.is_watertight),"winding":bool(candidate.is_winding_consistent),
    "components":len(candidate.split(only_watertight=False)),
    "model_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),
    "likeness_accepted":False,"print_ready_certified":False,
    "manual_inspection":["mask vs eyes, hair volume, full sleeves, back feathers, boots"],
}
(root/"geometry_qa.json").write_text(json.dumps(stats,indent=2),encoding="utf-8")
print("NEW_REAL_HUNYUAN_MASTER",json.dumps(stats),flush=True)
