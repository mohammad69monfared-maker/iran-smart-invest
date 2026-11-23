"""Template-based Persian narration of already-computed results.

The language model, when configured, only rephrases the text. It never sees a
task to invent prices, signals or percentages.
"""
import json
import os
from urllib.request import Request, urlopen


def _value(value, dash="—"):
    return dash if value is None or value == "" else str(value)


def build_narrative(report):
    """Explain a report using only fields present in that report."""
    lines = [
        f"تاریخ داده: {_value(report.get('date'))}",
        f"زمان پردازش: {_value(report.get('generated_at'))}",
        f"وضعیت: {_value(report.get('status'))}",
        _value(report.get("summary")),
    ]
    market = report.get("market") or {}
    if market:
        lines.append(
            f"شاخص کل: {_value(market.get('index'))} · شاخص هموزن: {_value(market.get('equal_weight'))}"
        )
        if market.get("turnover") is not None:
            lines.append(f"ارزش معاملات ثبتشده بازار: {market['turnover']:,} ریال")
    lines.append(f"نمادهای بررسیشده: {_value(report.get('scanned'))} · ردشده: {_value(report.get('rejected'))}")
    quality = report.get("data_quality") or {}
    if quality:
        lines.append(
            f"سلامت داده: {quality.get('valid', 0)} معتبر از {quality.get('checked', 0)} بررسیشده"
        )
    signals = report.get("signals") or []
    if not signals:
        lines.append("فرصت مناسب شناسایی نشد.")
    for number, signal in enumerate(signals, 1):
        lines.extend([
            "",
            f"{number}) {signal.get('symbol')} — امتیاز {_value(signal.get('score'))}",
            "چرا انتخاب شد: " + ("، ".join(signal.get("reasons") or []) or "دلیل ثبتشده موجود نیست"),
            "در چه شرایطی ورود معتبر است: "
            f"قیمت در محدوده {_value(signal.get('entry_low'))} تا {_value(signal.get('entry_high'))} "
            f"و وضعیت معاملاتی تأییدشده باشد",
            "ابطال سیگنال: " + _value(signal.get("invalidation")),
            "خروج قابل بررسی: "
            f"حد ضرر {_value(signal.get('stop_loss'))} · هدف اول {_value(signal.get('target1'))} "
            f"· هدف دوم {_value(signal.get('target2'))} · انقضا {_value(signal.get('expires'))}",
            "خطرات: " + ("، ".join(signal.get("risks") or []) or "خطر ثبتشده موجود نیست"),
        ])
    alerts = report.get("alerts") or []
    if alerts:
        lines.append("")
        lines.append("هشدارها: " + " · ".join(str(a) for a in alerts))
    lines.append("")
    lines.append("این خروجی تحلیل داده است و توصیه خرید یا تضمین سود محسوب نمیشود.")
    return "\n".join(lines)


def optional_ollama(text, *, host=None, model=None, timeout=8):
    """Optionally rephrase Persian narration through a local Ollama model.

    Returns None when Ollama is not configured or unavailable. The caller must
    keep the template text as the authoritative output.
    """
    host = (host if host is not None else os.getenv("OLLAMA_HOST", "")).strip().rstrip("/")
    model = (model if model is not None else os.getenv("OLLAMA_MODEL", "")).strip()
    if not host or not model or not host.startswith(("http://127.0.0.1", "http://localhost")):
        return None
    prompt = (
        "متن فارسی زیر را تنها از نظر نگارش بازنویسی کن. "
        "هیچ عدد، قیمت، درصد یا جمله جدیدی اضافه نکن و توصیه سرمایهگذاری نکن.\n\n" + text
    )
    try:
        request = Request(
            host + "/api/generate",
            data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        result = payload.get("response")
        return result.strip() if isinstance(result, str) and result.strip() else None
    except (OSError, ValueError):
        return None
