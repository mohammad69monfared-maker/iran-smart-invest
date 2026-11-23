import unittest

from engine.reports.jalali import to_jalali


class JalaliTests(unittest.TestCase):
    def test_known_dates(self):
        self.assertEqual(to_jalali("2026-11-23", persian_digits=False), "1405/09/02")
        self.assertEqual(to_jalali("2026-03-21", persian_digits=False), "1405/01/01")
        self.assertEqual(to_jalali("2025-03-20", persian_digits=False), "1404/01/01")

    def test_persian_digits(self):
        self.assertEqual(to_jalali("2026-11-23"), "۱۴۰۵/۰۹/۰۲")


if __name__ == "__main__":
    unittest.main()
