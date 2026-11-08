"""gh-672: the earnings-calendar provider caps its response at 4000 rows and
keeps the newest dates, so one request over a multi-day window silently drops
the oldest days. `get_earnings_calendar` now fetches one day at a time,
concatenates, dedupes on (symbol, date), and warns when a single day still
hits the cap. The transport is mocked; no API key or network is used.
"""

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fmp_client import FMPClient

PROVIDER_CAP = 4000


def _make_client():
    client = FMPClient(api_key="test_key", max_api_calls=200)
    client.max_retries = 0
    client.RATE_LIMIT_DELAY = 0
    return client


def _response(rows):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = rows
    return resp


def _patch_provider_cap(monkeypatch):
    """Emulate the provider: multi-day requests keep only the newest
    PROVIDER_CAP rows; single-day requests return everything."""

    def fake_get(url, params=None, timeout=30):
        frm = date.fromisoformat(params["from"])
        to = date.fromisoformat(params["to"])
        window = (to - frm).days
        # Deterministic row generator for the whole requested range.
        all_rows = []
        day = frm
        index = 0
        while day <= to:
            for _ in range(3):
                all_rows.append(
                    {
                        "symbol": f"S{index % 7}",
                        "date": day.isoformat(),
                        "eps": float(index),
                        "time": "bmo" if index % 2 else None,
                    }
                )
                index += 1
            day += timedelta(days=1)
        if window > 0:
            all_rows = all_rows[-PROVIDER_CAP:]
        return _response(all_rows)

    return fake_get


def test_chunked_window_keeps_the_oldest_days(monkeypatch):
    client = _make_client()
    fake_get = _patch_provider_cap(monkeypatch)
    client.session.get = MagicMock(side_effect=fake_get)

    start = date(2026, 10, 24)
    end = date(2026, 10, 27)
    rows = client.get_earnings_calendar(start.isoformat(), end.isoformat())

    assert rows is not None
    dates = sorted({row["date"] for row in rows})
    assert dates == [(start + timedelta(days=i)).isoformat() for i in range(4)]
    # 4 day-requests, not one multi-day request
    assert client.api_calls_made == 4


def test_single_day_over_cap_warns(monkeypatch, capsys):
    client = _make_client()
    big_day = [
        {"symbol": f"S{n}", "date": "2026-10-26", "eps": 1.0, "time": None}
        for n in range(PROVIDER_CAP)
    ]
    client.session.get = MagicMock(return_value=_response(big_day))

    rows = client.get_earnings_calendar("2026-10-26", "2026-10-26")

    assert rows is not None
    assert len(rows) == PROVIDER_CAP
    err = capsys.readouterr().err
    assert "4000-row provider cap" in err


def test_duplicates_across_days_are_deduped(monkeypatch):
    client = _make_client()

    def fake_get(url, params=None, timeout=30):
        frm = date.fromisoformat(params["from"])
        # The same announcement reported on two consecutive days.
        row = {"symbol": "S0", "date": "2026-10-26", "eps": 1.0, "time": "bmo"}
        rows = (
            [row]
            if frm <= date(2026, 10, 26)
            else [row, {"symbol": "S1", "date": "2026-10-27", "eps": 2.0, "time": None}]
        )
        return _response(rows)

    client.session.get = MagicMock(side_effect=fake_get)
    rows = client.get_earnings_calendar("2026-10-25", "2026-10-27")

    key_count = sum(1 for row in rows if row["symbol"] == "S0")
    assert key_count == 1
    assert any(row["symbol"] == "S1" for row in rows)


def test_transport_failure_still_returns_none(monkeypatch):
    client = _make_client()
    client.session.get = MagicMock(side_effect=requests.exceptions.ConnectionError("network down"))

    assert client.get_earnings_calendar("2026-10-24", "2026-10-26") is None


def test_non_dict_rows_are_passed_through_without_raising():
    client = _make_client()
    day_rows = [{"symbol": "AAA", "date": "2026-10-26", "eps": 1.0}, "junk", None]
    client.session.get = MagicMock(return_value=_response(day_rows))

    rows = client.get_earnings_calendar("2026-10-26", "2026-10-26")

    assert rows is not None
    assert {"symbol": "AAA", "date": "2026-10-26", "eps": 1.0} in rows
    assert "junk" in rows and None in rows


def test_symbolless_rows_are_not_deduped():
    client = _make_client()
    day_rows = [
        {"date": "2026-10-26", "eps": 1.0},
        {"date": "2026-10-26", "eps": 2.0},
        {"symbol": "", "date": "2026-10-26", "eps": 3.0},
    ]
    client.session.get = MagicMock(return_value=_response(day_rows))

    rows = client.get_earnings_calendar("2026-10-26", "2026-10-26")

    assert len(rows) == 3


def test_end_before_start_sets_last_error():
    client = _make_client()
    client.session.get = MagicMock()

    assert client.get_earnings_calendar("2026-10-27", "2026-10-26") is None
    assert "before start" in client._last_error
    client.session.get.assert_not_called()


def test_invalid_date_sets_last_error():
    client = _make_client()
    client.session.get = MagicMock()

    assert client.get_earnings_calendar("not-a-date", "2026-10-26") is None
    assert "invalid earnings calendar range" in client._last_error
    client.session.get.assert_not_called()


def test_non_list_body_is_a_fetch_failure():
    for body in ("oops", 5):
        client = _make_client()
        client.session.get = MagicMock(return_value=_response(body))

        assert client.get_earnings_calendar("2026-10-26", "2026-10-26") is None
        assert "unexpected earnings calendar body" in client._last_error


def test_same_day_rows_for_one_symbol_are_kept():
    # Two sessions (bmo/amc) for one symbol on one day are distinct rows;
    # dedupe applies only to a row repeated on a later queried day.
    client = _make_client()
    day_rows = [
        {"symbol": "AAA", "date": "2026-10-26", "time": "bmo"},
        {"symbol": "AAA", "date": "2026-10-26", "time": "amc"},
    ]
    client.session.get = MagicMock(return_value=_response(day_rows))

    rows = client.get_earnings_calendar("2026-10-26", "2026-10-26")

    assert len(rows) == 2


def test_provider_error_payload_sets_last_error():
    client = _make_client()
    payload = {"Error Message": "Invalid API KEY."}
    client.session.get = MagicMock(return_value=_response(payload))

    assert client.get_earnings_calendar("2026-10-26", "2026-10-27") == payload
    assert "Invalid API KEY." in client._last_error


def test_provider_error_payload_redacts_api_key():
    client = _make_client()
    payload = {"Error Message": "Invalid API KEY: test_key"}
    client.session.get = MagicMock(return_value=_response(payload))

    client.get_earnings_calendar("2026-10-26", "2026-10-26")

    assert "test_key" not in client._last_error
