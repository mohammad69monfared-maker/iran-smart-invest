"""Synthetic provider fixtures only; no trading signals are generated here."""
import unittest
from engine.providers import Codal, ProviderError, Tsetmc, market_context
from engine.providers.tsetmc import parse_history


def candle(day, price, prior):
    return dict(dEven=day, pClosing=price, priceFirst=price, priceMax=price, priceMin=price,
                pDrCotVal=price, priceYesterday=prior, qTotTran5J=300, qTotCap=price*300)


class ProvidersTest(unittest.TestCase):
    def test_adjustment_uses_only_included_dates(self):
        rows = [candle(20260101, 100, 100), candle(20260102, 50, 50)]
        self.assertEqual(parse_history(rows)[0]["close"], 50)
        self.assertEqual(parse_history(rows)[0]["raw_close"], 100)
        self.assertEqual(parse_history(rows, "2026-01-01")[0]["close"], 100)

    def test_incomplete_dates_prices_and_duplicates(self):
        for rows in ([candle(20260230, 100, 100)], [candle(20260101, 0, 0)],
                     [candle(20260101, 100, 100)]*2, []):
            with self.subTest(rows=rows), self.assertRaises(ProviderError):
                parse_history(rows)

    def test_unknown_queue_not_false(self):
        bars = parse_history([candle(20260101, 100, 100)])
        context = market_context({"state":"A","date":"2025-12-31"}, bars)
        self.assertIsNone(context["tradable"])
        self.assertIsNone(context["buy_queue"])
        self.assertIsNone(context["liquid"])

    def test_halt_queue_and_buyer_date(self):
        bars = parse_history([candle(20260101, 100, 100)])
        snap = dict(state="I",date="2026-01-01",floor=90,ceiling=110,
                    bid=0,ask=90,bid_size=0,ask_size=10)
        context = market_context(snap, bars, dict(date="2025-12-30",buyer_power=2))
        self.assertFalse(context["tradable"])
        self.assertTrue(context["sell_queue"])
        self.assertIsNone(context["buyer_power"])

    def test_disclosures_exact_symbol_and_safe_url(self):
        item = dict(Symbol="الف",PublishDateTime="1404/01/01",Title="اطلاعیه",Url="//other.example")
        data = Codal(lambda url: {"Letters":[item,dict(item,Symbol="ب")]}).disclosures("الف")
        self.assertEqual(len(data), 1)
        self.assertIsNone(data[0]["url"])

    def test_universe_identity_and_missing(self):
        data = Tsetmc(lambda url: {"marketwatch":[dict(insCode="123",l18="الف")]}).universe()
        self.assertEqual(data[0]["code"], "123")
        with self.assertRaises(ProviderError):
            Tsetmc(lambda url: {"unexpected":[]}).universe()


if __name__ == "__main__":
    unittest.main()

