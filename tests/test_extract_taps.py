import os
import unittest
from unittest.mock import patch

from scripts import extract


class OperatorTapsTests(unittest.TestCase):
    def _load_factory(self, llm_rows, finance_rows=None):
        def fake_load(path, default):
            if path == "/tmp/operator_taps_llm.json":
                return {"data": llm_rows}
            if path == "/tmp/operator_taps_finance.json":
                # The finance read is retired; a stale file on disk must be ignored.
                return {"data": finance_rows or []}
            return default
        return fake_load

    def test_is_new_when_pending_since_is_yesterday_or_later(self):
        rows = [
            {"kind": "ticket_proposed", "ref": "t-old", "pending_since": "2026-09-01", "action": "Decide"},
            {"kind": "goal_policy_draft", "ref": "g-new", "pending_since": "2026-09-22", "action": "Approve"},
            {"kind": "ticket_research_complete", "ref": "t-today", "pending_since": "2026-09-23", "action": "Decide"},
        ]
        with patch.object(extract, "_load", side_effect=self._load_factory(rows)), \
             patch.dict(os.environ, {"YESTERDAY_ET": "2026-09-22"}):
            taps = extract._operator_taps()
        self.assertEqual([t["ref"] for t in taps], ["t-old", "g-new", "t-today"])  # oldest first
        self.assertEqual([t["is_new"] for t in taps], [False, True, True])

    def test_missing_anchor_mutes_every_tap(self):
        rows = [{"kind": "ticket_proposed", "ref": "t1", "pending_since": "2026-09-23", "action": "Decide"}]
        env = {k: v for k, v in os.environ.items() if k != "YESTERDAY_ET"}
        with patch.object(extract, "_load", side_effect=self._load_factory(rows)), \
             patch.dict(os.environ, env, clear=True):
            taps = extract._operator_taps()
        self.assertEqual(taps[0]["is_new"], False)

    def test_finance_relink_rows_are_no_longer_folded(self):
        finance = [{"item_id": "item-1", "pending_since": "2026-09-23"}]
        with patch.object(extract, "_load", side_effect=self._load_factory([], finance)), \
             patch.dict(os.environ, {"YESTERDAY_ET": "2026-09-22"}):
            taps = extract._operator_taps()
        self.assertEqual(taps, [])

    def test_counts_ride_data_json(self):
        rows = [
            {"kind": "ticket_proposed", "ref": "a", "pending_since": "2026-09-01", "action": "Decide"},
            {"kind": "ticket_proposed", "ref": "b", "pending_since": "2026-09-23", "action": "Decide"},
        ]
        with patch.object(extract, "_load", side_effect=self._load_factory(rows)), \
             patch.dict(os.environ, {"YESTERDAY_ET": "2026-09-22"}):
            taps = extract._operator_taps()
            counts = extract._tap_counts(taps)
        self.assertEqual(counts, {"operator_taps_total": 2, "operator_taps_new": 1})


if __name__ == "__main__":
    unittest.main()
