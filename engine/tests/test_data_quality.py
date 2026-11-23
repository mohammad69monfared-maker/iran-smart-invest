"""Synthetic fixtures only; these tests never produce operational data."""
import unittest
from datetime import date, timedelta

from engine.data import QualityTracker, validate_bars


def bars(n=60, as_of="2026-03-30"):
    end = date.fromisoformat(as_of)
    return [dict(date=str(end - timedelta(days=n - 1 - i)),
                 open=100 + i, high=101 + i, low=99 + i, close=100 + i,
                 volume=100, value=100000.0, adjusted=True, fetched_at=as_of)
            for i in range(n)]


class QualityTests(unittest.TestCase):
    def test_accepts_complete_window(self):
        rows = bars()
        valid, why = validate_bars(rows, "2026-03-30")
        self.assertTrue(valid, why)

    def test_rejects_future_stale_and_short(self):
        rows = bars()
        self.assertFalse(validate_bars(rows[:-1], rows[-1]["date"])[0])
        self.assertFalse(validate_bars(rows[:5], rows[4]["date"])[0])
        rows[-1]["date"] = "2026-04-01"
        self.assertIn("آینده", validate_bars(rows, "2026-03-30")[1])
        rows[-1]["date"] = "2026-03-30"
        rows[-1]["adjusted"] = False
        self.assertFalse(validate_bars(rows, "2026-03-30")[0])

    def test_rejects_bad_prices_and_duplicates(self):
        rows = bars()
        rows[3]["low"] = rows[3]["high"] + 1
        self.assertFalse(validate_bars(rows, rows[-1]["date"])[0])
        rows = bars()
        rows[5]["date"] = rows[4]["date"]
        self.assertFalse(validate_bars(rows, rows[-1]["date"])[0])
        rows = bars()
        rows[-1]["volume"] = float("nan")
        self.assertFalse(validate_bars(rows, rows[-1]["date"])[0])

    def test_tracker_summary_and_bounds(self):
        tracker = QualityTracker()
        tracker.record(source="TSETMC", symbol="X", fetched_at="t", data_time="d",
                       valid=True, completeness=0.8)
        tracker.record(source="TSETMC", symbol="Y", fetched_at="t", data_time=None,
                       valid=False, completeness=0.2, errors=("stale",))
        summary = tracker.summary()
        self.assertEqual(summary["checked"], 2)
        self.assertEqual(summary["valid"], 1)
        self.assertEqual(summary["by_source"]["TSETMC"]["invalid"], 1)
        self.assertEqual(summary["errors"], {"stale": 1})
        with self.assertRaises(ValueError):
            tracker.record(source="x", fetched_at="t", data_time="d", valid=True, completeness=2)


if __name__ == "__main__":
    unittest.main()
