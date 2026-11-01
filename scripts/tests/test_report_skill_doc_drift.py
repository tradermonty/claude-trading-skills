"""Offline contracts for the report-only skill guide drift reporter."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import report_skill_doc_drift as drift


def _repo(tmp_path, text="--alpha", *, generated=False):
    skill = tmp_path / "skills/demo"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Demo\nUse --alpha and --beta.\n")
    for lang in ("en", "ja"):
        page = tmp_path / f"docs/{lang}/skills/demo.md"
        page.parent.mkdir(parents=True)
        page.write_text(("---\ngenerated: true\n---\n" if generated else "# Guide\n") + text)
    return skill


@pytest.fixture
def dates(monkeypatch):
    monkeypatch.setattr(
        drift,
        "history_status",
        lambda root: {
            "head": "fictional-head",
            "complete": True,
            "reason": None,
        },
    )
    monkeypatch.setattr(
        drift, "last_commit_time", lambda root, path: 200 if path.name == "SKILL.md" else 100
    )


def test_newer_source_missing_flags_and_refresh_reduce_count(tmp_path, dates):
    _repo(tmp_path)
    report = drift.build_report(tmp_path)
    assert report["summary"]["drift_pages"] == 2
    assert report["pages"][0]["missing_flags"] == ["--beta"]
    assert report["pages"][0]["findings"][0]["category"] == "newer_source_missing_flags"
    for lang in ("en", "ja"):
        (tmp_path / f"docs/{lang}/skills/demo.md").write_text("--alpha --beta")
    assert drift.build_report(tmp_path)["summary"]["drift_pages"] == 0


def test_newer_page_is_not_flagged_just_for_missing_flags(tmp_path, dates, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(
        drift, "last_commit_time", lambda root, path: 100 if path.name == "SKILL.md" else 200
    )
    report = drift.build_report(tmp_path)
    assert report["summary"]["drift_pages"] == 0
    assert report["pages"][0]["missing_flags"] == ["--beta"]


def test_generated_frontmatter_only_is_excluded(tmp_path, dates):
    _repo(tmp_path, generated=True)
    assert drift.build_report(tmp_path)["pages"] == []
    (tmp_path / "docs/en/skills/demo.md").write_text(
        "# Example\n```yaml\ngenerated: true\n```\n--alpha"
    )
    assert len(drift.build_report(tmp_path)["pages"]) == 1


def test_unknown_history_missing_flags_are_visible(tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(
        drift,
        "history_status",
        lambda root: {
            "head": "shallow-head",
            "complete": False,
            "reason": "shallow git history",
        },
    )
    report = drift.build_report(tmp_path)
    assert report["summary"]["unknown_history_pages"] == 2
    assert report["pages"][0]["findings"][0]["category"] == "unknown_history_missing_flags"
    assert "shallow git history" in drift.render_markdown(report)


def test_repository_imports_are_checked_without_execution(tmp_path, dates):
    skill = _repo(
        tmp_path,
        text="--alpha --beta\n```python\nfrom skills.demo_name.scripts.tool import run\n```\n",
    )
    (skill / "scripts/tool.py").write_text(
        "raise RuntimeError('must not import')\ndef run(): pass\n"
    )
    report = drift.build_report(tmp_path)
    assert any(f["category"] == "missing_repository_import" for f in report["pages"][0]["findings"])
    assert not (tmp_path / "executed").exists()


def test_local_import_requires_static_bootstrap_and_checks_exports(tmp_path, dates):
    skill = _repo(tmp_path, text="--alpha --beta\n```python\nfrom tool import run\n```\n")
    (skill / "scripts/tool.py").write_text("def run(): pass\n")
    assert any(
        f["category"] == "missing_local_bootstrap"
        for f in drift.build_report(tmp_path)["pages"][0]["findings"]
    )
    page = tmp_path / "docs/en/skills/demo.md"
    page.write_text(
        "--alpha --beta\n```python\nimport sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path('skills/demo/scripts').resolve()))\nfrom tool import run\n```\n"
    )
    assert drift.build_report(tmp_path)["pages"][0]["findings"] == []
    page.write_text(page.read_text().replace("from tool import run", "from tool import missing"))
    assert any(
        f["category"] == "missing_repository_symbol"
        for f in drift.build_report(tmp_path)["pages"][0]["findings"]
    )


def test_external_dynamic_and_syntax_limits_are_explicit(tmp_path, dates):
    _repo(
        tmp_path,
        text="--alpha --beta\n```python\nimport unknown_provider\n__import__(name)\n```\n```python\nfrom broken import\n```\n",
    )
    page = drift.build_report(tmp_path)["pages"][0]
    assert {i["kind"] for i in page["unchecked_imports"]} == {"external", "dynamic"}
    assert any(f["category"] == "python_syntax_error" for f in page["findings"])


def test_late_or_conditional_bootstrap_does_not_validate_earlier_import(tmp_path, dates):
    skill = _repo(
        tmp_path,
        text="--alpha --beta\n```python\nfrom tool import run\nimport sys\nsys.path.insert(0, 'skills/demo/scripts')\n```\n",
    )
    (skill / "scripts/tool.py").write_text("def run(): pass\n")
    assert any(
        f["category"] == "missing_local_bootstrap"
        for f in drift.build_report(tmp_path)["pages"][0]["findings"]
    )


def test_sibling_module_is_not_a_symbol_export(tmp_path, dates):
    skill = _repo(
        tmp_path,
        text="--alpha --beta\n```python\nimport sys\nsys.path.insert(0, 'skills/demo/scripts')\nfrom tool import sibling\n```\n",
    )
    (skill / "scripts/tool.py").write_text("def run(): pass\n")
    (skill / "scripts/sibling.py").write_text("value = 1\n")
    assert any(
        f["category"] == "missing_repository_symbol"
        for f in drift.build_report(tmp_path)["pages"][0]["findings"]
    )


def test_git_metadata_scrubs_hook_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "other-repository")
    monkeypatch.setenv("GIT_INDEX_FILE", "other-index")
    captured = []

    def run(command, **kwargs):
        captured.append(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="123\n")

    monkeypatch.setattr(drift.subprocess, "run", run)
    assert drift.last_commit_time(tmp_path, tmp_path / "guide.md") == 123
    assert all(not key.startswith("GIT_") for key in captured[0])


def test_failed_output_write_is_not_hidden_by_report_only(tmp_path, dates, capsys):
    _repo(tmp_path)
    destination = tmp_path / "directory"
    destination.mkdir()
    assert drift.main(["--root", str(tmp_path), "--json-output", str(destination)]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_report_cli_is_report_only_and_writes_both_artifacts(tmp_path, dates, capsys):
    _repo(tmp_path)
    out = tmp_path / "reports"
    assert (
        drift.main(
            [
                "--root",
                str(tmp_path),
                "--json-output",
                str(out / "report.json"),
                "--markdown-output",
                str(out / "report.md"),
                "--github",
            ]
        )
        == 0
    )
    assert json.loads((out / "report.json").read_text())["summary"]["drift_pages"] == 2
    assert "::warning" in capsys.readouterr().out
    assert (out / "report.md").is_file()


def test_operational_errors_fail_visibly(tmp_path, capsys):
    assert drift.main(["--root", str(tmp_path)]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_annotation_escaping_and_cap():
    report = {
        "pages": [
            {
                "file": "docs/en/a,b.md",
                "findings": [
                    {"category": "test", "line": 2, "detail": "bad%\n::error::hidden"},
                    {"category": "test", "line": 3, "detail": "second"},
                ],
            }
        ]
    }
    warnings = drift.github_annotations(report, limit=1)
    assert len(warnings) == 1
    assert "a%2Cb.md" in warnings[0]
    assert "bad%25%0A::error::hidden" in warnings[0]
    assert "\n" not in warnings[0]


def test_workflow_is_read_only_full_history_and_keeps_drift_report_only():
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((root / ".github/workflows/skill-doc-drift.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    steps = workflow["jobs"]["report"]["steps"]
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0
    text = (root / ".github/workflows/skill-doc-drift.yml").read_text()
    assert "--github" in text and "--json-output" in text and "--markdown-output" in text
    assert "GITHUB_STEP_SUMMARY" in text and "actions/upload-artifact@" in text
    assert "secrets." not in text and "pull-requests: write" not in text
    assert "continue-on-error" not in text  # operational failures must remain visible
