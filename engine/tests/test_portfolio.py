from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from engine.portfolio import Ledger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = Ledger(Path(tmp.name) / "test.sqlite3")

    def test_manual_ledger_fees_and_rollback(self):
        self.ledger.trade("buy", "A", 10, 80, 10, "2020-01-02", "one")
        self.ledger.trade("buy", "A", 10, 80, 10, "2020-01-02", "one")
        with self.assertRaises(ValueError):
            self.ledger.trade("sell", "A", 2, 90, day="2020-01-01")
        self.ledger.trade("sell", "A", 4, 100, 2, "2020-01-03")
        result = self.ledger.snapshot({"A": 110})
        self.assertEqual(result["totals"], {"market_value":660,"realized":74,"unrealized":174})
        self.assertIsNone(self.ledger.snapshot({})["totals"]["market_value"])

    def test_alerts(self):
        self.ledger.watch("A", 75, 100)
        self.assertEqual(self.ledger.snapshot({"A": 75})["alerts"][0]["kind"], "floor")
        self.assertEqual(self.ledger.snapshot({})["alerts"], [])
        self.ledger.unwatch("A")
        self.assertEqual(self.ledger.snapshot({"A": 100})["alerts"], [])

    def test_forward_observations(self):
        s = dict(id="a",symbol="A",date="2020-01-01",expires="2020-01-08",entry_low=90,entry_high=100,
                 stop_loss=80,target1=120)
        self.ledger.observe_signals([s,s],s["date"])
        self.ledger.mark_signals({"A":95},s["date"])
        self.assertEqual(self.ledger.performance()["signals"][0]["state"], "pending")
        self.ledger.mark_signals({"A":100},"2020-01-02")
        self.ledger.mark_signals({"A":130},"2020-01-02")
        self.assertEqual(self.ledger.performance()["closed"], 0)
        outcome = self.ledger.mark_signals({"A":70},"2020-01-03")
        self.assertEqual(outcome["closed"], 1)
        self.assertAlmostEqual(outcome["average_return"], -0.30)

