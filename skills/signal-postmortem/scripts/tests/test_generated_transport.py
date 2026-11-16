"""Fictional transport evidence for the scoped #495 migration."""

import copy
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import postmortem_recorder as recorder
import pytest
import requests

ROWS = [{"date": "2026-09-06", "close": 110}, {"date": "2026-09-01", "close": 100}]
KEY = "fictional-transport-secret"


@pytest.fixture
def transport(monkeypatch):
    adapter = importlib.import_module("postmortem_fmp_client")
    module = sys.modules[adapter.load_client_class().__module__]
    state = SimpleNamespace(replies=[(200, ROWS)], sessions=[], calls=[], sleeps=[])

    class Session:
        def __init__(self):
            self.headers = {}
            self.closed = False
            state.sessions.append(self)

        def get(self, url, params=None, timeout=None):
            state.calls.append((url, dict(params or {}), timeout))
            response = state.replies.pop(0)
            if isinstance(response, Exception):
                raise response
            status, payload = response
            return SimpleNamespace(
                status_code=status, json=lambda: copy.deepcopy(payload), text=str(payload)
            )

        def close(self):
            self.closed = True

    monkeypatch.setattr(module.requests, "Session", Session)
    monkeypatch.setattr(module.time, "sleep", state.sleeps.append)
    state.adapter = adapter
    return state


def fetch():
    return recorder.fetch_price_data("FICTION", "2026-09-01", "2026-09-26", KEY)


def test_exact_range_uses_sibling_transport_and_closes(transport):
    assert fetch() == {"2026-09-06": 110, "2026-09-01": 100}
    assert transport.calls == [
        (
            "https://financialmodelingprep.com/stable/historical-price-eod/full",
            {"symbol": "FICTION", "from": "2026-09-01", "to": "2026-09-26", "apikey": KEY},
            30,
        )
    ]
    assert transport.sessions[0].closed


@pytest.mark.parametrize(
    "rows",
    [
        [ROWS[0], ROWS[0]],
        [{"date": "2026-09-06"}],
        [{"close": 110}],
        [{"date": "2026-09-06", "close": float("nan")}],
        [{"date": "2026-09-06", "close": float("inf")}],
        [{"date": "2026-09-06", "close": True}],
        [{"date": "2026-09-06", "close": "110"}],
        [{"date": "2026-09-06", "close": 0}],
        [{"date": "2026-02-30", "close": 110}],
        [None],
    ],
)
def test_raw_invalid_evidence_is_not_normalized_away(transport, rows):
    transport.replies = [(200, rows)]
    assert fetch() == {}
    assert transport.sessions[0].closed


def test_filter_dates_without_truncating_or_reordering_evidence(transport):
    transport.replies = [(200, [{"date": "2000-01-01", "close": 5}, *ROWS])]
    assert fetch() == {row["date"]: row["close"] for row in ROWS}


@pytest.mark.parametrize(
    "body",
    [
        {"Error Message": KEY},
        {"historical": None},
        {"historicalStockList": [None]},
        {"historicalStockList": [{"symbol": None, "historical": ROWS}]},
        {"historicalStockList": [{"symbol": "OTHER", "historical": ROWS}]},
    ],
)
def test_malformed_or_wrong_symbol_envelopes_fail_safely(transport, body, capsys):
    transport.replies = [(200, body)]
    assert fetch() == {}
    assert KEY not in capsys.readouterr().err


@pytest.mark.parametrize("status", [401, 402, 403, 404, 500])
def test_http_failure_has_no_legacy_fallback_or_invented_price(transport, status, capsys):
    transport.replies = [(status, {"error": KEY})]
    assert fetch() == {}
    assert len(transport.calls) == 1
    assert KEY not in capsys.readouterr().err


def test_request_exception_redacts_secret_and_closes(transport, capsys):
    transport.replies = [requests.exceptions.ConnectionError(f"url?apikey={KEY}&symbol=X")]
    assert fetch() == {}
    assert KEY not in capsys.readouterr().err
    assert transport.sessions[0].closed


def test_batch_reuses_rate_limit_state_and_cleans_up(transport):
    transport.replies = [(429, {}), (429, {})]
    with transport.adapter.price_data_session(KEY):
        assert fetch() == {}
        assert fetch() == {}
        assert len(transport.sessions) == 1
        assert not transport.sessions[0].closed
    assert len(transport.calls) == 2  # one retry total, not for every signal
    assert 60 in transport.sleeps
    assert transport.sessions[0].closed


def test_retry_then_success_and_multiple_signal_timing(transport):
    transport.replies = [(429, {}), (200, ROWS), (200, ROWS)]
    with transport.adapter.price_data_session(KEY):
        assert fetch() and fetch()
    assert len(transport.sessions) == 1
    assert len(transport.calls) == 3
    assert any(0 < delay <= 0.3 for delay in transport.sleeps)
    assert transport.sessions[0].closed


def test_scope_restored_and_closed_on_exception(transport):
    with pytest.raises(RuntimeError, match="fictional interruption"):
        with transport.adapter.price_data_session(KEY):
            assert fetch()
            raise RuntimeError("fictional interruption")
    transport.replies = [(200, ROWS)]
    assert fetch()
    assert len(transport.sessions) == 2
    assert all(s.closed for s in transport.sessions)


def test_actual_batch_uses_one_session_and_skips_no_price(transport, tmp_path, monkeypatch):
    signals = [
        {
            "signal_id": f"fixture{i}",
            "ticker": f"ZZ{i}",
            "signal_date": "2026-09-01",
            "entry_price": 100,
            "predicted_direction": "LONG",
        }
        for i in range(2)
    ]
    source = tmp_path / "signals.json"
    source.write_text(json.dumps(signals))
    transport.replies = [(429, {}), (429, {})]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(Path(recorder.__file__)),
            "--signals-file",
            str(source),
            "--api-key",
            KEY,
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(SystemExit) as result:
        recorder.main()
    assert result.value.code == 1
    assert len(transport.sessions) == 1 and len(transport.calls) == 2
    assert transport.sessions[0].closed
    assert not list((tmp_path / "out/postmortems").glob("*.json"))
