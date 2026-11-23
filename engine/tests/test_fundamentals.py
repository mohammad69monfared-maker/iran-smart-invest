"""Synthetic Codal HTML only; never used by the operational engine."""
import unittest

from engine.data import FundamentalAnalyzer


def report_html(period, revenue, income):
    return f"""<html><body><table>
      <tr><td></td><td>{period}</td></tr>
      <tr><td>درآمدهای عملیاتی</td><td>{revenue:,}</td></tr>
      <tr><td>سود (زیان) خالص</td><td>{income:,}</td></tr>
      <tr><td>سود (زیان) خالص هر سهم</td><td>12</td></tr>
      </table></body></html>"""


class FakeCodal:
    def __init__(self, letters=None, fail=False):
        self.letters = letters or []
        self.fail = fail

    def disclosures(self, symbol):
        if self.fail:
            raise RuntimeError("offline")
        return self.letters


class FundamentalTests(unittest.TestCase):
    def setUp(self):
        self.letters = [
            dict(title="گزارش عملکرد 1403/01/01", published_at="1403/04/01",
                 period="1403/01/01", url="https://codal.ir/old"),
            dict(title="گزارش عملکرد 1404/01/01", published_at="1404/04/01",
                 period="1404/01/01", url="https://codal.ir/new"),
        ]
        self.pages = {
            "https://codal.ir/new": report_html("1404/01/01", 1_000_000, 100_000),
            "https://codal.ir/old": report_html("1403/01/01", 800_000, 60_000),
        }

    def test_comparable_growth(self):
        analyzer = FundamentalAnalyzer(FakeCodal(self.letters), self.pages.get)
        result = analyzer.analyze("TEST")
        self.assertTrue(result["available"])
        self.assertEqual(result["period"], "1404/01/01")
        self.assertEqual(result["metrics"]["operating_revenue"], 1_000_000)
        self.assertAlmostEqual(result["growth"]["operating_revenue"], 0.25)
        self.assertAlmostEqual(analyzer.earnings_growth(result), 100_000 / 60_000 - 1)

    def test_missing_data_is_declared_not_guessed(self):
        analyzer = FundamentalAnalyzer(FakeCodal([]), self.pages.get)
        result = analyzer.analyze("TEST")
        self.assertFalse(result["available"])
        self.assertIsNone(analyzer.earnings_growth(result))
        self.assertIsNone(result["period"])

    def test_provider_failure_and_bad_url(self):
        analyzer = FundamentalAnalyzer(FakeCodal(fail=True), self.pages.get)
        self.assertFalse(analyzer.analyze("TEST")["available"])
        bad = [dict(title="گزارش 1404/01/01", published_at="1404/04/01",
                    period="1404/01/01", url="https://evil.example/x")]
        analyzer = FundamentalAnalyzer(FakeCodal(bad), self.pages.get)
        self.assertFalse(analyzer.analyze("TEST")["available"])

    def test_one_period_has_no_growth(self):
        analyzer = FundamentalAnalyzer(FakeCodal(self.letters[1:]), self.pages.get)
        result = analyzer.analyze("TEST")
        self.assertTrue(result["available"])
        self.assertIsNone(analyzer.earnings_growth(result))
        self.assertEqual(result["growth"], {})


if __name__ == "__main__":
    unittest.main()
