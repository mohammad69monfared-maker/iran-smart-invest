"""Offline tests for public-market adapters. No network, no invented prices."""
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from engine.providers import global_markets as gm


def dated_bars(days=70, first=date(2026, 9, 1)):
    bars = []
    for i in range(days):
        day = str(first + timedelta(days=i))
        base = 100 + i
        bars.append(dict(date=day, open=base, high=base + 2, low=base - 2,
                         close=base + 1, volume=100 + i, value=(100 + i) * base,
                         adjusted=True, valid=True, source="TEST"))
    return bars


class GlobalMarketTests(unittest.TestCase):
    def test_binance_bars_parse_real_payload_shape(self):
        rows = []
        for i in range(3):
            rows.append([1795392000000 + i * 86400000, "100", "102", "99",
                         "101", "12.5"] + [0] * 6)
        with patch.object(gm, "get_json", return_value=rows):
            bars = gm.binance_bars("BTCUSDT")
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[-1]["close"], 101.0)
        self.assertEqual(bars[-1]["source"], "Binance")
        self.assertAlmostEqual(bars[-1]["value"], 101 * 12.5)

    def test_yahoo_bars_skip_null_sessions(self):
        payload = {"chart": {"result": [{
            "timestamp": [1795392000, 1795478400],
            "indicators": {"quote": [{
                "open": [100, None], "high": [102, None], "low": [99, None],
                "close": [101, None], "volume": [10, 0]}]}}]}}
        with patch.object(gm, "get_json", return_value=payload):
            bars = gm.yahoo_bars("GC=F")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["close"], 101.0)

    def test_analyze_reports_unavailable_instead_of_guessing(self):
        with patch.object(gm, "bars_for", side_effect=gm.ProviderError("offline")):
            result = gm.analyze_global()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["signals"], [])
        self.assertTrue(result["instruments"])
        self.assertTrue(all(not v["ok"] for v in result["instruments"].values()))

    def test_analyze_includes_technical_summary_without_signal(self):
        bars = dated_bars()
        with patch.object(gm, "bars_for", return_value=bars):
            result = gm.analyze_global()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["summaries"]), len(gm.CATALOG))
        self.assertIn("rsi14", result["summaries"][0]["technical"])
        # All items share the same flat synthetic bar; no trend is expected.
        self.assertTrue(all(not item.get("signal") for item in result["summaries"]))


if __name__ == "__main__":
    unittest.main()
