from statistics import median
from urllib.parse import urlencode
from .common import ProviderError, day, first, get_json, now, number, rows

BASE = "https://cdn.tsetmc.com/api/"


def code_of(value):
    code = str(value)
    if not (code.isascii() and code.isdigit() and 0 < len(code) <= 20):
        raise ProviderError("Invalid instrument code")
    return code


def parse_history(records, as_of=None):
    """Adjust to the latest INCLUDED session; original executions and value are preserved."""
    dated = {}
    for raw in records:
        date = day(raw.get("dEven"))
        if not date or date in dated:
            raise ProviderError("Missing or duplicate trading date")
        if not as_of or date <= as_of:
            dated[date] = raw
    result = []
    received = now()
    reference = None
    factor = 1.
    skipped = 0
    for date in sorted(dated, reverse=True):
        row = dated[date]
        volume, value = number(row.get("qTotTran5J")), number(row.get("qTotCap"))
        if volume == value == 0:
            # Halt / no-trade session: keep the adjustment chain, drop the bar.
            reference = number(row.get("priceYesterday")) or reference
            skipped += 1
            continue
        prices = [number(row.get(k)) for k in ("priceFirst","priceMax","priceMin","pClosing","pDrCotVal")]
        if any(v is None or v <= 0 for v in prices + [volume, value]):
            reference = number(row.get("priceYesterday")) or reference
            skipped += 1
            continue
        opening, high, low, close, last = prices
        if not low <= opening <= high or not low <= last <= high:
            # A single malformed exchange row must not invalidate years of
            # otherwise usable history. The date still participates in the
            # adjustment chain through priceYesterday.
            reference = number(row.get("priceYesterday")) or reference
            skipped += 1
            continue
        # TSETMC's official closing price (pClosing) is a session average and
        # can fall marginally outside the min/max of the individual trades. An
        # OHLC bar must still contain its own open and close, so the reported
        # range is widened to include them. Nothing is invented: every level
        # below was actually reported for that session.
        high = max(high, opening, close, last)
        low = min(low, opening, close, last)
        if result:
            if reference is None or reference <= 0:
                raise ProviderError("Missing price adjustment reference")
            factor *= reference / close
        reference = number(row.get("priceYesterday"))
        result.append(dict(date=date, open=opening*factor, high=high*factor, low=low*factor,
                           close=close*factor, last=last*factor, raw_open=opening, raw_high=high,
                           raw_low=low, raw_close=close, raw_last=last, adjusted=True,
                           adjustment_factor=factor, previous_reference=reference, volume=volume,
                           value=value, fetched_at=received, valid=True, source="TSETMC"))
    if not result:
        raise ProviderError("Empty price history")
    return result[::-1]


class Tsetmc:
    def __init__(self, fetch=get_json):
        self.fetch = fetch

    def universe(self):
        query = urlencode({"market": 0, "industrialGroup": "", "paperTypes[0]": 1, "showTraded": "false",
                           "withBestLimits": "true", "hEven": 0, "RefID": 0})
        records = rows(self.fetch(BASE+"ClosingPrice/GetMarketWatch?"+query), "marketwatch")
        received = now()
        result = {}
        for raw in records:
            code = code_of(first(raw,"insCode","inscode","id"))
            # TSETMC renamed the market-watch fields (l18 -> lva, etc.). Legacy
            # names are kept as fallbacks so cached responses still parse.
            symbol = first(raw,"lva","l18","lVal18AFC")
            if not isinstance(symbol,str) or not symbol.strip():
                raise ProviderError("Missing market watch symbol")
            state = first(raw,"instrumentState","cEtaval","cEtatVal","state")
            if isinstance(state, dict):
                state = first(state, "cEtaval", "cEtatVal", "state")
            limits = raw.get("staticThreshold") or {}
            best = next((row for row in (raw.get("blDs") or []) if isinstance(row, dict)), {})
            result[code] = dict(
                code=code, symbol=symbol.strip(),
                name=first(raw,"lvc","l30","lVal30"),
                date=day(first(raw,"dEven","deven")),
                state=str(state).strip() if state else None,
                sector=first(raw,"cGrValCot","cgrValCot","cs","cSecVal"),
                last_price=number(first(raw,"pdv","pl","pDrCotVal")),
                volume=number(first(raw,"qtj","qTotTran5J")),
                value=(lambda v, p: v*p if v is not None and p is not None else None)(
                    number(first(raw,"qtj","qTotTran5J")), number(first(raw,"pdv","pDrCotVal"))),
                bid=number(first(raw,"pmd","pd1","pMeDem")),
                ask=number(first(raw,"pmo","po1","pMeOf")),
                bid_size=number(first(best,"qmd","qd1","qTitMeDem")),
                ask_size=number(first(best,"qmo","qo1","qTitMeOf")),
                ceiling=number(first(raw,"pMax","tmax","psGelStaMax") or first(limits,"psGelStaMax")),
                floor=number(first(raw,"pMin","tmin","psGelStaMin") or first(limits,"psGelStaMin")),
                flow=number(raw.get("flow")),
                fetched_at=received, source="TSETMC")
        if not result:
            raise ProviderError("Empty market watch")
        return list(result.values())

    def history(self, code, days=1200, as_of=None):
        code = code_of(code)
        if not isinstance(days, int) or not 1 <= days <= 10000:
            raise ProviderError("Invalid history window")
        data = rows(self.fetch(BASE+f"ClosingPrice/GetClosingPriceDailyList/{code}/{days}"),"closingPriceDaily")
        if any(str(row.get("insCode",code)) != code for row in data):
            raise ProviderError("Instrument code mismatch")
        return parse_history(data, as_of)

    def overview(self, flow=1):
        if flow not in (1,2):
            raise ProviderError("Unknown market")
        data = self.fetch(BASE+f"MarketData/GetMarketOverview/{flow}").get("marketOverview")
        if not isinstance(data,dict):
            raise ProviderError("Missing market overview")
        # The snapshot endpoint leaves dEven at 0; the last completed session
        # is exposed as marketActivityDEven instead.
        date = day(first(data, "marketActivityDEven", "dEven"))
        return dict(index=number(data.get("indexLastValue")),
                    equal_weight=number(data.get("indexEqualWeightedLastValue")),
                    change=number(data.get("indexChange")),
                    equal_weight_change=number(data.get("indexEqualWeightedChange")),
                    trade_count=number(data.get("marketActivityZTotTran")),
                    turnover=number(data.get("marketActivityQTotCap")),
                    market_state=data.get("marketStateTitle"),
                    date=date, fetched_at=now(), source="TSETMC")

    def board(self, code):
        data = rows(self.fetch(BASE+f"ClientType/GetClientTypeHistory/{code_of(code)}"),"clientType")
        dated = [(day(first(row,"recDate","dEven")),row) for row in data]
        dated = [(d,row) for d,row in dated if d]
        if not dated:
            raise ProviderError("Missing dated client type records")
        date,row = max(dated, key=lambda pair:pair[0])
        # In TSETMC's client-type payload "_I_" is حقوقی (legal) and "_N_" is
        # حقیقی (retail). Do not mix the two when deriving order-flow metrics.
        legal_buy, legal_sell = number(row.get("buy_I_Value")), number(row.get("sell_I_Value"))
        retail_buy, retail_sell = number(row.get("buy_N_Value")), number(row.get("sell_N_Value"))
        retail_bc, retail_sc = number(row.get("buy_N_Count")), number(row.get("sell_N_Count"))
        bp = retail_buy/retail_bc if None not in (retail_buy,retail_bc) and retail_bc > 0 else None
        sp = retail_sell/retail_sc if None not in (retail_sell,retail_sc) and retail_sc > 0 else None
        return dict(date=date,
                    buyer_power=bp/sp if bp is not None and sp and sp > 0 else None,
                    net_retail_value=retail_buy-retail_sell if None not in (retail_buy,retail_sell) else None,
                    net_legal_value=legal_buy-legal_sell if None not in (legal_buy,legal_sell) else None,
                    buy_per_capita=bp, sell_per_capita=sp,
                    retail_buy_value=retail_buy, retail_sell_value=retail_sell,
                    legal_buy_value=legal_buy, legal_sell_value=legal_sell,
                    fetched_at=now(), source="TSETMC")


def market_context(instrument, bars, board=None, min_daily_value=10_000_000_000):
    """Point-in-time tradability snapshot.

    The market-watch payload no longer carries a usable trading date or an
    explicit state code. The dated price history is therefore the authority
    for freshness; a symbol is treated as tradable only when it actually
    traded on that date (or when an explicit exchange state is available).
    """
    latest = bars[-1] if bars else {}
    date = latest.get("date")
    watch_date = instrument.get("date")
    fresh = bool(date and (watch_date in (None, date)))
    state = instrument.get("state") if fresh else None
    bid, ask, bs, ss, ceiling, floor = [instrument.get(k) for k in
        ("bid","ask","bid_size","ask_size","ceiling","floor")]
    book = fresh and all(isinstance(v,(int,float)) and v >= 0 for v in (bid,ask,bs,ss,ceiling,floor)) and ceiling >= floor > 0
    values = [bar.get("value") for bar in bars[-20:]]
    traded = fresh and number(latest.get("volume")) is not None and latest["volume"] > 0
    if state:
        tradable = state in ("A", "مجاز")
    elif fresh:
        tradable = traded
    else:
        tradable = None
    return dict(tradable=tradable,
                adjusted=all(bar.get("adjusted") is True for bar in bars) if bars else None,
                liquid=median(values) >= min_daily_value if len(values)==20 and None not in values else None,
                buy_queue=bool(bid == ceiling and bs > 0 and ss == 0) if book else None,
                sell_queue=bool(ask == floor and ss > 0 and bs == 0) if book else None,
                last_price=latest.get("raw_last") or instrument.get("last_price"),
                buyer_power=board.get("buyer_power") if board and date and board.get("date")==date else None,
                net_legal_value=board.get("net_legal_value") if board and date and board.get("date")==date else None)

