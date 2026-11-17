"""Offline Tripo v3 API contract tests (never spend credits)."""
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from tflex_figurines.tripo import TripoClient, TripoError, valid_download_url
from tflex_figurines.tripo_cli import main


def answer(data, status=200):
    obj = Mock(status_code=status)
    obj.json.return_value = {"code": 0, "data": data}
    return obj


def new_client():
    session = Mock()
    return TripoClient(api_key="test-secret", session=session), session


def test_balance_read_only():
    c, s = new_client()
    s.request.return_value = answer({"balance": 20, "frozen": 0})
    assert c.balance()["balance"] == 20
    assert s.request.call_args.args == ("GET", "https://openapi.tripo3d.ai/v3/account/balance")
    assert s.request.call_args.kwargs["headers"]["Authorization"] == "Bearer test-secret"


def test_text_generation_contract():
    c, s = new_client()
    s.request.return_value = answer({"task_id": "abc-123"})
    assert c.text_to_model("a solid statue") == "abc-123"
    assert s.request.call_args.args[1].endswith("/generation/text-to-model")
    payload = s.request.call_args.kwargs["json"]
    assert payload["model"] == "v3.1-20260211"
    assert payload["texture"] is False and payload["pbr"] is False


def test_image_upload_contract(tmp_path):
    image = tmp_path / "ref.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfile")
    c, s = new_client()
    s.request.side_effect = [answer({"file_token": "file_test"}), answer({"task_id": "task123"})]
    assert c.image_to_model(image) == "task123"
    assert s.request.call_args_list[0].args[1].endswith("/files")
    assert s.request.call_args_list[1].kwargs["json"]["input"] == "file_test"


def test_wait_and_terminal_status():
    c, s = new_client()
    s.request.side_effect = [answer({"status": "running"}), answer({"status": "success"})]
    with patch("tflex_figurines.tripo.time.sleep"):
        assert c.wait("task-1", timeout=5)["status"] == "success"
    s.request.side_effect = None
    s.request.return_value = answer({"status": "failed", "error_code": 222})
    with pytest.raises(TripoError, match="failed"):
        c.wait("task-1")


def test_model_download_and_no_overwrite(tmp_path):
    c, s = new_client()
    s.request.return_value = answer({"status": "success", "output": {"model_url": "https://cdn.tripo3d.ai/model.glb"}})
    reply = Mock(status_code=200)
    reply.iter_content.return_value = [b"glTF" + b"\x00" * 28]
    reply.__enter__ = Mock(return_value=reply)
    reply.__exit__ = Mock(return_value=False)
    s.get.return_value = reply
    target = tmp_path / "fox.glb"
    assert c.download("abc", target) == target
    assert target.read_bytes().startswith(b"glTF")
    with pytest.raises(ValueError, match="exists"):
        c.download("abc", target)
    assert s.get.call_args.kwargs["allow_redirects"] is False


def test_bad_download_cleanup_and_ssrf_guard(tmp_path):
    c, s = new_client()
    s.request.return_value = answer({"status": "success", "output": {"model_url": "https://cdn.tripo3d.ai/model.glb"}})
    reply = Mock(status_code=200)
    reply.iter_content.return_value = [b"<html>not model"]
    reply.__enter__ = Mock(return_value=reply)
    reply.__exit__ = Mock(return_value=False)
    s.get.return_value = reply
    target = tmp_path / "fox.glb"
    with pytest.raises(TripoError, match="GLB header"):
        c.download("abc", target)
    assert not target.exists()
    assert not target.with_suffix(".glb.part").exists()
    for value in ("http://cdn.tripo3d.ai/foo", "https://localhost/hi", "https://127.0.0.1/secret"):
        with pytest.raises(TripoError):
            valid_download_url(value)


def test_dry_run_blocks_spending_without_key(monkeypatch, capsys):
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    assert main(["submit-text", "--prompt", "Cute fox"]) == 0
    assert '"dry_run": true' in capsys.readouterr().out
    assert main(["submit-text", "--prompt", "Cute fox", "--yes-spend-credits"]) == 2
    assert "TRIPO_API_KEY" in capsys.readouterr().err


def test_no_secret_in_errors():
    c, s = new_client()
    s.request.return_value = answer({}, status=401)
    with pytest.raises(TripoError) as result:
        c.balance()
    assert "test-secret" not in str(result.value)
    assert "HTTP 401" in str(result.value)


def test_invalid_task_id_blocks_network():
    c, s = new_client()
    with pytest.raises(ValueError):
        c.task("../not-task")
    s.request.assert_not_called()
