"""Entry / stop / target alerts derived only from published report levels.

No price is invented: every comparison uses the current public quote and the
levels already computed for the signal. Alerts are deduplicated per signal,
event and Tehran date in a local SQLite database.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from .providers.global_markets import latest_prices

TEHRAN = timezone(timedelta(hours=3, minutes=30))

EVENTS = {
    "stop": "رسیدن به حد ضرر",
    "target2": "رسیدن به هدف دوم",
    "target1": "رسیدن به هدف اول",
    "entry": "ورود به محدودهٔ مورد نظر",
    "expired": "انقضای اعتبار سیگنال",
}


def classify(signal, price, today):
    """Return (event_key, persian_label) or (None, None)."""
    if not isinstance(price, (int, float)) or price <= 0:
        return None, None
    expires = str(signal.get("expires") or "")
    if expires and expires < today:
        return "expired", EVENTS["expired"]
    stop = signal.get("stop_loss")
    if isinstance(stop, (int, float)) and price <= stop:
        return "stop", EVENTS["stop"]
    for key in ("target2", "target1"):
        target = signal.get(key)
        if isinstance(target, (int, float)) and price >= target:
            return key, EVENTS[key]
    low, high = signal.get("entry_low"), signal.get("entry_high")
    if all(isinstance(v, (int, float)) for v in (low, high)) and low <= price <= high:
        return "entry", EVENTS["entry"]
    return None, None


def check(report, db_path, *, tsetmc=None, global_quotes=None):
    """Return new alert messages; never mutates the published report."""
    signals = list(report.get("signals") or [])
    signals += list((report.get("global") or {}).get("signals") or [])
    if not signals:
        return []
    today = datetime.now(TEHRAN).date().isoformat()
    prices = {}
    if any(s.get("source") in ("Binance", "Yahoo Finance") for s in signals):
        prices.update(global_quotes if global_quotes is not None else latest_prices())
    if any(s.get("source") not in ("Binance", "Yahoo Finance") for s in signals) and tsetmc:
        try:
            for row in tsetmc.universe():
                if row.get("last_price") is not None:
                    prices[row["symbol"]] = row["last_price"]
        except Exception:
            pass
    messages = []
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("create table if not exists alerts(id text primary key, created_at text)")
        for signal in signals:
            symbol = signal.get("symbol")
            price = prices.get(symbol)
            event, label = classify(signal, price, today)
            if not event:
                continue
            key = f"{signal.get('id') or symbol}/{event}/{today}"
            if db.execute("select 1 from alerts where id=?", (key,)).fetchone():
                continue
            db.execute("insert or ignore into alerts values (?,?)",
                       (key, datetime.now(TEHRAN).isoformat()))
            messages.append(
                f"[{signal.get('market', 'بورس تهران')}] {symbol}\n"
                f"رویداد: {label}\nقیمت فعلی: {price}\n"
                f"محدوده ورود: {signal.get('entry_low')} – {signal.get('entry_high')}\n"
                f"حد ضرر: {signal.get('stop_loss')} · هدف ۱: {signal.get('target1')}\n"
                f"منبع: {signal.get('source', 'TSETMC')} · اعتبار تا {signal.get('expires')}\n"
                "توصیه خرید نیست؛ تصمیم با شماست.")
    return messages
