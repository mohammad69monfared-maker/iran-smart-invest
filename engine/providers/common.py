import json
import math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import time


class ProviderError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def day(value):
    try:
        return datetime.strptime(str(value), "%Y%m%d").date().isoformat() if len(str(value)) == 8 else None
    except ValueError:
        return None


# TSETMC's CDN rejects API calls that do not look like they originate from its
# web application. The Referer/Origin fields are required in practice; without
# them the endpoint either answers HTTP 403 or stalls the TLS handshake.
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://www.tsetmc.com/",
    "Origin": "https://www.tsetmc.com",
    "Accept-Language": "fa,en;q=0.9",
}


def get_json(url):
    request = Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25) as response:
                body = response.read(16_000_001)
            if len(body) > 16_000_000:
                raise ProviderError("Response exceeds size limit")
            data = json.loads(body.decode("utf-8-sig"))
            if not isinstance(data, dict):
                raise ProviderError("Unexpected response schema")
            return data
        except HTTPError as exc:
            if attempt >= 2 or exc.code not in (403, 429, 500, 502, 503, 504):
                raise ProviderError(f"HTTP {exc.code}") from exc
        except (URLError, OSError) as exc:
            if attempt >= 2:
                raise ProviderError(f"Connection unavailable ({type(exc).__name__})") from exc
        except (json.JSONDecodeError, UnicodeError) as exc:
            if attempt >= 2:
                raise ProviderError("Non-JSON response") from exc
        time.sleep(1 + attempt)


def rows(payload, key):
    data = payload.get(key)
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ProviderError(f"Invalid schema: {key}")
    return data


def first(record, *keys):
    return next((record[key] for key in keys if record.get(key) is not None), None)

