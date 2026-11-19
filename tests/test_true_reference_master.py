"""Guardrail tests for the only candidate workflow that uses the game's views."""
import json
from pathlib import Path
from PIL import Image
import pytest
from scripts.reconstruct_true_4view_master import validate_input, main


def test_real_image_preflight_is_network_free(tmp_path, monkeypatch, capsys):
    src = {}
    for name in ("front", "back", "left", "right"):
        p = tmp_path / (name + ".png")
        Image.new("RGB", (320, 500), (30, 50, 90)).save(p)
        src[name] = p
    monkeypatch.delenv("HF_TOKEN", raising=False)
    output = tmp_path / "candidate"
    argv = []
    for name,p in src.items():
        argv.extend(["--"+name, str(p)])
    argv.extend(["--output-dir", str(output)])
    assert main(argv) == 0
    meta = json.loads((output/"reference_manifest.json").read_text())
    assert meta["mode"] == "readonly_preflight"
    assert len(meta["input"]) == 4
    assert meta["likeness_approved"] is False
    assert meta["print_ready_certified"] is False
    assert len(list(output.glob("*.stl"))) == 0
    assert "ZERO external AI calls" in capsys.readouterr().out


def test_invalid_fake_reference_cannot_generate(tmp_path):
    bad = tmp_path/"fake.png"
    bad.write_bytes(b"not-an-image")
    with pytest.raises(Exception):
        validate_input(bad)


def test_small_image_rejected(tmp_path):
    tiny = tmp_path/"tiny.png"
    Image.new("RGB", (60, 90), "white").save(tiny)
    with pytest.raises(ValueError, match="too small"):
        validate_input(tiny)
