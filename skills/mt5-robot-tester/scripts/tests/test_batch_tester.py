"""Tests for the orchestrator's pure helpers and safety boundaries."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mt5_batch_tester as batch  # noqa: E402
from mt5_batch_tester import (  # noqa: E402
    Pipeline,
    TerminalTerminationError,
    acquire_lock,
    block_lock,
    build_backtest_ini,
    build_optimize_param_ini,
    compute_range,
    evaluate_finalist,
    evaluate_round2_profile,
    experts_relpath,
    inputs_from_passes,
    lock_blocker_path,
    main,
    mt5_data_dir,
    release_lock,
    select_strategy_params,
    shared_lock_path,
)
from parse_mt5_optimization import parse_passes  # noqa: E402

DEPOSIT = 10000
GATES = {
    "finalist_min_profit_multiple": 4.0,
    "finalist_max_drawdown_pct": 12.0,
    "finalist_require_improvement": True,
}
COMMON = {
    "period": "H1",
    "from": "2020.01.01",
    "to": "2026.06.30",
    "model": 4,
    "deposit": 10000,
    "currency": "USD",
    "leverage": 100,
    "optimization_criterion": 0,
}


# --- ranges --------------------------------------------------------------


def test_compute_range_float():
    start, step, stop = compute_range(1.5, 0.5, 0.05)
    assert start == 0.75
    assert stop == 2.25
    assert abs(step - 0.075) < 1e-9


def test_compute_range_integer_period():
    start, step, stop = compute_range(86, 0.5, 0.05)
    assert (start, stop) == (43, 129)
    assert step == 4  # round(86*0.05)=4


def test_compute_range_zero_returns_none():
    assert compute_range(0, 0.5, 0.05) is None


def test_compute_range_small_int_step_floor_one():
    _, step, _ = compute_range(10, 0.5, 0.05)  # 0.5 -> round 0 -> floored to 1
    assert step == 1


# --- parameter selection -------------------------------------------------


def test_select_params_after_magic():
    names = [
        "FillType",
        "ForceFill",
        "CustomComment",
        "MagicNumber",
        "GannHiLoPeriod1",
        "PriceEntryMult1",
        "StopLossCoef1",
        "TrailingStopCoef1",
        "TrailingActCef1",
    ]
    got = select_strategy_params(names, "MagicNumber", 6)
    assert got == [
        "GannHiLoPeriod1",
        "PriceEntryMult1",
        "StopLossCoef1",
        "TrailingStopCoef1",
        "TrailingActCef1",
    ]


def test_select_params_fallback_without_magic():
    names = ["A", "B", "C"]
    assert select_strategy_params(names, "MagicNumber", 6) == ["A", "B", "C"]


def test_inputs_from_passes_ordered():
    passes = parse_passes(Path(__file__).resolve().parent / "fixtures" / "sample_opt.xml")
    inputs = inputs_from_passes(passes)
    names = [n for n, _ in inputs]
    assert names[0] == "MagicNumber"
    assert names[1] == "GannHiLoPeriod1"
    strategy_params = select_strategy_params(names, "MagicNumber", 6)
    assert strategy_params == [
        "GannHiLoPeriod1",
        "PriceEntryMult1",
        "StopLossCoef1",
        "TrailingStopCoef1",
        "TrailingActCef1",
    ]


def test_find_terminal_prefers_environment_over_config(tmp_path, monkeypatch):
    env_terminal = tmp_path / "env" / "terminal64.exe"
    config_terminal = tmp_path / "config" / "terminal64.exe"
    env_terminal.parent.mkdir()
    config_terminal.parent.mkdir()
    env_terminal.touch()
    config_terminal.touch()
    monkeypatch.setenv("MT5_TERMINAL_PATH", str(env_terminal))

    assert batch.find_terminal(configured=str(config_terminal)) == env_terminal


# --- finalist decision ---------------------------------------------------


def test_finalist_passes():
    final = {"net_profit": 45000, "drawdown_max_pct": 10.0}
    ok, reason = evaluate_finalist(final, r2_profit=20000, deposit=DEPOSIT, gates=GATES)
    assert ok is True
    assert reason == "ok"


def test_finalist_fails_on_drawdown():
    final = {"net_profit": 45000, "drawdown_max_pct": 13.0}
    ok, reason = evaluate_finalist(final, 20000, DEPOSIT, GATES)
    assert ok is False
    assert "DD" in reason


def test_finalist_fails_without_improvement():
    final = {"net_profit": 45000, "drawdown_max_pct": 8.0}
    ok, reason = evaluate_finalist(final, r2_profit=50000, deposit=DEPOSIT, gates=GATES)
    assert ok is False
    assert "does not improve" in reason


def test_finalist_fails_below_4x():
    final = {"net_profit": 30000, "drawdown_max_pct": 8.0}
    ok, reason = evaluate_finalist(final, 20000, DEPOSIT, GATES)
    assert ok is False
    assert "profit" in reason


# --- round-2 profile -----------------------------------------------------


def test_round2_profile_all_pass():
    ref = {
        "min_profit_pct": 300,
        "max_drawdown_pct": 15,
        "min_pct_positive_months": 70,
        "require_all_years_positive": True,
        "min_lr_correlation": 0.80,
        "max_months_to_new_high": 3,
    }
    metrics = {
        "profit_pct": 320,
        "drawdown_max_pct": 10,
        "pct_positive_months": 75,
        "all_years_positive": True,
        "lr_correlation": 0.9,
        "max_months_to_new_high": 2,
    }
    res = evaluate_round2_profile(metrics, DEPOSIT, ref)
    assert res["all_passed"] is True


def test_round2_profile_fails_lr():
    ref = {
        "min_profit_pct": 300,
        "max_drawdown_pct": 15,
        "min_pct_positive_months": 70,
        "require_all_years_positive": True,
        "min_lr_correlation": 0.80,
        "max_months_to_new_high": 3,
    }
    metrics = {
        "profit_pct": 320,
        "drawdown_max_pct": 10,
        "pct_positive_months": 75,
        "all_years_positive": True,
        "lr_correlation": 0.7,
        "max_months_to_new_high": 2,
    }
    res = evaluate_round2_profile(metrics, DEPOSIT, ref)
    assert res["lr_correlation"] is False
    assert res["all_passed"] is False


# --- expert path ---------------------------------------------------------


def test_experts_relpath_under_experts():
    p = r"C:\Users\x\AppData\Roaming\MetaQuotes\Terminal\ABC\MQL5\Experts\candidate bots"
    assert experts_relpath(p) == "candidate bots"


def test_experts_relpath_nested():
    p = r"C:\MT5\MQL5\Experts\group\candidate bots"
    assert experts_relpath(p) == "group\\candidate bots"


def test_path_helpers_support_posix_paths(tmp_path):
    candidates = tmp_path / "MQL5" / "Experts" / "group" / "candidates"
    assert experts_relpath(candidates) == "group\\candidates"
    assert mt5_data_dir(candidates) == tmp_path


def test_mt5_data_dir_supports_windows_paths_on_any_host():
    p = r"C:\Users\x\AppData\Roaming\MetaQuotes\Terminal\ABC\MQL5\Experts\bots"
    assert str(mt5_data_dir(p)) == (r"C:\Users\x\AppData\Roaming\MetaQuotes\Terminal\ABC")


# --- INI builders --------------------------------------------------------


def test_backtest_ini_optimization_0_with_inputs(tmp_path):
    ini = build_backtest_ini(
        "candidate bots\\Bot.ex5",
        "US100.cash",
        COMMON,
        tmp_path / "r2",
        inputs=[("StopLossCoef1", 1.0)],
    )
    assert "Optimization=0" in ini
    assert "Symbol=US100.cash" in ini
    assert "[TesterInputs]" in ini
    assert "StopLossCoef1=1" in ini


def test_dry_run_generates_per_symbol_backtests_with_relative_reports(tmp_path):
    candidates = tmp_path / "MQL5" / "Experts" / "candidates"
    candidates.mkdir(parents=True)
    (candidates / "Bot.ex5").write_bytes(b"")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "folders": {"candidates": str(candidates)},
                "common": {"symbols": ["EURUSD", "US100.cash"]},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"

    assert main(["--config", str(config), "--output-dir", str(output), "--dry-run"]) == 0

    inis = sorted((output / "mt5_ini").glob("*.ini"))
    assert [path.name for path in inis] == [
        "Bot__R1_EURUSD.ini",
        "Bot__R1_US100_cash.ini",
    ]
    for path in inis:
        text = path.read_text(encoding="utf-8")
        assert "Optimization=0" in text
        assert "Optimization=3" not in text
        report = next(line for line in text.splitlines() if line.startswith("Report="))
        assert report.startswith("Report=mt5rt_Bot_R1_")
        assert str(output.resolve()) not in report


def test_lock_takes_over_stale_pid(tmp_path):
    lock = tmp_path / ".pipeline.lock"
    lock.write_text("999999999")
    handle = acquire_lock(lock)
    assert handle is not None
    assert lock.read_text().strip() == str(os.getpid())
    release_lock(handle)


def test_lock_release_allows_next_owner_without_unlinking_lock_file(tmp_path):
    lock = tmp_path / ".pipeline.lock"
    first = acquire_lock(lock)
    assert first is not None
    assert lock.exists()
    release_lock(first)
    second = acquire_lock(lock)
    assert second is not None
    release_lock(second)
    assert lock.exists()


def test_shared_lock_contends_across_output_directories(tmp_path):
    candidates = tmp_path / "MQL5" / "Experts" / "candidates"
    candidates.mkdir(parents=True)
    terminal = tmp_path / "terminal64.exe"
    lock_a = shared_lock_path(candidates, terminal)
    lock_b = shared_lock_path(candidates, terminal)

    assert lock_a == lock_b == tmp_path / ".mt5-robot-tester.lock"
    handle = acquire_lock(lock_a)
    assert handle is not None
    assert acquire_lock(lock_b) is None
    release_lock(handle)


def test_os_lock_excludes_a_second_process(tmp_path):
    lock = tmp_path / ".pipeline.lock"
    scripts_dir = Path(__file__).resolve().parents[1]
    child_code = (
        "import sys\n"
        f"sys.path.insert(0, {str(scripts_dir)!r})\n"
        "from pathlib import Path\n"
        "from mt5_batch_tester import acquire_lock, release_lock\n"
        f"h = acquire_lock(Path({str(lock)!r}))\n"
        "print('locked' if h is not None else 'failed', flush=True)\n"
        "sys.stdin.readline()\n"
        "release_lock(h)\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", child_code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "locked"
        assert acquire_lock(lock) is None
    finally:
        child.stdin.write("\n")
        child.stdin.flush()
        child.wait(timeout=10)


def test_unconfirmed_terminal_blocker_prevents_future_lock(tmp_path):
    lock = tmp_path / ".pipeline.lock"
    first = acquire_lock(lock)
    assert first is not None
    blocker = block_lock(lock, TerminalTerminationError(4321, "timeout"))
    release_lock(first)

    assert blocker == lock_blocker_path(lock)
    assert acquire_lock(lock) is None
    payload = json.loads(blocker.read_text(encoding="utf-8"))
    assert payload["pid"] == 4321
    assert payload["reason"] == "unconfirmed_mt5_termination"


def test_interrupted_tester_terminates_exact_child(tmp_path, monkeypatch):
    class Proc:
        def __init__(self):
            self.running = True
            self.terminated = False

        def poll(self):
            return None if self.running else 0

        def terminate(self):
            self.terminated = True
            self.running = False

        def wait(self, _timeout):
            return 0

        def kill(self):
            self.running = False

    proc = Proc()
    monkeypatch.setattr(batch.subprocess, "Popen", lambda _cmd: proc)
    monkeypatch.setattr(
        batch.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt)
    )

    with pytest.raises(KeyboardInterrupt):
        batch.run_tester(
            tmp_path / "terminal64.exe",
            tmp_path / "test.ini",
            tmp_path,
            "report",
            30,
            False,
            (".htm",),
        )

    assert proc.terminated is True
    assert proc.poll() == 0


def test_stale_report_cleanup_failure_never_launches_terminal(tmp_path, monkeypatch):
    (tmp_path / "report.htm").mkdir()
    launched = []
    monkeypatch.setattr(batch.subprocess, "Popen", lambda _cmd: launched.append(True))

    report, status = batch.run_tester(
        tmp_path / "terminal64.exe",
        tmp_path / "test.ini",
        tmp_path,
        "report",
        30,
        False,
        (".htm",),
    )

    assert report is None
    assert status == "stale_report_cleanup_failed"
    assert launched == []


def test_timeout_with_partial_report_is_never_success(tmp_path, monkeypatch):
    class Proc:
        def poll(self):
            return None

    def launch(_cmd):
        (tmp_path / "report.htm").write_text("partial", encoding="utf-8")
        return Proc()

    monkeypatch.setattr(batch.subprocess, "Popen", launch)
    monkeypatch.setattr(batch, "terminate_child_process", lambda _proc: True)

    report, status = batch.run_tester(
        tmp_path / "terminal64.exe",
        tmp_path / "test.ini",
        tmp_path,
        "report",
        0,
        False,
        (".htm",),
    )

    assert report is None
    assert status == "timeout"


def test_timeout_reports_unconfirmed_termination(tmp_path, monkeypatch):
    class Proc:
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(batch.subprocess, "Popen", lambda _cmd: Proc())
    monkeypatch.setattr(batch, "terminate_child_process", lambda _proc: False)

    with pytest.raises(TerminalTerminationError, match="PID 4321"):
        batch.run_tester(
            tmp_path / "terminal64.exe",
            tmp_path / "test.ini",
            tmp_path,
            "report",
            0,
            False,
            (".htm",),
        )


def test_nonzero_terminal_exit_quarantines_even_parseable_report(tmp_path, monkeypatch):
    class Proc:
        pid = 4321

        def poll(self):
            return 7

    def launch(_cmd):
        (tmp_path / "report.htm").write_text(
            "<table><tr><td>Total Net Profit:</td><td>50000</td></tr></table>",
            encoding="utf-8",
        )
        return Proc()

    monkeypatch.setattr(batch.subprocess, "Popen", launch)

    report, status = batch.run_tester(
        tmp_path / "terminal64.exe",
        tmp_path / "test.ini",
        tmp_path,
        "report",
        30,
        False,
        (".htm",),
    )

    assert report is None
    assert status == "terminal_exit_7"
    assert not (tmp_path / "report.htm").exists()
    assert len(list(tmp_path.glob("report.failed-*.htm"))) == 1


def test_main_stops_after_first_bot_when_terminal_exit_is_unconfirmed(tmp_path, monkeypatch):
    candidates = tmp_path / "MQL5" / "Experts" / "candidates"
    candidates.mkdir(parents=True)
    (candidates / "A.ex5").write_bytes(b"a")
    (candidates / "B.ex5").write_bytes(b"b")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "folders": {
                    "candidates": str(candidates),
                    "in_testing": str(tmp_path / "in-testing"),
                    "finalists": str(tmp_path / "finalists"),
                },
                "common": {"symbols": ["EURUSD"]},
            }
        ),
        encoding="utf-8",
    )
    launches = []

    class Proc:
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(
        batch, "find_terminal", lambda _explicit, _configured: tmp_path / "terminal64.exe"
    )
    monkeypatch.setattr(
        batch.subprocess,
        "Popen",
        lambda cmd: launches.append(cmd) or Proc(),
    )
    monkeypatch.setattr(batch, "terminate_child_process", lambda _proc: False)

    result = main(
        [
            "--config",
            str(config),
            "--output-dir",
            str(tmp_path / "output"),
            "--timeout",
            "-1",
        ]
    )

    lock = tmp_path / ".mt5-robot-tester.lock"
    assert result == 2
    assert len(launches) == 1
    assert lock_blocker_path(lock).exists()
    assert not list((tmp_path / "output").glob("leaderboard_*"))


@pytest.mark.parametrize("failing_write", ["fatal_log", "fatal_state"])
def test_fatal_blocker_survives_output_reporting_failure(tmp_path, monkeypatch, failing_write):
    candidates = tmp_path / "MQL5" / "Experts" / "candidates"
    candidates.mkdir(parents=True)
    (candidates / "A.ex5").write_bytes(b"a")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "folders": {
                    "candidates": str(candidates),
                    "in_testing": str(tmp_path / "in-testing"),
                    "finalists": str(tmp_path / "finalists"),
                },
                "common": {"symbols": ["EURUSD"]},
            }
        ),
        encoding="utf-8",
    )

    class Proc:
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(
        batch, "find_terminal", lambda _explicit, _configured: tmp_path / "terminal64.exe"
    )
    monkeypatch.setattr(batch.subprocess, "Popen", lambda _cmd: Proc())
    monkeypatch.setattr(batch, "terminate_child_process", lambda _proc: False)

    real_log = Pipeline.log
    real_save = Pipeline._save_state

    def maybe_fail_log(self, message):
        if failing_write == "fatal_log" and "ERROR FATAL" in message:
            raise OSError("output log full")
        return real_log(self, message)

    def maybe_fail_save(self):
        fatal = any(
            "could not confirm termination" in str(state.get("reason"))
            for state in self.state["bots"].values()
        )
        if failing_write == "fatal_state" and fatal:
            raise OSError("output state full")
        return real_save(self)

    monkeypatch.setattr(Pipeline, "log", maybe_fail_log)
    monkeypatch.setattr(Pipeline, "_save_state", maybe_fail_save)

    result = main(
        [
            "--config",
            str(config),
            "--output-dir",
            str(tmp_path / "output"),
            "--timeout",
            "-1",
        ]
    )

    lock = tmp_path / ".mt5-robot-tester.lock"
    assert result == 2
    assert lock_blocker_path(lock).exists()
    assert not list((tmp_path / "output").glob("leaderboard_*"))


def test_optimize_param_ini_range_syntax(tmp_path):
    strategy_params = [("GannHiLoPeriod1", 86), ("PriceEntryMult1", 1.5)]
    ini = build_optimize_param_ini(
        "candidate bots\\Bot.ex5",
        "US100.cash",
        COMMON,
        tmp_path / "r3",
        strategy_params,
        "GannHiLoPeriod1",
        (43, 4, 129),
    )
    assert "Optimization=1" in ini
    assert "GannHiLoPeriod1=43||43||4||129||Y" in ini
    assert "PriceEntryMult1=1.5" in ini  # fixed


def _pipeline(tmp_path):
    data = tmp_path / "data"
    candidates = data / "MQL5" / "Experts" / "candidates"
    in_testing = data / "MQL5" / "Experts" / "in-testing"
    finalists = data / "MQL5" / "Experts" / "finalists"
    candidates.mkdir(parents=True)
    config = {
        "folders": {
            "candidates": str(candidates),
            "in_testing": str(in_testing),
            "finalists": str(finalists),
        },
        "common": {"symbols": ["EURUSD"]},
    }
    pipe = Pipeline(config, tmp_path / "output", None, 5, False, False)
    return pipe, candidates, in_testing, finalists


def test_move_bot_reports_missing_folder_configuration_in_english(tmp_path):
    pipe, candidates, _, _ = _pipeline(tmp_path)
    bot = candidates / "Bot.ex5"

    pipe.in_testing = None
    assert pipe._move_bot(bot, "rejected", None) == (
        False,
        "missing folders.in_testing",
    )

    pipe.in_testing = tmp_path / "in-testing"
    pipe.finalists = None
    assert pipe._move_bot(bot, "finalist", []) == (
        False,
        "missing folders.finalists",
    )


def test_round1_rejection_moves_candidate_and_records_truth(tmp_path):
    pipe, candidates, in_testing, _ = _pipeline(tmp_path)
    bot = candidates / "Bot.ex5"
    bot.write_bytes(b"candidate")
    pipe.state["bots"]["Bot"] = {
        "status": "round1",
        "round1": {"passed": False, "reason": "too few profitable symbols"},
        "fingerprint": pipe._execution_fingerprint("Bot", bot),
    }

    state = pipe.process_bot(bot)

    assert state["status"] == "done"
    assert state["moved"] is True
    assert not bot.exists()
    assert (in_testing / "Bot.ex5").read_bytes() == b"candidate"


def test_round1_execution_failure_keeps_candidate_retryable(tmp_path, monkeypatch):
    pipe, candidates, in_testing, _ = _pipeline(tmp_path)
    bot = candidates / "Bot.ex5"
    bot.write_bytes(b"candidate")
    monkeypatch.setattr(
        pipe,
        "_run",
        lambda *_args, **_kwargs: (None, "no_report", tmp_path / "r1.ini"),
    )

    state = pipe.process_bot(bot)

    assert state["status"] == "error"
    assert state["reason"] == "R1 EURUSD: no_report"
    assert bot.exists()
    assert not (in_testing / bot.name).exists()


def test_resume_retries_round2_error_instead_of_skipping(tmp_path, monkeypatch):
    pipe, candidates, in_testing, finalists = _pipeline(tmp_path)
    pipe.resume = True
    pipe.gates["round1_min_positive"] = 1
    pipe.gates["round1_min_profit_multiple"] = 0
    bot = candidates / "Bot.ex5"
    bot.write_bytes(b"candidate")
    calls = []

    def fake_run(_ini, _name, stub, _report_name, _exts):
        calls.append(stub)
        if stub == "R2" and calls.count("R2") == 1:
            return None, "no_report", tmp_path / "r2.ini"
        return tmp_path / f"{stub}.htm", "ok", tmp_path / f"{stub}.ini"

    metrics = {
        "net_profit": 50000,
        "profit_pct": 500,
        "drawdown_max_pct": 5,
        "pct_positive_months": 80,
        "all_years_positive": True,
        "lr_correlation": 0.95,
        "max_months_to_new_high": 1,
        "total_trades": 10,
    }
    monkeypatch.setattr(pipe, "_run", fake_run)
    monkeypatch.setattr(batch, "parse_report_file", lambda *_args: metrics)

    first = pipe.process_bot(bot)
    first_status = first["status"]
    second = pipe.process_bot(bot)

    assert first_status == "error"
    assert second["status"] == "done"
    assert calls == ["R1_EURUSD", "R2", "R2"]
    assert not bot.exists()
    assert (in_testing / bot.name).exists()
    assert (finalists / bot.name).exists()


def test_resume_fingerprint_changes_for_ea_set_symbols_and_period(tmp_path):
    pipe, candidates, *_ = _pipeline(tmp_path)
    bot = candidates / "Bot.ex5"
    bot.write_bytes(b"version-1")
    set_path = bot.with_suffix(".set")
    set_path.write_text("MagicNumber=1\nParam=10\n", encoding="utf-8")
    original = pipe._execution_fingerprint("Bot", bot)

    bot.write_bytes(b"version-2")
    assert pipe._execution_fingerprint("Bot", bot) != original
    bot.write_bytes(b"version-1")

    set_path.write_text("MagicNumber=1\nParam=20\n", encoding="utf-8")
    assert pipe._execution_fingerprint("Bot", bot) != original
    set_path.write_text("MagicNumber=1\nParam=10\n", encoding="utf-8")

    pipe.common["symbols"] = ["GBPUSD"]
    assert pipe._execution_fingerprint("Bot", bot) != original
    pipe.common["symbols"] = ["EURUSD"]

    pipe.common["from"] = "2021.01.01"
    assert pipe._execution_fingerprint("Bot", bot) != original


def test_round3_tests_and_saves_the_same_complete_input_set(tmp_path, monkeypatch):
    pipe, *_ = _pipeline(tmp_path)
    pipe.r3["params_after_magic"] = 1
    state = {
        "inputs": [
            ("NonDefaultBeforeMagic", 77),
            ("MagicNumber", 42),
            ("OptimizedParam", 10),
            ("NonSelectedAfter", 99),
        ],
        "round2": {"net_profit": 100},
    }
    inis = []

    def fake_run(ini, _name, stub, _report_name, _exts):
        inis.append((stub, ini))
        return tmp_path / f"{stub}.xml", "ok", tmp_path / f"{stub}.ini"

    monkeypatch.setattr(pipe, "_run", fake_run)
    monkeypatch.setattr(
        batch,
        "parse_passes",
        lambda _path: [
            {
                "profit": 200,
                "inputs": {"OptimizedParam": 15},
            }
        ],
    )
    monkeypatch.setattr(
        batch,
        "parse_report_file",
        lambda *_args: {"net_profit": 50000, "drawdown_max_pct": 5},
    )

    result = pipe._round3("Bot", "Bot.ex5", "EURUSD", state)
    final_ini = dict(inis)["final"]
    saved = tmp_path / "Bot.set"
    pipe._write_set(saved, result["best_set"])

    assert result["status"] == "ok"
    assert "NonDefaultBeforeMagic=77" in final_ini
    assert "MagicNumber=42" in final_ini
    assert "OptimizedParam=15" in final_ini
    assert "NonSelectedAfter=99" in final_ini
    assert saved.read_text(encoding="utf-8").splitlines() == [
        "NonDefaultBeforeMagic=77",
        "MagicNumber=42",
        "OptimizedParam=15",
        "NonSelectedAfter=99",
    ]


def test_move_collision_preserves_source_and_existing_destination(tmp_path):
    pipe, candidates, in_testing, _ = _pipeline(tmp_path)
    bot = candidates / "Bot.ex5"
    bot.write_bytes(b"candidate")
    in_testing.mkdir(parents=True)
    destination = in_testing / bot.name
    destination.write_bytes(b"existing")

    state = pipe._finish("Bot", "rejected", "gate", {}, ex5=bot)

    assert state["status"] == "move_error"
    assert state["moved"] is False
    assert bot.read_bytes() == b"candidate"
    assert destination.read_bytes() == b"existing"


def test_finalist_copy_failure_does_not_move_only_candidate(tmp_path, monkeypatch):
    pipe, candidates, in_testing, finalists = _pipeline(tmp_path)
    bot = candidates / "Bot.ex5"
    bot.write_bytes(b"candidate")

    def fail_copy(*_args, **_kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr(Pipeline, "_copy_exclusive", staticmethod(fail_copy))
    state = pipe._finish("Bot", "finalist", "ok", {}, ex5=bot)

    assert state["status"] == "move_error"
    assert state["moved"] is False
    assert bot.exists()
    assert not (in_testing / bot.name).exists()
    assert not (finalists / bot.name).exists()


def test_finalist_move_failure_rolls_back_created_copy(tmp_path, monkeypatch):
    pipe, candidates, in_testing, finalists = _pipeline(tmp_path)
    bot = candidates / "Bot.ex5"
    bot.write_bytes(b"candidate")

    def fail_move(*_args, **_kwargs):
        raise OSError("move failed")

    monkeypatch.setattr(Pipeline, "_move_exclusive", staticmethod(fail_move))
    state = pipe._finish("Bot", "finalist", "ok", {}, ex5=bot)

    assert state["status"] == "move_error"
    assert state["moved"] is False
    assert bot.exists()
    assert not (in_testing / bot.name).exists()
    assert not (finalists / bot.name).exists()


def test_finalist_copy_happens_before_candidate_move(tmp_path, monkeypatch):
    pipe, candidates, in_testing, finalists = _pipeline(tmp_path)
    bot = candidates / "Bot.ex5"
    bot.write_bytes(b"candidate")
    events = []
    real_copy = Pipeline._copy_exclusive

    def tracked_copy(*args, **kwargs):
        events.append("copy")
        return real_copy(*args, **kwargs)

    def tracked_move(source, destination):
        events.append("move")
        real_copy(source, destination)
        source.unlink()

    monkeypatch.setattr(Pipeline, "_copy_exclusive", staticmethod(tracked_copy))
    monkeypatch.setattr(Pipeline, "_move_exclusive", staticmethod(tracked_move))
    state = pipe._finish("Bot", "finalist", "ok", {}, ex5=bot)

    assert events == ["copy", "move"]
    assert state["status"] == "done"
    assert state["moved"] is True
    assert (finalists / bot.name).exists()
    assert (in_testing / bot.name).exists()


def test_learnings_markdown_stays_under_output_directory(tmp_path):
    pipe, *_ = _pipeline(tmp_path)
    assert pipe._learn_md == pipe.output_dir / "learnings.md"
