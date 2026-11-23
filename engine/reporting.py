import html
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def archive(storage, code, bars, board, symbol, market):
    # closing() is required on Windows: a bare `with connect()` only commits,
    # it does not release the file handle, which blocks cleanup and rotation.
    # The scan runs in a thread pool, so a busy-timeout is needed to serialise
    # concurrent writers instead of failing with "database is locked".
    with closing(sqlite3.connect(storage / "history.sqlite3", timeout=60)) as db, db:
        db.execute("create table if not exists bars(code text, day text, observation text, primary key(code,day))")
        db.execute("create table if not exists boards(code text, day text, observation text, primary key(code,day))")
        db.execute("create table if not exists sessions(code text, day text, observation text, primary key(code,day))")
        db.execute("create table if not exists instruments(code text primary key, symbol text not null)")
        db.execute("insert or replace into instruments values(?,?)", (code, symbol))
        db.execute("insert or replace into sessions values(?,?,?)",
                   (code, bars[-1]["date"], json.dumps(market, ensure_ascii=False)))
        db.executemany("insert or replace into bars values(?,?,?)",
                       ((code, b["date"], json.dumps(b, ensure_ascii=False)) for b in bars))
        if board and board.get("date"):
            db.execute("insert or replace into boards values(?,?,?)",
                       (code, board["date"], json.dumps(board, ensure_ascii=False)))


def render(storage, report):
    def esc(value):
        return html.escape(str(value))

    cards = []
    for signal in report.get("signals", []):
        rows = []
        for key, title in (("last_price", "آخرین قیمت"), ("score", "امتیاز"),
                           ("entry_low", "کف ورود"), ("entry_high", "سقف ورود"),
                           ("stop_loss", "حد ضرر"), ("target1", "هدف اول"),
                           ("target2", "هدف دوم"), ("reward_risk", "نسبت سود به زیان"),
                           ("horizon", "افق زمانی"), ("risk_level", "سطح ریسک"),
                           ("expires", "انقضا"), ("status", "وضعیت")):
            rows.append(f"<tr><th>{title}</th><td><bdi>{esc(signal.get(key, '—'))}</bdi></td></tr>")
        reasons = "، ".join(signal.get("reasons") or []) or "—"
        risks = "، ".join(signal.get("risks") or []) or "—"
        fundamental = signal.get("fundamentals") or {}
        availability = "موجود" if fundamental.get("available") else "ناموجود"
        book = signal.get("tablovani") or {}
        cards.append(
            f"<article><h2><bdi>{esc(signal['symbol'])}</bdi></h2><table>{''.join(rows)}</table>"
            f"<p><b>چرا انتخاب شد:</b> <bdi>{esc(reasons)}</bdi></p>"
            f"<p><b>شرایط ابطال:</b> <bdi>{esc(signal.get('invalidation', '—'))}</bdi></p>"
            f"<p><b>خطرات:</b> <bdi>{esc(risks)}</bdi></p>"
            f"<p><b>داده بنیادی:</b> {availability} · <b>دوره:</b> "
            f"<bdi>{esc(fundamental.get('period') or '—')}</bdi></p>"
            f"<p><b>تابلوبانی:</b> جریان حقیقی <bdi>{esc(book.get('net_retail_value', '—'))}</bdi> · "
            f"قدرت خریدار <bdi>{esc(book.get('buyer_power', '—'))}</bdi> · "
            f"نسبت حجم <bdi>{esc(round(book['volume_ratio'], 2) if book.get('volume_ratio') is not None else '—')}</bdi></p>"
            f"</article>")

    overview = report.get("market") or {}
    indices = " · ".join(
        f"{label} <bdi>{esc(overview.get(key) or '—')}</bdi>"
        for key, label in (("index", "شاخص کل"), ("equal_weight", "شاخص هموزن"),
                           ("change", "تغییر شاخص"), ("turnover", "ارزش معاملات")))
    if overview.get("date"):
        indices += f" · تاریخ شاخص <bdi>{esc(overview['date'])}</bdi>"
    alerts = "".join(f"<li><bdi>{esc(a)}</bdi></li>" for a in report.get("alerts", []))
    quality = report.get("data_quality") or {}
    quality_line = (f"بررسیشده {quality.get('checked', 0)} · معتبر {quality.get('valid', 0)} · "
                    f"نامعتبر {quality.get('invalid', 0)} · میانگین کامل بودن "
                    f"{quality.get('mean_completeness', '—')}")
    rejections = report.get("rejection_reasons") or {}
    rejection_line = "، ".join(f"{esc(k)}: {v}" for k, v in sorted(rejections.items(), key=lambda kv: -kv[1]))
    industries = report.get("industry_turnover_rial") or {}
    industry_line = "، ".join(f"{esc(k)}: {v:,}" for k, v in
                              sorted(industries.items(), key=lambda kv: -kv[1])[:8])
    narrative = esc(report.get("narrative") or "")
    portfolio = (report.get("portfolio") or {}).get("totals", {})
    market_value = esc(portfolio.get("market_value") if portfolio.get("market_value") is not None else "—")
    sources = esc(json.dumps(report.get("sources", {}), ensure_ascii=False, indent=2))
    content = f"""<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>گزارش بورس ایران</title>
    <style>
    body{{font:16px/1.9 Vazirmatn,Tahoma,sans-serif;background:#0b1220;color:#e8edf5;max-width:1000px;margin:auto;padding:24px}}
    h1,h2{{color:#e7bf74}} h1{{font-size:26px}} h2{{font-size:20px}}
    article,section,details{{padding:16px 20px;background:#132033;margin:16px 0;border-radius:12px;border:1px solid #22344d}}
    table{{width:100%;border-collapse:collapse}} th{{text-align:right;color:#9fb3cc;width:45%;padding:4px 8px}}
    td{{padding:4px 8px}} pre{{white-space:pre-wrap;direction:ltr;text-align:left}}
    .muted{{color:#9fb3cc}} .banner{{background:#1d2c44;border-right:4px solid #e7bf74}}
    </style><h1>گزارش بورس ایران</h1>
    <section class="banner"><p>تاریخ داده <bdi>{esc(report['date'])}</bdi> · زمان پردازش <bdi>{esc(report['generated_at'])}</bdi></p>
    <h2>{esc(report['summary'])}</h2>
    <p>نمادهای بررسیشده {report['scanned']} · ردشده {report['rejected']} · رتبهبندیخارجشده {report.get('ranked_out', 0)}</p>
    <p>{indices}</p></section>
    <section><h2>سلامت منابع داده</h2><p>{quality_line}</p><p class="muted">{rejection_line}</p></section>
    <section><h2>صنایع بر اساس ارزش معاملات مشاهدهشده</h2><p>{industry_line or '—'}</p></section>
    {''.join(cards)}
    <section><h2>سبد سهام و هشدارها</h2><p>ارزش ثبتشده {market_value}</p><ul>{alerts}</ul></section>
    <section><h2>روایت گزارش</h2><pre>{narrative}</pre></section>
    <details><summary>وضعیت خام منابع</summary><pre>{sources}</pre></details>
    <p class="muted">این گزارش توصیه خرید نیست و سودی تضمین نمیکند.</p></html>"""
    temp = storage / "report.html.tmp"
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, storage / "report.html")
