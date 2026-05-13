"""Tests for scripts/generate_workflow_docs.py.

Verify the generator produces stable, schema-aware output and that
--check correctly detects drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_workflow_docs import (  # noqa: E402
    load_workflows,
    main,
    render_page,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_workflow(workflows_dir: Path, wf: dict) -> None:
    wf_id = wf["id"]
    (workflows_dir / f"{wf_id}.yaml").write_text(
        yaml.safe_dump(wf, sort_keys=False), encoding="utf-8"
    )


def make_workflow(workflows_dir: Path, **overrides) -> dict:
    """Create a minimal but complete workflow YAML and return the dict."""
    base = {
        "schema_version": 1,
        "id": "sample-workflow",
        "display_name": "Sample Workflow",
        "cadence": "daily",
        "estimated_minutes": 10,
        "target_users": ["test-user"],
        "difficulty": "beginner",
        "api_profile": "no-api-basic",
        "when_to_run": "When the test demands it.",
        "when_not_to_run": "When you are unsure.",
        "required_skills": ["alpha"],
        "optional_skills": ["beta"],
        "artifacts": [
            {"id": "primary_output", "produced_by_step": 1, "required": True},
        ],
        "steps": [
            {
                "step": 1,
                "name": "Run alpha",
                "skill": "alpha",
                "produces": ["primary_output"],
                "decision_gate": False,
            }
        ],
        "journal_destination": "alpha",
    }
    base.update(overrides)
    _write_workflow(workflows_dir, base)
    return base


@pytest.fixture
def workflows_dir(tmp_path: Path) -> Path:
    d = tmp_path / "workflows"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_workflows_returns_sorted_list(workflows_dir: Path) -> None:
    make_workflow(workflows_dir, id="zebra")
    make_workflow(workflows_dir, id="alpha")
    workflows = load_workflows(workflows_dir)
    assert [w["id"] for w in workflows] == ["alpha", "zebra"]


def test_load_workflows_skips_files_without_id(workflows_dir: Path) -> None:
    (workflows_dir / "broken.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "no_id_here": True}), encoding="utf-8"
    )
    make_workflow(workflows_dir, id="good")
    workflows = load_workflows(workflows_dir)
    assert [w["id"] for w in workflows] == ["good"]


# ---------------------------------------------------------------------------
# Render — content checks
# ---------------------------------------------------------------------------


def test_render_includes_summary_table(workflows_dir: Path) -> None:
    make_workflow(workflows_dir, id="alpha", cadence="daily", estimated_minutes=15)
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    assert "## Available workflows" in page
    assert "`alpha`" in page
    assert "daily" in page


def test_render_marks_optional_steps(workflows_dir: Path) -> None:
    make_workflow(
        workflows_dir,
        id="opt-test",
        required_skills=["alpha"],
        optional_skills=["beta"],
        artifacts=[],
        steps=[
            {"step": 1, "name": "Required", "skill": "alpha", "decision_gate": False},
            {
                "step": 2,
                "name": "Optional",
                "skill": "beta",
                "optional": True,
                "decision_gate": False,
            },
        ],
    )
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    # Optional step should carry the (optional) flag
    assert "Step 2: Optional**" in page
    assert "(optional)" in page


def test_render_marks_decision_gates_with_question(workflows_dir: Path) -> None:
    make_workflow(
        workflows_dir,
        id="decide-test",
        required_skills=["alpha"],
        artifacts=[],
        steps=[
            {
                "step": 1,
                "name": "Decide",
                "skill": "alpha",
                "decision_gate": True,
                "decision_question": "Is this a test?",
            }
        ],
    )
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    assert "(decision gate)" in page
    assert "Is this a test?" in page


def test_render_includes_prerequisite_workflows(workflows_dir: Path) -> None:
    make_workflow(
        workflows_dir,
        id="downstream",
        prerequisite_workflows=[
            {
                "id": "upstream",
                "artifact": "their_artifact",
                "rationale": "Need upstream output",
            }
        ],
    )
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    assert "Prerequisite workflows" in page
    assert "`upstream`" in page
    assert "`their_artifact`" in page
    assert "Need upstream output" in page


def test_render_includes_final_outputs(workflows_dir: Path) -> None:
    make_workflow(
        workflows_dir,
        id="monthly-style",
        final_outputs=[
            {"id": "decision_log", "description": "Trade-side decisions"},
            {"id": "rule_changes", "description": "Rules to change"},
        ],
    )
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    assert "Final outputs" in page
    assert "`decision_log`" in page
    assert "Trade-side decisions" in page


def test_render_japanese_uses_japanese_labels(workflows_dir: Path) -> None:
    make_workflow(workflows_dir, id="ja-test")
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "ja")
    # Page title and frontmatter
    assert "title: ワークフロー" in page
    # Localized section headings
    assert "実行タイミング" in page
    assert "必須スキル" in page
    assert "ステップ 1" in page


def test_render_omits_prerequisite_section_when_absent(workflows_dir: Path) -> None:
    """Workflows without prerequisite_workflows should not show that heading."""
    make_workflow(workflows_dir, id="no-prereq")
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    assert "Prerequisite workflows" not in page


# ---------------------------------------------------------------------------
# Idempotency / drift
# ---------------------------------------------------------------------------


def test_render_is_idempotent(workflows_dir: Path) -> None:
    make_workflow(workflows_dir, id="alpha")
    make_workflow(workflows_dir, id="beta")
    workflows = load_workflows(workflows_dir)
    a = render_page(workflows, "en")
    b = render_page(workflows, "en")
    assert a == b


def test_check_mode_passes_when_files_match(tmp_path: Path) -> None:
    """End-to-end: write files then re-run with --check; should exit 0."""
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    make_workflow(workflows_dir, id="alpha")

    # Write
    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert rc == 0
    assert (tmp_path / "out.md").is_file()

    # Re-run with --check on the same output → should match
    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
            "--check",
        ]
    )
    assert rc == 0


def test_check_mode_fails_when_files_drift(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    make_workflow(workflows_dir, id="alpha")

    main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )

    # Tamper with the output
    (tmp_path / "out.md").write_text("intentionally wrong content", encoding="utf-8")

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
            "--check",
        ]
    )
    assert rc == 1


def test_check_mode_fails_when_target_missing(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    make_workflow(workflows_dir, id="alpha")

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
            "--check",
        ]
    )
    assert rc == 1


# ---------------------------------------------------------------------------
# CLI argument validation
# ---------------------------------------------------------------------------


def test_main_rejects_output_with_lang_all(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    make_workflow(workflows_dir, id="alpha")

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "all",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert rc == 2


def test_main_fails_when_workflows_dir_missing(tmp_path: Path) -> None:
    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "en",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )
    assert rc == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
