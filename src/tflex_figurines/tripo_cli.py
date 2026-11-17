"""Tripo figurine commands. Generation requires explicit credit-spending consent flag."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from .tripo import TripoClient, TripoError, DEFAULT_MODEL, image_mime


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("balance")
    for kind in ("text", "image"):
        cmd = sub.add_parser("submit-" + kind)
        if kind == "text":
            cmd.add_argument("--prompt", required=True)
        else:
            cmd.add_argument("--image", type=Path, required=True)
        cmd.add_argument("--model", default=DEFAULT_MODEL)
        cmd.add_argument("--texture", action="store_true")
        cmd.add_argument("--yes-spend-credits", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("task_id")
    s.add_argument("--wait", action="store_true")
    s.add_argument("--timeout", type=float, default=300)
    d = sub.add_parser("download")
    d.add_argument("task_id")
    d.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.command.startswith("submit-") and not args.yes_spend_credits:
            if args.command == "submit-image":
                image_mime(args.image)
            elif not 0 < len(args.prompt.strip()) <= 1024:
                raise ValueError("Prompt must be 1 to 1024 characters")
            result = {"dry_run": True, "model": args.model, "texture": args.texture,
                      "note": "Pass --yes-spend-credits to create an actual task."}
        else:
            client = TripoClient()
            if args.command == "balance":
                result = client.balance()
            elif args.command == "submit-text":
                result = {"task_id": client.text_to_model(args.prompt, model=args.model, texture=args.texture)}
            elif args.command == "submit-image":
                result = {"task_id": client.image_to_model(args.image, model=args.model, texture=args.texture)}
            elif args.command == "status":
                result = client.wait(args.task_id, timeout=args.timeout) if args.wait else client.task(args.task_id)
            elif args.command == "download":
                result = {"file": str(client.download(args.task_id, args.output))}
            else:
                raise AssertionError("Unrecognized command")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (TripoError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
