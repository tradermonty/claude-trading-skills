"""Issue #834: regular-only 5-year average yield rebuilt from dividends + prices.

Everything here is synthetic and offline. Prices are controlled per month so the
expected average is computed by hand-rolled loops that do not call the module.
"""

import csv
import json
import sys
from datetime import date, timedelta

import build_entry_signals as cli
import pytest
import regular_yield_history as ryh
import requests
from build_entry_signals import build_entry_row
from event_scanner import CLEAN_CONFIRMED, ScanResult
from regular_yield_history import (
    YieldHistoryInputError,
    apply_frequency_special_label,
    load_yield_history,
    reconstruct_regular_yield,
)

AS_OF = "2026-11-20"
SECRET = "sekret-key-834-do-not-print"  # pragma: allowlist secret


# --- fixtures -----------------------------------------------------------------


def close_for(year, month):
    return 40.0 + ((year * 12 + month) % 7)


def daily_prices(start=date(2021, 9, 1), end=date(2026, 11, 20)):
    rows = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            rows.append({"date": day.isoformat(), "close": close_for(day.year, day.month)})
        day += timedelta(days=1)
    return rows


def quarterly_amount(day):
    return round(0.50 + 0.02 * (day.year - 2020), 4)


def quarterly_dividends(extra=None, adj=False):
    rows = []
    for year in range(2020, 2027):
        for month in (3, 6, 9, 12):
            day = date(year, month, 15)
            if day > date(2026, 9, 15):
                continue
            row = {"date": day.isoformat(), "dividend": quarterly_amount(day)}
            row["frequency"] = "Quarterly"
            if adj:
                row["adjDividend"] = row["dividend"]
            rows.append(row)
    rows.extend(extra or [])
    return rows


def expected_average(dividends=None, skip=(), as_of_cap=None):
    """Independent hand calculation: last weekday of each month, last pay known by then."""
    pays = [
        (date.fromisoformat(r["date"]), r["dividend"])
        for r in (dividends or quarterly_dividends())
        if r.get("frequency") != "Special" and r.get("label") != "special"
    ]
    values = []
    year, month = 2021, 11
    for _ in range(60):
        nxt = date(year + (month == 12), month % 12 + 1, 1)
        last = nxt - timedelta(days=1)
        while last.weekday() >= 5:
            last -= timedelta(days=1)
        latest = max((d, a) for d, a in pays if d <= last)[1]
        if (year, month) not in skip:
            values.append(latest * 4 / close_for(year, month) * 100)
        year, month = nxt.year, nxt.month
    return sum(values) / len(values)


def reconstruct(dividends=None, prices=None, **kw):
    kw.setdefault("splits", [])
    return reconstruct_regular_yield(
        dividends if dividends is not None else quarterly_dividends(),
        prices if prices is not None else daily_prices(),
        as_of=AS_OF,
        source="synthetic",
        **kw,
    )


FINANCIALS = {
    "sector": "Consumer Defensive",
    "gaap_eps": 5.0,
    "adjusted_eps": 5.0,
    "adjusted_eps_source": "MANUAL",
    "fcf_per_share": 6.0,
}


def entry_row(price, history=None, dividends=None, **updates):
    args = dict(
        ticker="SYN",
        alpha_pp=0.5,
        quote={"price": price, "date": AS_OF},
        profile={"sector": "Consumer Defensive"},
        key_metrics=[{"dividendYield": 0.04}] * 5,
        dividend_history=dividends if dividends is not None else quarterly_dividends(),
        floor_pct=2.0,
        financials=dict(FINANCIALS),
        event_scan=ScanResult(ticker="SYN", result=CLEAN_CONFIRMED),
        as_of=AS_OF,
        yield_history=history if history is not None else reconstruct(),
    )
    args.update(updates)
    return build_entry_row(**args)


# --- 1. steady quarterly history ----------------------------------------------


def test_steady_quarterly_history_matches_hand_calculation():
    result = reconstruct()
    assert result.status == "OK"
    assert result.observation_count == 60
    assert result.expected_observations == 60
    assert result.coverage_ratio == 1.0
    assert result.window_start == "2021-11-01"
    assert result.window_end == "2026-10-31"
    assert result.method == "month_end_60_regular_only_v1"
    assert result.source == "synthetic"
    assert result.avg_yield_pct == pytest.approx(round(expected_average(), 2), abs=0.005)
    assert len(result.observations) == 60
    assert {"date", "close", "regular_annualized", "yield_pct"} <= set(result.observations[0])


def test_adjusted_close_field_is_never_used():
    prices = [dict(r, adjClose=r["close"] * 3) for r in daily_prices()]
    assert reconstruct(prices=prices).avg_yield_pct == reconstruct().avg_yield_pct


# --- 2/3. end to end through build_entry_row -----------------------------------


def test_price_below_target_is_triggered_and_order_ready():
    row = entry_row(30.0)
    assert row["yield_basis"] == "regular_only_reconstructed"
    assert row["historical_yield_basis"] == "regular_only_reconstructed"
    assert row["yield_observation_count"] == 60
    assert row["target_withheld_reason"] is None
    assert row["avg_5y_yield_pct"] == reconstruct().avg_yield_pct
    assert row["buy_target_price"] is not None and 30.0 <= row["buy_target_price"]
    assert row["signal"] == "TRIGGERED"
    assert row["verdict"] in {"CLEAN-PASS", "CONDITIONAL-PASS"}
    assert row["order_ready"] is True
    assert row["yield_history"]["status"] == "OK"
    assert "observations" not in row["yield_history"]
    assert row["provider_avg_5y_yield_pct"] == 4.0  # provider ratio stays report-only


def test_price_above_target_waits_and_is_not_order_ready():
    row = entry_row(100.0)
    assert row["signal"] == "WAIT"
    assert row["order_ready"] is False


def test_withheld_history_keeps_769_behavior_and_adds_reasons():
    short = reconstruct(prices=daily_prices(start=date(2024, 1, 1)))
    row = entry_row(30.0, history=short)
    assert short.status == "WITHHELD"
    assert row["buy_target_price"] is None
    assert row["target_withheld_reason"] == "regular_only_average_unavailable"
    assert row["yield_basis"] == "unavailable"
    assert row["historical_yield_basis"] == "provider_total_unverified"
    assert row["order_ready"] is False
    assert "yield_history:price_history_shorter_than_5y" in row["notes"]


def test_history_cannot_override_a_non_regular_numerator():
    # Too few regular pays: numerator is not regular-only, so the reconstruction
    # (even a valid OK object) must not unlock a target.
    row = entry_row(
        30.0,
        dividends=quarterly_dividends()[:2],
        history=reconstruct(),
    )
    assert row["target_withheld_reason"] is not None
    assert row["buy_target_price"] is None


# --- 4. ORI-like same-date regular + Special rows -------------------------------


def ori_rows(with_frequency=True):
    special = {"date": "2022-09-15", "dividend": 0.60}
    if with_frequency:
        special["frequency"] = "Special"
    return quarterly_dividends(extra=[special])


def test_same_date_special_is_excluded_via_frequency():
    baseline = reconstruct()
    with_special = reconstruct(dividends=ori_rows())
    assert with_special.status == "OK"
    assert with_special.avg_yield_pct == baseline.avg_yield_pct
    # Rows are not de-duplicated: the special is a separate row on the same date.
    assert sum(1 for r in ori_rows() if r["date"] == "2022-09-15") == 2
    # Without the frequency evidence the same amount would pollute the numerator.
    polluted = reconstruct(dividends=ori_rows(with_frequency=False))
    assert polluted.avg_yield_pct != baseline.avg_yield_pct


def test_frequency_special_maps_to_label_but_irregular_does_not():
    assert apply_frequency_special_label({"frequency": "Special"})["label"] == "special"
    assert apply_frequency_special_label({"frequency": "Irregular"}).get("label") is None
    kept = apply_frequency_special_label({"frequency": "Special", "label": "Cash"})
    assert kept["label"] == "Cash"
    assert apply_frequency_special_label({"frequency": "Special"})["frequency"] == "Special"


def test_client_labels_special_rows_and_keeps_frequency(monkeypatch):
    client = cli.FMPClient(api_key=SECRET, sleep_seconds=0)
    raw = [
        {"date": "2022-08-31", "dividend": 1.0, "frequency": "Special"},
        {"date": "2022-08-31", "dividend": 0.23, "frequency": "Quarterly"},
        {"date": "2023-01-03", "dividend": 0.3, "frequency": "Irregular"},
    ]
    monkeypatch.setattr(client, "_get", lambda *a, **k: [dict(r) for r in raw])
    rows = client.get_stock_dividend("ORI")
    assert len(rows) == 3  # same ex-date rows are both kept
    assert rows[0]["label"] == "special" and rows[0]["frequency"] == "Special"
    assert "label" not in rows[1] and "label" not in rows[2]


# --- 5. combined regular+special labelled Quarterly (SLDE-like) -----------------


def spike_rows():
    rows = quarterly_dividends()
    for row in rows:
        if row["date"] == "2023-12-15":
            row["dividend"] = round(row["dividend"] + 0.10, 4)  # regular + small special
    return rows


def write_history(tmp_path, ticker, dividends, **entry):
    body = {
        "source": "manual",
        "price_basis": "split_adjusted",
        "dividends": dividends,
        "prices": daily_prices(),
        "splits": [],
    }
    body.update(entry)
    path = tmp_path / "history.json"
    path.write_text(json.dumps({ticker: body}))
    return load_yield_history(path)[ticker]


def test_spike_needs_the_kind_override_exact_values(tmp_path):
    baseline = round(expected_average(), 2)
    assert reconstruct().avg_yield_pct == pytest.approx(baseline, abs=0.005)
    # Not an outlier (about 1.2x) and labelled Quarterly: the 0.66 pay is the
    # numerator for Dec 2023 - Feb 2024 until the next raise.
    polluted = reconstruct(dividends=spike_rows())
    pays = [dict(r) for r in spike_rows()]
    assert polluted.avg_yield_pct == pytest.approx(round(expected_average(pays), 2), abs=0.005)
    assert polluted.avg_yield_pct != reconstruct().avg_yield_pct

    rows = spike_rows()
    for row in rows:
        if row["date"] == "2023-12-15":
            row.update(kind="special", kind_source="Issuer press release 2023-11-20")
    loaded = write_history(tmp_path, "SLDE", rows)
    assert [r for r in loaded["dividends"] if r["date"] == "2023-12-15"][0]["label"] == "special"
    result = reconstruct(dividends=loaded["dividends"], prices=loaded["prices"])
    # The whole 2023-12 row is excluded, leaving a hole in the schedule: Jan-Feb 2024
    # look suspended (>136 days since Sep) and Mar-May follow a 182-day gap, so
    # exactly those five observations are invalid.
    skip = {(2024, m) for m in range(1, 6)}
    expected = expected_average(loaded["dividends"], skip=skip)
    assert result.status == "OK" and result.observation_count == 55
    assert result.avg_yield_pct == pytest.approx(round(expected, 2), abs=0.005)


def test_kind_combined_uses_the_regular_amount(tmp_path):
    rows = spike_rows()
    for row in rows:
        if row["date"] == "2023-12-15":
            row.update(
                kind="combined", regular_amount=0.56, kind_source="Issuer release 2023-11-20"
            )
    loaded = write_history(tmp_path, "SLDE", rows)
    fixed = [r for r in loaded["dividends"] if r["date"] == "2023-12-15"][0]
    assert fixed["dividend"] == 0.56 and "label" not in fixed
    result = reconstruct(dividends=loaded["dividends"], prices=loaded["prices"])
    assert result.observation_count == 60
    assert result.avg_yield_pct == pytest.approx(round(expected_average(), 2), abs=0.005)
    assert result.avg_yield_pct == reconstruct().avg_yield_pct


def test_kind_combined_scales_adj_dividend(tmp_path):
    rows = [dict(r, adjDividend=r["dividend"]) for r in quarterly_dividends()]
    for row in rows:
        if row["date"] == "2023-12-15":
            row.update(
                dividend=1.12,
                adjDividend=1.12,
                kind="combined",
                regular_amount=0.56,
                kind_source="Issuer release",
            )
    loaded = write_history(tmp_path, "SLDE", rows)
    fixed = [r for r in loaded["dividends"] if r["date"] == "2023-12-15"][0]
    assert fixed["dividend"] == 0.56
    assert fixed["adjDividend"] == pytest.approx(0.56)


def test_kind_exclude_drops_the_row(tmp_path):
    rows = quarterly_dividends(extra=[{"date": "2023-06-25", "dividend": 0.17}])
    rows[-1].update(kind="exclude", kind_source="Prorated stub per 8-K")
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps(
            {
                "AES": {
                    "source": "manual",
                    "price_basis": "split_adjusted",
                    "dividends": rows,
                    "prices": daily_prices(),
                    "splits": [],
                }
            }
        )
    )
    loaded = load_yield_history(path)["AES"]
    assert all(r["date"] != "2023-06-25" for r in loaded["dividends"])
    assert reconstruct(dividends=loaded["dividends"]).avg_yield_pct == reconstruct().avg_yield_pct


# --- 6. AES-like stub inside a quarterly stream --------------------------------


def test_prorated_stub_observations_are_invalid():
    stub = {"date": "2023-06-25", "dividend": 0.17, "frequency": "Monthly"}
    result = reconstruct(dividends=quarterly_dividends(extra=[stub]))
    dates = {o["date"] for o in result.observations}
    for missing in ("2023-06-30", "2023-07-31", "2023-08-31"):
        assert missing not in dates
    assert result.observation_count == 57
    assert any(r.startswith("invalid_observation:") for r in result.reasons)
    assert "2023-09-29" in dates  # the next full regular pay is valid again
    assert result.status == "OK"  # 57/60 = 0.95 >= 0.9
    assert result.coverage_ratio == pytest.approx(0.95)


def test_frequency_disagreeing_with_cadence_is_invalid():
    rows = quarterly_dividends()
    for row in rows:
        if row["date"] == "2024-03-15":
            row["frequency"] = "Annual"
    result = reconstruct(dividends=rows)
    assert "invalid_observation:frequency_mismatch" in result.reasons
    assert "2024-03-28" not in {o["date"] for o in result.observations}


# --- 7. SLG-like monthly -> quarterly switch ------------------------------------


def switch_rows():
    rows = []
    day = date(2020, 1, 25)
    while day <= date(2023, 6, 25):
        rows.append({"date": day.isoformat(), "dividend": 0.30, "frequency": "Monthly"})
        day = date(day.year + (day.month == 12), day.month % 12 + 1, 25)
    day = date(2023, 9, 25)
    while day <= date(2026, 9, 25):
        rows.append({"date": day.isoformat(), "dividend": 0.90, "frequency": "Quarterly"})
        month = day.month + 3
        day = date(day.year + (month > 12), (month - 1) % 12 + 1, 25)
    return rows


def test_frequency_switch_is_withheld_for_low_coverage():
    result = reconstruct(dividends=switch_rows())
    assert result.status == "WITHHELD"
    assert result.avg_yield_pct is None
    assert result.observation_count < 54
    assert "coverage_below_threshold" in result.reasons
    assert any(r.startswith("invalid_observation:") for r in result.reasons)


# --- 8. short histories ---------------------------------------------------------


def test_short_price_history_is_withheld():
    result = reconstruct(prices=daily_prices(start=date(2024, 1, 2)))
    assert result.status == "WITHHELD" and result.avg_yield_pct is None
    assert "price_history_shorter_than_5y" in result.reasons


def test_short_dividend_history_is_withheld():
    rows = [r for r in quarterly_dividends() if r["date"] >= "2023-01-01"]
    result = reconstruct(dividends=rows)
    assert result.status == "WITHHELD" and result.avg_yield_pct is None
    assert "dividend_history_shorter_than_5y" in result.reasons


def test_both_histories_short_report_both_reasons():
    rows = [r for r in quarterly_dividends() if r["date"] >= "2023-01-01"]
    result = reconstruct(dividends=rows, prices=daily_prices(start=date(2024, 1, 2)))
    assert {"price_history_shorter_than_5y", "dividend_history_shorter_than_5y"} <= set(
        result.reasons
    )


# --- 9. split basis -------------------------------------------------------------

SPLIT = [{"date": "2023-06-01", "numerator": 2, "denominator": 1}]


def test_split_in_window_without_adj_dividend_is_unverified():
    result = reconstruct(splits=SPLIT)
    assert result.status == "WITHHELD" and result.avg_yield_pct is None
    assert "split_basis_unverified" in result.reasons


def test_split_in_window_with_adj_dividend_is_accepted_and_used():
    rows = quarterly_dividends(adj=True)
    for row in rows:
        if row["date"] < "2023-06-01":
            row["adjDividend"] = round(row["dividend"] / 2, 4)
    result = reconstruct(dividends=rows, splits=SPLIT)
    assert "split_basis_unverified" not in result.reasons
    # adjusted amounts replace the raw amount in the numerator
    assert result.observations[0]["regular_annualized"] == pytest.approx(
        round(0.52 / 2, 4) * 4, abs=0.001
    )


def test_split_outside_window_does_not_matter():
    assert reconstruct(splits=[{"date": "2019-01-01"}]).status == "OK"


# --- 10. --yield-history-json validation ----------------------------------------


def good_entry(**updates):
    entry = {
        "source": "Verified data pack",
        "price_basis": "split_adjusted",
        "splits": [],
        "dividends": [{"date": "2025-03-15", "dividend": 0.5}],
        "prices": [{"date": "2025-03-14", "close": 40.0}],
    }
    entry.update(updates)
    return {"NNN": entry}


def test_loader_accepts_valid_file(tmp_path):
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(good_entry()))
    loaded = load_yield_history(path)
    assert loaded["NNN"]["source"] == "Verified data pack"
    assert loaded["NNN"]["splits"] == []


BAD_PAYLOADS = {
    "not_json": "{",
    "not_object": "[]",
    "missing_source": json.dumps(good_entry(source=None)),
    "empty_source": json.dumps(good_entry(source="  ")),
    "zero_close": json.dumps(good_entry(prices=[{"date": "2025-03-14", "close": 0}])),
    "negative_close": json.dumps(good_entry(prices=[{"date": "2025-03-14", "close": -1}])),
    "nan_close": json.dumps(good_entry(prices=[{"date": "2025-03-14", "close": float("nan")}])),
    "string_close": json.dumps(good_entry(prices=[{"date": "2025-03-14", "close": "40"}])),
    "bad_price_date": json.dumps(good_entry(prices=[{"date": "03/14/2025", "close": 40}])),
    "bad_dividend_date": json.dumps(good_entry(dividends=[{"date": "x", "dividend": 0.5}])),
    "kind_without_source": json.dumps(
        good_entry(dividends=[{"date": "2025-03-15", "dividend": 0.5, "kind": "special"}])
    ),
    "kind_blank_source": json.dumps(
        good_entry(
            dividends=[
                {"date": "2025-03-15", "dividend": 0.5, "kind": "exclude", "kind_source": " "}
            ]
        )
    ),
    "kind_unknown": json.dumps(
        good_entry(
            dividends=[{"date": "2025-03-15", "dividend": 0.5, "kind": "x", "kind_source": "y"}]
        )
    ),
    "bare_average": json.dumps({"NNN": 3.5}),
}


@pytest.mark.parametrize("name", sorted(BAD_PAYLOADS))
def test_loader_rejects_invalid_input(tmp_path, name):
    path = tmp_path / "bad.json"
    path.write_text(BAD_PAYLOADS[name])
    with pytest.raises(YieldHistoryInputError, match="Invalid --yield-history-json"):
        load_yield_history(path)


@pytest.mark.parametrize("name", ["not_json", "zero_close", "kind_without_source", "bare_average"])
def test_cli_rejects_invalid_history_with_exit_2_before_provider(
    tmp_path, monkeypatch, capsys, name
):
    path = tmp_path / "bad.json"
    path.write_text(BAD_PAYLOADS[name])
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_entry_signals.py", "--tickers", "NNN", "--yield-history-json", str(path)],
    )
    monkeypatch.setattr(
        cli, "FMPClient", lambda **kw: pytest.fail("Provider must not be initialized")
    )
    assert cli.main() == 2
    assert "Invalid --yield-history-json" in capsys.readouterr().err


# --- 11. main() path with a fake client ------------------------------------------


class FakeClient:
    instances = []

    def __init__(self, **kw):
        self.calls = []
        self.api_calls = 0
        FakeClient.instances.append(self)

    def get_batch_quotes(self, tickers):
        return {t: {"price": 30.0, "date": AS_OF} for t in tickers}

    def get_batch_profiles(self, tickers):
        return {t: {"sector": "Consumer Defensive"} for t in tickers}

    def get_ratios(self, *a, **kw):
        return [{"dividendYield": 0.04}] * 5

    def get_stock_dividend(self, ticker):
        self.calls.append(("dividends", ticker))
        return quarterly_dividends()

    def get_price_history(self, ticker, start, end):
        self.calls.append(("prices", ticker, start, end))
        return daily_prices()

    def get_splits(self, ticker):
        self.calls.append(("splits", ticker))
        return []

    def get_financials(self, *a, **kw):
        return dict(FINANCIALS)


def run_main(monkeypatch, tmp_path, *extra):
    FakeClient.instances.clear()
    monkeypatch.setattr(cli, "FMPClient", FakeClient)
    monkeypatch.setenv("FMP_API_KEY", "fictional-test-key")
    argv = [
        "build_entry_signals.py",
        "--tickers",
        "NNN",
        "--as-of",
        AS_OF,
        "--yield-floor",
        "2",
        "--output-dir",
        str(tmp_path),
        *extra,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert cli.main() == 0
    out = json.loads((tmp_path / f"kanchi_entry_signals_{AS_OF}.json").read_text())
    return out["rows"][0], FakeClient.instances[0]


def test_main_feeds_fetched_prices_and_splits_to_the_row(monkeypatch, tmp_path):
    row, client = run_main(monkeypatch, tmp_path)
    assert ("splits", "NNN") in client.calls
    price_call = next(c for c in client.calls if c[0] == "prices")
    assert price_call[2] == "2021-10-06" and price_call[3] == AS_OF  # 5y + 45 days back
    assert row["yield_basis"] == "regular_only_reconstructed"
    assert row["yield_history"]["status"] == "OK"
    assert row["yield_history"]["source"] == "fmp_stable_dividends_and_eod_prices"
    assert row["avg_5y_yield_pct"] == reconstruct().avg_yield_pct
    with (tmp_path / f"kanchi_entry_signals_{AS_OF}.csv").open() as stream:
        csv_row = next(csv.DictReader(stream))
    assert csv_row["yield_history_status"] == "OK"
    assert csv_row["yield_window_start"] == "2021-11-01"
    assert csv_row["yield_window_end"] == "2026-10-31"
    assert csv_row["yield_coverage_ratio"] == "1.0"
    assert csv_row["yield_method"] == "month_end_60_regular_only_v1"
    assert "observations" not in csv_row
    markdown = (tmp_path / f"kanchi_entry_signals_{AS_OF}.md").read_text()
    assert "regular_only_reconstructed" in markdown
    assert "2021-11-01" in markdown and "60/60" in markdown


def test_main_supplied_history_replaces_fetched_rows(monkeypatch, tmp_path):
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps(
            {
                "nnn": {
                    "source": "Verified data pack 2026-11",
                    "dividends": quarterly_dividends(),
                    "price_basis": "split_adjusted",
                    "prices": daily_prices(),
                    "splits": [],
                }
            }
        )
    )
    row, client = run_main(monkeypatch, tmp_path, "--yield-history-json", str(path))
    assert [c[0] for c in client.calls] == []  # nothing fetched for NNN
    assert row["yield_history"]["source"] == "Verified data pack 2026-11"
    assert row["yield_history"]["status"] == "OK"


def test_main_invalid_as_of_exits_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        sys, "argv", ["build_entry_signals.py", "--tickers", "NNN", "--as-of", "nope"]
    )
    monkeypatch.setattr(cli, "FMPClient", lambda **kw: pytest.fail("no provider"))
    assert cli.main() == 2


# --- client fetch helpers ---------------------------------------------------------


def test_fetch_helpers_fail_soft(monkeypatch):
    client = cli.FMPClient(api_key=SECRET, sleep_seconds=0)
    monkeypatch.setattr(client, "_request", lambda *a, **k: None)
    assert client.get_price_history("NNN", "2021-10-06", AS_OF) == []
    assert client.get_splits("NNN") is None
    monkeypatch.setattr(client, "_request", lambda *a, **k: [])
    assert client.get_splits("NNN") == []

    def boom(*a, **k):
        raise RuntimeError("transport exploded")

    monkeypatch.setattr(client, "_request", boom)
    assert client.get_price_history("NNN", "2021-10-06", AS_OF) == []
    assert client.get_splits("NNN") is None


def test_fetch_helpers_use_stable_endpoints(monkeypatch):
    client = cli.FMPClient(api_key=SECRET, sleep_seconds=0)
    seen = []
    monkeypatch.setattr(client, "_request", lambda url, params, **k: seen.append((url, params)))
    client.get_price_history("NNN", "2021-10-06", AS_OF)
    client.get_splits("NNN")
    assert seen[0][0].endswith("/stable/historical-price-eod/full")
    assert seen[0][1] == {"symbol": "NNN", "from": "2021-10-06", "to": AS_OF}
    assert seen[1][0].endswith("/stable/splits")


# --- 12. secrets never reach the output ---------------------------------------------


def test_api_key_never_printed_when_price_fetch_fails(monkeypatch, tmp_path, capsys):
    def failing_get(self, url, params=None, timeout=None, **kw):
        raise requests.exceptions.ConnectionError(f"boom {url}?apikey={SECRET}&symbol=NNN")

    monkeypatch.setattr(requests.Session, "get", failing_get)
    monkeypatch.setenv("FMP_API_KEY", SECRET)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_entry_signals.py",
            "--tickers",
            "NNN",
            "--as-of",
            AS_OF,
            "--sleep-seconds",
            "0",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert cli.main() == 0
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    for path in tmp_path.iterdir():
        assert SECRET not in path.read_text()
    row = json.loads((tmp_path / f"kanchi_entry_signals_{AS_OF}.json").read_text())["rows"][0]
    assert row["buy_target_price"] is None  # no prices -> nothing is actionable
    assert row["order_ready"] is False


def test_module_constants_come_from_thresholds():
    assert ryh.REGULAR_YIELD_MIN_COVERAGE == 0.9
    assert ryh.REGULAR_YIELD_OBSERVATIONS == 60
    assert ryh.REGULAR_YIELD_YEARS == 5
    assert ryh.REGULAR_YIELD_GAP_TOLERANCE == (0.5, 1.5)


# --- review fixes: B1 / S1 / S2 / S3 / S4 / S5 and loader nits --------------------


def flat_rows(amount=0.5):
    rows = []
    for year in range(2019, 2027):
        for month in (3, 6, 9, 12):
            day = date(year, month, 15)
            if day <= date(2026, 9, 15):
                rows.append({"date": day.isoformat(), "dividend": amount, "frequency": "Quarterly"})
    return rows


def test_irregular_latest_row_cannot_unlock_a_target():
    rows = flat_rows()
    rows[-1].update(dividend=0.7, frequency="Irregular")
    history = reconstruct(dividends=rows)
    row = entry_row(30.0, history=history, dividends=rows)
    assert row["target_withheld_reason"] == "latest_dividend_unconfirmed"
    assert "latest_dividend_unconfirmed" in row["pre_order_blockers"]
    assert row["buy_target_price"] is None
    assert row["order_ready"] is False
    # The last window observations used the Irregular row as numerator: invalid.
    assert "invalid_observation:irregular_frequency_row" in history.reasons
    assert "2026-09-30" not in {o["date"] for o in history.observations}


def test_pending_outlier_latest_row_cannot_unlock_a_target():
    rows = flat_rows()
    rows[-1]["dividend"] = 0.8  # 1.6x the trailing median, nothing after it to confirm
    history = reconstruct(dividends=rows)
    assert "invalid_observation:latest_dividend_unconfirmed" in history.reasons
    row = entry_row(30.0, history=history, dividends=rows)
    assert row["target_withheld_reason"] == "latest_dividend_unconfirmed"
    assert row["order_ready"] is False
    assert row["signal"] == "ASSUMPTION-REQUIRED"


def test_ordinary_raise_is_not_flagged_as_pending():
    rows = flat_rows()
    for row in rows:
        if row["date"] >= "2026-06-15":
            row["dividend"] = 0.52  # a normal 4% raise
    assert not ryh.latest_dividend_unconfirmed(rows, AS_OF)
    assert not ryh.latest_dividend_unconfirmed(flat_rows(), AS_OF)


def test_mid_window_unlabelled_special_is_classified_on_the_full_history():
    rows = flat_rows()
    for row in rows:
        if row["date"] == "2024-06-15":
            row["dividend"] = 1.0  # 2x, labelled Quarterly; reverts afterwards
    result = reconstruct(dividends=rows)
    assert result.status == "OK"
    assert max(o["regular_annualized"] for o in result.observations) == pytest.approx(2.0)
    assert result.avg_yield_pct == reconstruct(dividends=flat_rows()).avg_yield_pct


def test_dividend_basis_exposes_special_rows_additively():
    from dividend_basis import analyze_dividends

    rows = flat_rows()
    rows[-3]["dividend"] = 1.0
    basis = analyze_dividends(rows, 40.0, as_of_date=AS_OF)
    assert basis.special_rows == [(rows[-3]["date"], 1.0)]
    assert basis.latest_declared_annualized == 2.0


def test_splits_unknown_requires_adj_dividend_on_every_row():
    result = reconstruct(splits=None)
    assert result.status == "WITHHELD" and "split_basis_unverified" in result.reasons
    adjusted = reconstruct(dividends=quarterly_dividends(adj=True), splits=None)
    assert adjusted.status == "OK"


def test_split_after_the_window_still_requires_adj_dividend():
    after_window = [{"date": "2026-11-05", "numerator": 2, "denominator": 1}]
    assert "split_basis_unverified" in reconstruct(splits=after_window).reasons
    after_as_of = [{"date": "2027-01-05"}]
    assert "split_basis_unverified" in reconstruct(splits=after_as_of).reasons
    ok = reconstruct(dividends=quarterly_dividends(adj=True), splits=after_window)
    assert ok.status == "OK"


def test_suspension_inside_the_window_invalidates_stale_observations():
    rows = [r for r in flat_rows() if not ("2023-03-01" <= r["date"] <= "2024-03-31")]
    result = reconstruct(dividends=rows)
    dates = {o["date"] for o in result.observations}
    assert "invalid_observation:suspension_at_observation" in result.reasons
    assert not any("2023-08-01" <= d <= "2024-03-10" for d in dates)
    assert result.status == "WITHHELD" and "coverage_below_threshold" in result.reasons


def test_cut_inside_the_window_is_recorded_but_keeps_declared_rate():
    rows = flat_rows()
    for row in rows:
        if row["date"] >= "2024-06-15":
            row["dividend"] = 0.4
    result = reconstruct(dividends=rows)
    assert "cut_in_window" in result.reasons
    assert result.status == "OK"
    after = [o for o in result.observations if o["date"] > "2024-07-01"]
    assert after and all(o["regular_annualized"] == pytest.approx(1.6) for o in after)


def test_observation_price_must_be_in_the_last_week_of_the_month():
    prices = [p for p in daily_prices() if not ("2023-05-20" <= p["date"] <= "2023-05-31")]
    result = reconstruct(prices=prices)
    assert "2023-05-19" not in {o["date"] for o in result.observations}
    assert result.observation_count == 59


def test_prices_ending_before_the_window_end_are_withheld():
    prices = [p for p in daily_prices() if p["date"] < "2026-10-01"]
    result = reconstruct(prices=prices)
    assert result.status == "WITHHELD"
    assert "price_history_ends_before_window_end" in result.reasons


def raw_history(tmp_path, text):
    path = tmp_path / "raw.json"
    path.write_text(text)
    return path


def test_loader_requires_price_basis_and_splits(tmp_path):
    for field_name in ("price_basis", "splits"):
        payload = good_entry()
        del payload["NNN"][field_name]
        path = raw_history(tmp_path, json.dumps(payload))
        with pytest.raises(YieldHistoryInputError, match=field_name):
            load_yield_history(path)
    payload = good_entry(price_basis="adjusted")
    with pytest.raises(YieldHistoryInputError, match="price_basis"):
        load_yield_history(raw_history(tmp_path, json.dumps(payload)))


def test_loader_rejects_special_row_without_kind(tmp_path):
    for extra in ({"frequency": "Special"}, {"label": "Special cash"}):
        row = {"date": "2025-03-15", "dividend": 0.5, **extra}
        payload = good_entry(dividends=[row])
        with pytest.raises(YieldHistoryInputError, match="kind"):
            load_yield_history(raw_history(tmp_path, json.dumps(payload)))


def test_loader_rejects_bad_combined_amounts(tmp_path):
    for regular in (None, 0, 0.5, 0.9):
        row = {
            "date": "2025-03-15",
            "dividend": 0.5,
            "kind": "combined",
            "kind_source": "release",
            "regular_amount": regular,
        }
        with pytest.raises(YieldHistoryInputError, match="regular_amount"):
            load_yield_history(raw_history(tmp_path, json.dumps(good_entry(dividends=[row]))))


def test_loader_normalizes_dates_and_rejects_duplicate_keys(tmp_path):
    row = {"date": "2025-03-15T00:00:00", "dividend": 0.5}
    loaded = load_yield_history(raw_history(tmp_path, json.dumps(good_entry(dividends=[row]))))
    assert loaded["NNN"]["dividends"][0]["date"] == "2025-03-15"
    dup = '{"NNN": {"source": "a", "source": "b"}}'
    with pytest.raises(YieldHistoryInputError, match="duplicate"):
        load_yield_history(raw_history(tmp_path, dup))


def test_cli_warns_for_tickers_not_in_the_run(monkeypatch, tmp_path, capsys):
    path = tmp_path / "history.json"
    payload = good_entry()
    payload["ZZZ"] = payload["NNN"]
    path.write_text(json.dumps(payload))
    run_main(monkeypatch, tmp_path, "--yield-history-json", str(path))
    assert "ZZZ" in capsys.readouterr().err


# --- raise confirmation by repeat (re-review) -------------------------------------


def monthly_rows(amount=0.10):
    rows = []
    year, month = 2019, 1
    while date(year, month, 25) <= date(2026, 10, 25):
        rows.append(
            {"date": date(year, month, 25).isoformat(), "dividend": amount, "frequency": "Monthly"}
        )
        year, month = year + (month == 12), month % 12 + 1
    return rows


def test_combined_row_at_1_4x_labelled_quarterly_is_withheld_end_to_end():
    rows = flat_rows()
    rows[-1]["dividend"] = 0.7  # regular + special, labelled Quarterly, 1.4x
    history = reconstruct(dividends=rows)
    assert "invalid_observation:latest_dividend_unconfirmed" in history.reasons
    row = entry_row(30.0, history=history, dividends=rows)
    assert row["target_withheld_reason"] == "latest_dividend_unconfirmed"
    assert row["buy_target_price"] is None
    assert row["order_ready"] is False


def test_quarterly_raise_is_confirmed_at_the_second_raised_pay():
    rows = flat_rows()
    for row in rows:
        if row["date"] >= "2026-06-15":
            row["dividend"] = 0.8
    first = [r for r in rows if r["date"] <= "2026-06-15"]
    assert ryh.latest_dividend_unconfirmed(first, AS_OF) is True
    assert ryh.latest_dividend_unconfirmed(rows, AS_OF) is False
    # In the reconstruction both raised pays are confirmed by the repeat.
    result = reconstruct(dividends=rows)
    assert "invalid_observation:latest_dividend_unconfirmed" not in result.reasons
    assert entry_row(30.0, history=result, dividends=rows)["target_withheld_reason"] is None


def test_monthly_raise_is_confirmed_at_the_second_raised_month():
    rows = monthly_rows()
    for row in rows:
        if row["date"] >= "2026-09-25":
            row["dividend"] = 0.16
    first = [r for r in rows if r["date"] <= "2026-09-25"]
    assert ryh.latest_dividend_unconfirmed(first, AS_OF) is True
    assert ryh.latest_dividend_unconfirmed(rows, AS_OF) is False


def test_ten_percent_raise_is_never_withheld():
    for build, boundary in ((flat_rows, "2026-09-15"), (monthly_rows, "2026-10-25")):
        rows = build()
        base = rows[0]["dividend"]
        for row in rows:
            if row["date"] >= boundary:
                row["dividend"] = round(base * 1.10, 4)
        assert ryh.latest_dividend_unconfirmed(rows, AS_OF) is False


def test_combined_on_a_special_row_keeps_the_regular_part(tmp_path):
    rows = quarterly_dividends()
    for row in rows:
        if row["date"] == "2023-12-15":
            row.update(
                dividend=1.5,
                frequency="Special",
                kind="combined",
                regular_amount=0.56,
                kind_source="Issuer release 2023-11-20",
            )
    loaded = write_history(tmp_path, "SLDE", rows)
    fixed = [r for r in loaded["dividends"] if r["date"] == "2023-12-15"][0]
    assert fixed["dividend"] == 0.56 and fixed["frequency"] is None
    assert "label" not in fixed
    result = reconstruct(dividends=loaded["dividends"], prices=loaded["prices"])
    assert result.observation_count == 60
    january = [o for o in result.observations if o["date"].startswith("2024-01")][0]
    assert january["regular_annualized"] == pytest.approx(2.24)
