"""Issue #703: equity open_position() requires a quantity; doctor exit code.

Self-contained per this suite's convention (helpers are local).
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import thesis_store
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
CLI = SCRIPTS / "trader_memory_cli.py"
QTY_MSG = "requires a share count for an equity thesis"

# -- Helpers -------------------------------------------------------------------


def _register_entry_ready(state_dir, **overrides):
    data = {
        "ticker": "AAPL",
        "thesis_type": "dividend_income",
        "thesis_statement": "AAPL dividend income thesis for testing",
        "origin": {"skill": "test-skill", "output_file": "test_output.json"},
    }
    data.update(overrides)
    tid = thesis_store.register(state_dir, data)
    thesis_store.transition(state_dir, tid, "ENTRY_READY", "validated")
    return tid


def _equity_report(tmp_path: Path, **overrides) -> str:
    report = {
        "schema_version": "1.0",
        "mode": "shares",
        "parameters": {"entry_price": 150.0, "stop_price": 142.0},
        "calculations": {"fixed_fractional": {"method": "fixed_fractional", "shares": 125}},
        "final_recommended_shares": 125,
        "final_position_value": 18750.0,
        "final_risk_dollars": 1000.0,
        "final_risk_pct": 0.01,
    }
    report.update(overrides)
    path = tmp_path / "equity_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return str(path)


def _futures_report(tmp_path: Path) -> str:
    report = {
        "schema_version": "1.0",
        "symbol": "ES",
        "direction": "LONG",
        "sizing_status": "SIZED",
        "no_trade_reason": None,
        "entry": 5000.0,
        "stop": 4980.0,
        "stop_distance_points": 20.0,
        "stop_distance_ticks": "80",
        "contract_spec": {
            "multiplier": 50,
            "tick_size": 0.25,
            "tick_value": 12.5,
            "currency": "USD",
            "source": "cme",
            "verified": "2026-01-01",
        },
        "risk_per_contract_usd": 1000.0,
        "risk_budget_usd": 2000.0,
        "contracts": 2,
        "total_risk_usd": 2000.0,
        "risk_pct_of_account": 2.0,
        "max_contracts_cap_applied": False,
        "fx_rate_used": 1.0,
        "margin_note": "Margin requirements vary by broker.",
        "warnings": [],
        "run_context": {
            "symbol": "ES",
            "as_of": "2026-05-01",
            "schema_version": "1.0",
            "skill": "futures-position-sizer",
        },
    }
    path = tmp_path / "futures_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return str(path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rewrite_yaml(state_dir: Path, tid: str, mutate) -> None:
    thesis = thesis_store.get(state_dir, tid)
    mutate(thesis)
    (state_dir / f"{tid}.yaml").write_text(
        yaml.dump(thesis, default_flow_style=False), encoding="utf-8"
    )


def _make_legacy_active(state_dir: Path, entry_price=4000.0) -> str:
    """Pre-#703 record: ACTIVE with no position (shape of real legacy data).

    The public API can no longer create it, so open with shares=1 and then
    rewrite the YAML with ``position: None``. Index needs no rewrite.
    """
    tid = _register_entry_ready(state_dir)
    thesis_store.open_position(state_dir, tid, entry_price, "2026-03-01T10:00:00+00:00", shares=1)
    _rewrite_yaml(state_dir, tid, lambda t: t.__setitem__("position", None))
    return tid


def _cli(args, **kwargs):
    env = {**os.environ, "TRADER_MEMORY_CLI_INNER": "1"}
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        **kwargs,
    )


# -- Library: quantity guard ---------------------------------------------------


def test_equity_open_without_shares_or_position_rejected(tmp_path: Path):
    sd = tmp_path / "theses"
    tid = _register_entry_ready(sd)
    yaml_before = _sha(sd / f"{tid}.yaml")
    index_before = _sha(sd / thesis_store.INDEX_FILE)

    with pytest.raises(ValueError, match=QTY_MSG):
        thesis_store.open_position(sd, tid, 150.0, "2026-03-01T10:00:00+00:00")

    assert _sha(sd / f"{tid}.yaml") == yaml_before
    assert _sha(sd / thesis_store.INDEX_FILE) == index_before
    assert thesis_store.get(sd, tid)["status"] == "ENTRY_READY"


def test_equity_open_attached_position_without_share_count_rejected(tmp_path: Path):
    """attach_position cannot persist shares=None (schema), so build the
    'position without a share count' state with a direct YAML write."""
    sd = tmp_path / "theses"
    tid = _register_entry_ready(sd)
    _rewrite_yaml(sd, tid, lambda t: t.__setitem__("position", {"sizing_method": "manual"}))

    with pytest.raises(ValueError, match=QTY_MSG):
        thesis_store.open_position(sd, tid, 150.0, "2026-03-01T10:00:00+00:00")
    assert thesis_store.get(sd, tid)["status"] == "ENTRY_READY"

    t = thesis_store.open_position(sd, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=10)
    assert t["status"] == "ACTIVE"
    assert t["position"]["shares"] == 10
    assert t["position"]["shares_remaining"] == 10


def test_equity_open_with_attached_shares_closes_with_full_pnl(tmp_path: Path):
    sd = tmp_path / "theses"
    tid = _register_entry_ready(sd)
    thesis_store.attach_position(sd, tid, _equity_report(tmp_path))
    t = thesis_store.open_position(sd, tid, 150.0, "2026-03-01T10:00:00+00:00")
    assert t["position"]["shares_remaining"] == 125

    closed = thesis_store.close(
        sd,
        tid,
        exit_reason="target_hit",
        actual_price=180.0,
        actual_date="2026-04-01T10:00:00+00:00",
    )
    assert closed["status"] == "CLOSED"
    assert closed["outcome"]["pnl_dollars"] == 3750.0
    assert any("realized_pnl" in h for h in closed["status_history"])


def test_equity_open_explicit_fractional_shares_regression(tmp_path: Path):
    sd = tmp_path / "theses"
    tid = _register_entry_ready(sd)
    t = thesis_store.open_position(sd, tid, 142.10, "2026-05-02T10:00:00+00:00", shares=7.86)
    assert t["status"] == "ACTIVE"
    assert t["position"]["shares"] == 7.86
    assert t["position"]["shares_remaining"] == 7.86


def test_futures_open_after_attach_without_contracts_unaffected(tmp_path: Path):
    sd = tmp_path / "theses"
    tid = _register_entry_ready(sd, ticker="ES1")
    thesis_store.attach_futures_position(sd, tid, _futures_report(tmp_path))
    t = thesis_store.open_position(sd, tid, 5000.0, "2026-05-02T10:00:00+00:00")
    assert t["status"] == "ACTIVE"
    assert t["position"]["quantity"] == 2


def test_quantity_guard_runs_after_nothing_it_would_mask(tmp_path: Path):
    """Existing validation errors keep priority over the quantity error."""
    sd = tmp_path / "theses"
    idea = thesis_store.register(
        sd,
        {
            "ticker": "AAPL",
            "thesis_type": "dividend_income",
            "thesis_statement": "AAPL idea thesis for testing",
            "origin": {"skill": "test-skill", "output_file": "o.json"},
        },
    )
    with pytest.raises(ValueError, match="requires ENTRY_READY") as e1:
        thesis_store.open_position(sd, idea, 150.0, "2026-03-01T10:00:00+00:00")
    assert QTY_MSG not in str(e1.value)

    tid = _register_entry_ready(sd, ticker="MSFT")
    with pytest.raises(ValueError, match="finite actual_price") as e2:
        thesis_store.open_position(sd, tid, float("nan"), "2026-03-01T10:00:00+00:00")
    assert QTY_MSG not in str(e2.value)

    # Positive stop above the fill: existing initial-stop message wins.
    _rewrite_yaml(sd, tid, lambda t: t["exit"].__setitem__("stop_loss", 200.0))
    with pytest.raises(ValueError) as e3:
        thesis_store.open_position(sd, tid, 150.0, "2026-03-01T10:00:00+00:00")
    assert QTY_MSG not in str(e3.value)
    assert "stop" in str(e3.value).lower()


def test_attach_position_on_active_replaces_quantity_and_close_uses_it(tmp_path: Path):
    """Documented in the guide (Step 5): attaching on ACTIVE replaces the
    recorded quantity (shares and shares_remaining) with the report's."""
    sd = tmp_path / "theses"
    tid = _register_entry_ready(sd)
    thesis_store.open_position(sd, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=10)

    t = thesis_store.attach_position(sd, tid, _equity_report(tmp_path))
    assert t["status"] == "ACTIVE"
    assert t["position"]["shares"] == 125
    assert t["position"]["shares_remaining"] == 125
    assert thesis_store.get(sd, tid)["position"]["shares"] == 125

    closed = thesis_store.close(
        sd,
        tid,
        exit_reason="target_hit",
        actual_price=180.0,
        actual_date="2026-04-01T10:00:00+00:00",
    )
    assert closed["outcome"]["pnl_dollars"] == 3750.0  # 30 * 125, not 30 * 10


# -- Library: legacy records ---------------------------------------------------


def test_legacy_active_without_position_still_closes_per_share(tmp_path: Path):
    sd = tmp_path / "theses"
    tid = _make_legacy_active(sd)
    closed = thesis_store.close(
        sd,
        tid,
        exit_reason="target_hit",
        actual_price=4030.0,
        actual_date="2026-04-01T10:00:00+00:00",
    )
    assert closed["status"] == "CLOSED"
    assert closed["outcome"]["pnl_dollars"] == 30.0
    assert all("realized_pnl" not in h for h in closed["status_history"])


def test_legacy_active_zero_entry_price_pnl_pct_none(tmp_path: Path):
    sd = tmp_path / "theses"
    tid = _make_legacy_active(sd, entry_price=0.0)
    closed = thesis_store.close(
        sd,
        tid,
        exit_reason="target_hit",
        actual_price=5.0,
        actual_date="2026-04-01T10:00:00+00:00",
    )
    assert closed["status"] == "CLOSED"
    assert closed["outcome"]["pnl_pct"] is None


def test_legacy_active_without_position_invalidates_and_cannot_trim(tmp_path: Path):
    sd = tmp_path / "theses"
    tid = _make_legacy_active(sd)
    with pytest.raises(ValueError, match="requires a recorded position"):
        thesis_store.trim(sd, tid, shares_sold=1, price=4010.0, date="2026-03-05T10:00:00+00:00")
    t = thesis_store.terminate(
        sd,
        tid,
        terminal_status="INVALIDATED",
        exit_reason="thesis broke",
        actual_price=3970.0,
        actual_date="2026-03-10T10:00:00+00:00",
    )
    assert t["status"] == "INVALIDATED"
    assert t["outcome"]["pnl_dollars"] == -30.0


def test_legacy_active_without_position_passes_doctor(tmp_path: Path):
    """Proves the guard is not in _validate_thesis."""
    sd = tmp_path / "theses"
    _make_legacy_active(sd)
    assert thesis_store.validate_state(sd)["ok"] is True


# -- CLI -----------------------------------------------------------------------


def test_cli_issue_703_repro_open_without_shares_exits_1(tmp_path: Path):
    sd = tmp_path / "theses"
    src = tmp_path / "manual.json"
    src.write_text(
        json.dumps(
            {
                "ticker": "AAPL",
                "thesis_type": "pivot_breakout",
                "thesis_statement": "Fictional issue 703 repro",
                "origin": {"skill": "test-skill", "output_file": "x.json"},
            }
        ),
        encoding="utf-8",
    )
    r = _cli(["ingest", "--source", "manual", "--input", str(src), "--state-dir", str(sd)])
    assert r.returncode == 0, r.stderr
    tid = next(p.stem for p in sd.glob("th_*.yaml"))

    r = _cli(["store", "--state-dir", str(sd), "transition", tid, "ENTRY_READY", "--reason", "go"])
    assert r.returncode == 0, r.stderr

    r = _cli(
        [
            "store",
            "--state-dir",
            str(sd),
            "open-position",
            tid,
            "--actual-price",
            "4000",
            "--actual-date",
            "2026-11-02",
        ]
    )
    assert r.returncode == 1
    assert r.stderr.startswith("ERROR: open_position() requires a share count")
    assert "Traceback" not in r.stderr
    assert r.stdout == ""
    assert thesis_store.get(sd, tid)["status"] == "ENTRY_READY"

    r = _cli(
        [
            "store",
            "--state-dir",
            str(sd),
            "open-position",
            tid,
            "--actual-price",
            "4000",
            "--actual-date",
            "2026-11-02",
            "--shares",
            "10",
        ]
    )
    assert r.returncode == 0, r.stderr
    r = _cli(
        [
            "store",
            "--state-dir",
            str(sd),
            "close",
            tid,
            "--exit-reason",
            "target_hit",
            "--actual-price",
            "4030",
            "--actual-date",
            "2026-11-05",
        ]
    )
    assert r.returncode == 0, r.stderr
    assert thesis_store.get(sd, tid)["outcome"]["pnl_dollars"] == 300.0


def test_cli_open_position_prints_attached_share_count(tmp_path: Path):
    sd = tmp_path / "theses"
    tid = _register_entry_ready(sd)
    thesis_store.attach_position(sd, tid, _equity_report(tmp_path))
    r = _cli(
        [
            "store",
            "--state-dir",
            str(sd),
            "open-position",
            tid,
            "--actual-price",
            "150.0",
            "--actual-date",
            "2026-03-01",
        ]
    )
    assert r.returncode == 0, r.stderr
    assert "→ ACTIVE @ 150.0 x 125" in r.stdout


# -- doctor --------------------------------------------------------------------


def test_doctor_ok_exits_0(tmp_path: Path, capsys):
    _register_entry_ready(tmp_path)
    assert thesis_store.main(["--state-dir", str(tmp_path), "doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_doctor_missing_index_exits_1(tmp_path: Path, capsys):
    tid = _register_entry_ready(tmp_path)
    (tmp_path / thesis_store.INDEX_FILE).unlink()
    assert thesis_store.main(["--state-dir", str(tmp_path), "doctor"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["missing_in_index"] == [tid]


@pytest.mark.parametrize("kind", ["orphaned_index", "schema_error", "index_drift"])
def test_doctor_not_ok_exits_1(tmp_path: Path, capsys, kind):
    tid = _register_entry_ready(tmp_path)
    if kind == "orphaned_index":
        (tmp_path / f"{tid}.yaml").unlink()
    elif kind == "schema_error":
        _rewrite_yaml(tmp_path, tid, lambda t: t.__setitem__("status", "NOT_A_STATUS"))
    else:
        idx_path = tmp_path / thesis_store.INDEX_FILE
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        idx["theses"][tid]["next_review_date"] = "1999-01-01"
        idx_path.write_text(json.dumps(idx), encoding="utf-8")
    assert thesis_store.main(["--state-dir", str(tmp_path), "doctor"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


def test_doctor_exit_code_through_launcher(tmp_path: Path):
    tid = _register_entry_ready(tmp_path)
    (tmp_path / thesis_store.INDEX_FILE).unlink()
    r = _cli(["store", "--state-dir", str(tmp_path), "doctor"])
    assert r.returncode == 1
    assert json.loads(r.stdout)["ok"] is False
    assert "Traceback" not in r.stderr
    assert tid in r.stdout


def test_doctor_existing_empty_state_dir_exits_0(tmp_path: Path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert thesis_store.main(["--state-dir", str(empty), "doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_doctor_nonexistent_or_file_state_dir_errors(tmp_path: Path):
    missing = tmp_path / "nope"
    with pytest.raises(FileNotFoundError, match="state directory not found or not a directory"):
        thesis_store.main(["--state-dir", str(missing), "doctor"])
    a_file = tmp_path / "not_a_dir"
    a_file.write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="state directory not found or not a directory"):
        thesis_store.main(["--state-dir", str(a_file), "doctor"])

    for target in (missing, a_file):
        r = _cli(["store", "--state-dir", str(target), "doctor"])
        assert r.returncode == 1
        assert "ERROR: state directory not found or not a directory" in r.stderr
        assert "Traceback" not in r.stderr
