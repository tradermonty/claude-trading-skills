"""Tests that generated fmp_client.py stderr never leaks the apikey (Issue #357).

Covers all 10 vendored ``fmp_client.py`` files (rendered from
``scripts/fmp_client/core_template.py.tmpl`` and the four
``scripts/fmp_client/specials/*.py.tmpl``): a low-level request exception and a
non-200 HTTP response must both have ``apikey=...`` masked to
``apikey=REDACTED`` wherever the provider text (URL or response body) is
echoed to stderr, and nothing must reach stdout.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]

FAKE_KEY = "FAKEKEY123"  # pragma: allowlist secret

# Family B: core_template.py.tmpl clients that also enforce an API call budget
# (constructor takes max_api_calls).
FAMILY_B = [
    "skills/pead-screener/scripts/fmp_client.py",
    "skills/earnings-trade-analyzer/scripts/fmp_client.py",
    "skills/ibd-distribution-day-monitor/scripts/fmp_client.py",
]

# Family A: core_template.py.tmpl clients without budget enforcement
# (constructor takes only api_key).
FAMILY_A = [
    "skills/vcp-screener/scripts/fmp_client.py",
    "skills/parabolic-short-trade-planner/scripts/fmp_client.py",
    "skills/ftd-detector/scripts/fmp_client.py",
]

CORE_CLIENTS = FAMILY_B + FAMILY_A

SPECIAL_CLIENTS = [
    "skills/canslim-screener/scripts/fmp_client.py",
    "skills/macro-regime-detector/scripts/fmp_client.py",
    "skills/market-top-detector/scripts/fmp_client.py",
]

GARP_CLIENT = "skills/us-undervalued-growth-screener/scripts/fmp_client.py"

ALL_CLIENTS = CORE_CLIENTS + SPECIAL_CLIENTS + [GARP_CLIENT]

# The six clients rendered from core_template.py.tmpl store request failures
# in self._last_error; the three specials (canslim/macro/market_top) and garp
# do not have a _last_error attribute.
LAST_ERROR_CLIENTS = CORE_CLIENTS


def _load(rel_path: str):
    abs_path = REPO_ROOT / rel_path
    skill = abs_path.parent.parent.name.replace("-", "_")
    name = f"_fmp_redaction_{skill}"
    sys.modules.pop(name, None)
    sys.modules.pop("_fmp_compat", None)  # avoid leaking one skill's shim into another
    sys.path.insert(0, str(abs_path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, str(abs_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(abs_path.parent))


def _make_client(rel_path: str, tmp_path: Path, api_key="test_key"):  # pragma: allowlist secret
    """Construct an FMPClient instance for `rel_path`, matching its family's signature."""
    mod = _load(rel_path)
    if rel_path == GARP_CLIENT:
        client = mod.FMPClient(
            api_key=api_key,  # pragma: allowlist secret
            max_api_calls=200,
            cache_path=tmp_path / "c.sqlite3",
        )
    elif rel_path in FAMILY_B:
        client = mod.FMPClient(api_key=api_key, max_api_calls=200)  # pragma: allowlist secret
    else:
        client = mod.FMPClient(api_key=api_key)  # pragma: allowlist secret
    return mod, client


class _StubResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):
        raise ValueError("not json")


@pytest.mark.parametrize("rel_path", ALL_CLIENTS)
def test_request_exception_redacts_key(rel_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod, client = _make_client(rel_path, tmp_path)

    # The `url` argument itself never carries the key (auth is injected into
    # `params` or a session header by the client, never baked into the caller's
    # url) -- only the underlying HTTP library's exception text does, because
    # it serializes the final request (url + params) into its message.
    url = "https://financialmodelingprep.com/stable/quote?symbol=AAPL"

    def _raise(*args, **kwargs):
        raise requests.exceptions.ConnectionError(
            f"HTTPSConnectionPool(host='financialmodelingprep.com', port=443): "
            f"Max retries exceeded with url: /stable/quote?symbol=AAPL&apikey={FAKE_KEY} "
            f"(Caused by ...)"
        )

    monkeypatch.setattr(client.session, "get", _raise)

    if rel_path == GARP_CLIENT:
        result = client._request_json(url, {})
    else:
        result = client._rate_limited_get(url, {})

    assert result is None
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.err
    assert FAKE_KEY not in captured.out
    assert captured.out == ""
    assert "apikey=REDACTED" in captured.err
    if rel_path in LAST_ERROR_CLIENTS:
        assert FAKE_KEY not in client._last_error


@pytest.mark.parametrize("rel_path", CORE_CLIENTS + SPECIAL_CLIENTS)
def test_non_200_response_redacts_key(rel_path, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod, client = _make_client(rel_path, tmp_path)

    url = "https://financialmodelingprep.com/stable/quote?symbol=AAPL"
    stub = _StubResponse(
        403,
        f'{{"Error Message": "Invalid API key, see .../?apikey={FAKE_KEY} for details"}}',
    )
    monkeypatch.setattr(client.session, "get", lambda *a, **k: stub)

    result = client._rate_limited_get(url, {})

    assert result is None
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.err
    assert FAKE_KEY not in captured.out
    assert captured.out == ""
    assert "apikey=REDACTED" in captured.err
    if rel_path in LAST_ERROR_CLIENTS:
        assert FAKE_KEY not in client._last_error


def test_garp_non_200_response_has_no_key_to_leak(tmp_path, monkeypatch, capsys):
    """garp's non-200 branch prints the bare url + status only (never response.text).

    Callers never put ``apikey`` in the ``url`` itself (garp injects it into the
    query params dict inside ``_request_json``), so this print site never carries
    the key in the first place -- assert that invariant holds.
    """
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod, client = _make_client(GARP_CLIENT, tmp_path)

    url = "https://financialmodelingprep.com/stable/quote?symbol=AAPL"
    stub = _StubResponse(403, f'{{"Error Message": "...?apikey={FAKE_KEY}..."}}')
    monkeypatch.setattr(client.session, "get", lambda *a, **k: stub)

    result = client._request_json(url, {})

    assert result is None
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.err
    assert FAKE_KEY not in captured.out
    assert captured.out == ""


def test_garp_failure_endpoint_identity_raw_but_diagnostics_masked(tmp_path, monkeypatch):
    """`_record_failure` keeps the raw url as the identity key (circuit breaker and
    capability-cache gate compare against it) and masks the key only in the
    `diagnostics()` failure samples."""
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    _mod, client = _make_client(GARP_CLIENT, tmp_path)

    url = f"https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey={FAKE_KEY}"
    client._record_failure(url, "http_403", 403)

    assert client._endpoint_failures.get(url) == 1
    assert client.failures[-1]["endpoint"] == url
    samples = client.diagnostics()["failure_samples"]
    assert samples[-1]["endpoint"].endswith("apikey=REDACTED")
    assert FAKE_KEY not in str(samples)


# Include every core client, including the Issue #495 Batch A clients.
ADDITIONAL_CORE_CLIENTS = [
    f"skills/{skill}/scripts/fmp_client.py"
    for skill in (
        "earnings-calendar",
        "economic-calendar-fetcher",
        "institutional-flow-tracker",
        "cot-contrarian-detector",
        "value-dividend-screener",
        "dividend-growth-pullback-screener",
        "kanchi-dividend-sop",
    )
]
GENERATED_CLIENTS = ALL_CLIENTS + ADDITIONAL_CORE_CLIENTS


@pytest.mark.parametrize("rel_path", GENERATED_CLIENTS)
@pytest.mark.parametrize("key", ["test_key", "Q"])
def test_bare_secret_exception_redacted(rel_path, key, tmp_path, monkeypatch, capsys):
    _mod, client = _make_client(rel_path, tmp_path)
    client.api_key = key

    def fail(*args, **kwargs):
        raise requests.ConnectionError(f"proxy echoed {key} twice: {key}")

    monkeypatch.setattr(client.session, "get", fail)
    request = client._request_json if rel_path == GARP_CLIENT else client._rate_limited_get
    assert request("https://financialmodelingprep.com/stable/quote", {}) is None
    captured = capsys.readouterr()
    assert key not in captured.err + captured.out
    assert "REDACTED" in captured.err
    assert captured.out == ""
    assert key not in str(getattr(client, "_last_error", ""))
    if rel_path == GARP_CLIENT:
        assert key not in str(client.diagnostics())


@pytest.mark.parametrize("rel_path", [p for p in GENERATED_CLIENTS if p != GARP_CLIENT])
@pytest.mark.parametrize("prefix_length", [0, 195])
def test_http_body_redacted_before_truncation(
    rel_path, prefix_length, tmp_path, monkeypatch, capsys
):
    _mod, client = _make_client(rel_path, tmp_path)
    body = "z" * prefix_length + "test_key" + " suffix test_key"
    monkeypatch.setattr(client.session, "get", lambda *a, **k: _StubResponse(403, body))
    assert client._rate_limited_get("https://financialmodelingprep.com/stable/quote", {}) is None
    captured = capsys.readouterr()
    # A key crossing the 200-character boundary must leave no partial prefix either.
    assert "test_" not in captured.err + captured.out
    assert "test_" not in str(getattr(client, "_last_error", ""))
    assert captured.out == ""


@pytest.mark.parametrize("rel_path", [FAMILY_A[0], FAMILY_A[1]])
def test_csv_fallback_exception_redacted_without_sending_key(
    rel_path, tmp_path, monkeypatch, capsys
):
    mod, client = _make_client(rel_path, tmp_path)

    def fail(url, **kwargs):
        assert "financialmodelingprep" not in url
        assert kwargs == {"timeout": 30}
        raise requests.ConnectionError("third party echoed test_key")

    monkeypatch.setattr(mod.requests, "get", fail)
    assert client._fetch_constituents_csv() is None
    captured = capsys.readouterr()
    assert "test_key" not in captured.err + captured.out
    assert "REDACTED" in captured.err


@pytest.mark.parametrize(
    "skill,method",
    [
        ("macro-regime-detector", "_get_from_yfinance"),
        ("market-top-detector", "_get_hist_from_yfinance"),
    ],
)
def test_yfinance_fallback_exception_redacted(skill, method, tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    _mod, client = _make_client(f"skills/{skill}/scripts/fmp_client.py", tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("fallback echoed test_key")

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=fail, download=fail))
    assert getattr(client, method)("SPY", 30) is None
    captured = capsys.readouterr()
    assert "test_key" not in captured.err + captured.out
    assert "REDACTED" in captured.err


def test_garp_warning_and_diagnostics_redact_bare_url_secret(tmp_path, monkeypatch, capsys):
    _mod, client = _make_client(GARP_CLIENT, tmp_path)
    url = "https://financialmodelingprep.com/stable/test_key"

    def fail(*args, **kwargs):
        raise requests.ConnectionError("test_key")

    monkeypatch.setattr(client.session, "get", fail)
    assert client._request_json(url, {}) is None
    captured = capsys.readouterr()
    assert "test_key" not in captured.err + captured.out
    assert "test_key" not in str(client.diagnostics())
    assert client._endpoint_failures[url] == 1  # raw identity still drives circuit breaker


@pytest.mark.parametrize("rel_path", GENERATED_CLIENTS)
@pytest.mark.parametrize("source", ["explicit", "environment"])
@pytest.mark.parametrize("encoding", ["raw", "quote", "quote_plus", "mixed_hex"])
@pytest.mark.parametrize("failure", ["exception", "http"])
def test_normalized_encoded_secret_never_reaches_diagnostics(
    rel_path, source, encoding, failure, tmp_path, monkeypatch, capsys
):
    from urllib.parse import quote, quote_plus

    key = "Demo+Key/with space=Z"  # pragma: allowlist secret
    monkeypatch.setenv("FMP_API_KEY", " \t" + key + "\n")
    _mod, client = _make_client(
        rel_path, tmp_path, api_key=" \t" + key + "\n" if source == "explicit" else None
    )
    assert client.api_key == key
    if "apikey" in client.session.headers:
        assert client.session.headers["apikey"] == key
    echoed = {
        "raw": key,
        "quote": quote(key, safe=""),
        "quote_plus": quote_plus(key, safe=""),
        "mixed_hex": quote(key, safe="").replace("%2B", "%2b"),
    }[encoding]

    def fail(url, **kwargs):
        if "apikey" not in client.session.headers:
            assert kwargs["params"]["apikey"] == key
        if failure == "exception":
            raise requests.ConnectionError(f"bare echo: {echoed}")
        return _StubResponse(403, f"bare echo: {echoed}")

    monkeypatch.setattr(client.session, "get", fail)
    request = client._request_json if rel_path == GARP_CLIENT else client._rate_limited_get
    assert request("https://financialmodelingprep.com/stable/quote", {}) is None
    captured = capsys.readouterr()
    diagnostics = captured.err + str(getattr(client, "_last_error", ""))
    if rel_path == GARP_CLIENT:
        client._record_failure(f"https://example.test/{echoed}", "http_403", 403)
        diagnostics += str(client.diagnostics())
    assert captured.out == ""
    assert key not in diagnostics
    assert echoed not in diagnostics
    assert "REDACTED" in diagnostics or (rel_path == GARP_CLIENT and failure == "http")


@pytest.mark.parametrize("rel_path", GENERATED_CLIENTS)
def test_whitespace_only_key_preserves_missing_key_policy(rel_path, tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", " \t\n")
    if "macro-regime-detector" in rel_path:
        _mod, client = _make_client(rel_path, tmp_path, api_key=None)
        assert client.api_key == ""
        assert "apikey" not in client.session.headers
    else:
        with pytest.raises(ValueError, match="API key required"):
            _make_client(rel_path, tmp_path, api_key=None)
    if rel_path == GARP_CLIENT:
        mod = _load(rel_path)
        client = mod.FMPClient(api_key=" \n", offline=True, cache_path=tmp_path / "offline.db")
        assert client.api_key == ""


@pytest.mark.parametrize("rel_path", GENERATED_CLIENTS)
def test_short_key_does_not_reprocess_replacement(rel_path, tmp_path):
    _mod, client = _make_client(rel_path, tmp_path, api_key="D")
    assert client._redact_secret("D D") == "***REDACTED*** ***REDACTED***"
