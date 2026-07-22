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
        "display_name_ja": "サンプルワークフロー",
        "cadence": "daily",
        "estimated_minutes": 10,
        "target_users": ["test-user"],
        "difficulty": "beginner",
        "api_profile": "no-api-basic",
        "when_to_run": "When the test demands it.",
        "when_to_run_ja": "テストで必要なときに実行します。",
        "when_not_to_run": "When you are unsure.",
        "when_not_to_run_ja": "判断に迷うときは実行しません。",
        "required_skills": ["alpha"],
        "optional_skills": ["beta"],
        "artifacts": [
            {"id": "primary_output", "produced_by_step": 1, "required": True},
        ],
        "steps": [
            {
                "step": 1,
                "name": "Run alpha",
                "name_ja": "alphaを実行する",
                "skill": "alpha",
                "produces": ["primary_output"],
                "decision_gate": False,
            }
        ],
        "manual_review": ["Confirm the test output."],
        "manual_review_ja": ["テスト出力を確認します。"],
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
            {
                "step": 1,
                "name": "Required",
                "name_ja": "必須ステップ",
                "skill": "alpha",
                "decision_gate": False,
            },
            {
                "step": 2,
                "name": "Optional",
                "name_ja": "任意ステップ",
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
                "name_ja": "判断する",
                "skill": "alpha",
                "decision_gate": True,
                "decision_question": "Is this a test?",
                "decision_question_ja": "これはテストですか？",
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
                "rationale_ja": "上流の出力が必要です",
            }
        ],
    )
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    assert "Prerequisite workflows" in page
    assert "`upstream`" in page
    assert "`their_artifact`" in page
    assert "Need upstream output" in page


def test_render_includes_manual_input_contracts(workflows_dir: Path) -> None:
    make_workflow(
        workflows_dir,
        id="manual-inputs",
        manual_inputs=[
            {
                "id": "tax_holdings_input",
                "required": False,
                "used_by_steps": [2],
                "schema_ref": "skills/tax/references/input-schema.md",
                "description": "JSON object with a holdings array.",
                "description_ja": "holdings配列を含むJSONオブジェクトです。",
            }
        ],
    )
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    assert "Manual input contracts" in page
    assert "`tax_holdings_input`" in page
    assert "2" in page
    assert "`skills/tax/references/input-schema.md`" in page
    assert "JSON object with a holdings array." in page


def test_render_includes_final_outputs(workflows_dir: Path) -> None:
    make_workflow(
        workflows_dir,
        id="monthly-style",
        final_outputs=[
            {
                "id": "decision_log",
                "description": "Trade-side decisions",
                "description_ja": "売買判断",
            },
            {
                "id": "rule_changes",
                "description": "Rules to change",
                "description_ja": "変更するルール",
            },
        ],
    )
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "en")
    assert "Final outputs" in page
    assert "`decision_log`" in page
    assert "Trade-side decisions" in page


def test_render_japanese_uses_japanese_labels(workflows_dir: Path) -> None:
    make_workflow(
        workflows_dir,
        id="ja-test",
        manual_inputs=[
            {
                "id": "operator_input",
                "required": False,
                "used_by_steps": [1],
                "schema_ref": "schemas/input.json",
                "description": "English manual input description.",
                "description_ja": "手動入力の説明です。",
            }
        ],
        prerequisite_workflows=[
            {
                "id": "upstream",
                "artifact": "upstream_output",
                "rationale": "English prerequisite rationale.",
                "rationale_ja": "上流の成果物が必要です。",
            }
        ],
    )
    workflows = load_workflows(workflows_dir)
    page = render_page(workflows, "ja")
    # Page title and frontmatter
    assert "title: ワークフロー" in page
    # Localized section headings
    assert "実行タイミング" in page
    assert "必須スキル" in page
    assert "ステップ 1" in page
    assert "サンプルワークフロー" in page
    assert "毎日" in page
    assert "初級" in page
    assert "約10分" in page
    assert "alphaを実行する" in page
    assert "テスト出力を確認します。" in page
    assert "手動入力の説明です。" in page
    assert "上流の成果物が必要です。" in page
    assert "定義ファイル" in page
    assert "成果物" in page
    assert "参考情報" in page
    assert "English manual input description." not in page
    assert "English prerequisite rationale." not in page
    assert "When the test demands it." not in page


def test_render_japanese_requires_translated_fields(workflows_dir: Path) -> None:
    workflow = make_workflow(workflows_dir, id="missing-ja")
    del workflow["steps"][0]["name_ja"]
    _write_workflow(workflows_dir, workflow)

    with pytest.raises(ValueError, match=r"steps\[0\]\.name_ja"):
        render_page(load_workflows(workflows_dir), "ja")


@pytest.mark.parametrize("manual_review_ja", [[], [""]])
def test_render_japanese_requires_aligned_manual_review(
    workflows_dir: Path, manual_review_ja: list[str]
) -> None:
    make_workflow(
        workflows_dir,
        id="bad-ja-review",
        manual_review_ja=manual_review_ja,
    )

    with pytest.raises(ValueError, match="manual_review_ja"):
        render_page(load_workflows(workflows_dir), "ja")


def test_render_japanese_rejects_non_list_manual_review(workflows_dir: Path) -> None:
    make_workflow(
        workflows_dir,
        id="bad-source-review",
        manual_review="Review this output.",
        manual_review_ja=[],
    )

    with pytest.raises(ValueError, match="manual_review must be a list"):
        render_page(load_workflows(workflows_dir), "ja")


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("prerequisite_workflows", {"id": "upstream"}),
        ("manual_inputs", {"id": "operator_input"}),
        ("steps", None),
        ("steps", {"step": 1}),
        ("steps", ["not-a-mapping"]),
        ("final_outputs", {"id": "decision"}),
        ("manual_inputs", ["not-a-mapping"]),
    ],
)
def test_render_rejects_malformed_workflow_collections(
    workflows_dir: Path, field: str, invalid_value: object
) -> None:
    make_workflow(workflows_dir, id="malformed", **{field: invalid_value})

    with pytest.raises(ValueError, match=field):
        render_page(load_workflows(workflows_dir), "ja")


def test_main_reports_incomplete_japanese_translation(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    workflow = make_workflow(workflows_dir, id="missing-ja-cli")
    del workflow["when_to_run_ja"]
    _write_workflow(workflows_dir, workflow)

    rc = main(
        [
            "--project-root",
            str(tmp_path),
            "--lang",
            "ja",
            "--output",
            str(tmp_path / "out.md"),
        ]
    )

    assert rc == 1
    assert not (tmp_path / "out.md").exists()


def test_render_english_ignores_japanese_fields(workflows_dir: Path) -> None:
    make_workflow(workflows_dir, id="en-stable")
    page = render_page(load_workflows(workflows_dir), "en")

    assert "Sample Workflow" in page
    assert "When the test demands it." in page
    assert "Run alpha" in page
    assert "サンプルワークフロー" not in page
    assert "テストで必要なときに実行します。" not in page
    assert "alphaを実行する" not in page


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
