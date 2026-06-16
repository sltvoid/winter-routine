#!/usr/bin/env python3
"""Stop accidental same-day morning-briefing full replays before writes.

Input is a compact query_raw_sql response saved to /tmp, usually containing the
recent morning llm_runs rows for the target day. This script does not query the
database itself; it keeps the guard usable with either HTTP MCP or native MCP
fallbacks that materialize JSON locally.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


RUN_TYPES = {"rt_yesterday", "email_daily", "daily_briefing", "calendar_write", "agent_runs"}


def _load(path: str) -> dict[str, Any]:
    with open(path) as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise SystemExit(f"replay_guard.py: {path} must contain a JSON object")
    return payload


def _matches_today(row: dict[str, Any], today: str) -> bool:
    return today in {
        str(row.get("input_today") or ""),
        str(row.get("output_date") or ""),
        str(row.get("briefing_date") or ""),
    } or today in str(row.get("goal") or "")


def _select_same_day(
    rows: list[dict[str, Any]], today: str, yesterday: str
) -> list[dict[str, Any]]:
    """Two-pass same-day selection (spec §3.2).

    rt_yesterday / email_daily rows carry output_response.date = the analyzed
    (yesterday) day and only carry input_payload.today when TODAY_ET was
    exported, so the per-row today predicate alone misses them. Detect them via
    (a) sharing a pipeline with a same-day daily_briefing, or (b) an analyzed
    date equal to today's yesterday.
    """
    same_day_pipelines = {
        str(row.get("pipeline_id"))
        for row in rows
        if isinstance(row, dict)
        and str(row.get("run_type") or "") == "daily_briefing"
        and _matches_today(row, today)
        and row.get("pipeline_id")
    }
    selected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        run_type = str(row.get("run_type") or "")
        if run_type not in RUN_TYPES:
            continue
        pipeline_id = str(row.get("pipeline_id") or "")
        analyzed_match = (
            run_type in {"rt_yesterday", "email_daily"}
            and str(row.get("output_date") or "") == yesterday
        )
        if (
            _matches_today(row, today)
            or (pipeline_id and pipeline_id in same_day_pipelines)
            or analyzed_match
        ):
            selected.append(row)
    return selected


def _rows_by_type(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        run_type = str(row.get("run_type") or "")
        if run_type in RUN_TYPES:
            out[run_type].append(row)
    return dict(out)


def _calendar_ok(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        target_verified = str(row.get("target_verified") or "").lower()
        primary_copies = str(row.get("primary_copies") or "")
        if target_verified == "yes" and primary_copies in {"0", "0.0"}:
            return True
    return False


def _is_zero_create_watchdog_row(row: dict[str, Any]) -> bool:
    events_written = str(row.get("events_written") or "")
    if events_written not in {"0", "0.0"}:
        return False
    markers = {
        str(row.get("watchdog") or "").lower(),
        str(row.get("repair") or "").lower(),
        str(row.get("status") or "").lower(),
        str(row.get("errors") or "").lower(),
    }
    return bool(
        {"true", "blocked_no_daily_briefing", "no_same_day_daily_briefing"} & markers
    )


def _watchdog_only_without_briefing(by_type: dict[str, list[dict[str, Any]]]) -> bool:
    if set(by_type) != {"calendar_write"}:
        return False
    rows = by_type.get("calendar_write") or []
    return bool(rows) and all(_is_zero_create_watchdog_row(row) for row in rows)


def _summary(
    *,
    today: str,
    pipeline_id: str,
    matching_rows: list[dict[str, Any]],
    allow_full_replay: bool,
    diagnostic_on_existing: bool,
) -> dict[str, Any]:
    by_type = _rows_by_type(matching_rows)
    existing_types = sorted(by_type)
    row_ids = {
        run_type: [row.get("id") for row in rows]
        for run_type, rows in by_type.items()
    }
    pipelines = sorted({
        str(row.get("pipeline_id"))
        for row in matching_rows
        if row.get("pipeline_id")
    })

    if not matching_rows:
        status = "ok"
        action = "continue"
        recommendation = "No same-day morning rows found; continue full pipeline."
    elif allow_full_replay:
        status = "ok"
        action = "full_replay_explicit"
        recommendation = "Explicit full replay enabled; continue and expect duplicate/new rows."
    elif diagnostic_on_existing:
        status = "ok"
        action = "diagnostic_replay"
        recommendation = (
            "Same-day morning rows already exist; continue read/build/validate "
            "stages in dry-run mode only, with no llm_runs, agent_runs, "
            "calendar creates, or save_memory writes."
        )
    elif _watchdog_only_without_briefing(by_type):
        status = "ok"
        action = "continue_after_watchdog_only"
        recommendation = (
            "Only zero-create Calendar watchdog rows exist and no same-day "
            "daily_briefing exists; continue the full daily pipeline."
        )
    elif "daily_briefing" in by_type and not _calendar_ok(by_type.get("calendar_write", [])):
        status = "stop"
        action = "calendar_only_repair"
        recommendation = "Existing daily_briefing found but calendar verification is incomplete; do calendar-only repair."
    else:
        status = "stop"
        action = "same_day_rows_exist"
        recommendation = "Same-day morning rows already exist; stop unless explicit replay is requested."

    return {
        "status": status,
        "action": action,
        "today_et": today,
        "pipeline_id": pipeline_id,
        "existing_run_types": existing_types,
        "row_ids": row_ids,
        "pipelines": pipelines,
        "allow_full_replay": allow_full_replay,
        "diagnostic_on_existing": diagnostic_on_existing,
        "recommendation": recommendation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing-runs", default="/tmp/morning_existing_runs.json")
    parser.add_argument("--today-et", required=True)
    parser.add_argument("--yesterday-et", required=True)
    parser.add_argument("--pipeline-id", required=True)
    parser.add_argument("--out", default="/tmp/replay_guard.json")
    parser.add_argument(
        "--allow-full-replay",
        action="store_true",
        default=os.environ.get("ALLOW_FULL_REPLAY") == "1",
        help="Allow duplicate/new rows for an explicit replay case.",
    )
    parser.add_argument(
        "--diagnostic-on-existing",
        action="store_true",
        default=os.environ.get("DIAGNOSTIC_REPLAY_ON_EXISTING") == "1",
        help="When same-day rows exist, continue in no-write diagnostic mode.",
    )
    args = parser.parse_args()

    payload = _load(args.existing_runs)
    if payload.get("status") != "ok":
        summary = {
            "status": "stop",
            "action": "preflight_query_failed",
            "today_et": args.today_et,
            "pipeline_id": args.pipeline_id,
            "error": payload.get("error") or "existing-runs query did not return status=ok",
            "recommendation": "Stop before Stage 0 and fix the replay-guard query.",
        }
    else:
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            raise SystemExit("replay_guard.py: existing-runs data must be a list")
        matching = _select_same_day(rows, args.today_et, args.yesterday_et)
        summary = _summary(
            today=args.today_et,
            pipeline_id=args.pipeline_id,
            matching_rows=matching,
            allow_full_replay=args.allow_full_replay,
            diagnostic_on_existing=args.diagnostic_on_existing,
        )

    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(
        "replay_guard.py: "
        f"status={summary['status']} "
        f"action={summary['action']} "
        f"existing={','.join(summary.get('existing_run_types') or []) or 'none'}"
    )
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
