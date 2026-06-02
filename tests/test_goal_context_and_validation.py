import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import extract, replay_guard, validate_payloads


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
                "target": {"label": "One concrete repo change", "source": "goal_policy"},
                "success_condition": "A tested repo change exists by the cutoff.",
                "source_action_rank": 1,
                "evidence": [{"source": "goal_policy", "signal": "60 minute artifact target"}],
            },
            "priority_actions": [
                {
                    "rank": 1,
                    "action": "Ship one tested repo change before noon.",
                    "source": "goal_policy",
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


class ReplayGuardTests(unittest.TestCase):
    def test_same_day_rows_can_continue_as_diagnostic_replay(self):
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
            diagnostic_on_existing=True,
        )

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["action"], "diagnostic_replay")
        self.assertEqual(summary["row_ids"]["daily_briefing"], ["3303"])


if __name__ == "__main__":
    unittest.main()
