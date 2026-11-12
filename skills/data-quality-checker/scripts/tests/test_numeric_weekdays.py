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


def test_fullwidth_digits_do_not_allow_suffix_salvage():
    assert check_dates("２０２６/１１-１０（水）", as_of=date(2026, 11, 7)) == []


@pytest.mark.parametrize(
    "text",
    ["１２０２６/１１/１０（水）", "２０２６/ １１/１０（水）", "２０２６-１１/１０（水）"],
)
def test_fullwidth_malformed_year_still_reports_a_weekday_wrong_in_every_reading(text):
    # 2026-11-10 is a Tuesday, the written and the inferred year agree.
    assert len(check_dates(text, as_of=date(2026, 11, 7))) == 1
    assert check_dates(text.replace("水", "火"), as_of=date(2026, 11, 7)) == []


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


@pytest.mark.parametrize("separator", ["-", "/"])
@pytest.mark.parametrize("brackets", [("(", ")"), ("（", "）")])
def test_range_without_first_weekday_checks_second_date(separator, brackets):
    # 2026-12-10 is a Thursday. main flagged this second endpoint before #657.
    opening, closing = brackets
    bad = f"FOMC 12/9{separator}12/10{opening}金{closing}"
    findings = check_dates(bad, as_of=date(2026, 11, 7))
    assert len(findings) == 1
    assert "12/10" in findings[0].message
    good = f"FOMC 12/9{separator}12/10{opening}木{closing}"
    assert check_dates(good, as_of=date(2026, 11, 7)) == []


@pytest.mark.parametrize(
    "text",
    [
        "12/9 10:00-12/10(金)",
        "１２/９-１２/１０（金）",
        "2026/12/9-12/10(金)",
        "2026-12-09-2026-12-10 (Fri)",
        "2026/12/09-2026/12/10 (Fri)",
    ],
)
def test_digit_joined_range_variants_check_second_date(text):
    # 2026-12-10 is a Thursday.
    findings = check_dates(text, as_of=date(2026, 11, 7))
    assert len(findings) == 1


def test_many_dates_stay_fast():
    import time

    doc = "".join(f"Line {i}: 11/10(火) and 2026-11-10 (Tue).\n" for i in range(5000))
    started = time.perf_counter()
    assert check_dates(doc, as_of=date(2026, 11, 7)) == []
    assert time.perf_counter() - started < 5


@pytest.mark.parametrize(
    "text",
    [
        "2026/ 11/10 (Wed)",
        "2026-11/10 (Wed)",
        "v1.2.3/11/10 (Wed)",
        "a1-11/10 (Wed)",
        # Digit-joined tokens that are not the second endpoint of a range.
        "12/10/26 (Thu)",
        "1/2/10 (Sat)",
        "abc123/11/10 (Wed)",
        "a123-11/10 (Wed)",
        "1.234/11/10 (Wed)",
        "https://x.com/p/123/11/10 (Wed)",
        "ratio 100/3/4 (Mon)",
        "score 3-2/10 (Thu)",
        "１２３/１１/１０ (Wed)",
        "#3-11/10 (Wed)",
        "Week 45-11/10 (Wed)",
        "11/9-10/11/10 (Wed)",
    ],
)
def test_digit_joined_prefix_does_not_salvage_malformed_dates(text):
    assert check_dates(text, as_of=date(2026, 11, 7)) == []


@pytest.mark.parametrize(
    "text",
    [
        # main flagged these through its unguarded M/D(曜) pattern.
        "12/9(水) 22:00-12/10(金)",
        "12/9 (水) 10:00-12/10(金)",
        "22:00-12/10(金)",
        "12/8-12/9-12/10(金)",
        "12/9 9:30:00-12/10(金)",
        "12/9 9時-12/10(金)",
        "_12/10(金)_",
        "__12/10(金)__",
        "FOMC12/10(金)",
        "CPI発表日/12/10(金)",
        "日程-12/10(金)",
        "Q4-12/10(金)",
        "...12/10(金)",
        "v１２/１０（金）",
    ],
)
def test_legacy_japanese_slash_dates_keep_main_coverage(text):
    # 2026-12-10 is a Thursday.
    findings = check_dates(text, as_of=date(2026, 11, 7))
    assert len(findings) == 1
    assert "12/10" in findings[0].message or "１２/１０" in findings[0].message


def test_explicit_year_is_not_reported_twice_by_the_legacy_pattern():
    # 2025-11-10 is a Monday; the inferred 2026 would make 11/10(月) wrong.
    assert check_dates("2025/11/10(月)", as_of=date(2026, 11, 7)) == []
    assert len(check_dates("2025/11/10(火)", as_of=date(2026, 11, 7))) == 1


@pytest.mark.parametrize(
    "text",
    [
        "FOMC2026/12/10(金)",
        "_2026/12/10(金)_",
        "...2026/12/10(金)",
        "日程-2026/12/10(金)",
        "2026/12/9(水) 22:00-2026/12/10(金)",
        "2026/12/9 (水) 10:00-2026/12/10(金)",
    ],
)
def test_labelled_explicit_year_dates_are_checked_with_the_written_year(text):
    # 2026-12-10 is a Thursday.
    findings = check_dates(text, as_of=date(2026, 11, 7))
    assert len(findings) == 1
    assert "(year: 2026)" in findings[0].message


def test_labelled_explicit_year_wins_over_inferred_year():
    # 2025-11-10 is a Monday; the inferred year 2026 would make it a Tuesday.
    assert check_dates("FOMC2025/11/10(月)", as_of=date(2026, 11, 7)) == []


@pytest.mark.parametrize(
    "text,flagged",
    [
        ("2025-11/10(水)", True),  # Monday in 2025, Tuesday in 2026
        ("2025-11/10(月)", False),  # right if 2025 is the year
        ("2025-11/10(火)", False),  # right if the inferred 2026 is the year
        ("2026/ 12/10(月)", True),
    ],
)
def test_malformed_year_prefix_reports_only_weekdays_wrong_under_both_years(text, flagged):
    findings = check_dates(text, as_of=date(2026, 11, 7))
    assert bool(findings) is flagged


def test_ambiguous_year_prefix_uses_only_valid_readings():
    # 2025-02-29 does not exist; 2028-02-29 is a Tuesday.
    findings = check_dates("2025-2/29(月)", as_of=date(2028, 3, 1))
    assert len(findings) == 1
    assert "(inferred year: 2028)" in findings[0].message
    assert check_dates("2025-2/29(火)", as_of=date(2028, 3, 1)) == []
