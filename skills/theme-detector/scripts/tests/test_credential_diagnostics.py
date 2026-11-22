"""Provider exceptions must not reach logs, including traceback text (#778)."""

from unittest.mock import Mock
from urllib.parse import quote

import finviz_performance_client as performance
import pytest
import representative_stock_selector as target
import requests

MARKER = "issue778-marker/with+reserved?chars"


@pytest.mark.parametrize(
    "error_type", [requests.ConnectionError, requests.Timeout, requests.HTTPError]
)
@pytest.mark.parametrize("source", ["elite", "public", "fmp"])
def test_selector_failure_does_not_expose_key(monkeypatch, capsys, caplog, error_type, source):
    error = error_type(f"failed request: ?auth={MARKER}&apikey={quote(MARKER, safe='')}")
    monkeypatch.setattr(target.requests, "get", Mock(side_effect=error))
    monkeypatch.setattr(target, "Overview", Mock(side_effect=error))
    selector = target.RepresentativeStockSelector(
        finviz_elite_key=MARKER, fmp_api_key=MARKER, rate_limit_sec=0
    )
    if source == "fmp":
        monkeypatch.setattr(requests.Session, "get", Mock(side_effect=error))
        result = selector._fetch_etf_holdings("XLK", 4)
    else:
        result = getattr(selector, f"_fetch_finviz_{source}")("Biotechnology", 4, False)
    assert result == []
    assert selector.source_states[source].total_failures == 1
    captured = capsys.readouterr()
    output = captured.out + captured.err + caplog.text
    assert MARKER not in output
    assert quote(MARKER, safe="") not in output
    assert "failed" in output
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize(
    "error_type", [requests.ConnectionError, requests.Timeout, requests.HTTPError]
)
def test_performance_failure_stays_safe(monkeypatch, capsys, error_type):
    monkeypatch.setattr(performance.requests, "get", Mock(side_effect=error_type(MARKER)))
    monkeypatch.setattr(performance, "HAS_FINVIZFINANCE", False)
    assert performance.get_sector_performance(api_key=MARKER) == []
    captured = capsys.readouterr()
    assert MARKER not in captured.out + captured.err
