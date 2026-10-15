import json
import tempfile
import unittest

from scripts import validate_payloads


def _valid_payload() -> dict:
    return {
        "date": "2026-09-24",
        "goal_context": {
            "career_search_closed": True,
            "active_goal": "Consistent hands-on technical skill-building",
            "artifact_target_min": 30,
        },
        "hero": {
            "headline": "Log the 15-min drill rep",
            "reason": "Drill rep opens at 7 PM; 0/15 min so far.",
            "urgency": "today",
            "secondary": "Floor is 15 min",
            "action_type": "learning",
            "avoid": "youtube.com",
            "target": {"label": "Dojo rep: 15-min no-AI drill", "source": "program"},
            "success_condition": "15+ core_coding minutes logged.",
            "source_action_rank": 1,
            "evidence": [{"source": "program", "signal": "Drill rep open — 0/15 min"}],
        },
        "priority_actions": [
            {"rank": 1, "action": "Do the 7 PM drill rep: 15 hands-on minutes.",
             "source": "program", "urgency": "today", "context": "Program anchor slot."},
        ],
        "schedule_blocks": [
            {"time_range": "7:00 AM - 9:00 AM", "activity": "Wake, breakfast", "category": "meal", "device": "none", "rationale": "Ease in."},
            {"time_range": "9:00 AM - 12:00 PM", "activity": "Employer workday (employer device)", "category": "admin", "device": "none", "rationale": "Day job on the untracked device."},
            {"time_range": "12:00 PM - 1:00 PM", "activity": "Lunch", "category": "meal", "device": "none", "rationale": "Protein-anchored meal."},
            {"time_range": "1:00 PM - 5:00 PM", "activity": "Employer workday (employer device)", "category": "admin", "device": "none", "rationale": "Day job continues."},
            {"time_range": "5:00 PM - 7:00 PM", "activity": "Gym + dinner", "category": "gym", "device": "none", "rationale": "Hold lift loads."},
            {"time_range": "7:00 PM - 8:00 PM", "activity": "Dojo rep: 15-min drill", "category": "project", "device": "macbook", "rationale": "Program anchor slot."},
        ],
        "morning_brief": {},
        "risk_flags": [],
        "health_summary": {},
        "focus_yesterday": {},
        "device_strategy": {},
        "sources_used": [],
    }


class ServerLimitTests(unittest.TestCase):
    def _run(self, payload):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        errors, warnings = [], []
        validate_payloads.validate_briefing(tmp.name, errors, warnings)
        return errors, warnings

    def test_valid_payload_passes_with_day_job_wording(self):
        errors, _ = self._run(_valid_payload())
        self.assertEqual([], errors)

    def test_target_label_over_80_chars_is_rejected(self):
        p = _valid_payload(); p["hero"]["target"]["label"] = "x" * 81
        errors, _ = self._run(p)
        self.assertTrue(any("hero.target.label exceeds 80" in e for e in errors), errors)

    def test_target_label_of_80_chars_is_accepted(self):
        p = _valid_payload(); p["hero"]["target"]["label"] = "x" * 80
        errors, _ = self._run(p)
        self.assertEqual([], errors)

    def test_target_source_over_40_chars_is_rejected(self):
        p = _valid_payload(); p["hero"]["target"]["source"] = "s" * 41
        errors, _ = self._run(p)
        self.assertTrue(any("hero.target.source exceeds 40" in e for e in errors), errors)

    def test_more_than_three_evidence_items_is_rejected(self):
        p = _valid_payload()
        p["hero"]["evidence"] = [{"source": "program", "signal": f"s{i}"} for i in range(4)]
        errors, _ = self._run(p)
        self.assertTrue(any("hero.evidence has 4 items" in e for e in errors), errors)

    def test_success_condition_over_140_chars_is_rejected(self):
        p = _valid_payload(); p["hero"]["success_condition"] = "y" * 141
        errors, _ = self._run(p)
        self.assertTrue(any("hero.success_condition exceeds 140" in e for e in errors), errors)

    def test_job_board_still_reads_as_career_search(self):
        p = _valid_payload()
        p["schedule_blocks"][1]["activity"] = "Browse the job board"
        errors, _ = self._run(p)
        self.assertTrue(any("turns closed career search into scheduled work" in e for e in errors), errors)

    def test_long_block_copy_warns_not_fails(self):
        p = _valid_payload()
        p["schedule_blocks"][5]["activity"] = "a" * 61
        p["schedule_blocks"][5]["rationale"] = "r" * 141
        errors, warnings = self._run(p)
        self.assertEqual([], errors)
        self.assertTrue(any("schedule_blocks[6].activity is 61 chars" in w for w in warnings), warnings)
        self.assertTrue(any("schedule_blocks[6].rationale is 141 chars" in w for w in warnings), warnings)

    # -- A1: rule-15 mirror tap exemption -----------------------------------

    def _rule_15_tap_action(self, rank: int) -> dict:
        return {
            "rank": rank,
            "action": "Tap: decide ticket 3f2a9c1e (research complete) and goal-policy draft 7b1c…",
            "source": "user_profile",
            "urgency": "today",
            "context": "Naming ref 3f2a9c1e (ticket), 7b1c… (goal-policy draft).",
        }

    def test_rule_15_mirror_tap_as_last_entry_beyond_rank_1_is_aligned(self):
        p = _valid_payload()
        p["priority_actions"].append(self._rule_15_tap_action(rank=2))
        errors, _ = self._run(p)
        self.assertEqual([], errors)

    def test_rule_15_mirror_tap_at_rank_1_is_not_exempt(self):
        p = _valid_payload()
        p["priority_actions"] = [self._rule_15_tap_action(rank=1)]
        errors, _ = self._run(p)
        self.assertTrue(
            any("priority_actions[1] is not aligned with active productivity goal" in e for e in errors),
            errors,
        )

    def test_rule_15_mirror_tap_not_last_is_not_exempt(self):
        p = _valid_payload()
        p["priority_actions"].append(self._rule_15_tap_action(rank=2))
        p["priority_actions"].append(
            {"rank": 3, "action": "Wind down by 10 PM.", "source": "health",
             "urgency": "today", "context": "Sleep hygiene."}
        )
        errors, _ = self._run(p)
        self.assertTrue(
            any("priority_actions[2] is not aligned with active productivity goal" in e for e in errors),
            errors,
        )

    # -- A2: mirrored server limits (raw length) ----------------------------

    def test_evidence_signal_over_120_chars_is_rejected(self):
        p = _valid_payload()
        p["hero"]["evidence"] = [{"source": "program", "signal": "s" * 121}]
        errors, _ = self._run(p)
        self.assertTrue(
            any("hero.evidence[1].signal exceeds 120 chars (server limit)" in e for e in errors), errors
        )

    def test_evidence_signal_of_120_chars_is_accepted(self):
        p = _valid_payload()
        p["hero"]["evidence"] = [{"source": "program", "signal": "s" * 120}]
        errors, _ = self._run(p)
        self.assertEqual([], errors)

    def test_evidence_source_over_40_chars_is_rejected(self):
        p = _valid_payload()
        p["hero"]["evidence"] = [{"source": "p" * 41, "signal": "Drill rep open"}]
        errors, _ = self._run(p)
        self.assertTrue(
            any("hero.evidence[1].source exceeds 40 chars (server limit)" in e for e in errors), errors
        )

    def test_empty_evidence_list_is_rejected(self):
        p = _valid_payload()
        p["hero"]["evidence"] = []
        errors, _ = self._run(p)
        self.assertTrue(
            any("hero.evidence must have 1–3 items (server limit)" in e for e in errors), errors
        )

    def test_reason_over_two_lines_is_rejected(self):
        p = _valid_payload()
        p["hero"]["reason"] = "Line one.\nLine two.\nLine three."
        errors, _ = self._run(p)
        self.assertTrue(
            any("hero.reason exceeds 2 lines (server limit)" in e for e in errors), errors
        )

    def test_label_of_80_chars_plus_trailing_space_is_rejected_raw(self):
        p = _valid_payload()
        p["hero"]["target"]["label"] = "x" * 80 + " "
        errors, _ = self._run(p)
        self.assertTrue(any("hero.target.label exceeds 80" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()


class ServerWhitespaceNitTests(unittest.TestCase):
    def _run(self, payload):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        errors, warnings = [], []
        validate_payloads.validate_briefing(tmp.name, errors, warnings)
        return errors

    def test_reason_lines_are_counted_like_the_server(self):
        p = _valid_payload(); p["hero"]["reason"] = "one\rtwo\rthree"
        errors = self._run(p)
        self.assertTrue(any("hero.reason exceeds 2 lines" in e for e in errors), errors)

    def test_whitespace_only_evidence_signal_is_rejected(self):
        p = _valid_payload(); p["hero"]["evidence"] = [{"source": "program", "signal": " "}]
        errors = self._run(p)
        self.assertTrue(any("evidence[1].signal is required" in e for e in errors), errors)


class RepServerLimitTests(unittest.TestCase):
    """2026-10-14: a 278-char program title passed locally and the platform
    rejected the briefing (daily_briefing.schema.json rep.title maxLength 120)."""

    def _run(self, rep):
        p = _valid_payload()
        p["rep"] = rep
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(p, tmp)
        errors, warnings = [], []
        validate_payloads.validate_briefing(tmp.name, errors, warnings)
        return errors

    def _rep(self, **over):
        rep = {"family": "drill", "title": "Rustlings set 1",
               "success_condition": "exercises committed", "floor_minutes": 15}
        rep.update(over)
        return rep

    def test_rep_within_limits_passes(self):
        self.assertEqual([], self._run(self._rep(title="t" * 120, success_condition="s" * 200)))

    def test_rep_title_over_120_is_rejected(self):
        errors = self._run(self._rep(title="t" * 121))
        self.assertTrue(any("rep.title is 121 chars, exceeds 120" in e for e in errors), errors)

    def test_rep_success_condition_over_200_is_rejected(self):
        errors = self._run(self._rep(success_condition="s" * 201))
        self.assertTrue(any("rep.success_condition is 201 chars, exceeds 200" in e for e in errors), errors)

    def test_rep_title_must_be_a_string(self):
        errors = self._run(self._rep(title=["not", "a", "string"]))
        self.assertTrue(any("rep.title must be a string" in e for e in errors), errors)

    def test_rep_floor_minutes_must_be_a_number(self):
        errors = self._run(self._rep(floor_minutes="15"))
        self.assertTrue(any("rep.floor_minutes must be a number" in e for e in errors), errors)
        self.assertTrue(any("must be a number" in e for e in self._run(self._rep(floor_minutes=True))))
        self.assertEqual([], self._run(self._rep(floor_minutes=15.5)))
        self.assertTrue(any("must be a number" in e for e in self._run(self._rep(floor_minutes=None))))
        rep = self._rep(); rep.pop("floor_minutes")
        self.assertEqual([], self._run(rep))   # absent is fine (optional in the schema)

    def test_rep_null_is_rejected(self):
        p = _valid_payload()
        p["rep"] = None
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(p, tmp)
        errors = []
        validate_payloads.validate_briefing(tmp.name, errors, [])
        self.assertTrue(any("rep must be an object when present" in e for e in errors), errors)

    def test_rep_absent_is_fine(self):
        p = _valid_payload()
        p.pop("rep", None)
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(p, tmp)
        errors = []
        validate_payloads.validate_briefing(tmp.name, errors, [])
        self.assertEqual([], errors)
