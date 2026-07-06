"""Smoke test: drive the Phase 1 pipeline against a fixture, no FMP calls.

Verifies that ``run_dry_run`` + ``build_json_report`` + ``write_outputs``
produce a valid v1.0 JSON, that the parabolic XYZ fixture survives all
filters, and that the flat CALM fixture is rejected (insufficient ROC /
extension). Acts as the executable schema contract for downstream skills.
"""

import json
import logging
from pathlib import Path

# screen_parabolic.py is a CLI module; import works because conftest puts
# the scripts dir on sys.path.
import screen_parabolic  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "dry_run_minimal.json"


def _flnc_like_fixture(tmp_path, last_earnings_date: str = "2026-04-28"):
    """Clone the minimal fixture and inject earnings metadata for the
    parabolic XYZ symbol so it simulates an FLNC-like post-earnings move.

    ``last_earnings_date`` defaults to 2026-04-28 (Tuesday) → 2 trading
    days before the XYZ fixture's latest bar 2026-04-30 (Thursday).
    """
    fixture = json.loads(FIXTURE_PATH.read_text())
    for sym in fixture["symbols"]:
        if sym["ticker"] == "XYZ":
            sym["last_earnings_date"] = last_earnings_date
            sym["market_data_as_of"] = "2026-04-30"
            # Leave trading_days_since_earnings unset to exercise the
            # "compute from last_earnings_date" branch in run_dry_run.
            break
    out_path = tmp_path / "dry_run_with_earnings.json"
    out_path.write_text(json.dumps(fixture), encoding="utf-8")
    return out_path


def _upcoming_earnings_fixture(tmp_path, next_earnings_date: str):
    """Clone the minimal fixture and set the XYZ symbol's next earnings.

    Used to exercise the forward-looking blackout via
    ``--exclude-earnings-within-days``.
    """
    fixture = json.loads(FIXTURE_PATH.read_text())
    for sym in fixture["symbols"]:
        if sym["ticker"] == "XYZ":
            sym["next_earnings_date"] = next_earnings_date
            sym["market_data_as_of"] = "2026-04-30"
            break
    out_path = tmp_path / "dry_run_with_upcoming_earnings.json"
    out_path.write_text(json.dumps(fixture), encoding="utf-8")
    return out_path


def _make_args(**overrides):
    parser = screen_parabolic.build_arg_parser()
    args = parser.parse_args(
        [
            "--dry-run",
            "--fixture",
            str(FIXTURE_PATH),
            "--watch-min-grade",
            "D",
            "--min-roc-5d",
            "30",
            "--as-of",
            "2026-04-30",
        ]
    )
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


class TestDryRunPipeline:
    def test_xyz_survives_calm_rejected(self):
        args = _make_args()
        candidates = screen_parabolic.run_dry_run(str(FIXTURE_PATH), args)
        tickers = [c["ticker"] for c in candidates]
        assert "XYZ" in tickers
        assert "CALM" not in tickers

    def test_pipeline_writes_valid_v1_json(self, tmp_path):
        args = _make_args(output_dir=str(tmp_path), output_prefix="ps_smoke")
        candidates = screen_parabolic.run_dry_run(str(FIXTURE_PATH), args)
        report = screen_parabolic.build_json_report(
            candidates=candidates,
            mode=args.mode,
            universe=args.universe,
            as_of=args.as_of,
            data_source="fixture",
        )
        json_path, md_path = screen_parabolic.write_outputs(
            report, args.output_dir, args.output_prefix, args.as_of
        )
        # Verify JSON is well-formed and matches schema essentials
        loaded = json.loads(json_path.read_text())
        assert loaded["schema_version"] == "1.0"
        assert loaded["skill"] == "parabolic-short-trade-planner"
        assert loaded["phase"] == "screen"
        assert loaded["mode"] == "safe_largecap"
        assert loaded["data_source"] == "fixture"
        assert loaded["candidates_total"] == len(candidates)

        # Markdown must have header and the surviving ticker
        md = md_path.read_text()
        assert "Parabolic Short Watchlist" in md
        if candidates:
            assert candidates[0]["ticker"] in md


class TestRejectionLogging:
    """The smoke runbook's Tier 1 PASS criterion is "--verbose
    documents at least one rejection reason". Pin that contract: when
    a candidate fails a soft threshold, the screener emits a DEBUG
    line of the form "Rejected <T>: <reason> ..." which is visible
    under --verbose (which sets root level to DEBUG)."""

    def test_soft_threshold_rejection_logs_reason(self, caplog):
        # CALM is a flat fixture that fails min_roc_5d at the default
        # 30% threshold. Capturing at DEBUG simulates --verbose.
        args = _make_args()
        with caplog.at_level(logging.DEBUG, logger="parabolic_short.screen"):
            screen_parabolic.run_dry_run(str(FIXTURE_PATH), args)
        rejection_lines = [r.message for r in caplog.records if r.message.startswith("Rejected ")]
        # At least one ticker must have logged a rejection reason.
        assert rejection_lines, (
            "Expected at least one 'Rejected ...' DEBUG line — the smoke "
            "runbook's Tier 1 PASS criterion depends on this."
        )
        # Reason text should be human-readable (not just a code).
        assert any("threshold not met" in line for line in rejection_lines), (
            f"Expected a 'threshold not met' rejection reason; got {rejection_lines}"
        )


class TestRecentEarningsCatalystWarning:
    """When the fixture supplies a ``last_earnings_date`` within the
    catalyst window, the screener must emit the
    ``recent_earnings_catalyst`` warning. This is the FLNC-style
    post-earnings parabolic case that motivated the fix."""

    def test_warning_appears_for_recent_earnings(self, tmp_path):
        fixture = _flnc_like_fixture(tmp_path, last_earnings_date="2026-04-28")
        args = _make_args()
        candidates = screen_parabolic.run_dry_run(str(fixture), args)
        xyz = next(c for c in candidates if c["ticker"] == "XYZ")
        assert "recent_earnings_catalyst" in xyz["warnings"]
        assert xyz["last_earnings_date"] == "2026-04-28"
        # 2026-04-28 (Tue) → 2026-04-30 (Thu): Wed + Thu = 2 trading days.
        assert xyz["trading_days_since_earnings"] == 2
        # Forward-looking blackout fields are independent.
        assert xyz["earnings_within_2d"] is False
        assert xyz["earnings_in_blackout_window"] is False
        assert xyz["market_data_as_of"] == "2026-04-30"

    def test_warning_absent_outside_catalyst_window(self, tmp_path):
        # 2026-03-13 (Fri) is well beyond the default 10-trading-day window
        # from market_data_as_of 2026-04-30.
        fixture = _flnc_like_fixture(tmp_path, last_earnings_date="2026-03-13")
        args = _make_args()
        candidates = screen_parabolic.run_dry_run(str(fixture), args)
        xyz = next(c for c in candidates if c["ticker"] == "XYZ")
        assert "recent_earnings_catalyst" not in xyz["warnings"]

    def test_top_level_market_data_as_of_propagates(self, tmp_path):
        fixture = _flnc_like_fixture(tmp_path, last_earnings_date="2026-04-28")
        args = _make_args()
        candidates = screen_parabolic.run_dry_run(str(fixture), args)
        report = screen_parabolic.build_json_report(
            candidates=candidates,
            mode=args.mode,
            universe=args.universe,
            as_of=args.as_of,
            run_date=args.as_of,
            data_source="fixture",
        )
        # XYZ is the only surviving candidate, so the unique-date branch
        # should set top-level market_data_as_of without a mixed warning.
        assert report["market_data_as_of"] == "2026-04-30"
        assert "mixed_market_data_as_of" not in report["warnings"]
        assert report["as_of"] == report["run_date"] == "2026-04-30"


class TestExcludeEarningsWithinDaysOverride:
    """The CLI flag ``--exclude-earnings-within-days`` must propagate as
    an override into ``check_invalidation`` so the hard blackout uses
    the user-supplied threshold, not the mode default of 2 calendar days.
    """

    def test_default_threshold_excludes_within_2_calendar_days(self, tmp_path):
        # next_earnings_date is 1 calendar day after market_data_as_of
        # (2026-04-30 → 2026-05-01) — caught by the default blackout of 2.
        fixture = _upcoming_earnings_fixture(tmp_path, next_earnings_date="2026-05-01")
        args = _make_args()  # default --exclude-earnings-within-days 2
        candidates = screen_parabolic.run_dry_run(str(fixture), args)
        assert all(c["ticker"] != "XYZ" for c in candidates), (
            "XYZ should be hard-invalidated when next earnings is 1 day out"
        )

    def test_default_threshold_keeps_candidate_4_days_out(self, tmp_path):
        # 4 calendar days out — outside the default 2-day blackout.
        fixture = _upcoming_earnings_fixture(tmp_path, next_earnings_date="2026-05-04")
        args = _make_args()
        candidates = screen_parabolic.run_dry_run(str(fixture), args)
        assert any(c["ticker"] == "XYZ" for c in candidates)

    def test_widened_threshold_excludes_4_days_out(self, tmp_path):
        # Same fixture (4 calendar days out) but with --exclude-earnings-within-days 5.
        # Without the override plumbing, this widened threshold is silently
        # ignored and the candidate slips through.
        fixture = _upcoming_earnings_fixture(tmp_path, next_earnings_date="2026-05-04")
        args = _make_args(exclude_earnings_within_days=5)
        candidates = screen_parabolic.run_dry_run(str(fixture), args)
        assert all(c["ticker"] != "XYZ" for c in candidates), (
            "XYZ should be hard-invalidated when next earnings is 4 days out "
            "and --exclude-earnings-within-days=5"
        )


class TestMainCLI:
    def test_main_dry_run_returns_zero(self, tmp_path):
        rc = screen_parabolic.main(
            [
                "--dry-run",
                "--fixture",
                str(FIXTURE_PATH),
                "--output-dir",
                str(tmp_path),
                "--as-of",
                "2026-04-30",
                "--watch-min-grade",
                "D",
                "--min-roc-5d",
                "30",
            ]
        )
        assert rc == 0
        files = sorted(p.name for p in tmp_path.iterdir())
        assert any(f.endswith(".json") for f in files)
        assert any(f.endswith(".md") for f in files)
