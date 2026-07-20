"""Tests for futures_position_sizer.py -- the CLI wrapper.

Covers: the hardened gate-json loader (unreadable / parse_error incl.
RecursionError / non_finite, mirroring contrarian-setup-gate's own
load_json_file), full mode-A and mode-B end-to-end runs, argparse-level
numeric validator rejections (inf/nan/1e309/zero/negative), exit-code
asymmetry (ConfigError -> 2, gate-caused NO_TRADE -> 0), and JSON/text
report generation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import futures_position_sizer as cli
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "futures_position_sizer.py"


def _run_cli(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _ready_gate_fixture(**overrides) -> dict[str, Any]:
    fixture = {
        "schema_version": "1.0",
        "symbol": "B6",
        "setup_status": "READY_FOR_PLAN",
        "direction": "SHORT",
        "gate_confidence": "HIGH",
        "entry_trigger": "price-action confirmation: key_reversal at week_of=2026-07-06",
        "invalidation_level": 1.3450,
        "missing_confirmations": [],
        "warnings": [],
        "inputs": {},
        "run_context": {"symbol": "B6", "as_of": "2026-07-15", "schema_version": "1.0"},
    }
    fixture.update(overrides)
    return fixture


# --- Section 1: hardened gate-json loader -----------------------------------


def test_load_json_file_missing_file_is_unreadable(tmp_path: Path) -> None:
    data, reason = cli.load_json_file(str(tmp_path / "nope.json"))
    assert data is None
    assert reason == "unreadable"


def test_load_json_file_directory_is_unreadable(tmp_path: Path) -> None:
    data, reason = cli.load_json_file(str(tmp_path))
    assert data is None
    assert reason == "unreadable"


def test_load_json_file_non_utf8_binary_is_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "binary.json"
    path.write_bytes(b"\xff\xfe\x00bad")
    data, reason = cli.load_json_file(str(path))
    assert data is None
    assert reason == "unreadable"


def test_load_json_file_invalid_json_is_parse_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    data, reason = cli.load_json_file(str(path))
    assert data is None
    assert reason == "parse_error"


def test_load_json_file_extreme_nesting_is_parse_error(tmp_path: Path) -> None:
    depth = 250_000
    raw_text = "[" * depth + "1" + "]" * depth
    path = tmp_path / "extreme.json"
    path.write_text(raw_text, encoding="utf-8")
    data, reason = cli.load_json_file(str(path))
    assert data is None
    assert reason == "parse_error"


def test_load_json_file_overflow_number_is_non_finite(tmp_path: Path) -> None:
    path = tmp_path / "overflow.json"
    path.write_text('{"invalidation_level": 1e309}', encoding="utf-8")
    data, reason = cli.load_json_file(str(path))
    assert data is None
    assert reason == "non_finite"


def test_load_json_file_literal_infinity_is_non_finite(tmp_path: Path) -> None:
    path = tmp_path / "infinity.json"
    path.write_text('{"invalidation_level": Infinity}', encoding="utf-8")
    data, reason = cli.load_json_file(str(path))
    assert data is None
    assert reason == "non_finite"


def test_load_json_file_nan_nested_deep_is_non_finite(tmp_path: Path) -> None:
    path = tmp_path / "deep_nan.json"
    path.write_text('{"a": {"b": {"c": [1, 2, NaN]}}}', encoding="utf-8")
    data, reason = cli.load_json_file(str(path))
    assert data is None
    assert reason == "non_finite"


def test_load_json_file_deep_but_finite_field_loads_normally(tmp_path: Path) -> None:
    fixture = _ready_gate_fixture()
    deep = 1.0
    for _ in range(500):
        deep = [deep]
    fixture["_deep_unused"] = deep
    path = tmp_path / "deep_finite.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    data, reason = cli.load_json_file(str(path))
    assert reason is None
    assert data["symbol"] == "B6"


def test_load_json_file_valid_json_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(_ready_gate_fixture()), encoding="utf-8")
    data, reason = cli.load_json_file(str(path))
    assert reason is None
    assert data["setup_status"] == "READY_FOR_PLAN"


# --- Section 2: numeric argparse validators (subprocess, exit code 2) ------


class TestNumericValidatorsRejectDegenerateValues:
    BASE_ARGS = [
        "--symbol",
        "ES",
        "--direction",
        "LONG",
        "--entry",
        "5000.25",
        "--stop",
        "4980.00",
        "--account-size",
        "100000",
        "--risk-pct",
        "1.0",
        "--output-dir",
        "/tmp/does-not-matter",
    ]

    def _with_override(self, flag: str, value: str) -> list[str]:
        args = list(self.BASE_ARGS)
        idx = args.index(flag)
        args[idx + 1] = value
        return args

    @pytest.mark.parametrize("bad_value", ["inf", "-inf", "nan", "1e309", "0", "-5"])
    def test_entry_rejects_degenerate_values(self, bad_value):
        result = _run_cli(self._with_override("--entry", bad_value))
        assert result.returncode == 2

    @pytest.mark.parametrize("bad_value", ["inf", "nan", "1e309", "0", "-5"])
    def test_stop_rejects_degenerate_values(self, bad_value):
        result = _run_cli(self._with_override("--stop", bad_value))
        assert result.returncode == 2

    @pytest.mark.parametrize("bad_value", ["inf", "nan", "1e309", "0", "-100000"])
    def test_account_size_rejects_degenerate_values(self, bad_value):
        result = _run_cli(self._with_override("--account-size", bad_value))
        assert result.returncode == 2

    @pytest.mark.parametrize("bad_value", ["inf", "nan", "0", "-1", "10.01"])
    def test_risk_pct_rejects_degenerate_or_out_of_range_values(self, bad_value):
        result = _run_cli(self._with_override("--risk-pct", bad_value))
        assert result.returncode == 2

    def test_risk_pct_accepts_boundary_10(self):
        result = _run_cli(self._with_override("--risk-pct", "10.0"))
        assert result.returncode == 0

    @pytest.mark.parametrize("bad_value", ["-1", "1.5", "inf", "nan"])
    def test_max_contracts_rejects_degenerate_values(self, bad_value):
        args = [*self.BASE_ARGS, "--max-contracts", bad_value]
        result = _run_cli(args)
        assert result.returncode == 2

    def test_max_contracts_zero_means_no_cap(self):
        args = [*self.BASE_ARGS, "--max-contracts", "0"]
        result = _run_cli(args)
        assert result.returncode == 0

    def test_max_contracts_beyond_2_pow_53_parses_exactly(self, tmp_path):
        # Code review round 3, P2-4: a --max-contracts value beyond
        # float64's exact-integer range must parse without precision
        # loss -- this is far above any real cap, so it's never actually
        # binding here, but it must not be silently coerced to a
        # different integer or crash.
        out_dir = tmp_path / "reports"
        args = [
            *self.BASE_ARGS,
            "--max-contracts",
            "9007199254740995",
            "--output-dir",
            str(out_dir),
        ]
        result = _run_cli(args)
        assert result.returncode == 0

    @pytest.mark.parametrize("bad_value", ["1.0", "1e2", "1,000"])
    def test_max_contracts_rejects_non_integer_syntax(self, bad_value):
        # int()-based parsing is intentionally stricter than the old
        # float()-based one: a decimal point or exponent notation is never
        # valid --max-contracts syntax now, even when mathematically a
        # whole number.
        args = [*self.BASE_ARGS, "--max-contracts", bad_value]
        result = _run_cli(args)
        assert result.returncode == 2

    @pytest.mark.parametrize("bad_value", ["inf", "nan", "1e309", "0", "-1.2"])
    def test_fx_rate_rejects_degenerate_values(self, bad_value):
        args = [*self.BASE_ARGS, "--fx-rate", bad_value]
        result = _run_cli(args)
        assert result.returncode == 2


# --- Section 2b: float64 overflow guards (code review round 1, P2) ---------
#
# --account-size/--multiplier/--tick-size/--fx-rate lacked a max_value cap
# (unlike --risk-pct, which already had one) -- an individually "valid"
# (finite, positive) but extreme value on one of these, or an extreme
# --entry/--stop (deliberately left uncapped -- real prices have no reason
# to be bounded), could make a COMPUTED intermediate (risk_budget,
# risk_per_contract, or the tick-grid ratio) overflow to a non-finite
# value, which used to escape as an uncaught OverflowError/ValueError --
# exit 1, violating the two-class exit contract (2 config / 0 fail-closed
# report -- never 1).


class TestOverflowGuards:
    BASE_ARGS = [
        "--symbol", "ES",
        "--direction", "LONG",
        "--entry", "5000.25",
        "--stop", "4980.00",
        "--account-size", "100000",
        "--risk-pct", "1.0",
        "--as-of", "2026-07-17",
    ]  # fmt: skip

    UNKNOWN_SYMBOL_ARGS = [
        "--symbol", "ZZZZ",
        "--direction", "LONG",
        "--entry", "100.0",
        "--stop", "90.0",
        "--contract-currency", "USD",
        "--account-size", "100000",
        "--risk-pct", "1.0",
        "--as-of", "2026-07-17",
    ]  # fmt: skip

    def _with_override(self, base: list[str], flag: str, value: str) -> list[str]:
        args = list(base)
        idx = args.index(flag)
        args[idx + 1] = value
        return args

    def test_repro_a_extreme_account_size_exits_2_not_1(self, tmp_path):
        # Exact code-review repro A: --account-size 1.5e308 --risk-pct 10.0
        # used to overflow risk_budget to inf, then crash with
        # OverflowError inside math.floor() -- exit 1. Now caught by the
        # --account-size argparse cap itself, before any risk math runs.
        out_dir = tmp_path / "reports"
        args = self._with_override(self.BASE_ARGS, "--account-size", "1.5e308")
        args = self._with_override(args, "--risk-pct", "10.0")
        args = [*args, "--output-dir", str(out_dir)]
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert not out_dir.exists() or not any(out_dir.iterdir())

    def test_repro_b_extreme_multiplier_override_exits_2_not_1(self, tmp_path):
        # Exact code-review repro B: an unknown-symbol override with
        # --multiplier 1e308 --tick-size 0.01 used to overflow
        # risk_per_contract to inf, then crash writing the JSON report
        # (allow_nan=False -> ValueError) -- exit 1. Now caught by the
        # --multiplier argparse cap itself.
        out_dir = tmp_path / "reports"
        args = [
            *self.UNKNOWN_SYMBOL_ARGS,
            "--multiplier", "1e308",
            "--tick-size", "0.01",
            "--output-dir", str(out_dir),
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert not out_dir.exists() or not any(out_dir.iterdir())

    def test_account_size_boundary_at_cap_succeeds(self, tmp_path):
        out_dir = tmp_path / "reports"
        args = self._with_override(self.BASE_ARGS, "--account-size", "1e12")
        args = [*args, "--output-dir", str(out_dir), "--format", "json"]
        result = _run_cli(args)
        assert result.returncode == 0

    def test_account_size_boundary_above_cap_rejected(self):
        args = self._with_override(self.BASE_ARGS, "--account-size", "1.1e12")
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr

    def test_multiplier_boundary_at_cap_succeeds(self, tmp_path):
        out_dir = tmp_path / "reports"
        args = [
            *self.UNKNOWN_SYMBOL_ARGS,
            "--multiplier", "1e9",
            "--tick-size", "0.01",
            "--output-dir", str(out_dir),
            "--format", "json",
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 0

    def test_multiplier_boundary_above_cap_rejected(self):
        args = [
            *self.UNKNOWN_SYMBOL_ARGS,
            "--multiplier", "1.1e9",
            "--tick-size", "0.01",
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr

    def test_tick_size_boundary_at_cap_succeeds(self, tmp_path):
        # Entry/stop must be at least one 1e6-sized tick apart, or this
        # would (correctly) hit stop_too_close instead of exercising the
        # tick-size cap boundary itself.
        out_dir = tmp_path / "reports"
        args = [
            "--symbol", "ZZZZ",
            "--direction", "LONG",
            "--entry", "3000000.0",
            "--stop", "1000000.0",
            "--multiplier", "1",
            "--tick-size", "1e6",
            "--contract-currency", "USD",
            "--account-size", "100000",
            "--risk-pct", "1.0",
            "--as-of", "2026-07-17",
            "--output-dir", str(out_dir),
            "--format", "json",
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 0

    def test_tick_size_boundary_above_cap_rejected(self):
        args = [
            *self.UNKNOWN_SYMBOL_ARGS,
            "--multiplier", "1",
            "--tick-size", "1.1e6",
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr

    def test_fx_rate_boundary_at_cap_succeeds(self, tmp_path):
        out_dir = tmp_path / "reports"
        args = [
            *self.BASE_ARGS,
            "--fx-rate",
            "1e6",
            "--output-dir",
            str(out_dir),
            "--format",
            "json",
        ]
        result = _run_cli(args)
        assert result.returncode == 0

    def test_fx_rate_boundary_above_cap_rejected(self):
        args = [*self.BASE_ARGS, "--fx-rate", "1.1e6"]
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr

    def test_one_trillion_account_size_control_case_still_sizes(self, tmp_path):
        # The cap's own boundary value must still produce an ordinary,
        # correct SIZED result -- the fix must never false-positive on a
        # merely large (but finite) account size.
        out_dir = tmp_path / "reports"
        args = self._with_override(self.BASE_ARGS, "--account-size", "1e12")
        args = [*args, "--output-dir", str(out_dir), "--format", "json"]
        result = _run_cli(args)
        assert result.returncode == 0
        payload = json.loads((out_dir / "futures_position_size_ES_2026-07-17.json").read_text())
        assert payload["sizing_status"] == "SIZED"
        assert payload["risk_budget_usd"] == pytest.approx(1e12 * 1.0 / 100.0)

    def test_extreme_entry_uncapped_flag_still_exits_2_not_1(self, tmp_path):
        # --entry deliberately has NO max_value cap (real prices are never
        # artificially bounded) -- this is the residual overflow route the
        # argparse-level caps on multiplier/tick-size/fx-rate alone cannot
        # prevent. Only the isfinite() guard on the computed
        # risk_per_contract catches it. Must exit 2 cleanly, never crash.
        out_dir = tmp_path / "reports"
        args = [
            "--symbol", "ES",
            "--direction", "LONG",
            "--entry", "1e308",
            "--stop", "1.0",
            "--account-size", "100000",
            "--risk-pct", "1.0",
            "--output-dir", str(out_dir),
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert not out_dir.exists() or not any(out_dir.iterdir())

    def test_extreme_bond_entry_gets_overflow_message_not_32nds(self, tmp_path):
        # Code review round 3, P3: an extreme --entry (>1e300) on a BOND
        # symbol used to trip the 32nds-notation ConfigError, misattributing
        # a numeric overflow as a notation mistake. Must exit 2 with an
        # overflow/magnitude message instead, and never mention "32nds".
        out_dir = tmp_path / "reports"
        args = [
            "--symbol", "ZB",
            "--direction", "LONG",
            "--entry", "1e308",
            "--stop", "1.0",
            "--account-size", "100000",
            "--risk-pct", "1.0",
            "--output-dir", str(out_dir),
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert "32nds" not in result.stderr
        assert "not finite" in result.stderr
        assert "--entry" in result.stderr
        assert not out_dir.exists() or not any(out_dir.iterdir())

    def test_normal_off_grid_bond_entry_still_gets_32nds_message(self, tmp_path):
        # Regression guard for the same fix: an ordinary, finite off-grid
        # bond entry (the classic 110.16-vs-110'16 mistype) must still be
        # rejected with the 32nds-notation message, not misrouted into the
        # overflow path.
        out_dir = tmp_path / "reports"
        args = [
            "--symbol", "ZB",
            "--direction", "LONG",
            "--entry", "110.16",
            "--stop", "108.00",
            "--account-size", "100000",
            "--risk-pct", "1.0",
            "--output-dir", str(out_dir),
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert "32nds" in result.stderr
        assert not out_dir.exists() or not any(out_dir.iterdir())


# --- Section 2c: code review round 3 (user re-review) -----------------------
# P1-1: floor epsilon rounded contracts UP past the risk budget at large
# scale. P1-2: denormal underflow (risk_per_contract == 0.0) crashed with
# ZeroDivisionError, exit 1.


class TestBudgetInvariantAndUnderflowGuards:
    def test_p1_1_exact_repro_never_exceeds_budget_end_to_end(self, tmp_path):
        # budget = account_size * risk_pct / 100 = 999999999500 * 10 / 100
        # = 99,999,999,950.0; risk_per_contract = distance(10) *
        # multiplier(100) = 1000.0 -- reproduces the reviewer's exact
        # q=99999999.95 case end-to-end through the real CLI.
        out_dir = tmp_path / "reports"
        args = [
            "--symbol", "ZZZZ",
            "--direction", "LONG",
            "--entry", "100.0",
            "--stop", "90.0",
            "--multiplier", "100",
            "--tick-size", "0.01",
            "--contract-currency", "USD",
            "--account-size", "999999999500",
            "--risk-pct", "10.0",
            "--as-of", "2026-07-17",
            "--output-dir", str(out_dir),
            "--format", "json",
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 0
        payload = json.loads((out_dir / "futures_position_size_ZZZZ_2026-07-17.json").read_text())
        assert payload["sizing_status"] == "SIZED"
        assert payload["contracts"] == 99_999_999
        assert payload["contracts"] * payload["risk_per_contract_usd"] <= payload["risk_budget_usd"]

    def test_p1_2_denormal_underflow_exits_2_not_1(self, tmp_path):
        # Exact reviewer repro end-to-end through the real CLI: all four
        # values individually pass the finite/positive validators, but the
        # product underflows to exactly 0.0.
        out_dir = tmp_path / "reports"
        args = [
            "--symbol", "ZZZZ",
            "--direction", "LONG",
            "--entry", "2e-308",
            "--stop", "1e-308",
            "--multiplier", "1e-308",
            "--tick-size", "1e-308",
            "--contract-currency", "USD",
            "--account-size", "100000",
            "--risk-pct", "1.0",
            "--output-dir", str(out_dir),
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert not out_dir.exists() or not any(out_dir.iterdir())

    def test_p1_1_followup_hang_repro_terminates_and_exits_2(self, tmp_path):
        # Second re-review of the P1-1 fix: the absolute-epsilon + hard
        # post-condition loop that "fixed" P1-1 could not terminate in
        # practice at this scale (float64 can no longer represent
        # `(contracts - 1) * rpc != contracts * rpc` once contracts is
        # ~2.4e285, so the loop's decrement never reaches its exit
        # condition). A `timeout=` on the subprocess call turns a
        # regression back into that failure mode into a clean pytest
        # failure (TimeoutExpired) instead of an actually-hanging test
        # suite. The exact-rational floor must terminate instantly and
        # reject the absurd result outright.
        out_dir = tmp_path / "reports"
        args = [
            "--symbol", "ZZZZ",
            "--direction", "LONG",
            "--entry", "2",
            "--stop", "1",
            "--multiplier", "1.4296227991821346e-275",
            "--tick-size", "1",
            "--contract-currency", "USD",
            "--account-size", "341482236954.82006",
            "--risk-pct", "10",
            "--output-dir", str(out_dir),
        ]  # fmt: skip
        result = _run_cli(args, timeout=10.0)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert "implausible" in result.stderr
        assert not out_dir.exists() or not any(out_dir.iterdir())


# --- Section 3: mode A / mode B end-to-end (in-process via cli.main) -------


def _argv(args, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["futures_position_sizer.py", *args])


class TestModeAEndToEnd:
    def test_es_long_hand_checked_sized(self, tmp_path, monkeypatch, capsys):
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--symbol",
                "ES",
                "--direction",
                "LONG",
                "--entry",
                "5000.25",
                "--stop",
                "4980.00",
                "--account-size",
                "100000",
                "--risk-pct",
                "2.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        json_path = out_dir / "futures_position_size_ES_2026-07-17.json"
        assert json_path.exists()
        payload = json.loads(json_path.read_text())
        assert payload["sizing_status"] == "SIZED"
        assert payload["contracts"] == 1
        assert payload["risk_per_contract_usd"] == pytest.approx(1012.50)

    def test_geometry_violation_exits_2_no_report(self, tmp_path, monkeypatch, capsys):
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--symbol",
                "ES",
                "--direction",
                "LONG",
                "--entry",
                "5000.00",
                "--stop",
                "5010.00",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--output-dir",
                str(out_dir),
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 2
        assert not out_dir.exists() or not any(out_dir.iterdir())

    def test_bond_off_grid_entry_exits_2(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--symbol",
                "ZB",
                "--direction",
                "LONG",
                "--entry",
                "110.16",
                "--stop",
                "108.00",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--output-dir",
                str(out_dir),
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 2

    def test_zero_contracts_is_no_trade_exit_0(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--symbol",
                "ES",
                "--direction",
                "LONG",
                "--entry",
                "5000.25",
                "--stop",
                "4980.00",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        payload = json.loads((out_dir / "futures_position_size_ES_2026-07-17.json").read_text())
        assert payload["sizing_status"] == "NO_TRADE"
        assert payload["no_trade_reason"] == "risk_below_one_contract"

    def test_unknown_symbol_without_overrides_exits_2(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--symbol",
                "ZZZZ",
                "--direction",
                "LONG",
                "--entry",
                "100.0",
                "--stop",
                "90.0",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--output-dir",
                str(out_dir),
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 2

    def test_unknown_symbol_with_full_overrides_sizes(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--symbol",
                "ZZZZ",
                "--direction",
                "LONG",
                "--entry",
                "100.0",
                "--stop",
                "90.0",
                "--multiplier",
                "10",
                "--tick-size",
                "0.5",
                "--contract-currency",
                "USD",
                "--account-size",
                "100000",
                "--risk-pct",
                "5.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        payload = json.loads((out_dir / "futures_position_size_ZZZZ_2026-07-17.json").read_text())
        assert payload["sizing_status"] == "SIZED"

    def test_direction_and_gate_json_conflict_exits_2(self, tmp_path):
        # parser.error() raises SystemExit -- exercised via subprocess like
        # every other argparse-level (as opposed to fs.ConfigError-level)
        # usage error, matching position-sizer's own convention.
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(json.dumps(_ready_gate_fixture()), encoding="utf-8")
        result = _run_cli(
            [
                "--gate-json",
                str(gate_path),
                "--direction",
                "LONG",
                "--entry",
                "1.35",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
            ]
        )
        assert result.returncode == 2


class TestModeBEndToEnd:
    def test_ready_gate_report_sizes_via_gate_stop(self, tmp_path, monkeypatch):
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(json.dumps(_ready_gate_fixture()), encoding="utf-8")
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--gate-json",
                str(gate_path),
                "--entry",
                "1.3400",
                "--account-size",
                "100000",
                "--risk-pct",
                "5.0",
                "--fx-rate",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        payload = json.loads((out_dir / "futures_position_size_B6_2026-07-17.json").read_text())
        assert payload["direction"] == "SHORT"
        assert payload["stop"] == pytest.approx(1.3450)
        assert payload["gate"]["setup_status"] == "READY_FOR_PLAN"

    def test_non_ready_gate_report_is_no_trade_exit_0(self, tmp_path, monkeypatch):
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(
            json.dumps(
                _ready_gate_fixture(setup_status="CROWDED", direction=None, invalidation_level=None)
            ),
            encoding="utf-8",
        )
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--gate-json",
                str(gate_path),
                "--entry",
                "1.34",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        payload = json.loads((out_dir / "futures_position_size_B6_2026-07-17.json").read_text())
        assert payload["sizing_status"] == "NO_TRADE"
        assert payload["no_trade_reason"] == "gate_not_ready"

    def test_binary_gate_file_is_no_trade_exit_0(self, tmp_path, monkeypatch):
        gate_path = tmp_path / "gate.json"
        gate_path.write_bytes(b"\xff\xfe\x00bad")
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--gate-json",
                str(gate_path),
                "--symbol",
                "B6",
                "--entry",
                "1.34",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        payload = json.loads((out_dir / "futures_position_size_B6_2026-07-17.json").read_text())
        assert payload["sizing_status"] == "NO_TRADE"
        assert payload["no_trade_reason"] == "gate_json_unreadable"

    def test_symbol_mismatch_is_no_trade_exit_0(self, tmp_path, monkeypatch):
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(json.dumps(_ready_gate_fixture()), encoding="utf-8")
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--gate-json",
                str(gate_path),
                "--symbol",
                "ES",
                "--entry",
                "5000",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        payload = json.loads((out_dir / "futures_position_size_ES_2026-07-17.json").read_text())
        assert payload["no_trade_reason"] == "gate_symbol_mismatch"

    # --- Code review round 3 (user re-review), P1-3 ------------------------

    def test_whitespace_only_gate_symbol_is_no_trade_exit_0(self, tmp_path, monkeypatch):
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(json.dumps(_ready_gate_fixture(symbol="   ")), encoding="utf-8")
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--gate-json",
                str(gate_path),
                "--entry",
                "1.34",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],  # fmt: skip
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        payload = json.loads(
            (out_dir / "futures_position_size_UNKNOWN_2026-07-17.json").read_text()
        )
        assert payload["sizing_status"] == "NO_TRADE"
        assert payload["no_trade_reason"] == "gate_json_malformed"

    def test_path_hostile_gate_symbol_is_no_trade_with_safe_filename(self, tmp_path, monkeypatch):
        # "A/B" must never reach the output filename -- with no --symbol
        # given to fall back on, the CLI must resolve to the safe literal
        # "UNKNOWN", not crash with FileNotFoundError writing into a
        # nonexistent "futures_position_size_A" subdirectory.
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(json.dumps(_ready_gate_fixture(symbol="A/B")), encoding="utf-8")
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--gate-json",
                str(gate_path),
                "--entry",
                "1.34",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],  # fmt: skip
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        written_files = list(out_dir.iterdir())
        assert len(written_files) == 1
        assert "/" not in written_files[0].name
        payload = json.loads(written_files[0].read_text())
        assert payload["sizing_status"] == "NO_TRADE"
        assert payload["no_trade_reason"] == "gate_json_malformed"

    def test_path_hostile_explicit_symbol_exits_2(self, tmp_path):
        # The same allowlist applies to an operator-typed --symbol in
        # explicit mode -- a usage error, exit 2, symmetric with the
        # gate-file case above being a fail-closed NO_TRADE (exit 0).
        out_dir = tmp_path / "reports"
        args = [
            "--symbol", "A/B",
            "--direction", "LONG",
            "--entry", "100.0",
            "--stop", "90.0",
            "--account-size", "100000",
            "--risk-pct", "1.0",
            "--output-dir", str(out_dir),
        ]  # fmt: skip
        result = _run_cli(args)
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert not out_dir.exists() or not any(out_dir.iterdir())

    def test_gate_stop_off_tick_grid_bond_is_no_trade_exit_0(self, tmp_path, monkeypatch):
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(
            json.dumps(
                _ready_gate_fixture(symbol="ZB", direction="LONG", invalidation_level=108.16)
            ),
            encoding="utf-8",
        )
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--gate-json",
                str(gate_path),
                "--entry",
                "110.50",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0
        payload = json.loads((out_dir / "futures_position_size_ZB_2026-07-17.json").read_text())
        assert payload["no_trade_reason"] == "gate_stop_off_tick_grid"

    def test_gate_stop_too_close_is_no_trade_exit_0(self, tmp_path, monkeypatch):
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(
            json.dumps(_ready_gate_fixture(direction="LONG", invalidation_level=1.34995)),
            encoding="utf-8",
        )
        out_dir = tmp_path / "reports"
        _argv(
            [
                "--gate-json",
                str(gate_path),
                "--entry",
                "1.35000",
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
                "--as-of",
                "2026-07-17",
                "--output-dir",
                str(out_dir),
                "--format",
                "json",
            ],
            monkeypatch,
        )
        exit_code = cli.main()
        assert exit_code == 0

    def test_entry_always_required_missing_exits_2(self, tmp_path):
        # parser.error() raises SystemExit -- see subprocess note above.
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(json.dumps(_ready_gate_fixture()), encoding="utf-8")
        result = _run_cli(
            [
                "--gate-json",
                str(gate_path),
                "--account-size",
                "100000",
                "--risk-pct",
                "1.0",
            ]
        )
        assert result.returncode == 2


# --- Section 4: --list-specs -------------------------------------------------


def test_list_specs_prints_table_and_exits_0(capsys, monkeypatch):
    _argv(["--list-specs"], monkeypatch)
    exit_code = cli.main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "ES" in captured.out
    assert "GC" in captured.out


def test_list_specs_ignores_other_missing_required_args(monkeypatch):
    _argv(["--list-specs"], monkeypatch)
    exit_code = cli.main()
    assert exit_code == 0


# --- Section 5: currency / fx-rate guard ------------------------------------


def test_non_usd_symbol_without_fx_rate_exits_2(tmp_path, monkeypatch):
    out_dir = tmp_path / "reports"
    _argv(
        [
            "--symbol",
            "ZZZZ",
            "--direction",
            "LONG",
            "--entry",
            "100.0",
            "--stop",
            "90.0",
            "--multiplier",
            "10",
            "--tick-size",
            "0.5",
            "--contract-currency",
            "GBP",
            "--account-size",
            "100000",
            "--risk-pct",
            "1.0",
            "--output-dir",
            str(out_dir),
        ],
        monkeypatch,
    )
    exit_code = cli.main()
    assert exit_code == 2


def test_non_usd_symbol_with_fx_rate_sizes(tmp_path, monkeypatch):
    out_dir = tmp_path / "reports"
    _argv(
        [
            "--symbol",
            "ZZZZ",
            "--direction",
            "LONG",
            "--entry",
            "100.0",
            "--stop",
            "90.0",
            "--multiplier",
            "10",
            "--tick-size",
            "0.5",
            "--contract-currency",
            "GBP",
            "--fx-rate",
            "1.25",
            "--account-size",
            "100000",
            "--risk-pct",
            "5.0",
            "--as-of",
            "2026-07-17",
            "--output-dir",
            str(out_dir),
            "--format",
            "json",
        ],
        monkeypatch,
    )
    exit_code = cli.main()
    assert exit_code == 0
    payload = json.loads((out_dir / "futures_position_size_ZZZZ_2026-07-17.json").read_text())
    assert payload["fx_rate_used"] == 1.25


# --- Section 6: text format renders for SIZED and NO_TRADE -----------------


def test_text_format_renders_sized(tmp_path, monkeypatch, capsys):
    out_dir = tmp_path / "reports"
    _argv(
        [
            "--symbol",
            "ES",
            "--direction",
            "LONG",
            "--entry",
            "5000.25",
            "--stop",
            "4980.00",
            "--account-size",
            "100000",
            "--risk-pct",
            "2.0",
            "--as-of",
            "2026-07-17",
            "--output-dir",
            str(out_dir),
            "--format",
            "text",
        ],
        monkeypatch,
    )
    exit_code = cli.main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "SIZED" in captured.out
    assert "1" in captured.out


def test_text_format_renders_no_trade(tmp_path, monkeypatch, capsys):
    out_dir = tmp_path / "reports"
    _argv(
        [
            "--symbol",
            "ES",
            "--direction",
            "LONG",
            "--entry",
            "5000.25",
            "--stop",
            "4980.00",
            "--account-size",
            "100000",
            "--risk-pct",
            "1.0",
            "--as-of",
            "2026-07-17",
            "--output-dir",
            str(out_dir),
            "--format",
            "text",
        ],
        monkeypatch,
    )
    exit_code = cli.main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "NO_TRADE" in captured.out
    assert "risk_below_one_contract" in captured.out


# --- Section 7: JSON writer never emits non-standard tokens -----------------


def test_json_report_has_no_nan_or_infinity_tokens(tmp_path, monkeypatch):
    out_dir = tmp_path / "reports"
    _argv(
        [
            "--symbol",
            "ES",
            "--direction",
            "LONG",
            "--entry",
            "5000.25",
            "--stop",
            "4980.00",
            "--account-size",
            "100000",
            "--risk-pct",
            "2.0",
            "--as-of",
            "2026-07-17",
            "--output-dir",
            str(out_dir),
            "--format",
            "json",
        ],
        monkeypatch,
    )
    cli.main()
    raw_text = (out_dir / "futures_position_size_ES_2026-07-17.json").read_text()
    assert "NaN" not in raw_text
    assert "Infinity" not in raw_text
    json.loads(raw_text)  # must be strictly valid JSON
