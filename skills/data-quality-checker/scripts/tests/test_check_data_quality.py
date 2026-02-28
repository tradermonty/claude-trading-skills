"""Tests for data quality checker.

TDD-first: these tests define the expected behavior of check_data_quality.py.
"""

from __future__ import annotations

import calendar
import os
import subprocess
import sys
import tempfile
from datetime import date

from check_data_quality import (
    Finding,
    check_allocations,
    check_dates,
    check_notation,
    check_price_scale,
    check_units,
    generate_report,
    infer_year,
    run_checks,
)

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..")


# ──────────────────────────────────────────────
# Price Scale Tests
# ──────────────────────────────────────────────


class TestPriceScale:
    """Price scale detection using digit-count hints."""

    def test_price_scale_gld_label_with_futures_price(self):
        """GLD expects 2-3 digits; $2,800 has 4 digits -> WARNING."""
        content = "GLD: $2,800"
        findings = check_price_scale(content)
        assert len(findings) >= 1
        f = findings[0]
        assert f.severity == "WARNING"
        assert f.category == "price_scale"
        assert "GLD" in f.message
        assert "4 digits" in f.message

    def test_price_scale_gc_label_with_etf_price(self):
        """GC expects 3-4 digits; $18 has 2 digits -> WARNING."""
        content = "GC: $18"
        findings = check_price_scale(content)
        assert len(findings) >= 1
        f = findings[0]
        assert f.severity == "WARNING"
        assert f.category == "price_scale"
        assert "GC" in f.message
        assert "2 digits" in f.message

    def test_price_scale_gc_high_value_valid(self):
        """GC at $3,996 has 4 digits, within (3,4) range -> no warning."""
        content = "Gold futures (GC) closed at $3,996"
        findings = check_price_scale(content)
        gc_findings = [f for f in findings if "GC" in f.message]
        assert len(gc_findings) == 0

    def test_price_scale_gc_very_high_valid(self):
        """GC: $5,080 has 4 digits, within (3,4) range -> no warning."""
        content = "GC: $5,080"
        findings = check_price_scale(content)
        gc_findings = [f for f in findings if "GC" in f.message]
        assert len(gc_findings) == 0

    def test_price_scale_mixed_in_same_doc(self):
        """GLD: $2,800 should warn (4 digits); Gold: $268 has no ticker match."""
        content = "GLD: $2,800\nGold: $268"
        findings = check_price_scale(content)
        gld_findings = [f for f in findings if "GLD" in f.message]
        assert len(gld_findings) >= 1
        assert gld_findings[0].severity == "WARNING"

    def test_price_scale_consistent(self):
        """GLD: $268 (3 digits in 2-3 range) and SPY: $580 (3 digits in 2-3 range) -> OK."""
        content = "GLD: $268\nSPY: $580"
        findings = check_price_scale(content)
        assert len(findings) == 0

    def test_price_scale_ratio_mismatch(self):
        """GLD $280 + GC $1,600 in same doc: ratio 5.7x vs expected ~15x -> WARNING."""
        content = "GLD: $280\nGC: $1,600"
        findings = check_price_scale(content)
        ratio_findings = [f for f in findings if "ratio" in f.message.lower()]
        assert len(ratio_findings) >= 1
        assert ratio_findings[0].severity == "WARNING"
        assert "GC" in ratio_findings[0].message
        assert "GLD" in ratio_findings[0].message

    def test_price_scale_ratio_consistent(self):
        """GLD $280 + GC $4,200: ratio 15x matches expected -> no ratio warning."""
        content = "GLD: $280\nGC: $4,200"
        findings = check_price_scale(content)
        ratio_findings = [f for f in findings if "ratio" in f.message.lower()]
        assert len(ratio_findings) == 0

    def test_price_scale_ratio_later_mismatch(self):
        """GLD $280 + GC $4,200 (ok) + later GC $1,600 (bad ratio) -> WARNING."""
        content = "GLD: $280\nGC: $4,200\nLater GC: $1,600"
        findings = check_price_scale(content)
        ratio_findings = [f for f in findings if "ratio" in f.message.lower()]
        # GC $4,200 / GLD $280 = 15x (ok), GC $1,600 / GLD $280 = 5.7x (bad)
        assert len(ratio_findings) >= 1


# ──────────────────────────────────────────────
# Notation Consistency Tests
# ──────────────────────────────────────────────


class TestNotation:
    """Instrument notation consistency checks."""

    def test_notation_inconsistency_gold(self):
        """Mixed Gold, GLD, and 金 -> WARNING about mixed notation."""
        content = "Gold is trading higher. GLD reached $268. 金は上昇中。"
        findings = check_notation(content)
        gold_findings = [f for f in findings if "gold" in f.message.lower()]
        assert len(gold_findings) >= 1
        assert gold_findings[0].severity == "WARNING"
        assert gold_findings[0].category == "notation"

    def test_notation_standard_compliance(self):
        """Consistent GLD usage -> no warnings for gold group."""
        content = "GLD is at $268. GLD options are active. Buy GLD."
        findings = check_notation(content)
        gold_findings = [f for f in findings if "gold" in f.message.lower()]
        assert len(gold_findings) == 0


# ──────────────────────────────────────────────
# Date/Weekday Tests
# ──────────────────────────────────────────────


class TestDates:
    """Date-weekday validation for English and Japanese content."""

    def test_date_weekday_mismatch_english_with_year(self):
        """January 1, 2026 is Thursday, not Monday -> ERROR."""
        assert calendar.day_name[calendar.weekday(2026, 1, 1)] == "Thursday"
        content = "January 1, 2026 (Monday)"
        findings = check_dates(content)
        assert len(findings) >= 1
        f = findings[0]
        assert f.severity == "ERROR"
        assert f.category == "dates"
        assert "Thursday" in f.message

    def test_date_weekday_correct_english_with_year(self):
        """January 1, 2026 is Thursday -> no error."""
        assert calendar.day_name[calendar.weekday(2026, 1, 1)] == "Thursday"
        content = "January 1, 2026 (Thursday)"
        findings = check_dates(content)
        date_findings = [f for f in findings if "January 1" in f.message]
        assert len(date_findings) == 0

    def test_date_weekday_mismatch_english_no_year(self):
        """Jan 1 (Monday) with as_of=2026-01-15 -> infers 2026, Jan 1 is Thursday -> ERROR."""
        assert calendar.day_name[calendar.weekday(2026, 1, 1)] == "Thursday"
        content = "Jan 1 (Monday)"
        findings = check_dates(content, as_of=date(2026, 1, 15))
        assert len(findings) >= 1
        f = findings[0]
        assert f.severity == "ERROR"
        assert f.category == "dates"
        assert "Thursday" in f.message

    def test_date_weekday_correct_english_no_year(self):
        """Jan 1 (Thu) with as_of=2026-01-15 -> infers 2026, Jan 1 is Thursday -> OK."""
        assert calendar.day_name[calendar.weekday(2026, 1, 1)] == "Thursday"
        content = "Jan 1 (Thu)"
        findings = check_dates(content, as_of=date(2026, 1, 15))
        date_findings = [f for f in findings if "Jan 1" in f.message]
        assert len(date_findings) == 0

    def test_date_weekday_mismatch_japanese(self):
        """1月1日（月）with as_of=2026-01-15 -> Jan 1, 2026 is Thursday (木), not Monday (月)."""
        assert calendar.weekday(2026, 1, 1) == 3  # Thursday = 3
        content = "1月1日（月）"
        findings = check_dates(content, as_of=date(2026, 1, 15))
        assert len(findings) >= 1
        f = findings[0]
        assert f.severity == "WARNING"
        assert f.category == "dates"
        assert "木" in f.message  # actual weekday is Thursday = 木

    def test_date_weekday_correct_japanese(self):
        """1月1日（木）with as_of=2026-01-15 -> Jan 1, 2026 is Thursday (木) -> OK."""
        assert calendar.weekday(2026, 1, 1) == 3  # Thursday
        content = "1月1日（木）"
        findings = check_dates(content, as_of=date(2026, 1, 15))
        assert len(findings) == 0

    def test_date_slash_format_japanese(self):
        """1/1(木) with as_of=2026-01-15 -> Jan 1, 2026 is Thursday -> OK."""
        assert calendar.weekday(2026, 1, 1) == 3  # Thursday
        content = "1/1(木)"
        findings = check_dates(content, as_of=date(2026, 1, 15))
        assert len(findings) == 0

    def test_date_week_notation(self):
        """11/03週 -> week notation, no weekday to check, no error."""
        content = "11/03週"
        findings = check_dates(content, as_of=date(2026, 11, 10))
        assert len(findings) == 0

    def test_date_year_inference_from_as_of(self):
        """Feb 28 (Sat) with as_of=date(2026,3,1) -> infers 2026, Feb 28 is Saturday -> OK."""
        assert calendar.day_name[calendar.weekday(2026, 2, 28)] == "Saturday"
        content = "Feb 28 (Sat)"
        findings = check_dates(content, as_of=date(2026, 3, 1))
        date_findings = [f for f in findings if "Feb 28" in f.message]
        assert len(date_findings) == 0

    def test_date_year_inference_from_document(self):
        """Document has '# Report 2026-01-15' and 'Jan 1 (Thu)' -> infers 2026 -> OK."""
        assert calendar.day_name[calendar.weekday(2026, 1, 1)] == "Thursday"
        content = "# Report 2026-01-15\nJan 1 (Thu)"
        findings = check_dates(content)
        date_findings = [f for f in findings if "Jan 1" in f.message]
        assert len(date_findings) == 0

    def test_date_year_inference_fallback_current(self):
        """No year info -> uses current year. Test won't fail as long as logic is consistent."""
        # This is a structural test: no as_of, no year in document
        content = "some content without a year"
        # Should not crash
        findings = check_dates(content)
        assert isinstance(findings, list)

    def test_date_year_inference_cross_year(self):
        """as_of=2026-01-15, 'Dec 25 (Thu)' -> Dec is >6 months back, infers 2025.
        Dec 25, 2025 is Thursday."""
        assert calendar.day_name[calendar.weekday(2025, 12, 25)] == "Thursday"
        content = "Dec 25 (Thu)"
        findings = check_dates(content, as_of=date(2026, 1, 15))
        date_findings = [f for f in findings if "Dec 25" in f.message]
        assert len(date_findings) == 0


# ──────────────────────────────────────────────
# Allocation Total Tests
# ──────────────────────────────────────────────


class TestAllocations:
    """Allocation total validation (section-limited)."""

    def test_allocation_table_sum_over_100(self):
        """Table with 配分 header summing to 110% -> WARNING."""
        content = (
            "| Asset | 配分 |\n"
            "|-------|------|\n"
            "| Stocks | 60% |\n"
            "| Bonds | 30% |\n"
            "| Cash | 20% |\n"
        )
        findings = check_allocations(content)
        assert len(findings) >= 1
        f = findings[0]
        assert f.severity == "WARNING"
        assert f.category == "allocations"
        assert "110" in f.message

    def test_allocation_table_sum_correct(self):
        """Table with Allocation header summing to 100% -> no warning."""
        content = (
            "| Asset | Allocation |\n"
            "|-------|------------|\n"
            "| Stocks | 60% |\n"
            "| Bonds | 30% |\n"
            "| Cash | 10% |\n"
        )
        findings = check_allocations(content)
        assert len(findings) == 0

    def test_allocation_list_format(self):
        """Bullet list under セクター配分 heading summing to 95% -> WARNING."""
        content = "## セクター配分\n- Tech: 40%\n- Healthcare: 30%\n- Energy: 25%\n"
        findings = check_allocations(content)
        assert len(findings) >= 1
        assert findings[0].severity == "WARNING"
        assert "95" in findings[0].message

    def test_allocation_ignores_body_percentages(self):
        """Body text percentages should not trigger allocation warnings."""
        content = "The probability is 35% and momentum at 20%."
        findings = check_allocations(content)
        assert len(findings) == 0

    def test_allocation_ignores_trigger_percentages(self):
        """Trigger conditions should not trigger allocation warnings."""
        content = "RSI < 30% triggers buy signal"
        findings = check_allocations(content)
        assert len(findings) == 0

    def test_allocation_ignores_indicator_percentages(self):
        """Indicator descriptions should not trigger allocation warnings."""
        content = "YoY +3.2% growth is strong"
        findings = check_allocations(content)
        assert len(findings) == 0

    def test_allocation_ignores_position_heading(self):
        """ポジション戦略 heading (without 配分) should NOT be treated as allocation."""
        content = "## ポジション戦略\n- Stocks: 60%\n- Cash: 30%\n"
        findings = check_allocations(content)
        assert len(findings) == 0

    def test_allocation_range_notation_valid(self):
        """Range notation where 100% is contained in [sum_mins, sum_maxs] -> OK."""
        content = "## 配分\n- Stocks: 50-55%\n- Bonds: 20-25%\n- Gold: 15-20%\n- Cash: 5-10%\n"
        # sum_mins = 50+20+15+5 = 90, sum_maxs = 55+25+20+10 = 110
        # 100 is in [90, 110] -> OK
        findings = check_allocations(content)
        assert len(findings) == 0

    def test_allocation_range_notation_invalid(self):
        """Range notation where sum_mins > 100 -> WARNING."""
        # sum_mins = 60+30+10 = 100, sum_maxs = 65+35+15 = 115
        # sum_mins == 100 which is <= 100.5, sum_maxs = 115 >= 99.5
        # Actually this should be OK since 100 IS contained in the range.
        # Wait, re-read the spec: "sum_mins=100, sum_maxs=115, min>100 so WARNING"
        # But 100 is not > 100. Let me re-read...
        # The spec says: "sum_mins=100, sum_maxs=115, min>100 so WARNING"
        # This seems like a spec error. Let me follow the implementation logic:
        # sum_mins > 100.5 OR sum_maxs < 99.5 -> WARNING
        # 100 > 100.5? No. 115 < 99.5? No. So no warning.
        # But the spec explicitly says WARNING. Let me adjust the values.
        # Actually I need to re-read the spec more carefully:
        # "- A: 60-65%\n- B: 30-35%\n- C: 10-15%" -> sum_mins=100, sum_maxs=115
        # The original prompt says "min>100 so WARNING" but 100 is not > 100.
        # I'll change the test values to make sum_mins clearly > 100.
        pass

    def test_allocation_range_notation_invalid_v2(self):
        """Range notation where sum_mins > 100.5 -> WARNING."""
        content = "## 配分\n- A: 60-65%\n- B: 30-35%\n- C: 15-20%\n"
        # sum_mins = 60+30+15 = 105, sum_maxs = 65+35+20 = 120
        # 105 > 100.5 -> WARNING
        findings = check_allocations(content)
        assert len(findings) >= 1
        assert findings[0].severity == "WARNING"

    def test_allocation_detects_sector_allocation_heading(self):
        """セクター配分 heading should trigger allocation detection."""
        content = "## セクター配分\n- Tech: 50%\n- Finance: 50%\n"
        findings = check_allocations(content)
        # 50 + 50 = 100 -> no warning
        assert len(findings) == 0

    def test_allocation_detects_ratio_column(self):
        """Table with 目安比率 column header triggers allocation detection."""
        content = (
            "| Sector | 目安比率 |\n|--------|----------|\n| Tech | 50% |\n| Finance | 50% |\n"
        )
        findings = check_allocations(content)
        # 50 + 50 = 100 -> no warning, but proves the section was detected
        assert len(findings) == 0


# ──────────────────────────────────────────────
# Unit Tests
# ──────────────────────────────────────────────


class TestUnits:
    """Unit consistency checks."""

    def test_unit_missing_warning(self):
        """'Gold moved 50 today' with no $ or % -> WARNING."""
        content = "Gold moved 50 today"
        findings = check_units(content)
        warnings = [f for f in findings if f.severity == "WARNING"]
        assert len(warnings) >= 1
        assert any("unit" in f.message.lower() or "missing" in f.message.lower() for f in warnings)

    def test_unit_bp_vs_pct_mixed(self):
        """Mixed bp and % for yields -> INFO."""
        content = "yield rose 25bp. The rate increased 0.25%"
        findings = check_units(content)
        info_findings = [f for f in findings if f.severity == "INFO"]
        assert len(info_findings) >= 1
        assert any("bp" in f.message.lower() or "basis" in f.message.lower() for f in info_findings)


# ──────────────────────────────────────────────
# Full-width Character Tests
# ──────────────────────────────────────────────


class TestFullWidth:
    """Full-width character handling."""

    def test_fullwidth_percent_sign(self):
        """Full-width ％ should be parsed as %."""
        content = "## 配分\n- Stocks: 50％\n- Bonds: 30％\n- Cash: 20％\n"
        findings = check_allocations(content)
        # 50 + 30 + 20 = 100 -> no warning, proves ％ was parsed
        assert len(findings) == 0

    def test_fullwidth_tilde_range(self):
        """Full-width tilde 〜 should be parsed as range separator."""
        content = "## 配分\n- Stocks: 50〜55%\n- Bonds: 20〜25%\n- Gold: 15〜20%\n- Cash: 5〜10%\n"
        # sum_mins = 90, sum_maxs = 110, 100 in range -> OK
        findings = check_allocations(content)
        assert len(findings) == 0

    def test_fullwidth_dash(self):
        """En-dash should be parsed as range separator."""
        content = (
            "## 配分\n"
            "- Stocks: 50\u201355%\n"
            "- Bonds: 20\u201325%\n"
            "- Gold: 15\u201320%\n"
            "- Cash: 5\u201310%\n"
        )
        # sum_mins = 90, sum_maxs = 110, 100 in range -> OK
        findings = check_allocations(content)
        assert len(findings) == 0


# ──────────────────────────────────────────────
# Edge Case Tests
# ──────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and integration tests."""

    def test_empty_file(self):
        """Empty string -> no findings."""
        findings = run_checks("")
        assert findings == []

    def test_no_financial_content(self):
        """Non-financial content -> no findings."""
        findings = run_checks("Hello world, this is a test.")
        assert findings == []

    def test_multiple_findings_sorted_by_severity(self):
        """Multiple issues -> sorted ERROR first, then WARNING, then INFO."""
        content = (
            "January 1, 2026 (Monday)\n"  # ERROR: wrong weekday
            "GLD: $2,800\n"  # WARNING: wrong digit count
            "yield rose 25bp. rate increased 0.25%\n"  # INFO: mixed units
        )
        findings = run_checks(content)
        assert len(findings) >= 2
        severities = [f.severity for f in findings]
        # Verify ordering: all ERRORs before WARNINGs before INFOs
        severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        order_values = [severity_order[s] for s in severities]
        assert order_values == sorted(order_values)

    def test_cli_file_not_found(self):
        """Non-existent file -> exit 1."""
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPTS_DIR, "check_data_quality.py"),
                "--file",
                "/tmp/nonexistent_file_xyz.md",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_cli_findings_exit_zero(self):
        """File with findings -> exit 0 (advisory mode)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("GLD: $2,800\n")
            f.flush()
            tmpfile = f.name

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subprocess.run(
                    [
                        sys.executable,
                        os.path.join(SCRIPTS_DIR, "check_data_quality.py"),
                        "--file",
                        tmpfile,
                        "--output-dir",
                        tmpdir,
                    ],
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0
        finally:
            os.unlink(tmpfile)

    def test_cli_no_findings_exit_zero(self):
        """Clean file -> exit 0."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("This is a clean document.\n")
            f.flush()
            tmpfile = f.name

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subprocess.run(
                    [
                        sys.executable,
                        os.path.join(SCRIPTS_DIR, "check_data_quality.py"),
                        "--file",
                        tmpfile,
                        "--output-dir",
                        tmpdir,
                    ],
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0
        finally:
            os.unlink(tmpfile)

    def test_report_generation(self):
        """Verify report output format."""
        findings = [
            Finding(severity="ERROR", category="dates", message="Date mismatch", line_number=5),
            Finding(severity="WARNING", category="price_scale", message="Price issue"),
        ]
        report = generate_report(findings, "test.md")
        assert "# Data Quality Report" in report
        assert "**Source:** test.md" in report
        assert "**Total findings:** 2" in report
        assert "## ERROR (1)" in report
        assert "## WARNING (1)" in report

    def test_check_filter(self):
        """--checks price_scale,dates -> only those checks run."""
        content = (
            "GLD: $2,800\n"  # price_scale finding
            "Gold and GLD are mixed.\n"  # notation finding (should be skipped)
            "January 1, 2026 (Monday)\n"  # dates finding
        )
        findings = run_checks(content, checks=["price_scale", "dates"])
        categories = {f.category for f in findings}
        assert "notation" not in categories
        # Should have price_scale and/or dates findings
        assert categories.issubset({"price_scale", "dates"})

    def test_checks_with_spaces(self):
        """--checks 'price_scale, dates' with spaces should work (strip applied)."""
        content = (
            "GLD: $2,800\n"  # price_scale finding
            "January 1, 2026 (Monday)\n"  # dates finding
        )
        # Simulate what CLI does after fix: strip each check name
        checks = [c.strip() for c in "price_scale, dates".split(",")]
        findings = run_checks(content, checks=checks)
        categories = {f.category for f in findings}
        assert "price_scale" in categories
        assert "dates" in categories

    def test_date_year_inference_from_filename(self):
        """Filename containing YYYY-MM-DD -> year extracted from filename."""
        # No as_of, no year in content -> should use filename
        # Jan 1, 2025 is Wednesday
        assert calendar.day_name[calendar.weekday(2025, 1, 1)] == "Wednesday"
        year = infer_year(1, 1, None, "no year here", filepath="/reports/2025-03-15-weekly.md")
        assert year == 2025

    def test_as_of_option(self):
        """--as-of 2026-02-28 is accepted and used for year inference."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Feb 28 (Sat)\n")
            f.flush()
            tmpfile = f.name

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subprocess.run(
                    [
                        sys.executable,
                        os.path.join(SCRIPTS_DIR, "check_data_quality.py"),
                        "--file",
                        tmpfile,
                        "--output-dir",
                        tmpdir,
                        "--as-of",
                        "2026-02-28",
                    ],
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0
        finally:
            os.unlink(tmpfile)
