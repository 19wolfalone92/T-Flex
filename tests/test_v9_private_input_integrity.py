"""V9 private reference contract: enforce checksums and reject fake master claims."""
import hashlib,json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from scripts.v9_private_kaggle_hunyuan3d_mv import validate_refs,VIEWS

def make_refs(root):
    records=[]
    for view,filename in VIEWS.items():
        arr=np.zeros((1024,1024,4),dtype=np.uint8)
        arr[200:800,275:800,:3]=(145,155,220)
        arr[200:800,275:800,3]=255
        f=root/filename;Image.fromarray(arr).save(f)
        records.append({"view":view,"output_sha256":hashlib.sha256(f.read_bytes()).hexdigest()})
    (root/"V9_INPUT_QA.json").write_text(json.dumps({"records":records}),encoding="utf8")
    return root

def test_reference_sha_validation(tmp_path):
    assert len(validate_refs(make_refs(tmp_path)))==5

def test_rejects_missing_reference(tmp_path):
    d=make_refs(tmp_path);(d/VIEWS["left"]).unlink()
    with pytest.raises(FileNotFoundError):validate_refs(d)

def test_rejects_modified_reference(tmp_path):
    d=make_refs(tmp_path);(d/VIEWS["front"]).write_bytes(b"tampered")
    with pytest.raises(ValueError):validate_refs(d)

def test_rejects_empty_alpha(tmp_path):
    d=make_refs(tmp_path)
    p=d/VIEWS["back"];Image.new("RGBA",(1024,1024),(0,0,0,0)).save(p)
    data=json.loads((d/"V9_INPUT_QA.json").read_text())
    for r in data["records"]:
        if r["view"]=="back":r["output_sha256"]=hashlib.sha256(p.read_bytes()).hexdigest()
    (d/"V9_INPUT_QA.json").write_text(json.dumps(data))
    with pytest.raises(ValueError):validate_refs(d)
