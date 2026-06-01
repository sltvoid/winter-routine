#!/usr/bin/env python3
"""Normalize Codex-native MCP responses into local /tmp response files.

Shell scripts in this repo can call the HTTP MCP surface directly, but they
cannot invoke Codex-native MCP tools. When the desktop run falls back to native
tools, use this helper to write each native response to the same file contract
as scripts/mcp.sh without custom one-off Python snippets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_input(path: str | None) -> Any:
    if path:
        with open(path) as f:
            return json.load(f)
    return json.load(sys.stdin)


def _status(payload: Any) -> str:
    if isinstance(payload, dict):
        if "status" in payload:
            return str(payload.get("status"))
        if "events" in payload:
            return "ok"
    return "unknown"


def _count(payload: Any) -> int | str:
    if not isinstance(payload, dict):
        return "unknown"
    if "row_count" in payload:
        return payload.get("row_count")
    data = payload.get("data")
    if isinstance(data, list):
        return len(data)
    events = payload.get("events")
    if isinstance(events, list):
        return len(events)
    return "unknown"


def cmd_write(args: argparse.Namespace) -> int:
    payload = _load_input(args.input)
    status = _status(payload)
    if not args.allow_error and status != "ok":
        error = payload.get("error") if isinstance(payload, dict) else None
        raise SystemExit(
            f"native_mcp_files.py: {args.label} returned status={status} error={error}"
        )
    out = Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=True))
    print(
        "native_mcp_files.py: "
        f"wrote={out} label={args.label} status={status} count={_count(payload)}"
    )
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    bundle = _load_input(args.input)
    if not isinstance(bundle, dict):
        raise SystemExit("native_mcp_files.py: bundle input must be a JSON object")
    manifest = bundle.get("files")
    if not isinstance(manifest, list):
        raise SystemExit("native_mcp_files.py: bundle must contain files[]")

    written = 0
    for entry in manifest:
        if not isinstance(entry, dict):
            raise SystemExit("native_mcp_files.py: bundle files[] entries must be objects")
        label = str(entry.get("label") or "native_response")
        out = entry.get("out")
        payload = entry.get("payload")
        if not out or payload is None:
            raise SystemExit("native_mcp_files.py: each bundle entry needs out and payload")
        status = _status(payload)
        if not args.allow_error and status != "ok":
            error = payload.get("error") if isinstance(payload, dict) else None
            raise SystemExit(
                f"native_mcp_files.py: {label} returned status={status} error={error}"
            )
        Path(str(out)).write_text(json.dumps(payload, ensure_ascii=True))
        written += 1
        print(
            "native_mcp_files.py: "
            f"wrote={out} label={label} status={status} count={_count(payload)}"
        )
    print(f"native_mcp_files.py: bundle_written={written}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write")
    write.add_argument("--label", required=True)
    write.add_argument("--out", required=True)
    write.add_argument("--input", help="Read response JSON from this file instead of stdin.")
    write.add_argument("--allow-error", action="store_true")
    write.set_defaults(func=cmd_write)

    bundle = sub.add_parser("bundle")
    bundle.add_argument("--input", help="Read bundle JSON from this file instead of stdin.")
    bundle.add_argument("--allow-error", action="store_true")
    bundle.set_defaults(func=cmd_bundle)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
