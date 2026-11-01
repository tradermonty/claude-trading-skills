"""Exercise public guide examples using fictional, temporary thesis state."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/trader-memory-core/scripts"
sys.path.insert(0, str(ROOT / "scripts"))
from report_skill_doc_drift import python_blocks


@pytest.mark.parametrize("language", ["en", "ja"])
def test_python_examples_import_and_bind_actual_signatures(language):
    """Execute only imports/setup; bind calls without executing state mutations."""
    guide = (ROOT / f"docs/{language}/skills/trader-memory-core.md").read_text()
    checked = 0
    for _, code in python_blocks(guide):
        tree = ast.parse(code)
        setup = []
        checks = []
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Name):
                    checks.append(
                        f"inspect.signature({call.func.id}).bind("
                        + ", ".join(
                            [ast.unparse(arg) for arg in call.args]
                            + [f"{kw.arg}={ast.unparse(kw.value)}" for kw in call.keywords]
                        )
                        + ")"
                    )
                    continue
            setup.append(ast.unparse(node))
        result = subprocess.run(
            [sys.executable, "-c", "import inspect\n" + "\n".join(setup + checks)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
        checked += len(checks)
    assert checked == 6


@pytest.mark.parametrize("language", ["en", "ja"])
def test_actual_python_guide_transition_open_close_sequence(tmp_path, language):
    guide = (ROOT / f"docs/{language}/skills/trader-memory-core.md").read_text()
    steps = []
    for _, code in python_blocks(guide):
        tree = ast.parse(code)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"transition", "open_position", "close"}
            for node in ast.walk(tree)
        ):
            # Only the three trusted, published lifecycle examples, redirected
            # to fictional temporary state; preserve every call argument.
            setup = [node for node in tree.body if not isinstance(node, ast.Expr)]
            calls = [node for node in tree.body if isinstance(node, ast.Expr)]
            steps.extend(ast.unparse(node) for node in setup)
            steps += ["state_dir = fixture_state", "thesis_id = fixture_id"]
            steps.extend(ast.unparse(node) for node in calls)
    program = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(SCRIPTS)!r})
import thesis_store as store
fixture_state = Path({str(tmp_path / "theses")!r})
fixture_id = store.register(fixture_state, {{
    'ticker': 'AAPL', 'thesis_type': 'pivot_breakout',
    'thesis_statement': 'Fictional guide sequence',
    'origin': {{'skill': 'test-skill', 'output_file': 'fictional.json'}},
    '_source_date': '2026-03-14',
}})
""" + "\n".join(steps)
    program += "\nassert store.get(fixture_state, fixture_id)['status'] == 'CLOSED'\n"
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("asset", ["equity", "futures"])
def test_documented_launcher_trim_close_lifecycle(tmp_path, asset):
    """Run the published command shapes through the launcher, offline."""
    env = {**os.environ, "TRADER_MEMORY_CLI_INNER": "1"}
    state_dir = tmp_path / "theses"
    registration = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import thesis_store as store
state = Path(sys.argv[2])
tid = store.register(state, {
    'ticker': 'ES1' if sys.argv[3] == 'futures' else 'AAPL',
    'thesis_type': 'pivot_breakout',
    'thesis_statement': 'Fictional documentation test',
    '_source_date': '2026-03-01',
    'origin': {'skill': 'test-skill', 'output_file': 'fictional.json'},
})
store.transition(state, tid, 'ENTRY_READY', reason='Fictional setup',
                 event_date='2026-03-01')
print(tid)
"""
    result = subprocess.run(
        [sys.executable, "-c", registration, str(SCRIPTS), str(state_dir), asset],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    tid = result.stdout.strip().splitlines()[-1]

    def run(*args):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "trader_memory_cli.py"),
                "store",
                "--state-dir",
                str(state_dir),
                *args,
            ],
            env=env,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )

    if asset == "futures":
        report = tmp_path / "futures.json"
        report.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "symbol": "ES",
                    "direction": "SHORT",
                    "sizing_status": "SIZED",
                    "entry": 5000,
                    "stop": 5020,
                    "contract_spec": {"multiplier": 50, "currency": "USD"},
                    "contracts": 2,
                    "risk_per_contract_usd": 1000,
                    "total_risk_usd": 2000,
                    "risk_pct_of_account": 2,
                }
            )
        )
        run("attach-futures-position", tid, "--report", str(report))
        run(
            "open-position",
            tid,
            "--actual-price",
            "5000",
            "--actual-date",
            "2026-05-10",
            "--event-date",
            "2026-05-10",
        )
        run("trim", tid, "--contracts-sold", "1", "--price", "4950", "--date", "2026-05-12")
        price, date, expected_pnl = "4900", "2026-05-15", 7500
    else:
        run(
            "open-position",
            tid,
            "--actual-price",
            "150",
            "--actual-date",
            "2026-03-16",
            "--shares",
            "2.5",
            "--event-date",
            "2026-03-16",
        )
        run("trim", tid, "--shares-sold", "0.5", "--price", "160.00", "--date", "2026-04-20")
        price, date, expected_pnl = "172", "2026-05-01", 49
    import yaml

    thesis_path = state_dir / f"{tid}.yaml"
    assert yaml.safe_load(thesis_path.read_text())["status"] == "PARTIALLY_CLOSED"
    run("close", tid, "--exit-reason", "target_hit", "--actual-price", price, "--actual-date", date)
    closed = yaml.safe_load(thesis_path.read_text())
    assert closed["status"] == "CLOSED"
    assert closed["outcome"]["pnl_dollars"] == expected_pnl
