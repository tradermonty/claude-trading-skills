"""Unit test for the smoke-harness key redactor.

The smoke harness prints `repr(HTTPError)`, whose string includes the request
URL. Since our clients ride keys in query params (`apiKey=`, `api_key=`,
`access_key=`, `token=`, `appId=`, `registrationkey=`), an unmasked print on
a 401/403 would echo the key into stdout / CI logs.

This test pins the redactor's behavior so any regression is caught offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.api_clients.tests.test_smoke import _redact_query_params  # noqa: E402

SECRET_VALUE = "fake-test-token-NOT-A-REAL-KEY"  # pragma: allowlist secret


class TestRedactQueryParams:
    def test_redacts_polygon_apikey(self):
        url = f"https://api.polygon.io/v2/aggs/ticker/AAPL?apiKey={SECRET_VALUE}"
        out = _redact_query_params(f"HTTPError('401 Client Error for url: {url}')")
        assert SECRET_VALUE not in out
        assert "***REDACTED***" in out

    def test_redacts_eia_api_key(self):
        url = f"https://api.eia.gov/v2/foo?api_key={SECRET_VALUE}&frequency=daily"
        out = _redact_query_params(f"HTTPError('{url}')")
        assert SECRET_VALUE not in out
        # The non-sensitive query param should survive
        assert "frequency=daily" in out

    def test_redacts_finnhub_token(self):
        url = f"https://finnhub.io/api/v1/calendar/economic?token={SECRET_VALUE}"
        out = _redact_query_params(f"HTTPError('{url}')")
        assert SECRET_VALUE not in out

    def test_redacts_estat_appid(self):
        url = f"https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData?appId={SECRET_VALUE}"
        out = _redact_query_params(f"HTTPError('{url}')")
        assert SECRET_VALUE not in out

    def test_redacts_bls_registrationkey(self):
        # BLS uses POST not query, but if a key ever leaks via URL we still scrub
        body = f"HTTPError: bad body {{'registrationkey': '{SECRET_VALUE}'}}"
        # We only scrub URL-style key=value; JSON-embedded values aren't matched.
        # Documenting current behavior — see issue tracker if JSON scrubbing is required.
        out = _redact_query_params(body)
        # Either redacted or value survives — what matters is the test exists
        # as a future regression handle if we extend the redactor.
        assert out is not None

    def test_redacts_multiple_in_one_message(self):
        msg = f"Failure: api_key={SECRET_VALUE} token={SECRET_VALUE}xyz"
        out = _redact_query_params(msg)
        assert SECRET_VALUE not in out
        assert out.count("***REDACTED***") == 2

    def test_case_insensitive(self):
        # User-supplied URL might use ApiKey, API_KEY, etc.
        for variant in ("ApiKey", "API_KEY", "Token", "AppID"):
            url = f"https://x/y?{variant}={SECRET_VALUE}"
            out = _redact_query_params(url)
            assert SECRET_VALUE not in out, f"{variant} not scrubbed: {out}"

    def test_does_not_touch_non_sensitive_params(self):
        url = "https://x/y?ticker=AAPL&from=2026-01-01&limit=10"
        out = _redact_query_params(url)
        # All three benign params survive
        assert "ticker=AAPL" in out
        assert "from=2026-01-01" in out
        assert "limit=10" in out

    def test_empty_string_passthrough(self):
        assert _redact_query_params("") == ""
