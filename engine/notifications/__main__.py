import argparse
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

HELP = "/today گزارش امروز\n/signals فرصت‌ها\n/alerts هشدارها\n/portfolio سبد\n/status آخرین تحلیل\n/help راهنما"
REPORT = Path("data/latest.json")


def telegram(token, method, **body):
    req = Request(f"https://api.telegram.org/bot{token}/{method}",
                  data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
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


def render(command, report, today):
    if command in ("/start", "/help"):
        return HELP
    if not report:
        return "هنوز گزارشی ثبت نشده است."
    date = report.get("date")
    if command == "/status":
        return f"آخرین تحلیل {date}\n{report.get('summary', '')}"
    if date != today:
        return f"گزارش امروز در دسترس نیست. آخرین گزارش مربوط به {date} است."
    if command == "/today":
        return f"گزارش بورس {date}\n{report.get('summary', '')}\n{render('/signals', report, today)}\n{render('/alerts', report, today)}"
    if command == "/signals":
        if report.get("status") not in ("ok", "partial"):
            return "داده معتبر برای اعلام فرصت در دسترس نیست."
        return display(report.get("signals", [])[:5]) or "فرصت مناسب شناسایی نشد."
    if command == "/portfolio":
        return display(report.get("portfolio", {})) or "اطلاعات سبد در این گزارش موجود نیست."
    if command == "/alerts":
        return display(report.get("alerts", [])) or "هشداری در گزارش ثبت نشده است."
    return HELP


def deliver(token, owner, message, db=None, date=""):
    for pos in range(0, len(message), 1800):
        chunk = message[pos:pos + 1800]
        key = hashlib.sha256(f"{owner}/{date}/{pos}/{chunk}".encode()).hexdigest()
        if db and db.execute("select 1 from sent where id=?", (key,)).fetchone():
            continue
        telegram(token, "sendMessage", chat_id=owner, text=chunk)
        if db:
            db.execute("insert or ignore into sent values (?)", (key,))
            db.commit()


def reply(update, token, owner, report, today):
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private" or str(chat.get("id")) != owner or str((msg.get("from") or {}).get("id")) != owner:
        return
    words = msg.get("text", "").split()
    if words:
        deliver(token, owner, render(words[0].split("@")[0], report, today))


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
    with sqlite3.connect(REPORT.parent / "telegram.sqlite3") as db:
        db.execute("create table if not exists sent(id text primary key)")
        db.execute("create table if not exists cursor_state(id integer primary key, cursor integer)")
        while True:
            today = datetime.now(timezone(timedelta(hours=3, minutes=30))).date().isoformat()
            try:
                report = json.loads(REPORT.read_text(encoding="utf-8-sig")) if REPORT.exists() else {}
                if action == "publish":
                    if report.get("date") == today:
                        deliver(token, owner, render("/today", report, today), db, today)
                        print("Telegram report delivered or previously sent.")
                    else:
                        print("No current report to send.")
                    return 0
                row = db.execute("select cursor from cursor_state where id=1").fetchone()
                for update in telegram(token, "getUpdates", offset=row[0] if row else 0, timeout=25, allowed_updates=["message"]):
                    reply(update, token, owner, report, today)
                    with db:
                        db.execute("insert or replace into cursor_state values(1,?)", (update["update_id"]+1,))
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                print(f"Telegram failed ({type(exc).__name__})", flush=True)
                if action == "publish":
                    return 1
                time.sleep(15)


if __name__ == "__main__":
    raise SystemExit(main())
