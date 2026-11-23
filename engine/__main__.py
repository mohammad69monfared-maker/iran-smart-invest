import argparse
import json
import os
import sqlite3
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .providers import Tsetmc, Codal, market_context, ProviderError
from .data import QualityTracker, validate_bars, tablovani, FundamentalAnalyzer
from .reporting import archive, render
from .reports import build_narrative, optional_ollama, technical, fundamental_note
from .providers.global_markets import analyze_global
from .quant import evaluate
from .portfolio import Ledger
from .cloud import publish_report, CloudError

ROOT = Path(__file__).resolve().parents[1]
TEHRAN = timezone(timedelta(hours=3, minutes=30))
# Cheap first-stage liquidity screen from the single market-watch response.
# Avoids thousands of history/board requests for instruments that cannot pass
# the 20-session liquidity requirement anyway.
PRE_FILTER_VALUE = 5_000_000_000
# Every inspected symbol costs two network round trips, so a sequential scan
# over the whole liquid universe cannot finish inside a CI job. TSETMC access
# is stateless and each archive write uses its own connection, therefore a
# small thread pool is safe. Both limits are overridable for slow networks.
SCAN_WORKERS = max(1, min(16, int(os.environ.get("SCAN_WORKERS", "8"))))
SCAN_BUDGET_SECONDS = float(os.environ.get("SCAN_BUDGET_SECONDS", "4200"))
# A report may describe the previous published session (weekend, holiday or a
# late exchange publication) but never an older one.
MAX_SESSION_AGE_DAYS = 4


def latest_session(provider, instruments, sample=24):
    """Return the newest session the exchange actually published bars for.

    The market-watch snapshot carries no trustworthy trading date and the
    overview may point at the current calendar day before any trade is
    recorded. The dated price history is the authority, so the answer is the
    majority last-bar date of the most liquid instruments.
    """
    ordered = sorted(instruments, key=lambda item: -(item.get("value") or 0))[:sample]
    if not ordered:
        return None

    def last_bar_date(instrument):
        try:
            bars = provider.history(instrument["code"])
        except (ProviderError, ValueError, KeyError, TypeError):
            return None
        return bars[-1]["date"] if bars else None

    votes = Counter()
    with ThreadPoolExecutor(max_workers=max(1, min(SCAN_WORKERS, len(ordered)))) as pool:
        for session in pool.map(last_bar_date, ordered):
            if session:
                votes[session] += 1
    if not votes:
        return None
    session, count = votes.most_common(1)[0]
    return session if count * 2 >= len(ordered) else None


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
    except ProviderError:
        overview = {}
    # The exchange publishes a closing session slightly after the bell, and on
    # holidays it publishes nothing at all. Anchor the analysis on the newest
    # session that really exists instead of assuming today traded.
    session = latest_session(provider, instruments)
    if not session:
        report.update(status="unavailable",
                      summary="آخرین جلسه معاملاتی مشخص نشد. سیگنالی صادر نشد.")
        return report
    age = (now.date() - date.fromisoformat(session)).days
    report["session"] = session
    report["session_age_days"] = age
    if age < 0 or age > MAX_SESSION_AGE_DAYS:
        report.update(status="unavailable",
                      summary=f"آخرین داده معتبر مربوط به {session} است و برای تحلیل امروز کافی نیست.")
        return report
    day = session
    report["date"] = session
    # The index snapshot is informational and is never fed into signal scoring.
    # Keep its own publication date visible instead of implying it belongs to
    # the session used for the signals.
    report["market"] = dict(overview) if overview else {}
    if overview and overview.get("date") != session:
        report["sources"]["TSETMC index"] = (
            f"تاریخ شاخص ({overview.get('date')}) با جلسه تحلیل ({session}) هم\u200cخوان نیست")

    reasons = Counter()
    sectors = Counter()
    turnover = 0
    net_retail = 0
    flow_observations = 0
    candidates, quotes, books = [], {}, {}
    failed = fresh = 0

    def inspect(instrument):
        """Fetch and evaluate one symbol; never raises, always reports why."""
        symbol, code = instrument["symbol"], instrument["code"]
        fresh_at = now.isoformat()
        quick_value = instrument.get("value")
        if quick_value is not None and quick_value < PRE_FILTER_VALUE:
            return dict(kind="skipped", reason="نقدشوندگی اولیه تأیید نشد",
                        quality=dict(source="TSETMC", symbol=symbol, fetched_at=fresh_at,
                                     data_time=instrument.get("date"), valid=False,
                                     completeness=0.0,
                                     errors=("ارزش معاملات زیر آستانه اولیه",)))
        try:
            bars = provider.history(code)
            valid, why = validate_bars(bars, day)
            quality_entry = dict(
                source="TSETMC", symbol=symbol,
                fetched_at=bars[-1].get("fetched_at", fresh_at) if bars else fresh_at,
                data_time=bars[-1]["date"] if bars else None, valid=valid,
                completeness=min(1.0, len(bars) / 60) if bars else 0.0,
                errors=() if valid else (why,))
            if not valid:
                return dict(kind="skipped", reason=why, quality=quality_entry)
            # The dated price history is the freshness authority; the
            # market-watch snapshot no longer exposes a reliable date.
            instrument["date"] = bars[-1]["date"]
            board = provider.board(code)
            market = market_context(instrument, bars, board)
            market["sources"] = ["TSETMC"]
            book = tablovani(bars, board, instrument, day)
            market.update(book)
            archive(storage, code, bars, board, symbol, market)
            signal, reason = evaluate(symbol, bars, as_of=day, market=market, weights=weights)
            return dict(kind="ok", quality=quality_entry, bars=bars, board=board,
                        market=market, book=book, signal=signal, reason=reason)
        except (ProviderError, ValueError, KeyError, TypeError, sqlite3.Error):
            return dict(kind="failed", reason="دادهٔ منبع ناقص یا در دسترس نیست",
                        quality=dict(source="TSETMC", symbol=symbol, fetched_at=fresh_at,
                                     data_time=None, valid=False, completeness=0.0,
                                     errors=("داده منبع ناقص یا در دسترس نیست",)))

    total = len(instruments)
    collected = []
    started = time.monotonic()
    deadline = started + SCAN_BUDGET_SECONDS
    pool = ThreadPoolExecutor(max_workers=max(1, min(SCAN_WORKERS, total)))
    unfinished = 0
    try:
        futures = {pool.submit(inspect, instrument): index
                   for index, instrument in enumerate(instruments)}
        try:
            for done, future in enumerate(as_completed(futures), 1):
                collected.append((futures[future], future.result()))
                if done % 100 == 0 or done == total:
                    print(f"scanned {done}/{total} in {time.monotonic() - started:.0f}s", flush=True)
                if time.monotonic() > deadline:
                    print("scan budget reached; publishing a partial report", flush=True)
                    break
        except TimeoutError:
            print("scan budget reached while waiting; publishing a partial report", flush=True)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    collected.sort(key=lambda pair: pair[0])
    unfinished = total - len(collected)

    for index, result in collected:
        quality.record(**result["quality"])
        kind = result["kind"]
        if kind == "ok":
            bars, board = result["bars"], result["board"]
            market, book = result["market"], result["book"]
            fresh += 1
            turnover += bars[-1].get("value") or 0
            sectors[instruments[index].get("sector") or "نامشخص"] += bars[-1].get("value") or 0
            if board.get("net_retail_value") is not None:
                net_retail += board["net_retail_value"]
                flow_observations += 1
            if market.get("last_price"):
                quotes[instruments[index]["symbol"]] = market["last_price"]
            books[instruments[index]["symbol"]] = book
            if result["signal"]:
                candidates.append((result["signal"], bars, market))
            else:
                reasons[result["reason"]] += 1
        else:
            failed += kind == "failed"
            reasons[result["reason"]] += 1
    report["scanned"] = total
    if unfinished:
        reasons["به پایان نرسیدن اسکن در بودجه زمانی"] += unfinished

    report["observed_turnover_rial"] = turnover if fresh else None
    report["observed_net_retail_rial"] = net_retail if flow_observations else None
    report["retail_flow_symbols"] = flow_observations
    report["industry_turnover_rial"] = dict(sectors)

    candidates.sort(key=lambda item: (-item[0].get("score", 0), item[0]["symbol"]))
    # Fundamentals are retrieved only for the strongest candidates. A growth
    # figure is used only when two genuinely comparable periods were parsed.
    analyzer = FundamentalAnalyzer(codal)
    bars_by_symbol = {instruments[i]["symbol"]: result["bars"]
                      for i, result in collected if result["kind"] == "ok"}
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
        signal["technical"] = technical(bars_by_symbol.get(symbol, []))
        signal["fundamental_note"] = fundamental_note(fundamentals)
        finalists.append(signal)
    finalists.sort(key=lambda s: (-s.get("score", 0), s["symbol"]))
    report["signals"] = finalists[:5]
    # Public gold/FX/crypto context is an optional section: a failure there
    # must never suppress the validated stock signals.
    try:
        report["global"] = analyze_global(weights=weights)
    except (ProviderError, ValueError, OSError, KeyError, TypeError) as exc:
        report["global"] = dict(status="unavailable", signals=[], summaries=[],
                                error=type(exc).__name__)
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
