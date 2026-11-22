"""Tests for scripts/backfill_security_review.py (issue #496 security_review collector)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "backfill_security_review.py"


def load_module():
    spec = importlib.util.spec_from_file_location("backfill_security_review", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def collector():
    return load_module()


def run(mod, argv, output_dir: Path):
    assert mod.main([*argv, "--output-dir", str(output_dir)]) == 0
    return json.loads((output_dir / "security_review_evidence.json").read_text(encoding="utf-8"))


def test_module_is_reusable(collector):
    assert callable(collector.load_index)
    assert callable(collector.production_skills)
    assert callable(collector.reader_ids)
    assert callable(collector.declared_ids)
    assert callable(collector.reconcile)
    assert callable(collector.mechanical_checks)


def test_enumeration_pins_target_skills(collector):
    index = collector.load_index(ROOT / "skills-index.yaml")
    recon = collector.reconcile(index)
    # SSoT-drift fixes must not silently change the reviewed set; pin the IDs.
    assert set(recon["target_skills"]) == {
        "canslim-screener",
        "cot-contrarian-detector",
        "dividend-growth-pullback-screener",
        "downtrend-duration-analyzer",
        "earnings-calendar",
        "earnings-trade-analyzer",
        "economic-calendar-fetcher",
        "edge-candidate-agent",
        "finviz-screener",
        "ftd-detector",
        "ibd-distribution-day-monitor",
        "institutional-flow-tracker",
        "kanchi-dividend-review-monitor",
        "kanchi-dividend-sop",
        "macro-regime-detector",
        "market-top-detector",
        "news-reaction-failure-analyzer",
        "options-strategy-advisor",
        "pair-trade-screener",
        "parabolic-short-trade-planner",
        "pead-screener",
        "portfolio-manager",
        "signal-postmortem",
        "technical-analyst",
        "theme-detector",
        "trader-memory-core",
        "value-dividend-screener",
        "vcp-screener",
    }


def test_reconciliation_records_both_drift_directions(collector):
    index = collector.load_index(ROOT / "skills-index.yaml")
    recon = collector.reconcile(index)
    # Declared in integrations (id=fmp/finviz/alpaca) but no key reference in scripts.
    assert set(recon["declared_but_no_script_ref"]) == {
        "edge-candidate-agent",
        "kanchi-dividend-review-monitor",
    }
    # The only script-ref-but-undeclared skills are scanner-only meta skills,
    # which are excluded from the reviewed set by the same allowlist.
    assert set(recon["script_ref_but_not_declared"]) == {
        "dual-axis-skill-reviewer",
        "skill-integration-tester",
    }
    # Scanner-only meta skills are excluded from the reviewed set.
    assert set(recon["scanner_only_excluded"]) == {
        "dual-axis-skill-reviewer",
        "skill-integration-tester",
    }
    # Skills that read a key are also declared in integrations[] on origin/main
    # (no SSoT drift): market-top, downtrend, signal-postmortem each declare id=fmp.
    for skill_id in ("market-top-detector", "downtrend-duration-analyzer", "signal-postmortem"):
        assert skill_id in recon["readers"]
        assert skill_id in recon["declared"]


def test_meta_category_api_readers_are_not_excluded(collector):
    # earnings-calendar / economic-calendar-fetcher are category: meta but read FMP keys.
    index = collector.load_index(ROOT / "skills-index.yaml")
    recon = collector.reconcile(index)
    assert "earnings-calendar" in recon["target_skills"]
    assert "economic-calendar-fetcher" in recon["target_skills"]


def test_hardcoded_secret_detection(collector, tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    good = scripts / "good.py"
    good.write_text('key = os.environ["FMP_API_KEY"]\n')  # pragma: allowlist secret
    bad = scripts / "bad.py"
    bad.write_text('api_key = "sk-live-abc123"  # noqa\n')  # pragma: allowlist secret
    findings = collector._hardcoded_findings([good, bad])
    assert len(findings) == 1
    assert "bad.py" in findings[0]


def test_placeholder_is_not_a_hardcoded_secret(collector, tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    help_text = scripts / "help.py"
    help_text.write_text("print(\"export FMP_API_KEY='your-key'\")\n")  # pragma: allowlist secret
    assert collector._hardcoded_findings([help_text]) == []


def test_shell_injection_detection(collector, tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    safe = scripts / "safe.py"
    safe.write_text('subprocess.run(["echo", "x"], check=True)\n')
    unsafe = scripts / "unsafe.py"
    unsafe.write_text('subprocess.run(f"echo {user}", shell=True)\n')
    findings = collector._shell_findings([safe, unsafe])
    assert len(findings) == 1
    assert "unsafe.py" in findings[0]


def test_confirmation_gate_defaults_fail_closed(tmp_path: Path):
    report = run(load_module(), ["--skill", "vcp-screener"], tmp_path / "reports")
    item = report["results"][0]
    assert item["proposed_value"] == "gap"
    assert any("not reviewer-confirmed" in r for r in item["gap_reasons"])


def test_clean_and_confirmed_is_passed(tmp_path: Path):
    mod = load_module()
    report = run(
        mod, ["--skill", "vcp-screener", "--reviewer-confirmed", "vcp-screener"], tmp_path / "r2"
    )
    item = report["results"][0]
    assert item["proposed_value"] == ("passed" if item["mechanical"]["clean"] else "gap")


def test_main_writes_structured_report(tmp_path: Path):
    report = run(load_module(), [], tmp_path / "reports3")
    assert report["issue"].endswith("issues/496")
    assert report["reconciliation"]["target_skills"]
    for item in report["results"]:
        assert item["proposed_value"] in {"passed", "gap"}
        if item["proposed_value"] == "gap":
            assert item["gap_reasons"]


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_flags_key_in_params_with_printed_exception(collector, tmp_path: Path):
    script = _write(
        tmp_path,
        "leaky.py",
        'params = {"apikey": key}\n'
        "try:\n    requests.get(url, params=params)\n"
        "except requests.RequestException as e:\n"
        '    print(f"failed: {e}")\n',
    )
    finds = collector._exception_key_leak_findings([script])
    assert len(finds) == 1 and "leaky.py" in finds[0]


def test_flags_fstring_url_key_with_logger_exception(collector, tmp_path: Path):
    script = _write(
        tmp_path,
        "logs.py",
        'url = f"https://x/?auth={key}"\n'
        "try:\n    requests.get(url)\nexcept Exception:\n"
        '    logger.exception("fetch failed")\n',
    )
    assert len(collector._exception_key_leak_findings([script])) == 1


def test_redaction_helper_clears_the_finding(collector, tmp_path: Path):
    script = _write(
        tmp_path,
        "safe.py",
        'params = {"apikey": key}\n'
        "try:\n    requests.get(url, params=params)\n"
        "except requests.RequestException as e:\n"
        "    print(_redact(str(e)))\n",
    )
    assert collector._exception_key_leak_findings([script]) == []


def test_fixed_error_text_and_header_keys_are_not_flagged(collector, tmp_path: Path):
    fixed = _write(
        tmp_path,
        "fixed.py",
        'params = {"apikey": key}\n'
        "try:\n    requests.get(url, params=params)\n"
        "except requests.RequestException as e:\n"
        '    print("network error")\n',
    )
    header = _write(
        tmp_path,
        "header.py",
        'req = Request(url, headers={"apikey": key})\n'
        "try:\n    open(req)\nexcept OSError as e:\n"
        '    print(f"failed: {e}")\n',
    )
    assert collector._exception_key_leak_findings([fixed, header]) == []


def test_exception_leak_counts_against_clean(collector, tmp_path: Path):
    skill = tmp_path / "skills" / "demo" / "scripts"
    skill.mkdir(parents=True)
    (skill / "leaky.py").write_text(
        'params = {"apikey": key}\n'
        "try:\n    requests.get(url, params=params, timeout=5)\n"
        "except requests.RequestException as e:\n"
        '    print(f"failed: {e}")\n'
    )
    checks = collector.mechanical_checks("demo", root=tmp_path)
    assert checks["exception_key_leak_findings"]
    assert checks["clean"] is False


def test_credential_remediation_does_not_clear_independent_prerequisites(tmp_path: Path):
    remediated = [
        "downtrend-duration-analyzer",
        "value-dividend-screener",
        "dividend-growth-pullback-screener",
        "parabolic-short-trade-planner",
        "canslim-screener",
        "theme-detector",
    ]
    argv = [a for s in remediated for a in ("--skill", s, "--reviewer-confirmed", s)]
    report = run(load_module(), argv, tmp_path / "leaky")
    assert {r["skill_id"] for r in report["results"]} == set(remediated)
    for item in report["results"]:
        assert item["mechanical"]["exception_key_leak_findings"] == [], item["skill_id"]
        # Credential remediation is independent of newly enforced timeout evidence.
        expected = "gap" if item["mechanical"]["network_timeout_findings"] else "passed"
        assert item["proposed_value"] == expected, item["skill_id"]


def test_report_records_process_not_a_person(tmp_path: Path):
    report = run(load_module(), ["--skill", "vcp-screener"], tmp_path / "proc")
    assert "automated scan" in report["process"]
    assert "review_by" not in report


@pytest.mark.parametrize(
    "body",
    [
        'class Diagnostic(ValueError):\n    """Fixed parser reason."""\n\nraise Diagnostic("missing_columns")',
        'class Diagnostic(RuntimeError):\n    pass\n\nraise Diagnostic("Fixed plan guidance. " "Use another plan.")',
    ],
)
def test_fixed_local_diagnostic_is_not_request_exception(collector, tmp_path, body):
    script = _write(
        tmp_path,
        "safe.py",
        'params = {"auth": key}\n'
        + body
        + "\ntry:\n    work()\nexcept Diagnostic as exc:\n    print(str(exc))\n",
    )
    assert collector._exception_key_leak_findings([script]) == []


@pytest.mark.parametrize(
    "definition",
    [
        "class Diagnostic(ValueError):\n    pass\n\nraise Diagnostic(response.text)",
        'class Diagnostic(requests.RequestException):\n    pass\n\nraise Diagnostic("fixed")',
        'class Diagnostic(ValueError):\n    def __str__(self):\n        return key\n\nraise Diagnostic("fixed")',
    ],
)
def test_unproven_custom_exception_stays_flagged(collector, tmp_path, definition):
    script = _write(
        tmp_path,
        "unsafe.py",
        'params = {"auth": key}\n'
        + definition
        + "\ntry:\n    work()\nexcept Diagnostic as exc:\n    print(str(exc))\n",
    )
    assert collector._exception_key_leak_findings([script])


def test_same_binding_for_request_exception_stays_flagged(collector, tmp_path):
    script = _write(
        tmp_path,
        "mixed.py",
        'params = {"auth": key}\nclass Diagnostic(ValueError):\n    pass\nraise Diagnostic("fixed")\ntry:\n    work()\nexcept Diagnostic as exc:\n    print(str(exc))\ntry:\n    requests.get(url)\nexcept requests.RequestException as exc:\n    print(str(exc))\n',
    )
    assert collector._exception_key_leak_findings([script])


@pytest.mark.parametrize(
    "rebind",
    [
        "factory = Diagnostic\nraise factory(response.text)",
        "Diagnostic = requests.RequestException",
        "class Diagnostic(requests.RequestException):\n    pass",
        "ValueError = requests.RequestException",
        "def work(Diagnostic):\n    pass",
    ],
)
def test_diagnostic_alias_or_rebinding_is_not_exempt(collector, tmp_path, rebind):
    script = _write(
        tmp_path,
        "rebound.py",
        'params = {"auth": key}\nclass Diagnostic(ValueError):\n    pass\nDiagnostic("fixed")\n'
        + rebind
        + "\ntry:\n    requests.get(url)\nexcept Diagnostic as exc:\n    print(str(exc))\n",
    )
    assert collector._exception_key_leak_findings([script])


@pytest.mark.parametrize(
    "change",
    [
        "exc = requests.ConnectionError(response.text)",
        "exc.args = (response.text,)",
        "other = exc\n    other.args = (response.text,)",
        "exc.__dict__.update(secret=response.text)",
    ],
)
def test_mutated_diagnostic_binding_is_not_exempt(collector, tmp_path, change):
    script = _write(
        tmp_path,
        "changed.py",
        'params = {"auth": key}\nclass Diagnostic(ValueError):\n    pass\ntry:\n    raise Diagnostic("fixed")\nexcept Diagnostic as exc:\n    '
        + change
        + "\n    print(str(exc))\n",
    )
    assert collector._exception_key_leak_findings([script])
