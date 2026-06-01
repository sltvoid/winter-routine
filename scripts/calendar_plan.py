#!/usr/bin/env python3
"""Build a deterministic Google Calendar create plan from briefing blocks.

The Google Calendar connector still performs the write. This script keeps the
pre-write logic deterministic: parse schedule blocks, enforce the planning
horizon, skip overlaps with saved busy windows, and emit compact counts plus a
private create-argument file for the connector calls.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_CALENDAR_ID = (
    "ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6"
    "@group.calendar.google.com"
)
CANONICAL_CATEGORIES = {
    "project",
    "deep_work",
    "gym",
    "meal",
    "leisure",
    "wind_down",
    "admin",
    "interview",
    "applications",
    "engineering_rebuild",
}


def _load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def _parse_time_part(value: str) -> time:
    return datetime.strptime(value.strip(), "%I:%M %p").time()


def _parse_block_range(day: str, raw: Any, tz: ZoneInfo) -> tuple[datetime, datetime]:
    if not isinstance(raw, str) or " - " not in raw:
        raise ValueError("unparseable")
    start_raw, end_raw = raw.split(" - ", 1)
    base = datetime.fromisoformat(day).date()
    start = datetime.combine(base, _parse_time_part(start_raw), tz)
    end = datetime.combine(base, _parse_time_part(end_raw), tz)
    if end <= start:
        raise ValueError("non_positive")
    return start, end


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _event_title(activity: Any) -> str:
    text = str(activity or "Briefing block").strip()
    return text[:80]


def build_plan(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    briefing = _load_json(args.briefing)
    busy = _load_json(args.busy)
    tz = ZoneInfo(args.timezone)
    calendar_id = args.calendar_id
    day = args.date or briefing.get("date")
    if not day:
        raise SystemExit("calendar_plan.py: briefing date is required")

    horizon_start = datetime.combine(datetime.fromisoformat(day).date(), time(args.start_hour, 0), tz)
    horizon_end = datetime.combine(datetime.fromisoformat(day).date(), time(args.end_hour, 0), tz)
    publish_categories = {
        part.strip().lower()
        for part in (args.publish_categories or "").split(",")
        if part.strip()
    }

    busy_windows: list[tuple[datetime, datetime]] = []
    if busy.get("status") == "ok":
        for row in busy.get("busy_windows") or []:
            if not isinstance(row, dict):
                continue
            try:
                busy_windows.append((datetime.fromisoformat(row["start"]), datetime.fromisoformat(row["end"])))
            except (KeyError, TypeError, ValueError):
                continue

    events: list[dict[str, Any]] = []
    create_args: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    conflict_skipped: list[dict[str, Any]] = []
    past_or_started_skipped: list[dict[str, Any]] = []
    now = None
    if args.skip_started:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(tz)
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)

    blocks = briefing.get("schedule_blocks") or []
    for rank, block in enumerate(blocks, start=1):
        if not isinstance(block, dict):
            skipped.append({"rank": rank, "reason": "not_object"})
            continue
        category = str(block.get("category") or "").strip().lower()
        if category not in CANONICAL_CATEGORIES:
            skipped.append({"rank": rank, "reason": "noncanonical_category", "category": category})
            continue
        if block.get("calendar_publish") is False:
            skipped.append({"rank": rank, "reason": "calendar_publish_false", "category": category})
            continue
        if publish_categories and category not in publish_categories:
            skipped.append({"rank": rank, "reason": "category_not_published", "category": category})
            continue
        try:
            start, end = _parse_block_range(day, block.get("time_range"), tz)
        except ValueError as exc:
            skipped.append({"rank": rank, "reason": str(exc)})
            continue
        if start < horizon_start or end > horizon_end:
            skipped.append({"rank": rank, "reason": "outside_window"})
            continue
        if now is not None and start <= now:
            row = {"rank": rank, "reason": "past_or_started", "start": start.isoformat(), "end": end.isoformat()}
            skipped.append(row)
            past_or_started_skipped.append(row)
            continue
        if any(_overlaps(start, end, busy_start, busy_end) for busy_start, busy_end in busy_windows):
            conflict_skipped.append({"rank": rank, "start": start.isoformat(), "end": end.isoformat()})
            continue

        event = {
            "rank": rank,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "category": category,
            "duration_min": round((end - start).total_seconds() / 60),
            "title": _event_title(block.get("activity")),
        }
        events.append(event)
        create_args.append(
            {
                "calendar_id": calendar_id,
                "title": event["title"],
                "start_time": event["start"],
                "end_time": event["end"],
                "timezone_str": args.timezone,
                "attendees": [],
                "self_attendance": "omit",
                "add_google_meet": False,
                "description": None,
                "transparency": "opaque",
                "visibility": "private",
            }
        )

    category_counts = Counter(event["category"] for event in events)
    summary = {
        "status": "ok" if busy.get("status") == "ok" else "busy_source_failed",
        "calendar_id": calendar_id,
        "time_min": horizon_start.isoformat(),
        "time_max": horizon_end.isoformat(),
        "busy_source": busy.get("busy_source") or ("search" if busy.get("status") == "ok" else "failed"),
        "busy_window_count": busy.get("busy_window_count", len(busy_windows)),
        "candidate_count": len(events),
        "skipped": len(skipped),
        "conflict_skipped": len(conflict_skipped),
        "past_or_started_skipped": len(past_or_started_skipped),
        "category_counts": dict(sorted(category_counts.items())),
    }
    plan = {
        **summary,
        "events": events,
        "skipped_blocks": skipped,
        "conflict_skipped_blocks": conflict_skipped,
    }
    return plan, summary, create_args


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--briefing", default="/tmp/briefing.json")
    parser.add_argument("--busy", default="/tmp/calendar_busy.json")
    parser.add_argument("--calendar-id", default=DEFAULT_CALENDAR_ID)
    parser.add_argument("--timezone", default="America/Toronto")
    parser.add_argument("--date")
    parser.add_argument("--start-hour", type=int, default=7)
    parser.add_argument("--end-hour", type=int, default=22)
    parser.add_argument(
        "--publish-categories",
        help="Optional comma-separated category allowlist for calendar publication. schedule_blocks still drive steering.",
    )
    parser.add_argument(
        "--skip-started",
        action="store_true",
        help="Skip blocks whose start time is before or equal to now. Use for calendar-only repairs run after the briefing day has started.",
    )
    parser.add_argument(
        "--now",
        help="Optional ISO timestamp for --skip-started tests; defaults to current time in --timezone.",
    )
    parser.add_argument("--plan-out", default="/tmp/calendar_create_plan.json")
    parser.add_argument("--summary-out", default="/tmp/calendar_plan_summary.json")
    parser.add_argument("--create-args-out", default="/tmp/calendar_create_args_private.json")
    args = parser.parse_args()

    plan, summary, create_args = build_plan(args)
    Path(args.plan_out).write_text(json.dumps(plan, indent=2))
    Path(args.summary_out).write_text(json.dumps(summary, indent=2))
    Path(args.create_args_out).write_text(json.dumps(create_args, indent=2))
    print(
        "calendar_plan.py: "
        f"candidates={summary['candidate_count']} "
        f"skipped={summary['skipped']} "
        f"conflict_skipped={summary['conflict_skipped']} "
        f"past_or_started_skipped={summary['past_or_started_skipped']} "
        f"busy_source={summary['busy_source']}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
