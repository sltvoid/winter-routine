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
