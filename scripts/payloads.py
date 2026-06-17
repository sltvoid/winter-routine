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
  hero                     (object)
  priority_actions         (list)

All other fields are built mechanically from /tmp/data.json and do not
need to be re-written each morning.
"""
from __future__ import annotations
import json
import os
import sys
from typing import Any, Optional


def _load_data() -> dict:
    with open("/tmp/data.json") as f:
        return json.load(f)


def _calendar_source_quality(date: str) -> dict:
    path = "/tmp/calendar_busy.json"
    if not os.path.exists(path):
        return {
            "status": "partial",
            "latest": date,
            "notes": "Bounded Google Calendar search had not run when this base payload was built.",
        }
    try:
        with open(path) as f:
            busy = json.load(f)
    except Exception as exc:
        return {
            "status": "partial",
            "latest": date,
            "notes": f"Could not parse bounded Google Calendar busy-window summary: {exc}",
        }

    if busy.get("status") == "ok":
        count = busy.get("busy_window_count", len(busy.get("busy_windows") or []))
        return {
            "status": "ok",
            "latest": date,
            "notes": f"Bounded Google Calendar search succeeded; {count} busy window(s) constrain schedule synthesis.",
        }
    if busy.get("status") == "skipped_for_token_budget":
        return {
            "status": "skipped",
            "latest": date,
            "notes": "Calendar search intentionally skipped for token budget; schedule uses an empty busy-window stub.",
        }
    return {
        "status": "failed",
        "latest": date,
        "notes": "Bounded Google Calendar search failed; calendar writes must be skipped and reported in calendar_write.",
    }


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
            "category": source.get("category"),
        })
    return apps


def _is_browser_activity_name(value: Any) -> bool:
    text = str(value or "").lower()
    return any(
        term in text
        for term in (
            "chrome",
            "firefox",
            "safari",
            "arc",
            "brave",
            "edge",
            "browser",
        )
    )


def _artifact_tools(data: dict, *, browser_available: bool = False) -> list[dict]:
    """Return positive artifact/editor evidence only; never include distractions."""
    source = data.get("top_prod") or {}
    if not isinstance(source, dict) or not source.get("app"):
        return []
    if browser_available and _is_browser_activity_name(source.get("app")):
        return []
    devs = source.get("devices") or {}
    minutes = source.get("minutes") or 0
    if minutes <= 0:
        return []
    return [{
        "activity": source.get("app"),
        "minutes": minutes,
        "productivity": 2,
        "device": next(iter(devs.keys()), "unknown"),
        "category": source.get("category"),
    }]


def _strip_www(host: str) -> str:
    host = str(host or "").lower().strip()
    while host.startswith("www."):
        host = host[4:]
    return host


def _path_text(row: dict) -> str:
    hints = row.get("path_hints") or []
    if isinstance(hints, str):
        hints = [hints]
    if not isinstance(hints, list):
        return ""
    return " ".join(str(item or "").lower() for item in hints)


def _browser_category(row: dict) -> str:
    host = _strip_www(row.get("host"))
    path = _path_text(row)

    if not host:
        return "other"
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return "repo"

    build_hosts = (
        "vercel.com",
        "netlify.com",
        "render.com",
        "railway.app",
        "fly.io",
        "cloudflare.com",
        "supabase.com",
        "aws.amazon.com",
        "console.aws.amazon.com",
        "console.cloud.google.com",
        "heroku.com",
    )
    if any(host == item or host.endswith("." + item) for item in build_hosts):
        return "build_ci"
    if host.endswith("github.com") and any(term in path for term in ("actions", "runs", "deployments", "checks")):
        return "build_ci"

    repo_hosts = (
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        "sourcegraph.com",
    )
    if any(host == item or host.endswith("." + item) for item in repo_hosts):
        return "repo"

    ai_hosts = (
        "claude.ai",
        "chatgpt.com",
        "openai.com",
        "platform.openai.com",
        "poe.com",
        "perplexity.ai",
        "gemini.google.com",
    )
    if any(host == item or host.endswith("." + item) for item in ai_hosts):
        return "ai_tool"

    docs_hosts = (
        "stackoverflow.com",
        "stackexchange.com",
        "developer.mozilla.org",
        "mdn.dev",
        "npmjs.com",
        "pypi.org",
        "python.org",
        "react.dev",
        "nextjs.org",
        "tailwindcss.com",
        "docs.github.com",
        "docs.anthropic.com",
        "platform.openai.com",
    )
    if any(host == item or host.endswith("." + item) for item in docs_hosts) or host.startswith("docs."):
        return "docs_reference"

    distraction_hosts = (
        "youtube.com",
        "youtu.be",
        "x.com",
        "twitter.com",
        "reddit.com",
        "instagram.com",
        "facebook.com",
        "tiktok.com",
        "twitch.tv",
        "netflix.com",
        "hulu.com",
        "disneyplus.com",
        "espn.com",
        "hoofoot.ru",
    )
    if any(host == item or host.endswith("." + item) for item in distraction_hosts):
        return "distraction"

    admin_hosts = (
        "mail.google.com",
        "outlook.live.com",
        "calendar.google.com",
        "notion.so",
    )
    if any(host == item or host.endswith("." + item) for item in admin_hosts):
        return "admin"

    career_hosts = (
        "linkedin.com",
        "indeed.com",
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "workdayjobs.com",
        "wellfound.com",
    )
    if any(host == item or host.endswith("." + item) for item in career_hosts):
        return "career"

    return "other"


def _browser_activity_summary(data: dict) -> dict:
    rows = []
    category_minutes: dict[str, float] = {}
    for row in data.get("browser_rows") or []:
        if not isinstance(row, dict):
            continue
        minutes = row.get("minutes") or 0
        try:
            minutes = round(float(minutes), 1)
        except (TypeError, ValueError):
            continue
        if minutes <= 0:
            continue
        category = _browser_category(row)
        category_minutes[category] = round(category_minutes.get(category, 0.0) + minutes, 1)
        enriched = dict(row)
        enriched["category"] = category
        enriched["minutes"] = minutes
        rows.append(enriched)

    rows.sort(key=lambda item: item.get("minutes") or 0, reverse=True)

    def top_for(*categories: str, limit: int = 5) -> list[dict]:
        wanted = set(categories)
        out = []
        for row in rows:
            if row.get("category") not in wanted:
                continue
            out.append({
                "host": row.get("host"),
                "category": row.get("category"),
                "minutes": row.get("minutes"),
                "device": row.get("device"),
                "browser": row.get("browser"),
                "path_hints": row.get("path_hints") or [],
            })
            if len(out) >= limit:
                break
        return out

    return {
        "rows": rows,
        "total_minutes": round(sum(row.get("minutes") or 0 for row in rows), 1),
        "category_minutes": category_minutes,
        "repo_minutes": category_minutes.get("repo", 0.0),
        "build_ci_minutes": category_minutes.get("build_ci", 0.0),
        "ai_tool_minutes": category_minutes.get("ai_tool", 0.0),
        "docs_reference_minutes": category_minutes.get("docs_reference", 0.0),
        "distraction_minutes": category_minutes.get("distraction", 0.0),
        "artifact_evidence": top_for("repo", "build_ci"),
        "top_ai_tools": top_for("ai_tool"),
        "top_distractions": top_for("distraction"),
    }


def _browser_source_quality(data: dict, date: str) -> dict:
    rows = data.get("browser_rows") or []
    if rows:
        return {
            "status": "ok",
            "latest": date,
            "notes": "Host-level browser telemetry was consumed as semantic enrichment for RescueTime browser/app time, not as additive time.",
        }
    return {
        "status": "not_used",
        "latest": None,
        "notes": "No compact browser activity aggregate was available.",
    }


def _artifact_conversion(data: dict, productive_hours: float) -> dict:
    browser = _browser_activity_summary(data)
    browser_available = bool(browser["rows"])
    tools = _artifact_tools(data, browser_available=browser_available)
    productive_minutes = round(productive_hours * 60)
    ide_editor_minutes = sum(
        tool.get("minutes") or 0
        for tool in tools
        if "ide" in str(tool.get("category") or "").lower()
        or "code" in str(tool.get("activity") or "").lower()
    )
    browser_artifact_minutes = round(browser["repo_minutes"] + browser["build_ci_minutes"], 1)
    artifact_minutes = round(ide_editor_minutes + browser_artifact_minutes, 1)
    ai_tool_minutes = browser["ai_tool_minutes"] or None
    artifact_share = (
        round(100 * artifact_minutes / productive_minutes, 1)
        if productive_minutes and artifact_minutes
        else None
    )
    artifact_to_ai_ratio = (
        round(artifact_minutes / ai_tool_minutes, 2)
        if artifact_minutes and ai_tool_minutes
        else None
    )
    artifact_share_of_ai_plus_artifact = (
        round(100 * artifact_minutes / (artifact_minutes + ai_tool_minutes), 1)
        if artifact_minutes and ai_tool_minutes
        else None
    )
    rt_browser_minutes = None
    top_prod = data.get("top_prod") or {}
    if _is_browser_activity_name(top_prod.get("app")):
        rt_browser_minutes = top_prod.get("minutes")
    return {
        "schema_version": 1,
        "ai_or_agent_minutes": ai_tool_minutes,
        "pure_ide_editor_minutes": ide_editor_minutes or None,
        "terminal_build_minutes": None,
        "repo_browser_minutes_rescuetime": rt_browser_minutes,
        "browser_repo_minutes": browser["repo_minutes"] or None,
        "browser_build_ci_minutes": browser["build_ci_minutes"] or None,
        "artifact_minutes": artifact_minutes or None,
        "productive_minutes": productive_minutes,
        "artifact_to_ai_ratio": artifact_to_ai_ratio,
        "artifact_share_of_ai_plus_artifact_pct": artifact_share_of_ai_plus_artifact,
        "productive_artifact_share_pct": artifact_share,
        "ai_tool_minutes": ai_tool_minutes,
        "ide_editor_minutes": ide_editor_minutes or None,
        "top_ai_tools": browser["top_ai_tools"],
        "top_artifact_tools": tools,
        "browser_artifact_evidence": browser["artifact_evidence"],
        "browser_distraction_evidence": browser["top_distractions"],
        "browser_category_minutes": browser["category_minutes"],
        "source_quality": {
            "rescuetime": {
                "status": "ok" if productive_minutes is not None else "partial",
                "notes": "RescueTime remains authoritative for total time, device totals, and productive/distracting totals.",
            },
            "browser_activity": _browser_source_quality(data, data.get("analyzed_date") or os.environ.get("YESTERDAY_ET")),
            "double_counting_policy": {
                "status": "ok",
                "notes": "Browser telemetry classifies RescueTime browser/app time; browser minutes are not added to RescueTime totals.",
            },
        },
        "interpretation_hint": "Use RescueTime for duration magnitude and browser telemetry for semantic breakdown of browser time. Do not add browser minutes on top of RescueTime totals.",
    }


def _productive_ratio_label(productive_hours: float, distracting_hours: float) -> str:
    if productive_hours and distracting_hours:
        ratio = productive_hours / distracting_hours
        return f"{productive_hours:.1f}h productive / {distracting_hours:.1f}h distracting ({ratio:.1f}:1)"
    if productive_hours:
        return f"{productive_hours:.1f}h productive / 0.0h distracting"
    if distracting_hours:
        return f"0.0h productive / {distracting_hours:.1f}h distracting"
    return "No productive or distracting RescueTime totals available"


def _looks_like_system_noise(row: dict) -> bool:
    subject = str(row.get("subject") or "").lower()
    return (
        subject.startswith("[agent]")
        or "secure link to log in" in subject
        or "verification code" in subject
        or "sign in" in subject
        or "login" in subject
    )


def _actionable_emails(data: dict) -> list[dict]:
    rows = []
    for row in data.get("email_rows") or []:
        if not isinstance(row, dict):
            continue
        if row.get("email_type") != "career":
            continue
        if _looks_like_system_noise(row):
            continue
        rows.append({
            "subject": row.get("subject"),
            "from_name": row.get("from_name"),
            "email_type": row.get("email_type"),
            "received_et": row.get("received_et"),
            "priority": "low",
            "action": "Review only if it needs a reply; do not count it as genuine career pipeline movement without an application/interview confirmation.",
        })
    return rows[:10]


def _system_noise_examples(data: dict) -> tuple[int, list[str]]:
    examples = []
    count = 0
    for row in data.get("email_rows") or []:
        if isinstance(row, dict) and row.get("email_type") == "career" and _looks_like_system_noise(row):
            count += 1
            if len(examples) < 3 and row.get("subject"):
                examples.append(row["subject"])
    return count, examples


def _sleep_note(data: dict, sleep_hours: float, sleep_avg: float) -> str:
    parts = []
    if sleep_hours:
        if sleep_avg:
            delta = sleep_hours - sleep_avg
            direction = "above" if delta >= 0 else "below"
            parts.append(f"Sleep was {sleep_hours:.1f}h, {abs(delta):.1f}h {direction} the 7-day average of {sleep_avg:.1f}h.")
        else:
            parts.append(f"Sleep was {sleep_hours:.1f}h; no 7-day sleep average was available.")
    else:
        parts.append("Sleep duration was unavailable.")

    hrv_today = data.get("hrv_today")
    hrv_yesterday = data.get("hrv_yesterday")
    if hrv_today is not None and hrv_yesterday is not None:
        parts.append(f"HRV today is {hrv_today}ms versus {hrv_yesterday}ms yesterday.")
    return " ".join(parts)


def build_rt(data: dict) -> dict:
    split = _device_split(data)
    total_h = round(sum(r["total_hours"] for r in split), 1)
    prod_h = round(sum(r["productive_hours"] for r in split), 1)
    dist_h = round(sum(r["distracting_hours"] for r in split), 1)
    return {
        "mode": "rt_yesterday",
        "date": data.get("analyzed_date") or os.environ.get("YESTERDAY_ET"),
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
        "artifact_conversion": _artifact_conversion(data, prod_h),
    }


def build_email(data: dict) -> dict:
    by_type = data.get("email_by_type") or {}
    actionable = _actionable_emails(data)
    system_noise_count, system_noise_examples = _system_noise_examples(data)
    trend = data.get("career_trend") or []
    career_quality_note = (data.get("career_data_quality") or {}).get("note")
    career_days_note = data.get("career_days_note")
    caveat = "; ".join(part for part in (career_quality_note, career_days_note) if part)
    return {
        "mode": "email_daily",
        "date": data.get("analyzed_date") or os.environ.get("YESTERDAY_ET"),
        "total_count": data.get("email_total", 0),
        "by_type": by_type,
        "actionable_emails": actionable,
        "career_summary": data.get("career_headline"),
        "career_today_genuine": data.get("career_genuine", 0),
        "career_today_noise": data.get("career_noise", 0),
        "career_stall_since": data.get("career_stall"),
        "career_days_since_last_genuine": data.get("career_days"),
        "career_7d_trend": trend[-7:] if trend else [],
        "career_source_quality": {
            "schema_version": 1,
            "career_labeled_email_count": data.get("career_noise", 0) + data.get("career_genuine", 0),
            "application_interview_subject_signal_count": data.get("career_genuine", 0),
            "email_confirmed_applications_today": data.get("career_genuine", 0),
            "email_confirmed_applications_this_week": None,
            "likely_genuine_confirmations_today": data.get("career_genuine", 0),
            "likely_genuine_confirmations_this_week": None,
            "likely_genuine_confirmations": [],
            "genuine_confirmation_count": data.get("career_genuine", 0),
            "unclassified_career_email_count": (((data.get("career_data_quality") or {}).get("unclassified_count"))),
            "excluded_noise_count": data.get("career_noise", 0),
            "agent_or_system_noise_count": system_noise_count,
            "excluded_noise_examples": system_noise_examples,
            "recommended_source_of_truth": "email_confirmed_career_signals_only",
            "source_quality": {
                "email_confirmations": {
                    "status": "ok",
                    "notes": "No genuine career confirmation was inferred unless Stage 0 reported one.",
                },
                "triage_selection": {
                    "status": "partial",
                    "notes": caveat,
                },
            },
            "caveat": caveat,
        },
    }


def _rep_object(program_context: dict, skill: dict) -> Optional[dict]:
    """Mechanical lifeOS rep object for the briefing (data-platform schema:
    optional `rep` with required family/title/success_condition).

    Returns None when no program serves a rep today (rest day, no active
    program) — the field is additive-optional, so the briefing omits it and
    behaves exactly as pre-program-layer.
    """
    rep = (program_context or {}).get("today_rep") or {}
    if not rep.get("family") or not rep.get("title"):
        return None
    success = rep.get("success") or rep.get("success_condition") or ""
    floor = (program_context or {}).get("floor_minutes", 30)
    hands_on = (skill or {}).get("today_hands_on_min") or 0
    status = (
        f"floor met — {round(hands_on)} min logged"
        if hands_on >= floor
        else "rep open — {got}/{need} min, anchor {h}:00 ET".format(
            got=round(hands_on), need=floor,
            h=program_context.get("anchor_start_hour", 19))
    )
    out = {
        "family": rep["family"],
        "title": rep["title"],
        "success_condition": success,
        "floor_minutes": floor,
        "status": status,
    }
    if program_context.get("stale"):
        out["stale_program"] = True
    return out


def _skill_status(skill: dict) -> str:
    """One-line mechanical status string for skill_pulse (no LLM)."""
    th = skill.get("today_hands_on_min") or 0
    ta = skill.get("today_ai_assisted_min") or 0
    threshold = skill.get("threshold_min") or 30
    if th == 0 and ta > 0:
        return f"AI-dependent — 0 hands-on min today vs {round(ta)} AI-assisted"
    if th >= threshold:
        return f"Hands-on rep logged — {round(th)} min core coding today"
    return f"{round(th)} hands-on vs {round(ta)} AI-assisted min today"


def build_briefing_base(
    data: dict,
    *,
    date: str,
    day_of_week: str,
    analyzed_date: Optional[str] = None,
    analyzed_day_of_week: Optional[str] = None,
) -> dict:
    workout = data.get("workout") or {}
    crashes = data.get("crashes") or []
    peaks = data.get("peaks") or []
    skill = data.get("skill") or {}
    program_context = data.get("program_context") or {}

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
    split = _device_split(data)
    prod_h = round(sum(r["productive_hours"] for r in split), 1)
    dist_h = round(sum(r["distracting_hours"] for r in split), 1)
    goal_context = data.get("goal_context") or {}
    sources_used = ["compute_daily_insights", "rescuetime", "email", "health", "calendar"]
    if goal_context.get("policy_id"):
        sources_used.append("goal_policy")
    if data.get("browser_rows"):
        sources_used.append("browser_activity")
    goal_policy_quality = {
        "status": "ok" if goal_context.get("policy_id") else "partial",
        "latest": date,
        "notes": (
            "Active goal policy loaded; schedule synthesis should bind strict categories and artifact target."
            if goal_context.get("policy_id")
            else "No active goal policy file was available to the payload builder."
        ),
    }

    rep_obj = _rep_object(program_context, skill)

    return {
        "date": date,
        "analyzed_date": analyzed_date or date,
        "analyzed_day_of_week": analyzed_day_of_week or day_of_week,
        "mode": "daily_briefing",
        "day_of_week": day_of_week,
        "stage0_headlines": {
            "anomalies": data.get("anom_headline"),
            "parity": data.get("parity_headline"),
            "career": data.get("career_headline"),
        },
        "sources_used": sources_used,
        "source_quality": {
            "compute_daily_insights": {"status": "ok", "latest": analyzed_date or date, "notes": "Required first-stage source."},
            "rescuetime": {"status": "ok" if data.get("focus_pct") is not None else "partial", "latest": analyzed_date or date, "notes": "Device totals are supplementary; Stage 0 headlines remain authoritative."},
            "email": {"status": "ok" if data.get("email_total") is not None else "partial", "latest": analyzed_date or date, "notes": "Email detail is used for counts and low-priority review candidates; Stage 0 career verdict remains authoritative."},
            "health": {"status": "ok" if sleep_h or data.get("hrv_yesterday") else "partial", "latest": analyzed_date or date, "notes": "Apple Health daily metrics and workout summary were available."},
            "calendar": _calendar_source_quality(date),
            "goal_policy": goal_policy_quality,
            "browser_activity": _browser_source_quality(data, analyzed_date or date),
        },
        "goal_context": goal_context,

        # ------- AI fills these in (placeholders) -------
        "hero": {
            "headline": "",
            "reason": "",
            "urgency": "today",
            "secondary": None,
            "action_type": "",
            "avoid": "",
            "target": {
                "label": "",
                "source": "",
            },
            "success_condition": "",
            "source_action_rank": 1,
            "evidence": [],
        },
        "morning_brief": {
            "headline": "",
            "context": "",
            "energy_read": "",
        },
        "reasoning": {
            "yesterday_lesson": "",
            "cross_domain_insight": "",
            "prediction": "",
        },
        "risk_flags": [],

        # ------- mechanical from /tmp/data.json skill split (get_skill_summary) -------
        "skill_pulse": {
            "goal": skill.get("goal") or "Consistent hands-on technical skill-building",
            "today_hands_on_min": skill.get("today_hands_on_min", 0),
            "today_ai_assisted_min": skill.get("today_ai_assisted_min", 0),
            "hands_on_share": skill.get("hands_on_share"),
            "window_days": skill.get("window_days", 14),
            "window_hands_on_min": skill.get("window_hands_on_min", 0),
            "window_ai_assisted_min": skill.get("window_ai_assisted_min", 0),
            "streak_days": skill.get("streak_days", 0),
            "threshold_min": skill.get("threshold_min", 30),
            "enforcing_now": bool(skill.get("enforcing_now")),
            "status": _skill_status(skill),
            "most_important": "",  # AI synthesis overlay may fill
        },
        # ------- mechanical lifeOS rep (get_active_program); omitted on rest
        # days / no active program so pre-program briefings validate unchanged
        **({"rep": rep_obj} if rep_obj else {}),
        "health_summary": {
            "sleep_hours_yesterday": sleep_h,
            "sleep_hours": sleep_h,
            "sleep_7d_avg": sleep_avg,
            "hrv_ms": data.get("hrv_yesterday"),
            "hrv_ms_today": data.get("hrv_today"),
            "resting_hr_bpm": data.get("resting_hr"),
            "sleep_note": _sleep_note(data, sleep_h, sleep_avg),
            "steps": data.get("steps"),
            "active_kcal": data.get("active_kcal"),
            "workout_status": workout_status,
            "workout_recommendation": workout_rec,
        },
        "focus_yesterday": {
            "date": analyzed_date or date,
            "device_split": split,
            "overall_focus_pct": focus_pct,
            "productive_ratio": _productive_ratio_label(prod_h, dist_h),
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
        "priority_actions": [],
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
        print(
            "usage: payloads.py briefing_base <TODAY_YYYY-MM-DD> <TodayDayOfWeek> [YESTERDAY_YYYY-MM-DD] [YesterdayDayOfWeek]",
            file=sys.stderr,
        )
        sys.exit(2)
    date, dow = args[0], args[1]
    analyzed_date = args[2] if len(args) > 2 else None
    analyzed_day_of_week = args[3] if len(args) > 3 else None
    data = _load_data()
    with open("/tmp/briefing_base.json", "w") as f:
        json.dump(
            build_briefing_base(
                data,
                date=date,
                day_of_week=dow,
                analyzed_date=analyzed_date,
                analyzed_day_of_week=analyzed_day_of_week,
            ),
            f,
        )
    print("payloads.py: /tmp/briefing_base.json written")


def cmd_briefing_finalize(args):
    if not args:
        print("usage: payloads.py briefing_finalize <overlay.json>", file=sys.stderr)
        sys.exit(2)
    with open("/tmp/briefing_base.json") as f:
        base = json.load(f)
    with open(args[0]) as f:
        overlay = json.load(f)
    if "actionable_items" in overlay and "priority_actions" not in overlay:
        overlay["priority_actions"] = [
            {
                "rank": i,
                "action": item.get("action") or item.get("item") or "",
                "urgency": item.get("urgency") or "today",
                "source": item.get("source") or "cross-domain",
                "context": item.get("context") or item.get("priority") or "",
            }
            for i, item in enumerate(overlay.get("actionable_items") or [], start=1)
            if isinstance(item, dict)
        ]
    overlay.pop("actionable_items", None)
    merged = _deep_merge(base, overlay)
    with open("/tmp/briefing.json", "w") as f:
        json.dump(merged, f, indent=2)
    blocks = len(merged.get("schedule_blocks") or [])
    actions = len(merged.get("priority_actions") or [])
    print(f"payloads.py: /tmp/briefing.json written ({blocks} blocks, {actions} priority actions)")
    errors = []
    if blocks < 6:
        errors.append(f"schedule_blocks < 6 ({blocks})")
    if actions < 1:
        errors.append("priority_actions is empty")
    if not isinstance(merged.get("hero"), dict) or not merged["hero"].get("headline"):
        errors.append("hero.headline missing")
    if errors:
        for error in errors:
            print(f"payloads.py: WARNING {error}", file=sys.stderr)
        sys.exit(3)


def cmd_all(args):
    if len(args) < 2:
        print("usage: payloads.py all <TODAY_YYYY-MM-DD> <TodayDayOfWeek> [YESTERDAY_YYYY-MM-DD] [YesterdayDayOfWeek]", file=sys.stderr)
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
