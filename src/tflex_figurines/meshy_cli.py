"""Meshy API task workflow. ALL creation is dry-run without an explicit cost flag."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .meshy_quality import MIMES, MAX_IMAGE, MeshyClient, build_payload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    build = sub.add_parser("submit", help="Preview or submit image-to-3D task")
    build.add_argument("--images", type=Path, nargs="+", required=True)
    build.add_argument("--mode", choices=["sculpt", "display", "economy"], default="sculpt")
    build.add_argument("--yes-spend-credits", action="store_true")
    status = sub.add_parser("status", help="Query previous task")
    status.add_argument("--type", choices=["single", "multi"], required=True)
    status.add_argument("task_id")
    download = sub.add_parser("download", help="Download previous GLB task")
    download.add_argument("--type", choices=["single", "multi"], required=True)
    download.add_argument("task_id")
    download.add_argument("--output", type=Path, required=True)
    opts = p.parse_args(argv)
    try:
        if opts.command == "submit":
            if not 1 <= len(opts.images) <= 4:
                raise ValueError("Meshy accepts 1 to 4 views")
            for path in opts.images:
                if path.suffix.lower() not in MIMES or not path.is_file():
                    raise ValueError("Images must exist and be PNG/JPEG/WebP")
                if not 0 < path.stat().st_size <= MAX_IMAGE:
                    raise ValueError("Image must be 1 byte to 20 MB")
            endpoint, payload = build_payload(["private_input"] * len(opts.images), mode=opts.mode)
            if not opts.yes_spend_credits:
                result = {
                    "dry_run": True, "endpoint": endpoint, "mode": opts.mode,
                    "files": [str(i) for i in opts.images],
                    "parameters": {k: v for k, v in payload.items() if k not in ("image_url", "image_urls")},
                    "next": "Add --yes-spend-credits to submit a billable task.",
                }
            else:
                endpoint, task = MeshyClient().submit(opts.images, mode=opts.mode)
                result = {"task_id": task, "type": "multi" if len(opts.images) > 1 else "single",
                          "next": "Keep this ID; do not duplicate a POST on timeout."}
        else:
            endpoint = "/image-to-3d" if opts.type == "single" else "/multi-image-to-3d"
            client = MeshyClient()
            if opts.command == "status":
                state = client.task(endpoint, opts.task_id)
                result = {"status": state.get("status"), "progress": state.get("progress"),
                          "id": state.get("id")}
            else:
                result = {"model_file": str(client.download(endpoint, opts.task_id, opts.output))}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, Exception) as exc:
        # Mask underlying details rather than risking signed URL/key leaks.
        from .tripo import TripoError
        if isinstance(exc, (TripoError, ValueError, OSError)):
            print(f"Error: {exc}", file=sys.stderr)
        else:
            print(f"Error: Unexpected {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
