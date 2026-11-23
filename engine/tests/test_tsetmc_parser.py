"""Deterministic parser tests for real TSETMC payload shapes. No network."""
import unittest

from engine.data.quality import validate_bars
from engine.providers.common import ProviderError
from engine.providers.tsetmc import parse_history


def record(day, close, **overrides):
    row = dict(insCode="42", dEven=day, priceFirst=100, priceMax=101,
               priceMin=99, pClosing=close, pDrCotVal=100,
               priceYesterday=100, qTotTran5J=10, qTotCap=1000)
    row.update(overrides)
    return row


class TsetmcParserTests(unittest.TestCase):
    def test_official_close_widens_bar_without_changing_reported_levels(self):
        records = [
            record(20261120, 101.5),  # outside the reported high
            record(20261121, 98.5),   # outside the reported low
            record(20261122, 100),
        ]
        bars = parse_history(records)
        valid, why = validate_bars(bars, "2026-11-22", min_bars=3)
        self.assertTrue(valid, why)
        for bar in bars:
            self.assertLessEqual(bar["low"], bar["close"])
            self.assertGreaterEqual(bar["high"], bar["close"])
        self.assertEqual([bar["raw_close"] for bar in bars], [101.5, 98.5, 100])

    def test_no_trade_session_is_skipped_not_fabricated(self):
        records = [record(20261120, 100), record(20261121, 100,
                   qTotTran5J=0, qTotCap=0), record(20261122, 101)]
        bars = parse_history(records)
        self.assertEqual([bar["date"] for bar in bars],
                         ["2026-11-20", "2026-11-22"])

    def test_duplicate_dates_are_rejected(self):
        with self.assertRaises(ProviderError):
            parse_history([record(20261122, 100), record(20261122, 101)])


if __name__ == "__main__":
    unittest.main()
