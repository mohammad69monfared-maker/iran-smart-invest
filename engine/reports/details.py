"""Plain-language detail blocks attached to every signal.

Values are computed from the same bars that produced the signal; when a
source has no fundamental data this is stated instead of being guessed.
"""
from ..quant import indicators


def technical(bars):
    """Numeric technical context with a deterministic Persian description."""
    try:
        ind = indicators(bars)
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return {}
    close = float(bars[-1]["close"])
    note = []
    note.append("قیمت بالای میانگین ۲۰ و ۵۰روزه" if close > ind["sma20"] > ind["sma50"]
                else "قیمت پایینتر از میانگینها" if close < ind["sma20"] < ind["sma50"]
                else "میانگینهای ۲۰ و ۵۰روزه در همتنیدهاند")
    note.append("RSI در محدودهٔ میانه" if 40 <= ind["rsi14"] <= 70 else
                "RSI اشباع خرید" if ind["rsi14"] > 70 else "RSI اشباع فروش")
    note.append("روند جهتدار" if ind["adx14"] >= 25 else "روند ضعیف یا خنثی")
    note.append("شکست مقاومت ۲۰جلسه" if ind["breakout"] else "شکست مقاومت تأیید نشد")
    return dict(
        rsi14=round(ind["rsi14"], 2),
        adx14=round(ind["adx14"], 2),
        macd=round(ind["macd"], 4),
        macd_signal=round(ind["macd_signal"], 4),
        sma20=round(ind["sma20"], 2),
        sma50=round(ind["sma50"], 2),
        support=round(ind["support"], 2),
        resistance=round(ind["resistance"], 2),
        atr14=round(ind["atr14"], 2),
        volume_ma20=round(ind["volume_ma20"], 2),
        note=" · ".join(note),
    )


LABELS = {
    "revenue": "درآمد", "sales": "فروش", "net_income": "سود خالص",
    "profit": "سود", "eps": "سود هر سهم", "equity": "حقوق صاحبان سهام",
    "assets": "داراییها", "liabilities": "بدهیها", "gross_profit": "سود ناخالص",
    "operating_profit": "سود عملیاتی", "current_ratio": "نسبت جاری",
    "debt_ratio": "نسبت بدهی", "roe": "بازده حقوق", "roa": "بازده دارایی",
}


def fundamental_note(fundamentals):
    """Summarise only figures that were actually parsed from disclosures."""
    data = fundamentals or {}
    if not data.get("available"):
        return "داده بنیادی قابلاستخراج از اطلاعیهها نیست؛ سیگنال بر پایهٔ داده بازار صادر شده است."
    metrics = data.get("metrics") or {}
    items = [f"{LABELS.get(k, k)}: {v}" for k, v in metrics.items() if v is not None]
    period = data.get("period") or "دوره نامشخص"
    growth = data.get("growth") or {}
    growth_lines = [f"{LABELS.get(k, k)}: {v}" for k, v in growth.items() if v is not None]
    return "دورهٔ " + str(period) + (" · " + "، ".join(items[:6]) if items else "") + \
           (" · رشد: " + "، ".join(growth_lines[:3]) if growth_lines else "")
