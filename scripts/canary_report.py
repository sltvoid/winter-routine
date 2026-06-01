#!/usr/bin/env python3
"""Print a compact morning-briefing canary report.

The report intentionally avoids dumping payload bodies. It checks the local
files produced by the morning pipeline and emits only status, IDs, counts, and
contract-safety signals.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_CONTROL_CHARS = {"\n", "\r", "\t"}


def _load_json(path: str) -> Any:
    p = Path(path)
    if not p.exists():
        return None
    with p.open() as f:
        return json.load(f)


def _bad_control_chars(text: str) -> list[str]:
    found: list[str] = []
    for ch in text:
        if ord(ch) < 32 and ch not in ALLOWED_CONTROL_CHARS:
            code = f"U+{ord(ch):04X}"
            if code not in found:
                found.append(code)
    return found


def _memory_candidate_keys(data: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for name in ("mem_anom", "mem_parity", "mem_career"):
        candidate = data.get(name)
        if isinstance(candidate, dict) and candidate.get("key"):
            keys.append(str(candidate["key"]))
    return keys


def _agent_checks(envelope: dict[str, Any] | None) -> tuple[str, bool, list[str], bool]:
    if not isinstance(envelope, dict):
        return "missing", False, ["agent envelope missing"], False

    errors: list[str] = []
    final_response = envelope.get("final_response")
    if not isinstance(final_response, str) or not final_response.strip():
        errors.append("final_response missing")
        final_response = ""

    starts_with_contract = final_response.lstrip().startswith("Response contract:")
    if starts_with_contract:
        errors.append("final_response starts with Response contract:")

    bad_controls = _bad_control_chars(final_response)
    if bad_controls:
        errors.append("final_response has control characters: " + ",".join(bad_controls))

    agent_kind = "missing"
    raw_tool_calls = envelope.get("tool_calls")
    try:
        tool_calls = json.loads(raw_tool_calls) if isinstance(raw_tool_calls, str) else []
    except json.JSONDecodeError:
        tool_calls = []
    if tool_calls and isinstance(tool_calls[0], dict):
        classification = tool_calls[0].get("classification")
        if isinstance(classification, dict):
            agent_kind = str(classification.get("agent_kind") or "missing")
    if agent_kind != "morning_briefing":
        errors.append("agent_kind is not morning_briefing")

    return agent_kind, not starts_with_contract, bad_controls, not errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-id", required=True)
    parser.add_argument("--rt-id", default="pending")
    parser.add_argument("--email-id", default="pending")
    parser.add_argument("--briefing-id", default="pending")
    parser.add_argument("--calendar-write-id", default="pending")
    parser.add_argument("--agent-run-id", default="pending")
    parser.add_argument("--mode", choices=("dry_run", "live"), default="dry_run")
    parser.add_argument("--today-et")
    parser.add_argument("--yesterday-et")
    parser.add_argument("--calendar-events-written", type=int, default=0)
    parser.add_argument("--calendar-would-create", type=int)
    parser.add_argument("--calendar-skipped", type=int, default=0)
    parser.add_argument("--calendar-conflict-skipped", type=int, default=0)
    parser.add_argument("--calendar-deleted-prior", type=int, default=0)
    parser.add_argument("--calendar-busy-source", default="not_checked")
    parser.add_argument("--calendar-busy-windows", type=int, default=0)
    parser.add_argument("--calendar-target-verified", choices=("yes", "no", "unknown"), default="unknown")
    parser.add_argument("--calendar-primary-copies", type=int, default=-1)
    parser.add_argument("--next-action", default="keep paused")
    parser.add_argument("--data", default="/tmp/data.json")
    parser.add_argument("--briefing", default="/tmp/briefing.json")
    parser.add_argument("--agent-envelope", default="/tmp/write_agent_body.json")
    args = parser.parse_args()

    data = _load_json(args.data) or {}
    briefing = _load_json(args.briefing) or {}
    agent_envelope = _load_json(args.agent_envelope)

    headlines = [
        data.get("anom_headline"),
        data.get("parity_headline"),
        data.get("career_headline"),
    ]
    briefing_text = json.dumps(briefing, ensure_ascii=False, separators=(",", ":"))
    missing_headlines = [h for h in headlines if h and h not in briefing_text]

    schedule_blocks = briefing.get("schedule_blocks") if isinstance(briefing, dict) else None
    priority_actions = briefing.get("priority_actions") if isinstance(briefing, dict) else None
    block_count = len(schedule_blocks) if isinstance(schedule_blocks, list) else 0
    action_count = len(priority_actions) if isinstance(priority_actions, list) else 0
    analyzed_date = data.get("analyzed_date") if isinstance(data, dict) else None
    briefing_date = briefing.get("date") if isinstance(briefing, dict) else None

    would_create = (
        args.calendar_would_create
        if args.calendar_would_create is not None
        else (args.calendar_events_written if args.mode == "dry_run" else None)
    )
    events_written = 0 if args.mode == "dry_run" else args.calendar_events_written

    agent_kind, prefix_ok, bad_controls, agent_ok = _agent_checks(agent_envelope)
    errors: list[str] = []
    if missing_headlines:
        errors.append("missing Stage 0 headlines: " + str(len(missing_headlines)))
    if block_count < 6:
        errors.append("schedule_blocks < 6")
    if action_count < 1:
        errors.append("priority_actions empty")
    if not agent_ok:
        errors.append("agent envelope failed compact checks")
    if args.calendar_deleted_prior != 0:
        errors.append("calendar deleted_prior is not 0")
    if args.mode == "live" and args.calendar_busy_source != "search":
        errors.append(f"calendar busy source {args.calendar_busy_source}")
    if args.mode == "live" and events_written > 0 and args.calendar_target_verified != "yes":
        errors.append(f"calendar target verification {args.calendar_target_verified}")
    if args.mode == "live" and args.calendar_primary_copies > 0:
        errors.append(f"calendar primary copies {args.calendar_primary_copies}")
    if args.mode == "dry_run" and args.calendar_events_written:
        # Backward-compatible: older callers passed would-create count through
        # --calendar-events-written. Report it clearly as would_create instead.
        pass
    if args.yesterday_et and analyzed_date and analyzed_date != args.yesterday_et:
        errors.append(f"analyzed_date {analyzed_date} != yesterday_et {args.yesterday_et}")
    if args.today_et and briefing_date and briefing_date != args.today_et:
        errors.append(f"briefing date {briefing_date} != today_et {args.today_et}")

    status = "ok" if not errors else "needs_review"
    memory_keys = _memory_candidate_keys(data)

    lines = [
        "clean_canary_report",
        f"overall_status={status}",
        f"pipeline_id={args.pipeline_id}",
        f"row_ids rt_yesterday={args.rt_id} email_daily={args.email_id} daily_briefing={args.briefing_id} calendar_write={args.calendar_write_id} agent_runs={args.agent_run_id}",
        f"dates today_et={args.today_et or 'unknown'} yesterday_et={args.yesterday_et or 'unknown'} analyzed_date={analyzed_date or 'unknown'} briefing_date={briefing_date or 'unknown'}",
        f"briefing schedule_blocks={block_count} priority_actions={action_count} stage0_headlines_preserved={'yes' if not missing_headlines else 'no'}",
        f"calendar mode={args.mode} busy_source={args.calendar_busy_source} busy_windows={args.calendar_busy_windows} events_written={events_written} would_create={would_create if would_create is not None else 'n/a'} deleted_prior={args.calendar_deleted_prior} skipped={args.calendar_skipped} conflict_skipped={args.calendar_conflict_skipped} target_verified={args.calendar_target_verified} primary_copies={args.calendar_primary_copies if args.calendar_primary_copies >= 0 else 'unknown'}",
        f"agent agent_kind={agent_kind} response_contract_prefix={'no' if prefix_ok else 'yes'} control_chars={','.join(bad_controls) if bad_controls else 'none'}",
        f"memory candidate_keys={','.join(memory_keys) if memory_keys else 'none'} keys_saved=none",
        f"errors={'; '.join(errors) if errors else 'none'}",
        f"next_action={args.next_action}",
    ]
    print("\n".join(lines))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
