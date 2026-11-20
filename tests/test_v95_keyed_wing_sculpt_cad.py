"""V95 robust mechanical tests use synthetic blue fans, never private photos."""
import numpy as np,pytest,trimesh
pytest.importorskip("cv2")
pytest.importorskip("scipy")
pytest.importorskip("skimage")
pytest.importorskip("cadquery")
from PIL import Image,ImageDraw
from scripts.v95_source_derived_wings_with_integrated_pins import build
from scripts.v95_keyed_wing_sockets_cad import build as build_receivers

def source(tmp_path):
    a=Image.new("RGBA",(1024,1024))
    d=ImageDraw.Draw(a)
    d.ellipse((172,298,495,512),fill=(118,161,219,255))
    d.ellipse((548,302,872,515),fill=(123,163,222,255))
    # Different feather-light colors, still genuine geometry after synthetic masking.
    for i in range(3):
        d.ellipse((180+i*17,310+i*35,390+i*10,343+i*37),
                  fill=(116+i*2,158+i*3,216+i*2,255))
        d.ellipse((656-i*25,312+i*35,850-i*10,345+i*37),
                  fill=(118+i*2,161+i*3,220+i*2,255))
    p=tmp_path/"synthetic_rear.png";a.save(p)
    return p

def test_actual_wing_meshes_have_fused_pins_and_mechanical_separate_sockets(tmp_path):
    q=build(source(tmp_path),tmp_path/"wing")
    assert len(q["wings"])==2 and q["body_missing"]
    for info in q["wings"]:
        s=info["side"].upper()
        m=trimesh.load(tmp_path/"wing"/f"V95_{s}_SOURCE_WING_KEYED_RESIN_TRIAL.stl")
        assert m.is_watertight and m.body_count==1
        assert m.bounds[0,1]<8.0  # Male pin extends toward body (-Y).
        assert info["male_key_diameter_mm"]==3.1
        assert info["faces"]>5000
    hardware=build_receivers(tmp_path/"hardware")
    assert not hardware["real_body_merged"]
    for x in hardware["receivers"]:
        assert x["analytic_cad_valid"] and x["stl_watertight"]
        assert x["diametric_clearance_mm"]==.4
        assert (tmp_path/"hardware"/f'V95_{x["side"]}_FEMALE_RECEIVER_NOT_IN_BODY.step').stat().st_size>5000
    assert (tmp_path/"hardware"/"V95_RESIN_BORE_FIT_3p3_3p5_3p7.stl").is_file()

def test_fails_if_source_hash_tampered(tmp_path):
    p=source(tmp_path)
    with pytest.raises(ValueError,match="SHA"):
        build(p,tmp_path/"wrong",expected_sha="0"*64)
