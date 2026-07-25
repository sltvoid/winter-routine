#!/usr/bin/env python3
"""
Stage 0.5b extraction — single pass over /tmp/*.json files produced by
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
  /tmp/browser_activity.json    raw_sql host-level browser activity aggregate
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


def _browser_rows(payload: dict) -> list[dict]:
    """Normalize compact host-level browser telemetry.

    The browser source is semantic enrichment for RescueTime browser/app time,
    not additional time to add on top of RescueTime totals. Keep only redacted
    host/path-hint aggregates.
    """
    rows = (payload or {}).get("data") or []
    if not isinstance(rows, list):
        return []

    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        host = str(row.get("host") or "").strip().lower()
        if not host:
            continue
        minutes = row.get("minutes")
        if minutes is None and row.get("active_seconds") is not None:
            try:
                minutes = round(float(row.get("active_seconds") or 0) / 60.0, 1)
            except (TypeError, ValueError):
                minutes = None
        try:
            minutes = round(float(minutes or 0), 1)
        except (TypeError, ValueError):
            minutes = 0.0
        if minutes <= 0:
            continue

        raw_hints = row.get("path_hints")
        if raw_hints is None:
            raw_hints = row.get("path_hint")
        if isinstance(raw_hints, str):
            path_hints = [raw_hints]
        elif isinstance(raw_hints, list):
            path_hints = [str(item) for item in raw_hints if item]
        else:
            path_hints = []

        out.append({
            "host": host,
            "device": row.get("device") or row.get("canonical_device"),
            "browser": row.get("browser"),
            "minutes": minutes,
            "event_count": row.get("event_count"),
            "path_hints": path_hints[:3],
        })

    return out


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
        # Preference CONTENTS, not just keys — synthesis must see operator
        # constraints (work schedule, focus rules) verbatim or they cannot
        # shape schedule_blocks (gap found 2026-06-12: a work-hours memory
        # was invisible to the briefing model).
        "preferences": [
            str(row.get("content"))[:400]
            for row in memories
            if isinstance(row, dict)
            and str(row.get("category") or "") == "preference"
            and row.get("content")
        ][:5],
    }


def _program_context() -> dict:
    """Flatten get_active_program output (lifeOS program layer, data-platform
    spec docs/specs/2026-06-11-lifeos-surfaces-spec.md) into briefing inputs.

    /tmp/active_program.json is the raw tool response:
    {status, program{id, frame, rotation, ...}, stale, today_rep{family, title,
    success}|null}. Absent file or no active program degrades to
    {"present": False} — the briefing then behaves exactly as before the
    program layer existed.
    """
    payload = _load("/tmp/active_program.json", {}) or {}
    program = payload.get("program") or {}
    frame = _jsonish(program.get("frame"), {}) or {}
    rep = payload.get("today_rep") or None
    return {
        "present": bool(program),
        "program_id": program.get("id"),
        "stale": bool(payload.get("stale")),
        "today_rep": rep,
        "anchor_start_hour": frame.get("anchor_start_hour", 19),
        "anchor_end_hour": frame.get("anchor_end_hour", 20),
        "floor_minutes": frame.get("weekday_floor_minutes", 30),
        "green_week_bar": frame.get("green_week_bar", 4),
    }


def _operator_taps() -> list[dict]:
    """Fold the operator tap queue (quiet-mode design, data-platform
    session/2026-07-24-benefit-mode-study.md): pending one-tap actions the
    platform is waiting on. Sources are the two Stage 0.5 tap queries; absent
    files degrade to an empty queue (briefing behaves as before).

    Emits [{kind, ref, pending_since, action}] sorted oldest-first."""
    taps: list[dict] = []
    llm_rows = (_load("/tmp/operator_taps_llm.json", {}) or {}).get("data") or []
    for row in llm_rows:
        taps.append({
            "kind": row.get("kind"),
            "ref": row.get("ref"),
            "pending_since": row.get("pending_since"),
            "action": row.get("action"),
        })
    fin_rows = (_load("/tmp/operator_taps_finance.json", {}) or {}).get("data") or []
    for row in fin_rows:
        taps.append({
            "kind": "plaid_relink",
            "ref": row.get("item_id"),
            "pending_since": row.get("pending_since"),
            "action": "Tap the latest Winter Alerts relink email and log into the bank (~1 min); money data is frozen until then.",
        })
    taps.sort(key=lambda t: str(t.get("pending_since") or ""))
    return taps


def _skill_fields(payload: dict) -> dict:
    """Flatten get_skill_summary output into briefing skill_pulse inputs.

    `payload` is the get_skill_summary MCP response
    ({status, goal, today, window, streak, enforcement}). Tolerant of missing
    sections so a skill-source failure degrades to zeros rather than crashing.
    """
    p = payload or {}
    today = p.get("today") or {}
    window = p.get("window") or {}
    streak = p.get("streak") or {}
    enforcement = p.get("enforcement") or {}
    return {
        "goal": p.get("goal"),
        "today_hands_on_min": today.get("core_coding_min") or 0,
        "today_ai_assisted_min": today.get("ai_assisted_coding_min") or 0,
        "hands_on_share": today.get("hands_on_share"),
        "window_days": window.get("days"),
        "window_hands_on_min": window.get("core_coding_min") or 0,
        "window_ai_assisted_min": window.get("ai_assisted_coding_min") or 0,
        "streak_days": streak.get("core_coding_days") or 0,
        "threshold_min": streak.get("threshold_min") or 30,
        "enforcing_now": bool(enforcement.get("enforcing_now")),
    }


def main() -> int:
    insights = _load("/tmp/insights.json", {})
    sections = ((insights.get("data") or {}).get("sections")) or {}
    anom = sections.get("anomalies") or {}
    par = sections.get("parity") or {}
    car = sections.get("career") or {}
    loc = sections.get("location") or {}

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
    browser_activity = _load("/tmp/browser_activity.json", {})
    browser_rows = _browser_rows(browser_activity)

    rt_totals_raw = (_load("/tmp/rt_totals.json", {}) or {}).get("data") or []
    device_totals = rt_totals_raw if isinstance(rt_totals_raw, list) else []
    career_days, career_days_note = _career_days_since_last_genuine(car)
    goal_context = _goal_context()
    skill = _skill_fields(_load("/tmp/skill.json", {}))

    out = {
        "analyzed_date": (insights.get("data") or {}).get("date"),
        # anomalies
        "anom_headline": anom.get("headline"),
        "focus_pct": anom.get("overall_focus_pct"),
        "dod_delta": anom.get("dod_delta_pp"),
        "crashes": anom.get("crashes") or [],
        "peaks": anom.get("peaks") or [],
        "location_context": anom.get("location_context"),
        # location
        "location_headline": loc.get("headline"),
        "location_verdict": loc.get("verdict"),
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
        # browser activity: semantic breakdown of browser time, not additive time
        "browser_rows": browser_rows,
        "browser_total_minutes": round(sum(row.get("minutes") or 0 for row in browser_rows), 1),
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
        # skill mirror (hands-on vs AI-assisted) — sourced from get_skill_summary
        "skill": skill,
        # lifeOS program layer — today's pre-decided rep, from get_active_program
        "program_context": _program_context(),
        # operator tap queue — pending one-tap actions (quiet-mode design 2026-07-24)
        "operator_taps": _operator_taps(),
    }

    with open("/tmp/data.json", "w") as f:
        json.dump(out, f)
    print("extract.py: /tmp/data.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
