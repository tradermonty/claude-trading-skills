"""Tests for the weekly-performance-digest generator.

Fixtures are schema-faithful: every thesis built here is validated against the real
trader-memory-core validator (``thesis_store._validate_thesis``) so the consumer is
tested against the genuine producer contract, not a fabricated shape.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import generate_weekly_digest as gwd
import pytest
import yaml

# --------------------------------------------------------------------------- #
# Real TMC validator (the exact validator the producer runs on every write)
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[4]
_TMC_STORE = _REPO_ROOT / "skills" / "trader-memory-core" / "scripts" / "thesis_store.py"


def _load_tmc_validator():
    if not _TMC_STORE.exists():  # pragma: no cover - depends on checkout
        return None
    spec = importlib.util.spec_from_file_location("tmc_thesis_store", _TMC_STORE)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - missing optional deps
        return None
    return getattr(module, "_validate_thesis", None)


_TMC_VALIDATE = _load_tmc_validator()


# --------------------------------------------------------------------------- #
# Schema-faithful thesis builder
# --------------------------------------------------------------------------- #
def make_thesis(**overrides) -> dict:
    """Build a minimal schema-valid CLOSED thesis; override any nested block."""
    thesis = {
        "thesis_id": "th_AAPL_div_20260613_a1b2",
        "ticker": "AAPL",
        "created_at": "2026-06-01T09:00:00+00:00",
        "updated_at": "2026-06-13T16:00:00+00:00",
        "thesis_type": "dividend_income",
        "status": "CLOSED",
        "status_history": [
            {"status": "IDEA", "at": "2026-06-01T09:00:00+00:00", "reason": "screened"},
            {"status": "CLOSED", "at": "2026-06-13T16:00:00+00:00", "reason": "target"},
        ],
        "thesis_statement": "Quality dividend payer at a 5y-high yield.",
        "mechanism_tag": "structure",
        "entry": {"actual_price": 150.0, "actual_date": "2026-06-04T09:00:00+00:00"},
        "exit": {
            "stop_loss": 140.0,
            "actual_price": 160.0,
            "actual_date": "2026-06-13T16:00:00+00:00",
            "exit_reason": "target_hit",
        },
        "position": {"shares": 10.0},
        "market_context": {"sector": "Technology"},
        "origin": {
            "skill": "kanchi-dividend-sop",
            "output_file": "reports/kanchi.json",
            "screening_grade": "A",
        },
        "outcome": {
            "pnl_dollars": 100.0,
            "pnl_pct": 6.67,
            "holding_days": 9,
            "mae_pct": -2.5,
            "mfe_pct": 8.0,
            "lessons_learned": "Held through the pullback; thesis intact.",
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(thesis.get(key), dict):
            merged = copy.deepcopy(thesis[key])
            merged.update(value)
            thesis[key] = merged
        else:
            thesis[key] = value
    return thesis


def _write_theses(state_dir: Path, theses: list[dict]) -> None:
    for i, thesis in enumerate(theses):
        path = state_dir / f"th_T{i:03d}_div_20260613_a1b2.yaml"
        path.write_text(yaml.dump(thesis, sort_keys=False), encoding="utf-8")


@pytest.fixture
def winner() -> dict:
    return make_thesis()


@pytest.fixture
def loser() -> dict:
    return make_thesis(
        thesis_id="th_MSFT_grw_20260612_b2c3",
        ticker="MSFT",
        thesis_type="growth_momentum",
        mechanism_tag="behavior",
        entry={"actual_price": 200.0, "actual_date": "2026-06-06T09:00:00+00:00"},
        exit={
            "stop_loss": 190.0,
            "actual_price": 195.0,
            "actual_date": "2026-06-12T16:00:00+00:00",
            "exit_reason": "stop_hit",
        },
        market_context={"sector": "Technology"},
        origin={
            "skill": "vcp-screener",
            "output_file": "reports/vcp.json",
            "screening_grade": "B",
        },
        outcome={
            "pnl_dollars": -50.0,
            "pnl_pct": -2.5,
            "holding_days": 6,
            "mae_pct": -5.0,
            "mfe_pct": 1.0,
            "lessons_learned": "Stopped out; entry too extended.",
        },
    )


@pytest.fixture
def breakeven() -> dict:
    return make_thesis(
        thesis_id="th_GOOG_mvr_20260611_c3d4",
        ticker="GOOG",
        thesis_type="mean_reversion",
        outcome={
            "pnl_dollars": 0.0,
            "pnl_pct": 0.0,
            "holding_days": 4,
            "mae_pct": -1.0,
            "mfe_pct": 1.0,
            "lessons_learned": "Flat exit.",
        },
    )


# --------------------------------------------------------------------------- #
# Fixtures are genuinely schema-valid
# --------------------------------------------------------------------------- #
class TestFixturesAreSchemaValid:
    @pytest.mark.skipif(_TMC_VALIDATE is None, reason="TMC validator unavailable")
    def test_winner_loser_breakeven_validate(self, winner, loser, breakeven):
        for thesis in (winner, loser, breakeven):
            _TMC_VALIDATE(thesis)  # raises on invalid


# --------------------------------------------------------------------------- #
# Per-thesis calcs (incl. the three corrected field paths)
# --------------------------------------------------------------------------- #
class TestCalculatePnl:
    def test_valid_pnl(self, winner):
        assert gwd.calculate_pnl(winner) == (100.0, 6.67)

    def test_missing_outcome(self):
        assert gwd.calculate_pnl({"ticker": "X"}) == (None, None)

    def test_partial_outcome(self):
        assert gwd.calculate_pnl({"outcome": {"pnl_dollars": 12.0}}) == (12.0, None)


class TestCalculateHoldingDays:
    def test_from_outcome(self, winner):
        assert gwd.calculate_holding_days(winner) == 9

    def test_calculated_from_actual_dates(self, winner):
        # Corrected path: entry.actual_date (NOT entry.entry_date).
        t = make_thesis(outcome={"pnl_dollars": 1.0})  # drop holding_days
        t["outcome"].pop("holding_days", None)
        assert gwd.calculate_holding_days(t) == 9  # 2026-06-04 -> 2026-06-13

    def test_missing_dates(self):
        assert gwd.calculate_holding_days({"outcome": {}}) is None


class TestCalculateRMultiple:
    def test_uses_exit_stop_loss(self, winner):
        # Corrected path: exit.stop_loss. risk=(150-140)*10=100, pnl=100 -> R=1.0
        assert gwd.calculate_r_multiple(winner) == 1.0

    def test_losing_trade(self, loser):
        # risk=(200-190)*10=100, pnl=-50 -> R=-0.5
        assert gwd.calculate_r_multiple(loser) == -0.5

    def test_missing_stop_loss(self):
        t = make_thesis()
        t["exit"].pop("stop_loss")
        assert gwd.calculate_r_multiple(t) is None

    def test_entry_stop_loss_is_ignored(self):
        # The lost .pyc read entry.stop_loss; the real schema has no such field.
        # Putting a stop only under entry must yield None (proves the bug is fixed).
        t = make_thesis()
        t["exit"].pop("stop_loss")
        t["entry"]["stop_loss"] = 140.0
        assert gwd.calculate_r_multiple(t) is None


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
class TestCalculateMetrics:
    def test_mixed_trades(self, winner, loser, breakeven):
        out = gwd.calculate_metrics([winner, loser, breakeven])
        s, m = out["summary"], out["metrics"]
        assert s["total_trades"] == 3
        assert s["winners"] == 1 and s["losers"] == 1 and s["breakeven"] == 1
        assert s["win_rate"] == round(1 / 3, 4)
        assert s["total_realized_pnl"] == 50.0
        assert s["profit_factor"] == 2.0  # 100 / 50
        assert m["largest_winner"] == 100.0 and m["largest_loser"] == -50.0
        assert m["avg_mae_pct"] == round((-2.5 - 5.0 - 1.0) / 3, 4)
        assert m["avg_mfe_pct"] == round((8.0 + 1.0 + 1.0) / 3, 4)

    def test_empty_trades(self):
        out = gwd.calculate_metrics([])
        assert out["summary"]["total_trades"] == 0
        assert out["summary"]["profit_factor"] is None
        assert out["metrics"]["r_multiple_avg"] is None

    def test_all_winners_profit_factor_none(self, winner):
        out = gwd.calculate_metrics([winner, make_thesis(outcome={"pnl_dollars": 20.0})])
        assert out["summary"]["losers"] == 0
        assert out["summary"]["profit_factor"] is None

    def test_mae_mfe_sign_normalized(self):
        # MAE must be <= 0, MFE must be >= 0. TMC does not clamp, so an
        # out-of-convention mae_pct > 0 / mfe_pct < 0 must be clamped to 0 on read.
        t = make_thesis(outcome={"pnl_dollars": 10.0, "mae_pct": 2.0, "mfe_pct": -3.0})
        out = gwd.calculate_metrics([t])
        assert out["metrics"]["avg_mae_pct"] == 0.0
        assert out["metrics"]["avg_mfe_pct"] == 0.0

    def test_mae_mfe_within_convention_unchanged(self, winner, loser):
        # In-convention values (mae<=0, mfe>=0) pass through to the average.
        out = gwd.calculate_metrics([winner, loser])
        assert out["metrics"]["avg_mae_pct"] == round((-2.5 - 5.0) / 2, 4)
        assert out["metrics"]["avg_mfe_pct"] == round((8.0 + 1.0) / 2, 4)


class TestAnalyzePatterns:
    def test_dimensions(self, winner, loser, breakeven):
        out = gwd.analyze_patterns([winner, loser, breakeven])
        assert set(out) == {
            "by_source_skill",
            "by_exit_reason",
            "by_thesis_type",
            "by_sector",
            "by_mechanism_tag",
            "by_screening_grade",
        }
        assert out["by_source_skill"]["vcp-screener"]["losses"] == 1
        assert out["by_exit_reason"]["target_hit"]["wins"] == 1
        assert out["by_mechanism_tag"]["behavior"]["losses"] == 1
        assert out["by_screening_grade"]["A"]["wins"] == 1

    def test_unknown_bucket(self):
        t = make_thesis(market_context={"sector": None})
        out = gwd.analyze_patterns([t])
        assert "unknown" in out["by_sector"]

    def test_empty(self):
        out = gwd.analyze_patterns([])
        assert out["by_source_skill"] == {}


class TestExtractLessons:
    def test_top_trades(self, winner, loser, breakeven):
        out = gwd.extract_lessons([winner, loser, breakeven], top_n=2)
        assert out["top_wins"][0]["ticker"] == "AAPL"
        assert out["top_wins"][0]["lessons_learned"]  # outcome.lessons_learned surfaced
        assert out["top_losses"][0]["ticker"] == "MSFT"

    def test_empty(self):
        out = gwd.extract_lessons([])
        assert out["top_wins"] == [] and out["top_losses"] == []


class TestGatherClosedTheses:
    def test_within_range(self, tmp_path, winner, loser):
        _write_theses(tmp_path, [winner, loser])
        got = gwd.gather_closed_theses(tmp_path, "2026-06-01", "2026-06-15")
        assert len(got) == 2

    def test_excludes_out_of_range(self, tmp_path, winner):
        _write_theses(tmp_path, [winner])
        got = gwd.gather_closed_theses(tmp_path, "2026-07-01", "2026-07-15")
        assert got == []

    def test_excludes_non_closed(self, tmp_path):
        t = make_thesis(status="ACTIVE")
        _write_theses(tmp_path, [t])
        assert gwd.gather_closed_theses(tmp_path, "2026-06-01", "2026-06-15") == []


class TestGatherPartialTrims:
    def test_partially_closed_only(self, tmp_path):
        partial = make_thesis(
            thesis_id="th_NVDA_grw_20260610_d4e5",
            ticker="NVDA",
            status="PARTIALLY_CLOSED",
            status_history=[
                {"status": "ACTIVE", "at": "2026-06-05T09:00:00+00:00", "reason": "open"},
                {
                    "status": "PARTIALLY_CLOSED",
                    "at": "2026-06-10T15:00:00+00:00",
                    "reason": "trim",
                    "shares_sold": 4.0,
                    "price": 120.0,
                    "realized_pnl": 80.0,
                },
            ],
        )
        _write_theses(tmp_path, [partial])
        trims = gwd.gather_partial_trims(tmp_path, "2026-06-08", "2026-06-14")
        assert len(trims) == 1 and trims[0]["realized_pnl"] == 80.0

    def test_closed_trims_excluded_no_double_count(self, tmp_path, winner):
        # CLOSED thesis with a trim in status_history must NOT appear in partial_trims.
        winner["status_history"].insert(
            1,
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-06-09T15:00:00+00:00",
                "reason": "trim",
                "shares_sold": 5.0,
                "price": 158.0,
                "realized_pnl": 40.0,
            },
        )
        _write_theses(tmp_path, [winner])
        assert gwd.gather_partial_trims(tmp_path, "2026-06-01", "2026-06-15") == []


class TestGenerateMarkdownReport:
    def test_sections(self, winner, loser):
        digest = gwd.calculate_metrics([winner, loser])
        full = {
            "generated_at": "2026-06-20T00:00:00Z",
            "summary": digest["summary"],
            "metrics": digest["metrics"],
            "pattern_analysis": gwd.analyze_patterns([winner, loser]),
            "lessons": gwd.extract_lessons([winner, loser]),
            "partial_trims": {"count": 0, "total_realized_pnl": 0.0, "trims": []},
        }
        md = gwd.generate_markdown_report(full, "2026-06-13", "2026-06-20")
        for section in (
            "# Weekly Performance Digest",
            "## Executive Summary",
            "## Performance Metrics",
            "## Pattern Analysis",
            "## Lessons Learned",
            "### Top Winners",
            "### Top Losers",
            "### Process Improvements",
        ):
            assert section in md


class TestGenerateDigest:
    def test_full_digest(self, tmp_path, winner, loser, breakeven):
        state = tmp_path / "theses"
        state.mkdir()
        out = tmp_path / "reports"
        _write_theses(state, [winner, loser, breakeven])
        digest = gwd.generate_digest(state, "2026-06-01", "2026-06-15", out)
        assert digest["schema_version"] == "1.0"
        assert digest["report_type"] == "weekly_performance_digest"
        json_path = out / "weekly_digest_2026-06-15.json"
        md_path = out / "weekly_digest_2026-06-15.md"
        assert json_path.exists() and md_path.exists()
        loaded = json.loads(json_path.read_text())
        assert loaded["summary"]["total_trades"] == 3

    def test_empty_state_dir(self, tmp_path):
        state = tmp_path / "theses"
        state.mkdir()
        out = tmp_path / "reports"
        digest = gwd.generate_digest(state, "2026-06-01", "2026-06-15", out)
        assert digest["summary"]["total_trades"] == 0
        assert (out / "weekly_digest_2026-06-15.json").exists()


class TestMain:
    def test_missing_state_dir(self, tmp_path, capsys):
        rc = gwd.main(["--state-dir", str(tmp_path / "nope")])
        assert rc == 1

    def test_end_to_end(self, tmp_path, winner):
        state = tmp_path / "theses"
        state.mkdir()
        _write_theses(state, [winner])
        rc = gwd.main(
            [
                "--state-dir",
                str(state),
                "--from-date",
                "2026-06-01",
                "--to-date",
                "2026-06-15",
                "--output-dir",
                str(tmp_path / "reports"),
            ]
        )
        assert rc == 0
        assert (tmp_path / "reports" / "weekly_digest_2026-06-15.json").exists()
