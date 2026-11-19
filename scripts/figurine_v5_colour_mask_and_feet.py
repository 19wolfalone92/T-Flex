"""V5: real separately printable plague-doctor mask + boot-to-base pegs.

Rebuilds the verified V4 kit without crop loss. The black mask is a
surface-conformal slip-on GLUE overlay, NOT an anatomical boolean cut:
the original white hair/upper-head sculpt stays intact. Dedicated black STL
can be printed independently and fitted over it; 0.15-mm radial offset is a
nominal clearance to test. The rest of the character retains V4 geometry,
except two positively verified blind boot/base bores.

Only the actual source meshes can establish visual fidelity. No new AI
generation, no credit usage, no claim of printer certification.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import numpy as np
import scipy.sparse as sparse
import trimesh
import vtk
from scipy.sparse.csgraph import connected_components
from OCP.BRep import BRep_Builder
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound

from scripts.figurine_release_builder import as_vtk, cad_proxy, cad_solid


COLOURS = {
    1: (16, 20, 28), 2: (16, 20, 28), 3: (16, 20, 28), 4: (16, 20, 28),
    5: (118, 163, 226), 6: (118, 163, 226), 7: (234, 238, 243),
    8: (240, 184, 162), 9: (240, 184, 162), 10: (216, 220, 232),
    11: (22, 124, 230), 12: (22, 124, 230), 13: (211, 34, 54),
    14: (18, 22, 30), 15: (22, 23, 32),
}
MASK_NAME = "15_BLACK_PLAGUE_DOCTOR_MASK_OVERLAY"
BOOT_NAME = "01_BOOTS_AND_LOWER_BODY_BLACK"
BASE_NAME = "14_BASE_BLACK"
POSITION = ((-13.0, -10.0), (13.0, -10.0))
HOLE_RADIUS = 1.7
PIN_RADIUS = 1.5


def check(mesh: trimesh.Trimesh, name: str) -> trimesh.Trimesh:
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError("Nonmesh " + name)
    if not (mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0):
        raise ValueError("Broken positive solid: " + name)
    return mesh


def build_surface_mask(white_head: trimesh.Trimesh) -> trimesh.Trimesh:
    """Extract the actual original model's beaked front-left surface as a shell."""
    c = np.asarray(white_head.triangles_center)
    x, y, z = c.T
    hood = ((x + 12)/19)**2 + ((y + 20)/15)**2 + ((z - 143)/15)**2 < 1.28
    beak = ((x + 24)/15)**2 + ((y + 20)/13)**2 + ((z - 131)/13)**2 < 1.20
    selected = (hood | beak) & (y < -9.5) & (x < -2.0) & (z > 120.0)
    indices = np.flatnonzero(selected)
    if len(indices) < 7000:
        raise ValueError("Mask reference geometry not recognized")

    # Restrict to ONE contiguous portion of the original plague-doctor mask.
    adjacency = np.asarray(white_head.face_adjacency)
    adjacency = adjacency[selected[adjacency].all(axis=1)]
    sparse_adj = sparse.coo_matrix(
        (np.ones(len(adjacency)*2, dtype=bool),
         (np.r_[adjacency[:,0], adjacency[:,1]],
          np.r_[adjacency[:,1], adjacency[:,0]])),
        shape=(len(white_head.faces), len(white_head.faces)),
    ).tocsr()
    _, groups = connected_components(sparse_adj, directed=False)
    component = np.bincount(groups[indices]).argmax()
    faces = np.asarray(white_head.faces)[indices[groups[indices] == component]]
    if not 9000 <= len(faces) <= 15000:
        raise ValueError("Mask selected unexpected number of source triangles")

    ids, inverse = np.unique(faces, return_inverse=True)
    patch_faces = inverse.reshape(-1,3)
    surface = np.asarray(white_head.vertices)[ids]
    normals = np.asarray(white_head.vertex_normals)[ids]
    # Glue-on surface-conformal shell: inner clearance 0.15 mm,
    # nominal body thickness 1.30 mm. Protect the underlying white hair.
    outside = surface + normals * 1.45
    inside = surface + normals * 0.15
    n = len(ids)
    all_vertices = np.concatenate([outside, inside])
    horizontal = np.concatenate([patch_faces, patch_faces[:,[0,2,1]] + n])
    edges = np.concatenate([
        patch_faces[:,[0,1]],
        patch_faces[:,[1,2]],
        patch_faces[:,[2,0]],
    ])
    sorted_edges = np.sort(edges, axis=1)
    _, edge_ids, counts = np.unique(
        sorted_edges, axis=0, return_inverse=True, return_counts=True)
    borders = edges[counts[edge_ids] == 1]
    walls = np.concatenate([
        np.stack((borders[:,0], borders[:,1], borders[:,1]+n), axis=-1),
        np.stack((borders[:,0], borders[:,1]+n, borders[:,0]+n), axis=-1),
    ])
    mask = trimesh.Trimesh(
        vertices=all_vertices,
        faces=np.concatenate([horizontal, walls]),
        process=False,
    )
    mask.fix_normals()
    check(mask, "separate mask overlay")
    if len(mask.split(only_watertight=False)) != 1:
        raise ValueError("Mask fragmented")
    if not 1500 < mask.volume < 2200 or len(mask.faces) < 20000:
        raise ValueError("Mask surface volume outside validated range")
    return mask


def carve(mesh: trimesh.Trimesh, x: float, y: float,
          bottom: float, top: float, name: str) -> trimesh.Trimesh:
    """Exact 3D boolean; fail closed instead of emitting broken STL."""
    cutter = trimesh.creation.cylinder(
        radius=HOLE_RADIUS, height=top-bottom, sections=96)
    cutter.apply_translation([x,y,(bottom+top)/2])
    result = trimesh.boolean.difference([mesh,cutter], engine="manifold")
    check(result,name)
    removed = mesh.volume-result.volume
    if not 18 < removed < 75:
        raise ValueError(f"Drill volume unexpectedly {removed:.2f}mm3 for {name}")
    return result


def load_step(path: Path):
    reader=STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone or reader.TransferRoots() <= 0:
        raise ValueError("Unreadable CAD file "+path.name)
    model=reader.OneShape()
    if not BRepCheck_Analyzer(model).IsValid():
        raise ValueError("CAD BRep invalid "+path.name)
    return model


def write_step(shape, path: Path):
    writer=STEPControl_Writer()
    if writer.Transfer(shape,STEPControl_AsIs) != IFSelect_RetDone:
        raise ValueError("STEP transfer failed: "+path.name)
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise ValueError("STEP write failed: "+path.name)
    load_step(path)


def main(original_zip: Path, output_dir: Path):
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Output must be new and empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    kit=output_dir/"kit"
    kit.mkdir()
    with zipfile.ZipFile(original_zip) as archive:
        if archive.testzip():
            raise ValueError("Original V4 ZIP failed CRC")
        for item in archive.infolist():
            p=Path(item.filename)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError("Malicious ZIP entry")
        archive.extractall(kit)

    qa_file=kit/"QA_MANIFEST.json"
    qa=json.loads(qa_file.read_text("utf-8"))
    if qa.get("version")!="4.0" or len(qa["parts"])!=14 or len(qa["joints"])!=8:
        raise ValueError("V5 requires exact verified V4 kit")
    part_dir=kit/"STL_ASSEMBLY"
    head=check(trimesh.load_mesh(part_dir/"07_HAIR_AND_HEAD_WHITE.stl"),"original head")
    original_head_sha=hashlib.sha256((part_dir/"07_HAIR_AND_HEAD_WHITE.stl").read_bytes()).hexdigest()
    masked=build_surface_mask(head)
    masked.export(part_dir/(MASK_NAME+".stl"))
    print("MASK_OK:",len(masked.faces),round(masked.volume,3),flush=True)

    # Add two blind holes through the soles and into the stand. These are
    # aligned in the assembly coordinate system at z=0, without new floating
    # connectors, and with unchanged external boot and stand silhouettes.
    boots=check(trimesh.load_mesh(part_dir/(BOOT_NAME+".stl")),"boots")
    base=check(trimesh.load_mesh(part_dir/(BASE_NAME+".stl")),"stand")
    old_boot_vol,old_base_vol=boots.volume,base.volume
    for i,(x,y) in enumerate(POSITION):
        boots=carve(boots,x,y,bottom=-0.6,top=5.6,name=f"boot_{i}")
        base=carve(base,x,y,bottom=-4.3,top=0.5,name=f"stand_{i}")
    if not 70 < old_boot_vol-boots.volume < 130:
        raise ValueError("Unexpected boot drill volume")
    if not 60 < old_base_vol-base.volume < 110:
        raise ValueError("Unexpected base drill volume")
    boots.export(part_dir/(BOOT_NAME+".stl"))
    base.export(part_dir/(BASE_NAME+".stl"))
    print("FOOT_TO_STAND_HOLES_OK",round(old_boot_vol-boots.volume,3),
          round(old_base_vol-base.volume,3),flush=True)

    print_folder=kit/"STL_PRINT"
    single_solids=print_folder/"INDIVIDUAL_SOLIDS"
    for name,mesh in ((MASK_NAME,masked),(BOOT_NAME,boots),(BASE_NAME,base)):
        on_bed=mesh.copy()
        on_bed.apply_translation([0,0,-float(on_bed.bounds[0,2])])
        on_bed.export(print_folder/(name+"_on_bed.stl"))
        for old in single_solids.glob(name+"_shell_*.stl"):
            old.unlink()
        for idx,shell in enumerate(mesh.split(only_watertight=False),start=1):
            check(shell,"standalone "+name)
            on_bed_shell=shell.copy()
            on_bed_shell.apply_translation([0,0,-float(on_bed_shell.bounds[0,2])])
            on_bed_shell.export(single_solids/(name+f"_shell_{idx:02d}.stl"))

    # Dowel seats in foot and stand. The butt-to-butt mating plane is z=0,
    # the 8.8-mm pin fits within 5.6+4.3 mm of available axial depth.
    pin_dir=kit/"STL_PINS"
    for i,(x,y) in enumerate(POSITION, start=1):
        name=f"BASE_TO_BOOT_{i}"
        pin=trimesh.creation.cylinder(radius=PIN_RADIUS,height=8.8,sections=96)
        pin.apply_translation([x,y,.55])
        check(pin,name)
        pin.export(pin_dir/(name+"_ASSEMBLY.stl"))
        print_pin=pin.copy()
        print_pin.apply_translation([0,0,-float(print_pin.bounds[0,2])])
        print_pin.export(pin_dir/(name+"_PRINT.stl"))
        qa["joints"].append({
            "joint":name,"centre_mm":[x,y,0],
            "axis":2,"hole_diameter_mm":3.4,
            "pin_diameter_mm":3.0,"pin_length_mm":8.8,
            "boot_depth_mm":5.6,"stand_depth_mm":4.3,
            "radial_clearance_mm_each_side":.2,
            "gluing_and_dry_fit_required":True,
            "two_open_manifold_sockets":True,
        })

    # Mirror physical STL geometry in CAD: exact same cylinders and positions.
    step_dir=kit/"STEP_TFLEX"
    for label,bottom,top in (
        (BOOT_NAME,-.6,5.6),(BASE_NAME,-4.3,.5),
    ):
        source=step_dir/(label+"_FACETED_SOCKETS.step")
        cad=cq.Shape(load_step(source))
        for x,y in POSITION:
            cutter=cq.Solid.makeCylinder(
                HOLE_RADIUS,top-bottom,
                cq.Vector(x,y,bottom),cq.Vector(0,0,1))
            cad=cad.cut(cutter)
        if not cad.isValid():
            raise ValueError("CAD foot mount subtraction failed")
        cq.exporters.export(cad,str(source),exportType="STEP")
        load_step(source)
        print("STEP_UPDATED",source.name,flush=True)
    # Reduced faceted mask is a true separate STEP component. Its high-resolution
    # print mesh is unaffected by CAD decimation.
    try:
        simple=cad_proxy(as_vtk(masked))
        check(simple,"mask CAD proxy")
    except (RuntimeError,ValueError):
        simple=masked
    mask_cad=cq.Shape(cad_solid(simple))
    cq.exporters.export(
        mask_cad,str(step_dir/(MASK_NAME+"_FACETED.step")),
        exportType="STEP"
    )
    load_step(step_dir/(MASK_NAME+"_FACETED.step"))

    # Keep all 15 parts and 10 pegs in one T-FLEX-compatible STEP assembly.
    for existing in kit.glob("T-FLEX_18_V*_STEP_ASSEMBLY.step"):
        existing.unlink()
    compound=TopoDS_Compound()
    builder=BRep_Builder()
    builder.MakeCompound(compound)
    for file in sorted(step_dir.glob("*.step")):
        builder.Add(compound,load_step(file))
    for joint in qa["joints"]:
        if "centre_mm" not in joint:
            raise ValueError("Previous joint lacks coordinates")
        p=list(map(float,joint["centre_mm"]))
        axis=int(joint["axis"])
        diameter=float(joint["pin_diameter_mm"])
        length=float(joint["pin_length_mm"])
        p[axis]-=length/2
        vector=[0,0,0]
        vector[axis]=1
        cylinder=cq.Solid.makeCylinder(diameter/2,length,
                                      cq.Vector(*p),cq.Vector(*vector))
        builder.Add(compound,cylinder.wrapped)
    if not BRepCheck_Analyzer(compound).IsValid():
        raise ValueError("T-FLEX composite shell invalid")
    combined=kit/"T-FLEX_18_V5_15_COLOURS_10_PINS.step"
    write_step(compound,combined)

    # Standalone STL files are the source of truth for colour preview.
    # The GLB stores actual polygon geometry, not an AI-generated picture.
    for old in kit.glob("COLOUR_FIGURINE_*.glb"):
        old.unlink()
    scene=trimesh.Scene()
    for file in sorted(part_dir.glob("*.stl")):
        part=check(trimesh.load_mesh(file),file.name)
        number=int(file.name[:2])
        rgba=np.asarray([*COLOURS[number],255],dtype=np.uint8)
        part.visual.vertex_colors=np.tile(rgba,(len(part.vertices),1))
        scene.add_geometry(part,geom_name=file.stem)
    scene.export(str(kit/"COLOUR_FIGURINE_V5_15_PARTS_MOBILE.glb"))

    qa["version"]="5.0"
    qa["colour_separated_piece_count"]=15
    qa["mask_independent_STL"]=MASK_NAME+".stl"
    qa["mask_mount"]="surface-conformal glue-on overlay; no holes in white hair"
    qa["mask_inner_gap_mm"]=.15
    qa["mask_nominal_thickness_mm"]=1.3
    qa["white_hair_original_STL_sha256_unchanged"]=original_head_sha
    qa["original_sleeves_and_wings_untouched"]=True
    qa["stand_two_physical_dowels"]=True
    qa["all_joint_count"]=len(qa["joints"])
    qa["print_ready_certified"]=False
    qa["critical_fidelity_limitations"]=[
        "The V5 mask is a separate black glue-on shell, not a true subtractive split of the underlying white hair",
        "Plague mask overlay edge requires visual inspection and manual fitting",
        "Original AI reconstruction is not exact game geometry",
        "Some accent colours and eye details still need painting for exact fidelity",
        "Single mono FDM printer and filament are unspecified; no slicer or physical acceptance",
        "Original printed V4 wing joints and thin fingers still need strength tests",
    ]
    qa["parts"][MASK_NAME]={
        "triangles":len(masked.faces),"closed":True,"normals_consistent":True,
        "volume_mm3":round(masked.volume,3),
        "colour":"black","attachment":"glue-on conformal mask shell"
    }
    for name,mesh in ((BOOT_NAME,boots),(BASE_NAME,base)):
        qa["parts"][name]["triangles"]=len(mesh.faces)
        qa["parts"][name]["volume_mm3"]=round(mesh.volume,3)
    qa_file.write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding="utf8")

    # Rebuild the spec (do not hide colour mismatch or additive mask fitting).
    with (kit/"COLOUR_PARTS.csv").open("w",encoding="utf8",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["Part","Material colour","Units","Attachment"])
        for item in sorted(part_dir.glob("*.stl")):
            code=int(item.name[:2])
            name=item.stem
            mount=("glue to matching hair/beak surface"
                   if code==15 else
                   "2 dedicated stand pins" if code in (1,14) else
                   "8 pre-existing sockets/pins or glue after fitting")
            writer.writerow([name,COLOURS[code],1,mount])
    (kit/"V5_RU_READ_BEFORE_PRINT.txt").write_text(
        "V5 — 15 отдельных STL по цветам; у головы белые волосы, "
        "а маска чумного доктора стала отдельной печатной ЧЁРНОЙ "
        "накладкой. Накладка крепится КЛЕЕМ на исходную белую голову, "
        "прилегающий рельеф головы НЕ удалён. Зазор 0,15 мм "
        "условный и требует сухой примерки.\\n"
        "Добавлены два скрытых посадочных отверстия в ботинки и в "
        "подставку, 2 новых штифта BASE_TO_BOOT_1/2. Всего 10 штифтов.\\n"
        "Печатайте каждый *_on_bed.stl отдельно, меняя цвет филамента "
        "между группами. Подпиливайте соединения только после "
        "калибровочных тестов. Проверьте в слайсере минимальную толщину "
        "крыльев и пальцев, опоры, ориентацию, усадку и устойчивость.\\n"
        "STEP-сборка — фасеточная для T-FLEX CAD 18, "
        "а НЕ исходная параметрическая CAD-модель.\\n"
        "Это НЕ доказанная физической печатью модель и не точная копия "
        "игровых исходников.\\n",
        encoding="utf8",
    )
    sums={}
    for file in sorted(kit.rglob("*")):
        if file.is_file():
            sums[str(file.relative_to(kit))]=hashlib.sha256(file.read_bytes()).hexdigest()
    (output_dir/"SHA256.json").write_text(json.dumps(sums,indent=2),encoding="utf8")
    release=output_dir/"Winged_Character_V5_15_Colors_10_Pins_TFLEX_STEP.zip"
    with zipfile.ZipFile(release,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in sorted(kit.rglob("*")):
            if file.is_file():
                z.write(file,str(file.relative_to(kit)))
        z.write(output_dir/"SHA256.json","SHA256.json")
    with zipfile.ZipFile(release) as z:
        if z.testzip():
            raise ValueError("Generated release ZIP CRC failed")
    print("V5_RELEASE_READY",release,release.stat().st_size,flush=True)


if __name__=="__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
