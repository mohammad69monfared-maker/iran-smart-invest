import argparse
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .providers import Tsetmc, Codal, market_context, ProviderError
from .data import QualityTracker, validate_bars, tablovani, FundamentalAnalyzer
from .reporting import archive, render
from .reports import build_narrative, optional_ollama
from .quant import evaluate
from .portfolio import Ledger
from .cloud import publish_report, CloudError

ROOT = Path(__file__).resolve().parents[1]
TEHRAN = timezone(timedelta(hours=3, minutes=30))
# Cheap first-stage liquidity screen from the single market-watch response.
# Avoids thousands of history/board requests for instruments that cannot pass
# the 20-session liquidity requirement anyway.
PRE_FILTER_VALUE = 5_000_000_000


def analyze(now, storage, provider, codal, weights):
    day = now.date().isoformat()
    report = dict(date=day, generated_at=now.isoformat(), scanned=0, rejected=0,
                  signals=[], alerts=[], sources={}, portfolio={}, status="unavailable")
    quality = QualityTracker()
    if now.weekday() in (3, 4) or (now.hour, now.minute) < (12, 35):
        report.update(status="closed", summary="خارج از زمان تحلیل پایان جلسه")
        return report
    try:
        instruments = provider.universe()
    except ProviderError as error:
        report["sources"]["TSETMC"] = str(error)
        report["summary"] = "دریافت فهرست نمادها ناموفق بود. سیگنالی صادر نشد."
        return report
    quality.record(source="TSETMC", fetched_at=now.isoformat(), data_time=day,
                   valid=True, completeness=1.0)
    try:
        overview = provider.overview()
        report["market"] = overview if overview.get("date") == day else {}
    except ProviderError:
        report["market"] = {}

    reasons = Counter()
    sectors = Counter()
    turnover = 0
    net_retail = 0
    flow_observations = 0
    candidates, quotes, books = [], {}, {}
    failed = fresh = 0
    for instrument in instruments:
        report["scanned"] += 1
        symbol, code = instrument["symbol"], instrument["code"]
        quick_value = instrument.get("value")
        if quick_value is not None and quick_value < PRE_FILTER_VALUE:
            reasons["نقدشوندگی اولیه تأیید نشد"] += 1
            quality.record(source="TSETMC", symbol=symbol, fetched_at=now.isoformat(),
                           data_time=instrument.get("date"), valid=False, completeness=0.0,
                           errors=("ارزش معاملات زیر آستانه اولیه",))
            continue
        try:
            bars = provider.history(code)
            valid, why = validate_bars(bars, day)
            quality.record(
                source="TSETMC", symbol=symbol,
                fetched_at=bars[-1].get("fetched_at", now.isoformat()) if bars else now.isoformat(),
                data_time=bars[-1]["date"] if bars else None, valid=valid,
                completeness=min(1.0, len(bars) / 60) if bars else 0.0,
                errors=() if valid else (why,))
            if not valid:
                reasons[why] += 1
                continue
            # The dated price history is the freshness authority; the
            # market-watch snapshot no longer exposes a reliable date.
            instrument["date"] = bars[-1]["date"]
            board = provider.board(code)
            market = market_context(instrument, bars, board)
            market["sources"] = ["TSETMC"]
            book = tablovani(bars, board, instrument, day)
            market.update(book)
            archive(storage, code, bars, board, symbol, market)
            fresh += 1
            turnover += bars[-1].get("value") or 0
            sectors[instrument.get("sector") or "نامشخص"] += bars[-1].get("value") or 0
            if board.get("net_retail_value") is not None:
                net_retail += board["net_retail_value"]
                flow_observations += 1
            if market.get("last_price"):
                quotes[symbol] = market["last_price"]
            books[symbol] = book
            signal, reason = evaluate(symbol, bars, as_of=day, market=market, weights=weights)
            if signal:
                candidates.append((signal, bars, market))
            else:
                reasons[reason] += 1
        except (ProviderError, ValueError, KeyError, TypeError):
            failed += 1
            quality.record(source="TSETMC", symbol=symbol, fetched_at=now.isoformat(),
                           data_time=None, valid=False, completeness=0.0,
                           errors=("داده منبع ناقص یا در دسترس نیست",))
            reasons["دادهٔ منبع ناقص یا در دسترس نیست"] += 1

    report["observed_turnover_rial"] = turnover if fresh else None
    report["observed_net_retail_rial"] = net_retail if flow_observations else None
    report["retail_flow_symbols"] = flow_observations
    report["industry_turnover_rial"] = dict(sectors)

    candidates.sort(key=lambda item: (-item[0].get("score", 0), item[0]["symbol"]))
    # Fundamentals are retrieved only for the strongest candidates. A growth
    # figure is used only when two genuinely comparable periods were parsed.
    analyzer = FundamentalAnalyzer(codal)
    finalists = []
    for signal, bars, market in candidates[:8]:
        symbol = signal["symbol"]
        try:
            disclosures = codal.disclosures(symbol)
            report["sources"]["Codal"] = "اطلاعیه‌ها بررسی شد"
        except ProviderError:
            disclosures = []
            report["sources"]["Codal"] = "دریافت اطلاعیه ناموفق بود"
        fundamentals = analyzer.analyze(symbol, disclosures)
        growth = analyzer.earnings_growth(fundamentals)
        signal["fundamentals"] = fundamentals
        signal["tablovani"] = books.get(symbol, {})
        signal["disclosures"] = fundamentals["disclosures"]
        if growth is not None:
            revisit = dict(market)
            revisit["earnings_growth"] = growth
            improved, _ = evaluate(symbol, bars, as_of=day, market=revisit, weights=weights)
            if improved:
                improved.update(fundamentals=fundamentals, tablovani=books.get(symbol, {}),
                                disclosures=fundamentals["disclosures"])
                signal = improved
        finalists.append(signal)
    finalists.sort(key=lambda s: (-s.get("score", 0), s["symbol"]))
    report["signals"] = finalists[:5]

    ledger = Ledger(storage / "portfolio.sqlite3")
    ledger.mark_signals(quotes, day)
    ledger.observe_signals(report["signals"], day)
    report["performance"] = ledger.performance()
    report["portfolio"] = ledger.snapshot(quotes)
    report["alerts"] = list(report["portfolio"].get("alerts", []))
    exits = {"expired": "انقضای فرصت", "invalidated": "ابطال فرصت",
             "stop": "عبور از حد ضرر", "target": "رسیدن به هدف"}
    for item in report["performance"].get("signals", []):
        if item.get("ended") == day and item.get("state") in exits:
            report["alerts"].append(f"{item['symbol']} · {exits[item['state']]}")

    report["sources"]["TSETMC"] = dict(fresh=fresh, failed=failed)
    report["data_quality"] = quality.summary()
    report.update(rejected=report["scanned"]-len(candidates),
                  rejection_reasons=dict(reasons),
                  ranked_out=max(0, len(candidates)-len(report["signals"])),
                  status=("partial" if failed else "ok") if fresh else "unavailable")
    report["summary"] = ("دادهٔ معتبر امروز در دسترس نیست." if not fresh else
                         "فرصت مناسب شناسایی نشد." if not finalists else
                         f"{len(report['signals'])} فرصت برای بررسی شناسایی شد.")
    report["narrative"] = build_narrative(report)
    enhanced = optional_ollama(report["narrative"])
    if enhanced:
        report["narrative_enhanced"] = enhanced
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--force", action="store_true",
                        help="Run the analysis again even if today's report exists")
    args = parser.parse_args()
    storage = args.data_dir
    storage.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TEHRAN)
    with closing(sqlite3.connect(storage / "runs.sqlite3", timeout=2)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS reports(day TEXT PRIMARY KEY, body TEXT NOT NULL)")
        try:
            db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            print("Analysis already running or database unavailable.")
            return 2
        row = db.execute("SELECT body FROM reports WHERE day=?", (now.date().isoformat(),)).fetchone()
        report = json.loads(row[0]) if row else {}
        if args.force or report.get("status") != "ok":
            weights = json.loads((ROOT / "strategy.json").read_text(encoding="utf-8"))["weights"]
            report = analyze(now, storage, Tsetmc(), Codal(), weights)
        db.execute("INSERT OR REPLACE INTO reports VALUES(?,?)",
                   (report["date"], json.dumps(report, ensure_ascii=False, allow_nan=False)))
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=storage,
                                         delete=False) as output:
            json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(output.name, storage / "latest.json")
        render(storage, report)
        db.commit()
    try:
        cloud = publish_report(report, report_date=report["date"])
    except CloudError:
        cloud = "failed"
    print(f"report={storage / 'latest.json'} status={report['status']} cloud={cloud}")
    return int(report["status"] == "unavailable" or cloud == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
