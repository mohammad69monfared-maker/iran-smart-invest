"""Public, license-friendly adapters for global crypto, gold and FX markets.

Every number returned here comes from a real HTTP response. When a source is
unreachable the instrument is reported as unavailable; no level is ever
invented. This module deliberately has no dependency on the stock adapters.
"""
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..providers.common import ProviderError, number

MAX_BYTES = 4_000_000
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; IranSmartInvest/1.1)",
           "Accept": "application/json,text/plain,*/*"}


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_NoRedirects)

# Instruments with a real, accessible public source. Iranian physical gold,
# coin and the commodity exchange have no dependable free API reachable from
# this environment, so they are NOT given fabricated numbers.
CATALOG = (
    dict(symbol="BTC/USDT", code="BTCUSDT", provider="binance",
         fallback="BTC-USD", group="رمز ارز", currency="USDT"),
    dict(symbol="ETH/USDT", code="ETHUSDT", provider="binance",
         fallback="ETH-USD", group="رمز ارز", currency="USDT"),
    dict(symbol="XAU/USD (طلا جهانی)", code="GC=F", provider="yahoo",
         group="طلا جهانی", currency="USD"),
    dict(symbol="PAXG/USDT (طلای توکنشده)", code="PAXGUSDT", provider="binance",
         fallback="PAXG-USD", group="طلا جهانی", currency="USDT"),
    dict(symbol="EUR/USD", code="EURUSD=X", provider="yahoo",
         group="فارکس", currency="USD", volume_ok=True),
    dict(symbol="USD/IRR", code="USDIRR=X", provider="yahoo",
         group="ارز ایران", currency="IRR", volume_ok=True),
    dict(symbol="GBP/USD", code="GBPUSD=X", provider="yahoo",
         group="فارکس", currency="USD", volume_ok=True),
)


def get_json(url):
    request = Request(url, headers=HEADERS)
    for attempt in range(2):
        try:
            with _OPENER.open(request, timeout=25) as response:
                body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ProviderError("Response exceeds size limit")
            return json.loads(body.decode("utf-8-sig"))
        except (HTTPError, URLError, OSError, ValueError) as exc:
            if attempt:
                raise ProviderError(f"{type(exc).__name__}: {url}") from exc


def binance_get(path):
    """Public Binance data has two official hosts; use either that answers."""
    for host in ("https://api.binance.com", "https://data-api.binance.vision"):
        try:
            return get_json(host + path)
        except ProviderError:
            continue
    raise ProviderError("Binance endpoints unavailable")


def _bar(day, o, h, l, c, volume, source):
    return dict(date=day, open=o, high=h, low=l, close=c, volume=volume,
                value=volume * c, adjusted=True, valid=True, source=source,
                fetched_at=datetime.now(timezone.utc).isoformat())


def binance_bars(code, days=200):
    """Daily OHLCV from Binance's public klines endpoint."""
    if not code.isascii() or not code.isalnum():
        raise ProviderError("Invalid Binance symbol")
    payload = binance_get(
        "/api/v3/klines?symbol=" + code + f"&interval=1d&limit={int(days)}")
    if not isinstance(payload, list) or not payload:
        raise ProviderError("Invalid klines payload")
    result = []
    for row in payload:
        if not isinstance(row, list) or len(row) < 6:
            raise ProviderError("Invalid kline row")
        stamp = number(row[0])
        if stamp is None:
            raise ProviderError("Invalid kline time")
        day = datetime.fromtimestamp(stamp / 1000, timezone.utc).date().isoformat()
        o, h, l, c, volume = (number(row[i]) for i in range(1, 6))
        if None in (o, h, l, c, volume) or min(o, h, l, c) <= 0:
            raise ProviderError("Invalid kline price")
        result.append(_bar(day, o, h, l, c, volume, "Binance"))
    return _sorted(result)


def yahoo_bars(code, days=200):
    """Daily OHLC from Yahoo Finance's public chart endpoint."""
    if not code or any(ch in code for ch in "?&/ "):
        raise ProviderError("Invalid Yahoo symbol")
    payload = get_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{code}"
        f"?range={max(1, int(days / 260))}y&interval=1d")
    try:
        result = payload["chart"]["result"][0]
        stamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        closes = quote["close"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Invalid Yahoo chart payload") from exc
    if not isinstance(stamps, list) or len(stamps) != len(closes):
        raise ProviderError("Yahoo chart length mismatch")
    result_bars = []
    for stamp, o, h, l, c, volume in zip(
            stamps, quote["open"], quote["high"], quote["low"],
            closes, quote["volume"]):
        o, h, l, c = (number(x) for x in (o, h, l, c))
        if None in (o, h, l, c) or min(o, h, l, c) <= 0 or stamp is None:
            continue  # Yahoo pads holidays and halted sessions with nulls.
        # FX feeds occasionally publish a high/low band that excludes the
        # reported open or close. Widen it to the levels actually reported,
        # never inventing a new price level.
        h, l = max(h, o, c), min(l, o, c)
        if (h - l) / h > 0.5:
            continue
        result_bars.append(_bar(
            datetime.fromtimestamp(float(stamp), timezone.utc).date().isoformat(),
            o, h, l, c, number(volume) or 0.0, "Yahoo Finance"))
    return _sorted(result_bars)


def _sorted(bars):
    bars.sort(key=lambda b: b["date"])
    if len({b["date"] for b in bars}) != len(bars):
        raise ProviderError("Duplicate trading date")
    return bars


def bars_for(item, days=200):
    if item["provider"] == "binance":
        try:
            return binance_bars(item["code"], days)
        except ProviderError:
            return yahoo_bars(item.get("fallback") or item["code"], days)
    if item["provider"] == "yahoo":
        return yahoo_bars(item["code"], days)
    raise ProviderError("No trusted source configured")


def latest_prices():
    """Current published levels for the public instruments, no guessing."""
    out = {}
    for item in CATALOG:
        try:
            code = item["code"]
            if item["provider"] == "binance":
                try:
                    payload = binance_get("/api/v3/ticker/price?symbol=" + code)
                    price = number(payload.get("price"))
                except ProviderError:
                    price = yahoo_bars(item.get("fallback") or code, days=30)[-1]["close"]
            else:
                price = yahoo_bars(code, days=30)[-1]["close"]
            if price and price > 0:
                out[item["symbol"]] = price
        except (ProviderError, ValueError, KeyError, TypeError, OSError):
            continue
    return out


def analyze_global(as_of=None, weights=None):
    """Return explainable signals for the public markets in CATALOG."""
    from ..data.quality import validate_bars
    from ..quant import evaluate

    from ..reports.details import technical

    out = dict(signals=[], summaries=[], instruments={}, status="unavailable")
    for item in CATALOG:
        symbol = item["symbol"]
        try:
            bars = bars_for(item)
            day = as_of or bars[-1]["date"]
            out["summaries"].append(dict(
                symbol=symbol, group=item["group"], currency=item["currency"],
                date=bars[-1]["date"], last_price=bars[-1]["close"],
                technical=technical(bars), source=bars[-1]["source"]))
            valid, why = validate_bars(bars, day, min_bars=60)
            if not valid:
                out["instruments"][symbol] = dict(ok=False, reason=why)
                out["summaries"][-1].update(signal=False, reason=why)
                continue
            market = dict(tradable=True, adjusted=True, liquid=True,
                          buy_queue=False, sell_queue=False,
                          last_price=bars[-1]["close"],
                          sources=[bars[-1]["source"]],
                          volume_ok=bool(item.get("volume_ok", True)))
            signal, reason = evaluate(symbol, bars, as_of=day,
                                      market=market, weights=weights)
            if signal:
                signal.update(market=item["group"], currency=item["currency"],
                              source=bars[-1]["source"], data_date=day)
                out["signals"].append(signal)
                out["instruments"][symbol] = dict(ok=True, signal=True, date=day)
                out["summaries"][-1].update(signal=True, reason=None)
            else:
                out["instruments"][symbol] = dict(ok=True, signal=False, reason=reason)
                out["summaries"][-1].update(signal=False, reason=reason)
        except (ProviderError, ValueError, KeyError, TypeError, OSError) as exc:
            out["instruments"][symbol] = dict(ok=False, reason=type(exc).__name__)
    out["signals"].sort(key=lambda s: (-s.get("score", 0), s["symbol"]))
    out["signals"] = out["signals"][:5]
    out["status"] = "ok" if any(v.get("ok") for v in out["instruments"].values()) else "unavailable"
    return out
