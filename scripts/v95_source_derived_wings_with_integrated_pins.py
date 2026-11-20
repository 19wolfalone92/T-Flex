#!/usr/bin/env python3
"""V95 private-original-backed wing sculpt and truly fused twin-key pegs.

Source images MUST be kept in owner-private storage, never in a public repo.
These are resin-relief engineering candidates, NOT the whole 200mm figure.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np,cv2,trimesh
from PIL import Image
from scipy.ndimage import distance_transform_edt,gaussian_filter,binary_fill_holes
from skimage.measure import marching_cubes

MM_PER_PIXEL=200/830
ROOT_PEGS={"left":[(-17.,111.),(-17.,119.)],
           "right":[(19.,111.),(19.,119.)]}

def extract(rgba,side):
    if rgba.shape!=(1024,1024,4):raise ValueError("Private rear reference must be 1024 RGBA")
    hsv=cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2HSV)
    b=rgba[:,:,2].astype(float);g=rgba[:,:,1].astype(float);r=rgba[:,:,0].astype(float)
    colored=(hsv[:,:,0]>=95)&(hsv[:,:,0]<=130)&(hsv[:,:,1]>=60)&(hsv[:,:,2]>=70)
    colored&=(b>r+17)&(b>g+14)&(rgba[:,:,3]>220)
    region=np.zeros((1024,1024),np.uint8)
    if side=="left":region[288:525,152:499]=1;region[448:540,480:530]=0
    elif side=="right":region[291:530,551:876]=1;region[455:540,528:563]=0
    else:raise ValueError("left/right only")
    raw=np.uint8(colored&region.astype(bool))*255
    raw=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8),iterations=2)
    raw=cv2.morphologyEx(raw,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    n,labels,stats,_=cv2.connectedComponentsWithStats(raw,8)
    filtered=np.zeros_like(raw)
    for j in range(1,n):
        if stats[j,cv2.CC_STAT_AREA]>180:filtered[labels==j]=255
    filtered=cv2.morphologyEx(filtered,cv2.MORPH_CLOSE,np.ones((13,13),np.uint8),iterations=2)
    filled=binary_fill_holes(filtered>0)
    n,labels,stats,_=cv2.connectedComponentsWithStats(filled.astype(np.uint8),8)
    if n<2:raise ValueError("No wing connected component")
    largest=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
    result=np.uint8(labels==largest)
    if result.sum()<10000:raise ValueError("Wing reference pixels insufficient")
    return result

def sculpt(image,mask,side,pitch=.18):
    ys,xs=np.nonzero(mask)
    x0,x1=max(xs.min()-7,0),min(xs.max()+8,1024)
    z0,z1=max(ys.min()-7,0),min(ys.max()+8,1024)
    native=mask[z0:z1,x0:x1]
    rgb=image[z0:z1,x0:x1,:3]
    scale=pitch/MM_PER_PIXEL
    w,h=max(8,int(np.ceil((x1-x0)/scale))),max(8,int(np.ceil((z1-z0)/scale)))
    silhouette=cv2.resize(native,(w,h),interpolation=cv2.INTER_NEAREST).astype(float)
    silhouette=gaussian_filter(silhouette,.65)>.42
    texture=cv2.resize(rgb,(w,h),interpolation=cv2.INTER_AREA)
    mono=cv2.cvtColor(texture,cv2.COLOR_RGB2GRAY).astype(float)/255.
    low=gaussian_filter(mono,3.3)
    emboss=np.clip(.30*((low-gaussian_filter(low,12))/.15),-.17,.17)
    dist=distance_transform_edt(silhouette)*pitch
    depth=np.clip(1.+.60*np.minimum(dist,3)/3,1,1.60)+emboss
    depth=np.maximum(gaussian_filter(depth,1.1),1.15)
    rr,cc=np.mgrid[:h,:w]
    world_x=(x0+cc*scale-512)*MM_PER_PIXEL
    world_z=200-(z0+rr*scale-97)*MM_PER_PIXEL
    depth+=2*np.exp(-.5*(abs(world_x)/9)**2)
    start=-8.
    y_axis=start+np.arange(int(np.ceil((6-start)/pitch))+5)*pitch
    vox=silhouette[:,:,None] & (y_axis>=-.02)&(y_axis<=depth[:,:,None])
    for x,z in ROOT_PEGS[side]:
        radius=np.hypot(world_x-x,world_z-z)
        vox|=(radius[:,:,None]<=2.7)&(y_axis>=-.5)&(y_axis<=1.7)
        vox|=(radius[:,:,None]<=1.55)&(y_axis>=-6.9)&(y_axis<=.8)
        vox|=(radius[:,:,None]<=1.25)&(y_axis>=-7.35)&(y_axis< -6.9)
    vox=np.pad(vox,((2,2),(2,2),(2,2)))
    v,f,_,_=marching_cubes(vox.astype(np.float32),.5,spacing=(pitch,pitch,pitch))
    xw=(x0+((v[:,1]-2*pitch)/pitch)*scale-512)*MM_PER_PIXEL
    zw=200-(z0+((v[:,0]-2*pitch)/pitch)*scale-97)*MM_PER_PIXEL
    yw=13.5+v[:,2]-2*pitch+start
    mesh=trimesh.Trimesh(vertices=np.stack((xw,yw,zw),axis=1),faces=f,process=True)
    if mesh.volume<0:mesh.invert()
    if not mesh.is_watertight or mesh.body_count!=1:
        raise ValueError("Generated wing is not single watertight manifold")
    rgba=np.empty((len(mesh.vertices),4),np.uint8)
    pix_x=np.clip(np.rint(512+xw/MM_PER_PIXEL).astype(int),0,1023)
    pix_y=np.clip(np.rint(97+(200-zw)/MM_PER_PIXEL).astype(int),0,1023)
    colors=image[pix_y,pix_x,:3].copy()
    blue=(colors[:,2].astype(int)>colors[:,1].astype(int)+8)&(
         colors[:,2].astype(int)>colors[:,0].astype(int)+12)
    # Replace ONLY obvious scenery contamination with a real feather median.
    candidates=image[:,:,:3].astype(int)
    verified=(candidates[:,:,2]>candidates[:,:,1]+8)&(
             candidates[:,:,2]>candidates[:,:,0]+12)&(image[:,:,3]>180)
    fallback=np.median(image[:,:,:3][verified],axis=0) if verified.any() else [110,150,208]
    colors[~blue]=np.uint8(fallback)
    rgba[:,:3]=colors;rgba[:,3]=255
    mesh.visual.vertex_colors=rgba
    return mesh,{"side":side,"faces":int(len(mesh.faces)),"watertight":bool(mesh.is_watertight),
         "body_count":int(mesh.body_count),"volume_mm3":round(float(mesh.volume),2),
         "source_wing_pixels":int(mask.sum()),"mesh_pitch_mm":pitch,"bounds_mm":np.round(mesh.bounds,3).tolist(),
         "male_key_centers_xz_mm":ROOT_PEGS[side],
         "male_key_diameter_mm":3.1,"resin_fit_tested":False}

def build(source,out,expected_sha=None):
    if expected_sha and hashlib.sha256(source.read_bytes()).hexdigest()!=expected_sha:
        raise ValueError("Unauthorized or corrupt source reference SHA")
    img=np.asarray(Image.open(source).convert("RGBA"))
    out.mkdir(parents=True,exist_ok=True)
    report={"height_target_mm":200,"origin":"private original-game rear screenshot",
            "wings":[],"separate_color_parts_pending":True,
            "body_missing":True,"print_ready":False,"art_approved":False}
    for side in ("left","right"):
        mask=extract(img,side)
        mesh,info=sculpt(img,mask,side)
        name=f"V95_{side.upper()}"
        mesh.export(out/f"{name}_SOURCE_WING_KEYED_RESIN_TRIAL.stl")
        mesh.export(out/f"{name}_VERTEX_COLOR_PROOF.glb")
        report["wings"].append(info)
    (out/"V95_WING_SOURCE_MANIFOLD_QA.json").write_text(
         json.dumps(report,ensure_ascii=False,indent=2))
    print("REAL_GAME_WING_MESHES",len(report["wings"]), "ART_APPROVED false")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--private-original-rear",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--expected-sha256",default=None)
    a=p.parse_args();build(a.private_original_rear,a.output,a.expected_sha256)
