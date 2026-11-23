"""Order-book reading (تابلوبانی) from dated TSETMC observations.

Every metric is descriptive: it reports what the recorded data says and never
constitutes a buy/sell instruction on its own. Unknown values stay None.
"""
from statistics import median
from math import isfinite


def _ratio(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    value = numerator / denominator
    return value if isfinite(value) else None


def tablovani(bars, board, snapshot, as_of, *, min_daily_value=10_000_000_000):
    """Derive book metrics for a single already-validated symbol."""
    last = bars[-1] if bars else {}
    if not last or last.get("date") != as_of:
        raise ValueError("آخرین جلسه معتبر نیست")
    board = board if board and board.get("date") == as_of else {}
    book = snapshot if snapshot and snapshot.get("date") == as_of else {}
    volumes = [b.get("volume") for b in bars[-21:-1]]
    values = [b.get("value") for b in bars[-20:]]
    average_volume = median(volumes) if len(volumes) == 20 and None not in volumes else None
    volume_ratio = _ratio(last.get("volume"), average_volume)
    previous = bars[-2].get("raw_close") or bars[-2].get("close") if len(bars) > 1 else None
    current = last.get("raw_close") or last.get("close")
    change = None
    if previous and current and previous > 0:
        change = (float(current) / float(previous) - 1) * 100
    bid, ask = book.get("bid"), book.get("ask")
    ceiling, floor = book.get("ceiling"), book.get("floor")
    bid_size, ask_size = book.get("bid_size"), book.get("ask_size")
    book_valid = all(isinstance(v, (int, float)) and v >= 0 for v in
                     (bid, ask, ceiling, floor, bid_size, ask_size)) and ceiling >= floor > 0
    notes = []
    if volume_ratio is not None:
        notes.append(f"حجم آخرین جلسه {volume_ratio:.2f} برابر میانه ۲۰ جلسه است")
        if volume_ratio >= 3 or volume_ratio <= 1 / 3:
            notes.append("تغییر غیرعادی حجم ثبت شد؛ بررسی علت لازم است")
    if board.get("net_retail_value") is not None:
        notes.append("جریان خالص حقیقی ثبت شد" if board["net_retail_value"] >= 0
                     else "خروج خالص حقیقی ثبت شد")
    if book_valid and bid == ceiling and bid_size and not ask_size:
        notes.append("صف خرید در سقف مجاز ثبت شد")
    if book_valid and ask == floor and ask_size and not bid_size:
        notes.append("صف فروش در کف مجاز ثبت شد")
    return dict(
        date=as_of,
        net_retail_value=board.get("net_retail_value"),
        net_legal_value=board.get("net_legal_value"),
        buyer_power=board.get("buyer_power"),
        buy_per_capita=board.get("buy_per_capita"),
        sell_per_capita=board.get("sell_per_capita"),
        volume_ratio=volume_ratio,
        suspicious_volume=(volume_ratio is not None and (volume_ratio >= 3 or volume_ratio <= 1 / 3)),
        price_change_percent=change,
        liquid=median(values) >= min_daily_value if len(values) == 20 and None not in values else None,
        buy_queue=bool(book_valid and bid == ceiling and bid_size and not ask_size) if book_valid else None,
        sell_queue=bool(book_valid and ask == floor and ask_size and not bid_size) if book_valid else None,
        notes=notes,
        sources=["TSETMC"],
    )
