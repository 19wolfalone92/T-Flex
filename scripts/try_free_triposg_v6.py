"""One zero-cost candidate from the public TripoSG Space (not accepted V6 master).

Uses only the already public approved front studio image. Original 18 game
screenshots remain private and are never sent from GitHub. This is a controlled
free-GPU experiment; failures must never trigger fallback to V5 meshes.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path

import numpy as np
import requests
import trimesh
from PIL import Image
from gradio_client import Client, handle_file
import inspect

OUTPUT=Path("/tmp/triposg-v6-test")
OUTPUT.mkdir(parents=True,exist_ok=True)
url=os.environ["SOURCE_URL"]
if not url.startswith("https://assets.meshy.ai/"):
    raise ValueError("Only prior public studio reference URL is permitted")
response=requests.get(url,timeout=50,allow_redirects=False)
response.raise_for_status()
if not 1000<len(response.content)<12_000_000:
    raise ValueError("Unusable source image")
reference=OUTPUT/"source_public_studio_front.png"
reference.write_bytes(response.content)
with Image.open(reference) as image:
    image.verify()
token_param = "token" if "token" in inspect.signature(Client.__init__).parameters else "hf_token"
api=Client("VAST-AI/TripoSG",verbose=False,**{token_param:os.environ.get("HF_TOKEN") or None})
print("FREE_TRIPOSG_CONNECT_SUCCESS_NO_PAID_CREDITS",flush=True)
source=api.predict(handle_file(str(reference)),api_name="/run_segmentation")
print("SOURCE_SEGMENTATION_COMPLETE",flush=True)
try:
    model_file=api.predict(source,20261119,40,6.8,False,400000,
                           api_name="/image_to_3d")
except Exception as exc:
    raise RuntimeError("Public TripoSG GPU unavailable; V6 master remains BLOCKED") from exc
if isinstance(model_file,dict):
    model_file=model_file.get("path")
if not isinstance(model_file,str) or not Path(model_file).is_file():
    raise RuntimeError("TripoSG produced no locally downloadable GLB")
raw=OUTPUT/"NEW_CANDIDATE_TRIPOSG_RAW.glb"
shutil.copy2(model_file,raw)
mesh=trimesh.load(str(raw),force="scene").dump(concatenate=True)
if not isinstance(mesh,trimesh.Trimesh) or len(mesh.faces)<10000:
    raise RuntimeError("Invalid new 3D master from TripoSG")
if not np.isfinite(mesh.vertices).all():
    raise RuntimeError("Nonfinite geometry")
candidate=mesh.copy()
axis=int(np.argmax(candidate.extents))
if axis==1:
    candidate.apply_transform([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
elif axis==0:
    candidate.apply_transform([[0,0,-1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]])
candidate.apply_scale(150.0/float(candidate.extents[2]))
candidate.apply_translation([-float(candidate.centroid[0]),-float(candidate.centroid[1]),-float(candidate.bounds[0,2])])
candidate.export(str(OUTPUT/"NEW_MASTER_TRIPOSG_150mm_REVIEW_ONLY.stl"))
qa={"source":"public old studio front reference, NOT original game multi-view",
    "independent_new_sculpt":True,"paid_service_credits_used":0,
    "model":"TripoSG public HF demo",
    "raw_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),
    "triangles":len(candidate.faces),"watertight":bool(candidate.is_watertight),
    "components":len(candidate.split(only_watertight=False)),
    "likeness_review_passed":False,"print_ready_certified":False,
    "colour_split_allowed":False}
(OUTPUT/"EXPERIMENT_NOT_MASTER_QA.json").write_text(json.dumps(qa,indent=2),encoding="utf8")
print("TRIPOSG_NEW_GEOMETRY_CANDIDATE_CREATED",json.dumps(qa),flush=True)
