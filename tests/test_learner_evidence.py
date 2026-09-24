import unittest

from scripts import learner_evidence as le


def _env(rows):
    return {"status": "ok", "data": rows}


FULL = {
    "/tmp/program_versions.json": _env([
        {"id": "p1", "status": "active", "source": "claude_program_review", "valid_from": "2026-08-31",
         "valid_until": "2026-09-06", "has_operator_input": False, "recompose_count": 0},
        {"id": "p0", "status": "active", "source": "operator_recalibration", "valid_from": "2026-07-22",
         "valid_until": "2026-07-27", "has_operator_input": True, "recompose_count": 1},
    ]),
    "/tmp/rep_weeks.json": _env([
        {"week_start": "2026-09-14", "floors_met": 0, "bar": 2, "green": False,
         "rollup": {"consecutive_non_green": 1, "auto_weeks_no_operator_input": 9}},
        {"week_start": "2026-09-07", "floors_met": 2, "bar": 2, "green": True,
         "rollup": {"consecutive_non_green": 0, "auto_weeks_no_operator_input": 8}},
        {"week_start": "2026-08-31", "floors_met": 0, "bar": 2, "green": False,
         "rollup": {"consecutive_non_green": 5, "auto_weeks_no_operator_input": 8}},
        {"week_start": "2026-08-24", "floors_met": 0, "bar": 2, "green": False,
         "rollup": {"consecutive_non_green": 4, "auto_weeks_no_operator_input": 8}},
    ]),
    "/tmp/rep_days.json": _env([
        {"day": "2026-09-09", "family": "drill", "floor_met": True, "floor_minutes": 20, "artifact": True, "travel_excused": False},
        {"day": "2026-09-10", "family": "drill", "floor_met": True, "floor_minutes": 15, "artifact": False, "travel_excused": False},
        {"day": "2026-09-12", "family": "milestone", "floor_met": False, "floor_minutes": 0, "artifact": False, "travel_excused": True},
        {"day": "2026-09-16", "family": "drill", "floor_met": False, "floor_minutes": 0, "artifact": False, "travel_excused": False},
    ]),
    "/tmp/steering.json": _env([
        {"issued_at": "2026-09-10T23:10:00+00:00", "action": "WARN_LOCAL", "final_outcome": "reduced", "delivery_tag": "delivered"},
        {"issued_at": "2026-09-11T14:10:00+00:00", "action": "LOCK_WINDOWS", "final_outcome": "backfired", "delivery_tag": "undelivered"},
    ]),
    "/tmp/health_daily.json": _env([
        {"metric_date": "2026-09-09", "metric_type": "sleep_seconds", "value": 7.5 * 3600},
        {"metric_date": "2026-09-10", "metric_type": "sleep_seconds", "value": 6.0 * 3600},
        {"metric_date": "2026-09-16", "metric_type": "sleep_seconds", "value": 6.0 * 3600},
        {"metric_date": "2026-09-09", "metric_type": "hrv_ms", "value": 50},
    ]),
    "/tmp/workouts.json": _env([{"day": "2026-09-09"}, {"day": "2026-09-16"}]),
    "/tmp/skill.json": {"status": "ok", "window": {"days": 90, "core_coding_min": 35, "ai_assisted_coding_min": 900, "hands_on_share": 0.037},
                        "streak": {"core_coding_days": 0}},
    "/tmp/remarks.json": _env([{"key": "operator_context_2026_07_job_engrossed", "created_at": "2026-07-22", "content": "x" * 300}]),
    "/tmp/direction.json": {"status": "ok", "direction": {"version": 3, "domains": {"skill": {"current_phase": "settled-job skill season"}}}},
    "/tmp/program_reviews.json": _env([
        {"created_at": "2026-09-13T08:12:00+00:00", "head": "KILL-GATE STOPPED — no program written"},
        {"created_at": "2026-09-20T08:14:00+00:00", "head": "Weekly program review — week of 2026-09-21"},
    ]),
}


class EvidencePacketTests(unittest.TestCase):
    def _build(self, files):
        return le.build_evidence("2026-06-25", "2026-09-23", loader=lambda p: files.get(p))

    def test_full_packet_values(self):
        ev = self._build(FULL)
        self.assertEqual(ev["window"], {"start": "2026-06-25", "end": "2026-09-23", "days": 90})
        self.assertEqual(ev["program"]["operator_recalibrations"], 1)
        self.assertEqual(ev["program"]["auto_versions"], 1)
        self.assertEqual(ev["program"]["kill_gate_stops"], ["2026-09-13"])
        self.assertEqual(ev["rep_weeks"]["green_rate"], 0.25)
        self.assertEqual(ev["rep_weeks"]["consecutive_non_green_now"], 1)
        self.assertEqual(ev["rep_weeks"]["auto_weeks_no_operator_input"], 9)
        fam = {r["family"]: r for r in ev["rep_days"]["by_family"]}
        self.assertEqual((fam["drill"]["slots"], fam["drill"]["floors"], fam["drill"]["artifacts"]), (3, 2, 1))
        self.assertEqual(fam["drill"]["avg_minutes"], 11.7)
        self.assertEqual(ev["rep_days"]["days_with_floor"], 2)
        self.assertEqual(ev["rep_days"]["longest_floor_streak"], 2)
        self.assertEqual(ev["rep_days"]["travel_excused_days"], 1)
        self.assertEqual(ev["steering"]["episodes"], 2)
        self.assertEqual(ev["steering"]["outcomes"]["backfired"], 1)
        self.assertEqual(ev["steering"]["by_action"]["LOCK_WINDOWS"], 1)
        self.assertEqual(ev["steering"]["delivery"]["undelivered"], 1)
        self.assertEqual(ev["steering"]["evening_share"], 0.5)  # 23:10Z = 19:10 ET
        self.assertEqual(ev["health"]["floor_rate_sleep_ge_7h"], 1.0)   # 09-09 slept 7.5h, floor met
        self.assertEqual(ev["health"]["floor_rate_sleep_lt_6_5h"], 0.5) # 09-10 met, 09-16 missed
        self.assertEqual(ev["health"]["floor_rate_workout_days"], 0.5)  # 09-09 met, 09-16 missed
        self.assertEqual(ev["health"]["floor_rate_rest_days"], 0.5)     # 09-10 met, 09-12 missed
        self.assertEqual(ev["health"]["workout_days"], 2)
        self.assertEqual(ev["skill"], {"hands_on_min": 35, "ai_assisted_min": 900, "hands_on_share": 0.037, "streak_days": 0})
        self.assertEqual(len(ev["context"]["operator_remarks"][0]["excerpt"]), 240)
        self.assertEqual(ev["context"]["direction"], {"version": 3, "skill_phase_excerpt": "settled-job skill season"})
        self.assertEqual(ev["coverage"], {"rep_weeks_in_window": 4, "sparse": False, "missing_inputs": []})

    def test_empty_inputs_degrade_to_nulls_and_missing_list(self):
        ev = self._build({})
        self.assertIsNone(ev["program"])
        self.assertIsNone(ev["health"])
        self.assertEqual(ev["coverage"]["rep_weeks_in_window"], 0)
        self.assertTrue(ev["coverage"]["sparse"])
        self.assertIn("/tmp/rep_weeks.json", ev["coverage"]["missing_inputs"])
        self.assertEqual(len(ev["coverage"]["missing_inputs"]), 10)

    def test_sparse_flag_flips_at_four_rep_weeks(self):
        three = dict(FULL); three["/tmp/rep_weeks.json"] = _env(FULL["/tmp/rep_weeks.json"]["data"][:3])
        self.assertTrue(self._build(three)["coverage"]["sparse"])
        self.assertFalse(self._build(FULL)["coverage"]["sparse"])

    def test_rates_are_null_when_denominator_is_zero(self):
        files = dict(FULL); files["/tmp/workouts.json"] = _env([])
        ev = self._build(files)
        self.assertIsNone(ev["health"]["floor_rate_workout_days"])
        self.assertEqual(ev["health"]["workout_days"], 0)

    def test_errored_envelope_counts_as_missing(self):
        files = dict(FULL); files["/tmp/steering.json"] = {"status": "error", "error": "boom"}
        ev = self._build(files)
        self.assertIsNone(ev["steering"])
        self.assertEqual(ev["coverage"]["missing_inputs"], ["/tmp/steering.json"])

    def test_malformed_day_rows_are_skipped_not_fatal(self):
        files = dict(FULL)
        rows = list(FULL["/tmp/rep_days.json"]["data"]) + [
            {"day": None, "family": "drill", "floor_met": True, "floor_minutes": 5, "artifact": False, "travel_excused": False},
            {"day": "not-a-date", "family": "drill", "floor_met": True, "floor_minutes": 5, "artifact": False, "travel_excused": False},
        ]
        files["/tmp/rep_days.json"] = _env(rows)
        ev = self._build(files)
        self.assertEqual(ev["rep_days"]["days_with_floor"], 2)      # the two bad rows add no floor day
        self.assertEqual(ev["rep_days"]["longest_floor_streak"], 2)
        fam = {r["family"]: r for r in ev["rep_days"]["by_family"]}
        self.assertEqual(fam["drill"]["slots"], 5)                  # they still count as slots
        self.assertIn("?", [r["weekday"] for r in ev["rep_days"]["by_weekday"]])


class SteeringEveningShareTests(unittest.TestCase):
    """B1: Postgres `issued_at::text` renders a bare +00 offset that
    Python 3.10's fromisoformat rejects; a silent `except: pass` used to
    count every such row as not-evening instead of unmeasurable."""

    def test_bare_offset_rows_parse_and_evening_share_is_correct(self):
        rows = [
            # 19:02:03 UTC -4 (EDT) = 15:02 ET -> not evening
            {"issued_at": "2026-06-26 19:02:03.826675+00", "action": "WARN_LOCAL",
             "final_outcome": "reduced", "delivery_tag": "delivered"},
            # 23:30:00 UTC -4 (EDT) = 19:30 ET -> evening
            {"issued_at": "2026-06-26 23:30:00+00", "action": "WARN_LOCAL",
             "final_outcome": "reduced", "delivery_tag": "delivered"},
        ]
        result = le._steering(rows)
        self.assertEqual(result["evening_share"], 0.5)
        self.assertEqual(result["unparsed_issued_at"], 0)

    def test_unparseable_issued_at_makes_evening_share_null(self):
        rows = [
            {"issued_at": "2026-06-26 19:02:03.826675+00", "action": "WARN_LOCAL",
             "final_outcome": "reduced", "delivery_tag": "delivered"},
            {"issued_at": "2026-06-26 23:30:00+00", "action": "WARN_LOCAL",
             "final_outcome": "reduced", "delivery_tag": "delivered"},
            {"issued_at": "garbage", "action": "LOCK_WINDOWS",
             "final_outcome": "backfired", "delivery_tag": "undelivered"},
        ]
        result = le._steering(rows)
        self.assertIsNone(result["evening_share"])
        self.assertEqual(result["unparsed_issued_at"], 1)
        self.assertEqual(result["episodes"], 3)


class ProgramOperatorSourceTests(unittest.TestCase):
    """B2: live `source` values are `operator_review`/`operator_bootstrap`,
    never the `operator_recalibration` literal the old check special-cased."""

    def test_operator_review_source_counts_as_recalibration(self):
        rows = [
            {"id": "p1", "status": "active", "source": "operator_review", "valid_from": "2026-08-01",
             "valid_until": "2026-08-07", "has_operator_input": False, "recompose_count": 0},
            {"id": "p0", "status": "active", "source": "claude_program_review", "valid_from": "2026-07-22",
             "valid_until": "2026-07-27", "has_operator_input": False, "recompose_count": 0},
        ]
        result = le._program(rows)
        self.assertEqual(result["operator_recalibrations"], 1)
        self.assertEqual(result["auto_versions"], 1)


class RepWeeksExcusalTests(unittest.TestCase):
    """B3: a week can read green only because travel-excused days reduced
    the verifier's effective bar, not because floors were actually met —
    the packet must say so explicitly instead of leaving floor_met=0 mute."""

    def test_excused_days_and_green_by_excusal_on_full_fixture(self):
        ev = le.build_evidence("2026-06-25", "2026-09-23", loader=lambda p: FULL.get(p))
        rows = {r["week_start"]: r for r in ev["rep_weeks"]["rows"]}
        self.assertEqual(rows["2026-09-07"]["excused_days"], 1)  # the 09-12 travel_excused row
        self.assertFalse(rows["2026-08-31"]["green_by_excusal"])

    def test_rep_day_rows_none_gives_zero_excused_days(self):
        result = le._rep_weeks(FULL["/tmp/rep_weeks.json"]["data"], None)
        self.assertTrue(all(r["excused_days"] == 0 for r in result["rows"]))


if __name__ == "__main__":
    unittest.main()
