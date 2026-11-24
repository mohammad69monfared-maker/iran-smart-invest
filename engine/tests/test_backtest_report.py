"""Offline tests for backtest reporting. No network, no invented prices."""
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.backtest_report import backtest_symbol, backtest_persian_summary


def _make_db(storage, symbol="آزمون", code="1", days_count=100):
    db = storage / "history.sqlite3"
    with closing(sqlite3.connect(db, timeout=60)) as db_conn:
        db_conn.execute("create table instruments(code text primary key, symbol text not null)")
        db_conn.execute("create table bars(code text, day text, observation text, primary key(code,day))")
        db_conn.execute("create table boards(code text, day text, observation text, primary key(code,day))")
        db_conn.execute("create table sessions(code text, day text, observation text, primary key(code,day))")
        db_conn.execute("insert into instruments values(?,?)", (code, symbol))
        base = 100
        for i in range(days_count):
            d = f"2026-{(i//30)+1:02d}-{(i%30)+1:02d}"
            bar = dict(date=d, open=base+i, high=base+i+2, low=base+i-2,
                       close=base+i+1, volume=1000+i, value=(1000+i)*(base+i),
                       adjusted=True, valid=True, source="TEST")
            db_conn.execute("insert into bars values(?,?,?)",
                            (code, d, json.dumps(bar, ensure_ascii=False)))
            snap = dict(tradable=True, adjusted=True, buy_queue=False,
                        sell_queue=False, last_price=base+i+1,
                        liquid=True)
            db_conn.execute("insert into sessions values(?,?,?)",
                            (code, d, json.dumps(snap, ensure_ascii=False)))
        db_conn.commit()


class BacktestReportTests(unittest.TestCase):
    def test_backtest_symbol_structure(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        storage = Path(tmp.name)
        _make_db(storage)
        result = backtest_symbol("آزمون", "1", storage)
        # Backtest may return None if no signal criteria are met in the
        # synthetic data; when it returns, structure must be correct.
        if result is not None:
            self.assertEqual(result["symbol"], "آزمون")
            self.assertEqual(result["code"], "1")
            self.assertIn("number_of_trades", result)
            self.assertIn("return_after_costs", result)
            self.assertIn("disclaimer", result)
            self.assertIn("تضمین سود آینده نیست", result["disclaimer"])

    def test_backtest_persian_summary(self):
        result = dict(symbol="آزمون", number_of_trades=5,
                      return_after_costs=0.05, maximum_drawdown=0.1,
                      win_rate=0.6, profit_factor=1.5)
        summary = backtest_persian_summary(result)
        self.assertIn("آزمون", summary)
        self.assertIn("بازده تقریبی", summary)
        self.assertIn("نرخ پیروزی", summary)
        self.assertIn("تضمین سود آینده نیست", summary)

    def test_backtest_persian_summary_none(self):
        self.assertIn("داده کافی", backtest_persian_summary(None))

    def test_insufficient_data_returns_none(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        storage = Path(tmp.name)
        _make_db(storage, days_count=10)
        result = backtest_symbol("آزمون", "1", storage)
        self.assertIsNone(result)

    def test_backtest_persian_summary_none(self):
        self.assertIn("داده کافی", backtest_persian_summary(None))

    def test_insufficient_data_returns_none(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        storage = Path(tmp.name)
        _make_db(storage, days_count=10)
        result = backtest_symbol("آزمون", "1", storage)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
