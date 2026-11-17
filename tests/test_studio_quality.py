"""Professional studio requests and topology audits, without paid API calls."""
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest
import trimesh

from tflex_figurines.quality import audit, compare, mesh_quality_report
from tflex_figurines.studio_cli import main as tripo_studio
from tflex_figurines.meshy_cli import main as meshy_studio
from tflex_figurines.tripo import TripoClient
from tflex_figurines.tripo_quality import (
    describe_profile, generate_synthetic_views, params_for_profile,
    submit_generated_views, submit_image, submit_multiview, submit_text,
)
from tflex_figurines.meshy_quality import MeshyClient, build_payload


def ok(data):
    response = Mock(status_code=200)
    response.json.return_value = {"code": 0, "data": data}
    return response


def test_h31_sculpt_profile_is_detailed_untextured_and_adaptive():
    q = params_for_profile("sculpt")
    assert q["model"] == "v3.1-20260211"
    assert q["geometry_quality"] == "detailed"
    assert q["texture"] is False and q["pbr"] is False
    assert "face_limit" not in q
    assert "texture_quality" not in q
    assert describe_profile("sculpt")["billing"]


def test_h31_8k_display_and_parts_are_compatible():
    display = params_for_profile("display", model_seed=123)
    assert display["texture_quality"] == "extreme"
    assert display["texture_version"] == "v3.5-20260815"
    assert display["pbr"] is True and display["model_seed"] == 123
    parts = params_for_profile("parts")
    assert parts["generate_parts"] is True
    assert parts["texture"] is False and parts["pbr"] is False
    assert "texture_quality" not in parts
    with pytest.raises(ValueError):
        params_for_profile("not-a-profile")
    with pytest.raises(ValueError):
        params_for_profile("sculpt", model_seed=-2)


def test_studio_dry_run_never_uses_credits(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    assert tripo_studio(["text", "--prompt", "Detailed wolf statuette"]) == 0
    assert '"dry_run": true' in capsys.readouterr().out
    image = tmp_path / "front.png"
    image.write_bytes(b"some image bytes")
    assert tripo_studio(["image", "--image", str(image)]) == 0
    assert tripo_studio(["auto-views", "--image", str(image)]) == 0
    assert tripo_studio(["multiview", "--front", str(image)]) == 2
    assert tripo_studio(["multiview", "--front", str(image), "--back", str(image)]) == 0
    assert tripo_studio(["text", "--prompt", "Wolf", "--yes-spend-credits"]) == 2
    assert "TRIPO_API_KEY" in capsys.readouterr().err


def test_submit_text_ultra_payload():
    session = Mock()
    session.request.return_value = ok({"task_id": "task-123"})
    client = TripoClient(api_key="key", session=session)
    assert submit_text(client, "figure", profile="sculpt", model_seed=77) == "task-123"
    url = session.request.call_args.args[1]
    payload = session.request.call_args.kwargs["json"]
    assert url.endswith("/generation/text-to-model")
    assert payload["geometry_quality"] == "detailed"
    assert payload["model_seed"] == 77
    assert payload["texture"] is False


def test_tripo_multiview_uploads_in_canonical_order(tmp_path):
    session = Mock()
    session.request.side_effect = [
        ok({"file_token": "front_token"}), ok({"file_token": "left_token"}),
        ok({"file_token": "back_token"}), ok({"task_id": "task-multi"}),
    ]
    client = TripoClient(api_key="key", session=session)
    images = {}
    for view in ("front", "left", "back"):
        file = tmp_path / f"{view}.png"
        file.write_bytes(b"valid-length-placeholder")
        images[view] = file
    unordered = {"back": images["back"], "front": images["front"], "left": images["left"]}
    assert submit_multiview(client, unordered, profile="sculpt") == "task-multi"
    payload = session.request.call_args.kwargs["json"]
    assert payload["inputs"] == [
        {"front": "front_token"}, {"left": "left_token"}, {"back": "back_token"}
    ]
    assert payload["geometry_quality"] == "detailed"
    assert payload["texture"] is False
    assert session.request.call_count == 4


def test_tripo_multiview_missing_or_bad_reference_is_rejected_before_upload(tmp_path):
    session = Mock()
    client = TripoClient(api_key="key", session=session)
    front = tmp_path / "front.png"
    front.write_bytes(b"ref")
    with pytest.raises(ValueError):
        submit_multiview(client, {"front": front})
    with pytest.raises(ValueError):
        submit_multiview(client, {"front": front, "back": tmp_path / "missing.png"})
    session.request.assert_not_called()


def test_generated_view_chain_is_two_explicitly_billed_tasks(tmp_path):
    session = Mock()
    session.request.side_effect = [ok({"file_token": "front"}), ok({"task_id": "view-task"}), ok({"task_id": "3d-task"})]
    client = TripoClient(api_key="key", session=session)
    front = tmp_path / "front.png"
    front.write_bytes(b"abc")
    assert generate_synthetic_views(client, front) == "view-task"
    assert submit_generated_views(client, "view-task", profile="display") == "3d-task"
    first_task = session.request.call_args_list[1]
    second_task = session.request.call_args_list[2]
    assert first_task.args[1].endswith("/generation/image-to-multiview")
    assert second_task.args[1].endswith("/generation/multiview-to-model")
    assert second_task.kwargs["json"]["inputs"] == [{"task_id": "view-task"}]


def test_meshy_single_max_and_multiview_do_not_use_unsupported_4k():
    endpoint, data = build_payload(["data:image/png;base64,AA=="], mode="sculpt")
    assert endpoint == "/image-to-3d" and data["geometry_resolution"] == "4k"
    assert data["ai_model"] == "meshy-7.1" and data["should_remesh"] is False
    path, payload = build_payload(["front", "back", "left"], mode="sculpt")
    assert path == "/multi-image-to-3d"
    assert payload["geometry_resolution"] == "2k"
    assert payload["image_urls"][0] == "front"
    path, display = build_payload(["front", "back"], mode="display")
    assert display["texture_resolution"] == "8k"
    assert display["texture_model"] == "meshy-7"
    assert display["enable_pbr"] is True
    with pytest.raises(ValueError):
        build_payload(["1", "2", "3", "4", "5"])


def test_meshy_submit_preserves_order_and_credit_guard(tmp_path, monkeypatch, capsys):
    files = []
    for name in ["front.png", "back.png"]:
        f = tmp_path / name
        f.write_bytes(b"fake-png-content")
        files.append(f)
    monkeypatch.delenv("MESHY_API_KEY", raising=False)
    assert meshy_studio(["submit", "--images", *map(str, files)]) == 0
    assert '"dry_run": true' in capsys.readouterr().out
    assert meshy_studio(["submit", "--images", *map(str, files), "--yes-spend-credits"]) == 2
    assert "MESHY_API_KEY" in capsys.readouterr().err
    session = Mock()
    session.request.return_value = Mock(status_code=200, json=lambda: {"result": "0101-abc"})
    client = MeshyClient(api_key="key", session=session)
    endpoint, id = client.submit(files)
    assert endpoint == "/multi-image-to-3d" and id == "0101-abc"
    payload = session.request.call_args.kwargs["json"]
    assert payload["geometry_resolution"] == "2k"
    assert payload["image_urls"][0].startswith("data:image/png;base64,")


def test_audit_closed_box_and_open_triangles(tmp_path):
    box = trimesh.creation.box(extents=(10, 10, 20))
    box_file = tmp_path / "box.stl"
    box.export(box_file)
    result = audit(box_file)
    assert result["watertight"] is True
    assert result["topology_gate"] is True
    assert result["verified_print_ready"] is False
    assert result["separate_shells"] == 1

    triangle = trimesh.Trimesh(
        vertices=[[0, 0, 0], [5, 0, 0], [0, 0, 4]],
        faces=[[0, 1, 2]],
        process=False,
    )
    triangle_file = tmp_path / "open.stl"
    triangle.export(triangle_file)
    bad = audit(triangle_file)
    assert bad["topology_gate"] is False
    assert bad["watertight"] is False
    comp = compare([box_file, triangle_file])
    assert comp["topology_pass_count"] == 1


def test_audit_multiple_shells_is_flagged():
    a = trimesh.creation.box(extents=(1, 1, 1))
    b = trimesh.creation.box(extents=(1, 1, 1))
    b.apply_translation([9, 0, 0])
    combined = trimesh.util.concatenate([a, b])
    result = mesh_quality_report(combined)
    assert result["separate_shells"] == 2
    assert result["topology_gate"] is False
    assert any("separate shells" in s for s in result["needs_review"])
