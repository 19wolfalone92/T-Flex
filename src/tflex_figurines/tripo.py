"""Tripo API v3 client. Submission may consume credits; other methods are read-only."""
from __future__ import annotations

import ipaddress
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE_URL = "https://openapi.tripo3d.ai/v3"
DEFAULT_MODEL = "v3.1-20260211"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_MODEL_BYTES = 150 * 1024 * 1024
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
FAILED = {"failed", "cancelled", "banned", "expired"}


class TripoError(RuntimeError):
    """An error without sensitive authorization or signed URL details."""


def valid_id(value: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError("Invalid task ID")
    return value


def image_mime(path: Path) -> str:
    from .source_images import validate_generation_image
    return validate_generation_image(
        path, max_bytes=MAX_IMAGE_BYTES, allow_webp=False
    )


def valid_download_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise TripoError("Model URL must use HTTPS without embedded credentials")
    if host.lower() in {"localhost", "metadata.google.internal"} or host.lower().endswith((".local", ".localhost", ".internal")):
        raise TripoError("Local model URL rejected")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return url
    raise TripoError("IP-literal model URL rejected")


class TripoClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        key = api_key if api_key is not None else os.environ.get("TRIPO_API_KEY", "")
        if not isinstance(key, str) or not key.strip():
            raise TripoError("TRIPO_API_KEY is missing; use a local environment variable or GitHub Secret")
        self._key = key.strip()
        self.session = session or requests.Session()

    def _api(self, method: str, path: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self._key}"}
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        try:
            resp = self.session.request(method, BASE_URL + path, headers=headers, timeout=30, allow_redirects=False, **kwargs)
        except requests.RequestException as exc:
            raise TripoError("Tripo request failed (network or timeout)") from exc
        if not 200 <= resp.status_code < 300:
            raise TripoError(f"Tripo API returned HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise TripoError("Tripo returned invalid JSON") from exc
        if not isinstance(body, dict) or body.get("code") != 0 or not isinstance(body.get("data"), dict):
            raise TripoError(f"Tripo returned error code {body.get('code', 'invalid') if isinstance(body, dict) else 'invalid'}")
        return body["data"]

    def balance(self) -> dict:
        return self._api("GET", "/account/balance")

    def upload_image(self, path: Path) -> str:
        mime = image_mime(path)
        with path.open("rb") as stream:
            data = self._api("POST", "/files", files={"file": (path.name, stream, mime)})
        token = data.get("file_token")
        if not isinstance(token, str) or not token:
            raise TripoError("Upload returned no file token")
        return token

    def _create(self, endpoint: str, payload: dict) -> str:
        # Never retry an uncertain POST: it could duplicate a billed task.
        result = self._api("POST", endpoint, json=payload)
        return valid_id(result.get("task_id"))

    def text_to_model(self, prompt: str, *, model: str = DEFAULT_MODEL, texture: bool = False) -> str:
        if not isinstance(prompt, str) or not 0 < len(prompt.strip()) <= 1024:
            raise ValueError("Prompt must be 1 to 1024 characters")
        if not isinstance(model, str) or not 0 < len(model) <= 80:
            raise ValueError("Invalid model")
        return self._create("/generation/text-to-model", {"prompt": prompt.strip(), "model": model, "texture": texture, "pbr": texture})

    def image_to_model(self, image: Path, *, model: str = DEFAULT_MODEL, texture: bool = False) -> str:
        image_mime(image)
        if not isinstance(model, str) or not 0 < len(model) <= 80:
            raise ValueError("Invalid model")
        file_token = self.upload_image(image)
        return self._create("/generation/image-to-model", {"input": file_token, "model": model, "texture": texture, "pbr": texture})

    def task(self, task_id: str) -> dict:
        return self._api("GET", "/tasks/" + valid_id(task_id))

    def wait(self, task_id: str, timeout: float = 300, interval: float = 3) -> dict:
        if timeout <= 0 or interval <= 0:
            raise ValueError("Polling timeout and interval must be positive")
        end = time.monotonic() + timeout
        while True:
            data = self.task(task_id)
            status = data.get("status")
            if status == "success":
                return data
            if status in FAILED:
                raise TripoError(f"Task ended with {status}; error code {data.get('error_code', 'unknown')}")
            if time.monotonic() >= end:
                raise TripoError("Polling timed out; resume using task ID")
            time.sleep(min(interval, max(0.01, end - time.monotonic())))

    def download(self, task_id: str, path: Path) -> Path:
        data = self.task(task_id)
        if data.get("status") != "success":
            raise TripoError("Task not finished: check status first")
        output = data.get("output")
        url = output.get("model_url") if isinstance(output, dict) else None
        if not isinstance(url, str):
            raise TripoError("Task output missing model_url")
        valid_download_url(url)
        if path.suffix.lower() != ".glb":
            raise ValueError("Output path must end in .glb")
        if path.exists():
            raise ValueError("Output already exists; refusing overwrite")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".glb.part")
        if tmp.exists():
            raise ValueError("Partial download exists")
        try:
            try:
                resp = self.session.get(url, timeout=30, stream=True, allow_redirects=False)
            except requests.RequestException as exc:
                raise TripoError("GLB download failed (network or timeout)") from exc
            with resp:
                if not 200 <= resp.status_code < 300:
                    raise TripoError(f"GLB download returned HTTP {resp.status_code}")
                total = 0
                header = b""
                with tmp.open("xb") as file:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > MAX_MODEL_BYTES:
                            raise TripoError("GLB larger than 150 MiB")
                        if len(header) < 4:
                            header += chunk[:4 - len(header)]
                        file.write(chunk)
                    if header != b"glTF":
                        raise TripoError("Not a valid GLB header")
            tmp.replace(path)
            return path
        finally:
            if tmp.exists():
                tmp.unlink()
