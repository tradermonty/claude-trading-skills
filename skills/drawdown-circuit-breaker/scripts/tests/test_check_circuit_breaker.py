"""Tests for check_circuit_breaker.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml
from check_circuit_breaker import (
    CircuitConfig,
    evaluate_circuit_breaker,
    load_theses,
    main,
    parse_as_of,
)


def load_thesis_store_module():
    module_path = (
        Path(__file__).resolve().parents[3] / "trader-memory-core" / "scripts" / "thesis_store.py"
    )
    spec = importlib.util.spec_from_file_location("thesis_store_for_circuit_tests", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def register_producer_thesis(state_dir: Path, *, ticker: str, source_date: str = "2026-07-01"):
    thesis_store = load_thesis_store_module()
    thesis_id = thesis_store.register(
        state_dir,
        {
            "ticker": ticker,
            "thesis_type": "growth_momentum",
            "thesis_statement": f"{ticker} producer-backed thesis",
            "origin": {
                "skill": "drawdown-circuit-breaker-test",
                "output_file": f"{ticker.lower()}-fixture.json",
            },
            "_source_date": source_date,
        },
    )
    return thesis_store, thesis_id


def write_thesis(
    state_dir: Path,
    thesis_id: str,
    *,
    ticker: str = "TEST",
    status: str = "CLOSED",
    history: list[dict] | None = None,
    pnl_dollars: float | None = None,
    exit_date: str | None = None,
) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    thesis = {
        "thesis_id": thesis_id,
        "ticker": ticker,
        "created_at": "2026-06-01T09:30:00-04:00",
        "updated_at": exit_date or "2026-07-02T16:00:00-04:00",
        "thesis_type": "growth_momentum",
        "status": status,
        "status_history": history or [],
        "thesis_statement": f"{ticker} test thesis",
        "origin": {"skill": "test", "output_file": "fixture.json"},
    }
    if pnl_dollars is not None:
        thesis["outcome"] = {"pnl_dollars": pnl_dollars, "pnl_pct": pnl_dollars / 1000}
    if exit_date is not None:
        thesis["exit"] = {"actual_date": exit_date, "actual_price": 100.0, "exit_reason": "manual"}

    path = state_dir / f"{thesis_id}.yaml"
    path.write_text(yaml.safe_dump(thesis, sort_keys=False))
    return path


def evaluate_state(
    state_dir: Path,
    *,
    as_of: str = "2026-07-02",
    account_size: float = 100_000,
    config: CircuitConfig | None = None,
) -> dict:
    theses, quality, warnings = load_theses(state_dir)
    return evaluate_circuit_breaker(
        theses,
        account_size,
        parse_as_of(as_of),
        config or CircuitConfig(),
        initial_quality=quality,
        initial_warnings=warnings,
    )


def test_empty_state_is_allowed_with_empty_state_quality(tmp_path: Path):
    result = evaluate_state(tmp_path / "missing")

    assert result["recommendation"] == "TRADING_ALLOWED"
    assert result["data_quality"] == "EMPTY_STATE"
    assert result["metrics"]["theses_scanned"] == 0


def test_realized_pnl_today_includes_partial_trim_and_daily_halt(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_trim_gm_20260702_0001",
        status="PARTIALLY_CLOSED",
        history=[
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T10:00:00-04:00",
                "reason": "trim",
                "realized_pnl": -1250.0,
            },
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T15:00:00-04:00",
                "reason": "trim",
                "realized_pnl": -750.0,
            },
        ],
    )

    result = evaluate_state(state_dir)

    assert result["metrics"]["realized_pnl_today"] == -2000.0
    assert result["recommendation"] == "HALTED"
    assert result["triggered_rules"][0]["rule"] == "max_daily_loss"
    assert result["triggered_rules"][0]["active_until"].startswith("2026-07-03T00:00:00")


def test_daily_loss_below_threshold_is_allowed(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_small_gm_20260702_0001",
        status="PARTIALLY_CLOSED",
        history=[
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T11:00:00-04:00",
                "reason": "trim",
                "realized_pnl": -1999.99,
            }
        ],
    )

    result = evaluate_state(state_dir)

    assert result["metrics"]["realized_pnl_today"] == -1999.99
    assert result["recommendation"] == "TRADING_ALLOWED"


def test_producer_trim_bare_date_counts_on_named_trading_date(tmp_path: Path):
    state_dir = tmp_path / "theses"
    thesis_store, thesis_id = register_producer_thesis(state_dir, ticker="PRODTRIM")

    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "transition",
                thesis_id,
                "ENTRY_READY",
                "--reason",
                "ready",
                "--event-date",
                "2026-07-01",
            ]
        )
        == 0
    )
    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "open-position",
                thesis_id,
                "--actual-price",
                "100",
                "--actual-date",
                "2026-07-01",
                "--shares",
                "100",
                "--event-date",
                "2026-07-01",
            ]
        )
        == 0
    )
    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "trim",
                thesis_id,
                "--shares-sold",
                "40",
                "--price",
                "0",
                "--date",
                "2026-07-02",
            ]
        )
        == 0
    )

    result = evaluate_state(state_dir, as_of="2026-07-02")

    assert result["metrics"]["realized_pnl_today"] == -4000.0
    assert result["recommendation"] == "HALTED"
    assert result["triggered_rules"][0]["rule"] == "max_daily_loss"


def test_realized_pnl_uses_eastern_date_boundaries(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_tz_gm_20260702_0001",
        status="PARTIALLY_CLOSED",
        history=[
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T00:30:00+00:00",
                "reason": "trim",
                "realized_pnl": -500.0,
            },
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T13:30:00+00:00",
                "reason": "trim",
                "realized_pnl": -250.0,
            },
        ],
    )

    result = evaluate_state(state_dir, as_of="2026-07-02T12:00:00-04:00")
    previous_day = evaluate_state(state_dir, as_of="2026-07-01T23:00:00-04:00")

    assert result["metrics"]["realized_pnl_today"] == -250.0
    assert previous_day["metrics"]["realized_pnl_today"] == -500.0


def test_future_events_after_as_of_time_are_excluded(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_future_gm_20260702_0001",
        status="PARTIALLY_CLOSED",
        history=[
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T11:00:00-04:00",
                "reason": "trim",
                "realized_pnl": -100.0,
            },
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T15:00:00-04:00",
                "reason": "trim",
                "realized_pnl": -5000.0,
            },
        ],
    )
    write_thesis(
        state_dir,
        "th_future_loss_gm_20260702_0002",
        ticker="FLOSS",
        pnl_dollars=-100.0,
        exit_date="2026-07-02T15:30:00-04:00",
    )

    noon_result = evaluate_state(state_dir, as_of="2026-07-02T12:00:00-04:00")
    end_of_day_result = evaluate_state(state_dir, as_of="2026-07-02")

    assert noon_result["metrics"]["realized_pnl_today"] == -100.0
    assert noon_result["metrics"]["consecutive_losses"] == 0
    assert noon_result["recommendation"] == "TRADING_ALLOWED"
    assert end_of_day_result["metrics"]["realized_pnl_today"] == -5200.0
    assert end_of_day_result["metrics"]["consecutive_losses"] == 1
    assert end_of_day_result["recommendation"] == "HALTED"


def test_malformed_yaml_sets_partial_quality_without_blocking(tmp_path: Path):
    state_dir = tmp_path / "theses"
    (state_dir).mkdir()
    (state_dir / "th_bad.yaml").write_text("status: [")
    write_thesis(
        state_dir,
        "th_good_gm_20260702_0001",
        status="PARTIALLY_CLOSED",
        history=[
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T11:00:00-04:00",
                "reason": "trim",
                "realized_pnl": 100.0,
            }
        ],
    )

    result = evaluate_state(state_dir)

    assert result["data_quality"] == "PARTIAL"
    assert result["recommendation"] == "TRADING_ALLOWED"
    assert result["metrics"]["theses_scanned"] == 1
    assert result["warnings"]


def test_losing_streak_triggers_cooldown(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_loss1_gm_20260701_0001",
        ticker="AAA",
        pnl_dollars=-100.0,
        exit_date="2026-07-01T10:00:00-04:00",
    )
    write_thesis(
        state_dir,
        "th_loss2_gm_20260701_0002",
        ticker="BBB",
        pnl_dollars=-150.0,
        exit_date="2026-07-01T15:30:00-04:00",
    )

    result = evaluate_state(state_dir, as_of="2026-07-02T10:00:00-04:00")

    assert result["recommendation"] == "COOLDOWN"
    assert result["metrics"]["consecutive_losses"] == 2
    assert result["triggered_rules"][0]["rule"] == "losing_streak_cooldown"
    assert result["triggered_rules"][0]["active_until"] == "2026-07-02T15:30:00-04:00"


def test_losing_streak_resets_on_break_even_and_expires_after_24h(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_loss1_gm_20260701_0001",
        ticker="AAA",
        pnl_dollars=-100.0,
        exit_date="2026-07-01T10:00:00-04:00",
    )
    write_thesis(
        state_dir,
        "th_flat_gm_20260701_0002",
        ticker="BBB",
        pnl_dollars=0.0,
        exit_date="2026-07-01T12:00:00-04:00",
    )
    write_thesis(
        state_dir,
        "th_loss2_gm_20260701_0003",
        ticker="CCC",
        pnl_dollars=-150.0,
        exit_date="2026-07-01T15:30:00-04:00",
    )

    reset_result = evaluate_state(state_dir, as_of="2026-07-02T10:00:00-04:00")

    assert reset_result["metrics"]["consecutive_losses"] == 1
    assert reset_result["recommendation"] == "TRADING_ALLOWED"

    write_thesis(
        state_dir,
        "th_loss3_gm_20260701_0004",
        ticker="DDD",
        pnl_dollars=-50.0,
        exit_date="2026-07-01T16:00:00-04:00",
    )
    expired_result = evaluate_state(state_dir, as_of="2026-07-02T16:00:00-04:00")

    assert expired_result["metrics"]["consecutive_losses"] == 2
    assert expired_result["recommendation"] == "TRADING_ALLOWED"


def test_losing_streak_terminal_ordering_uses_eastern_time(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_loss_utc_gm_20260702_0001",
        ticker="UTCLOSS",
        pnl_dollars=-100.0,
        exit_date="2026-07-02T00:30:00+00:00",
    )
    write_thesis(
        state_dir,
        "th_win_et_gm_20260701_0002",
        ticker="ETWIN",
        pnl_dollars=0.0,
        exit_date="2026-07-01T23:00:00-04:00",
    )
    write_thesis(
        state_dir,
        "th_loss_late_gm_20260702_0003",
        ticker="LATELOSS",
        pnl_dollars=-50.0,
        exit_date="2026-07-02T09:00:00-04:00",
    )

    result = evaluate_state(state_dir, as_of="2026-07-02T10:00:00-04:00")

    assert result["metrics"]["consecutive_losses"] == 1
    assert result["recommendation"] == "TRADING_ALLOWED"
    assert result["metrics"]["last_loss_exit_at"] == "2026-07-02T09:00:00-04:00"


def test_terminal_thesis_missing_pnl_sets_partial_quality(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_missing_outcome_gm_20260701_0001",
        ticker="MISS",
        exit_date="2026-07-01T10:00:00-04:00",
    )
    write_thesis(
        state_dir,
        "th_loss_gm_20260701_0002",
        ticker="LOSS",
        pnl_dollars=-100.0,
        exit_date="2026-07-01T15:30:00-04:00",
    )

    result = evaluate_state(state_dir, as_of="2026-07-02T10:00:00-04:00")

    assert result["data_quality"] == "PARTIAL"
    assert result["metrics"]["consecutive_losses"] == 1
    assert any("missing pnl_dollars" in warning for warning in result["warnings"])


def test_producer_legacy_close_outcome_falls_back_to_drawdown_metrics(tmp_path: Path):
    state_dir = tmp_path / "theses"
    thesis_store, thesis_id = register_producer_thesis(state_dir, ticker="LEGACY")

    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "transition",
                thesis_id,
                "ENTRY_READY",
                "--reason",
                "ready",
                "--event-date",
                "2026-07-01",
            ]
        )
        == 0
    )
    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "open-position",
                thesis_id,
                "--actual-price",
                "100",
                "--actual-date",
                "2026-07-01",
                "--event-date",
                "2026-07-01",
            ]
        )
        == 0
    )
    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "close",
                thesis_id,
                "--exit-reason",
                "manual",
                "--actual-price",
                "79.5",
                "--actual-date",
                "2026-07-02",
                "--event-date",
                "2026-07-02",
            ]
        )
        == 0
    )

    result = evaluate_state(state_dir, as_of="2026-07-02", account_size=1000)

    assert result["metrics"]["realized_pnl_today"] == -20.5
    assert result["recommendation"] == "HALTED"
    assert result["data_quality"] == "PARTIAL"
    assert any("Inferred missing realized_pnl" in warning for warning in result["warnings"])


def test_producer_legacy_invalidated_outcome_falls_back_to_drawdown_metrics(tmp_path: Path):
    state_dir = tmp_path / "theses"
    thesis_store, thesis_id = register_producer_thesis(state_dir, ticker="INVAL")

    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "transition",
                thesis_id,
                "ENTRY_READY",
                "--reason",
                "ready",
                "--event-date",
                "2026-07-01",
            ]
        )
        == 0
    )
    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "open-position",
                thesis_id,
                "--actual-price",
                "100",
                "--actual-date",
                "2026-07-01",
                "--event-date",
                "2026-07-01",
            ]
        )
        == 0
    )
    assert (
        thesis_store.main(
            [
                "--state-dir",
                str(state_dir),
                "terminate",
                thesis_id,
                "--terminal-status",
                "INVALIDATED",
                "--exit-reason",
                "setup failed",
                "--actual-price",
                "79.5",
                "--actual-date",
                "2026-07-02",
                "--event-date",
                "2026-07-02",
            ]
        )
        == 0
    )

    result = evaluate_state(state_dir, as_of="2026-07-02", account_size=1000)

    assert result["metrics"]["realized_pnl_today"] == -20.5
    assert result["recommendation"] == "HALTED"
    assert result["data_quality"] == "PARTIAL"
    assert any("Inferred missing realized_pnl" in warning for warning in result["warnings"])


def test_exit_null_does_not_crash_terminal_scan(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_exit_null_gm_20260702_0001",
        pnl_dollars=-100.0,
        history=[
            {
                "status": "CLOSED",
                "at": "2026-07-02T10:00:00-04:00",
                "reason": "manual",
            }
        ],
    )
    path = state_dir / "th_exit_null_gm_20260702_0001.yaml"
    data = yaml.safe_load(path.read_text())
    data["exit"] = None
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    result = evaluate_state(state_dir, as_of="2026-07-02")

    assert result["metrics"]["consecutive_losses"] == 1
    assert result["metrics"]["realized_pnl_today"] == -100.0


def test_terminal_non_list_history_still_uses_outcome_fallback(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_bad_history_gm_20260702_0001",
        pnl_dollars=-100.0,
        exit_date="2026-07-02T10:00:00-04:00",
    )
    path = state_dir / "th_bad_history_gm_20260702_0001.yaml"
    data = yaml.safe_load(path.read_text())
    data["status_history"] = {"status": "CLOSED", "at": "2026-07-02T10:00:00-04:00"}
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    result = evaluate_state(state_dir, as_of="2026-07-02")

    assert result["metrics"]["realized_pnl_today"] == -100.0
    assert result["data_quality"] == "PARTIAL"
    assert any("expected list" in warning for warning in result["warnings"])
    assert any("Inferred missing realized_pnl" in warning for warning in result["warnings"])


def test_terminal_exit_null_and_non_list_history_degrades_to_partial(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_exit_null_bad_history_gm_20260702_0001",
        pnl_dollars=-100.0,
        history=[
            {
                "status": "CLOSED",
                "at": "2026-07-02T10:00:00-04:00",
                "reason": "manual",
            }
        ],
    )
    path = state_dir / "th_exit_null_bad_history_gm_20260702_0001.yaml"
    data = yaml.safe_load(path.read_text())
    data["exit"] = None
    data["status_history"] = {"status": "CLOSED", "at": "2026-07-02T10:00:00-04:00"}
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    result = evaluate_state(state_dir, as_of="2026-07-02")

    assert result["recommendation"] == "TRADING_ALLOWED"
    assert result["data_quality"] == "PARTIAL"
    assert result["metrics"]["realized_pnl_today"] == 0
    assert any("expected list" in warning for warning in result["warnings"])
    assert any("no valid terminal date" in warning for warning in result["warnings"])


def test_weekly_and_monthly_drawdown_rules_use_calendar_boundaries(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_prior_week_gm_20260628_0001",
        status="PARTIALLY_CLOSED",
        history=[
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-06-28T15:00:00-04:00",
                "reason": "trim",
                "realized_pnl": -10_000.0,
            }
        ],
    )
    write_thesis(
        state_dir,
        "th_this_week_gm_20260701_0001",
        status="PARTIALLY_CLOSED",
        history=[
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-01T15:00:00-04:00",
                "reason": "trim",
                "realized_pnl": -5_000.0,
            }
        ],
    )

    result = evaluate_state(state_dir, as_of="2026-07-02T12:00:00-04:00")

    assert result["metrics"]["realized_pnl_wtd"] == -5000.0
    assert result["metrics"]["realized_pnl_mtd"] == -5000.0
    assert [rule["rule"] for rule in result["triggered_rules"]] == ["weekly_drawdown_halt"]
    assert result["triggered_rules"][0]["active_until"].startswith("2026-07-06T00:00:00")


def test_monthly_drawdown_halt_and_halted_priority_over_cooldown(tmp_path: Path):
    state_dir = tmp_path / "theses"
    write_thesis(
        state_dir,
        "th_loss1_gm_20260701_0001",
        ticker="AAA",
        pnl_dollars=-100.0,
        exit_date="2026-07-01T10:00:00-04:00",
    )
    write_thesis(
        state_dir,
        "th_loss2_gm_20260701_0002",
        ticker="BBB",
        pnl_dollars=-150.0,
        exit_date="2026-07-01T15:30:00-04:00",
        history=[
            {
                "status": "CLOSED",
                "at": "2026-07-01T15:30:00-04:00",
                "reason": "manual",
                "realized_pnl": -8_000.0,
            }
        ],
    )

    result = evaluate_state(state_dir, as_of="2026-07-02T10:00:00-04:00")

    assert result["recommendation"] == "HALTED"
    rules = {rule["rule"]: rule for rule in result["triggered_rules"]}
    assert "losing_streak_cooldown" in rules
    assert "monthly_drawdown_halt" in rules
    assert rules["monthly_drawdown_halt"]["active_until"].startswith("2026-08-01T00:00:00")


def test_json_only_cli_creates_json_without_markdown(tmp_path: Path):
    state_dir = tmp_path / "theses"
    output_dir = tmp_path / "reports"
    write_thesis(
        state_dir,
        "th_ok_gm_20260702_0001",
        status="PARTIALLY_CLOSED",
        history=[
            {
                "status": "PARTIALLY_CLOSED",
                "at": "2026-07-02T11:00:00-04:00",
                "reason": "trim",
                "realized_pnl": 10.0,
            }
        ],
    )

    exit_code = main(
        [
            "--state-dir",
            str(state_dir),
            "--account-size",
            "100000",
            "--as-of",
            "2026-07-02",
            "--output-dir",
            str(output_dir),
            "--json-only",
        ]
    )

    assert exit_code == 0
    json_files = list(output_dir.glob("circuit_breaker_decision_*.json"))
    md_files = list(output_dir.glob("circuit_breaker_decision_*.md"))
    assert len(json_files) == 1
    assert md_files == []
    data = json.loads(json_files[0].read_text())
    assert data["schema_version"] == "1.0"
    assert data["recommendation"] == "TRADING_ALLOWED"
    assert set(data) >= {
        "generated_at",
        "as_of_date",
        "triggered_rules",
        "metrics",
        "account_size",
        "config",
        "data_quality",
        "rationale",
    }


def test_config_file_and_cli_overrides_are_applied(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"max_daily_loss_pct": 1.0, "losing_streak_n": 3}))
    output_dir = tmp_path / "reports"

    exit_code = main(
        [
            "--state-dir",
            str(tmp_path / "missing"),
            "--account-size",
            "100000",
            "--config",
            str(config_path),
            "--losing-streak-n",
            "4",
            "--output-dir",
            str(output_dir),
            "--json-only",
        ]
    )

    assert exit_code == 0
    data = json.loads(next(output_dir.glob("circuit_breaker_decision_*.json")).read_text())
    assert data["config"]["max_daily_loss_pct"] == 1.0
    assert data["config"]["losing_streak_n"] == 4


def test_unknown_config_key_fails_closed(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"max_daily_loss_pct_typo": 1.0}))

    exit_code = main(
        [
            "--state-dir",
            str(tmp_path / "missing"),
            "--account-size",
            "100000",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "reports"),
            "--json-only",
        ]
    )

    assert exit_code == 1
