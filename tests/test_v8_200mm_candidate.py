"""V8 200-mm candidate: technical checks, not artistic likeness approval."""
import json
import os
from pathlib import Path
import pytest
import trimesh

ROOT=Path(os.environ.get("V8_OUT","./out/v8"))
GLB=ROOT/"WINGED_CHARACTER_V8_200MM_HIGHPOLY_CANDIDATE.glb"
QA=ROOT/"V8_GEOMETRY_QA.json"

@pytest.fixture(autouse=True)
def require_generated_v8_artifact():
    """Normal unit CI doesn't generate geometry. Dedicated V8 CI must."""
    if GLB.is_file() and QA.is_file():
        return
    if os.environ.get("V8_REQUIRE_ARTIFACT") == "1":
        pytest.fail("Missing V8 model or QA in mandatory V8 CI", pytrace=False)
    pytest.skip("V8 artifact not generated; full checks run in V8 dedicated workflow")


def test_real_glb_and_200mm():
    p=ROOT/"WINGED_CHARACTER_V8_200MM_HIGHPOLY_CANDIDATE.glb"
    assert p.is_file() and p.stat().st_size>1_000_000
    s=trimesh.load(p,force="scene")
    assert len(s.geometry)>=455
    assert 199.99<=float(s.bounds[1,2]-s.bounds[0,2])<=200.01
    assert all(m.is_watertight and m.volume>0 for m in s.geometry.values())

def test_real_relief_not_only_polycount():
    q=json.loads((ROOT/"V8_GEOMETRY_QA.json").read_text())
    assert q["modified_sculpt_surfaces"]>=120
    assert q["real_detail_solids"]>=10
    assert q["face_count"]>300_000
    assert q["thin_bbox_under_0_8mm"]>=0

def test_do_not_approve_fake_final_stl():
    q=json.loads((ROOT/"V8_GEOMETRY_QA.json").read_text())
    for k in ["full_likeness_approved","physical_colour_parts_approved",
              "wing_hardware_integrated","test_print_completed","print_ready_certified"]:
        assert q[k] is False

def test_two_wings_sleeves_and_boots_preserved():
    names=set(trimesh.load(ROOT/"WINGED_CHARACTER_V8_200MM_HIGHPOLY_CANDIDATE.glb",force="scene").geometry)
    for signature in ("WING_L_primary","WING_R_primary","arm_full_flared_sleeve_-1",
            "arm_full_flared_sleeve_1","boot_tall_shaft_-1","boot_tall_shaft_1",
            "iris_-1","iris_1"):
        assert any(signature in name for name in names),signature
