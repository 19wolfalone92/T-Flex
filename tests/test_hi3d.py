"""Mocked Hi3D API contract. No network, no credit-consuming operations."""
from pathlib import Path
from unittest.mock import Mock
from PIL import Image
import pytest

from tflex_figurines.hi3d import Hi3DClient, Hi3DError
from tflex_figurines.hi3d_cli import main


def response(data, code=200):
    reply = Mock(status_code=200)
    reply.json.return_value = {"code": code, "msg": "success", "data": data}
    return reply


def fake_png(p):
    Image.new("RGB", (512, 512), (120, 140, 180)).save(p)


def test_basic_credentials_token_are_not_printed():
    session = Mock()
    session.request.side_effect = [
        response({"accessToken": "a-secret-session-token-long-enough"}),
        response({"totalBalance": 14.0})
    ]
    api = Hi3DClient("ACCESS", "SECRET", session=session)
    assert api.balance() == {"totalBalance": 14.0}
    auth = session.request.call_args_list[0]
    assert auth.args == ("POST", "https://api.hitem3d.ai/open-api/v1/auth/token")
    assert auth.kwargs["auth"] == ("ACCESS", "SECRET")
    assert "Authorization" not in auth.kwargs["headers"]
    assert session.request.call_args_list[1].kwargs["headers"]["Authorization"].startswith("Bearer ")
    assert session.request.call_args_list[1].args[1].endswith("/balance")


def test_single_view_master_and_task_endpoint(tmp_path):
    image = tmp_path / "front.png"
    fake_png(image)
    session = Mock()
    session.request.side_effect = [
        response({"accessToken": "a-secret-session-token-long-enough"}),
        response({"task_id": "ghi123.abc-321"}),
        response({"state": "success", "task_id": "ghi123.abc-321"})
    ]
    api = Hi3DClient("AK", "SK", session=session)
    assert api.submit({"front": image}, profile="master") == "ghi123.abc-321"
    submit = session.request.call_args_list[1]
    assert submit.args[1].endswith("/submit-task")
    assert submit.kwargs["data"]["request_type"] == "1"
    assert submit.kwargs["data"]["resolution"] == "2048master"
    assert submit.kwargs["data"]["face"] == "5000000"
    assert submit.kwargs["data"]["format"] == "2"
    assert len(submit.kwargs["files"]) == 1
    assert api.task("ghi123.abc-321")["state"] == "success"


def test_multiview_bit_order_front_back_left_right(tmp_path):
    views = {}
    for view in ("left", "front", "right"):
        path = tmp_path / (view + ".png")
        fake_png(path)
        views[view] = path
    session = Mock()
    session.request.side_effect = [
        response({"accessToken": "a-secret-session-token-long-enough"}),
        response({"task_id": "hi-task"})
    ]
    api = Hi3DClient("A", "B", session=session)
    assert api.submit(views) == "hi-task"
    call = session.request.call_args_list[1]
    assert call.kwargs["data"]["multi_images_bit"] == "1011"
    assert [f[1][0] for f in call.kwargs["files"]] == ["front.png", "left.png", "right.png"]


def test_reject_invalid_and_missing_sources_without_auth_or_expense(tmp_path):
    s = Mock()
    c = Hi3DClient("AK", "SK", session=s)
    image = tmp_path / "bad.png"
    image.write_bytes(b"not a real image")
    with pytest.raises(ValueError):
        c.submit({"front": image})
    with pytest.raises(ValueError):
        c.submit({"back": image})
    with pytest.raises(ValueError):
        c.submit({"front": image}, profile="nonsense")
    s.request.assert_not_called()


def test_dry_run_requires_no_credentials(tmp_path, monkeypatch, capsys):
    source = tmp_path / "front.png"
    fake_png(source)
    monkeypatch.delenv("HI3D_ACCESS_KEY", raising=False)
    monkeypatch.delenv("HI3D_SECRET_KEY", raising=False)
    assert main(["submit", "--front", str(source)]) == 0
    assert '"dry_run": true' in capsys.readouterr().out
    assert main(["submit", "--front", str(source), "--yes-spend-credits"]) == 2
    assert "HI3D_ACCESS_KEY" in capsys.readouterr().err


def test_api_errors_no_key_echo():
    c = Hi3DClient("TOP-SECRET-ACCESS", "TOP-SECRET-SK", session=Mock())
    c.session.request.return_value = response({}, 40010000)
    with pytest.raises(Hi3DError) as err:
        c.balance()
    assert "TOP-SECRET" not in str(err.value)


def test_invalid_task_does_not_contact_network():
    c = Hi3DClient("AK", "SK", session=Mock())
    with pytest.raises(ValueError):
        c.task("../etc/passwd")
    c.session.request.assert_not_called()
