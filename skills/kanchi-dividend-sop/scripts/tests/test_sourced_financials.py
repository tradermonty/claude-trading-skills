"""Issue #772: sourced metrics and aggregate readiness, entirely offline."""

import csv
import json
import sys
from datetime import date, timedelta

import build_entry_signals as cli
import pytest
from event_scanner import CLEAN_CONFIRMED, ScanResult
from sourced_financials import RULES, FinancialsInputError, load_financials, merge_financials

AS_OF = "2026-05-17"


def metric(value=6.0, unit="USD/share", **updates):
    return dict(
        value=value,
        unit=unit,
        source="Fictional issuer",
        as_of=AS_OF,
        document_ref="Fictional annual report p. 10",
        **updates,
    )


def load(tmp_path, fields):
    path = tmp_path / "financials.json"
    path.write_text(json.dumps({"schema_version": 1, "tickers": {"PG": fields}}))
    return load_financials(path, AS_OF)["PG"]


def history():
    return [
        {
            "date": (date(2023, 1, 1) + timedelta(days=91 * i)).isoformat(),
            "dividend": 0.40 + 0.01 * (i // 4),
            "label": "cash",
        }
        for i in range(14)
    ]


def row(financials, **updates):
    args = dict(
        ticker="PG",
        alpha_pp=0.5,
        quote={"price": 20, "date": AS_OF},
        profile={"sector": "Consumer Defensive"},
        key_metrics=[{"dividendYield": 0.04}] * 5,
        dividend_history=history(),
        floor_pct=3.0,
        financials=financials,
        event_scan=ScanResult(ticker="PG", result=CLEAN_CONFIRMED),
        as_of=AS_OF,
    )
    args.update(updates)
    return cli.build_entry_row(**args)


def base():
    return {
        "sector": "Consumer Defensive",
        "gaap_eps": 6.0,
        "fcf_per_share": 7.0,
        "adjusted_eps": None,
        "adjusted_eps_source": "UNAVAILABLE",
    }


def test_sourced_eps_changes_safety_with_provenance(tmp_path):
    assert row(base())["payout_safety"]["safety_verdict"] == "HOLD-REVIEW"
    supplied = load(tmp_path, {"adjusted_eps": metric()})
    result = row(merge_financials(base(), supplied))
    assert result["payout_safety"]["safety_verdict"] == "PASS"
    assert result["order_ready"] is False  # Existing entry-basis gate remains closed.
    assert "regular_only_average_unavailable" in result["pre_order_blockers"]
    assert result["event_t1_blocked"] is False
    assert result["provenance"]["payout_source"] == "MANUAL"
    assert result["provenance"]["manual_financials"]["adjusted_eps"] == dict(
        metric(), input_method="MANUAL"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("value", True),
        ("value", None),
        ("value", "6"),
        ("value", 0),
        ("value", -1),
        ("value", float("nan")),
        ("value", float("inf")),
        ("value", 10**400),
        ("unit", "EUR/share"),
        ("unit", "percent"),
        ("source", " "),
        ("document_ref", ""),
        ("as_of", "2026-05-18"),
        ("as_of", "2026-02-30"),
        ("as_of", "20260517"),
        ("as_of", None),
    ],
)
def test_invalid_manual_input_cannot_become_ready(tmp_path, field, value):
    record = metric()
    record[field] = value
    supplied = load(tmp_path, {"adjusted_eps": record})
    existing = dict(base(), adjusted_eps=6, adjusted_eps_source="FMP")
    result = row(merge_financials(existing, supplied))
    assert result["payout_safety"]["safety_verdict"] == "HOLD-REVIEW"
    assert result["verdict"] == "HOLD-REVIEW"
    assert result["order_ready"] is False
    assert result["provenance"]["manual_financials_errors"]
    assert any(b.startswith("manual_financials:") for b in result["pre_order_blockers"])


def test_invalid_input_preserves_hard_fail(tmp_path):
    supplied = load(tmp_path, {"adjusted_eps": metric(-1)})
    result = row(
        merge_financials(dict(base(), adjusted_eps=1, adjusted_eps_source="FMP"), supplied)
    )
    assert result["payout_safety"]["safety_verdict"] == "FAIL"
    assert result["verdict"] == "FAIL"
    assert not result["order_ready"]


@pytest.mark.parametrize("key,rule", list(RULES.items()))
def test_every_supported_metric_has_validated_provenance(tmp_path, key, rule):
    unit, _, _, choices = rule
    record = metric(sorted(choices)[0] if choices else 0.2, unit)
    fields = {key: record} if "." not in key else {key.split(".")[0]: {key.split(".")[1]: record}}
    supplied = load(tmp_path, fields)
    assert not supplied["errors"]
    assert supplied["provenance"][key]["input_method"] == "MANUAL"
    merged = merge_financials(base(), supplied)
    if "." in key:
        group, name = key.split(".")
        assert merged[group][name] == record["value"]


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"unknown": metric()},
        {"utility_metrics": {}},
        {"bank_metrics": {"cet1": metric(12, "fraction")}},
        {"bank_metrics": {"cre_concentration": metric("typo", "category")}},
    ],
)
def test_invalid_ticker_fields_hold(tmp_path, fields):
    supplied = load(tmp_path, fields)
    assert supplied["errors"]
    assert (
        row(merge_financials(base(), supplied))["payout_safety"]["safety_verdict"] == "HOLD-REVIEW"
    )


@pytest.mark.parametrize("key", ["ffo_to_debt", "combined_ratio", "deposit_beta"])
def test_fraction_can_exceed_one(tmp_path, key):
    group = {
        "ffo_to_debt": "utility_metrics",
        "combined_ratio": "insurer_metrics",
        "deposit_beta": "bank_metrics",
    }[key]
    supplied = load(tmp_path, {group: {key: metric(1.2, "fraction")}})
    assert not supplied["errors"]
    assert supplied["values"][f"{group}.{key}"] == 1.2


def test_duke_like_open_blocker_is_not_ready():
    result = row(dict(base(), sector="Utilities"), profile={"sector": "Utilities"})
    assert "utility_ffo_debt_unavailable" in result["pre_order_blockers"]
    assert result["event_t1_blocked"] is False
    assert result["order_ready"] is False


@pytest.mark.parametrize(
    "updates", [{"floor_pct": None}, {"quote": {"price": 200, "date": AS_OF}}, {"event_scan": None}]
)
def test_non_actionable_rows_not_ready(updates):
    result = row(dict(base(), adjusted_eps=6, adjusted_eps_source="MANUAL"), **updates)
    assert not result["order_ready"]


@pytest.mark.parametrize(
    "text",
    [
        '{"schema_version":1,"tickers":{"PG":{},"PG":{}}}',
        '{"schema_version":1,"tickers":{"PG":{"adjusted_eps":1,"adjusted_eps":2}}}',
        '{"schema_version":1,"tickers":{"PG":{"adjusted_eps":{"value":1,"value":2}}}}',
        '{"schema_version":1,"tickers":{"PG":{},"pg":{}}}',
        '{"schema_version":true,"tickers":{}}',
        "[]",
        "{",
    ],
)
def test_structural_errors_rejected(tmp_path, text):
    path = tmp_path / "invalid.json"
    path.write_text(text)
    with pytest.raises(FinancialsInputError, match="Invalid --financials-json"):
        load_financials(path, AS_OF)


def test_cli_malformed_input_before_provider(tmp_path, monkeypatch, capsys):
    path = tmp_path / "invalid.json"
    path.write_text("[]")
    monkeypatch.setattr(
        sys, "argv", ["build_entry_signals.py", "--tickers", "PG", "--financials-json", str(path)]
    )
    monkeypatch.setattr(
        cli, "FMPClient", lambda **kw: pytest.fail("Provider must not be initialized")
    )
    assert cli.main() == 2
    assert "Invalid --financials-json" in capsys.readouterr().err


def test_cli_end_to_end_offline(tmp_path, monkeypatch):
    class FakeClient:
        api_calls = 0

        def __init__(self, **kw):
            pass

        def get_batch_quotes(self, tickers):
            return {"PG": {"price": 20, "date": AS_OF}}

        def get_batch_profiles(self, tickers):
            return {"PG": {"sector": "Consumer Defensive"}}

        def get_ratios(self, *a, **kw):
            return [{"dividendYield": 0.04}] * 5

        def get_stock_dividend(self, ticker):
            return history()

        def get_price_history(self, *a, **kw):
            return []  # #834: main() now requests prices; none -> average withheld.

        def get_splits(self, *a, **kw):
            return []

        def get_financials(self, *a, **kw):
            return base()

    inputs = tmp_path / "manual.json"
    inputs.write_text(
        json.dumps({"schema_version": 1, "tickers": {"PG": {"adjusted_eps": metric()}}})
    )
    monkeypatch.setattr(cli, "FMPClient", FakeClient)
    monkeypatch.setenv("FMP_API_KEY", "fictional-test-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_entry_signals.py",
            "--tickers",
            "PG",
            "--as-of",
            AS_OF,
            "--yield-floor",
            "3",
            "--financials-json",
            str(inputs),
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert cli.main() == 0
    result = json.loads((tmp_path / f"kanchi_entry_signals_{AS_OF}.json").read_text())["rows"][0]
    assert result["payout_safety"]["adjusted_eps_source"] == "MANUAL"
    assert not result["order_ready"]  # event scan skipped remains blocked.
    with (tmp_path / f"kanchi_entry_signals_{AS_OF}.csv").open() as stream:
        csv_row = next(csv.DictReader(stream))
    assert csv_row["order_ready"] == "False"
    assert "Order Ready" in (tmp_path / f"kanchi_entry_signals_{AS_OF}.md").read_text()


@pytest.mark.parametrize(
    "posture,signal,t1,blockers,expected",
    [
        ("CLEAN-PASS", "TRIGGERED", False, [], True),
        ("CONDITIONAL-PASS", "TRIGGERED", False, [], True),
        ("PASS-CAUTION", "TRIGGERED", False, ["utility_ffo_debt_unavailable"], False),
        ("CLEAN-PASS", "TRIGGERED", False, ["unresolved"], False),
        ("CLEAN-PASS", "WAIT", False, [], False),
        ("CLEAN-PASS", "ASSUMPTION-REQUIRED", False, [], False),
        ("STEP1-RECHECK", "TRIGGERED", False, [], False),
        ("HOLD-REVIEW", "TRIGGERED", True, [], False),
        ("CLEAN-PASS", "TRIGGERED", True, [], False),
    ],
)
def test_aggregate_gate_contract(posture, signal, t1, blockers, expected):
    # Include the legacy false-T1/open-FFO-blocker combination independently
    # from today's additional regular-yield-basis restriction.
    assert (
        cli.order_ready(dict(verdict=posture, signal=signal, t1_blocked=t1), blockers) is expected
    )


@pytest.mark.parametrize("dotted_first", [True, False])
def test_dotted_alias_cannot_hide_invalid_nested_metric(tmp_path, dotted_first):
    fields = {
        "utility_metrics": {"ffo_to_debt": metric(-1, "fraction")},
        "utility_metrics.ffo_to_debt": metric(0.18, "fraction"),
    }
    if dotted_first:
        fields = dict(reversed(list(fields.items())))
    supplied = load(tmp_path, fields)
    assert len(supplied["errors"]) == 2
    assert supplied["values"] == {}
    result = row(merge_financials(dict(base(), sector="Utilities"), supplied))
    assert result["payout_safety"]["safety_verdict"] == "HOLD-REVIEW"
    assert not result["order_ready"]


@pytest.mark.parametrize("eps", [5e-324, 1e-307, 1e-306])
def test_extreme_finite_eps_fails_safe_without_nonfinite_outputs(tmp_path, eps):
    supplied = load(tmp_path, {"adjusted_eps": metric(eps)})
    result = row(merge_financials(base(), supplied))
    assert result["payout_safety"]["safety_verdict"] == "HOLD-REVIEW"
    assert "gaap_adjusted_divergence_non_finite" in result["pre_order_blockers"]
    assert not result["order_ready"]
    json.dumps(result, allow_nan=False)
