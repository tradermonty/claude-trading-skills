"""Public date validation for report formats that previously escaped checking."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from check_data_quality import check_dates

DATES = ["2026-11-10", "2026/11/10", "11/10", "11月10日"]


@pytest.mark.parametrize(
    "value,good,bad",
    [
        (v, g, b)
        for v in DATES
        for g, b in [("Tue", "Wed"), ("Tuesday", "Wednesday"), ("火", "水"), ("火曜日", "水曜日")]
        if not ("月" in v and g.isascii())
    ],
)
@pytest.mark.parametrize("brackets", [("(", ")"), ("（", "）")])
@pytest.mark.parametrize("space", ["", " ", "\t"])
def test_weekday_formats(value, brackets, space, good, bad):
    prefix, suffix = brackets
    assert check_dates(f"{value}{space}{prefix}{good}{suffix}", as_of=date(2026, 11, 7)) == []
    findings = check_dates(
        f"# Sample\n\nEvent {value}{space}{prefix}{bad}{suffix}", as_of=date(2026, 11, 7)
    )
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].category == "dates"
    assert findings[0].line_number == 3


@pytest.mark.parametrize(
    "text",
    [
        "12026/11/10 (Wed)",
        "2026-11/10 (Wed)",
        "2026/11-10 (Wed)",
        "v11/10 (Wed)",
        "2026/ 11/10 (Wed)",
        "2026-02-30 (Wed)",
        "1900/02/29 (Wed)",
        "11/10 (Wednesdayish)",
        "11/10（Wed)",
        "11/10(Wed）",
        "11/10\n(Wed)",
    ],
)
def test_no_partial_or_invalid_matches(text):
    assert check_dates(text, as_of=date(2026, 11, 7)) == []


def test_explicit_year_wins_and_has_no_yearless_duplicate():
    assert check_dates("2026/11/10 (Tuesday)", as_of=date(2027, 11, 7)) == []
    assert len(check_dates("2026/11/10 (Wednesday)", as_of=date(2027, 11, 7))) == 1
    assert check_dates("開催日2026-11-10（火）", as_of=date(2027, 11, 7)) == []
    assert len(check_dates("開催日2026-11-10（水）", as_of=date(2027, 11, 7))) == 1


def test_leap_day_and_yearless_inference():
    assert check_dates("2000/02/29 (Tue)", as_of=date(2026, 11, 7)) == []
    assert len(check_dates("2000/02/29 (Wed)", as_of=date(2026, 11, 7))) == 1
    assert check_dates("1/1 (Fri)", as_of=date(2026, 12, 20)) == []  # 2027
    assert check_dates("12/31 (Wed)", as_of=date(2026, 1, 5)) == []  # 2025
    assert check_dates("# Report 2026\n11/10 (Tue)") == []
    assert check_dates("11/10 (Tue)", filepath="report-2026-11-07.md") == []


def test_cli_emits_findings_but_remains_advisory(tmp_path):
    source = tmp_path / "sample.md"
    source.write_text("Event 2026-11-10 (Wed).\n", encoding="utf-8")
    output = tmp_path / "reports"
    script = Path(__file__).resolve().parents[1] / "check_data_quality.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--file",
            str(source),
            "--as-of",
            "2026-11-07",
            "--checks",
            "dates",
            "--output-dir",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rows = json.loads(next(output.glob("*.json")).read_text(encoding="utf-8"))
    assert len(rows) == 1 and rows[0]["severity"] == "ERROR"
    assert rows[0]["line_number"] == 1
    assert "Tuesday" in rows[0]["message"]
    assert "## ERROR (1)" in next(output.glob("*.md")).read_text(encoding="utf-8")


@pytest.mark.parametrize("weekday", ["ſun", "Frİday"])
def test_unicode_casefold_is_not_an_english_weekday(weekday):
    assert check_dates(f"2026-11-10 ({weekday})", as_of=date(2026, 11, 7)) == []


@pytest.mark.parametrize("separator", ["-", "/"])
@pytest.mark.parametrize("brackets", [("(", ")"), ("（", "）")])
@pytest.mark.parametrize(
    "dates", [("11/10", "11/12"), ("2026-11-10", "2026-11-12"), ("2026/11/10", "2026/11/12")]
)
@pytest.mark.parametrize("wrong", [(True, False), (False, True), (True, True), (False, False)])
def test_tight_ranges_check_both_endpoints(separator, brackets, dates, wrong):
    opening, closing = brackets
    first, second = dates
    first_day = "Wed" if wrong[0] else "Tue"
    second_day = "Wed" if wrong[1] else "Thu"
    text = f"{first}{opening}{first_day}{closing}{separator}{second}{opening}{second_day}{closing}"
    findings = check_dates(text, as_of=date(2026, 11, 7))
    assert len(findings) == sum(wrong)
    for value, is_wrong in zip(dates, wrong):
        assert any(value in row.message for row in findings) == is_wrong


@pytest.mark.parametrize("value", ["11月10日", "11/10", "2026-11-10", "2026/11/10"])
@pytest.mark.parametrize("brackets", [("（", ")"), ("(", "）")])
@pytest.mark.parametrize("weekday,expected", [("水", 1), ("水曜日", 1), ("火", 0)])
def test_japanese_weekdays_preserve_mixed_parentheses(value, brackets, weekday, expected):
    opening, closing = brackets
    findings = check_dates(f"{value}{opening}{weekday}{closing}", as_of=date(2026, 11, 7))
    assert len(findings) == expected


@pytest.mark.parametrize(
    "value", ["１１/１０", "２０２６/１１/１０", "２０２６-１１-１０", "１１月１０日"]
)
@pytest.mark.parametrize("weekday,expected", [("水", 1), ("火", 0)])
def test_fullwidth_date_digits(value, weekday, expected):
    findings = check_dates(f"{value}（{weekday}）", as_of=date(2026, 11, 7))
    assert len(findings) == expected


@pytest.mark.parametrize(
    "text",
    [
        "１２０２６/１１/１０（水）",
        "２０２６/ １１/１０（水）",
        "２０２６-１１/１０（水）",
        "２０２６/１１-１０（水）",
        "v１１/１０（水）",
    ],
)
def test_fullwidth_digits_do_not_allow_suffix_salvage(text):
    assert check_dates(text, as_of=date(2026, 11, 7)) == []


def test_fullwidth_explicit_year_wins():
    assert check_dates("２０２６/１１/１０（火）", as_of=date(2027, 11, 7)) == []
    assert len(check_dates("２０２６/１１/１０（水）", as_of=date(2027, 11, 7))) == 1


@pytest.mark.parametrize("separator", ["-", "/"])
@pytest.mark.parametrize("closing", [")", "）"])
def test_japanese_tight_range_regression(separator, closing):
    text = f"11/10（火{closing}{separator}11/12（水）"
    findings = check_dates(text, as_of=date(2026, 11, 7))
    assert len(findings) == 1
    assert "11/12（水）" in findings[0].message
