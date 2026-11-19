"""The private source atlas must never fabricate or silently omit screenshots."""
from pathlib import Path

from PIL import Image
import pytest

from scripts.build_v6_reference_atlas import ALL_ORIGINALS,CROPS,build


def fake_originals(path):
    path.mkdir(exist_ok=True)
    for fname in ALL_ORIGINALS:
        Image.new("RGB",(1536,864),(60,90,140)).save(path/fname)


def test_all_18_real_files_needed_and_15_exact_crops(tmp_path):
    data=tmp_path/"originals"
    fake_originals(data)
    output=tmp_path/"private"
    manifest,zip_path=build(data,output,archive=True)
    assert len(manifest["originals"])==18
    assert len(manifest["views"])==15
    assert manifest["private_source_do_not_upload_public"]
    assert not manifest["artistic_master_approved"]
    assert (output/"V6_ATLAS_UNALTERED_CROPS.png").is_file()
    assert zip_path.is_file()
    for label,(filename,bbox) in CROPS.items():
        actual=Image.open(output/"TRUTH_CROPS"/(label+".png"))
        assert actual.size == (bbox[2]-bbox[0], bbox[3]-bbox[1])
    with pytest.raises(ValueError,match="empty"):
        build(data,output)


def test_missing_last_eye_closeup_rejected(tmp_path):
    data=tmp_path/"sources"
    fake_originals(data)
    (data/"1000133508.jpg").unlink()
    with pytest.raises(ValueError,match="Missing original"):
        build(data,tmp_path/"output")
