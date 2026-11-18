"""Hi3D semantic split contract and independent STL component export."""
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
import trimesh

from tflex_figurines.hi3d import Hi3DClient
from tflex_figurines.hi3d_cli import main as hi3d_main
from tflex_figurines.parts import extract


def result(data):
    reply = Mock(status_code=200)
    reply.json.return_value = {"code": 200, "data": data, "msg": "success"}
    return reply


def test_character_split_sends_pin_joint_and_template(tmp_path):
    mesh = tmp_path/"sample.glb"
    mesh.write_bytes(b"fake model bytes for request-body contract")
    session = Mock()
    session.request.side_effect = [
        result({"accessToken": "this-is-an-extended-test-token"}),
        result({"task_id": "split_task-23"}),
        result({"task_id": "split_task-23", "state": "success", "url": "https://cdn.example.com/model.glb"}),
    ]
    api = Hi3DClient("access", "secret", session=session)
    assert api.submit_split(mesh, template="a", joint="pin", merge=True) == "split_task-23"
    r = session.request.call_args_list[1]
    assert r.args[1].endswith("/split/create-task")
    assert r.kwargs["data"] == {
        "model": "character", "format": "2", "part": "a", "joint": "pin", "merge": "yes"
    }
    assert "files" in r.kwargs
    assert api.split_task("split_task-23")["state"] == "success"
    q = session.request.call_args_list[2]
    assert q.args[1].endswith("/split/query-task")
    assert q.kwargs["headers"]["Authorization"] == "Token this-is-an-extended-test-token"


def test_general_split_and_preflight_no_cost(tmp_path):
    mesh = tmp_path/"mesh.stl"
    mesh.write_bytes(b"some bytes")
    session = Mock()
    session.request.side_effect = [
        result({"accessToken": "this-is-an-extended-test-token"}),
        result({"task_id": "split_ok"}),
    ]
    api = Hi3DClient("access", "secret", session=session)
    assert api.submit_split(mesh, kind="general", level="high") == "split_ok"
    assert session.request.call_args_list[1].kwargs["data"] == {
        "model": "general", "format": "2", "level": "high"
    }
    session.request.reset_mock()
    with pytest.raises(ValueError):
        api.submit_split(tmp_path/"missing.glb")
    session.request.assert_not_called()


def test_vendor_split_dry_run_without_credentials(tmp_path, monkeypatch, capsys):
    mesh = tmp_path/"mesh.glb"
    mesh.write_bytes(b"geometry-identifier-mock")
    monkeypatch.delenv("HI3D_ACCESS_KEY", raising=False)
    monkeypatch.delenv("HI3D_SECRET_KEY", raising=False)
    assert hi3d_main(["split", "--mesh", str(mesh), "--template", "a"]) == 0
    assert '"dry_run": true' in capsys.readouterr().out
    assert hi3d_main(["split", "--mesh", str(mesh), "--yes-spend-credits"]) == 2


def test_extract_two_named_parts_keeps_cad_alignment_and_print_z0(tmp_path):
    scene = trimesh.Scene()
    box1 = trimesh.creation.box(extents=(10, 8, 10))
    box2 = trimesh.creation.box(extents=(6, 6, 15))
    box1.apply_translation([0, 0, 0])
    box2.apply_translation([0, 0, 15])
    scene.add_geometry(box1, node_name="bottom", geom_name="box_bottom")
    scene.add_geometry(box2, node_name="top", geom_name="box_top")
    source = tmp_path/"semantic.glb"
    scene.export(file_obj=str(source))
    result = extract(source, tmp_path/"exported", height_mm=120)
    assert len(result["parts"]) == 2
    assert result["print_ready_certified"] is False
    for part in result["parts"]:
        a = trimesh.load(tmp_path/"exported"/part["assembly"], force="mesh")
        p = trimesh.load(tmp_path/"exported"/part["print"], force="mesh")
        assert a.is_watertight and p.is_watertight
        assert a.volume > 0 and p.volume > 0
        assert abs(float(p.bounds[0][2])) < 1e-4
    assert (tmp_path/"exported/parts.csv").is_file()


def test_extract_rejects_single_part(tmp_path):
    scene = trimesh.Scene(trimesh.creation.box())
    src = tmp_path/"one.glb"
    scene.export(file_obj=str(src))
    with pytest.raises(ValueError, match="2..64"):
        extract(src, tmp_path/"failed", height_mm=120)
