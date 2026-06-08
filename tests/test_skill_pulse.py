"""skill_pulse repurpose (Phase 2C).

The morning routine retires the obsolete career_pulse briefing slot and emits
skill_pulse (hands-on vs AI-assisted coding) instead. Skill data is sourced from
the get_skill_summary MCP tool in Stage 0.5, flattened by extract._skill_fields,
and rendered mechanically by payloads.build_briefing_base.
"""

import unittest

from scripts import extract, payloads

# Shape returned by the get_skill_summary HTTP MCP tool (mcp_router wrapper).
_SKILL_SUMMARY = {
    "status": "ok",
    "goal": "Consistent hands-on technical skill-building",
    "today": {"core_coding_min": 0.0, "ai_assisted_coding_min": 196.0, "hands_on_share": 0.0},
    "window": {"days": 14, "core_coding_min": 0.0, "ai_assisted_coding_min": 480.0},
    "streak": {"core_coding_days": 0, "threshold_min": 30},
    "enforcement": {"enforcing_now": False},
}


class SkillFieldsExtractionTests(unittest.TestCase):
    def test_flattens_get_skill_summary(self):
        out = extract._skill_fields(_SKILL_SUMMARY)
        self.assertEqual(out["today_hands_on_min"], 0.0)
        self.assertEqual(out["today_ai_assisted_min"], 196.0)
        self.assertEqual(out["window_ai_assisted_min"], 480.0)
        self.assertEqual(out["streak_days"], 0)
        self.assertEqual(out["threshold_min"], 30)
        self.assertFalse(out["enforcing_now"])
        self.assertEqual(out["goal"], "Consistent hands-on technical skill-building")

    def test_tolerates_empty_or_missing(self):
        out = extract._skill_fields({})
        self.assertEqual(out["today_hands_on_min"], 0)
        self.assertEqual(out["today_ai_assisted_min"], 0)
        self.assertEqual(out["streak_days"], 0)


class SkillStatusTests(unittest.TestCase):
    def test_ai_dependent_when_no_handson(self):
        s = payloads._skill_status(
            {"today_hands_on_min": 0, "today_ai_assisted_min": 196, "threshold_min": 30}
        )
        self.assertIn("AI-dependent", s)

    def test_rep_logged_when_threshold_met(self):
        s = payloads._skill_status(
            {"today_hands_on_min": 35, "today_ai_assisted_min": 10, "threshold_min": 30}
        )
        self.assertIn("Hands-on", s)


class SkillPulseBriefingTests(unittest.TestCase):
    def _data(self):
        return {
            "analyzed_date": "2026-06-06",
            "anom_headline": "Focus steady",
            "parity_headline": "No app data",
            "career_headline": "ignored",
            "goal_context": {},
            "skill": extract._skill_fields(_SKILL_SUMMARY),
        }

    def test_briefing_has_skill_pulse_not_career_pulse(self):
        briefing = payloads.build_briefing_base(
            self._data(),
            date="2026-06-07",
            day_of_week="Sunday",
            analyzed_date="2026-06-06",
            analyzed_day_of_week="Saturday",
        )
        self.assertNotIn("career_pulse", briefing)
        sp = briefing["skill_pulse"]
        self.assertEqual(sp["today_hands_on_min"], 0.0)
        self.assertEqual(sp["today_ai_assisted_min"], 196.0)
        self.assertEqual(sp["window_ai_assisted_min"], 480.0)
        self.assertEqual(sp["streak_days"], 0)
        self.assertEqual(sp["threshold_min"], 30)
        self.assertFalse(sp["enforcing_now"])
        self.assertIn("AI-dependent", sp["status"])
        self.assertEqual(sp["most_important"], "")


class ValidatorDropsCareerPulseRequirementTests(unittest.TestCase):
    """The routine's local validator must no longer require career_pulse, so a
    skill_pulse-bearing briefing (without career_pulse) passes the required-key
    check. career_pulse stays an allowed optional field for the suppression gate.
    """

    def _write(self, payload: dict) -> str:
        import json, tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        return tmp.name

    def test_career_pulse_not_required(self):
        from scripts import validate_payloads
        payload = {
            "date": "2026-06-07",
            "morning_brief": {},
            "risk_flags": [],
            "skill_pulse": {},
            "health_summary": {},
            "focus_yesterday": {},
            "device_strategy": {},
            "sources_used": [],
        }
        errors, warnings = [], []
        validate_payloads.validate_briefing(self._write(payload), errors, warnings)
        self.assertNotIn("daily_briefing.career_pulse is required", errors)


if __name__ == "__main__":
    unittest.main()
