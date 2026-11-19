"""V6 anti-rotation wing interface: offline geometry + CAD regression suite."""
from dataclasses import replace

import pytest
import trimesh

from tflex_figurines.wing_mount_v6 import WingMountConfig, make_mount, export_fixture


def test_left_right_non_interfering_dual_hand_keyed_mounts():
    parts, joints = make_mount(WingMountConfig())
    assert len(parts) == 3
    assert len(joints) == 2
    assert joints[0]["peg_centres_xz_mm"] != joints[1]["peg_centres_xz_mm"]
    assert joints[0]["body_to_hub_gap_mm"] == 4.0
    for name, part in parts.items():
        assert part.isValid() and part.Volume() > 100, name
        if name.startswith("WING_"):
            assert parts["CENTRAL_HIDDEN_BLACK_BRIDGE"].intersect(part).Volume() < .005
    for joint in joints:
        assert joint["two_handed_non_collinear_keys"]
        assert joint["end_clearance_mm"] >= .3
        assert joint["pin_diameter_mm"] < joint["bore_diameter_mm"]


def test_invalid_wall_thickness_and_pin_fit_rejected():
    cfg = WingMountConfig()
    with pytest.raises(ValueError):
        make_mount(replace(cfg,radial_clearance_mm=0.01))
    with pytest.raises(ValueError):
        make_mount(replace(cfg,peg_center_spacing_mm=1))
    with pytest.raises(ValueError):
        make_mount(replace(cfg,hub_width_mm=6))
    with pytest.raises(ValueError):
        make_mount(replace(cfg,body_to_wing_hub_gap_mm=1))
    with pytest.raises(ValueError):
        make_mount(replace(cfg,peg_length_mm=12))


def test_real_stl_mobile_glb_step_reimport_calibration(tmp_path):
    output = tmp_path/"fixture"
    m = export_fixture(output)
    assert m["not_a_real_character_model"]
    assert not m["print_ready_certified"]
    assert m["step_readback_valid"]
    for path in (output/"STL_ASSEMBLY").glob("*.stl"):
        obj=trimesh.load_mesh(path,force="mesh")
        assert obj.is_volume and obj.is_watertight and obj.is_winding_consistent
    for path in (output/"STL_PRINT").glob("*.stl"):
        assert abs(float(trimesh.load_mesh(path).bounds[0][2])) < .01
    scene=trimesh.load(output/"Wing_Mount_V6_MOBILE_PREVIEW.glb",force="scene")
    assert len(scene.geometry)==3
    assert len(list((output/"CALIBRATION").glob("*.stl")))==4
    assert (output/"Wing_Mount_V6_TFLEX18_Assembly.step").stat().st_size > 10000
    with pytest.raises(FileExistsError):
        export_fixture(output)
