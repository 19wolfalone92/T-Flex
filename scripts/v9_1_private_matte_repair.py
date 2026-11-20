#!/usr/bin/env python3
"""PRIVATE source mattes, not a model: remove grass/scenery from five game views.
Never uploads images, never manufactures anatomy, never marks likeness approved.
Input = V9 prep folder with *original* crops, SHA manifest and prior alpha PNGs.
Output MUST be a new folder; the original input remains unchanged.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image,ImageDraw

VIEWS={"front":"01_FRONT_ORIGINAL_CROP.png","back":"02_BACK_ORIGINAL_CROP.png",
       "left":"03_LEFT_ORIGINAL_CROP.png","right":"04_RIGHT_ORIGINAL_CROP.png",
       "three_quarter":"05_THREE_QUARTER_CROP.png"}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prior_native_alpha(prior,rec):
    w,h=rec["source_size"];x0,y0,x1,y1=rec["alpha_bbox"]
    bw,bh=x1-x0,y1-y0
    scale=min(830/bh,875/bw);tw,th=round(bw*scale),round(bh*scale)
    x=(1024-tw)//2;y=(1024-th)//2
    a=np.asarray(prior.convert("RGBA"))[y:y+th,x:x+tw,3]
    if a.shape!=(th,tw):raise ValueError("Prior alpha transform invalid")
    native=np.zeros((h,w),dtype=np.uint8)
    native[y0:y1,x0:x1]=cv2.resize(a,(bw,bh),interpolation=cv2.INTER_NEAREST)
    return native

def make_matte(src:Path,prior:Path,rec:dict,view:str,dest:Path):
    if sha(src)!=rec["sha256_source"]:raise ValueError("Original source SHA mismatch")
    if sha(prior)!=rec["output_sha256"]:raise ValueError("Original prior SHA mismatch")
    rgb=np.asarray(Image.open(src).convert("RGB"))
    h,w=rgb.shape[:2]
    mask=prior_native_alpha(Image.open(prior),rec)
    if rgb.shape[:2]!=(rec["source_size"][1],rec["source_size"][0]):
        raise ValueError("Original source geometry mismatch")
    H,S,V=cv2.split(cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV))
    red,green,blue=(rgb[:,:,i].astype(np.float32) for i in (0,1,2))
    green_matte=((H>=29)&(H<=97)&(S>=70)&(V>=90)&(green>red*1.13)&(green>blue*.98))
    olive_grass=((H>=22)&(H<=70)&(S>=95)&(V>=88)&(blue<green*.78))
    mask[green_matte|olive_grass]=0
    excluded=np.zeros((h,w),dtype=np.uint8)
    def poly(coords):
        q=np.asarray([(round(w*x),round(h*y)) for x,y in coords],dtype=np.int32)
        cv2.fillPoly(excluded,[q],255)
    if view=="left":
        # Wooden roof/lantern above head & to right of beak; never fill gaps.
        for pts in [[(.625,0),(1,0),(1,.34),(.665,.30),(.625,.23)],
                    [(.735,.295),(1,.295),(1,.49),(.765,.48)],
                    [(0,0),(.17,0),(.17,.24),(0,.24)],
                    [(.17,0),(.255,0),(.255,.088),(.17,.088)],
                    [(.465,0),(.625,0),(.625,.09),(.465,.09)],
                    [(.57,.075),(.63,.075),(.63,.19),(.57,.19)]]:
            poly(pts)
    if view=="right":
        poly([(0,0),(.20,0),(.20,.27),(0,.27)])
    mask[excluded>0]=0
    n,cc,stats,_=cv2.connectedComponentsWithStats((mask>0).astype(np.uint8),8)
    if n<=1:raise ValueError("Empty source matte: "+view)
    kept=np.where(cc==1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA])),255,0).astype(np.uint8)
    y,x=np.where(kept!=0)
    if len(x)<w*h*.05:raise ValueError("Severe matte information loss: "+view)
    x0,x1=int(x.min()),int(x.max())+1
    y0,y1=int(y.min()),int(y.max())+1
    crop=np.dstack([rgb,kept])[y0:y1,x0:x1]
    scale=min(830/(y1-y0),875/(x1-x0))
    tw,th=round((x1-x0)*scale),round((y1-y0)*scale)
    rendered=Image.fromarray(crop,"RGBA").resize((tw,th),Image.Resampling.LANCZOS)
    canvas=Image.new("RGBA",(1024,1024),(0,0,0,0))
    canvas.alpha_composite(rendered,((1024-tw)//2,(1024-th)//2))
    # Exclude only tiny disjoint prop/plant fragments after alpha resizing.
    rgba=np.asarray(canvas).copy()
    n,cc,stats,_=cv2.connectedComponentsWithStats((rgba[:,:,3]>5).astype(np.uint8),8)
    if n>1:
        main=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
        rgba[:,:,3][cc!=main]=0
    Image.fromarray(rgba,"RGBA").save(dest)
    return {"view":view,"source":src.name,"sha256_source":sha(src),
            "source_size":[w,h],"output_sha256":sha(dest),
            "prior_input_sha256":sha(prior),"pixels_with_alpha":int((rgba[:,:,3]>5).sum()),
            "post_crop_alpha_fraction":round(float((rgba[:,:,3]>5).mean()),4),
            "not_a_ground_truth_segmentation":True,"artist_review_required":True,
            "occluded_legs":view in ("left","right"),"colour_artifacts_possible":True}

def process(source_dir:Path,output_dir:Path):
    if output_dir.resolve()==source_dir.resolve():raise ValueError("Never modify original reference directory")
    records=json.loads((source_dir/"V9_INPUT_QA.json").read_text(encoding="utf8"))["records"]
    byview={r["view"]:r for r in records}
    if set(byview)!=set(VIEWS):raise ValueError("Five authentic original views required")
    output_dir.mkdir(parents=True,exist_ok=True)
    result=[]
    for view,original in VIEWS.items():
        src=source_dir/original
        prior=source_dir/f"MV_{view.upper()}_RGBA_1024.png"
        dest=output_dir/f"MV_{view.upper()}_RGBA_1024.png"
        if not src.is_file() or not prior.is_file():raise FileNotFoundError(view)
        result.append(make_matte(src,prior,byview[view],view,dest))
    qa={"records":result,"original_images_authoritative":True,"target_height_mm":200,
        "multiview_pose_consistency_unverified":True,"master_mesh_created":False,
        "source_reconstruction_artist_approved":False,"print_ready_certified":False}
    for name in ("V9_INPUT_QA.json","V91_INPUT_QA.json"):
        (output_dir/name).write_text(json.dumps(qa,ensure_ascii=False,indent=2))
    sheet=Image.new("RGB",(5*1024,1080),"#dde2e8");d=ImageDraw.Draw(sheet)
    for i,view in enumerate(VIEWS):
        i0=Image.open(output_dir/f"MV_{view.upper()}_RGBA_1024.png")
        panel=Image.new("RGBA",(1024,1024),"#d7dce6");panel.alpha_composite(i0)
        sheet.paste(panel.convert("RGB"),(i*1024,48))
        d.text((i*1024+18,14),view.upper(),fill="#182030")
    sheet.save(output_dir/"V91_MASKS_REVIEW_PRIVATE.png")
    return qa

def main():
    p=argparse.ArgumentParser();p.add_argument("--original-dir",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    a=p.parse_args();qa=process(a.original_dir,a.output_dir)
    print("PRIVATE_MATTES_REFINED",len(qa["records"]),"real_3d_model_generated=False")
if __name__=="__main__":main()
