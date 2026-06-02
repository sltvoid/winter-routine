import unittest

from scripts import extract, payloads


class BrowserActivityExtractionTests(unittest.TestCase):
    def test_browser_rows_normalize_compact_host_aggregates(self):
        rows = extract._browser_rows(
            {
                "data": [
                    {
                        "host": "GitHub.com",
                        "canonical_device": "macbook",
                        "browser": "firefox",
                        "minutes": "12.34",
                        "event_count": 4,
                        "path_hints": ["/owner/repo", "/owner/repo/actions", None, "/extra"],
                    },
                    {"host": "", "minutes": 5},
                    {"host": "youtube.com", "active_seconds": 90},
                ]
            }
        )

        self.assertEqual("github.com", rows[0]["host"])
        self.assertEqual(12.3, rows[0]["minutes"])
        self.assertEqual(["/owner/repo", "/owner/repo/actions", "/extra"], rows[0]["path_hints"])
        self.assertEqual(1.5, rows[1]["minutes"])


class BrowserArtifactConversionTests(unittest.TestCase):
    def test_browser_activity_enriches_without_double_counting_browser_app(self):
        data = {
            "analyzed_date": "2026-06-01",
            "top_prod": {
                "app": "Firefox",
                "minutes": 120,
                "category": "Browsers",
                "devices": {"windows": 120},
            },
            "browser_rows": [
                {
                    "host": "github.com",
                    "minutes": 30,
                    "device": "windows",
                    "browser": "firefox",
                    "path_hints": ["/owner/repo"],
                },
                {
                    "host": "github.com",
                    "minutes": 10,
                    "device": "windows",
                    "browser": "firefox",
                    "path_hints": ["/owner/repo/actions"],
                },
                {"host": "claude.ai", "minutes": 20, "device": "windows", "browser": "firefox"},
                {"host": "youtube.com", "minutes": 40, "device": "windows", "browser": "firefox"},
            ],
        }

        conversion = payloads._artifact_conversion(data, productive_hours=3.0)

        self.assertEqual(120, conversion["repo_browser_minutes_rescuetime"])
        self.assertEqual(30.0, conversion["browser_repo_minutes"])
        self.assertEqual(10.0, conversion["browser_build_ci_minutes"])
        self.assertEqual(20.0, conversion["ai_tool_minutes"])
        self.assertEqual(40.0, conversion["artifact_minutes"])
        self.assertEqual(2.0, conversion["artifact_to_ai_ratio"])
        self.assertEqual([], conversion["top_artifact_tools"])
        self.assertEqual(["github.com", "github.com"], [row["host"] for row in conversion["browser_artifact_evidence"]])
        self.assertEqual(["youtube.com"], [row["host"] for row in conversion["browser_distraction_evidence"]])
        self.assertIn("not added to RescueTime totals", conversion["source_quality"]["double_counting_policy"]["notes"])

    def test_briefing_base_marks_browser_activity_as_source_when_present(self):
        data = {
            "analyzed_date": "2026-06-01",
            "browser_rows": [{"host": "github.com", "minutes": 15}],
            "device_totals": [],
            "goal_context": {},
        }

        briefing = payloads.build_briefing_base(
            data,
            date="2026-06-02",
            day_of_week="Tuesday",
            analyzed_date="2026-06-01",
            analyzed_day_of_week="Monday",
        )

        self.assertIn("browser_activity", briefing["sources_used"])
        self.assertEqual("ok", briefing["source_quality"]["browser_activity"]["status"])


if __name__ == "__main__":
    unittest.main()
