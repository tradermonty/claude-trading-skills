"""Offline CSV foundation: arithmetic, rejection and privacy contracts."""

import io
import json
import socket
from pathlib import Path

import pytest
from review_csv import CsvError, build_report, main, render_markdown

HEADER = "symbol,asset_type,quantity,direction,price,currency,cost_basis,account\n"
ROWS = "FICTA,equity,2.5,LONG,20,USD,15,private-account\nFICTB,equity,1,SHORT,30,USD,40,private-account\n"
STAMP = "2026-10-20T12:00:00Z"


def report(text=HEADER + ROWS, stamp=STAMP):
    return build_report(io.StringIO(text), stamp)


def test_exact_fractional_long_short_values_and_privacy():
    result = report()
    assert result["gross_holdings_value"] == "80"
    assert result["net_holdings_value"] == "20"
    a, b = result["positions"]
    assert a["gross_weight_pct"] == "62.5"
    assert b["gross_weight_pct"] == "37.5"
    assert a["unrealized_pnl"] == "12.5"
    assert b["unrealized_pnl"] == "10"
    assert result["provenance"] == {
        "source": "local_csv",
        "as_of": "2026-10-20T12:00:00+00:00",
        "freshness": "operator_asserted",
    }
    assert "private-account" not in json.dumps(result) + render_markdown(result)


def test_missing_cost_is_unavailable_without_aggregate():
    result = report((HEADER + ROWS).replace(",40,", ",,"))
    assert result["positions"][1]["unrealized_pnl"] is None
    assert "unrealized_pnl" not in result
    assert "unavailable" in render_markdown(result)
    result = report((HEADER + ROWS).replace(",15,", ",,").replace(",40,", ",,"))
    assert all(p["unrealized_pnl"] is None for p in result["positions"])


@pytest.mark.parametrize(
    "text",
    [
        "",
        HEADER,
        HEADER + "\n",
        HEADER + ROWS + ROWS,
        (HEADER + ROWS).replace("FICTB", " ficta "),
        (HEADER + ROWS).replace("FICTA", "[private](url)"),
        (HEADER + ROWS).replace("FICTA", "FICT\x00A"),
        (HEADER + ROWS).replace("equity", "option"),
        (HEADER + ROWS).replace("USD", "EUR"),
        (HEADER + ROWS).replace("LONG", "BUY"),
        (HEADER + ROWS).replace("quantity,", "secret,"),
        (HEADER + ROWS).replace("account\n", "quantity\n"),
        HEADER + ROWS + "FICTC,equity,1\n",
        HEADER + ROWS.replace("private-account", "private,extra"),
        'symbol,asset_type,quantity,direction,price,currency\n"unterminated',
    ],
)
def test_invalid_inputs_do_not_echo_private_values(text):
    with pytest.raises(CsvError) as err:
        report(text)
    assert "private" not in str(err.value)


@pytest.mark.parametrize("field", ["quantity", "price", "cost_basis"])
@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "1e100000", "0.0000000000001", "9" * 80])
def test_numeric_limits(field, bad):
    columns = HEADER.strip().split(",")
    values = ROWS.splitlines()[0].split(",")
    values[columns.index(field)] = bad
    with pytest.raises(CsvError):
        report(HEADER + ",".join(values) + "\n")


def test_zero_rules_and_bounded_extreme_totals():
    with pytest.raises(CsvError):
        report((HEADER + ROWS).replace("2.5", "0"))
    with pytest.raises(CsvError):
        report((HEADER + ROWS).replace(",20,", ",0,"))
    assert report((HEADER + ROWS).replace(",15,", ",0,"))["positions"][0]["unrealized_pnl"] == "50"
    result = report(
        (HEADER + ROWS).replace("2.5", "1000000000000").replace(",20,", ",1000000000000,")
    )
    assert result["gross_holdings_value"] == "1000000000000000000000030"


@pytest.mark.parametrize("stamp", ["", "2026-10-20", "2026-10-20T12:00:00", "invalid"])
def test_explicit_aware_timestamp(stamp):
    with pytest.raises(CsvError):
        report(stamp=stamp)


def test_row_limit():
    with pytest.raises(CsvError, match="limit"):
        report(HEADER + "".join(f"FICT{i},equity,1,LONG,1,USD,,\n" for i in range(10001)))


def test_cli_fixture_is_offline_and_redacts_errors(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("network access")

    monkeypatch.setattr(socket, "socket", forbidden)
    fixture = Path(__file__).resolve().parents[2] / "assets" / "fictional_holdings.csv"
    output = tmp_path / "reports"
    assert main(["--input", str(fixture), "--as-of", STAMP, "--output-dir", str(output)]) == 0
    data = json.loads((output / "portfolio_csv_review.json").read_text())
    assert data["gross_holdings_value"] == "80"
    assert (output / "portfolio_csv_review.md").exists()
    assert main(["--input", str(tmp_path / "private-name.csv"), "--as-of", STAMP]) == 1
    captured = capsys.readouterr()
    assert "private" not in captured.err + captured.out
    invalid = tmp_path / "bad.csv"
    invalid.write_text(HEADER)
    assert (
        main(["--input", str(invalid), "--as-of", STAMP, "--output-dir", str(tmp_path / "absent")])
        == 1
    )
    assert not (tmp_path / "absent").exists()


def test_output_alias_cannot_destroy_input(tmp_path):
    import os

    source = tmp_path / "holdings.csv"
    original = HEADER + ROWS
    source.write_text(original)
    output = tmp_path / "output"
    output.mkdir()
    os.link(source, output / "portfolio_csv_review.json")
    assert main(["--input", str(source), "--as-of", STAMP, "--output-dir", str(output)]) == 1
    assert source.read_text() == original


def test_symlink_loop_has_safe_diagnostic(tmp_path, capsys):
    source = tmp_path / "holdings.csv"
    source.write_text(HEADER + ROWS)
    loop = tmp_path / "private-account"
    loop.symlink_to(loop)
    assert main(["--input", str(source), "--as-of", STAMP, "--output-dir", str(loop)]) == 1
    captured = capsys.readouterr()
    assert "private-account" not in captured.err + captured.out
