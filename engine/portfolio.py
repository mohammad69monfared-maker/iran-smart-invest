"""SQLite ledger for manual transactions and prospective close-based signal monitoring. Prices in rials."""
import argparse
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4


def amount(value, allow_zero=False):
    value = Decimal(str(value))
    if not value.is_finite() or value < 0 or (not allow_zero and not value):
        raise ValueError("Invalid monetary amount")
    return value


def symbol_name(value):
    name = value.strip().replace("ي", "ی").replace("ك", "ک")
    if not name or len(name) > 80:
        raise ValueError("Invalid symbol")
    return name


def quote_price(quote):
    if isinstance(quote, dict):
        quote = quote.get("price")
    return amount(quote) if quote is not None else None


def balances(rows):
    positions = defaultdict(lambda: [0, Decimal(0), Decimal(0)])
    for row in rows:
        symbol, side, size, price, fee = [row[k] for k in ("symbol","side","quantity","price","fee")]
        price, fee = amount(price), amount(fee, True)
        position = positions[symbol]
        if side == "buy":
            position[0] += size
            position[1] += size*price + fee
        else:
            if size > position[0]:
                raise ValueError("Sale exceeds holdings on transaction date")
            cost = position[1] if size == position[0] else position[1]*size/position[0]
            position[0] -= size
            position[1] -= cost
            position[2] += size*price - cost - fee
    return positions


class Ledger:
    def __init__(self, path="data/portfolio.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY, day TEXT NOT NULL, symbol TEXT NOT NULL,
                    side TEXT CHECK(side IN ('buy','sell')), quantity INTEGER CHECK(quantity>0),
                    price TEXT NOT NULL, fee TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS trades_by_day ON trades(day);
                CREATE TABLE IF NOT EXISTS watches (symbol TEXT PRIMARY KEY, floor TEXT, ceiling TEXT);
                CREATE TABLE IF NOT EXISTS tracked (
                    id TEXT PRIMARY KEY, symbol TEXT, issued TEXT, expires TEXT, low TEXT,
                    high TEXT, stop TEXT, target TEXT, state TEXT, entry TEXT, entered TEXT,
                    exit_price TEXT, ended TEXT, last_seen TEXT);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def trade(self, side, symbol, quantity, price, fee=0, day=None, trade_id=None):
        day = Date.fromisoformat(day) if day else Date.today()
        if day > Date.today() or type(quantity) is not int or quantity <= 0 or side not in ("buy","sell"):
            raise ValueError("Invalid side, quantity or transaction date")
        key = trade_id or uuid4().hex
        values = (key,day.isoformat(),symbol_name(symbol),side,quantity,str(amount(price)),str(amount(fee,True)))
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM trades WHERE id=?", (key,)).fetchone()
            if existing:
                if tuple(existing) != values:
                    raise ValueError("Conflicting transaction ID")
                return key
            db.execute("INSERT INTO trades VALUES (?,?,?,?,?,?,?)", values)
            balances(db.execute("SELECT * FROM trades WHERE symbol=? ORDER BY day,rowid", (values[2],)))
        return key

    def watch(self, symbol, floor=None, ceiling=None):
        lo = amount(floor) if floor is not None else None
        hi = amount(ceiling) if ceiling is not None else None
        if lo and hi and lo >= hi:
            raise ValueError("Floor must be below ceiling")
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO watches VALUES (?,?,?)",
                       (symbol_name(symbol),str(lo) if lo else None,str(hi) if hi else None))

    def unwatch(self, symbol):
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM watches WHERE symbol=?", (symbol_name(symbol),))

    def snapshot(self, quotes):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN")
            holdings = balances(db.execute("SELECT * FROM trades ORDER BY day,rowid"))
            watches = [dict(r) for r in db.execute("SELECT * FROM watches ORDER BY symbol")]
        alerts, positions, industries = [], [], defaultdict(float)
        floors = {w["symbol"]: w["floor"] for w in watches}
        for symbol, (quantity,cost,realized) in holdings.items():
            if not quantity:
                continue
            quote = quotes.get(symbol)
            price = quote_price(quote)
            value = quantity*price if price is not None else None
            industry = (quote.get("industry") if isinstance(quote,dict) else None) or "نامشخص"
            stop = floors.get(symbol)
            positions.append(dict(symbol=symbol,quantity=quantity,cost=float(cost),average_cost=float(cost/quantity),
                market_value=float(value) if value is not None else None,
                unrealized=float(value-cost) if value is not None else None,industry=industry,
                risk_to_floor=float(max(price-amount(stop),0)*quantity) if stop and price is not None else None))
        for w in watches:
            price = quote_price(quotes.get(w["symbol"]))
            if price is None:
                continue
            for key,hit in (("floor",lambda a: price <= a),("ceiling",lambda a: price >= a)):
                if w[key] and hit(amount(w[key])):
                    alerts.append(dict(symbol=w["symbol"],kind=key,price=float(price),threshold=float(w[key])))
        complete = all(p["market_value"] is not None for p in positions)
        value = sum(p["market_value"] for p in positions) if complete else None
        for p in positions:
            p["weight"] = p["market_value"]/value if value else None
            if value:
                industries[p["industry"]] += p["weight"]
        return dict(positions=positions,watchlist=watches,alerts=alerts,industry_weights=dict(industries),
                    totals=dict(market_value=value,realized=float(sum(p[2] for p in holdings.values())),
                                unrealized=sum(p["unrealized"] for p in positions) if complete else None))

    def observe_signals(self, signals, date):
        day = Date.fromisoformat(date).isoformat()
        with closing(self.connect()) as db, db:
            for s in signals:
                lo,hi,stop,target = [amount(s[k]) for k in ("entry_low","entry_high","stop_loss","target1")]
                expiry = Date.fromisoformat(s["expires"]).isoformat()
                if not (stop < lo <= hi < target and expiry > day and day == s["date"]):
                    raise ValueError("Invalid published signal")
                db.execute("""INSERT INTO tracked (id,symbol,issued,expires,low,high,stop,target,state)
                    VALUES (?,?,?,?,?,?,?,?,'pending') ON CONFLICT(id) DO NOTHING""",
                    (s["id"],symbol_name(s["symbol"]),day,expiry,str(lo),str(hi),str(stop),str(target)))

    def mark_signals(self, quotes, date):
        day = Date.fromisoformat(date).isoformat()
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            for s in db.execute("""SELECT * FROM tracked WHERE state IN ('pending','open')
                AND issued < ? AND (last_seen IS NULL OR last_seen < ?)""",(day,day)).fetchall():
                price = quote_price(quotes.get(s["symbol"]))
                if s["state"] == "pending" and day > s["expires"]:
                    db.execute("UPDATE tracked SET state='expired',ended=? WHERE id=?",(day,s["id"]))
                elif price is not None:
                    db.execute("UPDATE tracked SET last_seen=? WHERE id=?",(day,s["id"]))
                    if s["state"] == "pending":
                        if amount(s["low"]) <= price <= amount(s["high"]):
                            db.execute("UPDATE tracked SET state='open',entry=?,entered=? WHERE id=?",
                                       (str(price),day,s["id"]))
                        elif price <= amount(s["stop"]):
                            db.execute("UPDATE tracked SET state='invalidated',ended=? WHERE id=?", (day,s["id"]))
                    elif price <= amount(s["stop"]) or price >= amount(s["target"]):
                        state = "stop" if price <= amount(s["stop"]) else "target"
                        db.execute("UPDATE tracked SET state=?,exit_price=?,ended=? WHERE id=?",
                                   (state,str(price),day,s["id"]))
        return self.performance()

    def performance(self):
        with closing(self.connect()) as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM tracked ORDER BY issued,id")]
        returns = [float(amount(r["exit_price"])/amount(r["entry"])-1) for r in rows if r["exit_price"]]
        return dict(method="prospective_close_observations_before_costs",signals=rows,closed=len(returns),
                    average_return=sum(returns)/len(returns) if returns else None,
                    win_rate=sum(r>0 for r in returns)/len(returns) if returns else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/portfolio.sqlite3")
    commands = parser.add_subparsers(dest="action", required=True)
    for side in ("buy","sell"):
        trade = commands.add_parser(side)
        trade.add_argument("symbol")
        trade.add_argument("quantity", type=int)
        trade.add_argument("price")
        trade.add_argument("--fee", default="0")
        trade.add_argument("--day", help="YYYY-MM-DD")
        trade.add_argument("--id", dest="trade_id")
    watch = commands.add_parser("watch")
    watch.add_argument("symbol")
    watch.add_argument("--floor")
    watch.add_argument("--ceiling")
    commands.add_parser("unwatch").add_argument("symbol")
    commands.add_parser("show")
    commands.add_parser("performance")
    args = vars(parser.parse_args())
    ledger = Ledger(args.pop("db"))
    action = args.pop("action")
    try:
        if action in ("buy","sell"):
            result = ledger.trade(action,**args)
        elif action == "show":
            result = ledger.snapshot({})
        else:
            result = getattr(ledger,action)(**args)
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except (ValueError,ArithmeticError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

