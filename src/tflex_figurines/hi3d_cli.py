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
    status = sub.add_parser("status")
    status.add_argument("task_id")
    status.add_argument("--wait", action="store_true")
    status.add_argument("--timeout", type=int, default=1800)
    download = sub.add_parser("download")
    download.add_argument("task_id")
    download.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "submit":
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
