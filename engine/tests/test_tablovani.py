"""Synthetic fixtures only; no operational signal is produced."""
import unittest
from datetime import date, timedelta

from engine.data import tablovani


def bars(n=21, volume=100, last_volume=100, price=100):
    end = date(2026, 3, 30)
    return [dict(date=str(end - timedelta(days=n - 1 - i)), open=price, high=price + 1,
                 low=price - 1, close=price, raw_close=price,
                 volume=last_volume if i == n - 1 else volume,
                 value=(last_volume if i == n - 1 else volume) * price,
                 adjusted=True)
            for i in range(n)]


class TablovaniTests(unittest.TestCase):
    def test_known_flows_and_volume_ratio(self):
        board = dict(date="2026-03-30", net_retail_value=1500, net_legal_value=-1500,
                     buyer_power=1.4, buy_per_capita=2.8, sell_per_capita=2.0)
        snap = dict(date="2026-03-30", bid=105, ask=0, bid_size=500, ask_size=0,
                    ceiling=105, floor=95)
        result = tablovani(bars(last_volume=300), board, snap, "2026-03-30")
        self.assertEqual(result["net_retail_value"], 1500)
        self.assertEqual(result["net_legal_value"], -1500)
        self.assertAlmostEqual(result["volume_ratio"], 3.0)
        self.assertTrue(result["suspicious_volume"])
        self.assertTrue(result["buy_queue"])
        self.assertFalse(result["sell_queue"])
        self.assertIn("صف خرید", " ".join(result["notes"]))

    def test_stale_board_and_unknown_book_are_none(self):
        board = dict(date="2026-03-29", net_retail_value=99)
        snap = dict(date="2026-03-29", bid=1, ask=1, bid_size=1, ask_size=1, ceiling=2, floor=1)
        result = tablovani(bars(), board, snap, "2026-03-30")
        self.assertIsNone(result["net_retail_value"])
        self.assertIsNone(result["buy_queue"])
        self.assertIsNone(result["sell_queue"])
        self.assertAlmostEqual(result["volume_ratio"], 1.0)

    def test_rejects_wrong_date(self):
        with self.assertRaises(ValueError):
            tablovani(bars(), {}, {}, "2026-03-29")


if __name__ == "__main__":
    unittest.main()
