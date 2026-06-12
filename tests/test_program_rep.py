"""lifeOS program rep serving (data-platform spec 2026-06-11 §6).

The morning routine reads get_active_program in Stage 0.5, flattens it via
extract._program_context, and payloads.build_briefing_base emits a mechanical
optional `rep` object — additive like skill_pulse, omitted whenever no program
serves a rep (rest day / no active program), so pre-program briefings
validate unchanged.
"""

import json
import os
import tempfile
import unittest

from scripts import extract, payloads, validate_payloads

# Shape returned by the get_active_program HTTP MCP tool.
_PROGRAM_RESPONSE = {
    "status": "ok",
    "stale": False,
    "program": {
        "id": "p-week1",
        "status": "active",
        "frame": {
            "anchor_start_hour": 19,
            "anchor_end_hour": 20,
            "weekday_floor_minutes": 30,
            "green_week_bar": 4,
        },
        "rotation": {"fri": {"family": "drill", "title": "Rustlings set 1",
                             "success": "exercises committed"}},
    },
    "today_rep": {"family": "drill", "title": "Rustlings set 1",
                  "success": "exercises committed"},
}


class ProgramContextExtractionTests(unittest.TestCase):
    def _write_tmp(self, payload):
        with open("/tmp/active_program.json", "w") as f:
            json.dump(payload, f)

    def tearDown(self):
        try:
            os.remove("/tmp/active_program.json")
        except FileNotFoundError:
            pass

    def test_flattens_get_active_program(self):
        self._write_tmp(_PROGRAM_RESPONSE)
        out = extract._program_context()
        self.assertTrue(out["present"])
        self.assertEqual(out["program_id"], "p-week1")
        self.assertEqual(out["today_rep"]["title"], "Rustlings set 1")
        self.assertEqual(out["anchor_start_hour"], 19)
        self.assertEqual(out["floor_minutes"], 30)
        self.assertFalse(out["stale"])

    def test_tolerates_missing_file(self):
        out = extract._program_context()
        self.assertFalse(out["present"])
        self.assertIsNone(out["today_rep"])


class RepObjectTests(unittest.TestCase):
    def _ctx(self, **overrides):
        ctx = {
            "present": True, "program_id": "p-week1", "stale": False,
            "today_rep": {"family": "drill", "title": "Rustlings set 1",
                          "success": "exercises committed"},
            "anchor_start_hour": 19, "anchor_end_hour": 20,
            "floor_minutes": 30, "green_week_bar": 4,
        }
        ctx.update(overrides)
        return ctx

    def test_rep_object_built(self):
        rep = payloads._rep_object(self._ctx(), {"today_hands_on_min": 0})
        self.assertEqual(rep["family"], "drill")
        self.assertEqual(rep["success_condition"], "exercises committed")
        self.assertIn("rep open", rep["status"])

    def test_floor_met_status(self):
        rep = payloads._rep_object(self._ctx(), {"today_hands_on_min": 42})
        self.assertIn("floor met", rep["status"])

    def test_rest_day_returns_none(self):
        self.assertIsNone(payloads._rep_object(self._ctx(today_rep=None), {}))
        self.assertIsNone(payloads._rep_object({}, {}))

    def test_stale_program_flagged(self):
        rep = payloads._rep_object(self._ctx(stale=True), {})
        self.assertTrue(rep["stale_program"])

    def test_briefing_base_includes_rep_only_when_served(self):
        data = {"skill": {}, "program_context": self._ctx(),
                "goal_context": {}}
        base = payloads.build_briefing_base(data, date="2026-06-12", day_of_week="Friday")
        self.assertIn("rep", base)
        data_rest = {"skill": {}, "program_context": self._ctx(today_rep=None),
                     "goal_context": {}}
        base_rest = payloads.build_briefing_base(data_rest, date="2026-06-14", day_of_week="Sunday")
        self.assertNotIn("rep", base_rest)


class RepValidationTests(unittest.TestCase):
    def _validate(self, payload):
        errors = []
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            path = f.name
        try:
            validate_payloads.validate_briefing(path, errors)
        except TypeError:
            errors = []
            validate_payloads.validate_briefing(path, errors=errors)
        finally:
            os.remove(path)
        return errors

    def _briefing(self, rep=None, blocks=None):
        payload = {
            "morning_brief": {}, "risk_flags": [], "health_summary": {},
            "focus_yesterday": {}, "device_strategy": {}, "sources_used": [],
            "schedule_blocks": blocks if blocks is not None else [],
        }
        if rep is not None:
            payload["rep"] = rep
        return payload

    def test_rep_requires_anchor_block(self):
        rep = {"family": "drill", "title": "Rustlings set 1",
               "success_condition": "committed"}
        errors = self._validate(self._briefing(rep=rep, blocks=[]))
        self.assertTrue(any("anchor" in e for e in errors))
        errors = self._validate(self._briefing(
            rep=rep,
            blocks=[{"category": "project", "label": "Dojo rep", "start": "19:00", "end": "20:00"}],
        ))
        self.assertFalse(any("anchor" in e for e in errors))

    def test_bad_family_rejected(self):
        rep = {"family": "yoga", "title": "x", "success_condition": "y"}
        errors = self._validate(self._briefing(rep=rep, blocks=[{"category": "project"}]))
        self.assertTrue(any("family" in e for e in errors))

    def test_no_rep_briefing_unchanged(self):
        errors = self._validate(self._briefing())
        self.assertFalse(any("rep" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
