"""Credit-safe Hi3D 3.0 console: balance, plan, submit, status, download."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .hi3d import Hi3DClient, Hi3DError, PROFILES, VIEWS, MAX_IMAGE
from .source_images import validate_generation_image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("balance", help="Read-only Hi3D authorization / resource balance")
    submit = sub.add_parser("submit", help="Plan only unless --yes-spend-credits")
    submit.add_argument("--front", type=Path, required=True)
    for name in VIEWS[1:]:
        submit.add_argument("--" + name, type=Path)
    submit.add_argument("--profile", choices=tuple(PROFILES), default="quality")
    submit.add_argument("--with-textures", action="store_true")
    submit.add_argument("--yes-spend-credits", action="store_true")
    split_cmd = sub.add_parser("split", help="Paid vendor semantic split-to-print (DRY RUN by default)")
    split_cmd.add_argument("--mesh", required=True, type=Path)
    split_cmd.add_argument("--kind", choices=("character", "general"), default="character")
    split_cmd.add_argument("--template", choices=tuple("abcdef"), default="a", help="character: a=6 parts, f=2")
    split_cmd.add_argument("--joint", choices=("pin", "ball", "dovetail", "none"), default="pin")
    split_cmd.add_argument("--no-merge", action="store_true")
    split_cmd.add_argument("--level", choices=("low", "medium", "high"), default="medium")
    split_cmd.add_argument("--yes-spend-credits", action="store_true")
    split_status = sub.add_parser("split-status", help="Check vendor split task; no spending")
    split_status.add_argument("task_id")
    split_status.add_argument("--wait", action="store_true")
    split_status.add_argument("--timeout", type=int, default=1800)
    split_download = sub.add_parser("split-download", help="Download vendor's joined multipart GLB")
    split_download.add_argument("task_id")
    split_download.add_argument("--output", type=Path, required=True)
    status = sub.add_parser("status")
    status.add_argument("task_id")
    status.add_argument("--wait", action="store_true")
    status.add_argument("--timeout", type=int, default=1800)
    download = sub.add_parser("download")
    download.add_argument("task_id")
    download.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "split":
            source = args.mesh
            if source.suffix.lower() not in (".glb", ".obj", ".stl") or not source.is_file():
                raise ValueError("Provide a real existing GLB/STL/OBJ mesh")
            if not 0 < source.stat().st_size <= 200_000_000:
                raise ValueError("Mesh must be 1 byte..200 MB")
            if not args.yes_spend_credits:
                result = {
                    "dry_run": True, "operation": "Hi3D semantic split-to-print",
                    "mesh": str(source), "kind": args.kind,
                    "template": args.template if args.kind == "character" else None,
                    "expected_character_parts": {"a": 6, "b": 5, "c": 4, "d": 4, "e": 3, "f": 2}.get(args.template) if args.kind == "character" else None,
                    "joint": args.joint if args.kind == "character" else None,
                    "merge": not args.no_merge, "level": args.level,
                    "requires_paid_credits": True,
                    "next": "Use --yes-spend-credits ONLY after checking Hi3D split cost.",
                }
            else:
                task_id = Hi3DClient().submit_split(
                    source, kind=args.kind, template=args.template,
                    joint=args.joint, merge=not args.no_merge, level=args.level
                )
                result = {"task_id": task_id, "operation": "Hi3D semantic split-to-print"}
        elif args.command == "submit":
            views = {name: getattr(args, name) for name in VIEWS if getattr(args, name) is not None}
            for source in views.values():
                validate_generation_image(source, max_bytes=MAX_IMAGE, allow_webp=True)
            request = {
                "dry_run": not args.yes_spend_credits,
                "engine": "hi3dv3.0",
                "profile": args.profile,
                "params": PROFILES[args.profile],
                "input_views": {k: str(v) for k, v in views.items()},
                "geometry_only": not args.with_textures,
                "hi3d_view_order": list(VIEWS),
                "requires_spending": True,
            }
            if args.yes_spend_credits:
                task_id = Hi3DClient().submit(
                    views, profile=args.profile, geometry_only=not args.with_textures
                )
                result = {"task_id": task_id, "engine": "hi3dv3.0", "profile": args.profile}
            else:
                result = request
        else:
            api = Hi3DClient()
            if args.command == "balance":
                # Do not print token or credentials, only nonsecret balance data.
                result = api.balance()
            elif args.command == "split-status":
                info = api.wait_split(args.task_id, timeout=args.timeout) if args.wait else api.split_task(args.task_id)
                result = {"state": info.get("state"), "task_id": info.get("task_id")}
            elif args.command == "split-download":
                result = {"model_file": str(api.download_split(args.task_id, args.output))}
            elif args.command == "status":
                info = api.wait(args.task_id, timeout=args.timeout) if args.wait else api.task(args.task_id)
                result = {"state": info.get("state"), "task_id": info.get("task_id")}
            else:
                result = {"model_file": str(api.download(args.task_id, args.output))}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, Hi3DError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
