"""Synthetic-only silhouette QA regression, never download private user screenshots."""
import hashlib,json
from pathlib import Path
import numpy as np,pytest
from PIL import Image,ImageDraw

pytest.importorskip("cv2")
from scripts.v9_silhouette_qa import SOURCE,measure,compare

def test_alignment_and_different_geometry():
    a=Image.new("L",(1024,1024),0);d=ImageDraw.Draw(a)
    d.ellipse((355,97,670,926),fill=255)
    arr=np.asarray(a)
    exact=Image.new("RGB",(1000,1200),(212,217,227))
    d=ImageDraw.Draw(exact);d.ellipse((345,200,655,1000),fill=(40,45,80))
    result,_=measure(arr,exact)
    assert result["silhouette_iou"]>.95
    bad=Image.new("RGB",(1000,1200),(212,217,227))
    d=ImageDraw.Draw(bad);d.ellipse((180,200,820,1000),fill=(40,45,80))
    wrong,_=measure(arr,bad)
    assert wrong["silhouette_iou"]<.55

def test_full_private_sha_contract_and_fail_closed(tmp_path):
    refs=tmp_path/"private";refs.mkdir()
    images=tmp_path/"renders";images.mkdir()
    records=[]
    for view,name in SOURCE.items():
        original=Image.new("RGBA",(1024,1024))
        d=ImageDraw.Draw(original);d.ellipse((350,97,674,926),fill=(30,50,90,255))
        p=refs/name;original.save(p)
        records.append({"view":("three_quarter" if view=="3Q" else view.lower()),
                        "output_sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
        render=Image.new("RGB",(1000,1200),(212,217,227))
        d=ImageDraw.Draw(render);d.ellipse((340,200,660,1000),fill=(30,50,90))
        render.save(images/("TEST_"+view+"_RENDER.png"))
    (refs/"V9_INPUT_QA.json").write_text(json.dumps({"records":records}))
    result=compare(refs,images,tmp_path/"qa","TEST")
    assert all(result[k]["silhouette_iou"]>.95 for k in SOURCE)
    assert not result["automated_art_approved"] and not result["print_ready_certified"]
    assert (tmp_path/"qa"/"V9_PRIVATE_FIVE_VIEW_SILHOUETTE_COMPARISON.png").exists()
    (refs/SOURCE["FRONT"]).write_bytes(b"modified")
    with pytest.raises(ValueError,match="hash"):
        compare(refs,images,tmp_path/"qa2","TEST")
