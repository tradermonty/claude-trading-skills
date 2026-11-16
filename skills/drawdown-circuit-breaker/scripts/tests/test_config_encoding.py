"""Configuration decoding must not depend on the host locale (#785)."""

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import check_circuit_breaker as circuit
import pytest


def unicode_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"cooldown_hours": "２４", "max_daily_loss_pct": 1.5}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("legacy_encoding", ["ascii", "cp1252"])
def test_config_matches_utf8_baseline_with_legacy_default(tmp_path, monkeypatch, legacy_encoding):
    path = unicode_config(tmp_path)
    args = circuit.build_parser().parse_args(
        ["--account-size", "100000", "--config", str(path), "--losing-streak-n", "4"]
    )
    baseline = asdict(circuit.build_config(args))
    real_open = Path.open

    def legacy_open(target, *args, **kwargs):
        # Simulate default text decoding without interfering with an explicit
        # encoding or with unrelated thesis/report I/O.
        if target == path and kwargs.get("encoding") is None:
            kwargs["encoding"] = legacy_encoding
        return real_open(target, *args, **kwargs)

    monkeypatch.setattr(Path, "open", legacy_open)
    assert asdict(circuit.build_config(args)) == baseline
    assert baseline["cooldown_hours"] == 24.0
    assert baseline["max_daily_loss_pct"] == 1.5
    assert baseline["losing_streak_n"] == 4


def test_cli_reads_utf8_config_in_non_utf8_locale(tmp_path):
    path = unicode_config(tmp_path)
    env = dict(
        os.environ,
        LC_ALL="C",
        LANG="C",
        PYTHONUTF8="0",
        PYTHONCOERCECLOCALE="0",
        PYTHONIOENCODING="utf-8",
    )
    probe = subprocess.run(
        [sys.executable, "-c", "import locale; print(locale.getpreferredencoding(False))"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    if probe.stdout.strip().lower().replace("-", "") == "utf8":
        pytest.skip("host keeps UTF-8 in the C locale; legacy defaults covered by simulation")
    out = tmp_path / "reports"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(circuit.__file__)),
            "--account-size",
            "100000",
            "--state-dir",
            str(tmp_path / "missing-state"),
            "--config",
            str(path),
            "--as-of",
            "2026-11-16",
            "--output-dir",
            str(out),
            "--json-only",
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    report = json.loads(
        next(out.glob("circuit_breaker_decision_*.json")).read_text(encoding="utf-8")
    )
    assert report["config"]["cooldown_hours"] == 24.0
    assert report["config"]["max_daily_loss_pct"] == 1.5


@pytest.mark.parametrize(
    "contents", [b"{broken", b"[]", b'{"cooldown_hours": 0}', b'{"cooldown_hours": "\xff"}']
)
def test_bad_config_still_fails_cleanly_without_reports(tmp_path, capsys, contents):
    path = tmp_path / "bad.json"
    path.write_bytes(contents)
    out = tmp_path / "reports"
    rc = circuit.main(
        ["--account-size", "100000", "--config", str(path), "--output-dir", str(out), "--json-only"]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error:")
    assert "Traceback" not in captured.err
    assert not out.exists()
