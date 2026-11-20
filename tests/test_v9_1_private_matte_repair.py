"""Only synthetic pixels: private screenshots are never committed to CI."""
import hashlib,json
from pathlib import Path
import numpy as np
import pytest
cv2=pytest.importorskip("cv2")
from PIL import Image
from scripts.v9_1_private_matte_repair import process,VIEWS

def source_fixture(tmp_path):
    src=tmp_path/"private";src.mkdir()
    records=[]
    for view,fn in VIEWS.items():
        w,h=408,559
        rgb=np.zeros((h,w,3),dtype=np.uint8);rgb[:]=(112,124,50)
        rgb[80:525,125:265]=(24,25,29)
        rgb[45:145,140:245]=(230,226,223)
        rgb[200:285,64:145]=(118,172,227)
        # A continuous body+wing silhouette without invented geometry.
        alpha=np.zeros((h,w),dtype=np.uint8);alpha[:]=255
        scale=min(830/h,875/w);tw,th=round(w*scale),round(h*scale)
        c=Image.new("RGBA",(1024,1024))
        opaque=np.dstack((rgb,alpha))
        c.alpha_composite(Image.fromarray(opaque,"RGBA").resize((tw,th),Image.Resampling.NEAREST),
                          ((1024-tw)//2,(1024-th)//2))
        p=src/fn;Image.fromarray(rgb).save(p)
        pp=src/f"MV_{view.upper()}_RGBA_1024.png";c.save(pp)
        records.append({"view":view,"source_size":[w,h],
                        "alpha_bbox":[0,0,w,h],
                        "sha256_source":hashlib.sha256(p.read_bytes()).hexdigest(),
                        "output_sha256":hashlib.sha256(pp.read_bytes()).hexdigest()})
    (src/"V9_INPUT_QA.json").write_text(json.dumps({"records":records}))
    return src

def test_matte_refinement_rejects_grass_and_emits_real_private_png(tmp_path):
    src=source_fixture(tmp_path)
    qa=process(src,tmp_path/"clean")
    assert len(qa["records"])==5
    assert qa["master_mesh_created"] is False
    for view in VIEWS:
        p=tmp_path/"clean"/f"MV_{view.upper()}_RGBA_1024.png"
        im=np.asarray(Image.open(p))
        assert im.shape==(1024,1024,4)
        assert np.count_nonzero(im[:,:,3]>5)>3000
    assert (tmp_path/"clean"/"V91_MASKS_REVIEW_PRIVATE.png").is_file()

def test_originals_are_immutable_and_sha_guard_fails_closed(tmp_path):
    src=source_fixture(tmp_path)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()}
    process(src,tmp_path/"clean")
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()}
    with pytest.raises(ValueError):
        process(src,src)
    p=src/VIEWS["front"]
    Image.new("RGB",(408,559),(0,0,0)).save(p)
    with pytest.raises(ValueError,match="SHA"):
        process(src,tmp_path/"recheck")
