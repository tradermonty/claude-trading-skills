"""Offline evidence for the operational gate, independently of contract drift."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import check_provider_contracts as cli


def _report():
    return {
        "provider": "fmp",
        "generated_at": "2026-11-01T12:00:00+00:00",
        "budget": {"used": 1, "max": 1},
        "ok": True,
        "contracts": {
            "profile": {"status": 200, "rows": 1, "ok": True, "anomalies": [], "deprecations": []}
        },
    }


def _errors(report, *, outcome="success", code=0, expected=None):
    return cli.health_errors(report, expected or {"profile"}, "fmp", outcome, code)


def test_healthy_and_legacy_fmp_report():
    report = _report()
    assert _errors(report) == []
    del report["provider"]
    assert _errors(report) == []


def test_field_type_nullability_drift_is_report_only():
    report = _report()
    report["ok"] = report["contracts"]["profile"]["ok"] = False
    report["contracts"]["profile"]["anomalies"] = [
        {"code": "missing_required_field:symbol", "severity": "fatal", "count": 2}
    ]
    assert _errors(report, outcome="failure", code=1) == []


@pytest.mark.parametrize("status,rows", [(-1, 0), (403, 1), (429, 1), (503, 0), (200, 0)])
def test_no_nonempty_successful_response_fails(status, rows):
    report = _report()
    report["ok"] = report["contracts"]["profile"]["ok"] = False
    report["contracts"]["profile"].update(
        status=status, rows=rows, anomalies=[{"code": "test", "severity": "fatal"}]
    )
    assert _errors(report, outcome="failure", code=1)


def test_partial_availability_remains_report_only():
    report = _report()
    report["contracts"]["quote"] = {
        "status": -1,
        "rows": 0,
        "ok": False,
        "anomalies": [{"code": "http_status:-1", "severity": "fatal"}],
        "deprecations": [],
    }
    report["budget"] = {"used": 2, "max": 2}
    report["ok"] = False
    assert _errors(report, expected={"profile", "quote"}, outcome="failure", code=1) == []


@pytest.mark.parametrize("value", [None, {}, {"contracts": []}, {"ok": True, "contracts": {}}])
def test_missing_empty_or_malformed_report_fails(value):
    assert _errors(value)


@pytest.mark.parametrize(
    "path,value",
    [
        (("provider",), "trader-monty"),
        (("generated_at",), "not-a-time"),
        (("budget", "used"), 0),
        (("budget", "max"), False),
        (("ok",), "true"),
        (("contracts", "profile"), []),
        (("contracts", "profile", "status"), True),
        (("contracts", "profile", "status"), -2),
        (("contracts", "profile", "rows"), -1),
        (("contracts", "profile", "rows"), True),
        (("contracts", "profile", "anomalies"), "error"),
        (("contracts", "profile", "deprecations"), [{}]),
        (("contracts", "profile", "ok"), 1),
    ],
)
def test_bad_evidence_fails(path, value):
    report = _report()
    target = report
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    assert _errors(report)


@pytest.mark.parametrize(
    "outcome,code",
    [("skipped", 0), ("cancelled", 0), ("failure", 2), ("failure", 0), ("success", 1)],
)
def test_probe_process_evidence_must_match_report(outcome, code):
    assert _errors(_report(), outcome=outcome, code=code)


def test_incomplete_contract_set_fails_even_with_one_success():
    assert _errors(_report(), expected={"profile", "quote"})


@pytest.mark.parametrize("contracts", [[], {}, None])
def test_empty_summary_is_visible_but_stays_report_only(tmp_path, capsys, contracts):
    report = {"ok": True, "contracts": contracts}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    assert cli.main(["summarize", "--report", str(path), "--github"]) == 0
    output = capsys.readouterr().out
    assert "ANOMALIES" in output and "::error" in output
    assert "no contracts" in output.lower()


def test_summary_escapes_html_in_every_table_cell():
    report = _report()
    report["contracts"]["<img src=x>"] = report["contracts"].pop("profile")
    report["contracts"]["<img src=x>"]["anomalies"] = [
        {"code": "<script>alert(1)</script>|x", "severity": "fatal"}
    ]
    summary = cli.render_summary(report)
    assert "<img" not in summary and "<script>" not in summary
    assert "&lt;img src=x&gt;" in summary and "&lt;script&gt;" in summary
    assert "\\|x" in summary


def test_health_runs_with_only_standard_library_and_no_network(tmp_path):
    report = _report()
    entry = report["contracts"].pop("profile")
    report["contracts"] = {
        name: copy.deepcopy(entry)
        for name, contract in cli.load_contracts(ROOT).items()
        if contract.provider == "fmp"
    }
    count = len(report["contracts"])
    report["budget"] = {"used": count, "max": count}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    code = """
import runpy, socket, sys
def forbidden(*args, **kwargs):
    raise AssertionError('health must not use network')
socket.socket = forbidden
socket.getaddrinfo = forbidden
sys.argv = ['check_provider_contracts.py', 'health', '--report', sys.argv[1],
            '--probe-outcome', 'success', '--probe-exit-code', '0']
runpy.run_path('scripts/check_provider_contracts.py', run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", code, str(path)],
        cwd=ROOT,
        env={**os.environ, "FMP_API_KEY": ""},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
