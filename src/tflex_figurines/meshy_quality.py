"""Optional Meshy 7.1 API adapter with geometry-first quality presets.

The ChatGPT Meshy plugin is separate from using this library on a GitHub runner:
this adapter needs its own MESHY_API_KEY variable.
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import requests

from .tripo import TripoError, valid_download_url

BASE = "https://api.meshy.ai/openapi/v1"
TASK_ID = re.compile(r"^[0-9a-zA-Z-]{1,128}$")
MIMES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
MAX_IMAGE = 20_000_000
MAX_OUTPUT = 150 * 1024 * 1024


def image_data_uri(path: Path) -> str:
    from .source_images import validate_generation_image
    mime = validate_generation_image(
        path, max_bytes=MAX_IMAGE, allow_webp=True
    )
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def build_payload(image_urls: list[str], *, mode: str = "sculpt") -> tuple[str, dict]:
    """Return Meshy official endpoint and payload, no network request.

    Single-view geometry Ultra 4K; multi-view geometry Ultra 2K
    (Multi-Image API explicitly rejects 4K geometry).
    """
    if not 1 <= len(image_urls) <= 4 or not all(image_urls):
        raise ValueError("Meshy takes 1–4 nonempty image sources")
    if mode not in {"sculpt", "display", "economy"}:
        raise ValueError("mode must be sculpt, display or economy")
    multi = len(image_urls) > 1
    path = "/multi-image-to-3d" if multi else "/image-to-3d"
    payload: dict = {
        "ai_model": "meshy-7.1",
        "geometry_resolution": "standard" if mode == "economy" else "2k" if multi else "4k",
        "should_remesh": False,
        "should_texture": mode == "display",
        "target_formats": ["glb"],
    }
    if mode == "display":
        payload.update({
            "texture_model": "meshy-7",
            "texture_resolution": "8k",
            "enable_pbr": True,
        })
    payload["image_urls" if multi else "image_url"] = image_urls if multi else image_urls[0]
    return path, payload


class MeshyClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        key = api_key if api_key is not None else os.environ.get("MESHY_API_KEY", "")
        if not isinstance(key, str) or not key.strip():
            raise TripoError("MESHY_API_KEY missing (ChatGPT app credentials are not GitHub Secrets)")
        self._key = key.strip()
        self.session = session or requests.Session()

    def _call(self, method: str, endpoint: str, **kwargs) -> dict:
        try:
            reply = self.session.request(
                method, BASE + endpoint,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=30, allow_redirects=False, **kwargs,
            )
        except requests.RequestException as exc:
            raise TripoError("Meshy network/timeout error") from exc
        if not 200 <= reply.status_code < 300:
            raise TripoError(f"Meshy API returned HTTP {reply.status_code}")
        try:
            result = reply.json()
        except ValueError as exc:
            raise TripoError("Meshy returned non-JSON response") from exc
        if not isinstance(result, dict):
            raise TripoError("Meshy returned malformed response")
        return result

    def submit(self, paths: list[Path], mode: str = "sculpt") -> tuple[str, str]:
        # Validate every source BEFORE any expensive request.
        from .source_images import validate_generation_image
        for path in paths:
            validate_generation_image(path, max_bytes=MAX_IMAGE, allow_webp=True)
        sources = [image_data_uri(path) for path in paths]
        endpoint, payload = build_payload(sources, mode=mode)
        # Do not retry POST if the response is lost.
        result = self._call("POST", endpoint, json=payload)
        task = result.get("result")
        if not isinstance(task, str) or not TASK_ID.fullmatch(task):
            raise TripoError("Meshy returned invalid task ID")
        return endpoint, task

    def task(self, endpoint: str, task_id: str) -> dict:
        if endpoint not in {"/image-to-3d", "/multi-image-to-3d"}:
            raise ValueError("Unknown Meshy endpoint")
        if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
            raise ValueError("Invalid Meshy task ID")
        return self._call("GET", endpoint + "/" + task_id)

    def download(self, endpoint: str, task_id: str, dest: Path) -> Path:
        state = self.task(endpoint, task_id)
        if state.get("status") != "SUCCEEDED":
            raise TripoError("Meshy task not succeeded")
        urls = state.get("model_urls")
        url = urls.get("glb") if isinstance(urls, dict) else None
        if not isinstance(url, str):
            raise TripoError("Meshy GLB URL missing")
        valid_download_url(url)
        if dest.suffix.lower() != ".glb" or dest.exists():
            raise ValueError("Output must be a new .glb file")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".glb.part")
        if tmp.exists():
            raise ValueError("Previous partial file exists")
        try:
            try:
                reply = self.session.get(url, stream=True, timeout=30, allow_redirects=False)
            except requests.RequestException as exc:
                raise TripoError("Meshy download failed") from exc
            with reply:
                if not 200 <= reply.status_code < 300:
                    raise TripoError(f"Meshy download HTTP {reply.status_code}")
                total, header = 0, b""
                with tmp.open("xb") as f:
                    for chunk in reply.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > MAX_OUTPUT:
                            raise TripoError("Meshy GLB too large")
                        if len(header) < 4:
                            header += chunk[:4-len(header)]
                        f.write(chunk)
                    if header != b"glTF":
                        raise TripoError("Meshy output did not have GLB signature")
            tmp.replace(dest)
            return dest
        finally:
            if tmp.exists():
                tmp.unlink()
