#!/usr/bin/env python3
"""Stage 1.2 of the monthly learner — fold the lifeOS Stage 1 reads into ONE
deterministic evidence packet, /tmp/evidence.json (spec
docs/specs/2026-09-23-routine-reevaluation-spec.md §4.3).

No LLM, no network. Every input is an MCP envelope {"status","data"} written
by the runbook's Stage 1; a missing or errored file degrades that section to
null and lists the path in coverage.missing_inputs. Health rows and rep days
live in different databases, so the correlates are joined here on the ET
date. Exit code is 0 unless the output cannot be written.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/Toronto")
SPARSE_REP_WEEKS = 4
INPUTS = [
    "/tmp/program_versions.json", "/tmp/rep_weeks.json", "/tmp/rep_days.json",
    "/tmp/steering.json", "/tmp/health_daily.json", "/tmp/workouts.json",
    "/tmp/skill.json", "/tmp/remarks.json", "/tmp/direction.json",
    "/tmp/program_reviews.json",
]
SLEEP_GOOD_H = 7.0
SLEEP_SHORT_H = 6.5


def _default_loader(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:  # unreadable = missing
        print(f"learner_evidence: could not parse {path}: {exc}", file=sys.stderr)
        return None


def _rows(payload: Any) -> list[dict] | None:
    """Rows of an ok envelope, else None (missing / error / malformed)."""
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    data = payload.get("data")
    return data if isinstance(data, list) else None


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _safe_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(_day(value))
    except ValueError:
        return None


def _program(rows: list[dict]) -> dict:
    versions = [{
        "id": r.get("id"), "status": r.get("status"), "source": r.get("source"),
        "valid_from": _day(r.get("valid_from")), "valid_until": _day(r.get("valid_until")),
        "operator_input": bool(r.get("has_operator_input")),
        "recompose_count": int(r.get("recompose_count") or 0),
    } for r in rows]
    recal = sum(1 for v in versions if str(v["source"] or "").startswith("operator_") or v["operator_input"])
    return {"versions": versions, "operator_recalibrations": recal,
            "auto_versions": len(versions) - recal, "kill_gate_stops": []}


def _rep_weeks(rows: list[dict], rep_day_rows: list[dict] | None = None) -> dict:
    ordered = sorted(rows, key=lambda r: _day(r.get("week_start")), reverse=True)
    newest = (ordered[0].get("rollup") or {}) if ordered else {}
    excused_dates = [
        d for d in (_safe_date(r.get("day")) for r in (rep_day_rows or []) if r.get("travel_excused"))
        if d is not None
    ]

    def excused_days_for(week_start: date | None) -> int:
        if week_start is None:
            return 0
        week_end = week_start + timedelta(days=6)
        return sum(1 for d in excused_dates if week_start <= d <= week_end)

    row_out = []
    for r in ordered:
        week_start_date = _safe_date(r.get("week_start"))
        green = bool(r.get("green"))
        floors_met = r.get("floors_met")
        bar = r.get("bar")
        try:
            floors_short_of_bar = floors_met is not None and bar is not None and floors_met < bar
        except TypeError:
            floors_short_of_bar = False
        row_out.append({
            "week_start": _day(r.get("week_start")), "floors_met": floors_met,
            "bar": bar, "green": green,
            # A week that reads green only because travel-excused days
            # reduced the verifier's effective bar, not because floors were
            # actually met — never read this as practice evidence.
            "excused_days": excused_days_for(week_start_date),
            "green_by_excusal": bool(green and floors_short_of_bar),
        })
    return {
        "rows": row_out,
        "green_rate": _rate(sum(1 for r in ordered if r.get("green")), len(ordered)),
        "consecutive_non_green_now": newest.get("consecutive_non_green"),
        "auto_weeks_no_operator_input": newest.get("auto_weeks_no_operator_input"),
    }


def _rep_days(rows: list[dict]) -> dict:
    by_family: dict[str, dict] = defaultdict(lambda: {"slots": 0, "floors": 0, "artifacts": 0, "minutes": 0.0})
    by_weekday: dict[str, dict] = defaultdict(lambda: {"slots": 0, "floors": 0})
    floor_days: set[date] = set()
    travel = 0
    for r in rows:
        fam = str(r.get("family") or "none")
        parsed = _safe_date(r.get("day"))
        f = by_family[fam]
        f["slots"] += 1
        f["minutes"] += float(r.get("floor_minutes") or 0)
        if r.get("floor_met") and parsed is not None:
            f["floors"] += 1
            floor_days.add(parsed)
        if r.get("artifact"):
            f["artifacts"] += 1
        if r.get("travel_excused"):
            travel += 1
        wd = parsed.strftime("%a").lower() if parsed else "?"
        by_weekday[wd]["slots"] += 1
        if r.get("floor_met"):
            by_weekday[wd]["floors"] += 1
    # longest run of consecutive calendar days with a floor met
    longest = run = 0
    prev: date | None = None
    for d in sorted(floor_days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d
    return {
        "by_family": [{"family": k, "slots": v["slots"], "floors": v["floors"], "artifacts": v["artifacts"],
                       "avg_minutes": round(v["minutes"] / v["slots"], 1) if v["slots"] else None}
                      for k, v in sorted(by_family.items())],
        "by_weekday": [{"weekday": k, **v} for k, v in sorted(by_weekday.items())],
        "days_with_floor": len(floor_days),
        "longest_floor_streak": longest,
        "travel_excused_days": travel,
    }


def _normalize_issued_at(raw: str) -> str:
    """Postgres `issued_at::text` on a timestamptz renders a bare 2-digit
    offset (e.g. "...826675+00", no colon, no minutes) that Python 3.10's
    `datetime.fromisoformat` rejects. Pad it to the +HH:MM form it accepts,
    and accept a trailing "Z" too."""
    text = raw.replace("Z", "+00:00")
    return re.sub(r"([+-]\d{2})$", r"\1:00", text)


def _steering(rows: list[dict]) -> dict:
    outcomes = Counter(); actions = Counter(); delivery = Counter()
    evening = 0
    unparsed = 0
    for r in rows:
        outcomes[str(r.get("final_outcome") or "insufficient_data")] += 1
        actions[str(r.get("action") or "?")] += 1
        delivery[str(r.get("delivery_tag") or "undelivered")] += 1
        try:
            text = _normalize_issued_at(str(r.get("issued_at") or ""))
            hour = datetime.fromisoformat(text).astimezone(ET).hour
            if 19 <= hour < 22:
                evening += 1
        except (ValueError, TypeError):
            unparsed += 1
    # An unmeasurable evening_share must read as null, never as 0 — a row
    # that failed to parse is unknown, not "not evening".
    evening_share = None if unparsed else _rate(evening, len(rows))
    return {
        "episodes": len(rows),
        "outcomes": {k: outcomes.get(k, 0) for k in ("reduced", "held", "backfired", "insufficient_data")},
        "by_action": {k: actions.get(k, 0) for k in ("WARN_LOCAL", "LOCK_WINDOWS")},
        "delivery": {k: delivery.get(k, 0) for k in ("enforced", "delivered", "delivered_not_enforced", "undelivered")},
        "evening_share": evening_share,
        "unparsed_issued_at": unparsed,
    }


def _health(health_rows: list[dict], workout_rows: list[dict] | None, rep_rows: list[dict] | None,
            window_end: str) -> dict:
    sleep_h: dict[str, float] = {}
    hrv: dict[str, float] = {}
    for r in health_rows:
        d = _day(r.get("metric_date"))
        if r.get("metric_type") == "sleep_seconds" and r.get("value") is not None:
            sleep_h[d] = float(r["value"]) / 3600.0
        elif r.get("metric_type") == "hrv_ms" and r.get("value") is not None:
            hrv[d] = float(r["value"])
    end = date.fromisoformat(window_end)
    cut30 = (end - timedelta(days=30)).isoformat()
    s30 = [v for d, v in sleep_h.items() if d >= cut30]
    h30 = [v for d, v in hrv.items() if d >= cut30]
    workout_days = {_day(r.get("day")) for r in (workout_rows or []) if r.get("day")}
    floor_by_day = {_day(r.get("day")): bool(r.get("floor_met")) for r in (rep_rows or [])}

    def rate(pred: Callable[[str], bool]) -> float | None:
        picked = [met for d, met in floor_by_day.items() if pred(d)]
        return _rate(sum(1 for m in picked if m), len(picked))

    return {
        "sleep_avg_h_30d": round(sum(s30) / len(s30), 2) if s30 else None,
        "sleep_avg_h_90d": round(sum(sleep_h.values()) / len(sleep_h), 2) if sleep_h else None,
        "hrv_avg_30d": round(sum(h30) / len(h30), 1) if h30 else None,
        "workout_days": len(workout_days),
        "floor_rate_sleep_ge_7h": rate(lambda d: d in sleep_h and sleep_h[d] >= SLEEP_GOOD_H),
        "floor_rate_sleep_lt_6_5h": rate(lambda d: d in sleep_h and sleep_h[d] < SLEEP_SHORT_H),
        "floor_rate_workout_days": rate(lambda d: d in workout_days) if workout_rows is not None else None,
        "floor_rate_rest_days": rate(lambda d: d not in workout_days) if workout_rows is not None else None,
        "samples": {"sleep_days": len(sleep_h),
                    "joined_rep_days": sum(1 for d in floor_by_day if d in sleep_h)},
    }


def _skill(payload: Any) -> dict | None:
    if not isinstance(payload, dict) or payload.get("status") not in (None, "ok"):
        return None
    window = payload.get("window") or {}
    streak = payload.get("streak") or {}
    if not window:
        return None
    return {"hands_on_min": window.get("core_coding_min") or 0,
            "ai_assisted_min": window.get("ai_assisted_coding_min") or 0,
            "hands_on_share": window.get("hands_on_share"),
            "streak_days": streak.get("core_coding_days") or 0}


def _context(remark_rows: list[dict] | None, direction: Any) -> dict:
    remarks = [{"key": r.get("key"), "created_at": _day(r.get("created_at")),
                "excerpt": str(r.get("content") or "")[:240]} for r in (remark_rows or [])]
    d = (direction or {}).get("direction") if isinstance(direction, dict) else None
    dir_out = None
    if isinstance(d, dict):
        skill = ((d.get("domains") or {}).get("skill") or {})
        dir_out = {"version": d.get("version"), "skill_phase_excerpt": str(skill.get("current_phase") or "")[:240]}
    return {"operator_remarks": remarks, "direction": dir_out}


def build_evidence(window_start: str, window_end: str, *, loader: Callable[[str], Any] = _default_loader) -> dict:
    raw = {p: loader(p) for p in INPUTS}
    rows = {p: _rows(raw[p]) for p in INPUTS}
    missing = [p for p in INPUTS if rows[p] is None and p not in ("/tmp/skill.json", "/tmp/direction.json")]
    skill = _skill(raw["/tmp/skill.json"])
    if skill is None:
        missing.append("/tmp/skill.json")
    if not isinstance(raw["/tmp/direction.json"], dict):
        missing.append("/tmp/direction.json")
    missing = [p for p in INPUTS if p in missing]  # keep INPUTS order

    program = _program(rows["/tmp/program_versions.json"]) if rows["/tmp/program_versions.json"] is not None else None
    if program is not None and rows["/tmp/program_reviews.json"] is not None:
        program["kill_gate_stops"] = sorted(_day(r.get("created_at")) for r in rows["/tmp/program_reviews.json"]
                                           if str(r.get("head") or "").startswith("KILL-GATE"))
    rep_weeks_rows = rows["/tmp/rep_weeks.json"]
    n_weeks = len(rep_weeks_rows or [])
    days = (date.fromisoformat(window_end) - date.fromisoformat(window_start)).days
    return {
        "window": {"start": window_start, "end": window_end, "days": days},
        "program": program,
        "rep_weeks": _rep_weeks(rep_weeks_rows, rows["/tmp/rep_days.json"]) if rep_weeks_rows is not None else None,
        "rep_days": _rep_days(rows["/tmp/rep_days.json"]) if rows["/tmp/rep_days.json"] is not None else None,
        "steering": _steering(rows["/tmp/steering.json"]) if rows["/tmp/steering.json"] is not None else None,
        "health": (_health(rows["/tmp/health_daily.json"], rows["/tmp/workouts.json"], rows["/tmp/rep_days.json"], window_end)
                   if rows["/tmp/health_daily.json"] is not None else None),
        "skill": skill,
        "context": _context(rows["/tmp/remarks.json"], raw["/tmp/direction.json"]),
        "coverage": {"rep_weeks_in_window": n_weeks, "sparse": n_weeks < SPARSE_REP_WEEKS, "missing_inputs": missing},
    }


def main() -> int:
    start = os.environ.get("WINDOW_START_ET")
    end = os.environ.get("TODAY_ET")
    if not start or not end:
        print("learner_evidence: WINDOW_START_ET and TODAY_ET must be exported (source /tmp/anchors.env)", file=sys.stderr)
        return 2
    packet = build_evidence(start, end)
    with open("/tmp/evidence.json", "w") as f:
        json.dump(packet, f)
    cov = packet["coverage"]
    print(f"learner_evidence: /tmp/evidence.json written rep_weeks={cov['rep_weeks_in_window']} "
          f"sparse={cov['sparse']} missing={len(cov['missing_inputs'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
