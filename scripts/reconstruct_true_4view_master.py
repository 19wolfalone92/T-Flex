"""Hunyuan3D-2mv genuine multi-view master reconstruction (NOT V5 processing).

Requires the original four reference screenshots in a LOCAL private directory.
This is an opt-in external ZeroGPU inference request; no money is billed.
If GPU quota is exhausted, execution fails without creating a bad stand-in mesh.

Usage:
    python scripts/reconstruct_true_4view_master.py \\
      --front refs/08_front.jpg --back refs/06_back.jpg \\
      --left refs/05_left_profile.jpg --right refs/03_right_profile.jpg \\
      --output-dir builds/master_candidate --yes-generate

The four original screenshots contain perspective, grass, partial boot occlusion,
and inconsistent views; never claim photogrammetric certainty or printability.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import shutil
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


def validate_input(p: Path) -> dict:
    if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        raise ValueError("Expected a local original JPEG/PNG/WebP reference: " + str(p))
    if not 0 < p.stat().st_size <= 20_000_000:
        raise ValueError("Source image size invalid")
    with Image.open(p) as im:
        im.verify()
    with Image.open(p) as im:
        w,h=im.size
    if min(w,h)<200:
        raise ValueError("Reference view too small")
    return {"filename":p.name,"pixels":[w,h]}


def main(argv: list[str]|None=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("front","back","left","right"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--yes-generate",action="store_true",
                        help="Explicitly invoke public third-party HF GPU service")
    args=parser.parse_args(argv)
    views={k:getattr(args,k) for k in ("front","back","left","right")}
    evidence={k:validate_input(v) for k,v in views.items()}
    report={"source":"Four ORIGINAL multi-angle character screenshots",
            "input":evidence,
            "limitations":["screenshots are perspective and not exact orthographic",
                           "parts of boots obscured by grass",
                           "must visually compare to all eight original views",
                           "no STEP/STL splitting before likeness review"],
            "print_ready_certified":False,
            "likeness_approved":False,
            "mode":"readonly_preflight" if not args.yes_generate else "public_hunyuan_gpu"}
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError("Output directory not empty")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/"reference_manifest.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False),encoding="utf8")
    if not args.yes_generate:
        print("PREFLIGHT_OK: 4 actual original views checked; ZERO external AI calls")
        return 0
    from gradio_client import Client,handle_file
    token=os.environ.get("HF_TOKEN")
    client=Client("tencent/Hunyuan3D-2mv",hf_token=token,verbose=False)
    # Official /shape_generation signature pinned to read-only schema check.
    # NO fallback to an existing V5 mesh when this fails.
    try:
        answer=client.predict(
            None,None,
            handle_file(str(views["front"])),
            handle_file(str(views["back"])),
            handle_file(str(views["left"])),
            handle_file(str(views["right"])),
            8,5.0,20261119,384,True,8000,False,
            api_name="/shape_generation",
        )
    except Exception as exc:
        # Never include provider exception text: it could disclose signed URLs.
        raise RuntimeError("Public GPU generation failed (quota, authentication or provider error)") from exc
    path=answer[0] if isinstance(answer,(tuple,list)) and answer else None
    if isinstance(path,dict): path=path.get("path")
    if not isinstance(path,str) or not Path(path).is_file():
        raise RuntimeError("Provider returned no downloadable 3D master")
    source=Path(path)
    if source.suffix.lower() not in (".glb",".obj",".stl",".ply"):
        raise ValueError("Unexpected 3D export format")
    raw=args.output_dir/("MASTER_FROM_FOUR_GAME_VIEWS_RAW"+source.suffix.lower())
    shutil.copy2(source,raw)
    scene=trimesh.load(raw,force="scene")
    mesh=scene.dump(concatenate=True)
    if not isinstance(mesh,trimesh.Trimesh) or len(mesh.faces)<20000:
        raise ValueError("3D output insufficient for a collectible figure")
    if not np.isfinite(mesh.vertices).all():
        raise ValueError("Invalid 3D mesh coordinates")
    canonical=mesh.copy()
    vertical=int(np.argmax(canonical.extents))
    if vertical==1:
        canonical.apply_transform([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
    elif vertical==0:
        canonical.apply_transform([[0,0,-1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]])
    canonical.apply_scale(150.0/float(canonical.extents[2]))
    canonical.apply_translation([-canonical.centroid[0],-canonical.centroid[1],-canonical.bounds[0,2]])
    candidate=args.output_dir/"MASTER_150mm_FOR_LIKENESS_REVIEW_ONLY.stl"
    canonical.export(candidate)
    report["candidate"]={
        "mesh_faces":len(canonical.faces),
        "watertight":bool(canonical.is_watertight),
        "consistent_normals":bool(canonical.is_winding_consistent),
        "height_mm":float(canonical.extents[2]),
        "build_certified":False,
    }
    (args.output_dir/"reference_manifest.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False),encoding="utf8")
    print("MASTER_CANDIDATE_GEOMETRY_CREATED",str(candidate))
    print("NOT CERTIFIED: check the actual model against all eight images before splitting")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
