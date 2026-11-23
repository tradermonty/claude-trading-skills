"""Unknown provider evidence and split amounts cannot establish no dividend/cuts."""

import csv
import json
import sys
from copy import deepcopy

import build_entry_signals as cli
import pytest
import requests
from dividend_basis import analyze_dividends, step1_decision
from test_issue834_regular_yield_history import (
    AS_OF,
    FakeClient,
    daily_prices,
    quarterly_dividends,
    reconstruct,
)


def split_history(reverse=False):
    rows = quarterly_dividends(adj=True)
    for row in rows:
        row["adjDividend"] = 0.25
        row["dividend"] = (0.125 if reverse else 0.50) if row["date"] < "2024-01-01" else 0.25
    return rows


class Response:
    text = ""

    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload


def real_client(monkeypatch, payload=None, status=200, error=None):
    client = cli.FMPClient("offline-test-value", sleep_seconds=0)
    monkeypatch.setattr("time.sleep", lambda _: None)

    def get(*a, **kw):
        if error:
            raise error
        return Response(payload, status)

    monkeypatch.setattr(client.session, "get", get)
    return client


@pytest.mark.parametrize(
    "payload,status,error",
    [
        (None, 200, None),
        ({"Error Message": "access"}, 200, None),
        (None, 403, None),
        (None, 429, None),
        (None, 200, requests.Timeout("timeout")),
        ([None], 200, None),
        ([{}], 200, None),
        ([{"date": "2026-01-01"}], 200, None),
    ],
)
def test_real_client_failed_or_malformed_history_is_unknown(monkeypatch, payload, status, error):
    assert real_client(monkeypatch, payload, status, error).get_stock_dividend("SYN") is None


def test_real_client_empty_success_is_confirmed_empty(monkeypatch):
    assert real_client(monkeypatch, []).get_stock_dividend("SYN") == []


def test_unknown_basis_is_recheck_without_profile_substitution():
    b = analyze_dividends(None, 20.0)
    assert b.status == "ASSUMPTION-REQUIRED"
    assert step1_decision(b, 1.0)[0] == "STEP1-RECHECK"
    row = cli.build_entry_row(
        "SYN", 0.5, {"price": 20}, {"lastDiv": 10}, [], dividend_history=None, floor_pct=1.0
    )
    assert row["step1_verdict"] == "STEP1-RECHECK"
    assert row["dividend_basis"]["status"] == "ASSUMPTION-REQUIRED"
    assert row["t1_blocked"] and not row["order_ready"]
    assert row["provenance"]["dividend_source"] == "unavailable"
    assert row["annual_dividend_per_share"] is None
    assert row["current_yield_pct"] is None


def test_confirmed_empty_remains_fail_no_dividend():
    assert step1_decision(analyze_dividends([], 20), 1.0) == ("FAIL", "no_dividend")


@pytest.mark.parametrize("reverse", [False, True])
def test_split_adjusted_series_avoids_false_cut_or_growth(reverse):
    h = split_history(reverse)
    original = deepcopy(h)
    b = analyze_dividends(h, 20, as_of_date=AS_OF)
    assert not b.cut_flag
    assert not b.variable_policy_flag
    assert b.latest_declared_annualized == 1.0
    assert b.last_increase_date is None
    assert b.dividend_amount_basis == "split_adjusted"
    assert step1_decision(b, 1.0)[0] != "FAIL"
    assert h == original


def test_genuine_adjusted_cut_remains_fail():
    h = split_history()
    h[-1]["adjDividend"] = 0.20
    b = analyze_dividends(h, 20, as_of_date=AS_OF)
    assert b.cut_flag
    assert step1_decision(b, 1.0) == ("FAIL", "dividend_cut")


@pytest.mark.parametrize("value", [None, "bad", float("nan"), float("inf"), 0, -1, True, 10**400])
def test_invalid_adjusted_value_cannot_fall_back_to_raw(value):
    h = split_history()
    h[6]["adjDividend"] = value
    b = analyze_dividends(h, 20, as_of_date=AS_OF)
    assert b.status == "ASSUMPTION-REQUIRED"
    assert step1_decision(b, 1.0)[0] == "STEP1-RECHECK"


def test_mixed_adjustment_basis_is_not_compared():
    h = split_history()
    del h[6]["adjDividend"]
    assert analyze_dividends(h, 20).status == "ASSUMPTION-REQUIRED"


def test_string_adjusted_numbers_are_accepted():
    h = split_history()
    for row in h:
        row["adjDividend"] = "0.25"
    assert not analyze_dividends(h, 20).cut_flag


@pytest.mark.parametrize(
    "splits", [None, [{"date": "2024-01-01", "numerator": 2, "denominator": 1}]]
)
def test_raw_only_needs_confirmed_split_basis_when_required(splits):
    b = analyze_dividends(
        quarterly_dividends(),
        20,
        as_of_date=AS_OF,
        split_history=splits,
        require_split_evidence=True,
    )
    assert b.status == "ASSUMPTION-REQUIRED"
    assert step1_decision(b, 1.0)[0] == "STEP1-RECHECK"


def test_confirmed_no_splits_raw_history_remains_usable():
    b = analyze_dividends(
        quarterly_dividends(), 20, as_of_date=AS_OF, split_history=[], require_split_evidence=True
    )
    assert b.status == "OK"
    assert b.dividend_amount_basis == "raw_no_splits_confirmed"


def test_original_currency_split_basis_requires_review():
    h = split_history()
    for r in h:
        r.update(
            original_dividend=r["dividend"] * 100,
            original_currency="JPY",
            original_dividend_source="synthetic issuer release",
        )
    b = analyze_dividends(h, 20, as_of_date=AS_OF)
    assert b.status == "ASSUMPTION-REQUIRED"
    assert step1_decision(b, 1.0)[0] == "STEP1-RECHECK"


@pytest.mark.parametrize(
    "h",
    [
        [{"date": "2030-01-01", "dividend": 1}],
        [{"date": "2030-01-01", "declarationDate": "2030-01-01", "dividend": 1}],
        [{"date": "invalid", "dividend": 1}],
        [{"date": "2026-01-01", "dividend": "bad"}],
    ],
)
def test_nonempty_but_unusable_is_not_confirmed_absence(h):
    assert analyze_dividends(h, 20, as_of_date=AS_OF).status == "ASSUMPTION-REQUIRED"


def test_future_bad_adjusted_value_does_not_poison_historical_analysis():
    h = split_history()
    h.append({"date": "2030-01-01", "dividend": 1, "adjDividend": "bad"})
    assert analyze_dividends(h, 20, as_of_date=AS_OF).status == "OK"


def test_reconstructed_yield_and_current_numerator_agree():
    h = split_history()
    b = analyze_dividends(h, 20, as_of_date=AS_OF)
    yh = reconstruct(dividends=h)
    assert yh.status == "OK"
    assert b.latest_declared_annualized == 1.0
    assert all(o["regular_annualized"] == 1.0 for o in yh.observations)


@pytest.mark.parametrize(
    "dividends,splits,expected",
    [
        (None, [], "STEP1-RECHECK"),
        ([], [], "FAIL"),
        ([{"date": "2030-01-01", "dividend": 1}], [], "STEP1-RECHECK"),
        ([{"date": "invalid", "dividend": 1}], [], "STEP1-RECHECK"),
        (quarterly_dividends(), None, "STEP1-RECHECK"),
        (quarterly_dividends(), [{}], "STEP1-RECHECK"),
        (quarterly_dividends(), [{"date": "invalid"}], "STEP1-RECHECK"),
        (split_history(), [{"date": "2024-01-01"}], "HOLD-REVIEW"),
    ],
)
def test_real_cli_reports_evidence_status(monkeypatch, tmp_path, dividends, splits, expected):
    class Client(FakeClient):
        def get_stock_dividend(self, ticker):
            return dividends

        def get_splits(self, ticker):
            return splits

    monkeypatch.setattr(cli, "FMPClient", Client)
    monkeypatch.setenv("FMP_API_KEY", "offline-test-value")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_entry_signals.py",
            "--tickers",
            "SYN",
            "--as-of",
            AS_OF,
            "--yield-floor",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert cli.main() == 0
    row = json.loads((tmp_path / f"kanchi_entry_signals_{AS_OF}.json").read_text())["rows"][0]
    assert row["step1_verdict"] == expected
    if dividends is None:
        assert row["step1_reason"] == "dividend_history_unavailable"
        assert row["t1_blocked"] and not row["order_ready"]
    with (tmp_path / f"kanchi_entry_signals_{AS_OF}.csv").open() as f:
        csv_row = next(csv.DictReader(f))
    assert csv_row["dividend_amount_basis"] == row["dividend_basis"]["dividend_amount_basis"]
    assert csv_row["dividend_history_status"] == row["dividend_basis"]["status"]
    md = (tmp_path / f"kanchi_entry_signals_{AS_OF}.md").read_text()
    assert row["dividend_basis"]["dividend_amount_basis"] in md


@pytest.mark.parametrize(
    "payload,status,expected",
    [(None, 403, "STEP1-RECHECK"), ([], 200, "FAIL"), (split_history(), 200, "HOLD-REVIEW")],
)
def test_cli_runs_real_generated_transport_with_fake_http(
    monkeypatch, tmp_path, payload, status, expected
):
    calls = []

    def get(session, url, params=None, timeout=None, **kw):
        endpoint = url.rsplit("/", 1)[-1]
        calls.append(endpoint)
        if endpoint == "dividends":
            return Response(payload, status)
        data = {
            "quote": [{"symbol": "SYN", "price": 20, "date": AS_OF}],
            "profile": [{"symbol": "SYN", "sector": "Consumer Defensive", "lastDividend": 99}],
            "ratios": [{"dividendYield": 0.04}],
            "full": daily_prices(),
            "splits": [{"date": "2024-01-01"}],
            "income-statement": [],
            "cash-flow-statement": [],
        }
        return Response(data[endpoint])

    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setenv("FMP_API_KEY", "offline-test-value")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_entry_signals.py",
            "--tickers",
            "SYN",
            "--as-of",
            AS_OF,
            "--yield-floor",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert cli.main() == 0
    row = json.loads((tmp_path / f"kanchi_entry_signals_{AS_OF}.json").read_text())["rows"][0]
    assert row["step1_verdict"] == expected
    assert "dividends" in calls and "splits" in calls
    if payload is None:
        assert row["annual_dividend_per_share"] is None
        assert row["step1_reason"] == "dividend_history_unavailable"
    if payload:
        assert row["dividend_basis"]["cut_flag"] is False
        assert row["annual_dividend_per_share"] == 1.0


@pytest.mark.parametrize("splits", [[None], [{}], [{"date": "invalid"}], {"date": "2024-01-01"}])
def test_malformed_split_response_is_unknown(monkeypatch, splits):
    assert real_client(monkeypatch, splits).get_splits("SYN") is None


@pytest.mark.parametrize("splits", [[None], [{}], [{"date": "invalid"}], {"date": "2024-01-01"}])
def test_malformed_split_evidence_cannot_confirm_a_raw_cut(splits):
    h = quarterly_dividends()
    for r in h:
        r["dividend"] = 0.50 if r["date"] < "2026-01-01" else 0.25
    b = analyze_dividends(
        h, 20, as_of_date=AS_OF, split_history=splits, require_split_evidence=True
    )
    assert b.status == "ASSUMPTION-REQUIRED"
    assert step1_decision(b, 1.0)[0] == "STEP1-RECHECK"
