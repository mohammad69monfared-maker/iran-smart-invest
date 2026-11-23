import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from engine.cloud import CloudError, publish_report


class PublishTests(unittest.TestCase):
    def emit(self, **changes):
        params = dict(report={"name": "آزمون"}, report_date="2024-03-23", run_id="x")
        params.update(changes)
        return publish_report(**params)

    def test_unconfigured(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.emit(), "disabled")

    def test_partly_configured_and_insecure_urls(self):
        for url in ["", "http://example.com", "https://u:p@example.com",
                    "https://example.com/private", "https://example.com?q=1"]:
            with self.subTest(url=url), patch.dict("os.environ", {
                "SUPABASE_URL": url, "SUPABASE_SERVICE_ROLE_KEY": "example"}, clear=True):
                with self.assertRaises(CloudError):
                    self.emit()

    def test_request_contract(self):
        for key, expected in [("sb_secret_example", None), ("legacy.jwt.key", "Bearer legacy.jwt.key")]:
            with self.subTest(key=key), patch.dict("os.environ", {
                "SUPABASE_URL": "https://project.example/", "SUPABASE_SERVICE_ROLE_KEY": key
            }, clear=True), patch("engine.cloud.build_opener") as opener:
                opener.return_value.open.return_value.__enter__.return_value.status = 204
                self.assertEqual(self.emit(), "synced")
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, "https://project.example/rest/v1/rpc/publish_daily_report")
                self.assertEqual(request.get_header("Apikey"), key)
                self.assertEqual(request.get_header("Authorization"), expected)
                self.assertEqual(json.loads(request.data), {
                    "p_date": "2024-03-23", "p_report": {"name": "آزمون"}, "p_run_id": "x"})

    def test_error_sanitization(self):
        for error in [HTTPError("https://project.example", 403, "sensitive", {}, None),
                      URLError("sensitive"), TimeoutError("sensitive")]:
            with self.subTest(error=type(error)), patch.dict("os.environ", {
                "SUPABASE_URL": "https://project.example", "SUPABASE_SERVICE_ROLE_KEY": "sensitive"
            }, clear=True), patch("engine.cloud.build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(CloudError) as result:
                    self.emit()
                self.assertNotIn("sensitive", str(result.exception))

    def test_invalid_input(self):
        with patch.dict("os.environ", {
            "SUPABASE_URL": "https://project.example", "SUPABASE_SERVICE_ROLE_KEY": "key"
        }, clear=True), patch("engine.cloud.build_opener") as opener:
            for changes in [{"report_date":"2024-02-30"}, {"report": {}}, {"report":{"x":float("nan")}}]:
                with self.assertRaises(ValueError):
                    self.emit(**changes)
            opener.assert_not_called()
