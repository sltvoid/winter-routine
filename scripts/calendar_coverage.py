#!/usr/bin/env python3
"""Compare briefing schedule blocks with target Google Calendar search results.

The morning repair/watchdog flow needs a deterministic no-op gate: create only
blocks that are missing from the briefing calendar, and do not duplicate blocks
that already exist. This helper persists compact counts plus private create
arguments for missing blocks.
"""
from __future__ import annotations

import argparse
import json
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


def _load_json(path: str | Path) -> Any:
    with Path(path).open() as f:
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


def _event_title(activity: Any) -> str:
    text = str(activity or "Briefing block").strip()
    return text[:80]


def _iso(value: str) -> str:
    return datetime.fromisoformat(value).isoformat()


def _event_key(event: dict[str, Any]) -> tuple[str, str, str] | None:
    title = event.get("summary") or event.get("display_title")
    start = event.get("start")
    end = event.get("end")
    if not isinstance(title, str) or not isinstance(start, str) or not isinstance(end, str):
        return None
    try:
        return title[:80], _iso(start), _iso(end)
    except ValueError:
        return None


def _block_key(block: dict[str, Any], *, day: str, tz: ZoneInfo) -> tuple[str, str, str]:
    start, end = _parse_block_range(day, block.get("time_range"), tz)
    return _event_title(block.get("activity")), start.isoformat(), end.isoformat()


def _valid_blocks(
    briefing: dict[str, Any],
    *,
    timezone: str,
    start_hour: int,
    end_hour: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tz = ZoneInfo(timezone)
    day = briefing.get("date")
    if not day:
        raise SystemExit("calendar_coverage.py: briefing date is required")
    horizon_start = datetime.combine(datetime.fromisoformat(day).date(), time(start_hour, 0), tz)
    horizon_end = datetime.combine(datetime.fromisoformat(day).date(), time(end_hour, 0), tz)

    valid: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for rank, block in enumerate(briefing.get("schedule_blocks") or [], start=1):
        if not isinstance(block, dict):
            skipped.append({"rank": rank, "reason": "not_object"})
            continue
        category = str(block.get("category") or "").strip().lower()
        if category not in CANONICAL_CATEGORIES:
            skipped.append({"rank": rank, "reason": "noncanonical_category", "category": category})
            continue
        try:
            start, end = _parse_block_range(day, block.get("time_range"), tz)
        except ValueError as exc:
            skipped.append({"rank": rank, "reason": str(exc)})
            continue
        if start < horizon_start or end > horizon_end:
            skipped.append({"rank": rank, "reason": "outside_window"})
            continue
        valid.append(
            {
                "rank": rank,
                "title": _event_title(block.get("activity")),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "category": category,
            }
        )
    return valid, skipped


def build_coverage(
    *,
    briefing_path: str | Path,
    briefing_search_path: str | Path,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    timezone: str = "America/Toronto",
    start_hour: int = 7,
    end_hour: int = 22,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    briefing = _load_json(briefing_path)
    search = _load_json(briefing_search_path)
    if not isinstance(briefing, dict):
        raise SystemExit("calendar_coverage.py: briefing payload must be an object")

    valid_blocks, skipped = _valid_blocks(
        briefing,
        timezone=timezone,
        start_hour=start_hour,
        end_hour=end_hour,
    )
    event_keys = set()
    if isinstance(search, dict):
        for event in search.get("events") or []:
            if isinstance(event, dict):
                key = _event_key(event)
                if key:
                    event_keys.add(key)

    missing_blocks = []
    present = 0
    for block in valid_blocks:
        key = (block["title"], block["start"], block["end"])
        if key in event_keys:
            present += 1
        else:
            missing_blocks.append(block)

    create_args = [
        {
            "calendar_id": calendar_id,
            "title": block["title"],
            "start_time": block["start"],
            "end_time": block["end"],
            "timezone_str": timezone,
            "attendees": [],
            "self_attendance": "omit",
            "add_google_meet": False,
            "description": None,
            "transparency": "opaque",
            "visibility": "private",
        }
        for block in missing_blocks
    ]
    summary = {
        "status": "noop" if not missing_blocks else "missing",
        "valid_block_count": len(valid_blocks),
        "already_present": present,
        "missing": len(missing_blocks),
        "invalid_skipped": len(skipped),
        "missing_blocks": missing_blocks,
        "skipped_blocks": skipped,
    }
    return summary, create_args


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--briefing", default="/tmp/briefing.json")
    parser.add_argument("--briefing-search", default="/tmp/calendar_search_briefing.json")
    parser.add_argument("--calendar-id", default=DEFAULT_CALENDAR_ID)
    parser.add_argument("--timezone", default="America/Toronto")
    parser.add_argument("--start-hour", type=int, default=7)
    parser.add_argument("--end-hour", type=int, default=22)
    parser.add_argument("--summary-out", default="/tmp/calendar_coverage_summary.json")
    parser.add_argument("--create-args-out", default="/tmp/calendar_missing_create_args_private.json")
    args = parser.parse_args()

    summary, create_args = build_coverage(
        briefing_path=args.briefing,
        briefing_search_path=args.briefing_search,
        calendar_id=args.calendar_id,
        timezone=args.timezone,
        start_hour=args.start_hour,
        end_hour=args.end_hour,
    )
    Path(args.summary_out).write_text(json.dumps(summary, indent=2))
    Path(args.create_args_out).write_text(json.dumps(create_args, indent=2))
    print(
        "calendar_coverage.py: "
        f"status={summary['status']} "
        f"valid_blocks={summary['valid_block_count']} "
        f"already_present={summary['already_present']} "
        f"missing={summary['missing']} "
        f"invalid_skipped={summary['invalid_skipped']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
