import sqlite3
import unittest
from unittest.mock import patch
from engine.notifications.__main__ import LABEL_TO_COMMAND, deliver, keyboard, render, reply


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.report = {"date": "2026-11-22", "summary": "خلاصه", "status": "ok", "signals": [{"نماد": "آزمایشی"}]}

    def test_old_report_hidden(self):
        self.assertNotIn("آزمایشی", render("/signals", self.report, "2026-11-23"))
        self.assertIn("2026-11-22", render("/status", self.report, "2026-11-23"))

    def test_previous_session_report_is_still_current(self):
        report = dict(self.report, generated_at="2026-11-23T10:00:00+03:30")
        self.assertIn("آزمایشی", render("/report", report, "2026-11-23"))
        self.assertIn("جلسه تحلیل", render("/status", report, "2026-11-23"))

    def test_unavailable_suppresses_signals(self):
        self.report["status"] = "unavailable"
        self.assertNotIn("آزمایشی", render("/signals", self.report, self.report["date"]))

    @patch("engine.notifications.__main__.telegram")
    def test_owner_only(self, call):
        for sender, chat_type in [(456, "private"), (123, "group"), (123, "private")]:
            update = {"message": {"chat": {"id": 123, "type": chat_type}, "from": {"id": sender}, "text": "/today"}}
            reply(update, "mock", "123", self.report, self.report["date"])
        call.assert_called_once()
        self.assertIn("آزمایشی", call.call_args.kwargs["text"])

    @patch("engine.notifications.__main__.telegram")
    def test_publish_dedup(self, call):
        with sqlite3.connect(":memory:") as db:
            db.execute("create table sent(id text primary key)")
            for _ in range(2):
                deliver("mock", "123", "گزارش", db, "2026-11-22")
            call.assert_called_once()

    @patch("engine.notifications.__main__.telegram")
    def test_persian_button_uses_reply_keyboard(self, call):
        label = next(iter(LABEL_TO_COMMAND))
        update = {"message": {"chat": {"id": 123, "type": "private"},
                              "from": {"id": 123}, "text": label}}
        reply(update, "mock", "123", self.report, "2026-11-22")
        self.assertEqual(call.call_args.kwargs["reply_markup"], keyboard())
        self.assertIn("آزمایشی", call.call_args.kwargs["text"])

    @patch("engine.notifications.__main__.telegram", side_effect=RuntimeError("offline"))
    def test_failed_delivery_remains_retryable(self, call):
        with sqlite3.connect(":memory:") as db:
            db.execute("create table sent(id text primary key)")
            with self.assertRaises(RuntimeError):
                deliver("mock", "123", "گزارش", db, "2026-11-22")
            self.assertEqual(0, db.execute("select count(*) from sent").fetchone()[0])
