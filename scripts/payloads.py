#!/usr/bin/env python3
"""
Stage 1-3 payload builder.

Reads /tmp/data.json (produced by scripts/extract.py) and emits fully-formed
payloads for the three write_llm_run calls. Moves ~150 lines of mechanical
JSON plumbing out of the runbook and into a static script.

Subcommands:
  rt           -> /tmp/rt_yesterday.json        (Stage 1 body — fully mechanical)
  email        -> /tmp/email_daily.json         (Stage 2 body — fully mechanical)
  briefing_base -> /tmp/briefing_base.json      (Stage 3 body with AI-synthesis
                                                 fields as empty placeholders)
  briefing_finalize <overlay.json>
               -> /tmp/briefing.json            (merges briefing_base + overlay)
  all          -> rt + email + briefing_base    (one shot for the morning run)

The `briefing_base` skeleton leaves these fields for the AI to fill in:
  morning_brief.*          (prose)
  reasoning.*              (prose)
  risk_flags               (list — AI selects and writes evidence/mitigations)
  device_strategy.avoid_triggers / windows_allowed_for
  schedule_blocks          (list — AI synthesizes fresh each day)
  actionable_items         (list)

All other fields are built mechanically from /tmp/data.json and do not
need to be re-written each morning.
"""
from __future__ import annotations
import json
import sys
from typing import Any


def _load_data() -> dict:
    with open("/tmp/data.json") as f:
        return json.load(f)


def _device_split(data: dict) -> list[dict]:
    """Build per-device split from ground-truth `device_totals` (sourced from
    rescuetime_activity_slice via Stage 0.5 raw_sql). `focus_pct` is computed
    in Python with a zero-guard."""
    out = []
    for row in data.get("device_totals") or []:
        total = row.get("total_hours") or 0
        prod = row.get("productive_hours") or 0
        dist = row.get("distracting_hours") or 0
        out.append({
            "device": row.get("device"),
            "total_hours": round(total, 1),
            "productive_hours": round(prod, 1),
            "distracting_hours": round(dist, 1),
            "focus_pct": round(100 * prod / total, 1) if total > 0 else 0.0,
        })
    return out


def _top_apps(data: dict) -> list[dict]:
    top_prod = data.get("top_prod") or {}
    top_dist = data.get("top_dist") or {}
    apps = []
    for source, productivity in ((top_prod, 2), (top_dist, -2)):
        if not isinstance(source, dict) or not source.get("app"):
            continue
        devs = source.get("devices") or {}
        apps.append({
            "activity": source.get("app"),
            "minutes": source.get("minutes", 0),
            "productivity": productivity,
            "device": next(iter(devs.keys()), "unknown"),
        })
    return apps


def build_rt(data: dict) -> dict:
    split = _device_split(data)
    total_h = round(sum(r["total_hours"] for r in split), 1)
    prod_h = round(sum(r["productive_hours"] for r in split), 1)
    dist_h = round(sum(r["distracting_hours"] for r in split), 1)
    return {
        "total_hours": total_h,
        "productive_hours": prod_h,
        "distracting_hours": dist_h,
        "focus_score": data.get("focus_pct"),
        "dod_delta_pp": data.get("dod_delta"),
        "device_split": split,
        "top_apps": _top_apps(data),
        "hourly_focus": {
            "crashes": data.get("crashes") or [],
            "peaks": data.get("peaks") or [],
        },
        "anomalies_headline": data.get("anom_headline"),
        "parity_headline": data.get("parity_headline"),
    }


def build_email(data: dict) -> dict:
    by_type = data.get("email_by_type") or {}
    noise_types = {"marketing", "newsletter", "promotional"}
    actionable = {k: v for k, v in by_type.items() if k not in noise_types}
    trend = data.get("career_trend") or []
    return {
        "total_count": data.get("email_total", 0),
        "by_type": by_type,
        "actionable_emails": actionable,
        "career_summary": data.get("career_headline"),
        "career_today_genuine": data.get("career_genuine", 0),
        "career_today_noise": data.get("career_noise", 0),
        "career_stall_since": data.get("career_stall"),
        "career_days_since_last_genuine": data.get("career_days", 0),
        "career_7d_trend": trend[-7:] if trend else [],
    }


def build_briefing_base(data: dict, *, date: str, day_of_week: str) -> dict:
    workout = data.get("workout") or {}
    crashes = data.get("crashes") or []
    peaks = data.get("peaks") or []
    career_days = data.get("career_days") or 0
    career_genuine = data.get("career_genuine") or 0

    verdict = data.get("career_verdict")
    if verdict is None:
        import sys
        print("career payload missing verdict — defaulting to cautious", file=sys.stderr)
        on_pace = False
        career_status = "At risk"
        structured_pipeline_status = "suspended"
    else:
        on_pace = verdict in ("active", "recovering")
        career_status = "On pace" if on_pace else "At risk"
        structured_pipeline_status = "active" if on_pace else "suspended"

    workout_status = (
        "{title}, {mins}m, {sets} sets".format(
            title=workout.get("title", "No recent workout"),
            mins=round((workout.get("duration_seconds") or 0) / 60),
            sets=workout.get("total_sets", 0),
        )
        if workout else "No recent workout"
    )

    sleep_h = data.get("sleep_h") or 0
    sleep_avg = data.get("sleep_7d_avg") or 0
    workout_rec = "rest" if (sleep_h and sleep_avg and sleep_h < sleep_avg - 0.5) else "green_light"

    focus_pct = data.get("focus_pct") or 0

    return {
        "date": date,
        "day_of_week": day_of_week,
        "sources_used": ["rescuetime", "email", "health", "calendar"],

        # ------- AI fills these in (placeholders) -------
        "morning_brief": {
            "headline": "",
            "context": "",
            "energy_read": "",
        },
        "reasoning": {
            "yesterday_lesson": "",
            "cross_domain_insight": "",
        },
        "risk_flags": [],

        # ------- mechanical from /tmp/data.json -------
        "career_pulse": {
            "status": career_status,
            "on_pace": on_pace,
            "pipeline_trend": data.get("career_headline"),
            "career_emails_today": career_genuine,
            "career_emails_7d_trend": (data.get("career_trend") or [])[-7:],
            "structured_pipeline_status": structured_pipeline_status,
        },
        "health_summary": {
            "sleep_hours_yesterday": sleep_h,
            "sleep_7d_avg": sleep_avg,
            "hrv_ms": data.get("hrv_yesterday"),
            "hrv_ms_today": data.get("hrv_today"),
            "resting_hr_bpm": data.get("resting_hr"),
            "workout_status": workout_status,
            "workout_recommendation": workout_rec,
        },
        "focus_yesterday": {
            "date": date,
            "device_split": _device_split(data),
            "overall_focus_pct": focus_pct,
            "productive_ratio": "1:2" if focus_pct < 50 else "2:1",
            "best_hours": [p.get("hour") for p in peaks],
            "worst_hours": [c.get("hour") for c in crashes],
            "gap": "",   # AI may fill if gaps exist
            "top_apps": _top_apps(data),
        },
        "device_strategy": {
            "primary": "macbook",
            "rationale": data.get("parity_headline"),
            "avoid_triggers": [],     # AI fills
            "windows_allowed_for": "",  # AI fills
        },

        # ------- AI synthesizes fresh each day -------
        "schedule_blocks": [],
        "actionable_items": [],
    }


def _deep_merge(base: Any, overlay: Any) -> Any:
    """Right-biased deep merge. Lists in overlay replace lists in base."""
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = dict(base)
        for k, v in overlay.items():
            out[k] = _deep_merge(base.get(k), v) if k in base else v
        return out
    return overlay if overlay is not None else base


def cmd_rt(args):
    data = _load_data()
    with open("/tmp/rt_yesterday.json", "w") as f:
        json.dump(build_rt(data), f)
    print("payloads.py: /tmp/rt_yesterday.json written")


def cmd_email(args):
    data = _load_data()
    with open("/tmp/email_daily.json", "w") as f:
        json.dump(build_email(data), f)
    print("payloads.py: /tmp/email_daily.json written")


def cmd_briefing_base(args):
    if len(args) < 2:
        print("usage: payloads.py briefing_base <YYYY-MM-DD> <DayOfWeek>", file=sys.stderr)
        sys.exit(2)
    date, dow = args[0], args[1]
    data = _load_data()
    with open("/tmp/briefing_base.json", "w") as f:
        json.dump(build_briefing_base(data, date=date, day_of_week=dow), f)
    print("payloads.py: /tmp/briefing_base.json written")


def cmd_briefing_finalize(args):
    if not args:
        print("usage: payloads.py briefing_finalize <overlay.json>", file=sys.stderr)
        sys.exit(2)
    with open("/tmp/briefing_base.json") as f:
        base = json.load(f)
    with open(args[0]) as f:
        overlay = json.load(f)
    merged = _deep_merge(base, overlay)
    with open("/tmp/briefing.json", "w") as f:
        json.dump(merged, f, indent=2)
    blocks = len(merged.get("schedule_blocks") or [])
    items = len(merged.get("actionable_items") or [])
    print(f"payloads.py: /tmp/briefing.json written ({blocks} blocks, {items} items)")
    if blocks < 6:
        print(f"payloads.py: WARNING schedule_blocks < 6 ({blocks})", file=sys.stderr)
        sys.exit(3)


def cmd_all(args):
    if len(args) < 2:
        print("usage: payloads.py all <YYYY-MM-DD> <DayOfWeek>", file=sys.stderr)
        sys.exit(2)
    cmd_rt([])
    cmd_email([])
    cmd_briefing_base(args)


COMMANDS = {
    "rt": cmd_rt,
    "email": cmd_email,
    "briefing_base": cmd_briefing_base,
    "briefing_finalize": cmd_briefing_finalize,
    "all": cmd_all,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("usage: payloads.py <" + "|".join(COMMANDS) + "> [args...]", file=sys.stderr)
        return 2
    COMMANDS[sys.argv[1]](sys.argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
