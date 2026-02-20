"""Tests for evaluate_backtest.py — backtest quality evaluation tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 0. Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_win_rate_above_100(self, evaluator_module):
        """win_rate > 100 raises ValueError."""
        with pytest.raises(ValueError, match="win_rate"):
            evaluator_module.evaluate(
                total_trades=100, win_rate=110, avg_win_pct=2.0,
                avg_loss_pct=1.0, max_drawdown_pct=15, years_tested=5,
                num_parameters=3, slippage_tested=True,
            )

    def test_win_rate_negative(self, evaluator_module):
        """win_rate < 0 raises ValueError."""
        with pytest.raises(ValueError, match="win_rate"):
            evaluator_module.evaluate(
                total_trades=100, win_rate=-5, avg_win_pct=2.0,
                avg_loss_pct=1.0, max_drawdown_pct=15, years_tested=5,
                num_parameters=3, slippage_tested=True,
            )

    def test_negative_avg_win(self, evaluator_module):
        """Negative avg_win_pct raises ValueError."""
        with pytest.raises(ValueError, match="avg_win_pct"):
            evaluator_module.evaluate(
                total_trades=100, win_rate=60, avg_win_pct=-1.0,
                avg_loss_pct=1.0, max_drawdown_pct=15, years_tested=5,
                num_parameters=3, slippage_tested=True,
            )

    def test_negative_avg_loss(self, evaluator_module):
        """Negative avg_loss_pct raises ValueError."""
        with pytest.raises(ValueError, match="avg_loss_pct"):
            evaluator_module.evaluate(
                total_trades=100, win_rate=60, avg_win_pct=2.0,
                avg_loss_pct=-1.0, max_drawdown_pct=15, years_tested=5,
                num_parameters=3, slippage_tested=True,
            )

    def test_negative_total_trades(self, evaluator_module):
        """Negative total_trades raises ValueError."""
        with pytest.raises(ValueError, match="total_trades"):
            evaluator_module.evaluate(
                total_trades=-10, win_rate=60, avg_win_pct=2.0,
                avg_loss_pct=1.0, max_drawdown_pct=15, years_tested=5,
                num_parameters=3, slippage_tested=True,
            )

    def test_negative_max_drawdown(self, evaluator_module):
        """Negative max_drawdown_pct raises ValueError."""
        with pytest.raises(ValueError, match="max_drawdown_pct"):
            evaluator_module.evaluate(
                total_trades=100, win_rate=60, avg_win_pct=2.0,
                avg_loss_pct=1.0, max_drawdown_pct=-5, years_tested=5,
                num_parameters=3, slippage_tested=True,
            )

    def test_negative_years_tested(self, evaluator_module):
        """Negative years_tested raises ValueError."""
        with pytest.raises(ValueError, match="years_tested"):
            evaluator_module.evaluate(
                total_trades=100, win_rate=60, avg_win_pct=2.0,
                avg_loss_pct=1.0, max_drawdown_pct=15, years_tested=-1,
                num_parameters=3, slippage_tested=True,
            )

    def test_negative_num_parameters(self, evaluator_module):
        """Negative num_parameters raises ValueError."""
        with pytest.raises(ValueError, match="num_parameters"):
            evaluator_module.evaluate(
                total_trades=100, win_rate=60, avg_win_pct=2.0,
                avg_loss_pct=1.0, max_drawdown_pct=15, years_tested=5,
                num_parameters=-2, slippage_tested=True,
            )

    def test_boundary_win_rate_zero(self, evaluator_module):
        """win_rate=0 is valid (all losses)."""
        result = evaluator_module.evaluate(
            total_trades=100, win_rate=0, avg_win_pct=2.0,
            avg_loss_pct=1.0, max_drawdown_pct=15, years_tested=5,
            num_parameters=3, slippage_tested=True,
        )
        assert result["total_score"] >= 0

    def test_boundary_win_rate_100(self, evaluator_module):
        """win_rate=100 is valid (all wins)."""
        result = evaluator_module.evaluate(
            total_trades=100, win_rate=100, avg_win_pct=2.0,
            avg_loss_pct=1.0, max_drawdown_pct=15, years_tested=5,
            num_parameters=3, slippage_tested=True,
        )
        assert result["total_score"] >= 0


# ---------------------------------------------------------------------------
# 1. Sample Size scoring
# ---------------------------------------------------------------------------


class TestSampleSizeScoring:
    def test_below_minimum(self, evaluator_module):
        """<30 trades -> 0 points."""
        assert evaluator_module.score_sample_size(20) == 0

    def test_at_minimum(self, evaluator_module):
        """30 trades -> partial credit."""
        score = evaluator_module.score_sample_size(30)
        assert 0 < score < 15

    def test_good_sample(self, evaluator_module):
        """100 trades -> 15 points."""
        assert evaluator_module.score_sample_size(100) == 15

    def test_excellent_sample(self, evaluator_module):
        """200+ trades -> full 20 points."""
        assert evaluator_module.score_sample_size(200) == 20
        assert evaluator_module.score_sample_size(500) == 20


# ---------------------------------------------------------------------------
# 2. Expectancy calculation
# ---------------------------------------------------------------------------


class TestExpectancyCalculation:
    def test_positive_expectancy(self, evaluator_module):
        """Positive expectancy -> positive score."""
        score = evaluator_module.score_expectancy(
            win_rate=60, avg_win_pct=2.0, avg_loss_pct=1.0
        )
        assert score > 0

    def test_negative_expectancy(self, evaluator_module):
        """Negative expectancy -> 0 points."""
        score = evaluator_module.score_expectancy(
            win_rate=30, avg_win_pct=1.0, avg_loss_pct=2.0
        )
        assert score == 0

    def test_zero_expectancy(self, evaluator_module):
        """Break-even -> 0 points."""
        # win_rate=50, avg_win=1, avg_loss=1 => expectancy = 0
        score = evaluator_module.score_expectancy(
            win_rate=50, avg_win_pct=1.0, avg_loss_pct=1.0
        )
        assert score == 0

    def test_high_expectancy_capped(self, evaluator_module):
        """Very high expectancy still capped at 20."""
        score = evaluator_module.score_expectancy(
            win_rate=90, avg_win_pct=5.0, avg_loss_pct=0.5
        )
        assert score == 20


# ---------------------------------------------------------------------------
# 3. Risk Management scoring
# ---------------------------------------------------------------------------


class TestRiskManagementScoring:
    def test_low_drawdown(self, evaluator_module):
        """<20% drawdown + high PF -> full points."""
        # PF = (0.75 * 2.0) / (0.25 * 1.0) = 6.0 (well above 3.0 threshold)
        score = evaluator_module.score_risk_management(
            max_drawdown_pct=10, win_rate=75, avg_win_pct=2.0, avg_loss_pct=1.0
        )
        assert score == 20

    def test_moderate_drawdown(self, evaluator_module):
        """30% drawdown -> partial points."""
        score = evaluator_module.score_risk_management(
            max_drawdown_pct=30, win_rate=60, avg_win_pct=2.0, avg_loss_pct=1.0
        )
        assert 0 < score < 20

    def test_extreme_drawdown(self, evaluator_module):
        """50%+ drawdown -> 0 points."""
        score = evaluator_module.score_risk_management(
            max_drawdown_pct=55, win_rate=60, avg_win_pct=2.0, avg_loss_pct=1.0
        )
        assert score == 0


# ---------------------------------------------------------------------------
# 4. Robustness scoring — years tested
# ---------------------------------------------------------------------------


class TestRobustnessYears:
    def test_short_period(self, evaluator_module):
        """<5 years -> 0 for years component."""
        score = evaluator_module.score_robustness(years_tested=3, num_parameters=3)
        assert score < 15  # years component is 0

    def test_minimum_years(self, evaluator_module):
        """5 years -> partial credit."""
        score = evaluator_module.score_robustness(years_tested=5, num_parameters=3)
        assert score > 0

    def test_long_period(self, evaluator_module):
        """10+ years -> full years component (15 pts)."""
        score = evaluator_module.score_robustness(years_tested=10, num_parameters=3)
        assert score >= 15


# ---------------------------------------------------------------------------
# 5. Robustness scoring — parameters
# ---------------------------------------------------------------------------


class TestRobustnessParameters:
    def test_few_parameters(self, evaluator_module):
        """3 parameters -> full parameter component (5 pts)."""
        score = evaluator_module.score_robustness(years_tested=10, num_parameters=3)
        assert score == 20  # 15 (years) + 5 (params)

    def test_moderate_parameters(self, evaluator_module):
        """5 parameters -> partial deduction."""
        score = evaluator_module.score_robustness(years_tested=10, num_parameters=5)
        assert 15 <= score < 20

    def test_many_parameters(self, evaluator_module):
        """8+ parameters -> heavy deduction."""
        score = evaluator_module.score_robustness(years_tested=10, num_parameters=8)
        assert score < 18


# ---------------------------------------------------------------------------
# 6. Slippage flag
# ---------------------------------------------------------------------------


class TestSlippageFlag:
    def test_slippage_tested(self, evaluator_module):
        """Slippage tested -> full 20 points."""
        score = evaluator_module.score_execution_realism(slippage_tested=True)
        assert score == 20

    def test_slippage_not_tested(self, evaluator_module):
        """Slippage not tested -> 0 points."""
        score = evaluator_module.score_execution_realism(slippage_tested=False)
        assert score == 0


# ---------------------------------------------------------------------------
# 7. Overall verdict
# ---------------------------------------------------------------------------


class TestOverallVerdict:
    def test_deploy_verdict(self, evaluator_module):
        """Score >= 70 -> Deploy."""
        assert evaluator_module.get_verdict(75) == "Deploy"
        assert evaluator_module.get_verdict(100) == "Deploy"

    def test_refine_verdict(self, evaluator_module):
        """40 <= score < 70 -> Refine."""
        assert evaluator_module.get_verdict(50) == "Refine"
        assert evaluator_module.get_verdict(69) == "Refine"

    def test_abandon_verdict(self, evaluator_module):
        """Score < 40 -> Abandon."""
        assert evaluator_module.get_verdict(30) == "Abandon"
        assert evaluator_module.get_verdict(0) == "Abandon"


# ---------------------------------------------------------------------------
# 8. Profit factor calculation
# ---------------------------------------------------------------------------


class TestProfitFactor:
    def test_positive_profit_factor(self, evaluator_module):
        """win_rate=60, avg_win=2, avg_loss=1 -> PF = 3.0."""
        pf = evaluator_module.calc_profit_factor(
            win_rate=60, avg_win_pct=2.0, avg_loss_pct=1.0
        )
        assert abs(pf - 3.0) < 0.01

    def test_breakeven_profit_factor(self, evaluator_module):
        """win_rate=50, avg_win=1, avg_loss=1 -> PF = 1.0."""
        pf = evaluator_module.calc_profit_factor(
            win_rate=50, avg_win_pct=1.0, avg_loss_pct=1.0
        )
        assert abs(pf - 1.0) < 0.01

    def test_zero_loss_profit_factor(self, evaluator_module):
        """100% win rate -> PF = inf (capped)."""
        pf = evaluator_module.calc_profit_factor(
            win_rate=100, avg_win_pct=2.0, avg_loss_pct=1.0
        )
        assert pf == float("inf")


# ---------------------------------------------------------------------------
# 8b. PF score boundary smoothness
# ---------------------------------------------------------------------------


class TestProfitFactorScoreSmoothness:
    def test_pf_boundary_no_large_jump(self, evaluator_module):
        """PF score should not jump more than 2 points at PF=2.0 boundary."""
        # Use drawdown <20% so dd_score is constant at 12
        score_below = evaluator_module.score_risk_management(
            max_drawdown_pct=10, win_rate=50, avg_win_pct=3.98, avg_loss_pct=2.0
        )  # PF ~= 1.99
        score_at = evaluator_module.score_risk_management(
            max_drawdown_pct=10, win_rate=50, avg_win_pct=4.0, avg_loss_pct=2.0
        )  # PF = 2.0
        # The jump should be at most 2 points (not the previous 4-point gap)
        assert abs(score_at - score_below) <= 2

    def test_pf_monotonically_increasing(self, evaluator_module):
        """Higher PF should give equal or higher risk management score."""
        # All with same low drawdown to isolate PF component
        scores = []
        for avg_win in [1.0, 1.5, 2.0, 3.0, 5.0]:
            s = evaluator_module.score_risk_management(
                max_drawdown_pct=10, win_rate=60, avg_win_pct=avg_win, avg_loss_pct=1.0
            )
            scores.append(s)
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], (
                f"Score decreased: PF step {i} gave {scores[i]} "
                f"but step {i + 1} gave {scores[i + 1]}"
            )


# ---------------------------------------------------------------------------
# 9. Output JSON structure
# ---------------------------------------------------------------------------


class TestOutputJsonStructure:
    def test_evaluate_returns_all_keys(self, evaluator_module):
        """evaluate() result must contain all required keys."""
        result = evaluator_module.evaluate(
            total_trades=150,
            win_rate=62,
            avg_win_pct=1.8,
            avg_loss_pct=1.2,
            max_drawdown_pct=15,
            years_tested=8,
            num_parameters=3,
            slippage_tested=True,
        )
        required_keys = {
            "total_score",
            "verdict",
            "dimensions",
            "red_flags",
            "profit_factor",
            "expectancy",
        }
        assert required_keys.issubset(result.keys())

    def test_dimensions_structure(self, evaluator_module):
        """Each dimension must have name, score, max_score."""
        result = evaluator_module.evaluate(
            total_trades=100,
            win_rate=55,
            avg_win_pct=1.5,
            avg_loss_pct=1.0,
            max_drawdown_pct=20,
            years_tested=5,
            num_parameters=4,
            slippage_tested=True,
        )
        for dim in result["dimensions"]:
            assert "name" in dim
            assert "score" in dim
            assert "max_score" in dim
            assert dim["max_score"] == 20

    def test_total_score_range(self, evaluator_module):
        """Total score must be 0-100."""
        result = evaluator_module.evaluate(
            total_trades=200,
            win_rate=65,
            avg_win_pct=2.5,
            avg_loss_pct=1.0,
            max_drawdown_pct=12,
            years_tested=10,
            num_parameters=3,
            slippage_tested=True,
        )
        assert 0 <= result["total_score"] <= 100


# ---------------------------------------------------------------------------
# 10. Red flags detection
# ---------------------------------------------------------------------------


class TestRedFlagsDetection:
    def test_small_sample_flag(self, evaluator_module):
        """<30 trades triggers red flag."""
        result = evaluator_module.evaluate(
            total_trades=20,
            win_rate=80,
            avg_win_pct=3.0,
            avg_loss_pct=1.0,
            max_drawdown_pct=10,
            years_tested=10,
            num_parameters=3,
            slippage_tested=True,
        )
        flags = [f["id"] for f in result["red_flags"]]
        assert "small_sample" in flags

    def test_no_slippage_flag(self, evaluator_module):
        """Slippage not tested triggers red flag."""
        result = evaluator_module.evaluate(
            total_trades=200,
            win_rate=60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            max_drawdown_pct=15,
            years_tested=10,
            num_parameters=3,
            slippage_tested=False,
        )
        flags = [f["id"] for f in result["red_flags"]]
        assert "no_slippage_test" in flags

    def test_excessive_drawdown_flag(self, evaluator_module):
        """>50% drawdown triggers red flag."""
        result = evaluator_module.evaluate(
            total_trades=200,
            win_rate=60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            max_drawdown_pct=55,
            years_tested=10,
            num_parameters=3,
            slippage_tested=True,
        )
        flags = [f["id"] for f in result["red_flags"]]
        assert "excessive_drawdown" in flags

    def test_over_optimized_flag_at_8(self, evaluator_module):
        """8 parameters triggers red flag."""
        result = evaluator_module.evaluate(
            total_trades=200,
            win_rate=60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            max_drawdown_pct=15,
            years_tested=10,
            num_parameters=8,
            slippage_tested=True,
        )
        flags = [f["id"] for f in result["red_flags"]]
        assert "over_optimized" in flags

    def test_over_optimized_flag_at_7(self, evaluator_module):
        """7 parameters also triggers red flag (already penalized in scoring)."""
        result = evaluator_module.evaluate(
            total_trades=200,
            win_rate=60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            max_drawdown_pct=15,
            years_tested=10,
            num_parameters=7,
            slippage_tested=True,
        )
        flags = [f["id"] for f in result["red_flags"]]
        assert "over_optimized" in flags

    def test_no_over_optimized_flag_at_6(self, evaluator_module):
        """6 parameters does NOT trigger over_optimized flag."""
        result = evaluator_module.evaluate(
            total_trades=200,
            win_rate=60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            max_drawdown_pct=15,
            years_tested=10,
            num_parameters=6,
            slippage_tested=True,
        )
        flags = [f["id"] for f in result["red_flags"]]
        assert "over_optimized" not in flags

    def test_short_test_period_flag(self, evaluator_module):
        """<5 years triggers red flag."""
        result = evaluator_module.evaluate(
            total_trades=200,
            win_rate=60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            max_drawdown_pct=15,
            years_tested=3,
            num_parameters=3,
            slippage_tested=True,
        )
        flags = [f["id"] for f in result["red_flags"]]
        assert "short_test_period" in flags

    def test_clean_backtest_no_flags(self, evaluator_module):
        """Well-constructed backtest has no red flags."""
        result = evaluator_module.evaluate(
            total_trades=200,
            win_rate=60,
            avg_win_pct=2.0,
            avg_loss_pct=1.0,
            max_drawdown_pct=15,
            years_tested=10,
            num_parameters=3,
            slippage_tested=True,
        )
        assert result["red_flags"] == []


# ---------------------------------------------------------------------------
# 11. File output (JSON + Markdown)
# ---------------------------------------------------------------------------


class TestFileOutput:
    def test_write_outputs(self, evaluator_module, tmp_path: Path):
        """write_outputs creates .json and .md files."""
        result = evaluator_module.evaluate(
            total_trades=150,
            win_rate=62,
            avg_win_pct=1.8,
            avg_loss_pct=1.2,
            max_drawdown_pct=15,
            years_tested=8,
            num_parameters=3,
            slippage_tested=True,
        )
        json_path, md_path = evaluator_module.write_outputs(result, tmp_path)

        assert json_path.exists()
        assert md_path.exists()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["total_score"] == result["total_score"]

        md_text = md_path.read_text(encoding="utf-8")
        assert "# Backtest Evaluation Report" in md_text
        assert result["verdict"] in md_text
