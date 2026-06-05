#!/usr/bin/env python3
"""Derive compact busy windows from bounded Calendar search results.

The morning briefing watchdog needs a deterministic handoff from Google
Calendar search to `calendar_plan.py`: primary hard commitments should block new
briefing events, long work containers should remain schedulable capacity, and
existing briefing-calendar events should block duplicates.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_BRIEFING_CALENDAR_ID = (
    "ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6"
    "@group.calendar.google.com"
)
WORK_CONTAINER_RE = re.compile(r"\b(work|office|focus|deep work)\b", re.IGNORECASE)
WORK_CONTAINER_MINUTES = 240


def _load(path: str | Path) -> Any:
    with Path(path).open() as f:
        return json.load(f)


def _events(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [event for event in payload["events"] if isinstance(event, dict)]
    return []


def _title(event: dict[str, Any]) -> str:
    for key in ("summary", "display_title", "title"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def _time_pair(event: dict[str, Any]) -> tuple[datetime, datetime] | None:
    start = event.get("start")
    end = event.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        return None
    if end_dt <= start_dt:
        return None
    return start_dt, end_dt


def _duration_minutes(start: datetime, end: datetime) -> int:
    return round((end - start).total_seconds() / 60)


def _is_transparent(event: dict[str, Any]) -> bool:
    transparency = str(event.get("transparency") or event.get("transparency_status") or "").lower()
    return transparency == "transparent"


def _is_work_container(event: dict[str, Any], start: datetime, end: datetime) -> bool:
    return _duration_minutes(start, end) >= WORK_CONTAINER_MINUTES and bool(WORK_CONTAINER_RE.search(_title(event)))


def build_busy_summary(
    *,
    primary_path: str | Path,
    briefing_path: str | Path,
    primary_calendar_id: str = "primary",
    briefing_calendar_id: str = DEFAULT_BRIEFING_CALENDAR_ID,
) -> dict[str, Any]:
    primary_events = _events(_load(primary_path))
    briefing_events = _events(_load(briefing_path))

    busy_windows: list[dict[str, str]] = []
    skipped_transparent = 0
    skipped_work_containers = 0
    invalid_events = 0
    primary_busy_count = 0
    briefing_busy_count = 0

    for event in primary_events:
        pair = _time_pair(event)
        if pair is None:
            invalid_events += 1
            continue
        start, end = pair
        if _is_transparent(event):
            skipped_transparent += 1
            continue
        if _is_work_container(event, start, end):
            skipped_work_containers += 1
            continue
        busy_windows.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "calendar_id": primary_calendar_id,
            }
        )
        primary_busy_count += 1

    for event in briefing_events:
        pair = _time_pair(event)
        if pair is None:
            invalid_events += 1
            continue
        start, end = pair
        busy_windows.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "calendar_id": briefing_calendar_id,
            }
        )
        briefing_busy_count += 1

    return {
        "status": "ok",
        "busy_source": "search",
        "calendar_ids": [primary_calendar_id, briefing_calendar_id],
        "busy_windows": busy_windows,
        "busy_window_count": len(busy_windows),
        "primary_busy_count": primary_busy_count,
        "briefing_busy_count": briefing_busy_count,
        "transparent_primary_skipped": skipped_transparent,
        "work_container_skipped": skipped_work_containers,
        "invalid_event_count": invalid_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", required=True)
    parser.add_argument("--briefing", required=True)
    parser.add_argument("--primary-calendar-id", default="primary")
    parser.add_argument("--briefing-calendar-id", default=DEFAULT_BRIEFING_CALENDAR_ID)
    parser.add_argument("--out", default="/tmp/calendar_busy.json")
    args = parser.parse_args()

    summary = build_busy_summary(
        primary_path=args.primary,
        briefing_path=args.briefing,
        primary_calendar_id=args.primary_calendar_id,
        briefing_calendar_id=args.briefing_calendar_id,
    )
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(
        "calendar_busy_from_search.py: "
        f"busy_windows={summary['busy_window_count']} "
        f"primary_busy={summary['primary_busy_count']} "
        f"briefing_busy={summary['briefing_busy_count']} "
        f"work_containers={summary['work_container_skipped']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
