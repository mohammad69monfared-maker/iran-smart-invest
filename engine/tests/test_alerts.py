"""Alert tests: levels come from the report, quotes are supplied by the test."""
import tempfile
import unittest
from pathlib import Path

from engine.alerts import check, classify


SIGNAL = {
    "id": "test-1", "symbol": "BTC/USDT", "score": 80,
    "source": "Binance", "market": "رمز ارز",
    "entry_low": 100, "entry_high": 110, "stop_loss": 90,
    "target1": 130, "target2": 150, "expires": "2099-12-31",
}


class AlertTests(unittest.TestCase):
    def test_classify_levels(self):
        self.assertEqual(classify(SIGNAL, 105, "2026-11-23")[0], "entry")
        self.assertEqual(classify(SIGNAL, 88, "2026-11-23")[0], "stop")
        self.assertEqual(classify(SIGNAL, 135, "2026-11-23")[0], "target1")
        self.assertEqual(classify(SIGNAL, 160, "2026-11-23")[0], "target2")
        self.assertEqual(classify(SIGNAL, 120, "2026-11-23")[0], None)
        self.assertEqual(classify(SIGNAL, 105, "2100-01-01")[0], "expired")

    def test_check_uses_supplied_quote_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "alerts.sqlite3"
            report = {"signals": [], "global": {"signals": [SIGNAL]}}
            first = check(report, db, global_quotes={"BTC/USDT": 105.0})
            self.assertEqual(len(first), 1)
            self.assertIn("ورود", first[0])
            self.assertEqual(check(report, db, global_quotes={"BTC/USDT": 105.0}), [])

    def test_no_quote_means_no_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = {"signals": [], "global": {"signals": [SIGNAL]}}
            self.assertEqual(check(report, Path(tmp) / "a.sqlite3", global_quotes={}), [])


if __name__ == "__main__":
    unittest.main()
