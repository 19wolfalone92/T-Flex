"""Reference QA and review contact sheet are offline and credit-free."""
from pathlib import Path

from PIL import Image

from tflex_figurines.reference import image_report, multiview_report
from tflex_figurines.contact_sheet import make_sheet


def test_reference_reports_resolution_and_transparency(tmp_path: Path):
    good = tmp_path / "good.png"
    img = Image.new("RGBA", (512, 512), (240, 220, 210, 255))
    img.save(good)
    r = image_report(good)
    assert r["resolution"] == [512, 512]
    assert r["format_valid"] is True
    small = tmp_path / "small.png"
    Image.new("RGB", (128, 120)).save(small)
    r = image_report(small)
    assert "256x256" in " ".join(r["warnings"])


def test_multiview_checks_ratios_and_names(tmp_path: Path):
    a, b = tmp_path / "front.png", tmp_path / "back.png"
    Image.new("RGB", (300, 300)).save(a)
    Image.new("RGB", (350, 600)).save(b)
    result = multiview_report({"front": a, "back": b})
    assert len(result["views"]) == 2
    assert any("aspect ratios" in w for w in result["global_warnings"])


def test_contact_sheet_4views(tmp_path: Path):
    for name in ("front", "back", "left", "right"):
        Image.new("RGB", (70, 70), (120, 130, 150)).save(tmp_path / (name + ".png"))
    dest = tmp_path / "comparison.png"
    make_sheet(tmp_path, dest, tile=128)
    with Image.open(dest) as pic:
        assert pic.size == (256, 352)
