"""Export real V6 physical colour parts only from an approved multi-solid GLB.

No guessing material boundaries from textures or clipping a single mesh into
fake 'colour' halves. Same-colour components are grouped for filament changes
but never welded when physically separate (e.g., both blue wings).
Fail closed if any required anatomy, art approval, or mesh node is missing.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh


REQUIRED = {
    "face_skin", "hair_white", "plague_headwear_black", "face_mask_black",
    "full_left_sleeve", "full_right_sleeve", "left_wing_blue",
    "right_wing_blue", "left_boot", "right_boot", "back_star_silver",
    "ribbon_left_blue", "ribbon_right_blue", "torso"
}
MATERIALS = {
    "BLACK": (20,22,29), "DARK_GRAY": (47,47,54),
    "WHITE": (235,237,244), "SKIN": (239,190,175),
    "WING_BLUE": (153,181,230), "BRIGHT_BLUE": (18,137,226),
    "SILVER": (191,196,202), "ORANGE_PINK": (245,148,127),
    "RED": (130,35,45)
}


def validate_manifest(source: Path, manifest: dict):
    if manifest.get("schema_version") != "6.0":
        raise ValueError("V6 only; never reissue earlier V5 geometry")
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    if sha!=manifest.get("source_sha256"):
        raise ValueError("Master GLB checksum changed since review")
    review=manifest.get("artistic_review",{})
    if review.get("status")!="approved" or review.get("reviewer") not in (
        "user","independent_expert"
    ):
        raise ValueError("Visual appearance not approved: no colour splitting")
    if (not review.get("compared_to_original_screenshots") or
        len(review.get("actual_3d_view_files",[]))<5):
        raise ValueError("Require real 5-angle 3D previews, compared with game screenshots")
    if len(manifest.get("source_original_sha256",[]))<8:
        raise ValueError("Eight original game screenshots required, not AI concept only")
    pieces=manifest.get("pieces",[])
    if not pieces:
        raise ValueError("No physical colour regions")
    roles=set()
    seen=set()
    for piece in pieces:
        name=piece.get("node")
        if not isinstance(name,str) or not name or name in seen:
            raise ValueError("Duplicate or unnamed 3D node")
        seen.add(name)
        if piece.get("material") not in MATERIALS:
            raise ValueError("Unrecognized physical filament colour")
        if not piece.get("verified_separate_3d_volume",False):
            raise ValueError("Colour texture is not an independent STL volume: "+name)
        if not piece.get("roles"):
            raise ValueError("Missing semantic piece roles")
        roles.update(piece["roles"])
    missing=REQUIRED-roles
    if missing:
        raise ValueError("Missing required anatomical regions: "+str(sorted(missing)))
    return sha


def export_colour_stl(master:Path, manifest_path:Path, dest:Path, max_parts:int=100):
    if not master.is_file() or master.suffix.lower()!=".glb":
        raise ValueError("Need real approved .glb master")
    data=json.loads(manifest_path.read_text(encoding="utf-8"))
    checksum=validate_manifest(master,data)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("Use new empty output directory")
    scene=trimesh.load(str(master),force="scene",process=False)
    if not isinstance(scene,trimesh.Scene) or not scene.graph.nodes_geometry:
        raise ValueError("Need actual multi-object 3D scene")
    if len(data["pieces"])>max_parts:
        raise ValueError("Excessive micron-sized oversegmentation")
    nodes={str(key):key for key in scene.graph.nodes_geometry}
    all_meshes={}
    info=[]
    total=0.0
    # All-or-nothing validation: no truncated body can be exported.
    for piece in data["pieces"]:
        key=piece["node"]
        if key not in nodes:
            raise ValueError("No corresponding genuine 3D part "+key)
        transform,g=scene.graph[nodes[key]]
        base=scene.geometry[g]
        if not isinstance(base,trimesh.Trimesh):
            raise ValueError("Non-triangulated body "+key)
        mesh=base.copy()
        mesh.apply_transform(transform)
        mesh.remove_unreferenced_vertices()
        if not(mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0):
            raise ValueError("Nonmanifold / inverted printable part "+key)
        if len(mesh.split(only_watertight=False))!=1:
            raise ValueError("Disconnected fragments inside STL "+key)
        if not np.isfinite(mesh.vertices).all():
            raise ValueError("Nonfinite 3D geometry")
        all_meshes[key]=mesh
        total+=mesh.volume
        info.append({"node":key,"colour":piece["material"],
                     "roles":piece["roles"],"triangles":len(mesh.faces),
                     "volume_mm3":round(mesh.volume,3),
                     "assembly_bounds_mm":mesh.bounds.round(3).tolist()})
    omitted=set(nodes)-set(all_meshes)
    if omitted:
        raise ValueError("Master objects would be silently lost: "+str(sorted(omitted)))
    dest.mkdir(parents=True,exist_ok=True)
    for folder in ("STL_ASSEMBLY","STL_PRINT","GROUPS_BY_FILAMENT"):
        (dest/folder).mkdir()
    for record in info:
        name=record["node"]
        mesh=all_meshes[name]
        mesh.export(dest/"STL_ASSEMBLY"/(name+".stl"))
        on_bed=mesh.copy()
        on_bed.apply_translation([0,0,-float(on_bed.bounds[0][2])])
        on_bed.export(dest/"STL_PRINT"/(name+"_ON_BED.stl"))
        with (dest/"GROUPS_BY_FILAMENT"/(record["colour"]+".txt")).open("a",encoding="utf-8") as f:
            f.write(name+"_ON_BED.stl\n")
    with (dest/"PARTS_LIST.csv").open("w",encoding="utf-8",newline="") as f:
        out=csv.writer(f)
        out.writerow(["mesh_node","filament","roles","triangles","volume_mm3"])
        for r in info:
            out.writerow([r["node"],r["colour"]," + ".join(r["roles"]),
                          r["triangles"],r["volume_mm3"]])
    report={
        "v6_version":"6.0","new_master_sha256":checksum,
        "artwork_approved_before_split":True,
        "separate_physical_material_volumes":True,
        "all_body_parts_preserved":True,
        "all_glb_nodes_accounted_for":True,"components":info,
        "total_original_volume_mm3":round(total,3),
        "mechanical_connectors_integrated":False,
        "slicer_accepted":False,"print_ready_certified":False,
        "warning":"Independent STL colour bodies only; not an assembled or certified figure."
    }
    (dest/"QA_MANIFEST.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("master",type=Path)
    parser.add_argument("manifest",type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    args=parser.parse_args()
    report=export_colour_stl(args.master,args.manifest,args.output_dir)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
