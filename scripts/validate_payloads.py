#!/usr/bin/env python3
"""Validate morning routine payloads before writes.

This is intentionally narrower than the platform's server-side validation. It
catches contract drift that would otherwise create poor iOS output.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED_CONTROL_CHARS = {"\n", "\r", "\t"}
HERO_HEADLINE_MAX_CHARS = 44
HERO_HEADLINE_MAX_WORDS = 6
HERO_REASON_MAX_CHARS = 160
HERO_REASON_MAX_WORDS = 28
HERO_SECONDARY_MAX_CHARS = 56
HERO_SECONDARY_MAX_WORDS = 8
HERO_ACTION_TYPES = {
    "artifact",
    "focus_correction",
    "communication",
    "calendar",
    "recovery",
    "admin",
    "learning",
    "career",
    "health",
}


def _load_json(path: str | None) -> Any:
    if not path:
        return None
    with open(path) as f:
        return json.load(f)


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def _control_chars(text: str) -> list[str]:
    found: list[str] = []
    for ch in text:
        if ord(ch) < 32 and ch not in ALLOWED_CONTROL_CHARS:
            code = f"U+{ord(ch):04X}"
            if code not in found:
                found.append(code)
    return found


def _word_count(text: str) -> int:
    return len([part for part in text.replace("/", " ").split() if part.strip()])


def _validate_card_text(
    errors: list[str],
    *,
    field: str,
    value: Any,
    max_chars: int,
    max_words: int,
) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str):
        _fail(errors, f"daily_briefing.hero.{field} must be a string")
        return
    text = value.strip()
    if len(text) > max_chars:
        _fail(
            errors,
            f"daily_briefing.hero.{field} is too long for the card "
            f"({len(text)} chars > {max_chars})",
        )
    words = _word_count(text)
    if words > max_words:
        _fail(
            errors,
            f"daily_briefing.hero.{field} is too wordy for the card "
            f"({words} words > {max_words})",
        )


# Schedule-block categories the goal-policy steering actuator can bind to as
# "focused work" (deep_work normalizes to project server-side). If a briefing has
# none of these, the active goal policy stays inert all day — warn, don't fail
# (a legitimate rest/no-deep-work day shouldn't break the briefing).
STEERING_FOCUS_CATEGORIES = {"project", "deep_work"}
CANONICAL_SCHEDULE_CATEGORIES = {
    "project",
    "deep_work",
    "gym",
    "meal",
    "leisure",
    "wind_down",
    "admin",
    "interview",
    "applications",
    "engineering_rebuild",
}
CAREER_SEARCH_CATEGORIES = {"interview", "applications"}
CAREER_SEARCH_TERMS = {
    "application",
    "applications",
    "apply",
    "interview",
    "job",
    "job-search",
    "job search",
    "jobs",
    "outbound",
    "outreach",
    "recruiter",
    "genuine",
}
PRODUCTIVITY_GOAL_TERMS = {
    "artifact",
    "code",
    "coding",
    "deep work",
    "deep-work",
    "focus",
    "hands-on",
    "personal project",
    "productivity",
    "project",
    "skill-building",
    "skill building",
    "system design",
}
DIRECT_PRODUCTIVITY_ACTION_TERMS = {
    "artifact",
    "build",
    "code",
    "coding",
    "deep work",
    "deep-work",
    "focus block",
    "practice",
    "project",
    "repo",
    "ship",
    "skill",
    "system design",
    "tested",
}
SUPPORT_PRODUCTIVITY_ACTION_TERMS = {
    "block",
    "cutoff",
    "distraction",
    "focus",
    "gaming",
    "gym",
    "hrv",
    "lock",
    "macbook",
    "meal",
    "protect",
    "recovery",
    "sleep",
    "windows",
    "wind down",
    "workout",
    "youtube",
}
HARD_BLOCKER_ACTION_TERMS = {
    "appointment",
    "blocked",
    "deadline",
    "due",
    "ill",
    "meeting",
    "reply",
    "sick",
    "urgent",
}
PRODUCTIVITY_HERO_ACTION_TYPES = {"artifact", "focus_correction", "learning"}
HARD_BLOCKER_ACTION_TYPES = {"calendar", "communication", "health", "recovery"}
PRODUCTIVITY_ACTION_SOURCES = {"cross-domain", "goal_policy", "rescuetime", "user_profile"}
SUPPORT_ACTION_SOURCES = PRODUCTIVITY_ACTION_SOURCES | {"calendar", "health"}
HARD_BLOCKER_ACTION_SOURCES = {"calendar", "email", "health"}


def _parse_time_part(value: str) -> int | None:
    try:
        parsed = datetime.strptime(value.strip(), "%I:%M %p")
    except ValueError:
        return None
    return parsed.hour * 60 + parsed.minute


def _parse_time_range_minutes(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str) or " - " not in value:
        return None
    start_raw, end_raw = value.split(" - ", 1)
    start = _parse_time_part(start_raw)
    end = _parse_time_part(end_raw)
    if start is None or end is None or end <= start:
        return None
    return start, end


def _career_search_closed(payload: dict[str, Any]) -> bool:
    goal_context = payload.get("goal_context")
    if isinstance(goal_context, dict) and goal_context.get("career_search_closed") is True:
        return True
    career_pulse = payload.get("career_pulse")
    if not isinstance(career_pulse, dict):
        return False
    return str(career_pulse.get("structured_pipeline_status") or "").strip().lower() == "suspended"


def _has_career_search_term(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in CAREER_SEARCH_TERMS)


def _has_any_term(text: str, terms: set[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _goal_context(payload: dict[str, Any]) -> dict[str, Any]:
    goal_context = payload.get("goal_context")
    return goal_context if isinstance(goal_context, dict) else {}


def _has_active_productivity_goal(payload: dict[str, Any]) -> bool:
    goal_context = _goal_context(payload)
    active_goal = str(goal_context.get("active_goal") or "")
    categories = goal_context.get("strict_schedule_categories")
    category_text = " ".join(str(item) for item in categories) if isinstance(categories, list) else ""
    goal_text = " ".join(
        part
        for part in (
            active_goal,
            category_text,
            str(goal_context.get("goal_implication") or ""),
            str(goal_context.get("implication") or ""),
        )
        if part
    )
    if _has_any_term(goal_text, PRODUCTIVITY_GOAL_TERMS):
        return True
    return bool(goal_context.get("artifact_target_min")) and _has_any_term(category_text, STEERING_FOCUS_CATEGORIES)


def _hero_text(hero: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("headline", "reason", "secondary", "avoid", "success_condition"):
        parts.append(str(hero.get(key) or ""))
    target = hero.get("target")
    if isinstance(target, dict):
        parts.append(str(target.get("label") or ""))
        parts.append(str(target.get("source") or ""))
    evidence = hero.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, dict):
                parts.append(str(item.get("signal") or ""))
                parts.append(str(item.get("source") or ""))
            else:
                parts.append(str(item))
    return " ".join(part for part in parts if part)


def _action_text(action: dict[str, Any]) -> str:
    return " ".join(
        str(action.get(key) or "")
        for key in ("action", "context", "source", "urgency")
    )


def _is_hard_blocker(*, action_type: str | None = None, source: str | None = None, urgency: str | None = None, text: str) -> bool:
    if urgency != "now":
        return False
    if action_type and action_type not in HARD_BLOCKER_ACTION_TYPES:
        return False
    if source and source not in HARD_BLOCKER_ACTION_SOURCES:
        return False
    return _has_any_term(text, HARD_BLOCKER_ACTION_TERMS)


def _hero_aligns_with_productivity_goal(hero: dict[str, Any]) -> bool:
    action_type = str(hero.get("action_type") or "").strip().lower()
    text = _hero_text(hero)
    target = hero.get("target")
    target_source = str(target.get("source") or "").strip().lower() if isinstance(target, dict) else ""

    if action_type in PRODUCTIVITY_HERO_ACTION_TYPES:
        return True
    if target_source in PRODUCTIVITY_ACTION_SOURCES and _has_any_term(text, DIRECT_PRODUCTIVITY_ACTION_TERMS):
        return True
    if _is_hard_blocker(action_type=action_type, urgency=str(hero.get("urgency") or ""), text=text):
        return True
    return False


def _priority_action_aligns_with_productivity_goal(action: dict[str, Any], *, rank: int) -> bool:
    source = str(action.get("source") or "").strip().lower()
    urgency = str(action.get("urgency") or "").strip().lower()
    text = _action_text(action)
    direct = source in PRODUCTIVITY_ACTION_SOURCES and _has_any_term(text, DIRECT_PRODUCTIVITY_ACTION_TERMS)
    hard_blocker = _is_hard_blocker(source=source, urgency=urgency, text=text)
    if rank == 1:
        return direct or hard_blocker
    support = source in SUPPORT_ACTION_SOURCES and (
        _has_any_term(text, DIRECT_PRODUCTIVITY_ACTION_TERMS)
        or _has_any_term(text, SUPPORT_PRODUCTIVITY_ACTION_TERMS)
    )
    return direct or support or hard_blocker


def _artifact_target(payload: dict[str, Any]) -> tuple[float | None, int | None]:
    goal_context = _goal_context(payload)
    if not goal_context:
        return None, None
    target = goal_context.get("artifact_target_min")
    cutoff = goal_context.get("lock_cutoff_hour")
    try:
        target_min = float(target) if target is not None else None
    except (TypeError, ValueError):
        target_min = None
    try:
        cutoff_hour = int(cutoff) if cutoff is not None else None
    except (TypeError, ValueError):
        cutoff_hour = None
    return target_min, cutoff_hour


def validate_briefing(path: str, errors: list[str], warnings: list[str] | None = None) -> None:
    if warnings is None:
        warnings = []
    payload = _load_json(path)
    if not isinstance(payload, dict):
        _fail(errors, f"{path}: payload must be an object")
        return

    hero = payload.get("hero")
    if not isinstance(hero, dict):
        _fail(errors, "daily_briefing.hero is required")
    else:
        for key in ("headline", "reason", "urgency", "action_type", "success_condition", "source_action_rank"):
            if not hero.get(key):
                _fail(errors, f"daily_briefing.hero.{key} is required")
        for key in ("avoid", "evidence"):
            if key not in hero:
                _fail(errors, f"daily_briefing.hero.{key} is required")
        if hero.get("urgency") not in {"now", "today", "this_week"}:
            _fail(errors, "daily_briefing.hero.urgency must be now|today|this_week")
        action_type = hero.get("action_type")
        if action_type not in HERO_ACTION_TYPES:
            _fail(errors, f"daily_briefing.hero.action_type is not allowed: {action_type!r}")
        avoid = hero.get("avoid")
        if "avoid" in hero and avoid is not None and not isinstance(avoid, (list, str)):
            _fail(errors, "daily_briefing.hero.avoid must be a list, string, or null")
        evidence = hero.get("evidence")
        if "evidence" in hero and not isinstance(evidence, list):
            _fail(errors, "daily_briefing.hero.evidence must be a list")
        target = hero.get("target")
        if not isinstance(target, dict):
            _fail(errors, "daily_briefing.hero.target is required")
        else:
            for key in ("label", "source"):
                if not target.get(key):
                    _fail(errors, f"daily_briefing.hero.target.{key} is required")
        _validate_card_text(
            errors,
            field="headline",
            value=hero.get("headline"),
            max_chars=HERO_HEADLINE_MAX_CHARS,
            max_words=HERO_HEADLINE_MAX_WORDS,
        )
        _validate_card_text(
            errors,
            field="reason",
            value=hero.get("reason"),
            max_chars=HERO_REASON_MAX_CHARS,
            max_words=HERO_REASON_MAX_WORDS,
        )
        _validate_card_text(
            errors,
            field="secondary",
            value=hero.get("secondary"),
            max_chars=HERO_SECONDARY_MAX_CHARS,
            max_words=HERO_SECONDARY_MAX_WORDS,
        )
        if _career_search_closed(payload):
            if action_type == "career":
                _fail(errors, "daily_briefing.hero.action_type='career' conflicts with closed career search goal_context")
            if _has_career_search_term(_hero_text(hero)):
                _fail(errors, "daily_briefing.hero turns closed career search into hero copy")
        if _has_active_productivity_goal(payload) and not _hero_aligns_with_productivity_goal(hero):
            _fail(errors, "daily_briefing.hero is not aligned with active productivity goal")

    actions = payload.get("priority_actions")
    if not isinstance(actions, list) or not actions:
        _fail(errors, "daily_briefing.priority_actions must be a non-empty list")
    else:
        for index, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                _fail(errors, f"priority_actions[{index}] must be an object")
                continue
            for key in ("rank", "action", "source", "urgency", "context"):
                if action.get(key) in (None, ""):
                    _fail(errors, f"priority_actions[{index}].{key} is required")

    if "actionable_items" in payload:
        _fail(errors, "daily_briefing must use priority_actions, not actionable_items")

    blocks = payload.get("schedule_blocks")
    if not isinstance(blocks, list) or len(blocks) < 6:
        _fail(errors, "daily_briefing.schedule_blocks must contain at least 6 blocks")
    else:
        categories: list[str] = []
        for index, block in enumerate(blocks, start=1):
            if not isinstance(block, dict):
                _fail(errors, f"schedule_blocks[{index}] must be an object")
                continue
            category = str(block.get("category") or "").strip().lower()
            categories.append(category)
            if category not in CANONICAL_SCHEDULE_CATEGORIES:
                _fail(errors, f"schedule_blocks[{index}].category is not canonical: {category!r}")

        if not any(category in STEERING_FOCUS_CATEGORIES for category in categories):
            warnings.append(
                "daily_briefing.schedule_blocks has no project/deep_work block — the "
                "active goal policy will stay inert today (nothing for steering to bind to)"
            )

        target_min, cutoff_hour = _artifact_target(payload)
        if target_min and cutoff_hour:
            cutoff_min = cutoff_hour * 60
            has_target_block = False
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                category = str(block.get("category") or "").strip().lower()
                if category not in STEERING_FOCUS_CATEGORIES:
                    continue
                parsed = _parse_time_range_minutes(block.get("time_range"))
                if not parsed:
                    continue
                start, end = parsed
                if end <= cutoff_min and (end - start) >= target_min:
                    has_target_block = True
                    break
            if not has_target_block:
                warnings.append(
                    "daily_briefing.schedule_blocks has no pre-cutoff project/deep_work "
                    f"block meeting artifact_target_min={target_min:g}"
                )

        if _career_search_closed(payload):
            for index, block in enumerate(blocks, start=1):
                if not isinstance(block, dict):
                    continue
                category = str(block.get("category") or "").strip().lower()
                block_text = " ".join(
                    str(block.get(key) or "")
                    for key in ("activity", "rationale")
                )
                if category in CAREER_SEARCH_CATEGORIES:
                    _fail(
                        errors,
                        f"schedule_blocks[{index}].category={category!r} conflicts with closed career search goal_context",
                    )
                if _has_career_search_term(block_text):
                    _fail(
                        errors,
                        f"schedule_blocks[{index}] turns closed career search into scheduled work",
                    )

    if _career_search_closed(payload) and isinstance(actions, list):
        for index, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                continue
            source = str(action.get("source") or "").strip().lower()
            text = " ".join(
                str(action.get(key) or "").lower()
                for key in ("action", "context")
            )
            if (source == "career" or _has_career_search_term(text)):
                _fail(
                    errors,
                    f"priority_actions[{index}] turns closed career search into an action",
                )

    if _has_active_productivity_goal(payload) and isinstance(actions, list):
        for index, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                continue
            try:
                rank = int(action.get("rank") or index)
            except (TypeError, ValueError):
                rank = index
            if not _priority_action_aligns_with_productivity_goal(action, rank=rank):
                _fail(errors, f"priority_actions[{index}] is not aligned with active productivity goal")

    for key in (
        "morning_brief",
        "risk_flags",
        "career_pulse",
        "health_summary",
        "focus_yesterday",
        "device_strategy",
        "sources_used",
    ):
        if key not in payload:
            _fail(errors, f"daily_briefing.{key} is required")


def validate_rt(path: str, errors: list[str]) -> None:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        _fail(errors, f"{path}: rt payload must be an object")
        return

    conversion = payload.get("artifact_conversion")
    if not isinstance(conversion, dict):
        _fail(errors, "rt_yesterday.artifact_conversion is required")
        return

    for key in (
        "schema_version",
        "artifact_minutes",
        "productive_minutes",
        "top_artifact_tools",
        "source_quality",
        "interpretation_hint",
    ):
        if key not in conversion:
            _fail(errors, f"artifact_conversion.{key} is required")

    tools = conversion.get("top_artifact_tools")
    if not isinstance(tools, list):
        _fail(errors, "artifact_conversion.top_artifact_tools must be a list")
    else:
        for index, tool in enumerate(tools, start=1):
            if not isinstance(tool, dict):
                _fail(errors, f"top_artifact_tools[{index}] must be an object")
                continue
            if (tool.get("productivity") or 0) < 0:
                _fail(errors, f"top_artifact_tools[{index}] must not be a distraction")


def validate_email(path: str, errors: list[str]) -> None:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        _fail(errors, f"{path}: email payload must be an object")
        return

    actions = payload.get("actionable_emails")
    if not isinstance(actions, list):
        _fail(errors, "email_daily.actionable_emails must be a list")
    else:
        for index, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                _fail(errors, f"actionable_emails[{index}] must be an object")
                continue
            for key in ("subject", "email_type", "priority", "action"):
                if action.get(key) in (None, ""):
                    _fail(errors, f"actionable_emails[{index}].{key} is required")

    if (
        payload.get("career_today_genuine") == 0
        and payload.get("career_days_since_last_genuine") == 0
    ):
        _fail(errors, "career_days_since_last_genuine must not be 0 when today has 0 genuine signals")

    quality = payload.get("career_source_quality")
    if not isinstance(quality, dict):
        _fail(errors, "email_daily.career_source_quality is required")
        return
    for key in (
        "schema_version",
        "career_labeled_email_count",
        "excluded_noise_count",
        "agent_or_system_noise_count",
        "source_quality",
        "caveat",
    ):
        if key not in quality:
            _fail(errors, f"career_source_quality.{key} is required")


def validate_agent_envelope(path: str, errors: list[str]) -> None:
    envelope = _load_json(path)
    if not isinstance(envelope, dict):
        _fail(errors, f"{path}: agent envelope must be an object")
        return

    final_response = envelope.get("final_response")
    if not isinstance(final_response, str) or not final_response.strip():
        _fail(errors, "agent final_response is required")
    elif final_response.lstrip().startswith("Response contract:"):
        _fail(errors, "agent final_response must not start with Response contract:")
    else:
        control_chars = _control_chars(final_response)
        if control_chars:
            _fail(errors, "agent final_response contains disallowed control characters: " + ",".join(control_chars))

    raw_tool_calls = envelope.get("tool_calls")
    if not isinstance(raw_tool_calls, str):
        _fail(errors, "agent tool_calls must be a JSON array string")
        return
    try:
        tool_calls = json.loads(raw_tool_calls)
    except json.JSONDecodeError as exc:
        _fail(errors, f"agent tool_calls is not valid JSON: {exc}")
        return

    if not isinstance(tool_calls, list) or not tool_calls:
        _fail(errors, "agent tool_calls must contain classification metadata")
        return

    classification = tool_calls[0].get("classification") if isinstance(tool_calls[0], dict) else None
    if not isinstance(classification, dict):
        _fail(errors, "agent tool_calls[0].classification is required")
        return

    execution_mode = classification.get("execution_mode")
    if not isinstance(execution_mode, str) or not execution_mode.strip():
        _fail(errors, "agent classification execution_mode is required")

    agent_kind = classification.get("agent_kind")
    run_origin = classification.get("run_origin")
    visibility = classification.get("visibility")

    if agent_kind == "morning_briefing":
        expected = {
            "run_origin": "manual_mcp",
            "visibility": "user_visible",
        }
        for key, value in expected.items():
            if classification.get(key) != value:
                _fail(errors, f"agent classification {key} must be {value!r}")
        return

    if agent_kind == "deep_learner":
        if run_origin == "manual_mcp":
            if visibility != "user_visible":
                _fail(errors, "agent classification visibility must be 'user_visible' for production deep_learner")
            return
        if run_origin == "manual_mcp_test":
            if visibility != "test":
                _fail(errors, "agent classification visibility must be 'test' for test deep_learner")
            if classification.get("run_scope") != "test":
                _fail(errors, "agent classification run_scope must be 'test' for test deep_learner")
            return
        _fail(errors, "agent classification run_origin must be 'manual_mcp' or 'manual_mcp_test' for deep_learner")
        return

    _fail(errors, "agent classification agent_kind must be 'morning_briefing' or 'deep_learner'")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rt", help="Path to rt_yesterday output_response JSON")
    parser.add_argument("--email", help="Path to email_daily output_response JSON")
    parser.add_argument("--briefing", help="Path to daily_briefing output_response JSON")
    parser.add_argument("--agent-envelope", help="Path to write_agent_run request JSON")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    if args.rt:
        validate_rt(args.rt, errors)
    if args.email:
        validate_email(args.email, errors)
    if args.briefing:
        validate_briefing(args.briefing, errors, warnings)
    if args.agent_envelope:
        validate_agent_envelope(args.agent_envelope, errors)
    for warning in warnings:
        print(f"validate_payloads: WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"validate_payloads: {error}", file=sys.stderr)
        return 1
    print("validate_payloads: ok" + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
