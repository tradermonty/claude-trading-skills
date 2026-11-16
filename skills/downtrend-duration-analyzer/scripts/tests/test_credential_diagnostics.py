"""Offline regressions: provider failures must never expose credentials (#778)."""

import pytest
import requests

MARKER = "issue778-marker/with+reserved?chars"


@pytest.mark.parametrize(
    "error_type", [requests.ConnectionError, requests.Timeout, requests.HTTPError]
)
def test_request_failure_does_not_expose_key(monkeypatch, capsys, error_type):
    from urllib.parse import quote

    import analyze_downtrends as target

    def fail(*args, **kwargs):
        raise error_type(
            f"request failed: https://example.test/?auth={MARKER}&apikey={quote(MARKER, safe='')}"
        )

    monkeypatch.setattr(target.requests, "get", fail)
    assert target.fetch_stock_list(MARKER) == []
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert MARKER not in output
    assert quote(MARKER, safe="") not in output
    assert output  # failure remains visible
