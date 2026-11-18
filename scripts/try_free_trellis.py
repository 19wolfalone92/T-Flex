"""Free TRELLIS generative 3D alternative, no paid API or Meshy exports."""
import os, shutil, json
from pathlib import Path
import requests, trimesh
from gradio_client import Client, handle_file
from PIL import Image
out=Path("/tmp/trellis-figurine");out.mkdir(parents=True,exist_ok=True)
res=requests.get(os.environ["SOURCE_URL"],timeout=40);res.raise_for_status()
src=out/"reference.png";src.write_bytes(res.content)
with Image.open(src) as img:img.verify()
print("FREE_TRELLIS_GENERATION_START",flush=True)
client=Client("trellis-community/TRELLIS",verbose=False)
output=client.predict(handle_file(str(src)),[],0,7.5,12,3.0,12,"stochastic",0.95,1024,api_name="/generate_and_extract_glb")
print("OUTPUT_TYPES",[type(o).__name__ for o in output],flush=True)
target=output[-1]
if isinstance(target,dict):target=target.get("path")
if not isinstance(target,str) or not Path(target).is_file():raise RuntimeError("GLB not returned")
source=out/"reconstruction_trellis.glb";shutil.copy2(target,source)
scene=trimesh.load(str(source),force="scene")
mesh=scene.dump(concatenate=True)
if len(mesh.faces)<1000:raise RuntimeError("Empty generated mesh")
m=mesh.copy()
axis=int(m.extents.argmax())
if axis==1:m.apply_transform([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]])
if axis==0:m.apply_transform([[0,0,-1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]])
m.apply_scale(150/float(m.extents[2]));m.apply_translation([-m.centroid[0],-m.centroid[1],-m.bounds[0,2]])
initial=bool(m.is_watertight)
trimesh.repair.fill_holes(m)
file=out/"figurine_trellis_150mm_review.stl";m.export(str(file))
report={"model":"Independent TRELLIS reproduction, not Meshy data","faces":len(m.faces),"initial_watertight":initial,"after_fill_watertight":bool(m.is_watertight),"height_mm":float(m.extents[2]),"print_ready_certified":False}
(out/"qa.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print("TRELLIS_COPY_SUCCESS",json.dumps(report),flush=True)
