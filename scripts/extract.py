#!/usr/bin/env python3
"""
Stage 0.5b extraction — single pass over 9 /tmp/*.json files produced by
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

Output:
  /tmp/data.json   flat dict with the 25-ish fields stages 1-3 actually need
"""
from __future__ import annotations
import collections
import json
import os
import sys


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

    out = {
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
        "career_days": car.get("days_since_last_genuine") or 0,
        "career_trend": car.get("trend_14d") or [],
        "career_verdict": car.get("verdict"),
        # health
        "sleep_h": round((sleep_s or 0) / 3600, 1) if sleep_s else 0,
        "sleep_7d_avg": round(sleep_avg, 1) if sleep_avg else 0,
        "hrv_yesterday": hrv_y,
        "hrv_today": hrv_t,
        "resting_hr": rhr,
        "workout": workout,
        # rescuetime ground-truth totals (per-device; sum for day totals)
        "device_totals": device_totals,
        # email
        "email_total": len(emails),
        "email_by_type": dict(
            collections.Counter(e.get("email_type", "unknown") for e in emails)
        ),
        # memory candidates (may be null)
        "mem_anom": anom.get("memory_candidate"),
        "mem_parity": par.get("memory_candidate"),
        "mem_career": car.get("memory_candidate"),
    }

    with open("/tmp/data.json", "w") as f:
        json.dump(out, f)
    print("extract.py: /tmp/data.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
