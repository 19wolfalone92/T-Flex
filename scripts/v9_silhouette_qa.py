"""V9 REAL 3D Artistic QA: silhouette discrepancy vs SHA256-verified PRIVATE originals.

The result is diagnostic, NOT artistic approval: original game cameras and
poses are uncalibrated. Source photographs are never committed to public CI.
"""
from pathlib import Path
import argparse,hashlib,json
import cv2,numpy as np
from PIL import Image,ImageDraw

SOURCE={"FRONT":"MV_FRONT_RGBA_1024.png","BACK":"MV_BACK_RGBA_1024.png",
        "LEFT":"MV_LEFT_RGBA_1024.png","RIGHT":"MV_RIGHT_RGBA_1024.png",
        "3Q":"MV_THREE_QUARTER_RGBA_1024.png"}

def render_foreground(image):
    p=np.asarray(image.convert("RGB"),dtype=np.int16)
    bg=np.median(np.concatenate((p[:15].reshape(-1,3),p[-15:].reshape(-1,3)),axis=0),axis=0)
    raw=(np.linalg.norm(p-bg,axis=2)>31).astype("uint8")
    n,labels,stats,_=cv2.connectedComponentsWithStats(raw,8)
    kept=np.zeros_like(raw)
    for k in range(1,n):
        if stats[k,cv2.CC_STAT_AREA]>=max(100,raw.size*.0005):
            kept[labels==k]=1
    return kept

def normalized(mask):
    y,x=np.nonzero(mask)
    if len(x)<300:return np.zeros((1024,1024),np.uint8)
    x0,y0,x1,y1=x.min(),y.min(),x.max()+1,y.max()+1
    crop=mask[y0:y1,x0:x1]
    width=round(829*crop.shape[1]/crop.shape[0]);height=829
    if width>930:width=930;height=round(930*crop.shape[0]/crop.shape[1])
    image=cv2.resize(crop,(width,height),interpolation=cv2.INTER_NEAREST)
    out=np.zeros((1024,1024),dtype=np.uint8)
    out[(1024-height)//2:(1024-height)//2+height,
        (1024-width)//2:(1024-width)//2+width]=image
    return out

def measure(original_alpha,rendered_rgb):
    original=original_alpha>85
    candidate=normalized(render_foreground(rendered_rgb))>0
    intersection=np.logical_and(original,candidate).sum()
    union=np.logical_or(original,candidate).sum()
    overlap=float(intersection/max(union,1))
    border_orig=cv2.Canny(original.astype("uint8")*255,50,100)
    border_model=cv2.Canny(candidate.astype("uint8")*255,50,100)
    if border_orig.any() and border_model.any():
        d1=cv2.distanceTransform(255-border_orig,cv2.DIST_L2,3)[border_model>0].mean()
        d2=cv2.distanceTransform(255-border_model,cv2.DIST_L2,3)[border_orig>0].mean()
        edge=float((d1+d2)/2)
    else:edge=float("inf")
    return {"silhouette_iou":round(overlap,4),
            "mean_bidirectional_boundary_px":round(edge,2),
            "original_foreground_pixels":int(original.sum()),
            "render_foreground_pixels":int(candidate.sum())}, candidate

def compare(refs:Path,renders:Path,out:Path,prefix="V9"):
    manifest=json.loads((refs/"V9_INPUT_QA.json").read_text(encoding="utf8"))
    signatures={r["view"]:r["output_sha256"] for r in manifest["records"]}
    out.mkdir(parents=True,exist_ok=True)
    result={}
    sheet=Image.new("RGB",(2048,len(SOURCE)*1040),(235,237,240))
    d=ImageDraw.Draw(sheet)
    for i,(view,filename) in enumerate(SOURCE.items()):
        reference=refs/filename
        key="three_quarter" if view=="3Q" else view.lower()
        if not reference.is_file() or hashlib.sha256(reference.read_bytes()).hexdigest()!=signatures.get(key):
            raise ValueError("Source original screenshot hash mismatch "+view)
        rp=renders/(prefix+"_"+view+"_RENDER.png")
        if not rp.is_file():raise FileNotFoundError("Missing real 3D render "+str(rp))
        image=Image.open(reference).convert("RGBA")
        record,candidate=measure(np.asarray(image)[:,:,3],Image.open(rp))
        result[view]=record
        left=Image.new("RGBA",(1024,1024),(242,244,246,255));left.alpha_composite(image)
        sheet.paste(left.convert("RGB"),(0,i*1040+16))
        a=np.asarray(image)[:,:,3]>85;b=candidate>0
        overlay=np.zeros((1024,1024,3),np.uint8)+230
        overlay[a&b]=(42,140,86)
        overlay[a&~b]=(225,76,70)
        overlay[~a&b]=(55,100,212)
        sheet.paste(Image.fromarray(overlay),(1024,i*1040+16))
        d.text((16,i*1040+1),view+" original",fill=(15,20,25))
        d.text((1040,i*1040+1),view+" IoU "+str(record["silhouette_iou"]),fill=(15,20,25))
    sheet.save(out/"V9_PRIVATE_FIVE_VIEW_SILHOUETTE_COMPARISON.png")
    result["warnings"]=["Different in-game camera poses and perspectives are not calibrated.",
      "Grass occludes boots, so some original silhouettes have missing pixels.",
      "IoU is not approval; face, eyes, hair, feathers require independent artistic inspection."]
    result["automated_art_approved"]=False
    result["print_ready_certified"]=False
    (out/"V9_PRIVATE_SILHOUETTE_QA.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--refs",type=Path,required=True)
    p.add_argument("--renders",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--prefix",default="V9")
    a=p.parse_args()
    print(json.dumps(compare(a.refs,a.renders,a.out,a.prefix),indent=2,ensure_ascii=False))
