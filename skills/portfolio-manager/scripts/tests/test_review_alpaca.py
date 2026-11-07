"""Saved broker positions share the limited allocation contract with CSV."""

import copy
import io
import json
import socket
from pathlib import Path

import jsonschema
import pytest
from review_csv import CsvError, build_alpaca_report, build_report, main, render_markdown

ASSETS = Path(__file__).resolve().parents[2] / "assets"
STAMP = "2026-10-20T12:00:00Z"
POSITIONS = [
    {
        "symbol": "FICTA",
        "asset_class": "us_equity",
        "qty": "2.5",
        "side": "long",
        "current_price": "20",
        "avg_entry_price": "15",
        "asset_id": "private-asset-id",
    },
    {
        "symbol": "FICTB",
        "asset_class": "us_equity",
        "qty": "-1",
        "side": "short",
        "current_price": "30",
        "avg_entry_price": "40",
        "account": "private-account",
    },
]


def test_equivalent_positions_share_exact_calculations_and_distinct_sources():
    csv_report = build_report(io.StringIO((ASSETS / "fictional_holdings.csv").read_text()), STAMP)
    alpaca_report = build_alpaca_report(POSITIONS, STAMP)
    assert alpaca_report["provenance"] == {
        "source": "alpaca_positions_snapshot",
        "as_of": "2026-10-20T12:00:00+00:00",
        "freshness": "operator_asserted",
    }
    assert csv_report["provenance"]["source"] == "local_csv"
    assert {k: v for k, v in alpaca_report.items() if k != "provenance"} == {
        k: v for k, v in csv_report.items() if k != "provenance"
    }
    assert "private" not in json.dumps(alpaca_report) + render_markdown(alpaca_report)
    assert "alpaca_positions_snapshot" in render_markdown(alpaca_report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", None),
        ("symbol", "[private](url)"),
        ("symbol", 123),
        ("asset_class", "crypto"),
        ("asset_class", None),
        ("currency", "EUR"),
        ("side", "LONG"),
        ("side", "sell"),
        ("side", None),
        ("qty", "-2.5"),
        ("qty", "0"),
        ("qty", "NaN"),
        ("qty", "Infinity"),
        ("qty", "1e5"),
        ("qty", 2.5),
        ("qty", True),
        ("qty", " 2.5"),
        ("current_price", "0"),
        ("current_price", None),
        ("current_price", 20),
        ("current_price", "-20"),
        ("current_price", "1e100"),
        ("avg_entry_price", "-1"),
        ("avg_entry_price", False),
    ],
)
def test_invalid_native_fields_fail_without_echo(field, value):
    positions = copy.deepcopy(POSITIONS)
    positions[0][field] = value
    with pytest.raises(CsvError) as error:
        build_alpaca_report(positions, STAMP)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("qty", ["1", "-0", "+1", "--1", "-NaN", "-1e100", "- 1"])
def test_short_quantity_requires_negative_nonzero_decimal(qty):
    positions = copy.deepcopy(POSITIONS)
    positions[1]["qty"] = qty
    with pytest.raises(CsvError):
        build_alpaca_report(positions, STAMP)


@pytest.mark.parametrize("field", ["symbol", "asset_class", "qty", "side", "current_price"])
def test_required_native_fields(field):
    positions = copy.deepcopy(POSITIONS)
    del positions[0][field]
    with pytest.raises(CsvError):
        build_alpaca_report(positions, STAMP)


@pytest.mark.parametrize("value", [None, {}, [], [None], [123], ["private"]])
def test_malformed_or_empty_snapshots(value):
    with pytest.raises(CsvError):
        build_alpaca_report(value, STAMP)


def test_duplicate_normalized_symbol_and_row_limit_are_rejected():
    duplicate = copy.deepcopy(POSITIONS)
    duplicate[1]["symbol"] = " ficta "
    with pytest.raises(CsvError, match="duplicate"):
        build_alpaca_report(duplicate, STAMP)
    with pytest.raises(CsvError, match="limit"):
        build_alpaca_report([POSITIONS[0]] * 10001, STAMP)


@pytest.mark.parametrize("basis", [None, "", "0"])
def test_optional_per_share_basis_and_fractional_short(basis):
    positions = copy.deepcopy(POSITIONS)
    positions[1]["qty"] = "-0.000001"
    positions[1]["avg_entry_price"] = basis
    positions[1]["cost_basis"] = "999999"  # Total provider basis must never become per-share cost.
    result = build_alpaca_report(positions, STAMP)
    short = result["positions"][1]
    assert short["quantity"] == "0.000001"
    assert short["gross_market_value"] == "0.00003"
    assert short["cost_basis"] == ("0" if basis == "0" else None)
    assert short["unrealized_pnl"] == ("-0.00003" if basis == "0" else None)


def test_absent_basis_is_unavailable():
    positions = copy.deepcopy(POSITIONS)
    del positions[0]["avg_entry_price"]
    assert build_alpaca_report(positions, STAMP)["positions"][0]["cost_basis"] is None


@pytest.mark.parametrize("stamp", ["invalid", "2026-10-20", "2026-10-20T12:00:00"])
def test_native_input_uses_same_aware_asof_contract(stamp):
    with pytest.raises(CsvError):
        build_alpaca_report(POSITIONS, stamp)


def test_shared_json_schema_covers_csv_and_native_report():
    schema = json.loads((ASSETS / "holdings-review.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    reports = [
        build_report(io.StringIO((ASSETS / "fictional_holdings.csv").read_text()), STAMP),
        build_alpaca_report(POSITIONS, STAMP),
    ]
    for report in reports:
        jsonschema.validate(report, schema, format_checker=jsonschema.FormatChecker())
        report["positions"][0]["account"] = "private-account"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(report, schema)


def test_alpaca_cli_is_offline_and_uses_existing_output_names(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network call")

    monkeypatch.setattr(socket, "socket", forbidden)
    source = tmp_path / "private-input-name.json"
    source.write_text(json.dumps(POSITIONS))
    output = tmp_path / "reports"
    arguments = [
        "--input",
        str(source),
        "--input-format",
        "alpaca-json",
        "--as-of",
        STAMP,
        "--output-dir",
        str(output),
    ]
    assert main(arguments) == 0
    result = json.loads((output / "portfolio_csv_review.json").read_text())
    assert result["gross_holdings_value"] == "80"
    assert result["net_holdings_value"] == "20"
    assert result["provenance"]["source"] == "alpaca_positions_snapshot"
    assert (output / "portfolio_csv_review.md").exists()
    assert source.read_text() == json.dumps(POSITIONS)
    assert "private" not in capsys.readouterr().out
    source.write_text('{"private": invalid JSON')
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert "private" not in captured.err + captured.out
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def test_breakeven_short_has_unsigned_zero_pnl():
    positions = copy.deepcopy(POSITIONS)
    positions[1]["avg_entry_price"] = positions[1]["current_price"]
    assert build_alpaca_report(positions, STAMP)["positions"][1]["unrealized_pnl"] == "0"


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("qty", "-2.5", "position 2: invalid qty"),
        ("current_price", "0", "position 2: invalid current_price"),
        ("avg_entry_price", "-1", "position 2: invalid avg_entry_price"),
        ("symbol", "[bad]", "position 2: invalid equity symbol"),
    ],
)
def test_diagnostics_use_one_position_number_and_native_names(field, value, message):
    positions = [copy.deepcopy(POSITIONS[0]), {**POSITIONS[0], "symbol": "OTHER", field: value}]
    with pytest.raises(CsvError) as error:
        build_alpaca_report(positions, STAMP)
    assert str(error.value) == message


def test_csv_diagnostics_keep_row_numbers():
    text = "symbol,asset_type,quantity,direction,price,currency\nAAA,equity,1,LONG,0,USD\n"
    with pytest.raises(CsvError, match="row 2: invalid price"):
        build_report(io.StringIO(text), STAMP)
