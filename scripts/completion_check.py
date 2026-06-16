#!/usr/bin/env python3
"""End-of-run completion verifier for the morning-briefing pipeline (spec §3.6).

Read-only safety net: given the same compact query_raw_sql response the replay
guard consumes, assert that every expected same-day artifact landed exactly once.
Flags missing artifacts and duplicate run types (e.g. the 3664/3665 situation).
Does not query the database and never writes any pipeline artifact.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Make `scripts` importable whether run as `python3 scripts/completion_check.py`
# from the repo root or imported as `scripts.completion_check` under pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import replay_guard  # noqa: E402  reuse the broadened same-day selection


EXPECTED_TYPES = {
    "rt_yesterday",
    "email_daily",
    "daily_briefing",
    "calendar_write",
    "agent_runs",
}


def _evaluate(rows: list[dict[str, Any]], today: str, yesterday: str) -> dict[str, Any]:
    same_day = replay_guard._select_same_day(rows, today, yesterday)
    counts = Counter(str(row.get("run_type") or "") for row in same_day)
    present = {t for t in counts if t in EXPECTED_TYPES}
    missing = sorted(EXPECTED_TYPES - present)
    duplicate_run_types = sorted(
        t for t, c in counts.items() if t in EXPECTED_TYPES and c > 1
    )
    return {
        "complete": not missing and not duplicate_run_types,
        "missing": missing,
        "duplicate_run_types": duplicate_run_types,
        "present_run_types": sorted(present),
        "today_et": today,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing-runs", default="/tmp/morning_existing_runs.json")
    parser.add_argument("--today-et", required=True)
    parser.add_argument("--yesterday-et", required=True)
    parser.add_argument("--out", default="/tmp/completion_check.json")
    args = parser.parse_args()

    with open(args.existing_runs) as f:
        payload = json.load(f)
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        raise SystemExit("completion_check.py: existing-runs data must be a list")

    result = _evaluate(rows, args.today_et, args.yesterday_et)
    Path(args.out).write_text(json.dumps(result, indent=2))

    if result["complete"]:
        print("completion: ok")
        return 0
    parts = []
    if result["missing"]:
        parts.append(f"missing={result['missing']}")
    if result["duplicate_run_types"]:
        parts.append(f"duplicates={result['duplicate_run_types']}")
    print("completion: INCOMPLETE " + " ".join(parts))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
