"""Tests for the ``summarize`` subcommand of the FMP canary CLI (Issue #332).

``summarize`` renders a canary report as GitHub step-summary markdown and
optional workflow-command annotations. It reports; it never gates (exit 0).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts import check_provider_contracts as cli  # noqa: E402


def _entry(status=200, rows=3, anomalies=(), deprecations=(), ok=True):
    return {
        "status": status,
        "rows": rows,
        "anomalies": [{"code": c, "severity": "fatal"} for c in anomalies],
        "deprecations": [{"code": c, "severity": "deprecation"} for c in deprecations],
        "ok": ok,
    }


def _report(contracts, ok=True):
    return {
        "generated_at": "2026-10-12T12:00:00+00:00",
        "budget": {"max": len(contracts), "used": len(contracts)},
        "ok": ok,
        "contracts": contracts,
    }


@pytest.fixture
def ok_report():
    return _report({"alpha": _entry(), "beta": _entry(rows=5)})


@pytest.fixture
def bad_report():
    return _report(
        {
            "alpha": _entry(),
            "beta": _entry(anomalies=["missing_required_field:symbol"], ok=False),
            "gamma": _entry(deprecations=["legacy_alias_present:mktCap"]),
        },
        ok=False,
    )


def _write(tmp_path: Path, report) -> Path:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


# --- render_summary -------------------------------------------------------


def test_render_summary_all_ok(ok_report):
    md = cli.render_summary(ok_report)
    assert "OK" in md.split("\n\n")[0]
    assert "2026-10-12T12:00:00+00:00" in md
    assert "2/2" in md
    assert "| alpha |" in md
    assert "| beta |" in md
    assert "| Contract | HTTP | Rows |" in md


def test_render_summary_shows_codes(bad_report):
    md = cli.render_summary(bad_report)
    assert "ANOMALIES" in md
    assert "missing_required_field:symbol" in md
    assert "legacy_alias_present:mktCap" in md


def test_render_summary_none_is_no_report_section():
    md = cli.render_summary(None)
    assert "No canary report was produced" in md


def test_render_summary_escapes_pipe_and_newline():
    report = _report({"a|b": _entry(anomalies=["x|y\nz"], ok=False)}, ok=False)
    md = cli.render_summary(report)
    assert "a\\|b" in md
    assert "x\\|y z" in md
    row = [line for line in md.splitlines() if line.startswith("| a")][0]
    assert "\n" not in row


def test_render_summary_redacts_apikey():
    code = "bad https://x.test/y?apikey=REDACTME&z=1"  # pragma: allowlist secret
    report = _report({"a": _entry(anomalies=[code], ok=False)}, ok=False)
    md = cli.render_summary(report)
    assert "REDACTME" not in md
    assert "apikey=REDACTED" in md


# --- annotations ----------------------------------------------------------


def test_annotations_all_ok_empty(ok_report):
    assert cli.annotations(ok_report) == []


def test_annotations_fatal_and_deprecation(bad_report):
    lines = cli.annotations(bad_report)
    errors = [ln for ln in lines if ln.startswith("::error ")]
    warnings = [ln for ln in lines if ln.startswith("::warning ")]
    assert len(errors) == 1 and len(warnings) == 1
    assert errors[0].startswith("::error title=FMP contract anomaly::")
    assert "beta" in errors[0]
    assert "missing_required_field:symbol" in errors[0]
    assert warnings[0].startswith("::warning title=FMP contract deprecation::")
    assert "gamma" in warnings[0]


def test_annotations_http_failure_is_error():
    report = _report({"a": _entry(status=403, rows=0, anomalies=["http_status:403"], ok=False)})
    lines = cli.annotations(report)
    assert len(lines) == 1 and lines[0].startswith("::error ")
    assert "http_status:403" in lines[0]


def test_annotations_escape_percent_and_newlines():
    report = _report({"a": _entry(anomalies=["50%\r\nbad"], ok=False)}, ok=False)
    (line,) = cli.annotations(report)
    assert "\n" not in line and "\r" not in line
    assert "50%25%0D%0Abad" in line


def test_annotations_redact_apikey():
    code = "oops ?apikey=REDACTME"  # pragma: allowlist secret
    report = _report({"a": _entry(anomalies=[code], ok=False)}, ok=False)
    (line,) = cli.annotations(report)
    assert "REDACTME" not in line


def test_annotations_cap_per_severity():
    contracts = {f"c{i:02d}": _entry(anomalies=["boom"], ok=False) for i in range(15)}
    lines = cli.annotations(_report(contracts, ok=False))
    errors = [ln for ln in lines if ln.startswith("::error ")]
    assert len(errors) == 10
    assert "+6 more" in errors[-1]
    assert "c08" in errors[8] and "c09" not in "".join(errors[:9])


def test_annotations_exactly_ten_not_aggregated():
    contracts = {f"c{i:02d}": _entry(anomalies=["boom"], ok=False) for i in range(10)}
    errors = cli.annotations(_report(contracts, ok=False))
    assert len(errors) == 10
    assert not any("more" in ln for ln in errors)


def test_annotations_none_report_is_error():
    (line,) = cli.annotations(None)
    assert line.startswith("::error ")
    assert "no canary report" in line.lower()


def test_annotations_tolerate_malformed_entries():
    report = {"contracts": {"a": "garbage", "b": {"anomalies": "nope"}}}
    assert cli.annotations(report) == []
    assert "No canary report" not in cli.render_summary(report)


# --- CLI ------------------------------------------------------------------


def test_cli_missing_report(tmp_path, capsys):
    rc = cli.main(["summarize", "--report", str(tmp_path / "nope.json"), "--github"])
    out = capsys.readouterr()
    assert rc == 0
    assert "No canary report was produced" in out.out
    assert "::error" in out.out
    assert "::" not in out.err


def test_cli_malformed_report(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    rc = cli.main(["summarize", "--report", str(path), "--github"])
    out = capsys.readouterr()
    assert rc == 0
    assert "No canary report was produced" in out.out
    assert "::error" in out.out


def test_cli_non_object_report(tmp_path, capsys):
    path = _write(tmp_path, [1, 2])
    rc = cli.main(["summarize", "--report", str(path)])
    assert rc == 0
    assert "No canary report was produced" in capsys.readouterr().out


def test_cli_without_github_prints_no_annotations(tmp_path, capsys, bad_report):
    rc = cli.main(["summarize", "--report", str(_write(tmp_path, bad_report))])
    out = capsys.readouterr()
    assert rc == 0
    assert "::" not in out.out and "::" not in out.err
    assert "beta" in out.out


def test_cli_summary_file_gets_markdown_stdout_gets_annotations(tmp_path, capsys, bad_report):
    summary = tmp_path / "summary.md"
    summary.write_text("existing\n", encoding="utf-8")
    rc = cli.main(
        [
            "summarize",
            "--report",
            str(_write(tmp_path, bad_report)),
            "--summary-file",
            str(summary),
            "--github",
        ]
    )
    out = capsys.readouterr()
    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("existing\n")  # appended, not truncated
    assert "missing_required_field:symbol" in text
    assert "::" not in text
    assert "|" not in out.out
    assert out.out.count("::error ") == 1 and out.out.count("::warning ") == 1


def test_cli_missing_report_with_summary_file(tmp_path, capsys):
    summary = tmp_path / "summary.md"
    rc = cli.main(
        [
            "summarize",
            "--report",
            str(tmp_path / "nope.json"),
            "--summary-file",
            str(summary),
            "--github",
        ]
    )
    out = capsys.readouterr()
    assert rc == 0
    assert "No canary report was produced" in summary.read_text(encoding="utf-8")
    assert out.out.startswith("::error ")


def test_cli_script_entrypoint_exit_zero(tmp_path, bad_report):
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "check_provider_contracts.py"),
            "summarize",
            "--report",
            str(_write(tmp_path, bad_report)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "beta" in result.stdout


def test_module_import_is_stdlib_only():
    code = (
        f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r}); "
        "import scripts.check_provider_contracts; "
        "bad = [m for m in ('requests', 'yaml') if m in sys.modules]; "
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_not_ok_entry_without_codes_is_flagged():
    report = _report({"a": _entry(ok=False)}, ok=False)
    assert "not ok" in cli.render_summary(report)
    (line,) = cli.annotations(report)
    assert line.startswith("::error ") and "a: not ok" in line


def test_report_not_ok_but_nothing_flagged():
    report = _report({"a": _entry()}, ok=False)
    assert "no contract entry is flagged" in cli.render_summary(report)
    (line,) = cli.annotations(report)
    assert line.startswith("::error ") and "no contract entry is flagged" in line
