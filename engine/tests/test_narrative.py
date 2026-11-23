import unittest

from engine.reports import build_narrative, optional_ollama


REPORT = dict(
    date="2026-03-30", generated_at="2026-03-30T15:00:00+03:30",
    status="ok", summary="۱ فرصت برای بررسی شناسایی شد.",
    scanned=100, rejected=99,
    market=dict(index=1000, equal_weight=500, turnover=123456),
    data_quality=dict(checked=100, valid=98),
    signals=[dict(symbol="نماد", score=80.0, reasons=["روند صعودی", "افزایش حجم"],
                  entry_low=90, entry_high=92, stop_loss=85, target1=104, target2=110,
                  expires="2026-04-03", invalidation="شکست حد ضرر", risks=["صف فروش"])],
    alerts=["نماد · عبور از حد ضرر"],
)


class NarrativeTests(unittest.TestCase):
    def test_uses_only_computed_fields(self):
        text = build_narrative(REPORT)
        self.assertIn("چرا انتخاب شد", text)
        self.assertIn("روند صعودی", text)
        self.assertIn("90 تا 92", text)
        self.assertIn("شکست حد ضرر", text)
        self.assertIn("تضمین", text)
        self.assertIn("نماد · عبور از حد ضرر", text)

    def test_no_opportunity(self):
        text = build_narrative(dict(REPORT, signals=[]))
        self.assertIn("فرصت مناسب شناسایی نشد", text)

    def test_ollama_optional_and_local_only(self):
        self.assertIsNone(optional_ollama("متن", host="", model="x"))
        self.assertIsNone(optional_ollama("متن", host="https://remote.example", model="x"))


if __name__ == "__main__":
    unittest.main()
