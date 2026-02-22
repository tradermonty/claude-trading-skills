"""Tests for build_tax_planning_sheet.py."""

import csv
from pathlib import Path

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
