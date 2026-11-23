"""Synthetic fixtures only. Never imported by the operational analysis."""
import unittest
from datetime import date,timedelta
from engine.quant import indicators,evaluate,position_size,backtest,walk_forward


def synthetic(n=70):
    start=date(2025,1,1)
    return [dict(date=str(start+timedelta(days=i)),open=100+i,close=100+i,
                 high=100.4+i,low=99.6+i,volume=100 if i<59 else 300) for i in range(n)]


def market(price):
    return dict(tradable=True,adjusted=True,liquid=True,buy_queue=False,sell_queue=False,
                last_price=price,buyer_power=2,earnings_growth=.1,relative_strength=.05)


class QuantTests(unittest.TestCase):
    def test_indicators(self):
        rows=synthetic(60)
        x=indicators(rows)
        self.assertEqual(x["sma20"],149.5)
        self.assertEqual(x["sma50"],134.5)
        self.assertAlmostEqual(x["ema12"],153.5)
        self.assertAlmostEqual(x["ema26"],146.5)
        self.assertAlmostEqual(x["macd"],7)
        self.assertAlmostEqual(x["macd_signal"],7)
        self.assertEqual(x["rsi14"],100)
        self.assertEqual(x["adx14"],100)
        self.assertAlmostEqual(x["atr14"],1.4)
        self.assertEqual(x["obv"],6100)
        self.assertTrue(x["breakout"])
        self.assertAlmostEqual(x["support"],138.6)
        self.assertEqual(x["volume_ma20"],100)
        self.assertGreater(x["bollinger_upper"],x["sma20"])
        self.assertLess(x["bollinger_lower"],x["sma20"])
        self.assertAlmostEqual(indicators(rows,[b["close"] for b in rows])["relative_strength"],0)

    def test_risk_and_signal(self):
        bars=synthetic(60)
        kw=dict(as_of=bars[-1]["date"],market=market(159))
        s,_=evaluate("آزمون",bars,**kw)
        self.assertLess(s["stop_loss"],s["entry_low"])
        self.assertAlmostEqual((s["target1"]-s["entry_high"])/(s["entry_high"]-s["stop_loss"]),2)
        self.assertEqual(s,evaluate("آزمون",bars,**kw)[0])
        self.assertEqual(position_size(10000,1,100,95),20)
        with self.assertRaises(ValueError):
            position_size(10000,1,100,100)

    def test_reject(self):
        bars=synthetic()
        state=market(169)
        for key,value in (("liquid",False),("tradable",False),("adjusted",False),("buy_queue",True),("sell_queue",None)):
            self.assertIsNone(evaluate("X",bars,as_of=bars[-1]["date"],market=dict(state,**{key:value}))[0])
        self.assertIsNone(evaluate("X",bars,as_of="2026-01-01",market=state)[0])
        self.assertIsNone(evaluate("X",bars[:5],as_of=bars[4]["date"],market=state)[0])
        bars[-1]["close"]=float("nan")
        self.assertIsNone(evaluate("X",bars,as_of=bars[-1]["date"],market=state)[0])

    def test_execution(self):
        bars=synthetic(64)
        # Next opening within the entry range, both levels crossed on that day.
        bars[60].update(open=159,low=140,high=190,close=160)
        states={b["date"]:market(b["close"]) for b in bars}
        opts=dict(buy_fee=.001,sell_fee=.002,slippage=0)
        first=backtest("X",bars[:61],states,**opts)
        trade=first["trades"][0]
        self.assertEqual(trade["entry_date"],bars[60]["date"])
        self.assertLess(trade["net_return"],0)
        self.assertAlmostEqual(trade["net_return"],trade["exit"]*.998/(trade["entry"]*1.001)-1)
        self.assertEqual(first,backtest("X",bars,states,end=61,**opts))
        states[bars[60]["date"]]["buy_queue"]=True
        self.assertEqual(backtest("X",bars[:61],states,**opts)["number_of_trades"],0)
        self.assertEqual(len(walk_forward("X",bars,states,fold_size=2,**opts)),2)

