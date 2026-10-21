"""The morning briefing's sleep/HRV must be the LATEST SYNCED NIGHT under the
wake-date convention, at night grain, labelled with its age (2026-10-21).

Before: extract.py read `sleep_seconds` (the calendar-day total) from
YESTERDAY's row, which is the night before last, and the note said "Sleep was
X h" with no date. The phone syncs health 08:30-15:00 most days, so at 06:35
last night is usually absent; the honest answer is the newest night plus its age.
"""
import unittest

from scripts import extract, payloads


def _baseline(**row):
    return {"status": "ok", "data": [row]}


class NightFieldsTests(unittest.TestCase):
    def test_lagged_morning_reads_the_newest_night_with_its_age(self):
        f = extract._night_fields(_baseline(night_wake_date="2026-10-21", nights_old=1,
                                            sleep_night_hours=8.328, night_hrv_ms=83.43,
                                            night_rhr_bpm=None, avg_hours=6.431), {})
        self.assertEqual(f["sleep_h"], 8.3)
        self.assertEqual(f["sleep_7d_avg"], 6.4)
        self.assertEqual(f["sleep_as_of"], "2026-10-21")
        self.assertEqual(f["sleep_nights_old"], 1)
        self.assertEqual(f["hrv_night"], 83.4)
        self.assertIsNone(f["rhr_night"])

    def test_nothing_synced_in_a_week_is_unavailable_not_zero_hours(self):
        f = extract._night_fields(_baseline(night_wake_date=None, nights_old=None, sleep_night_hours=None,
                                            night_hrv_ms=None, night_rhr_bpm=None, avg_hours=None), {})
        self.assertEqual(f["sleep_h"], 0)
        self.assertIsNone(f["sleep_as_of"])
        self.assertIsNone(f["sleep_nights_old"])

    def test_old_shape_baseline_falls_back_to_todays_night_row_only(self):
        # A pre-change /tmp/sleep_baseline.json ({avg_hours} only): never fall back
        # to yesterday's row (that is the night before last) — only today's night.
        today = {"data": [{"metric_type": "sleep_night_asleep_seconds", "value": 25200}]}
        f = extract._night_fields({"data": [{"avg_hours": 6.5}]}, today)
        self.assertEqual((f["sleep_h"], f["sleep_nights_old"]), (7.0, 0))
        f = extract._night_fields({"data": [{"avg_hours": 6.5}]}, {})
        self.assertEqual(f["sleep_h"], 0)

    def test_string_numbers_from_json_are_accepted(self):
        f = extract._night_fields(_baseline(night_wake_date="2026-10-20", nights_old="2",
                                            sleep_night_hours="7.1", night_hrv_ms="63.7",
                                            night_rhr_bpm="64", avg_hours="6.4"), {})
        self.assertEqual((f["sleep_h"], f["sleep_nights_old"], f["rhr_night"]), (7.1, 2, 64.0))


class SleepNoteTests(unittest.TestCase):
    def test_today_night_reads_as_last_night(self):
        note = payloads._sleep_note({"sleep_nights_old": 0, "sleep_as_of": "2026-10-21", "hrv_night": 83.4},
                                    8.3, 6.4)
        self.assertTrue(note.startswith("Last night's sleep was 8.3h"))
        self.assertIn("HRV 83.4 ms", note)

    def test_lagged_night_names_its_age_and_never_says_last_night(self):
        note = payloads._sleep_note({"sleep_nights_old": 1, "sleep_as_of": "2026-10-21", "hrv_night": 83.4},
                                    8.3, 6.4)
        self.assertIn("As of the night before last (wake date 2026-10-21)", note)
        self.assertNotIn("Last night", note)
        note = payloads._sleep_note({"sleep_nights_old": 3, "sleep_as_of": "2026-10-19"}, 7.0, 6.4)
        self.assertIn("As of 3 nights ago (wake date 2026-10-19)", note)

    def test_unavailable_says_not_synced(self):
        note = payloads._sleep_note({}, 0, 6.4)
        self.assertIn("not synced", note)
        self.assertNotIn("0.0h", note)


class HealthSummaryTests(unittest.TestCase):
    def test_summary_carries_the_age_fields(self):
        base = payloads.build_briefing_base(
            {"sleep_h": 8.3, "sleep_7d_avg": 6.4, "sleep_as_of": "2026-10-21", "sleep_nights_old": 1,
             "hrv_night": 83.4}, date="2026-10-22", day_of_week="Thursday")
        hs = base["health_summary"]
        self.assertEqual((hs["sleep_as_of"], hs["sleep_nights_old"], hs["hrv_night_ms"]), ("2026-10-21", 1, 83.4))
        self.assertEqual(hs["sleep_hours"], 8.3)
        self.assertIn("night before last", hs["sleep_note"])


class RunbookReadTests(unittest.TestCase):
    def test_the_sleep_read_is_night_grain_wake_dated_and_et_anchored(self):
        text = open("morning-briefing.md", encoding="utf-8").read()
        line = next(l for l in text.splitlines() if "/tmp/sleep_baseline.json" in l and "query_raw_sql" in l)
        self.assertIn("sleep_night_asleep_seconds", line)
        self.assertIn("night_wake_date", line)
        self.assertIn("nights_old", line)
        self.assertIn("$TODAY_ET", line)
        self.assertNotIn("CURRENT_DATE", line)
        self.assertNotIn("'sleep_seconds'", line)


if __name__ == "__main__":
    unittest.main()
