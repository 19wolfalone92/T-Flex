"""Reproducible 150mm winged-figure colour kit with *real* sockets (v3).

Uses the legally obtained source mesh from the project's previously released
GitHub archive. 3D fidelity is limited by that existing AI mesh.
"""
from __future__ import annotations

import csv
import json
import math
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh
import vtk
from OCP.BRep import BRep_Builder
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader, STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound

from scripts.figurine_release_builder import as_vtk, from_vtk, cad_proxy, cad_solid
from scripts.figurine_v3_joinery import socket

COLOURS = {
    "01_BOOTS_AND_LOWER_BODY_BLACK": [16,20,28,255],
    "02_TORSO_CENTER_BLACK": [16,20,28,255],
    "03_LEFT_FULL_SLEEVE_BLACK": [16,20,28,255],
    "04_RIGHT_FULL_SLEEVE_BLACK": [16,20,28,255],
    "05_LEFT_FEATHER_WING_BLUE": [118,163,226,255],
    "06_RIGHT_FEATHER_WING_BLUE": [118,163,226,255],
    "07_HAIR_AND_HEAD_WHITE": [234,238,243,255],
    "08_LEFT_VISIBLE_HAND_SKIN": [240,184,162,255],
    "09_RIGHT_VISIBLE_HAND_SKIN": [240,184,162,255],
    "10_SILVER_BACK_STAR": [216,220,232,255],
    "11_BLUE_BACK_RIBBON_LEFT": [22,124,230,255],
    "12_BLUE_BACK_RIBBON_RIGHT": [22,124,230,255],
    "13_RED_FRONT_BADGE": [211,34,54,255],
    "14_BASE_BLACK": [18,22,30,255],
}
CLIPS = {
    "01": [(2,50,-1)],
    "02": [(2,50,1),(2,117,-1),(0,-20,1),(0,20,-1)],
    "03": [(2,50,1),(2,82,-1),(0,-20,-1)],
    "04": [(2,50,1),(2,82,-1),(0,20,1)],
    "05": [(2,82,1),(2,117,-1),(0,-20,-1)],
    "06": [(2,82,1),(2,117,-1),(0,20,1)],
    "07": [(2,117,1)],
}
JOINTS = [
    ("NECK_L", 2, [-6.,0.,117.], 1.7, 4.7, [("02",-1),("07",1)]),
    ("NECK_R", 2, [6.,0.,117.], 1.7, 4.7, [("02",-1),("07",1)]),
    ("WAIST_L", 2, [-9.,-2.5,50.], 1.7, 4.7, [("02",1),("01",-1)]),
    ("WAIST_R", 2, [9.,-2.5,50.], 1.7, 4.7, [("02",1),("01",-1)]),
    ("SLEEVE_L", 0, [-20.,-4.,77.], 1.7, 4.7, [("02",1),("03",-1)]),
    ("SLEEVE_R", 0, [20.,-4.,77.], 1.7, 4.7, [("02",-1),("04",1)]),
    ("WING_L", 0, [-20.,5.6,90.], 1.15, 3.35, [("02",1),("05",-1)]),
    ("WING_R", 0, [20.,5.6,90.], 1.15, 3.35, [("02",-1),("06",1)]),
]


def clip_solid(source, planes):
    boundaries = vtk.vtkPlaneCollection()
    for axis, position, sign in planes:
        wall = vtk.vtkPlane()
        origin = [0.,0.,0.]
        normal = [0.,0.,0.]
        origin[axis] = position
        normal[axis] = sign
        wall.SetOrigin(origin)
        wall.SetNormal(normal)
        boundaries.AddItem(wall)
    tool = vtk.vtkClipClosedSurface()
    tool.SetInputData(as_vtk(source))
    tool.SetClippingPlanes(boundaries)
    tool.GenerateFacesOn()
    tool.SetTolerance(1e-6)
    tool.Update()
    result = from_vtk(tool.GetOutput())
    if not result.is_watertight or not result.is_winding_consistent or result.volume<=0:
        raise ValueError("Source part could not be closed at colour seam")
    return result


def extrude_xz(outline, ymin, ymax):
    points = np.asarray(outline,float)
    count = len(points)
    vertices = [(float(x),float(y),float(z)) for y in (ymin,ymax) for x,z in points]
    vertices += [(float(points[:,0].mean()),float(y),float(points[:,1].mean())) for y in (ymin,ymax)]
    polygons = []
    for i in range(count):
        j = (i+1)%count
        polygons.append((2*count, j, i))
        polygons.append((2*count+1, count+i, count+j))
        polygons.extend([(i,j,count+j),(i,count+j,count+i)])
    mesh = trimesh.Trimesh(vertices=vertices,faces=polygons,process=True)
    mesh.fix_normals()
    if not mesh.is_watertight or mesh.volume<=0:
        raise ValueError("Accessory polygon cannot be made solid")
    return mesh


def star(cx,cz,radius,inner,ymin,ymax):
    points=[]
    for i in range(10):
        angle = math.pi/2 + math.pi*i/5
        r = radius if i%2==0 else inner
        points.append((cx+r*math.cos(angle),cz+r*math.sin(angle)))
    return extrude_xz(points,ymin,ymax)


def accessories():
    hands={}
    for side,code in [(-1,"08"),(1,"09")]:
        hand=trimesh.creation.icosphere(subdivisions=5)
        hand.apply_scale([3.95,3.9,4.85])
        hand.apply_translation([side*25.585,-3.45,50.14])
        hands[code]=hand
    ribbons={
        "11": extrude_xz([(-6.35,105),(-0.85,105),(-2.2,88),(-3.6,92)],16.,17.6),
        "12": extrude_xz([(0.85,105),(6.35,105),(3.6,92),(2.2,88)],16.,17.6),
    }
    stand = (cq.Workplane("XY").ellipse(47,32).extrude(5.5)
        .union(cq.Workplane("XY").workplane(offset=5.5)
               .ellipse(47,32).ellipse(44,29).extrude(.8)))
    stand_solid = stand.translate((0,0,-5.5)).val()
    # CAD export produces 94 x 64 mm oval black stand.
    stand_stl = stand_solid
    return {
        **hands,
        "10": star(0.,107.5,4.75,2.25,15.9,17.6),
        **ribbons,
        "13": star(0.,78.3,3.2,1.5,-15.8,-14.8),
        "14": None,  # Replaced by native CAD stand STL during build.
    }, stand_solid, stand_stl


def main(source: Path, target: Path):
    if target.exists() and any(target.iterdir()):
        raise ValueError("Use empty directory; no destructive overwrite")
    target.mkdir(parents=True,exist_ok=True)
    print("Loading licensed source",source,flush=True)
    body = trimesh.load_mesh(str(source),force="mesh")
    if not body.is_watertight or not body.is_winding_consistent or len(body.faces)!=301248:
        raise ValueError("Unexpected source geometry; refuse change without audit")
    if abs(body.volume-129078.027)>0.5:
        raise ValueError("Unexpected original volume; no clipping")
    print("Segmenting 7 original parts with volume conservation",flush=True)
    raw={}
    for code,planes in CLIPS.items():
        label=next(k for k in COLOURS if k.startswith(code))
        raw[label]=clip_solid(body,planes)
    summed=sum(m.volume for m in raw.values())
    if abs(summed-body.volume)>0.3:
        raise ValueError("Clipping removed body geometry")
    # Complete arms and bell-sleeves are in source; never crop them.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        objects, base, base_print = accessories()
        # Native CAD base is converted to STL for exact print assembly.
        obj_path=Path(tmp)/"base.stl"
        cq.exporters.export(base_print,str(obj_path),exportType="STL",tolerance=.05)
        objects["14"]=trimesh.load_mesh(str(obj_path),force="mesh")
    for code,mesh in objects.items():
        if mesh is None:
            raise ValueError("Missing independent figure part")
        label=next(k for k in COLOURS if k.startswith(code))
        raw[label]=mesh
    if len(raw)!=14:
        raise ValueError("Expected fourteen colour-separated parts")
    detailed={k:v.copy() for k,v in raw.items()}
    proof=[]
    for name,axis,centre,radius,depth,contacts in JOINTS:
        volumes=[]
        for code,direction in contacts:
            part=next(k for k in detailed if k.startswith(code))
            old=detailed[part]
            repaired=socket(old,centre,axis,direction,radius,depth)
            removed=old.volume-repaired.volume
            expected=math.pi*radius**2*depth
            if not 0.975*expected < removed < 1.025*expected:
                raise ValueError("Bore removed unexpected volume")
            detailed[part]=repaired
            volumes.append({"part":part,"removed_volume_mm3":round(removed,3)})
        proof.append({
            "joint":name,"centre_mm":centre,"axis":axis,
            "hole_diameter_mm":radius*2,"depth_mm_each_side":depth,
            "pin_diameter_mm":2*(radius-.2),"pin_length_mm":depth*2-.45,
            "two_open_manifold_sockets":True,"volumes":volumes,
        })
        print("Verified blind socket pair",name,flush=True)
    for d in ("STL_PRINT","STL_ASSEMBLY","STL_PINS","STEP_TFLEX","STL_PRINT/INDIVIDUAL_SOLIDS"):
        (target/d).mkdir(parents=True,exist_ok=True)
    parts_qa={}
    colour_scene=trimesh.Scene()
    for name,m in sorted(detailed.items()):
        if not (m.is_watertight and m.is_winding_consistent and m.volume>0):
            raise ValueError("Nonmanifold 3D print piece "+name)
        m.export(str(target/"STL_ASSEMBLY"/(name+".stl")))
        bed=m.copy()
        bed.apply_translation([0,0,-bed.bounds[0,2]])
        bed.export(str(target/"STL_PRINT"/(name+"_on_bed.stl")))
        for i,shell in enumerate(m.split(only_watertight=False),start=1):
            if not shell.is_watertight:
                raise ValueError("Independent shell is not watertight")
            placed=shell.copy()
            placed.apply_translation([0,0,-placed.bounds[0,2]])
            placed.export(str(target/"STL_PRINT"/"INDIVIDUAL_SOLIDS"/(name+f"_shell_{i:02d}.stl")))
        shade=m.copy()
        shade.visual.vertex_colors=np.tile(np.array(COLOURS[name],dtype=np.uint8),(len(shade.vertices),1))
        colour_scene.add_geometry(shade,geom_name=name)
        parts_qa[name]={
            "triangles":len(m.faces),"closed":m.is_watertight,
            "normals_consistent":m.is_winding_consistent,
            "volume_mm3":round(m.volume,3),
        }
    colour_scene.export(str(target/"COLOUR_FIGURINE_V3_WITH_PIN_SOCKETS_MOBILE.glb"))
    for j in proof:
        centre=j["centre_mm"]
        r=j["pin_diameter_mm"]/2
        length=j["pin_length_mm"]
        rod=trimesh.creation.cylinder(radius=r,height=length,sections=64)
        if j["axis"]==0:
            rod.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[0,1,0]))
        rod.apply_translation(centre)
        rod.export(str(target/"STL_PINS"/(j["joint"]+"_ASSEMBLY.stl")))
        rod.apply_translation([0,0,-rod.bounds[0,2]])
        rod.export(str(target/"STL_PINS"/(j["joint"]+"_PRINT.stl"))
    for diameter,pin_d in [(3.4,3.0),(2.3,1.9)]:
        block=(cq.Workplane("XY").box(11,11,6,centered=(True,True,False))
               .cut(cq.Workplane("XY").circle(diameter/2).extrude(6.1)))
        cq.exporters.export(block,str(target/"STL_PINS"/f"TEST_FIT_{pin_d:.1f}_IN_{diameter:.1f}.stl"),exportType="STL")
    # Build an honest CAD proxy and cut REAL matching holes in it.
    print("Creating T-FLEX 18 faceted CAD proxy for explicit mechanical sockets",flush=True)
    proxy = cad_proxy(as_vtk(body))
    cad_components=[]
    for name in sorted(raw):
        code=name[:2]
        if code in CLIPS:
            piece=clip_solid(proxy,CLIPS[code])
            shells=piece.split(only_watertight=False)
            shapes=[cq.Shape(cad_solid(shell)) for shell in shells if len(shell.faces)>8]
            if not shapes:
                raise ValueError("No CAD solids from source part "+name)
            cad=cq.Compound.makeCompound(shapes)
        elif code=="14":
            cad=base
        else:
            # Small independent details: a fully closed faceted proxy.
            m=raw[name]
            sample=m if len(m.faces)<7000 else cad_proxy(as_vtk(m))
            cad=cq.Shape(cad_solid(sample))
        cutters=[]
        for title,axis,centre,radius,depth,contacts in JOINTS:
            for part_id,direction in contacts:
                if part_id!=code:
                    continue
                basepoint=[float(a) for a in centre]
                basepoint[axis]-=direction*0.12
                vector=[0.,0.,0.]
                vector[axis]=float(direction)
                cutters.append(cq.Solid.makeCylinder(radius,depth+.12,cq.Vector(*basepoint),cq.Vector(*vector)))
        if cutters:
            cad=cad.cut(cq.Compound.makeCompound(cutters))
        if not cad.isValid():
            raise ValueError("Invalid T-FLEX CAD part "+name)
        file=target/"STEP_TFLEX"/(name+"_FACETED_SOCKETS.step")
        cq.exporters.export(cad,str(file),exportType="STEP")
        cad_components.append(cad.wrapped)
        print("STEP rebuilt",name,flush=True)
    for j in proof:
        centre=list(j["centre_mm"])
        axis=j["axis"]
        height=j["pin_length_mm"]
        centre[axis]-=height/2
        direction=[0.,0.,0.]
        direction[axis]=1.
        peg=cq.Solid.makeCylinder(j["pin_diameter_mm"]/2,height,cq.Vector(*centre),cq.Vector(*direction))
        cad_components.append(peg.wrapped)
    compound=TopoDS_Compound()
    builder=BRep_Builder()
    builder.MakeCompound(compound)
    for shape in cad_components:
        builder.Add(compound,shape)
    step=target/"T-FLEX_18_V3_COLOUR_PARTS_WITH_HOLES.step"
    writer=STEPControl_Writer()
    assert writer.Transfer(compound,STEPControl_AsIs)==IFSelect_RetDone
    assert writer.Write(str(step))==IFSelect_RetDone
    reader=STEPControl_Reader()
    assert reader.ReadFile(str(step))==IFSelect_RetDone
    assert reader.TransferRoots()>0
    assert BRepCheck_Analyzer(reader.OneShape()).IsValid()
    manifest={
        "version":"3.0",
        "source":"Previously generated Hi3DGen model, not exact recreation of later 2D art",
        "height_mm":150,
        "original_triangles":len(body.faces),
        "original_volume_mm3":body.volume,
        "original_seven_parts_volume_conserved":True,
        "parts":parts_qa,"joints":proof,
        "blind_holes_in_print_STL":True,
        "two_sockets_per_pin":True,
        "eight_real_mating_pins":True,
        "step_validated":True,
        "step_faceted_proxy":True,
        "step_colours_not_guaranteed":True,
        "print_ready_certified":False,
        "physical_validation_missing":[
            "physical fit coupons on actual printer","FDM wall thickness and slicer supports",
            "wing-root mechanical strength","T-FLEX CAD 18 on user Windows"
        ],
    }
    (target/"QA_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    with (target/"COLOUR_PARTS.csv").open("w",encoding="utf-8",newline="") as fp:
        csvout=csv.writer(fp)
        csvout.writerow(["STL","Filament colour","Count"])
        for name in sorted(detailed):
            csvout.writerow([name,name.split("_")[-1],1])
    (target/"ПЕЧАТЬ_И_СБОРКА_RU.txt").write_text(
        "Крылатый персонаж V3 — детали STL по цветам, 150 мм.\n"
        "ВНИМАНИЕ: внешность основана на прежнем 3D-скульпте, а не точном 2D-концепте.\n"
        "14 компонентов, длинные рукава и обе руки сохранены.\n"
        "Восемь настоящих штифтов и шестнадцать встроенных глухих отверстий.\n"
        "Голова и пояс по два штифта, левый и правый рукав и крыло по одному.\n"
        "Печатайте группы отдельно с заменой одноцветной катушки.\n"
        "Проверьте пробные посадки TEST_FIT в STL_PINS перед полной печатью.\n"
        "В T-FLEX CAD 18 открывайте T-FLEX_18_V3_COLOUR_PARTS_WITH_HOLES.step.\n"
        "Физическая печать не проверена. Проверьте тонкие перья и опоры в слайсере.\n",
        encoding="utf-8"
    )
    zip_path=target.parent/"Winged_Character_COLOUR_V3_TFLEX_STL_WITH_REAL_SOCKETS.zip"
    with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=5) as archive:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                archive.write(path,arcname=str(path.relative_to(target)))
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
    print("RELEASE_SUCCESS",zip_path,zip_path.stat().st_size,flush=True)


if __name__=="__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
