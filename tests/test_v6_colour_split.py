"""Guarantee no V6 STL is published without real multicolor 3D solid boundaries."""
import hashlib
import json
import pytest
import trimesh
from tflex_figurines.v6_colour_split import REQUIRED, export_colour_stl


def fixture(tmp_path):
    scene=trimesh.Scene()
    parts=[]
    for i,role in enumerate(sorted(REQUIRED)):
        mesh=trimesh.creation.box(extents=(3,3,5))
        mesh.apply_translation([8*i,0,10])
        name="piece_"+str(i)
        scene.add_geometry(mesh,node_name=name,geom_name=name)
        parts.append({"node":name,"material":"WING_BLUE" if "wing" in role else "BLACK",
                      "roles":[role],"verified_separate_3d_volume":True})
    raw=tmp_path/"source.glb"
    scene.export(raw)
    manifest={
        "schema_version":"6.0",
        "source_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),
        "source_original_sha256":["a"*64]*18,
        "artistic_review":{
            "status":"approved","reviewer":"user",
            "compared_to_original_screenshots":True,
            "actual_3d_view_files":[str(i)+".png" for i in range(5)]
        },
        "pieces":parts
    }
    meta=tmp_path/"manifest.json"
    meta.write_text(json.dumps(manifest))
    return raw,meta,manifest


def test_unapproved_sculpt_never_yields_STL(tmp_path):
    scene,meta,manifest=fixture(tmp_path)
    manifest["artistic_review"]["status"]="not approved"
    meta.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="not approved"):
        export_colour_stl(scene,meta,tmp_path/"result")
    assert not (tmp_path/"result").exists()


def test_approved_multi_solid_export_is_complete_and_closed(tmp_path):
    scene,meta,manifest=fixture(tmp_path)
    output=tmp_path/"result"
    report=export_colour_stl(scene,meta,output)
    assert report["all_body_parts_preserved"]
    assert not report["print_ready_certified"]
    assert len(report["components"])==len(REQUIRED)
    for file in (output/"STL_PRINT").glob("*.stl"):
        m=trimesh.load_mesh(file)
        assert m.is_watertight and m.volume>0
        assert abs(float(m.bounds[0][2]))<.001
    assert (output/"GROUPS_BY_FILAMENT"/"BLACK.txt").is_file()
    assert (output/"GROUPS_BY_FILAMENT"/"WING_BLUE.txt").is_file()
    with pytest.raises(ValueError,match="empty"):
        export_colour_stl(scene,meta,output)


def test_cannot_silently_omit_any_arm_or_other_role(tmp_path):
    scene,meta,manifest=fixture(tmp_path)
    manifest["pieces"].pop()
    meta.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="Missing required"):
        export_colour_stl(scene,meta,tmp_path/"result")


def test_source_replacement_rejected(tmp_path):
    scene,meta,manifest=fixture(tmp_path)
    manifest["source_sha256"]="f"*64
    meta.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="checksum changed"):
        export_colour_stl(scene,meta,tmp_path/"result")


def test_v5_or_texture_only_fake_part_rejected(tmp_path):
    scene,meta,manifest=fixture(tmp_path)
    manifest["schema_version"]="5.0"
    meta.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="V6 only"):
        export_colour_stl(scene,meta,tmp_path/"result")
    manifest["schema_version"]="6.0"
    manifest["pieces"][0]["verified_separate_3d_volume"]=False
    meta.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="texture"):
        export_colour_stl(scene,meta,tmp_path/"result")
