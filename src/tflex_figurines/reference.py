"""Reference-image QA before credit-consuming 3D generation.

Measures measurable image problems only; cannot determine same-character identity
or whether synthetic rear views faithfully represent a real subject.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .cli import write_json

VALID_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_PIXELS = 80_000_000
MAX_BYTES = 20_000_000


def image_report(path: Path) -> dict:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError(f"Missing, empty or oversized reference: {path} (max 20 MB)")
    try:
        with Image.open(path) as raw:
            if raw.format not in VALID_FORMATS:
                raise ValueError("Only PNG, JPEG, WEBP references are supported")
            if raw.width * raw.height > MAX_PIXELS:
                raise ValueError("Image exceeds safe pixel budget")
            photo = ImageOps.exif_transpose(raw).convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Unable to decode reference {path.name}") from exc
    width, height = photo.size
    downsampled = photo.convert("RGB")
    downsampled.thumbnail((512, 512))
    grayscale = np.asarray(downsampled.convert("L"), dtype=np.float32)
    contrast = float(grayscale.std())
    exposure_low = float((grayscale <= 3).mean())
    exposure_high = float((grayscale >= 252).mean())
    laplacian = (
        4 * grayscale[1:-1, 1:-1]
        - grayscale[1:-1, :-2]
        - grayscale[1:-1, 2:]
        - grayscale[:-2, 1:-1]
        - grayscale[2:, 1:-1]
    )
    focus_indicator = float(np.var(laplacian)) if laplacian.size else 0.0
    alpha = np.asarray(photo.getchannel("A"))
    has_transparency = bool(np.min(alpha) != 255)
    alpha_bbox = photo.getchannel("A").getbbox()
    warnings = []
    if width < 256 or height < 256:
        warnings.append("Resolution below Tripo recommended minimum 256x256")
    if exposure_low > 0.35 or exposure_high > 0.35:
        warnings.append("Large clipped dark or light areas; inspect background vs subject")
    if contrast < 15:
        warnings.append("Very low image contrast")
    if focus_indicator < 20:
        warnings.append("Weak high-frequency detail: inspect possible blur (heuristic only)")
    if has_transparency and alpha_bbox:
        l, t, r, b = alpha_bbox
        if l == 0 or t == 0 or r == width or b == height:
            warnings.append("Transparent subject touches frame edge: check for cropped parts")
    return {
        "source": str(path),
        "resolution": [width, height],
        "aspect_ratio": round(width / max(height, 1), 4),
        "format_valid": True,
        "contrast_std": round(contrast, 2),
        "focus_indicator_not_absolute_score": round(focus_indicator, 2),
        "clipped_dark_fraction": round(exposure_low, 4),
        "clipped_light_fraction": round(exposure_high, 4),
        "transparency": has_transparency,
        "warnings": warnings,
        "caveat": "No automated image metric certifies resemblance, pose consistency or true hidden viewpoints.",
    }


def multiview_report(views: dict[str, Path]) -> dict:
    if "front" not in views or not 1 <= len(views) <= 4:
        raise ValueError("Front reference required; maximum four views")
    from .tripo_quality import VIEWS

    if any(v not in VIEWS for v in views):
        raise ValueError("Unknown view label")
    reports = {name: image_report(views[name]) for name in VIEWS if name in views}
    warnings = []
    if len(reports) >= 2:
        ratios = [r["aspect_ratio"] for r in reports.values()]
        if max(ratios) - min(ratios) > 0.15:
            warnings.append("Image aspect ratios vary; align framing/camera views")
    warnings.append("Check same identity, proportions, lighting, neutral background and actual view direction manually")
    return {"views": reports, "global_warnings": warnings, "ready_for_visual_review": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--front", required=True, type=Path)
    for name in ("left", "back", "right"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    views = {name: getattr(args, name) for name in ("front", "left", "back", "right")
             if getattr(args, name) is not None}
    try:
        result = multiview_report(views)
        if args.report:
            write_json(args.report, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
