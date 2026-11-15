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
        "options-strategy-advisor",
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
