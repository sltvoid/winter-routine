#!/usr/bin/env python3
"""Classify bounded Google Calendar search results for morning briefing runs.

This helper keeps auth-like connector failures distinct from real calendar
conflicts. It does not emit event details; only counts and compact error state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


AUTH_MARKERS = (
    "reauth",
    "authentication",
    "authenticate",
    "auth",
    "permission",
    "scope",
    "connection requires",
)


def _load(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def _text_from_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        parts = []
        for key in ("error", "message", "text"):
            value = payload.get(key)
            if isinstance(value, str):
                parts.append(value)
        return " ".join(parts)
    if isinstance(payload, list):
        parts = []
        for item in payload:
            if isinstance(item, dict):
                value = item.get("text") or item.get("error") or item.get("message")
                if isinstance(value, str):
                    parts.append(value)
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def _classify(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return {
            "status": "ok",
            "event_count": len(payload["events"]),
            "failure_kind": "none",
            "error": None,
        }

    text = _text_from_payload(payload).strip()
    lower = text.lower()
    failure_kind = "auth" if any(marker in lower for marker in AUTH_MARKERS) else "unknown"
    return {
        "status": "failed",
        "event_count": 0,
        "failure_kind": failure_kind,
        "error": text or "calendar search did not return an events array",
    }


def summarize_search_pair(*, primary_path: str | Path, briefing_path: str | Path) -> dict[str, Any]:
    primary = _classify(_load(Path(primary_path)))
    briefing = _classify(_load(Path(briefing_path)))
    failures = [
        ("primary", primary),
        ("briefing", briefing),
    ]
    failed = [(name, result) for name, result in failures if result["status"] != "ok"]
    if failed:
        failure_kind = "auth" if any(result["failure_kind"] == "auth" for _, result in failed) else "unknown"
        errors = [
            {"calendar": name, "kind": result["failure_kind"], "error": result["error"]}
            for name, result in failed
        ]
        return {
            "status": "failed",
            "failure_kind": failure_kind,
            "retry_recommended": failure_kind == "auth",
            "recommended_action": "bounded_recheck_once" if failure_kind == "auth" else "write_failed_manifest",
            "primary_event_count": primary["event_count"],
            "briefing_event_count": briefing["event_count"],
            "errors": errors,
        }

    return {
        "status": "ok",
        "failure_kind": "none",
        "retry_recommended": False,
        "recommended_action": "continue",
        "primary_event_count": primary["event_count"],
        "briefing_event_count": briefing["event_count"],
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", required=True)
    parser.add_argument("--briefing", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()

    summary = summarize_search_pair(primary_path=args.primary, briefing_path=args.briefing)
    rendered = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n")
    print(
        "calendar_search_policy.py: "
        f"status={summary['status']} "
        f"failure_kind={summary['failure_kind']} "
        f"retry_recommended={str(summary['retry_recommended']).lower()} "
        f"recommended_action={summary['recommended_action']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
