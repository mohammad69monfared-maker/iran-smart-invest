"""Publish a completed daily report to Supabase."""
import json
import os
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class CloudError(RuntimeError):
    """Recoverable publishing error safe for status logs."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def publish_report(report: dict, *, report_date: str, run_id: str | None = None) -> str:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url and not key:
        return "disabled"
    parsed = urlsplit(url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not (key and parsed.hostname and not parsed.username and not parsed.password
            and not parsed.path and not parsed.query and not parsed.fragment
            and (parsed.scheme == "https" or (local and parsed.scheme == "http"))):
        raise CloudError("Invalid Supabase server configuration")
    if not isinstance(report, dict) or not report:
        raise ValueError("A non-empty report object is required")
    if date.fromisoformat(report_date).isoformat() != report_date:
        raise ValueError("report_date must use YYYY-MM-DD")
    payload = {"p_date": report_date, "p_report": report, "p_run_id": run_id}
    headers = {"Content-Type": "application/json", "apikey": key}
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = "Bearer " + key
    request = Request(url + "/rest/v1/rpc/publish_daily_report",
                      data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(),
                      headers=headers, method="POST")
    try:
        with build_opener(_NoRedirects()).open(request, timeout=15) as response:
            if not 200 <= response.status < 300:
                raise CloudError(f"Supabase returned HTTP {response.status}")
    except HTTPError as exc:
        raise CloudError(f"Supabase returned HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise CloudError("Supabase connection failed") from None
    return "synced"
