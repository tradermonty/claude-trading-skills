"""Offline regressions: provider failures must never expose credentials (#778)."""

import pytest
import requests

MARKER = "issue778-marker/with+reserved?chars"


@pytest.mark.parametrize(
    "error_type", [requests.ConnectionError, requests.Timeout, requests.HTTPError]
)
def test_request_failure_does_not_expose_key(monkeypatch, capsys, error_type):
    from urllib.parse import quote

    import check_institutional_endpoint as target

    def fail(*args, **kwargs):
        raise error_type(
            f"request failed: https://example.test/?auth={MARKER}&apikey={quote(MARKER, safe='')}"
        )

    monkeypatch.setenv("FMP_API_KEY", MARKER)
    monkeypatch.setattr(target.requests, "get", fail)
    assert target.check_institutional_endpoint() is False
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert MARKER not in output
    assert quote(MARKER, safe="") not in output
    assert output  # failure remains visible
