"""Backtest reporting for published signals.

Runs a point-in-time simulation on the archived bars/boards of the top
signals and returns Persian-friendly numbers with explicit disclaimers.
This is historical simulation only: execution prices, fills, slippage and
fees are assumed; no future return is guaranteed.
"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .quant import backtest
from .providers.common import ProviderError

DEFAULT_COSTS = dict(buy_fee=0.0014, sell_fee=0.0014, slippage=0.001)


def _load_snapshot_rows(db, code, days, bars):
    """Return {iso_day: snapshot_dict} from archived boards/sessions.

    When the archive has no market context for a day, we default to an active,
    adjusted, liquid session so the simulation can proceed on bar data. This
    is an approximation: real queue locks, halts and non-traded sessions are
    not reconstructed.
    """
    snapshots = {}
    bar_by_day = {b["date"]: b for b in bars}
    for day in days:
        row = db.execute(
            "select observation from sessions where code=? and day=?",
            (code, day),
        ).fetchone()
        if row:
            snapshots[day] = json.loads(row[0])
            continue
        row = db.execute(
            "select observation from boards where code=? and day=?",
            (code, day),
        ).fetchone()
        if row:
            snapshots[day] = json.loads(row[0])
            continue
        b = bar_by_day.get(day)
        if b and b.get("volume", 0) > 0:
            snapshots[day] = dict(
                tradable=True, adjusted=True, liquid=True,
                buy_queue=False, sell_queue=False,
                last_price=b.get("last", b.get("close")),
            )
    return snapshots


def _load_bar_rows(db, code):
    """Return all archived bar dicts for a code, oldest first."""
    rows = db.execute(
        "select observation from bars where code=? order by day",
        (code,),
    ).fetchall()
    return [json.loads(obs) for (obs,) in rows]


def backtest_symbol(symbol, code, storage, costs=None):
    """Run backtest for one symbol over its full archived window.

    Returns dict with symbol, code, metrics and Persian disclaimer, or None
    if there is insufficient data.
    """
    costs = costs or dict(DEFAULT_COSTS)
    with closing(sqlite3.connect(storage / "history.sqlite3", timeout=60)) as db, db:
        bars = _load_bar_rows(db, code)
        days = [b["date"] for b in bars]
        snapshots = _load_snapshot_rows(db, code, days, bars)
    if len(bars) < 70:
        return None
    try:
        result = backtest(symbol, bars, snapshots, **costs)
    except (ProviderError, ValueError, KeyError, TypeError, sqlite3.Error):
        return None
    result["symbol"] = symbol
    result["code"] = code
    result["disclaimer"] = (
        "بک‌تست شبیه‌سازی است وFill یا اجرای واقعی را پیمایش نمی‌کند. "
        "بازده گذشته تضمین سود آینده نیست."
    )
    return result


def backtest_signals(storage, signals, costs=None):
    """Run backtest for each signal and attach result to the signal dict."""
    costs = costs or dict(DEFAULT_COSTS)
    # Build code -> symbol mapping from archived instruments
    code_map = {}
    try:
        with closing(sqlite3.connect(storage / "history.sqlite3", timeout=60)) as db, db:
            rows = db.execute("select code, symbol from instruments").fetchall()
            for code, sym in rows:
                code_map[sym] = code
    except (sqlite3.Error, ProviderError):
        pass

    for signal in signals:
        symbol = signal.get("symbol")
        code = code_map.get(symbol, signal.get("code", symbol))
        result = backtest_symbol(symbol, code, storage, costs=costs)
        if result:
            signal["backtest"] = result
    return signals


def backtest_persian_summary(result):
    """Return one-line Persian summary with explicit risk warning."""
    if not result:
        return "داده کافی برای بک‌تست وجود ندارد."
    n = result.get("number_of_trades", 0)
    ret = result.get("return_after_costs")
    dd = result.get("maximum_drawdown")
    wr = result.get("win_rate")
    pf = result.get("profit_factor")
    parts = []
    if ret is not None:
        parts.append(f"بازده تقریبی بعد از هزینه: {ret*100:+.2f}%")
    if dd is not None:
        parts.append(f"بیشترین افت پیکر (Drawdown): {dd*100:.2f}%")
    if wr is not None:
        parts.append(f"نرخ پیروزی: {wr*100:.1f}%")
    elif n == 0:
        parts.append("بدون معامله در بازهٔ بک‌تست")
    if n:
        parts.append(f"تعداد معامله شبیه‌شده: {n}")
    base = "، ".join(parts) if parts else "بدون معامله شبیه‌شده."
    return (
        f"بک‌تست (شبیه‌سازی) — {result.get('symbol','—')}: {base}. "
        f"این عدد محاسباتی گذشته است و تضمین سود آینده نیست."
    )
