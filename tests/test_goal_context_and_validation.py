import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from scripts import extract, payloads, replay_guard, validate_payloads


class GoalContextTests(unittest.TestCase):
    def test_goal_context_detects_closed_career_from_memory_fallback(self):
        def fake_load(path, default):
            if path == "/tmp/active_goal_policy.json":
                return {"data": []}
            if path == "/tmp/active_goal_memory.json":
                return {"data": []}
            if path == "/tmp/agent_memory.json":
                return {
                    "data": [
                        {
                            "key": "goal-skill-building",
                            "category": "goal",
                            "content": (
                                "User started a new job and is no longer job-searching. "
                                "New primary goal: consistent hands-on technical skill-building."
                            ),
                        }
                    ]
                }
            return default

        with patch.object(extract, "_load", side_effect=fake_load):
            context = extract._goal_context()

        self.assertTrue(context["career_search_closed"])
        self.assertIn("goal-skill-building", context["memory_keys"])


class ClosedCareerValidationTests(unittest.TestCase):
    def _write_payload(self, payload: dict) -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        return tmp.name

    def _base_payload(self) -> dict:
        return {
            "date": "2026-06-01",
            "goal_context": {"career_search_closed": True},
            "hero": {
                "headline": "Send one application",
                "reason": "Career pipeline looked stale.",
                "urgency": "now",
                "secondary": "Before 10 AM",
                "action_type": "career",
            },
            "priority_actions": [
                {
                    "rank": 1,
                    "action": "Send one genuine application",
                    "source": "cross-domain",
                    "urgency": "now",
                    "context": "Use outreach to break the career stall.",
                }
            ],
            "schedule_blocks": [
                {"time_range": "7:00 AM - 8:00 AM", "activity": "Project", "category": "project"},
                {"time_range": "8:00 AM - 9:00 AM", "activity": "Deep work", "category": "deep_work"},
                {"time_range": "9:00 AM - 10:00 AM", "activity": "Admin", "category": "admin"},
                {"time_range": "10:00 AM - 11:00 AM", "activity": "Meal", "category": "meal"},
                {"time_range": "11:00 AM - 12:00 PM", "activity": "Gym", "category": "gym"},
                {"time_range": "12:00 PM - 1:00 PM", "activity": "Project", "category": "project"},
            ],
            "morning_brief": {},
            "risk_flags": [],
            "career_pulse": {"structured_pipeline_status": "suspended"},
            "health_summary": {},
            "focus_yesterday": {},
            "device_strategy": {},
            "sources_used": [],
        }

    def test_closed_career_rejects_hero_and_actions(self):
        payload_path = self._write_payload(self._base_payload())
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertTrue(
            any("hero.action_type='career'" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("priority_actions[1]" in error for error in errors),
            errors,
        )

    def test_suspended_career_pulse_rejects_career_even_when_goal_context_missing(self):
        payload = self._base_payload()
        payload.pop("goal_context")
        payload_path = self._write_payload(payload)
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertTrue(
            any("hero.action_type='career'" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("priority_actions[1]" in error for error in errors),
            errors,
        )


class HeroSchemaValidationTests(unittest.TestCase):
    def _write_payload(self, payload: dict) -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        return tmp.name

    def _payload(self, hero_overrides: dict | None = None) -> dict:
        hero = {
            "headline": "Ship one repo change",
            "reason": "Yesterday's focused window was thin; protect one build block.",
            "urgency": "today",
            "secondary": "Before 8 PM",
            "action_type": "artifact",
            "avoid": ["youtube.com"],
            "target": {"label": "One concrete repo change", "source": "goal_policy"},
            "success_condition": "A tested repo change exists by the cutoff.",
            "source_action_rank": 1,
            "evidence": [{"source": "rescuetime", "signal": "1.2h productive"}],
        }
        if hero_overrides:
            hero.update(hero_overrides)
        return {
            "date": "2026-06-01",
            "goal_context": {"career_search_closed": False},
            "hero": hero,
            "priority_actions": [
                {
                    "rank": 1,
                    "action": "Ship one tested repo change",
                    "source": "cross-domain",
                    "urgency": "today",
                    "context": "Matches the active skill-building goal.",
                }
            ],
            "schedule_blocks": [
                {"time_range": "7:00 AM - 8:00 AM", "activity": "Project", "category": "project"},
                {"time_range": "8:00 AM - 9:00 AM", "activity": "Deep work", "category": "deep_work"},
                {"time_range": "9:00 AM - 10:00 AM", "activity": "Admin", "category": "admin"},
                {"time_range": "10:00 AM - 11:00 AM", "activity": "Meal", "category": "meal"},
                {"time_range": "11:00 AM - 12:00 PM", "activity": "Gym", "category": "gym"},
                {"time_range": "12:00 PM - 1:00 PM", "activity": "Project", "category": "project"},
            ],
            "morning_brief": {},
            "risk_flags": [],
            "career_pulse": {},
            "health_summary": {},
            "focus_yesterday": {},
            "device_strategy": {},
            "sources_used": [],
        }

    def test_server_required_hero_schema_fields_are_validated_locally(self):
        payload = self._payload()
        del payload["hero"]["avoid"]
        del payload["hero"]["evidence"]
        payload_path = self._write_payload(payload)
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertIn("daily_briefing.hero.avoid is required", errors)
        self.assertIn("daily_briefing.hero.evidence is required", errors)

    def test_invalid_hero_action_type_is_rejected_before_server_write(self):
        payload_path = self._write_payload(self._payload({"action_type": "outreach"}))
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertIn("daily_briefing.hero.action_type is not allowed: 'outreach'", errors)

    def test_hero_evidence_items_require_server_signal_shape(self):
        payload_path = self._write_payload(
            self._payload({"evidence": [{"source": "calendar", "detail": "Open block before 9 AM."}]})
        )
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertIn("daily_briefing.hero.evidence[1].signal is required", errors)

    def test_runbook_overlay_shape_lists_full_hero_contract(self):
        runbook = Path("morning-briefing.md").read_text()

        for key in (
            '"source_action_rank"',
            '"avoid"',
            '"target"',
            '"evidence"',
            '"action_type"',
            '"success_condition"',
        ):
            self.assertIn(key, runbook)


class AgentEnvelopeValidationTests(unittest.TestCase):
    def _write_envelope(self, classification: dict) -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(
                {
                    "goal": "Weekly behavioral profile analysis v16 (TEST RUN)",
                    "final_response": "Learner preview summary.",
                    "model": "routine-selected",
                    "pipeline_id": "test-pipeline",
                    "tool_calls": json.dumps([{"classification": classification}]),
                },
                tmp,
            )
        return tmp.name

    def test_deep_learner_test_agent_envelope_is_valid(self):
        errors: list[str] = []
        path = self._write_envelope(
            {
                "run_origin": "manual_mcp_test",
                "execution_mode": "scheduled_claude",
                "agent_kind": "deep_learner",
                "visibility": "test",
                "run_scope": "test",
            }
        )

        validate_payloads.validate_agent_envelope(path, errors)

        self.assertEqual([], errors)

    def test_deep_learner_production_agent_envelope_is_valid(self):
        errors: list[str] = []
        path = self._write_envelope(
            {
                "run_origin": "manual_mcp",
                "execution_mode": "scheduled_claude",
                "agent_kind": "deep_learner",
                "visibility": "user_visible",
            }
        )

        validate_payloads.validate_agent_envelope(path, errors)

        self.assertEqual([], errors)

    def test_unknown_agent_kind_is_rejected(self):
        errors: list[str] = []
        path = self._write_envelope(
            {
                "run_origin": "manual_mcp",
                "execution_mode": "scheduled_claude",
                "agent_kind": "weekly_anything",
                "visibility": "user_visible",
            }
        )

        validate_payloads.validate_agent_envelope(path, errors)

        self.assertTrue(any("agent_kind" in error for error in errors), errors)


class ActiveGoalSteeringValidationTests(unittest.TestCase):
    def _write_payload(self, payload: dict) -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        return tmp.name

    def _payload(self) -> dict:
        return {
            "date": "2026-06-01",
            "goal_context": {
                "active_goal": (
                    "Consistent hands-on technical skill-building: focused deep-work blocks "
                    "for coding practice, system design study, and personal projects."
                ),
                "artifact_target_min": 60,
                "strict_schedule_categories": ["project"],
                "career_search_closed": False,
            },
            "hero": {
                "headline": "Ship one repo change",
                "reason": "Yesterday's focus was thin; protect one build block.",
                "urgency": "today",
                "secondary": "Before 8 PM",
                "action_type": "artifact",
                "avoid": ["youtube.com"],
                "target": {"label": "One concrete repo change", "source": "priority_actions[0]"},
                "success_condition": "A tested repo change exists by the cutoff.",
                "source_action_rank": 1,
                "evidence": [{"source": "user_profile", "signal": "60 minute artifact target"}],
            },
            "priority_actions": [
                {
                    "rank": 1,
                    "action": "Ship one tested repo change before noon.",
                    "source": "user_profile",
                    "urgency": "today",
                    "context": "Matches the active skill-building goal.",
                },
                {
                    "rank": 2,
                    "action": "Keep Windows gaming below eight minutes.",
                    "source": "rescuetime",
                    "urgency": "today",
                    "context": "Protects the project block from distraction drift.",
                },
            ],
            "schedule_blocks": [
                {"time_range": "7:00 AM - 8:00 AM", "activity": "Project", "category": "project"},
                {"time_range": "8:00 AM - 9:00 AM", "activity": "Deep work", "category": "deep_work"},
                {"time_range": "9:00 AM - 10:00 AM", "activity": "Admin", "category": "admin"},
                {"time_range": "10:00 AM - 11:00 AM", "activity": "Meal", "category": "meal"},
                {"time_range": "11:00 AM - 12:00 PM", "activity": "Gym", "category": "gym"},
                {"time_range": "12:00 PM - 1:00 PM", "activity": "Project", "category": "project"},
            ],
            "morning_brief": {},
            "risk_flags": [],
            "career_pulse": {"structured_pipeline_status": "active"},
            "health_summary": {},
            "focus_yesterday": {},
            "device_strategy": {},
            "sources_used": [],
        }

    def test_active_productivity_goal_rejects_non_goal_hero_and_top_action(self):
        payload = self._payload()
        payload["hero"].update(
            {
                "headline": "Clear the inbox",
                "reason": "Email volume is noisy today.",
                "action_type": "admin",
                "target": {"label": "Inbox review", "source": "email"},
                "success_condition": "Review low priority messages.",
                "evidence": [{"source": "email", "signal": "14 messages"}],
            }
        )
        payload["priority_actions"][0] = {
            "rank": 1,
            "action": "Review career-tagged emails before coding.",
            "source": "email",
            "urgency": "today",
            "context": "Inbox cleanup looked available.",
        }
        payload_path = self._write_payload(payload)
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertTrue(
            any("hero is not aligned with active productivity goal" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("priority_actions[1] is not aligned with active productivity goal" in error for error in errors),
            errors,
        )

    def test_active_productivity_goal_allows_artifact_and_focus_actions(self):
        payload_path = self._write_payload(self._payload())
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertEqual([], errors)

    def test_priority_action_source_must_match_live_server_enum(self):
        payload = self._payload()
        payload["priority_actions"][0]["source"] = "goal_policy"
        payload_path = self._write_payload(payload)
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertIn(
            "priority_actions[1].source is not server-accepted: 'goal_policy'",
            errors,
        )


class Stage0HeadlinePreservationTests(unittest.TestCase):
    def test_briefing_base_preserves_exact_stage0_headlines(self):
        data = {
            "analyzed_date": "2026-06-02",
            "anom_headline": "No focus anomalies — insufficient hourly data",
            "parity_headline": "No app data available",
            "career_headline": "Career pipeline stalled — no genuine outreach in 14-day window",
            "goal_context": {},
        }

        briefing = payloads.build_briefing_base(
            data,
            date="2026-06-03",
            day_of_week="Wednesday",
            analyzed_date="2026-06-02",
            analyzed_day_of_week="Tuesday",
        )

        self.assertEqual(
            {
                "anomalies": "No focus anomalies — insufficient hourly data",
                "parity": "No app data available",
                "career": "Career pipeline stalled — no genuine outreach in 14-day window",
            },
            briefing.get("stage0_headlines"),
        )


class DeviceMagnitudeValidationTests(unittest.TestCase):
    def _write_payload(self, payload: dict) -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        return tmp.name

    def _payload_with_multi_device_split(self) -> dict:
        payload = ActiveGoalSteeringValidationTests()._payload()
        payload["stage0_headlines"] = {
            "anomalies": "Focus was steady — 42% overall, no crashes or standout peaks",
            "parity": "codex 238min leads over top distraction youtube.com 129min; Mac share 100% (178% above 7d avg)",
            "career": "Career pipeline stalled — no genuine outreach in 14-day window",
        }
        payload["focus_yesterday"] = {
            "device_split": [
                {"device": "windows", "total_hours": 2.6, "productive_hours": 0.1},
                {"device": "macbook", "total_hours": 8.9, "productive_hours": 4.7},
            ],
            "top_apps": [
                {"activity": "codex", "device": "macbook", "minutes": 238},
                {"activity": "youtube.com", "device": "macbook", "minutes": 129},
            ],
        }
        return payload

    def test_generated_device_magnitude_claims_must_match_device_split(self):
        payload = self._payload_with_multi_device_split()
        payload["morning_brief"] = {
            "headline": "Turn Codex momentum into a shipped artifact.",
            "context": "Thursday was all Mac, with Mac share 100% across the tracked day.",
            "energy_read": "Sleep was slightly below baseline.",
        }
        payload["device_strategy"] = {
            "primary": "macbook",
            "rationale": "Mac share 100% (178% above 7d avg)",
            "avoid_triggers": ["youtube.com"],
            "windows_allowed_for": "Only short system tasks.",
        }
        payload_path = self._write_payload(payload)
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertTrue(
            any("device-magnitude claim conflicts with focus_yesterday.device_split" in error for error in errors),
            errors,
        )

    def test_stage0_headline_can_preserve_bad_device_claim_without_reuse(self):
        payload = self._payload_with_multi_device_split()
        payload["morning_brief"] = {
            "headline": "Turn Codex momentum into a shipped artifact.",
            "context": "Mac had the largest tracked share, while Windows also logged screen time.",
            "energy_read": "Sleep was slightly below baseline.",
        }
        payload["device_strategy"] = {
            "primary": "macbook",
            "rationale": "Mac had the largest tracked share; Windows still logged 2.6h.",
            "avoid_triggers": ["youtube.com"],
            "windows_allowed_for": "Only short system tasks.",
        }
        payload_path = self._write_payload(payload)
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertFalse(
            any("device-magnitude claim conflicts with focus_yesterday.device_split" in error for error in errors),
            errors,
        )


class CalendarManifestOnlyQualityTests(unittest.TestCase):
    def test_briefing_base_marks_token_budget_calendar_skip_as_skipped(self):
        busy = json.dumps(
            {
                "status": "skipped_for_token_budget",
                "busy_windows": [],
                "busy_window_count": 0,
            }
        )

        with patch("scripts.payloads.os.path.exists", return_value=True), patch(
            "builtins.open",
            mock_open(read_data=busy),
        ):
            quality = payloads._calendar_source_quality("2026-06-04")

        self.assertEqual("skipped", quality["status"])
        self.assertIn("intentionally skipped", quality["notes"])

    def test_validator_rejects_failed_calendar_status_when_busy_stub_was_skipped(self):
        payload = ActiveGoalSteeringValidationTests()._payload()
        payload["source_quality"] = {
            "calendar": {
                "status": "failed",
                "latest": "2026-06-04",
                "notes": "Bounded Google Calendar search failed.",
            }
        }
        payload_path = ActiveGoalSteeringValidationTests()._write_payload(payload)
        errors: list[str] = []
        warnings: list[str] = []

        with patch("scripts.validate_payloads._tmp_calendar_busy_status", return_value="skipped_for_token_budget"):
            validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertIn(
            "source_quality.calendar.status must be skipped or partial when calendar_busy is skipped_for_token_budget",
            errors,
        )


class OutputCalibrationValidationTests(unittest.TestCase):
    def _write_json(self, payload: dict) -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        return tmp.name

    def _write_text(self, text: str) -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        with tmp:
            tmp.write(text)
        return tmp.name

    def test_briefing_rejects_shipping_overclaim_from_weak_evidence(self):
        payload = ActiveGoalSteeringValidationTests()._payload()
        payload["reasoning"] = {
            "yesterday_lesson": "Codex ran 238 min, but nothing shipped.",
            "cross_domain_insight": "Low deploy evidence means the block needs a clearer artifact target.",
        }
        payload_path = self._write_json(payload)
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertTrue(any("overclaims shipping status" in error for error in errors), errors)

    def test_briefing_allows_calibrated_missing_deploy_evidence_language(self):
        payload = ActiveGoalSteeringValidationTests()._payload()
        payload["reasoning"] = {
            "yesterday_lesson": "Codex ran 238 min; no deploy/CI evidence visible in the available browser sources.",
            "cross_domain_insight": "Low deploy evidence means the block needs a clearer artifact target.",
        }
        payload_path = self._write_json(payload)
        errors: list[str] = []
        warnings: list[str] = []

        validate_payloads.validate_briefing(payload_path, errors, warnings)

        self.assertEqual([], errors)

    def test_narrative_rejects_closed_career_recommendations(self):
        context = ActiveGoalSteeringValidationTests()._payload()
        context["goal_context"]["career_search_closed"] = True
        context["career_pulse"] = {"structured_pipeline_status": "suspended"}
        context_path = self._write_json(context)
        narrative_path = self._write_text(
            "ACTIONABLE ITEMS\n"
            "1. Ship one code artifact.\n\n"
            "RECOMMENDATIONS\n"
            "1. Plan 15 min of prep for the SalesJack interview no later than Tuesday.\n"
        )
        errors: list[str] = []

        validate_payloads.validate_narrative(narrative_path, errors, briefing_context_path=context_path)

        self.assertTrue(any("career" in error.lower() for error in errors), errors)

    def test_calendar_handoff_rejects_redundant_generic_artifact_blocks(self):
        handoff = {
            "pipeline_id": "p",
            "today_et": "2026-06-05",
            "timezone": "America/Toronto",
            "mode": "diagnostic_calendar_handoff",
            "calendar_write_allowed": False,
            "recommended_blocks": [
                {
                    "rank": 1,
                    "title": "Project block — coding practice and artifact target",
                    "purpose": "Ship one concrete code commit before cutoff.",
                    "source_action_rank": 1,
                    "action_type": "deep_work",
                    "target": "Commit or PR",
                    "avoid": "youtube.com",
                    "evidence": ["Codex 238 min"],
                    "success_condition": "Commit pushed",
                    "preferred_duration_minutes": 120,
                    "minimum_duration_minutes": 60,
                    "energy": "high",
                    "flexibility": "movable",
                    "deadline_pressure": "today",
                    "active_goal_fit": "high",
                },
                {
                    "rank": 2,
                    "title": "Afternoon project block — build and ship concrete feature",
                    "purpose": "Extended coding window to ship another concrete feature.",
                    "source_action_rank": 1,
                    "action_type": "deep_work",
                    "target": "Deployable feature",
                    "avoid": "reddit.com",
                    "evidence": ["Goal policy project block"],
                    "success_condition": "Feature shipped",
                    "preferred_duration_minutes": 180,
                    "minimum_duration_minutes": 90,
                    "energy": "high",
                    "flexibility": "movable",
                    "deadline_pressure": "today",
                    "active_goal_fit": "high",
                },
            ],
            "placement_policy": {},
            "memory_candidates": [],
        }
        errors: list[str] = []

        validate_payloads.validate_calendar_handoff(self._write_json(handoff), errors)

        self.assertTrue(any("redundant generic artifact-shipping blocks" in error for error in errors), errors)

    def test_calendar_handoff_accepts_distinct_productivity_blocks(self):
        handoff = {
            "pipeline_id": "p",
            "today_et": "2026-06-05",
            "timezone": "America/Toronto",
            "mode": "diagnostic_calendar_handoff",
            "calendar_write_allowed": False,
            "recommended_blocks": [
                {
                    "rank": 1,
                    "title": "Ship repo artifact",
                    "purpose": "Implement and commit one concrete code change.",
                    "source_action_rank": 1,
                    "action_type": "deep_work",
                    "target": "Commit or PR",
                    "avoid": "youtube.com",
                    "evidence": ["Goal policy artifact target"],
                    "success_condition": "Commit pushed",
                    "preferred_duration_minutes": 120,
                    "minimum_duration_minutes": 60,
                    "energy": "high",
                    "flexibility": "movable",
                    "deadline_pressure": "today",
                    "active_goal_fit": "high",
                },
                {
                    "rank": 2,
                    "title": "Review implementation plan",
                    "purpose": "Review docs and write the next implementation checklist.",
                    "source_action_rank": 2,
                    "action_type": "deep_work",
                    "target": "Documented plan",
                    "avoid": "reddit.com",
                    "evidence": ["Planning reduces startup friction"],
                    "success_condition": "Plan note written",
                    "preferred_duration_minutes": 45,
                    "minimum_duration_minutes": 30,
                    "energy": "medium",
                    "flexibility": "movable",
                    "deadline_pressure": "today",
                    "active_goal_fit": "high",
                },
            ],
            "placement_policy": {},
            "memory_candidates": [],
        }
        errors: list[str] = []

        validate_payloads.validate_calendar_handoff(self._write_json(handoff), errors)

        self.assertEqual([], errors)


class ReplayGuardTests(unittest.TestCase):
    def test_briefing_present_but_siblings_missing_completes_missing(self):
        # Iteration 2 (2026-06-16): when same-day rows exist, the default completes
        # the gaps live (write only the missing artifacts). The no-write diagnostic
        # is now reachable only via the explicit --diagnostic-on-existing flag (see
        # test_replay_guard.CompleteMissingTests.test_explicit_diagnostic_overrides_complete).
        summary = replay_guard._summary(
            today="2026-06-01",
            pipeline_id="new-pipeline",
            matching_rows=[
                {
                    "id": "3303",
                    "run_type": "daily_briefing",
                    "pipeline_id": "existing-pipeline",
                    "output_date": "2026-06-01",
                }
            ],
            allow_full_replay=False,
            diagnostic_on_existing=False,
        )

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["action"], "complete_missing")
        self.assertEqual(
            summary["missing_run_types"],
            ["calendar_write", "email_daily", "rt_yesterday"],
        )
        self.assertEqual(summary["row_ids"]["daily_briefing"], ["3303"])

    def test_zero_create_watchdog_row_without_daily_briefing_does_not_block_daily_run(self):
        summary = replay_guard._summary(
            today="2026-06-04",
            pipeline_id="new-pipeline",
            matching_rows=[
                {
                    "id": "3345",
                    "run_type": "calendar_write",
                    "pipeline_id": "watchdog-pipeline",
                    "output_date": "2026-06-04",
                    "events_written": "0",
                    "target_verified": "no",
                    "primary_copies": "0",
                    "watchdog": "true",
                    "status": "blocked_no_daily_briefing",
                    "errors": "no_same_day_daily_briefing",
                }
            ],
            allow_full_replay=False,
            diagnostic_on_existing=False,
        )

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["action"], "continue_after_watchdog_only")
        self.assertEqual(summary["row_ids"]["calendar_write"], ["3345"])


if __name__ == "__main__":
    unittest.main()
