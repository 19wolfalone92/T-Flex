"""Verifiable high-detail Tripo H3.1 presets; no API calls during planning.

Official 2026 reference:
https://developers.tripo3d.ai/en/docs/generation-multiview-to-model/standard
"""
from __future__ import annotations

from pathlib import Path

from .tripo import DEFAULT_MODEL, TripoClient, TripoError, valid_id

PROFILES = {
    "sculpt": {
        "geometry_quality": "detailed",
        "texture": False,
        "pbr": False,
    },
    "display": {
        "geometry_quality": "detailed",
        "texture": True,
        "pbr": True,
        "texture_quality": "extreme",
        "texture_version": "v3.5-20260815",
        "delight": True,
    },
    "parts": {
        "geometry_quality": "detailed",
        "texture": False,
        "pbr": False,
        "generate_parts": True,
    },
    "economy": {
        "geometry_quality": "standard",
        "texture": False,
        "pbr": False,
    },
}
VIEWS = ("front", "left", "back", "right")


def params_for_profile(
    profile: str = "sculpt",
    *,
    model_seed: int | None = None,
    image_autofix: bool = False,
    for_image: bool = False,
) -> dict:
    """Return a new payload with valid H3.1 parameter combinations."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile {profile!r}; choose {list(PROFILES)}")
    payload = {"model": DEFAULT_MODEL, **PROFILES[profile]}
    if model_seed is not None:
        if type(model_seed) is not int or not 0 <= model_seed < 2**31:
            raise ValueError("model_seed must be an integer from 0 to 2147483647")
        payload["model_seed"] = model_seed
    if for_image and image_autofix:
        payload["enable_image_autofix"] = True
    return payload


def describe_profile(profile: str) -> dict:
    data = params_for_profile(profile)
    return {
        "profile": profile,
        "request_options": data,
        "warning": (
            "Geometry quality is not proof of likeness, manifoldness, printability, "
            "minimum wall thickness, or absence of hallucinated hidden surfaces."
        ),
        "billing": "Submitting a task consumes Tripo credits; plan mode never submits.",
    }


def submit_text(
    client: TripoClient,
    prompt: str,
    *,
    profile: str = "sculpt",
    model_seed: int | None = None,
) -> str:
    if not isinstance(prompt, str) or not 0 < len(prompt.strip()) <= 1024:
        raise ValueError("Prompt must contain 1–1024 characters")
    args = params_for_profile(profile, model_seed=model_seed)
    return client._create("/generation/text-to-model", {"prompt": prompt.strip(), **args})


def submit_image(
    client: TripoClient,
    image: Path,
    *,
    profile: str = "sculpt",
    model_seed: int | None = None,
    image_autofix: bool = False,
) -> str:
    args = params_for_profile(
        profile, model_seed=model_seed, image_autofix=image_autofix, for_image=True
    )
    token = client.upload_image(image)
    return client._create("/generation/image-to-model", {"input": token, **args})


def submit_multiview(
    client: TripoClient,
    views: dict[str, Path],
    *,
    profile: str = "sculpt",
    model_seed: int | None = None,
) -> str:
    args = params_for_profile(profile, model_seed=model_seed)
    if (
        "front" not in views
        or len(views) < 2
        or len(views) > 4
        or any(name not in VIEWS for name in views)
    ):
        raise ValueError("Multiview requires front plus 1–3 of left/back/right")
    from .tripo import image_mime

    # Preflight all files BEFORE any uploads.
    for image in views.values():
        image_mime(image)
    inputs = [{view: client.upload_image(views[view])} for view in VIEWS if view in views]
    return client._create("/generation/multiview-to-model", {"inputs": inputs, **args})


def submit_generated_views(
    client: TripoClient, source_task: str, *, profile: str = "sculpt"
) -> str:
    args = params_for_profile(profile)
    return client._create(
        "/generation/multiview-to-model",
        {"inputs": [{"task_id": valid_id(source_task)}], **args},
    )


def generate_synthetic_views(client: TripoClient, image: Path) -> str:
    """Billable image-to-multiview task; generated back/sides are conjecture."""
    return client._create(
        "/generation/image-to-multiview", {"input": client.upload_image(image)}
    )
