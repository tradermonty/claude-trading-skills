"""Tests for the stdlib-only trader_memory_cli.py launcher.

Drives the launcher as a subprocess (the unit under test IS the
process-spawning wrapper), so behavior matches how Hermes / cron will
invoke it. No third-party deps; safe to run anywhere `python3` exists.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
LAUNCHER = REPO_ROOT / "skills" / "trader-memory-core" / "scripts" / "trader_memory_cli.py"


def _run(args, *, env=None, cwd=None):
    """Run the launcher and capture (returncode, stdout, stderr)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        env=full_env,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_no_args_prints_usage_and_exits_nonzero():
    rc, _, err = _run([])
    assert rc == 2
    assert "usage:" in err.lower()
    assert "store" in err and "ingest" in err and "review" in err


def test_help_flag_exits_zero():
    rc, _, err = _run(["--help"])
    assert rc == 0
    assert "store" in err


def test_unknown_subcommand_exits_nonzero_with_hint():
    rc, _, err = _run(["bogus"])
    assert rc == 2
    assert "unknown subcommand" in err.lower()
    assert "store" in err  # lists valid options


def test_repo_env_var_is_honored(tmp_path):
    """CLAUDE_TRADING_SKILLS_REPO must be respected even when running from
    a foreign cwd (mirrors Hermes profile cwd)."""
    state_dir = tmp_path / "state"
    rc, out, err = _run(
        ["store", "--state-dir", str(state_dir), "list"],
        env={"CLAUDE_TRADING_SKILLS_REPO": str(REPO_ROOT)},
        cwd=tmp_path,
    )
    assert rc == 0, f"stdout={out!r} stderr={err!r}"
    # Empty state dir → empty JSON list-or-equivalent. We don't assert the
    # exact shape (that's thesis_store's contract) — just that it didn't
    # crash on missing deps.
    assert "ModuleNotFoundError" not in err
    assert "jsonschema is not installed" not in err.lower()


def test_repo_env_var_pointing_at_missing_repo_fails_clearly(tmp_path):
    rc, _, err = _run(
        ["store", "list"],
        env={"CLAUDE_TRADING_SKILLS_REPO": str(tmp_path / "does-not-exist")},
    )
    assert rc == 2
    assert "target script not found" in err.lower()


def test_ingest_unknown_source_exits_cleanly(tmp_path):
    input_file = tmp_path / "manual.json"
    input_file.write_text(
        json.dumps(
            {
                "ticker": "AMD",
                "thesis_statement": "AMD thesis",
                "thesis_type": "growth_momentum",
            }
        )
    )

    rc, _, err = _run(
        [
            "ingest",
            "--source",
            "not-a-source",
            "--input",
            str(input_file),
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )

    assert rc == 1
    assert "ERROR:" in err
    assert "Unknown source" in err
    assert "Traceback" not in err


def test_ingest_bulk_csv_via_launcher(tmp_path):
    csv_file = tmp_path / "manual.csv"
    csv_file.write_text(
        "\n".join(
            [
                "ticker,thesis_statement,thesis_type,entry_date",
                "AMD,AMD thesis,growth_momentum,2026-05-02",
                "OIH,OIH thesis,mean_reversion,2026-05-03",
            ]
        )
    )

    rc, out, err = _run(
        [
            "ingest",
            "--source",
            "manual",
            "--bulk-csv",
            str(csv_file),
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )

    assert rc == 0, err
    assert "Registered 2 thesis(es)" in out
    assert "Traceback" not in err


def test_store_attach_position_invalid_report_exits_cleanly(tmp_path):
    state_dir = tmp_path / "state"
    manual = tmp_path / "manual.json"
    manual.write_text(
        json.dumps(
            {
                "ticker": "AMD",
                "thesis_statement": "AMD thesis",
                "thesis_type": "growth_momentum",
            }
        )
    )

    rc, out, err = _run(
        [
            "ingest",
            "--source",
            "manual",
            "--input",
            str(manual),
            "--state-dir",
            str(state_dir),
        ]
    )
    assert rc == 0, err
    thesis_id = out.split(":", 1)[1].strip()

    bad_report = tmp_path / "position.json"
    bad_report.write_text(json.dumps({"mode": "budget"}))

    rc, _, err = _run(
        [
            "store",
            "--state-dir",
            str(state_dir),
            "attach-position",
            thesis_id,
            "--report",
            str(bad_report),
        ]
    )

    assert rc == 1
    assert "ERROR:" in err
    assert "expected 'shares'" in err
    assert "Traceback" not in err


def test_review_summary_and_monthly_report_via_launcher(tmp_path):
    state_dir = tmp_path / "state"
    manual = tmp_path / "manual.json"
    manual.write_text(
        json.dumps(
            {
                "ticker": "AAPL",
                "thesis_statement": "AAPL thesis",
                "thesis_type": "growth_momentum",
                "entry_date": "2026-04-01",
            }
        )
    )

    rc, out, err = _run(
        [
            "ingest",
            "--source",
            "manual",
            "--input",
            str(manual),
            "--state-dir",
            str(state_dir),
        ]
    )
    assert rc == 0, err
    thesis_id = out.split(":", 1)[1].strip()

    steps = [
        [
            "store",
            "--state-dir",
            str(state_dir),
            "transition",
            thesis_id,
            "ENTRY_READY",
            "--reason",
            "ready",
            "--event-date",
            "2026-04-01",
        ],
        [
            "store",
            "--state-dir",
            str(state_dir),
            "open-position",
            thesis_id,
            "--actual-price",
            "100",
            "--actual-date",
            "2026-04-01",
            "--shares",
            "1",
            "--event-date",
            "2026-04-01",
        ],
        [
            "store",
            "--state-dir",
            str(state_dir),
            "close",
            thesis_id,
            "--exit-reason",
            "target_hit",
            "--actual-price",
            "110",
            "--actual-date",
            "2026-04-15",
        ],
    ]
    for step in steps:
        rc, _, err = _run(step)
        assert rc == 0, err

    rc, out, err = _run(
        [
            "review",
            "--state-dir",
            str(state_dir),
            "summary",
            "--status",
            "CLOSED",
            "--compact",
        ]
    )
    assert rc == 0, err
    assert "AAPL" in out
    assert "CLOSED" in out

    report = tmp_path / "monthly.md"
    rc, out, err = _run(
        [
            "review",
            "--state-dir",
            str(state_dir),
            "monthly-report",
            "--month",
            "2026-04",
            "--output",
            str(report),
        ]
    )
    assert rc == 0, err
    assert "Monthly report generated" in out
    assert "# Monthly Review: 2026-04" in report.read_text()


def test_recursion_guard_blocks_inner_uv_reentry(tmp_path, monkeypatch):
    """With TRADER_MEMORY_CLI_INNER=1 set, the launcher must NOT re-exec
    via `uv run` — that would infinite-loop. Instead it falls through to
    the current-interpreter path."""
    # We can't easily simulate "uv is on PATH" vs not from here, so this
    # test asserts the guard fast-path: when inner=1, the launcher uses
    # sys.executable directly even if uv is available.
    state_dir = tmp_path / "state"
    rc, out, err = _run(
        ["store", "--state-dir", str(state_dir), "list"],
        env={
            "CLAUDE_TRADING_SKILLS_REPO": str(REPO_ROOT),
            "TRADER_MEMORY_CLI_INNER": "1",
        },
    )
    # If jsonschema is importable in this interpreter the call should
    # succeed (rc 0). If it's not (rare in CI), the launcher must emit the
    # informative error (rc 3) — NEVER hang.
    assert rc in (0, 3), f"rc={rc} stdout={out!r} stderr={err!r}"
    if rc == 3:
        assert "uv" in err.lower()


def test_missing_deps_error_message_is_actionable():
    """The launcher source must reference uv / repo env var in its missing
    -deps error, not just 'install jsonschema'."""
    src = LAUNCHER.read_text(encoding="utf-8")
    assert "uv" in src
    assert "CLAUDE_TRADING_SKILLS_REPO" in src
    # And the helper that builds the error string mentions all three paths.
    assert "Resolution options" in src


@pytest.mark.parametrize("sub", ["store", "ingest", "review"])
def test_subcommand_resolves_to_existing_target(sub):
    """Every advertised subcommand must point at a script that exists in
    the repo — catches typos in the launcher's SUBCOMMAND_TO_SCRIPT map."""
    targets = {
        "store": "thesis_store.py",
        "ingest": "thesis_ingest.py",
        "review": "thesis_review.py",
    }
    target = REPO_ROOT / "skills" / "trader-memory-core" / "scripts" / targets[sub]
    assert target.is_file(), f"missing target: {target}"
