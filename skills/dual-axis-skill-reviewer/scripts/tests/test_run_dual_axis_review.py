from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_parse_frontmatter_supports_yaml(reviewer_module):
    lines = [
        "---\n",
        "name: sample-skill\n",
        "description: >-\n",
        "  line one: value\n",
        "  line two\n",
        "---\n",
        "# body\n",
    ]

    frontmatter = reviewer_module.parse_frontmatter(lines)

    assert frontmatter["name"] == "sample-skill"
    assert "line one: value" in frontmatter["description"]
    assert "line two" in frontmatter["description"]


def test_parse_frontmatter_rejects_invalid_yaml(reviewer_module):
    lines = [
        "---\n",
        "name: sample\n",
        "description: [unterminated\n",
        "---\n",
    ]
    assert reviewer_module.parse_frontmatter(lines) == {}


def test_pick_skill_by_name_and_missing(reviewer_module, tmp_path: Path):
    skill_a = tmp_path / "skills" / "a-skill" / "SKILL.md"
    skill_b = tmp_path / "skills" / "b-skill" / "SKILL.md"
    write_text(skill_a, "---\nname: a-skill\ndescription: x\n---\n")
    write_text(skill_b, "---\nname: b-skill\ndescription: x\n---\n")
    skills = [skill_a, skill_b]

    picked = reviewer_module.pick_skill(skills, "b-skill", None)
    assert picked == skill_b

    with pytest.raises(ValueError):
        reviewer_module.pick_skill(skills, "missing-skill", None)


def test_discover_test_dirs_supports_two_layouts(reviewer_module, tmp_path: Path):
    skill_dir = tmp_path / "skills" / "sample"
    write_text(skill_dir / "scripts" / "tests" / "test_a.py", "def test_a():\n    assert True\n")
    write_text(skill_dir / "tests" / "test_b.py", "def test_b():\n    assert True\n")

    dirs = reviewer_module.discover_test_dirs(skill_dir)
    assert skill_dir / "scripts" / "tests" in dirs
    assert skill_dir / "tests" in dirs


def test_run_tests_fallbacks_to_python_pytest(reviewer_module, tmp_path: Path, monkeypatch):
    skill_dir = tmp_path / "skills" / "sample"
    write_text(skill_dir / "tests" / "test_x.py", "def test_x():\n    assert True\n")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "uv":
            raise FileNotFoundError("uv missing")
        return subprocess.CompletedProcess(cmd, 0, "ok\n1 passed\n", "")

    monkeypatch.setattr(reviewer_module.subprocess, "run", fake_run)

    status, command, output = reviewer_module.run_tests(tmp_path, skill_dir)

    assert status == "passed"
    assert command is not None and sys.executable in command
    assert "1 passed" in output
    assert calls[0][0] == "uv"
    assert calls[1][0] == sys.executable


def test_run_tests_fallback_timeout_is_captured(reviewer_module, tmp_path: Path, monkeypatch):
    skill_dir = tmp_path / "skills" / "sample"
    write_text(skill_dir / "tests" / "test_x.py", "def test_x():\n    assert True\n")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "uv":
            raise FileNotFoundError("uv missing")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=180)

    monkeypatch.setattr(reviewer_module.subprocess, "run", fake_run)

    status, command, output = reviewer_module.run_tests(tmp_path, skill_dir)

    assert status == "timeout"
    assert command is not None and sys.executable in command
    assert "timeout" in output.lower()
    assert calls[0][0] == "uv"
    assert calls[1][0] == sys.executable


def test_load_llm_review_validation(reviewer_module, tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"score": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError):
        reviewer_module.load_llm_review(str(bad), tmp_path)

    good = tmp_path / "good.json"
    good.write_text(
        json.dumps(
            {
                "score": 85,
                "summary": "ok",
                "findings": [
                    {
                        "severity": "HIGH",
                        "path": "skills/x/SKILL.md",
                        "line": 5,
                        "message": "issue",
                        "improvement": "fix",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = reviewer_module.load_llm_review(str(good), tmp_path)
    assert loaded["score"] == 85
    assert loaded["findings"][0]["severity"] == "high"


def test_combine_reviews_handles_zero_weights(reviewer_module):
    auto = {"score": 80, "findings": []}
    llm = {"provided": True, "score": 60, "findings": []}

    merged = reviewer_module.combine_reviews(auto, llm, auto_weight=0.0, llm_weight=0.0)

    assert merged["score"] == 70
    assert merged["weights"]["auto_weight"] == 0.5
    assert merged["weights"]["llm_weight"] == 0.5


def test_score_skill_counts_tests_in_root_tests_dir(reviewer_module, tmp_path: Path):
    project_root = tmp_path
    skill_dir = project_root / "skills" / "sample-skill"
    skill_md = skill_dir / "SKILL.md"
    write_text(
        skill_md,
        "\n".join(
            [
                "---",
                "name: sample-skill",
                "description: sample",
                "---",
                "",
                "## When to Use",
                "x",
                "## Prerequisites",
                "x",
                "## Workflow",
                "```bash",
                "python3 skills/sample-skill/scripts/run.py --output-dir reports/",
                "```",
                "## Output",
                "x",
                "## Resources",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    write_text(skill_dir / "scripts" / "run.py", "print('ok')\n")
    write_text(skill_dir / "references" / "ref.md", "# ref\n")
    write_text(skill_dir / "tests" / "test_sample.py", "def test_sample():\n    assert True\n")

    review = reviewer_module.score_skill(project_root, skill_md, skip_tests=True)

    assert review["score_breakdown"]["supporting_artifacts"] == 10
    assert review["score_breakdown"]["test_health"] == 8
    messages = [finding["message"] for finding in review["findings"]]
    assert "No `test_*.py` tests found for skill scripts." not in messages


def test_normalize_severity_direct(reviewer_module):
    assert reviewer_module.normalize_severity("HIGH") == "high"
    assert reviewer_module.normalize_severity(" medium ") == "medium"
    assert reviewer_module.normalize_severity("unknown") == "medium"


def test_extract_bash_blocks_handles_empty_and_multiple(reviewer_module):
    text = """
before
```bash
echo one
```
middle
```bash

```
after
```bash
echo two
```
"""
    blocks = reviewer_module.extract_bash_blocks(text)
    assert blocks == ["echo one", "echo two"]


def test_build_llm_prompt_includes_inventory(reviewer_module, tmp_path: Path):
    project_root = tmp_path
    skill_dir = project_root / "skills" / "prompt-skill"
    write_text(skill_dir / "SKILL.md", "---\nname: prompt-skill\ndescription: d\n---\n")
    write_text(skill_dir / "scripts" / "main.py", "print('x')\n")
    write_text(skill_dir / "tests" / "test_main.py", "def test_main():\n    assert True\n")
    write_text(skill_dir / "references" / "note.md", "# note\n")

    prompt = reviewer_module.build_llm_prompt(
        project_root=project_root,
        skill_dir=skill_dir,
        auto_review={"skill_name": "prompt-skill", "score": 88, "findings": []},
    )
    assert "LLM Skill Review Request" in prompt
    assert "skills/prompt-skill/scripts/main.py" in prompt
    assert "skills/prompt-skill/tests/test_main.py" in prompt
    assert "strict JSON only" in prompt


def test_to_markdown_contains_combined_sections(reviewer_module):
    report = {
        "generated_at": "2026-02-20 00:00:00",
        "skill_name": "x-skill",
        "skill_file": "skills/x-skill/SKILL.md",
        "selection_mode": "manual",
        "seed": 1,
        "auto_review": {
            "score": 80,
            "score_breakdown": {"a": 1},
            "test_status": "passed",
            "test_command": "pytest x",
        },
        "llm_review": {"provided": True, "score": 70},
        "final_review": {
            "score": 75,
            "weights": {"auto_weight": 0.5, "llm_weight": 0.5},
            "findings": [
                {
                    "axis": "auto",
                    "severity": "medium",
                    "path": "skills/x-skill/SKILL.md",
                    "line": 3,
                    "message": "m",
                }
            ],
            "improvements_required": True,
            "improvement_items": ["m -> fix"],
        },
        "llm_prompt_file": "reports/prompt.md",
    }
    md = reviewer_module.to_markdown(report)
    assert "# Dual-Axis Skill Review" in md
    assert "Final score: **75 / 100**" in md
    assert "## Findings (Combined)" in md
    assert "## Improvement Items (Final Score < 90)" in md


def test_execution_safety_max_25(reviewer_module, tmp_path: Path):
    """Verify execution_safety_reproducibility never exceeds 25."""
    project_root = tmp_path
    skill_dir = project_root / "skills" / "perfect-skill"
    skill_md = skill_dir / "SKILL.md"
    write_text(
        skill_md,
        "\n".join(
            [
                "---",
                "name: perfect-skill",
                "description: test",
                "requires_api_key: true",
                "---",
                "",
                "## When to Use",
                "x",
                "## Prerequisites",
                "x",
                "## Workflow",
                "```bash",
                "export FMP_API_KEY=your_key_here",
                "python3 skills/perfect-skill/scripts/run.py --output-dir reports/ --api-key $FMP_API_KEY",
                "```",
                "## Output",
                "x",
                "## Resources",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    write_text(skill_dir / "scripts" / "run.py", "print('ok')\n")
    write_text(skill_dir / "references" / "ref.md", "# ref\n")
    write_text(skill_dir / "tests" / "test_sample.py", "def test():\n    assert True\n")

    review = reviewer_module.score_skill(project_root, skill_md, skip_tests=True)
    exec_safety = review["score_breakdown"]["execution_safety_reproducibility"]
    assert exec_safety <= 25, f"execution_safety_reproducibility={exec_safety} exceeds max 25"


def test_api_key_score_exempt_with_frontmatter_flag(reviewer_module, tmp_path: Path):
    """Skills with requires_api_key: false should get full API key points."""
    project_root = tmp_path
    skill_dir = project_root / "skills" / "no-api-skill"
    skill_md = skill_dir / "SKILL.md"
    write_text(
        skill_md,
        "\n".join(
            [
                "---",
                "name: no-api-skill",
                "description: test",
                "requires_api_key: false",
                "---",
                "",
                "## When to Use",
                "x",
                "## Prerequisites",
                "x",
                "## Workflow",
                "```bash",
                "python3 skills/no-api-skill/scripts/run.py --output-dir reports/",
                "```",
                "## Output",
                "x",
                "## Resources",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    write_text(skill_dir / "scripts" / "run.py", "print('ok')\n")
    write_text(skill_dir / "references" / "ref.md", "# ref\n")

    review = reviewer_module.score_skill(project_root, skill_md, skip_tests=True)
    # API key exempt: should not have API key finding
    messages = [f["message"] for f in review["findings"]]
    assert not any("API key" in m for m in messages), f"Unexpected API key finding: {messages}"


def test_api_key_score_exempt_when_no_api_reference(reviewer_module, tmp_path: Path):
    """Skills with no API key references should get full API key points."""
    project_root = tmp_path
    skill_dir = project_root / "skills" / "chart-skill"
    skill_md = skill_dir / "SKILL.md"
    write_text(
        skill_md,
        "\n".join(
            [
                "---",
                "name: chart-skill",
                "description: Chart analysis skill",
                "---",
                "",
                "## When to Use",
                "x",
                "## Prerequisites",
                "x",
                "## Workflow",
                "```bash",
                "python3 skills/chart-skill/scripts/analyze.py --output-dir reports/",
                "```",
                "## Output",
                "x",
                "## Resources",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    write_text(skill_dir / "scripts" / "analyze.py", "print('ok')\n")
    write_text(skill_dir / "references" / "ref.md", "# ref\n")

    review = reviewer_module.score_skill(project_root, skill_md, skip_tests=True)
    messages = [f["message"] for f in review["findings"]]
    assert not any("API key" in m for m in messages), f"Unexpected API key finding: {messages}"


def test_domain_specific_workflow_and_reference_headings_are_recognized(
    reviewer_module, tmp_path: Path
):
    project_root = tmp_path
    skill_dir = project_root / "skills" / "knowledge-workflow"
    skill_md = skill_dir / "SKILL.md"
    write_text(
        skill_md,
        "\n".join(
            [
                "---",
                "name: knowledge-workflow",
                "description: guide",
                "---",
                "",
                "## When to Use This Skill",
                "x",
                "## Prerequisites",
                "x",
                "## Backtesting Workflow",
                "x",
                "## Available Reference Documentation",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    write_text(skill_dir / "references" / "ref.md", "# ref\n")

    review = reviewer_module.score_skill(project_root, skill_md, skip_tests=True)
    assert review["score_breakdown"]["workflow_coverage"] >= 18
    messages = [f["message"] for f in review["findings"]]
    assert "Missing section: `## Workflow`." not in messages
    assert "Missing section: `## Resources`." not in messages


def test_knowledge_only_skill_not_penalized_for_no_scripts_or_tests(
    reviewer_module, tmp_path: Path
):
    project_root = tmp_path
    skill_dir = project_root / "skills" / "knowledge-only"
    skill_md = skill_dir / "SKILL.md"
    write_text(
        skill_md,
        "\n".join(
            [
                "---",
                "name: knowledge-only",
                "description: guide",
                "---",
                "",
                "## When to Use",
                "x",
                "## Prerequisites",
                "x",
                "## Backtesting Workflow",
                "x",
                "## Output",
                "Conversational guidance only",
                "## Available Reference Documentation",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    write_text(skill_dir / "references" / "ref.md", "# ref\n")

    review = reviewer_module.score_skill(project_root, skill_md, skip_tests=False)
    assert review["skill_type"] == "knowledge_only"
    assert review["score_breakdown"]["supporting_artifacts"] == 9
    assert review["score_breakdown"]["test_health"] == 12
    assert review["test_status"] == "not_applicable"

    messages = [f["message"] for f in review["findings"]]
    assert "No runnable bash examples found." not in messages
    assert "No executable helper scripts found in `scripts/`." not in messages
    assert "No `test_*.py` tests found for skill scripts." not in messages


def test_combine_reviews_boundary_at_90_no_improvement(reviewer_module):
    auto = {
        "score": 90,
        "findings": [
            {"severity": "low", "message": "x", "improvement": "y", "path": "a", "line": None}
        ],
    }
    merged = reviewer_module.combine_reviews(auto, None, auto_weight=1.0, llm_weight=0.0)
    assert merged["score"] == 90
    assert merged["improvements_required"] is False
    assert merged["improvement_items"] == []


def test_main_e2e_generates_report_files(tmp_path: Path):
    project_root = tmp_path
    skill_dir = project_root / "skills" / "e2e-skill"
    write_text(
        skill_dir / "SKILL.md",
        "\n".join(
            [
                "---",
                "name: e2e-skill",
                "description: test",
                "---",
                "",
                "## When to Use",
                "x",
                "## Prerequisites",
                "x",
                "## Workflow",
                "```bash",
                "python3 skills/e2e-skill/scripts/run.py --output-dir reports/",
                "```",
                "## Output",
                "x",
                "## Resources",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    write_text(skill_dir / "scripts" / "run.py", "print('ok')\n")
    write_text(skill_dir / "references" / "ref.md", "# ref\n")

    script_path = Path(__file__).resolve().parents[1] / "run_dual_axis_review.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--project-root",
            str(project_root),
            "--skill",
            "e2e-skill",
            "--skip-tests",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    report_files = list((project_root / "reports").glob("skill_review_e2e-skill_*.json"))
    assert report_files


def test_api_key_detected_from_scripts(reviewer_module, tmp_path: Path):
    """API key reference in scripts (not SKILL.md) should be detected."""
    project_root = tmp_path
    skill_dir = project_root / "skills" / "api-in-scripts"
    skill_md = skill_dir / "SKILL.md"
    # SKILL.md has no API key references
    write_text(
        skill_md,
        "\n".join(
            [
                "---",
                "name: api-in-scripts",
                "description: test",
                "---",
                "",
                "## When to Use",
                "x",
                "## Prerequisites",
                "x",
                "## Workflow",
                "```bash",
                "python3 skills/api-in-scripts/scripts/run.py --output-dir reports/",
                "```",
                "## Output",
                "x",
                "## Resources",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    # Script uses FMP_API_KEY
    write_text(
        skill_dir / "scripts" / "run.py",
        'import os\napi_key = os.environ.get("FMP_API_KEY")\nprint(api_key)\n',
    )
    write_text(skill_dir / "references" / "ref.md", "# ref\n")

    review = reviewer_module.score_skill(project_root, skill_md, skip_tests=True)

    # Compare with a skill that truly doesn't use APIs
    no_api_dir = project_root / "skills" / "no-api-skill2"
    no_api_md = no_api_dir / "SKILL.md"
    write_text(
        no_api_md,
        "\n".join(
            [
                "---",
                "name: no-api-skill2",
                "description: test",
                "---",
                "",
                "## When to Use",
                "x",
                "## Prerequisites",
                "x",
                "## Workflow",
                "```bash",
                "python3 skills/no-api-skill2/scripts/run.py --output-dir reports/",
                "```",
                "## Output",
                "x",
                "## Resources",
                "- `references/ref.md`",
                "",
            ]
        ),
    )
    write_text(no_api_dir / "scripts" / "run.py", "print('ok')\n")
    write_text(no_api_dir / "references" / "ref.md", "# ref\n")

    no_api_review = reviewer_module.score_skill(project_root, no_api_md, skip_tests=True)

    # API-using skill should have lower exec score (0 for API handling)
    # vs non-API skill (4 for API exempt)
    api_exec = review["score_breakdown"]["execution_safety_reproducibility"]
    no_api_exec = no_api_review["score_breakdown"]["execution_safety_reproducibility"]
    assert api_exec < no_api_exec, (
        f"API skill exec_score ({api_exec}) should be lower than non-API skill ({no_api_exec})"
    )
