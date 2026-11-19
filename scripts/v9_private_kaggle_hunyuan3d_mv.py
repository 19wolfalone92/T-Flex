"""V9 real shape reconstruction from PRIVATE 200mm character references.
Official Tencent Hunyuan3D-2mv: requires CUDA, model weights, 3 REAL alpha views,
and an independently reviewed result. Original photos NEVER enter public repo.
"""
from pathlib import Path
import argparse, hashlib, json, os, gc, time
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
    if model in ("mv","mv_turbo"):
        model_path="tencent/Hunyuan3D-2mv"; subfolder=("hunyuan3d-dit-v2-mv-turbo" if model=="mv_turbo" else "hunyuan3d-dit-v2-mv")
        inp={key:images[key] for key in ("front","left","back")}
        steps=5 if model=="mv_turbo" else 38
    elif model=="mini":
        model_path="tencent/Hunyuan3D-2mini";subfolder="hunyuan3d-dit-v2-mini"
        inp=images["front"];steps=50
    else:raise ValueError(model)
    pipeline=Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        model_path,subfolder=subfolder,variant="fp16")
    # CPU-offload keeps the full multiview model from residing on a single 16 GiB T4.
    # Two Tesla T4 cards do NOT share one 32 GiB memory pool.
    if hasattr(pipeline,"enable_model_cpu_offload"):
        pipeline.enable_model_cpu_offload()
    else:
        raise RuntimeError("Required upstream T4 CPU-offload interface unavailable")
    if model=="mv_turbo":
        if not hasattr(pipeline,"enable_flashvdm"):
            raise RuntimeError("Turbo model requires FlashVDM; no fake speed fallback")
        pipeline.enable_flashvdm()
    torch.cuda.reset_peak_memory_stats()
    t0=time.monotonic()
    try:
        result=pipeline(image=inp,num_inference_steps=steps,octree_resolution=256,
                        num_chunks=8000,generator=torch.manual_seed(seed),output_type="trimesh")
        if not result or len(result[0].faces)<3000:
            raise ValueError("AI did not generate a valid real 3D mesh")
        mesh=result[0]
        if not np.isfinite(mesh.vertices).all():raise ValueError("Non-finite mesh")
        if len(mesh.vertices)<1000 or mesh.is_empty:raise ValueError("3D shape empty")
        runtime=round(time.monotonic()-t0,2)
        peak=round(torch.cuda.max_memory_allocated()/2**30,2)
        out.mkdir(parents=True,exist_ok=True)
        f=out/("V9_REAL_HUNYUAN_"+model.upper()+"_UNAPPROVED.glb")
        mesh.export(f)
        # Engineering-scale preview only: principal axis alignment is provisional.
        # Store BOTH untouched original mesh and 200 mm normalized illustration.
        upright=mesh.copy()
        longest=int(np.argmax(upright.extents))
        if longest==0:
            upright.apply_transform([[0,0,-1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]])
        elif longest==1:
            upright.apply_transform([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]])
        if upright.extents[2] <= 0:
            raise RuntimeError("Cannot normalize mesh to 200 mm")
        upright.apply_scale(200.0/float(upright.extents[2]))
        upright.apply_translation([-float(upright.bounds[0,0]+upright.bounds[1,0])/2,
                                   -float(upright.bounds[0,1]+upright.bounds[1,1])/2,
                                   -float(upright.bounds[0,2])])
        if not 199.999 <= upright.extents[2] <= 200.001:
            raise AssertionError("Physical 200 mm provisional scale lost")
        preview=out/("V9_200MM_"+model.upper()+"_SCALE_AND_ORIENTATION_PROVISIONAL.glb")
        upright.export(preview)
        status={
            "model":model_path,"variant":model,"seed":seed,\n            "runtime_seconds":runtime,"peak_cuda_allocated_gib":peak,\n            "inference_uses_model_cpu_offload":True,\n            "200mm_preview_sha256":hashlib.sha256(preview.read_bytes()).hexdigest(),\n            "200mm_preview_height_mm":round(float(upright.extents[2]),5),\n            "200mm_preview_up_direction_verified_against_original":False,
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
    p.add_argument("--model",choices=("mv","mv_turbo","mini"),default="mv")
    p.add_argument("--preflight-only",action="store_true")
    a=p.parse_args()
    validate_refs(a.private_reference_dir)
    print("FIVE_PRIVATE_ORIGINAL_VIEWS_SHA256_OK")
    if not a.preflight_only:produce(a.private_reference_dir,a.output,a.seed,a.model)
if __name__=="__main__":main()
