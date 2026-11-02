"""Tests for build_tax_planning_sheet.py."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import build_tax_planning_sheet as tax
import pytest
from build_tax_planning_sheet import classify_holding, render_markdown, write_csv


def test_classify_stock_with_sufficient_days_is_qualified_likely() -> None:
    row = classify_holding(
        {
            "ticker": "jnj",
            "instrument_type": "stock",
            "account_type": "taxable",
            "hold_days_in_window": 75,
            "security_type": "common",
        }
    )
    assert row.classification == "qualified_likely"


def test_classify_missing_days_is_assumption_required() -> None:
    row = classify_holding(
        {
            "ticker": "pg",
            "instrument_type": "stock",
            "account_type": "taxable",
        }
    )
    assert row.classification == "assumption_required"


def test_classify_mlp_is_out_of_scope() -> None:
    row = classify_holding(
        {
            "ticker": "et",
            "instrument_type": "mlp",
            "account_type": "ira",
            "hold_days_in_window": 200,
        }
    )
    assert row.classification == "out_of_scope_mlp"
    assert row.location_hint == "case_by_case"


def test_markdown_and_csv_generation(tmp_path: Path) -> None:
    rows = [
        classify_holding(
            {
                "ticker": "o",
                "instrument_type": "reit",
                "account_type": "ira",
                "hold_days_in_window": 100,
            }
        ),
        classify_holding(
            {
                "ticker": "jnj",
                "instrument_type": "stock",
                "account_type": "taxable",
                "hold_days_in_window": 80,
            }
        ),
    ]
    markdown = render_markdown(rows, "2026-02-22")
    assert "# US Dividend Tax Planning Sheet" in markdown
    assert "| O | reit | ira | 100 | ordinary_likely |" in markdown

    csv_path = tmp_path / "sheet.csv"
    write_csv(csv_path, rows)
    with csv_path.open() as f:
        reader = list(csv.reader(f))
    assert reader[0][0] == "ticker"
    assert reader[1][0] == "O"
    assert reader[2][0] == "JNJ"


@pytest.mark.parametrize(
    "security_type,days,classification,threshold",
    [
        ("common", 60, "ordinary_likely", 61),
        ("common", 61, "qualified_likely", 61),
        ("preferred", 90, "ordinary_likely", 91),
        ("preferred", 91, "qualified_likely", 91),
    ],
)
def test_holding_period_boundary(security_type, days, classification, threshold):
    row = classify_holding(
        {"ticker": "example", "security_type": security_type, "hold_days_in_window": days}
    )
    assert row.ticker == "EXAMPLE"
    assert row.hold_days_in_window == days
    assert row.classification == classification
    assert row.location_hint == "taxable_preferred"
    comparison = ">=" if classification == "qualified_likely" else "<"
    assert row.note == f"hold_days_in_window {comparison} {threshold}"


@pytest.mark.parametrize("instrument", ["reit", "bdc"])
@pytest.mark.parametrize("days", [0, 200, None])
def test_reit_and_bdc_keep_ordinary_planning_branch(instrument, days):
    row = classify_holding(
        {"instrument_type": instrument, "security_type": "preferred", "hold_days_in_window": days}
    )
    assert row.instrument_type == instrument
    assert row.hold_days_in_window == days
    assert row.classification == "ordinary_likely"
    assert row.location_hint == "tax_advantaged_preferred"
    assert "may include" in row.note


@pytest.mark.parametrize("security_type", ["common", "preferred"])
def test_null_days_remain_an_unverified_assumption(security_type):
    row = classify_holding({"security_type": security_type, "hold_days_in_window": None})
    assert row.hold_days_in_window is None
    assert row.classification == "assumption_required"


def test_zero_days_is_valid_but_insufficient():
    row = classify_holding({"hold_days_in_window": 0})
    assert row.hold_days_in_window == 0
    assert row.classification == "ordinary_likely"


INVALID_DAYS = ["invalid", "61", 61.5, 61.0, True, False, -1, [], {}, float("nan"), float("inf")]
INVALID_IDS = [
    "text",
    "numeric-text",
    "fractional",
    "float",
    "true",
    "false",
    "negative",
    "array",
    "object",
    "nan",
    "infinity",
]


@pytest.mark.parametrize("days", INVALID_DAYS, ids=INVALID_IDS)
def test_invalid_holding_days_have_a_descriptive_validation_error(days):
    with pytest.raises(ValueError, match="hold_days_in_window must be a non-negative integer"):
        classify_holding({"hold_days_in_window": days})


def _set_cli(monkeypatch, input_path, output):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(Path(tax.__file__)),
            "--input",
            str(input_path),
            "--output-dir",
            str(output),
            "--as-of",
            "2026-11-01",
        ],
    )


@pytest.mark.parametrize("days", INVALID_DAYS, ids=INVALID_IDS)
def test_invalid_days_fail_cli_before_writing_reports(tmp_path, monkeypatch, capsys, days):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"holdings": [{"hold_days_in_window": days}]}))
    output = tmp_path / "reports"
    _set_cli(monkeypatch, input_path, output)
    assert tax.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "hold_days_in_window" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()


def test_cli_writes_boundary_classifications_and_unknown_days(tmp_path, monkeypatch, capsys):
    holdings = [
        {"ticker": "C60", "security_type": "common", "hold_days_in_window": 60},
        {"ticker": "C61", "security_type": "common", "hold_days_in_window": 61},
        {"ticker": "P90", "security_type": "preferred", "hold_days_in_window": 90},
        {"ticker": "P91", "security_type": "preferred", "hold_days_in_window": 91},
        {"ticker": "UNKNOWN"},
        {"ticker": "REIT", "instrument_type": "reit", "hold_days_in_window": 200},
        {"ticker": "BDC", "instrument_type": "bdc", "hold_days_in_window": 200},
    ]
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"holdings": holdings}))
    output = tmp_path / "reports"
    _set_cli(monkeypatch, input_path, output)
    assert tax.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Wrote markdown:" in captured.out
    assert "Wrote csv:" in captured.out
    with (output / "tax_planning_sheet_2026-11-01.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["classification"] for row in rows] == [
        "ordinary_likely",
        "qualified_likely",
        "ordinary_likely",
        "qualified_likely",
        "assumption_required",
        "ordinary_likely",
        "ordinary_likely",
    ]
    assert rows[4]["hold_days_in_window"] == ""
    markdown = (output / "tax_planning_sheet_2026-11-01.md").read_text()
    for ticker, days, classification in (
        ("C60", 60, "ordinary_likely"),
        ("C61", 61, "qualified_likely"),
        ("P90", 90, "ordinary_likely"),
        ("P91", 91, "qualified_likely"),
    ):
        assert f"| {ticker} | stock | unknown | {days} | {classification} |" in markdown
    assert "| UNKNOWN | stock | unknown |  | assumption_required |" in markdown
    assert "Confirm final classification" in markdown


def test_empty_holdings_stops_without_reports(tmp_path, monkeypatch):
    input_path = tmp_path / "input.json"
    input_path.write_text('{"holdings": []}')
    output = tmp_path / "reports"
    _set_cli(monkeypatch, input_path, output)
    with pytest.raises(SystemExit, match="non-empty holdings list"):
        tax.main()
    assert not output.exists()


def test_standalone_cli_rejects_invalid_later_holding_without_overwriting(tmp_path):
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(
            {
                "holdings": [
                    {"ticker": "VALID", "hold_days_in_window": 61},
                    {"ticker": "INVALID", "hold_days_in_window": "invalid"},
                ]
            }
        )
    )
    output = tmp_path / "reports"
    output.mkdir()
    existing = output / "tax_planning_sheet_2026-11-01.csv"
    existing.write_text("existing report\n")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(tax.__file__)),
            "--input",
            str(input_path),
            "--output-dir",
            str(output),
            "--as-of",
            "2026-11-01",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "ERROR: hold_days_in_window" in result.stderr
    assert "Traceback" not in result.stderr
    assert existing.read_text() == "existing report\n"
    assert list(output.iterdir()) == [existing]
