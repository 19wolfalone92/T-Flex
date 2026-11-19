#!/usr/bin/env python3
"""Private V9.1 likeness QA: five REAL 3D GLB renders and five original game views.
Only invoked AFTER an actual Hunyuan GLB exists; NEVER a fake artistic approval.
No original reference is printed, committed, or sent to a public artifact.
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import trimesh
import vtk
from vtk.util.numpy_support import numpy_to_vtk

VIEWS={"FRONT":(0,-300,100),"BACK":(0,300,100),
       "LEFT":(-300,0,100),"RIGHT":(300,0,100),
       "THREE_QUARTER":(-220,-230,126)}

def private_review(glb:Path, refs:Path, out:Path):
    if not glb.is_file():raise FileNotFoundError("REAL 3D GLB is missing")
    qa=json.loads((refs/"V9_INPUT_QA.json").read_text())
    valid={x["view"].upper():x["output_sha256"] for x in qa["records"]}
    for view in VIEWS:
        f=refs/("MV_"+view+"_RGBA_1024.png")
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=valid[view]:
            raise ValueError("Missing/modified source reference: "+view)
    scene=trimesh.load(glb,force="scene")
    if not len(scene.geometry):raise ValueError("Not actual mesh")
    if not 199.99 <= scene.bounds[1,2]-scene.bounds[0,2] <= 200.01:
        raise ValueError("Mesh must be normalized to 200 mm")
    ren=vtk.vtkRenderer();ren.SetBackground(.83,.86,.9)
    win=vtk.vtkRenderWindow();win.SetSize(960,1100);win.SetOffScreenRendering(1);win.AddRenderer(ren)
    count=0
    for mesh in scene.geometry.values():
        if not isinstance(mesh,trimesh.Trimesh) or not len(mesh.faces):continue
        points=vtk.vtkPoints();points.SetData(numpy_to_vtk(mesh.vertices.astype(np.float32)))
        tri=np.column_stack((np.full(len(mesh.faces),3),mesh.faces)).astype(np.int64)
        cells=vtk.vtkCellArray();cells.SetCells(len(mesh.faces),numpy_to_vtk(tri.ravel(),deep=True,array_type=vtk.VTK_ID_TYPE))
        poly=vtk.vtkPolyData();poly.SetPoints(points);poly.SetPolys(cells)
        norms=vtk.vtkPolyDataNormals();norms.SetInputData(poly);norms.Update()
        mapper=vtk.vtkPolyDataMapper();mapper.SetInputConnection(norms.GetOutputPort())
        actor=vtk.vtkActor();actor.SetMapper(mapper);actor.GetProperty().SetColor(.68,.73,.84)
        actor.GetProperty().SetAmbient(.35);ren.AddActor(actor);count+=1
    if count==0:raise ValueError("No faces for rendering")
    cam=ren.GetActiveCamera();cam.ParallelProjectionOn();cam.SetParallelScale(128)
    out.mkdir(exist_ok=True,parents=True)
    review=Image.new("RGB",(1920,5600),(224,230,238))
    mark=ImageDraw.Draw(review)
    hashes={}
    for i,(name,pos) in enumerate(VIEWS.items()):
        cam.SetPosition(*pos);cam.SetFocalPoint(0,0,100);cam.SetViewUp(0,0,1)
        ren.ResetCameraClippingRange();win.Render()
        snap=vtk.vtkWindowToImageFilter();snap.SetInput(win)
        snap.SetInputBufferTypeToRGB();snap.ReadFrontBufferOff();snap.Update()
        rendered=out/("V91_REAL_MODEL_"+name+".png")
        writer=vtk.vtkPNGWriter();writer.SetFileName(str(rendered));writer.SetInputConnection(snap.GetOutputPort());writer.Write()
        src=Image.open(refs/("MV_"+name+"_RGBA_1024.png")).convert("RGBA")
        bg=Image.new("RGBA",src.size,(214,220,230,255));bg.alpha_composite(src)
        review.paste(bg.convert("RGB").resize((960,960)),(0,1120*i+54))
        review.paste(Image.open(rendered).convert("RGB").resize((960,1030)),(960,1120*i+54))
        mark.text((18,1120*i+16),name+" ORIGINAL",fill=(20,25,35))
        mark.text((980,1120*i+16),name+" ACTUAL 3D RENDER",fill=(20,25,35))
        hashes[name]=hashlib.sha256(rendered.read_bytes()).hexdigest()
    review.save(out/"V91_PRIVATE_REAL_FIVE_VIEW_COMPARISON.png")
    report={"actual_glb_sha256":hashlib.sha256(glb.read_bytes()).hexdigest(),
            "geometry_count":count,"five_real_model_views":hashes,
            "review_uses_private_originals":True,
            "camera_orientation_artist_verified":False,
            "likeness_approved":False,"print_ready_certified":False}
    (out/"V91_PRIVATE_ART_QA.json").write_text(json.dumps(report,indent=2))
    print("PRIVATE_REAL_3D_RENDER_QA",len(hashes),"approved=False")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--glb",required=True,type=Path)
    p.add_argument("--private-originals",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    private_review(a.glb,a.private_originals,a.out)
