import argparse
import hashlib
import json
import os
import sqlite3
import threading
import time

from ..alerts import check as check_alerts
from ..providers import Tsetmc
from ..reports.jalali import to_jalali
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

HELP = (
    "/report گزارش امروز بازار\n"
    "/signals فرصت‌های فعال\n"
    "/alerts هشدارهای گزارش\n"
    "/portfolio سبد ثبت‌شده\n"
    "/watch افزودن نماد به دیده‌بان (نمونه: /watch فولاد)\n"
    "/unwatch حذف نماد از دیده‌بان\n"
    "/status وضعیت آخرین تحلیل\n"
    "/help همین راهنما"
)
REPORT = Path("data/latest.json")

# A Persian reply keyboard so the bot is usable without typing slash commands.
KEYBOARD_ROWS = (
    ("گزارش امروز", "فرصت\u200cها"),
    ("هشدارها", "سبد من"),
    ("دیده\u200cبان", "وضعیت", "راهنما"),
)
LABEL_TO_COMMAND = {
    "گزارش امروز": "/report",
    "فرصت\u200cها": "/signals",
    "هشدارها": "/alerts",
    "سبد من": "/portfolio",
    "دیده\u200cبان": "/watch",
    "وضعیت": "/status",
    "راهنما": "/help",
}


def keyboard():
    return {"keyboard": [list(row) for row in KEYBOARD_ROWS],
            "resize_keyboard": True, "one_time_keyboard": False}

SIGNAL_FIELDS = (
    ("symbol", "نماد"),
    ("last_price", "قیمت آخر"),
    ("entry_low", "محدوده ورود از"),
    ("entry_high", "تا"),
    ("stop_loss", "حد ضرر"),
    ("target1", "هدف ۱"),
    ("target2", "هدف ۲"),
    ("reward_risk", "نسبت بازده به ریسک"),
    ("score", "امتیاز"),
    ("expires", "اعتبار تا"),
    ("invalidation", "ابطال"),
)


def telegram(token, method, **body):
    req = Request(f"https://api.telegram.org/bot{token}/{method}",
                  data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=45) as stream:
            payload = json.load(stream)
        if payload.get("ok"):
            return payload["result"]
    except (OSError, ValueError):
        pass
    raise RuntimeError("Telegram API unavailable")


def display(value):
    if isinstance(value, list):
        return "\n".join(map(display, value))
    if isinstance(value, dict):
        return "\n".join(f"{k}: {display(v)}" for k, v in value.items() if v is not None)
    return str(value)


def format_signals(signals):
    """Render each signal with the risk fields a reader actually needs."""
    blocks = []
    for signal in signals:
        if not isinstance(signal, dict):
            blocks.append(display(signal))
            continue
        lines = []
        for key, label in SIGNAL_FIELDS:
            value = signal.get(key)
            if value is None:
                continue
            if key == "expires" and isinstance(value, str) and len(value) == 10:
                value = f"{to_jalali(value)} ({value})"
            lines.append(f"{label}: {value}")
        if not lines:
            blocks.append(display(signal))
            continue
        reasons = signal.get("reasons")
        block = " | ".join(lines[:1]) + "\n" + "\n".join(lines[1:])
        if isinstance(reasons, list) and reasons:
            block += "\nدلایل: " + "، ".join(str(r) for r in reasons[:4])
        blocks.append(block)
    return "\n\n".join(blocks)


def render(command, report, today, watch=None):
    command = (command or "").split("@")[0].lower()
    if command in ("/start", "/help"):
        return HELP
    if command == "/watch":
        if watch:
            return "دیده‌بان شما:\n" + "\n".join(f"• {symbol}" for symbol in watch)
        return "دیده‌بان خالی است. نمونه: /watch فولاد"
    if not report:
        return "هنوز گزارشی ثبت نشده است."
    date = report.get("date")
    generated = str(report.get("generated_at") or "")[:10]
    # The analysis may describe the last published session (a holiday or a
    # late publication), so freshness is based on when the report was made.
    fresh = date == today or (bool(generated) and generated == today)
    if command == "/status":
        session = f"{to_jalali(date)} ({date})" if date else "—"
        published = f"{to_jalali(generated)} ({generated})" if generated else "—"
        return (f"جلسه تحلیل: {session}\ntاریخ انتشار: {published}\n"
                f"وضعیت: {report.get('status', 'نامشخص')}\n"
                f"نمادهای بررسی‌شده: {report.get('scanned', 0)} | رد‌شده: {report.get('rejected', 0)}\n"
                f"{report.get('summary', '')}")
    if not fresh:
        return f"گزارش تازه در دسترس نیست. آخرین انتشار مربوط به {generated or date} است."
    if command in ("/report", "/today"):
        label = f"{to_jalali(date)} ({date})" if date else "—"
        return (f"گزارش بورس {label}\n{report.get('summary', '')}\n\n"
                f"{render('/signals', report, today)}\n{render('/alerts', report, today)}")
    if command == "/signals":
        if report.get("status") not in ("ok", "partial"):
            return "داده معتبر برای اعلام فرصت در دسترس نیست."
        return format_signals(report.get("signals", [])[:5]) or "فرصت مناسب شناسایی نشد."
    if command == "/portfolio":
        return display(report.get("portfolio", {})) or "اطلاعات سبد در این گزارش موجود نیست."
    if command == "/alerts":
        return display(report.get("alerts", [])) or "هشداری در گزارش ثبت نشده است."
    return HELP


def deliver(token, owner, message, db=None, date="", markup=None):
    for pos in range(0, len(message), 1800):
        chunk = message[pos:pos + 1800]
        key = hashlib.sha256(
            f"{owner}/{date}/{pos}/{bool(markup)}/{chunk}".encode()).hexdigest()
        if db and db.execute("select 1 from sent where id=?", (key,)).fetchone():
            continue
        body = dict(chat_id=owner, text=chunk)
        if markup:
            body["reply_markup"] = markup
        telegram(token, "sendMessage", **body)
        if db:
            db.execute("insert or ignore into sent values (?)", (key,))
            db.commit()


def watchlist(db):
    if not db:
        return []
    return [row[0] for row in db.execute("select symbol from watch order by symbol")]


def update_watch(db, command, argument):
    """Add or remove a symbol; returns the confirmation text."""
    if not db or not argument:
        return render("/watch", {}, "", watchlist(db))
    if command == "/unwatch":
        db.execute("delete from watch where symbol=?", (argument,))
    else:
        db.execute("insert or ignore into watch values (?)", (argument,))
    db.commit()
    return f"{'حذف شد' if command == '/unwatch' else 'افزوده شد'}: {argument}\n\n" + \
        render("/watch", {}, "", watchlist(db))


def reply(update, token, owner, report, today, db=None):
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private" or str(chat.get("id")) != owner or str((msg.get("from") or {}).get("id")) != owner:
        return
    text = (msg.get("text") or "").strip()
    if not text:
        return
    command = None
    argument = ""
    for label, mapped in LABEL_TO_COMMAND.items():
        if text == label or text.startswith(label + " "):
            command = mapped
            argument = text[len(label):].strip()
            break
    if command is None:
        words = text.split()
        command = words[0].split("@")[0].lower()
        argument = words[1].strip() if len(words) > 1 else ""
    if command == "/watch" and not argument:
        # Tapping the Persian "دیدهبان" button shows the current list.
        deliver(token, owner, render("/watch", report, today, watchlist(db)),
                markup=keyboard())
        return
    if command in ("/watch", "/unwatch"):
        deliver(token, owner, update_watch(db, command, argument), markup=keyboard())
        return
    deliver(token, owner, render(command, report, today, watchlist(db)),
            markup=keyboard())


def load_report():
    """Prefer the local snapshot, then the published cloud copy."""
    if REPORT.exists():
        try:
            return json.loads(REPORT.read_text(encoding="utf-8-sig"))
        except ValueError:
            return {}
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return {}
    req = Request(f"{url}/rest/v1/daily_reports?select=report&order=report_date.desc&limit=1",
                  headers={"apikey": key, "Authorization": "Bearer " + key})
    try:
        with urlopen(req, timeout=20) as stream:
            rows = json.load(stream)
    except (OSError, ValueError):
        return {}
    return rows[0].get("report", {}) if rows else {}


def alert_loop(token, owner):
    """Check real quotes against published levels once a minute."""
    path = str(REPORT.parent / "alerts.sqlite3")
    while True:
        time.sleep(60)
        try:
            report = load_report()
            for message in check_alerts(report, path, tsetmc=Tsetmc()):
                deliver(token, owner, message)
        except (OSError, ValueError, RuntimeError, sqlite3.Error):
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("publish", "poll"))
    action = parser.parse_args().action
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    owner = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not owner.isdecimal():
        print("Telegram disabled: missing token or private owner ID.")
        return 0
    REPORT.parent.mkdir(exist_ok=True)
    poll_window = float(os.getenv("TELEGRAM_POLL_SECONDS", "0") or 0)
    poll_started = time.monotonic()
    if action == "poll":
        threading.Thread(target=alert_loop, args=(token, owner), daemon=True).start()
    with sqlite3.connect(REPORT.parent / "telegram.sqlite3") as db:
        db.execute("create table if not exists sent(id text primary key)")
        db.execute("create table if not exists cursor_state(id integer primary key, cursor integer)")
        db.execute("create table if not exists watch(symbol text primary key)")
        while True:
            today = datetime.now(timezone(timedelta(hours=3, minutes=30))).date().isoformat()
            try:
                report = load_report()
                if action == "publish":
                    if report.get("date") == today:
                        deliver(token, owner, render("/report", report, today), db, today,
                                markup=keyboard())
                        print("Telegram report delivered or previously sent.")
                    else:
                        print("No current report to send.")
                    return 0
                cursor_file = os.getenv("TELEGRAM_CURSOR_FILE", "").strip()
                if cursor_file:
                    if os.path.exists(cursor_file):
                        cursor = int(open(cursor_file, encoding="utf-8").read().strip() or 0)
                    else:
                        cursor = 0
                else:
                    row = db.execute("select cursor from cursor_state where id=1").fetchone()
                    cursor = row[0] if row else 0
                for update in telegram(token, "getUpdates", offset=cursor,
                                       timeout=25, allowed_updates=["message"]):
                    reply(update, token, owner, report, today, db)
                    cursor = update["update_id"] + 1
                    if cursor_file:
                        with open(cursor_file, "w", encoding="utf-8") as fh:
                            fh.write(str(cursor))
                    else:
                        with db:
                            db.execute("insert or replace into cursor_state values(1,?)", (cursor,))
                if os.getenv("TELEGRAM_POLL_ONCE", "").strip():
                    print("Telegram polled once.")
                    return 0
                if poll_window and time.monotonic() - poll_started >= poll_window:
                    print("Telegram poll window finished.", flush=True)
                    return 0
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                print(f"Telegram failed ({type(exc).__name__})", flush=True)
                if action == "publish":
                    return 1
                time.sleep(15)


if __name__ == "__main__":
    raise SystemExit(main())
