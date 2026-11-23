"""Gregorian (UTC/Tehran date strings) to Solar Hijri for display only.

The machine-readable report keeps ISO dates; this module is used by the HTML
report and Telegram messages so people see Shamsi dates.
"""
from datetime import date, datetime


def _days_from_civil(year, month, day):
    year -= month <= 2
    era = (year if year >= 0 else year - 399) // 400
    yoe = year - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


_EPOCH = _days_from_civil(622, 3, 22)
_MONTH_DAYS = (31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29)
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _leap(year):
    return ((((year - 474) % 2820) + 474 + 38) * 682) % 2816 < 682


def to_jalali(value, *, persian_digits=True):
    """Return YYYY/MM/DD; accepts a date, datetime or ISO date string."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if not isinstance(value, date):
        raise ValueError("Unsupported date value")
    days = _days_from_civil(value.year, value.month, value.day) - _EPOCH
    year = 1
    while True:
        length = 366 if _leap(year) else 365
        if days < length:
            break
        days -= length
        year += 1
    month = 1
    for length in _MONTH_DAYS:
        if days < length:
            break
        days -= length
        month += 1
    text = f"{year:04d}/{month:02d}/{days + 1:02d}"
    return text.translate(_FA) if persian_digits else text
