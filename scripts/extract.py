#!/usr/bin/env python3
"""
Stage 0.5b extraction — single pass over 11 /tmp/*.json files produced by
Stage 0.5, emitting /tmp/data.json as the single source of truth for
Stages 1-3.

This replaces the inline `python3 << PYSCRIPT` block in morning-briefing.md.
Kept deliberately defensive: any field can be null / missing and the script
still writes /tmp/data.json with `None` in the affected slot.

Inputs (all optional, missing ones default to empty/null):
  /tmp/insights.json            compute_daily_insights output
  /tmp/health_yesterday.json    query_health date=YESTERDAY mode=daily
  /tmp/health_today.json        query_health date=TODAY mode=daily
  /tmp/health_workouts.json     query_health mode=workouts
  /tmp/sleep_baseline.json      raw_sql 7-day sleep avg
  /tmp/rt_totals.json           raw_sql per-device totals from slice (ground truth)
  /tmp/emails_daily.json        raw_sql yesterday emails
  /tmp/weekly_trend.json        raw_sql latest weekly_trend run (optional)
  /tmp/agent_memory.json        recall_memory (optional, not consumed here)
  /tmp/calendar_blocks.json     query_calendar (optional, not consumed here)
  /tmp/active_goal_policy.json  active goal_policy_versions row (optional)
  /tmp/active_goal_memory.json  active goal/preference memories (optional)

Output:
  /tmp/data.json   flat dict with the 25-ish fields stages 1-3 actually need
"""
from __future__ import annotations
import collections
import json
import os
import sys
from typing import Any


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        print(f"extract.py: could not parse {path}: {exc}", file=sys.stderr)
        return default


def _metric(payload: dict, key: str):
    """Pick a single metric value out of a query_health daily response."""
    data = (payload or {}).get("data") or []
    if not isinstance(data, list):
        return None
    return next(
        (row.get("value") for row in data if row.get("metric_type") == key),
        None,
    )


def _round_metric(value, digits: int = 1):
    if value is None:
        return None
    try:
        return round(value, digits)
    except TypeError:
        return value


def _round_count(value):
    if value is None:
        return None
    try:
        return int(round(value))
    except TypeError:
        return value


def _career_days_since_last_genuine(career: dict) -> tuple[int | None, str | None]:
    """Return the best known recency without turning "unknown" into "today"."""
    raw = career.get("days_since_last_genuine")
    if raw is not None:
        return raw, None

    trend = career.get("trend_14d") or []
    if isinstance(trend, list):
        for offset, row in enumerate(reversed(trend)):
            if isinstance(row, dict) and (row.get("genuine") or 0) > 0:
                return offset, "Derived from trend_14d because days_since_last_genuine was absent."
        if trend:
            return None, f"No genuine signal found in the {len(trend)}-day trend window."

    return None, "No genuine-career recency source was available."


def _email_rows(emails: list) -> list[dict]:
    """Preserve compact email details for downstream actionable-email payloads."""
    rows = []
    for email in emails:
        if not isinstance(email, dict):
            continue
        rows.append({
            "subject": email.get("subject"),
            "from_name": email.get("from_name"),
            "received_et": email.get("received_et"),
            "email_type": email.get("email_type") or "unknown",
        })
    return rows


def _jsonish(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _goal_text(policy: dict, memories: list[dict]) -> str:
    parts: list[str] = []
    for goal in _jsonish(policy.get("goals"), []) or []:
        if isinstance(goal, dict):
            parts.append(str(goal.get("goal") or ""))
            parts.append(str(goal.get("implication") or ""))
        else:
            parts.append(str(goal))
    for row in memories:
        if isinstance(row, dict):
            parts.append(str(row.get("content") or ""))
            parts.append(str(row.get("key") or ""))
    return " ".join(part for part in parts if part).lower()


def _career_search_closed(policy: dict, memories: list[dict]) -> bool:
    text = _goal_text(policy, memories)
    closed_markers = (
        "no longer job-searching",
        "no longer job searching",
        "career search is done",
        "job search is closed",
        "offer received",
        "started a new job",
    )
    return any(marker in text for marker in closed_markers)


def _memory_rows_from(path: str) -> list[dict]:
    rows = (_load(path, {}) or {}).get("data") or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _dedupe_memory_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        key = str(row.get("key") or "")
        identity = key or str(row.get("content") or "")
        if not identity or identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def _goal_context() -> dict:
    policy_rows = (_load("/tmp/active_goal_policy.json", {}) or {}).get("data") or []
    policy = policy_rows[0] if policy_rows and isinstance(policy_rows[0], dict) else {}
    memories = _dedupe_memory_rows(
        _memory_rows_from("/tmp/active_goal_memory.json")
        + [
            row
            for row in _memory_rows_from("/tmp/agent_memory.json")
            if str(row.get("category") or "") in {"goal", "preference"}
        ]
    )
    goals = _jsonish(policy.get("goals"), []) or []
    enforcement = _jsonish(policy.get("enforcement"), {}) or {}
    first_goal = goals[0] if goals and isinstance(goals[0], dict) else {}
    return {
        "policy_id": policy.get("id"),
        "policy_status": policy.get("status"),
        "valid_from": policy.get("valid_from"),
        "valid_until": policy.get("valid_until"),
        "active_goal": first_goal.get("goal") if isinstance(first_goal, dict) else None,
        "goal_rank": first_goal.get("rank") if isinstance(first_goal, dict) else None,
        "goal_implication": first_goal.get("implication") if isinstance(first_goal, dict) else None,
        "strict_schedule_categories": enforcement.get("strict_schedule_categories") or [],
        "relaxed_schedule_categories": enforcement.get("relaxed_schedule_categories") or [],
        "artifact_target_min": enforcement.get("artifact_target_min"),
        "lock_cutoff_hour": enforcement.get("lock_cutoff_hour"),
        "windows_distraction_budget_min": enforcement.get("windows_distraction_budget_min"),
        "career_search_closed": _career_search_closed(policy, memories),
        "memory_keys": [
            row.get("key")
            for row in memories
            if isinstance(row, dict) and row.get("key")
        ],
    }


def main() -> int:
    insights = _load("/tmp/insights.json", {})
    sections = ((insights.get("data") or {}).get("sections")) or {}
    anom = sections.get("anomalies") or {}
    par = sections.get("parity") or {}
    car = sections.get("career") or {}

    health_y = _load("/tmp/health_yesterday.json", {})
    health_t = _load("/tmp/health_today.json", {})

    sleep_s = _metric(health_y, "sleep_seconds")
    hrv_y = _metric(health_y, "hrv_ms")
    rhr = _metric(health_y, "resting_heart_rate_bpm")
    hrv_t = _metric(health_t, "hrv_ms")
    steps = _metric(health_y, "steps")
    active_kcal = _metric(health_y, "active_energy_burned_kilocalories")

    workouts = (_load("/tmp/health_workouts.json", {}) or {}).get("data") or []
    workout = workouts[0] if workouts else {}

    sleep_base_rows = (_load("/tmp/sleep_baseline.json", {}) or {}).get("data") or []
    sleep_avg = (
        sleep_base_rows[0].get("avg_hours")
        if sleep_base_rows and isinstance(sleep_base_rows[0], dict)
        else None
    )

    emails_raw = (_load("/tmp/emails_daily.json", {}) or {}).get("data") or []
    emails = emails_raw if isinstance(emails_raw, list) else []

    rt_totals_raw = (_load("/tmp/rt_totals.json", {}) or {}).get("data") or []
    device_totals = rt_totals_raw if isinstance(rt_totals_raw, list) else []
    career_days, career_days_note = _career_days_since_last_genuine(car)
    goal_context = _goal_context()

    out = {
        "analyzed_date": (insights.get("data") or {}).get("date"),
        # anomalies
        "anom_headline": anom.get("headline"),
        "focus_pct": anom.get("overall_focus_pct"),
        "dod_delta": anom.get("dod_delta_pp"),
        "crashes": anom.get("crashes") or [],
        "peaks": anom.get("peaks") or [],
        # parity
        "parity_headline": par.get("headline"),
        "top_prod": par.get("top_productive") or {},
        "top_dist": par.get("top_distraction") or {},
        "baseline_7d_min": par.get("baseline_7d_avg_min"),
        # career
        "career_headline": car.get("headline"),
        "career_genuine": car.get("today_genuine") or 0,
        "career_noise": car.get("today_noise") or 0,
        "career_stall": car.get("stall_since"),
        "career_days": career_days,
        "career_days_note": career_days_note,
        "career_trend": car.get("trend_14d") or [],
        "career_verdict": car.get("verdict"),
        "career_data_quality": car.get("data_quality") or {},
        # health
        "sleep_h": round((sleep_s or 0) / 3600, 1) if sleep_s else 0,
        "sleep_7d_avg": round(sleep_avg, 1) if sleep_avg else 0,
        "hrv_yesterday": _round_metric(hrv_y),
        "hrv_today": _round_metric(hrv_t),
        "resting_hr": _round_metric(rhr),
        "steps": _round_count(steps),
        "active_kcal": _round_count(active_kcal),
        "workout": workout,
        # rescuetime ground-truth totals (per-device; sum for day totals)
        "device_totals": device_totals,
        # email
        "email_total": len(emails),
        "email_by_type": dict(
            collections.Counter(e.get("email_type", "unknown") for e in emails)
        ),
        "email_rows": _email_rows(emails),
        # memory candidates (may be null)
        "mem_anom": anom.get("memory_candidate"),
        "mem_parity": par.get("memory_candidate"),
        "mem_career": car.get("memory_candidate"),
        "goal_context": goal_context,
    }

    with open("/tmp/data.json", "w") as f:
        json.dump(out, f)
    print("extract.py: /tmp/data.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
