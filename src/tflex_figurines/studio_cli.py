"""Professional figurine planning and credit-guarded Tripo execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .tripo import TripoClient, TripoError, image_mime, valid_id
from .tripo_quality import (
    PROFILES, VIEWS, describe_profile, generate_synthetic_views, params_for_profile,
    submit_generated_views, submit_image, submit_multiview, submit_text,
)


def _parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("profiles", help="Read-only verified 2026 H3.1 profiles")
    sub.add_parser("balance", help="Read-only Tripo API account check")
    for name in ("text", "image", "multiview", "auto-views", "from-views-task"):
        command = sub.add_parser(name, help="DRY RUN unless --yes-spend-credits")
        command.add_argument("--yes-spend-credits", action="store_true")
        command.add_argument("--profile", choices=tuple(PROFILES), default="sculpt")
        if name == "text":
            command.add_argument("--prompt", required=True)
            command.add_argument("--seed", type=int)
        elif name == "image":
            command.add_argument("--image", type=Path, required=True)
            command.add_argument("--seed", type=int)
            command.add_argument("--autofix-image", action="store_true")
        elif name == "multiview":
            command.add_argument("--front", type=Path, required=True)
            for v in VIEWS[1:]:
                command.add_argument(f"--{v}", type=Path)
            command.add_argument("--seed", type=int)
        elif name == "auto-views":
            command.add_argument("--image", type=Path, required=True)
        elif name == "from-views-task":
            command.add_argument("--task-id", required=True)
    status = sub.add_parser("status", help="Check an existing task (no generation)")
    status.add_argument("task_id")
    status.add_argument("--wait", action="store_true")
    status.add_argument("--timeout", type=int, default=600)
    download = sub.add_parser("download", help="Download GLB of completed task")
    download.add_argument("task_id")
    download.add_argument("--output", type=Path, required=True)
    return root


def _preflight(args) -> dict:
    summary = {"mode": args.command, "requires_explicit_credit_authorization": True}
    if args.command == "text":
        if not 0 < len(args.prompt.strip()) <= 1024:
            raise ValueError("Prompt must contain 1–1024 characters")
        summary["prompt"] = args.prompt.strip()
    elif args.command == "image":
        image_mime(args.image)
        summary["image"] = str(args.image)
        summary["autofix_image"] = args.autofix_image
    elif args.command == "auto-views":
        image_mime(args.image)
        summary["image"] = str(args.image)
        summary["caveat"] = "Synthetic rear and side views can invent unseen details."
    elif args.command == "multiview":
        views = {v: getattr(args, v) for v in VIEWS if getattr(args, v) is not None}
        if len(views) < 2:
            raise ValueError("Provide front plus at least one other view")
        for image in views.values():
            image_mime(image)
        summary["views"] = {k: str(v) for k, v in views.items()}
    elif args.command == "from-views-task":
        valid_id(args.task_id)
        summary["views_task"] = args.task_id
    if args.command not in ("auto-views",):
        summary["quality"] = describe_profile(args.profile)
    else:
        summary["quality"] = "Tripo generated multi-view references, not a 3D model"
    if hasattr(args, "seed"):
        # Validate before sending, including when dry running.
        params_for_profile(args.profile, model_seed=args.seed)
        summary["seed"] = args.seed
    return summary


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "profiles":
            result = {profile: describe_profile(profile) for profile in PROFILES}
        elif args.command in ("text", "image", "multiview", "auto-views", "from-views-task"):
            plan = _preflight(args)
            if not args.yes_spend_credits:
                result = {"dry_run": True, **plan, "next": "Add --yes-spend-credits to pay for generation."}
            else:
                client = TripoClient()
                if args.command == "text":
                    task_id = submit_text(client, args.prompt, profile=args.profile, model_seed=args.seed)
                elif args.command == "image":
                    task_id = submit_image(client, args.image, profile=args.profile,
                                           model_seed=args.seed, image_autofix=args.autofix_image)
                elif args.command == "multiview":
                    views = {k: getattr(args, k) for k in VIEWS if getattr(args, k) is not None}
                    task_id = submit_multiview(client, views, profile=args.profile, model_seed=args.seed)
                elif args.command == "auto-views":
                    task_id = generate_synthetic_views(client, args.image)
                else:
                    task_id = submit_generated_views(client, args.task_id, profile=args.profile)
                result = {"task_id": task_id, "mode": args.command,
                          "next": "Save task_id; poll status. Do not submit again on timeout."}
        else:
            client = TripoClient()
            if args.command == "balance":
                result = client.balance()
            elif args.command == "status":
                result = client.wait(args.task_id, timeout=args.timeout) if args.wait else client.task(args.task_id)
            else:
                result = {"model_file": str(client.download(args.task_id, args.output))}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, TripoError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
