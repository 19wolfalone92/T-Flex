"""Fail fast on low-quality or invalid reference photos BEFORE any billable API call."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

MIN_SIDE_PX = 256
MAX_PIXELS = 80_000_000
MIME = {".png": ("PNG", "image/png"), ".jpg": ("JPEG", "image/jpeg"),
        ".jpeg": ("JPEG", "image/jpeg"), ".webp": ("WEBP", "image/webp")}


def validate_generation_image(
    path: Path,
    *,
    max_bytes: int,
    allow_webp: bool,
    minimum_px: int = MIN_SIDE_PX,
) -> str:
    """Check file exists, is a *real* decodable image and has sufficient detail.

    Formats and minimum size are checked before uploading. We do not silently
    upscale a low-resolution image and claim that lost details were restored.
    """
    supported = MIME if allow_webp else {key: val for key, val in MIME.items() if key != ".webp"}
    expected = supported.get(path.suffix.lower())
    if expected is None or not path.is_file():
        raise ValueError("Image must exist and use one of the supported formats")
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ValueError(f"Image must be nonempty and at most {max_bytes} bytes")
    try:
        with Image.open(path) as photo:
            if photo.format != expected[0]:
                raise ValueError("Image extension does not match actual image encoding")
            w, h = photo.size
            if w * h > MAX_PIXELS:
                raise ValueError("Image resolution is too large for safe processing")
            if w < minimum_px or h < minimum_px:
                raise ValueError(
                    f"Image must be at least {minimum_px} px on both axes for quality-first generation"
                )
            photo.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("Image file is corrupted or cannot be decoded") from exc
    return expected[1]
