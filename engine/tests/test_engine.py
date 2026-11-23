"""End-to-end analysis with synthetic providers. Never emitted as a real report."""
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.__main__ import analyze
from engine.reporting import render


DAY = date(2026, 3, 30)
TEHRAN = timezone(timedelta(hours=3, minutes=30))


def synthetic_bars():
    out = []
    for i in range(70):
        d = DAY - timedelta(days=69 - i)
        out.append(dict(date=str(d), open=100 + i, high=100.4 + i, low=99.6 + i,
                        close=100 + i, raw_close=100 + i,
                        volume=100 if i < 59 else 300,
                        value=(100 if i < 59 else 300) * (100 + i) * 1_000_000,
                        adjusted=True, fetched_at=datetime.now(timezone.utc).isoformat(),
                        valid=True, source="SYNTHETIC"))
    return out


class FakeProvider:
    def __init__(self, bars):
        self.bars = bars

    def universe(self):
        return [dict(code="1", symbol="آزمون", sector="آزمایشی",
                     bid=159, ask=0, bid_size=100, ask_size=0,
                     ceiling=180, floor=140, state=None, last_price=159)]

    def overview(self):
        return dict(index=1000, equal_weight=500, change=1.0,
                    equal_weight_change=2.0, turnover=10**12,
                    market_state="بسته", date=str(DAY))

    def history(self, code):
        return self.bars

    def board(self, code):
        return dict(date=str(DAY), buyer_power=2.0, net_retail_value=1000,
                    net_legal_value=-1000, buy_per_capita=4.0, sell_per_capita=2.0)


class FakeCodal:
    def disclosures(self, symbol):
        return []


class EngineIntegrationTests(unittest.TestCase):
    def test_full_report_pipeline(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        storage = Path(tmp.name)
        now = datetime(DAY.year, DAY.month, DAY.day, 15, 0, tzinfo=TEHRAN)
        report = analyze(now, storage, FakeProvider(synthetic_bars()), FakeCodal(), {})
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["date"], str(DAY))
        self.assertEqual(report["scanned"], 1)
        self.assertEqual(len(report["signals"]), 1)
        signal = report["signals"][0]
        self.assertLess(signal["stop_loss"], signal["entry_low"])
        self.assertFalse(signal["fundamentals"]["available"])
        self.assertIsNone(signal["fundamentals"]["metrics"].get("net_income"))
        self.assertEqual(signal["tablovani"]["net_retail_value"], 1000)
        self.assertTrue(report["data_quality"]["valid"] >= 1)
        self.assertIn("چرا انتخاب شد", report["narrative"])
        render(storage, report)
        self.assertIn("آزمون", (storage / "report.html").read_text(encoding="utf-8"))

    def test_calendar_and_hours_guard(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        now = datetime(DAY.year, DAY.month, DAY.day, 8, 0, tzinfo=TEHRAN)
        report = analyze(now, Path(tmp.name), FakeProvider(synthetic_bars()), FakeCodal(), {})
        self.assertEqual(report["status"], "closed")
        self.assertEqual(report["signals"], [])


if __name__ == "__main__":
    unittest.main()
