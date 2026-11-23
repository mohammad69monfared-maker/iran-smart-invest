"""Data provenance and validation.

Every observation consumed by the signal engine is checked here. Rejected
observations are logged and never reach scoring. All rules are deterministic;
no value is inferred or repaired.
"""
from collections import Counter
from math import isfinite

REQUIRED_BAR_FIELDS = ("date", "open", "high", "low", "close", "volume", "value")


def validate_bars(bars, as_of, *, min_bars=60):
    """Return (valid, reason). Only sessions up to ``as_of`` may be used."""
    if not isinstance(bars, list):
        return False, "سری قیمتی نامعتبر است"
    if len(bars) < min_bars:
        return False, f"حداقل {min_bars} جلسه لازم است"
    days = []
    for bar in bars:
        if not isinstance(bar, dict) or any(field not in bar for field in REQUIRED_BAR_FIELDS):
            return False, "ستون قیمتی لازم موجود نیست"
        if bar.get("adjusted") is not True:
            return False, "داده تعدیلشده نیست"
        try:
            day = str(bar["date"])
            values = [float(bar[k]) for k in REQUIRED_BAR_FIELDS[1:]]
        except (TypeError, ValueError, OverflowError):
            return False, "مقادیر عددی نامعتبرند"
        if not all(isfinite(v) and v >= 0 for v in values):
            return False, "قیمت یا حجم نامعتبر است"
        opening, high, low, close, volume, value = values
        if not (0 < low <= min(opening, close) <= max(opening, close) <= high):
            return False, "محدوده قیمتی ناسازگار است"
        # A genuine session cannot span more than half its own high: Iran's
        # daily limits make that impossible, so such a row is a data fault.
        if (high - low) / high > 0.5:
            return False, "محدوده قیمتی ناسازگار است"
        if day > str(as_of):
            return False, "داده آینده در محاسبات گذشته استفاده شده است"
        days.append(day)
    if days != sorted(set(days)):
        return False, "تاریخها تکراری یا نامرتبند"
    if days[-1] != str(as_of):
        return False, "آخرین جلسه متعلق به تاریخ تحلیل نیست"
    return True, "معتبر"


class QualityTracker:
    """Accumulates per-observation provenance for the daily report."""

    def __init__(self):
        self.records = []
        self._errors = Counter()

    def record(self, *, source, fetched_at, data_time, valid, completeness, symbol=None, errors=()):
        if not 0 <= float(completeness) <= 1:
            raise ValueError("completeness must be between 0 and 1")
        errors = tuple(str(e) for e in errors)
        self.records.append(dict(
            source=str(source), symbol=symbol, fetched_at=fetched_at,
            data_time=data_time, valid=bool(valid),
            completeness=round(float(completeness), 4), errors=errors))
        for error in errors:
            self._errors[error] += 1

    def summary(self):
        by_source = {}
        for record in self.records:
            item = by_source.setdefault(record["source"], dict(checked=0, valid=0, invalid=0))
            item["checked"] += 1
            item["valid" if record["valid"] else "invalid"] += 1
        completeness = [r["completeness"] for r in self.records]
        return dict(
            checked=len(self.records),
            valid=sum(r["valid"] for r in self.records),
            invalid=sum(not r["valid"] for r in self.records),
            mean_completeness=round(sum(completeness) / len(completeness), 4) if completeness else None,
            by_source=by_source,
            errors=dict(self._errors),
        )
