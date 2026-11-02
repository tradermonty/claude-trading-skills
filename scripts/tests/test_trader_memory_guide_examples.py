"""Exercise public guide examples using fictional, temporary thesis state."""

import ast
import json
import os
import re
import shlex
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


@pytest.mark.parametrize("language", ["en", "ja"])
@pytest.mark.parametrize("asset", ["equity", "futures"])
def test_documented_launcher_trim_close_lifecycle(tmp_path, asset, language):
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

    guide = (ROOT / f"docs/{language}/skills/trader-memory-core.md").read_text()
    commands = []
    for block in re.findall(r"```bash\n(.*?)```", guide, re.DOTALL):
        if "--contracts-sold" not in block and "--shares-sold" not in block:
            continue
        if ("--contracts-sold" in block) != (asset == "futures"):
            continue
        for line in block.replace("\\\n", " ").splitlines():
            if not line.startswith("python3 "):
                continue
            argv = shlex.split(line)
            substitutions = {
                "$THESIS_ID": tid,
                "state/theses/": str(state_dir),
                "reports/futures_position_es.json": str(tmp_path / "futures.json"),
            }
            commands.append([substitutions.get(arg, arg) for arg in argv[2:]])
    assert len(commands) == (4 if asset == "futures" else 1)

    def run(args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "trader_memory_cli.py"), *args],
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
        expected_pnl = 7500
    else:
        # The equity guide's trim needs an already open position. These setup
        # and final-close calls are fixtures; the trim argv comes from the page.
        run(
            [
                "store",
                "--state-dir",
                str(state_dir),
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
            ]
        )
        expected_pnl = 49
    import yaml

    thesis_path = state_dir / f"{tid}.yaml"
    for args in commands:
        if "close" in args:
            assert yaml.safe_load(thesis_path.read_text())["status"] == "PARTIALLY_CLOSED"
        run(args)
    if asset == "equity":
        assert yaml.safe_load(thesis_path.read_text())["status"] == "PARTIALLY_CLOSED"
        run(
            [
                "store",
                "--state-dir",
                str(state_dir),
                "close",
                tid,
                "--exit-reason",
                "target_hit",
                "--actual-price",
                "172",
                "--actual-date",
                "2026-05-01",
            ]
        )
    closed = yaml.safe_load(thesis_path.read_text())
    assert closed["status"] == "CLOSED"
    assert closed["outcome"]["pnl_dollars"] == expected_pnl


@pytest.mark.parametrize("language", ["en", "ja"])
def test_inline_api_examples_bind_actual_signatures(language):
    guide = (ROOT / f"docs/{language}/skills/trader-memory-core.md").read_text()
    # Inline call examples are complete; zero-argument mentions in quoted error
    # messages and prose are names, not executable examples.
    calls = []
    for inline in re.findall(r"(?<!`)`([^`\n]+)`(?!`)", guide):
        if not re.match(r"(?:terminate|link_report|attach_position|open_position)\(", inline):
            continue
        call = ast.parse(inline, mode="eval").body
        if not call.args and not call.keywords:
            continue
        assert not any(isinstance(n, ast.Constant) and n.value is Ellipsis for n in ast.walk(call))
        # Replace values, preserving argument count and keyword names.
        values = ["None" for _ in call.args] + [f"{kw.arg}=None" for kw in call.keywords]
        calls.append(f"inspect.signature(store.{call.func.id}).bind({', '.join(values)})")
    assert len(calls) == 5
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys, inspect\nsys.path.insert(0, {str(SCRIPTS)!r})\nimport thesis_store as store\n"
            + "\n".join(calls),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
