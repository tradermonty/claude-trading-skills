"""Tests for position_sizer.py — Fixed Fractional, ATR-based, Kelly Criterion sizing."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from position_sizer import (
    SizingParameters,
    calculate_atr_based,
    calculate_fixed_fractional,
    calculate_kelly,
    calculate_position,
    generate_markdown_report,
    validate_parameters,
)

# ─── Test: Basic Fixed Fractional ────────────────────────────────────────────


class TestFixedFractional:
    def test_fixed_fractional_basic(self):
        """entry=155, stop=148.50, account=100k, risk=1% -> 153 shares."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
        )
        result = calculate_fixed_fractional(params)
        assert result["risk_per_share"] == 6.50
        assert result["dollar_risk"] == 1000.0
        assert result["shares"] == 153  # int(1000 / 6.50) = 153

    def test_fixed_fractional_penny_stock(self):
        """entry=0.85, stop=0.70, account=50k, risk=0.5% -> 1666 shares."""
        params = SizingParameters(
            account_size=50_000,
            entry_price=0.85,
            stop_price=0.70,
            risk_pct=0.5,
        )
        result = calculate_fixed_fractional(params)
        assert result["risk_per_share"] == 0.15
        assert result["shares"] == 1666  # int(250 / 0.15) = 1666

    def test_fixed_fractional_large_account(self):
        """entry=500, stop=475, account=1M, risk=2% -> 800 shares."""
        params = SizingParameters(
            account_size=1_000_000,
            entry_price=500.0,
            stop_price=475.0,
            risk_pct=2.0,
        )
        result = calculate_fixed_fractional(params)
        assert result["shares"] == 800  # int(20000 / 25) = 800


# ─── Test: ATR-based Sizing ──────────────────────────────────────────────────


class TestATRBased:
    def test_atr_based_sizing(self):
        """entry=155, atr=3.20, mult=2.0, account=100k, risk=1%."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            risk_pct=1.0,
            atr=3.20,
            atr_multiplier=2.0,
        )
        result = calculate_atr_based(params)
        assert result["stop_price"] == 148.60
        assert result["risk_per_share"] == 6.40
        assert result["shares"] == 156  # int(1000 / 6.40) = 156

    def test_atr_multiplier_variations(self):
        """1.5x, 2x, 3x multipliers produce different share counts."""
        base = dict(account_size=100_000, entry_price=155.0, risk_pct=1.0, atr=3.20)
        r15 = calculate_atr_based(SizingParameters(**base, atr_multiplier=1.5))
        r20 = calculate_atr_based(SizingParameters(**base, atr_multiplier=2.0))
        r30 = calculate_atr_based(SizingParameters(**base, atr_multiplier=3.0))
        # Wider stop -> fewer shares
        assert r15["shares"] > r20["shares"] > r30["shares"]

    def test_atr_stop_price_calculation(self):
        """stop_price = entry - (atr * atr_multiplier)."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=200.0,
            risk_pct=1.0,
            atr=5.0,
            atr_multiplier=2.5,
        )
        result = calculate_atr_based(params)
        assert result["stop_price"] == 187.50  # 200 - (5 * 2.5)


# ─── Test: Kelly Criterion ───────────────────────────────────────────────────


class TestKelly:
    def test_kelly_criterion(self):
        """win_rate=0.55, avg_win=2.5, avg_loss=1.0 -> 37% kelly, 18.5% half-kelly."""
        params = SizingParameters(
            account_size=100_000,
            win_rate=0.55,
            avg_win=2.5,
            avg_loss=1.0,
        )
        result = calculate_kelly(params)
        # K = W - (1-W)/R = 0.55 - 0.45/2.5 = 0.55 - 0.18 = 0.37 = 37%
        assert result["kelly_pct"] == 37.0
        assert result["half_kelly_pct"] == 18.5

    def test_half_kelly(self):
        """half_kelly = kelly_pct / 2."""
        params = SizingParameters(
            account_size=100_000,
            win_rate=0.60,
            avg_win=2.0,
            avg_loss=1.0,
        )
        result = calculate_kelly(params)
        assert result["half_kelly_pct"] == result["kelly_pct"] / 2

    def test_kelly_negative_expectancy(self):
        """win_rate=0.30, avg_win=1.0, avg_loss=1.5 -> kelly=0, recommended=0."""
        params = SizingParameters(
            account_size=100_000,
            win_rate=0.30,
            avg_win=1.0,
            avg_loss=1.5,
        )
        result = calculate_kelly(params)
        # K = 0.30 - 0.70 / (1.0/1.5) = 0.30 - 0.70/0.6667 = 0.30 - 1.05 = -0.75
        # Floored to 0
        assert result["kelly_pct"] == 0.0
        assert result["half_kelly_pct"] == 0.0

    def test_kelly_budget_mode_no_entry(self):
        """Kelly without --entry -> budget mode, no shares in output."""
        params = SizingParameters(
            account_size=100_000,
            win_rate=0.55,
            avg_win=2.5,
            avg_loss=1.0,
        )
        result = calculate_position(params)
        assert result["mode"] == "budget"
        assert "final_recommended_shares" not in result
        assert "recommended_risk_budget" in result

    def test_kelly_shares_mode_with_entry(self):
        """Kelly with --entry and --stop -> shares mode."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            win_rate=0.55,
            avg_win=2.5,
            avg_loss=1.0,
        )
        result = calculate_position(params)
        assert result["mode"] == "shares"
        assert "final_recommended_shares" in result

    def test_kelly_shares_no_stop_risk_note(self):
        """Kelly with --entry but no --stop -> risk_dollars=None, risk_note present."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            win_rate=0.55,
            avg_win=2.5,
            avg_loss=1.0,
        )
        result = calculate_position(params)
        assert result["mode"] == "shares"
        assert result["final_recommended_shares"] > 0
        assert result["final_risk_dollars"] is None
        assert result["final_risk_pct"] is None
        assert "risk_note" in result


# ─── Test: Constraints & Final Recommendation ────────────────────────────────


class TestConstraints:
    def test_final_shares_no_constraints(self):
        """No constraints -> risk-calculated shares unchanged."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
        )
        result = calculate_position(params)
        # 153 shares from fixed fractional, no constraints
        assert result["final_recommended_shares"] == 153

    def test_final_shares_position_limit(self):
        """max_position_pct=10 -> max 64 shares at entry=155."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
            max_position_pct=10.0,
        )
        result = calculate_position(params)
        # Max position: 100000 * 10% / 155 = 64 shares
        assert result["final_recommended_shares"] == 64

    def test_final_shares_sector_limit(self):
        """max_sector_pct=30, current=22 -> max 51 shares."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
            max_sector_pct=30.0,
            current_sector_exposure=22.0,
        )
        result = calculate_position(params)
        # Remaining: (30 - 22)% * 100000 / 155 = 8000 / 155 = 51
        assert result["final_recommended_shares"] == 51

    def test_final_shares_multiple_constraints(self):
        """Multiple constraints -> strictest wins (minimum)."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
            max_position_pct=10.0,
            max_sector_pct=30.0,
            current_sector_exposure=22.0,
        )
        result = calculate_position(params)
        # Position limit: 64, sector limit: 51 -> min = 51
        assert result["final_recommended_shares"] == 51

    def test_binding_constraint_identification(self):
        """Verify binding_constraint field shows the tightest constraint."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
            max_position_pct=10.0,
            max_sector_pct=30.0,
            current_sector_exposure=22.0,
        )
        result = calculate_position(params)
        assert result["binding_constraint"] == "max_sector_pct"


# ─── Test: Fractional Shares ─────────────────────────────────────────────────


class TestFractionalShares:
    def test_fractional_exact_precision_boundary_is_preserved(self):
        """Binary float noise must not floor an exact decimal boundary twice."""
        params = SizingParameters(
            account_size=1_150,
            entry_price=100.0,
            stop_price=90.0,
            risk_pct=1.0,
            fractional_shares=True,
            share_precision=2,
        )
        result = calculate_position(params)
        assert result["calculations"]["fixed_fractional"]["shares"] == 1.15
        assert result["final_recommended_shares"] == 1.15
        assert result["final_risk_dollars"] == 11.5

    def test_fractional_decimal_inputs_are_used_before_subtraction(self):
        """Entry-stop subtraction must not pollute an exact share boundary."""
        params = SizingParameters(
            account_size=18.81,
            entry_price=10.0,
            stop_price=9.01,
            risk_pct=1.0,
            fractional_shares=True,
            share_precision=2,
        )
        result = calculate_position(params)
        assert result["calculations"]["fixed_fractional"]["shares"] == 0.19
        assert result["final_recommended_shares"] == 0.19
        assert result["final_risk_dollars"] == 0.19

    def test_fractional_fixed_fractional_floors_to_precision(self):
        """--fractional supports small-account sizing without exceeding risk."""
        params = SizingParameters(
            account_size=1_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
            fractional_shares=True,
            share_precision=4,
        )
        result = calculate_position(params)
        assert result["calculations"]["fixed_fractional"]["shares"] == 1.5384
        assert result["final_recommended_shares"] == 1.5384
        assert result["final_risk_dollars"] == 10.0
        assert result["final_risk_pct"] == 1.0
        assert result["parameters"]["fractional_shares"] is True
        assert result["parameters"]["share_precision"] == 4

    def test_fractional_atr_based_floors_to_precision(self):
        """ATR mode uses the same fractional flooring logic."""
        params = SizingParameters(
            account_size=1_000,
            entry_price=100.0,
            risk_pct=1.0,
            atr=3.0,
            atr_multiplier=2.0,
            fractional_shares=True,
            share_precision=4,
        )
        result = calculate_position(params)
        assert result["calculations"]["atr_based"]["shares"] == 1.6666
        assert result["final_recommended_shares"] == 1.6666
        assert result["final_risk_dollars"] == 10.0

    def test_fractional_kelly_shares_with_stop(self):
        """Kelly shares mode supports fractional output when a stop is provided."""
        params = SizingParameters(
            account_size=100,
            entry_price=155.0,
            stop_price=148.50,
            win_rate=0.55,
            avg_win=2.5,
            avg_loss=1.0,
            fractional_shares=True,
            share_precision=4,
        )
        result = calculate_position(params)
        assert result["calculations"]["kelly"]["half_kelly_pct"] == 18.5
        assert result["final_recommended_shares"] == 2.8461
        assert result["final_risk_dollars"] == 18.5

    def test_fractional_max_position_constraint(self):
        """Max-position constraints floor fractional shares before binding."""
        params = SizingParameters(
            account_size=1_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
            max_position_pct=10.0,
            fractional_shares=True,
            share_precision=4,
        )
        result = calculate_position(params)
        assert result["final_recommended_shares"] == 0.6451
        assert result["final_position_value"] == 99.99
        assert result["binding_constraint"] == "max_position_pct"
        assert result["final_position_value"] <= 100.0

    def test_fractional_max_sector_constraint(self):
        """Max-sector constraints floor fractional shares before binding."""
        params = SizingParameters(
            account_size=1_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
            max_sector_pct=30.0,
            current_sector_exposure=22.0,
            fractional_shares=True,
            share_precision=4,
        )
        result = calculate_position(params)
        assert result["final_recommended_shares"] == 0.5161
        assert result["final_position_value"] == 80.0
        assert result["binding_constraint"] == "max_sector_pct"
        assert result["final_position_value"] <= 80.0


# ─── Test: Input Validation ──────────────────────────────────────────────────


class TestValidation:
    def test_stop_above_entry_error(self):
        """stop > entry -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=160.0,
            risk_pct=1.0,
        )
        with pytest.raises(ValueError, match="stop_price must be below entry_price"):
            validate_parameters(params)

    def test_zero_risk_error(self):
        """risk_pct=0 -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=150.0,
            risk_pct=0.0,
        )
        with pytest.raises(ValueError, match="risk_pct must be positive"):
            validate_parameters(params)

    def test_negative_risk_error(self):
        """risk_pct=-1 -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=150.0,
            risk_pct=-1.0,
        )
        with pytest.raises(ValueError, match="risk_pct must be positive"):
            validate_parameters(params)

    def test_win_rate_over_one_error(self):
        """win_rate=1.5 -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            win_rate=1.5,
            avg_win=2.0,
            avg_loss=1.0,
        )
        with pytest.raises(ValueError, match="win_rate must be between"):
            validate_parameters(params)

    def test_avg_win_zero_error(self):
        """avg_win=0 -> ValueError (would cause ZeroDivisionError in Kelly)."""
        params = SizingParameters(
            account_size=100_000,
            win_rate=0.55,
            avg_win=0.0,
            avg_loss=1.0,
        )
        with pytest.raises(ValueError, match="avg_win must be positive"):
            validate_parameters(params)

    def test_avg_loss_zero_error(self):
        """avg_loss=0 -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            win_rate=0.55,
            avg_win=2.0,
            avg_loss=0.0,
        )
        with pytest.raises(ValueError, match="avg_loss must be positive"):
            validate_parameters(params)

    def test_account_size_zero_error(self):
        """account_size=0 -> ValueError."""
        params = SizingParameters(
            account_size=0,
            entry_price=155.0,
            stop_price=150.0,
            risk_pct=1.0,
        )
        with pytest.raises(ValueError, match="account_size must be positive"):
            validate_parameters(params)

    def test_atr_negative_error(self):
        """atr=-1 -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            risk_pct=1.0,
            atr=-1.0,
        )
        with pytest.raises(ValueError, match="atr must be positive"):
            validate_parameters(params)

    def test_entry_zero_error(self):
        """entry=0 -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=0.0,
            stop_price=-1.0,
            risk_pct=1.0,
        )
        with pytest.raises(ValueError, match="entry_price must be positive"):
            validate_parameters(params)

    def test_share_precision_below_zero_error(self):
        """share_precision below zero -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=150.0,
            risk_pct=1.0,
            fractional_shares=True,
            share_precision=-1,
        )
        with pytest.raises(ValueError, match="share_precision must be between 0 and 8"):
            validate_parameters(params)

    def test_share_precision_above_eight_error(self):
        """share_precision above eight -> ValueError."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=150.0,
            risk_pct=1.0,
            fractional_shares=True,
            share_precision=9,
        )
        with pytest.raises(ValueError, match="share_precision must be between 0 and 8"):
            validate_parameters(params)

    def test_risk_pct_and_kelly_mutual_exclusive(self):
        """Both risk_pct and win_rate via CLI -> SystemExit (argparse error)."""
        script = "skills/position-sizer/scripts/position_sizer.py"
        result = subprocess.run(
            [
                sys.executable,
                script,
                "--account-size",
                "100000",
                "--entry",
                "155",
                "--stop",
                "150",
                "--risk-pct",
                "1.0",
                "--win-rate",
                "0.55",
                "--avg-win",
                "2.5",
                "--avg-loss",
                "1.0",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[4]),
        )
        assert result.returncode != 0


# ─── Test: Output ─────────────────────────────────────────────────────────────


class TestOutput:
    def test_report_generation_json(self):
        """Verify JSON has required keys."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
        )
        result = calculate_position(params)
        assert "schema_version" in result
        assert "mode" in result
        assert "parameters" in result
        assert "calculations" in result
        assert "final_recommended_shares" in result
        # Verify JSON-serializable
        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        assert parsed["schema_version"] == "1.0"

    def test_report_generation_markdown(self):
        """Verify markdown report is generated with key sections."""
        params = SizingParameters(
            account_size=100_000,
            entry_price=155.0,
            stop_price=148.50,
            risk_pct=1.0,
        )
        result = calculate_position(params)
        md = generate_markdown_report(result)
        assert "# Position Sizing Report" in md
        assert "## Parameters" in md
        assert "## Final Recommendation" in md
        assert "153" in md  # final shares

    def test_cli_arguments(self):
        """Verify argparse works for standard cases."""
        script = "skills/position-sizer/scripts/position_sizer.py"
        result = subprocess.run(
            [
                sys.executable,
                script,
                "--account-size",
                "100000",
                "--entry",
                "155",
                "--stop",
                "148.50",
                "--risk-pct",
                "1.0",
                "--output-dir",
                "/tmp/position_sizer_test",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[4]),
        )
        assert result.returncode == 0
        assert "153 shares" in result.stdout

    def test_cli_fractional_arguments(self):
        """Verify CLI supports fractional share output."""
        script = "skills/position-sizer/scripts/position_sizer.py"
        result = subprocess.run(
            [
                sys.executable,
                script,
                "--account-size",
                "1000",
                "--entry",
                "155",
                "--stop",
                "148.50",
                "--risk-pct",
                "1.0",
                "--fractional",
                "--share-precision",
                "4",
                "--output-dir",
                "/tmp/position_sizer_test",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[4]),
        )
        assert result.returncode == 0
        assert "1.5384 shares" in result.stdout

    def test_cli_missing_required(self):
        """Missing --account-size -> SystemExit."""
        script = "skills/position-sizer/scripts/position_sizer.py"
        result = subprocess.run(
            [
                sys.executable,
                script,
                "--entry",
                "155",
                "--stop",
                "150",
                "--risk-pct",
                "1.0",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[4]),
        )
        assert result.returncode != 0
