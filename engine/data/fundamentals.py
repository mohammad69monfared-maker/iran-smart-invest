"""Fundamental analysis built only from parsed Codal report cells.

If a report cannot be retrieved or parsed, availability is reported as False.
No figure is ever estimated, extrapolated or fabricated.
"""
from ..providers.common import now
from ..providers.statements import clean, fiscal_period, get_report_html, metrics_from_report


def _growth(current, previous):
    if current is None or previous in (None, 0) or previous <= 0:
        return None
    return current / previous - 1


class FundamentalAnalyzer:
    def __init__(self, codal, fetch_html=get_report_html):
        self.codal = codal
        self.fetch_html = fetch_html

    def analyze(self, symbol, disclosures=None):
        received = now()
        result = dict(symbol=symbol, available=False, period=None, metrics={},
                      growth={}, disclosures=[], source="Codal", fetched_at=received,
                      reason="گزارش مالی قابلاستفاده یافت نشد")
        try:
            letters = disclosures if disclosures is not None else self.codal.disclosures(symbol)
        except Exception:
            letters = []
            result["reason"] = "دریافت اطلاعیه کدال ناموفق بود"
        result["disclosures"] = [dict(title=l.get("title"), published_at=l.get("published_at"),
                                      period=l.get("period"), url=l.get("url")) for l in (letters or [])[:5]]
        candidates = []
        for letter in letters or []:
            title = str(letter.get("title") or "")
            period = letter.get("period") or fiscal_period(title)
            url = letter.get("url")
            if not period or not url:
                continue
            try:
                metrics = metrics_from_report(self.fetch_html(url), period)
            except Exception:
                continue
            if metrics:
                candidates.append((period, clean(letter.get("published_at") or ""), metrics))
        if not candidates:
            return result
        period, published, metrics = max(candidates, key=lambda item: (item[0], item[1]))
        result.update(available=True, period=period, published_at=published, metrics=metrics,
                      reason=None)
        # Growth requires two comparable periods (same month/day, prior year).
        year, month, day = (int(part) for part in period.split("/"))
        previous_period = f"{year-1:04d}/{month:02d}/{day:02d}"
        older = next((m for p, _, m in candidates if p == previous_period), None)
        if older:
            result["growth"] = {
                "operating_revenue": _growth(metrics.get("operating_revenue"), older.get("operating_revenue")),
                "net_income": _growth(metrics.get("net_income"), older.get("net_income")),
                "comparison_period": previous_period,
            }
        else:
            result["reason"] = "دوره هممقایسه برای محاسبه رشد یافت نشد"
        return result

    def earnings_growth(self, analysis):
        """Return a number only for comparable periods, otherwise None."""
        if not analysis or not analysis.get("available"):
            return None
        value = analysis.get("growth", {}).get("net_income")
        return value if isinstance(value, (int, float)) else None
