"""V9 real shape reconstruction from PRIVATE 200mm character references.
Official Tencent Hunyuan3D-2mv: requires CUDA, model weights, 3 REAL alpha views,
and an independently reviewed result. Original photos NEVER enter public repo.
"""
from pathlib import Path
import argparse, hashlib, json, os, gc
import numpy as np
from PIL import Image

VIEWS = {
    "front":"MV_FRONT_RGBA_1024.png",
    "left":"MV_LEFT_RGBA_1024.png",
    "back":"MV_BACK_RGBA_1024.png",
    "right":"MV_RIGHT_RGBA_1024.png",
    "three_quarter":"MV_THREE_QUARTER_RGBA_1024.png"
}

def validate_refs(folder):
    manifest=json.loads((folder/"V9_INPUT_QA.json").read_text(encoding="utf8"))
    signatures={e["view"]:e["output_sha256"] for e in manifest["records"]}
    images={}
    for view,fn in VIEWS.items():
        path=folder/fn
        if not path.is_file() or view not in signatures:
            raise FileNotFoundError("Missing PRIVATE original view: "+view)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=signatures[view]:
            raise ValueError("Original reference checksum mismatch: "+view)
        image=Image.open(path).convert("RGBA")
        alpha=np.asarray(image)[:,:,3]
        if image.size!=(1024,1024) or not .06 <= np.mean(alpha>0) <= .65:
            raise ValueError("Unreviewed image dimensions/alpha: "+view)
        images[view]=image
    return images

def produce(folder,out,seed=20261120,model="mv"):
    images=validate_refs(folder)
    import torch
    if not torch.cuda.is_available():raise RuntimeError("No GPU; refusing fake reconstruction")
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
    if model=="mv":
        model_path="tencent/Hunyuan3D-2mv"; subfolder="hunyuan3d-dit-v2-mv"
        inp={key:images[key] for key in ("front","left","back")}
        steps=38
    elif model=="mini":
        model_path="tencent/Hunyuan3D-2mini";subfolder="hunyuan3d-dit-v2-mini"
        inp=images["front"];steps=50
    else:raise ValueError(model)
    pipeline=Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        model_path,subfolder=subfolder,variant="fp16")
    torch.cuda.reset_peak_memory_stats()
    try:
        result=pipeline(image=inp,num_inference_steps=steps,octree_resolution=256,
                        num_chunks=8000,generator=torch.manual_seed(seed),output_type="trimesh")
        if not result or len(result[0].faces)<3000:
            raise ValueError("AI did not generate a valid real 3D mesh")
        mesh=result[0]
        if not np.isfinite(mesh.vertices).all():raise ValueError("Non-finite mesh")
        out.mkdir(parents=True,exist_ok=True)
        f=out/("V9_REAL_HUNYUAN_"+model.upper()+"_UNAPPROVED.glb")
        mesh.export(f)
        status={
            "model":model_path,"variant":model,"seed":seed,
            "view_count_inference":3 if model=="mv" else 1,
            "other_original_images_for_independent_qa":True,
            "real_faces":len(mesh.faces),"watertight":bool(mesh.is_watertight),
            "model_checksum_sha256":hashlib.sha256(f.read_bytes()).hexdigest(),
            "height_target_mm":200,"raw_units_or_orientation_verified":False,
            "likeness_accepted":False,"colour_parts_physically_segmented":False,
            "wing_root_engineered_into_mesh":False,
            "print_ready_certified":False
        }
        (out/"V9_RAW_MESH_REPORT.json").write_text(
            json.dumps(status,ensure_ascii=False,indent=2),encoding="utf8")
        print("REAL_CANDIDATE_CREATED",len(mesh.faces),"GLB",f.name)
    except torch.cuda.OutOfMemoryError:
        raise RuntimeError("GPU VRAM exceeded; T4×2 is not pooled into 32 GB. "
                           "Need lower memory inference or a stronger single GPU.") from None
    finally:
        del pipeline
        gc.collect();torch.cuda.empty_cache()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--private-reference-dir",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("/kaggle/working/v9_raw"))
    p.add_argument("--seed",type=int,default=20261120)
    p.add_argument("--model",choices=("mv","mini"),default="mv")
    p.add_argument("--preflight-only",action="store_true")
    a=p.parse_args()
    validate_refs(a.private_reference_dir)
    print("FIVE_PRIVATE_ORIGINAL_VIEWS_SHA256_OK")
    if not a.preflight_only:produce(a.private_reference_dir,a.output,a.seed,a.model)
if __name__=="__main__":main()
