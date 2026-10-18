"""Regression checks for bundled resource references (Issue #499)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_skill_references.py"
spec = importlib.util.spec_from_file_location("skill_references", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def skill(tmp_path, text, name="example"):
    folder = tmp_path / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(text)
    return folder


@pytest.mark.parametrize(
    "text",
    [
        "Load `references/missing.md`",
        "```\n1. Load strategy reference (references/missing.md)\n```",
        "[Guide](references/missing.md#details)",
        "[Guide](<references/missing.md>)",
        "[references/missing.md]",
        "**references/missing.md**.",
        "*references/missing.md*",
        "_references/missing.md_",
        "Run ./scripts/missing.py!",
        "Read references/missing.md:",
        "Use assets/missing/",
        # Emphasis that opens before the path (review of #546).
        "2. **Read references/missing.md** for the framework",
        "_Load scripts/missing.py_",
        "Did you run scripts/missing.py?",
        "[see scripts/missing.py]",
        "see <scripts/missing.py>",
        "{scripts/missing.py}",
        "`scripts/missing.py:12`",
    ],
)
def test_missing_resource_in_each_markdown_context(tmp_path, text):
    skill(tmp_path, text)
    errors = checker.check(tmp_path)
    assert len(errors) == 1
    assert "missing resource:" in errors[0]
    assert "skills/example/SKILL.md:" in errors[0]


def test_existing_files_directories_fragments_and_bold(tmp_path):
    folder = skill(
        tmp_path,
        "**references/guide.md**.\n[Guide](references/guide.md#section)\n"
        "Use assets/ and ./scripts/run.py",
    )
    (folder / "references").mkdir()
    (folder / "references/guide.md").touch()
    (folder / "assets").mkdir()
    (folder / "scripts").mkdir()
    (folder / "scripts/run.py").touch()
    assert checker.check(tmp_path) == []


def test_suffixed_forms_of_existing_files_pass(tmp_path):
    folder = skill(
        tmp_path,
        "2. **Read references/guide.md** first\n_Load scripts/run.py_\n"
        "`scripts/run.py:12`\nsee <scripts/run.py>?\n",
    )
    (folder / "references").mkdir()
    (folder / "references/guide.md").touch()
    (folder / "scripts").mkdir()
    (folder / "scripts/run.py").touch()
    assert checker.check(tmp_path) == []


def test_identifier_prefix_is_not_a_resource_reference(tmp_path):
    skill(tmp_path, "my_references/x.md and data_scripts/run.py")
    assert checker.check(tmp_path) == []


def test_repo_paths_urls_and_templates_are_not_relative_references(tmp_path):
    skill(
        tmp_path,
        "skills/other/scripts/missing.py\n"
        "skills/edge-signal-aggregator/assets/custom_weights.yaml\n"
        "https://example.org/references/missing.md\n"
        "scripts/*.py\nscripts/test_*\nassets/$NAME.yaml\nscripts/run_{symbol}.py\n"
        "references/guide_<name>.md\nscripts/test_?.py\nscripts/test_[ab].py",
    )
    assert checker.check(tmp_path) == []


def test_repo_allowlist_is_exact_and_still_checks_existence(tmp_path):
    skill(tmp_path, "scripts/run_all_tests.sh", "kanchi-dividend-sop")
    assert "missing resource" in checker.check(tmp_path)[0]
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/run_all_tests.sh").touch()
    assert checker.check(tmp_path) == []
    skill(tmp_path, "scripts/run_all_tests.sh", "other")
    assert len(checker.check(tmp_path)) == 1


@pytest.mark.parametrize("resource", ["../references/outside.md", "references/../../outside.md"])
def test_traversal_rejected(tmp_path, resource):
    skill(tmp_path, resource)
    assert "escapes skill" in checker.check(tmp_path)[0]


def test_symlink_escape_and_dangling_link(tmp_path):
    folder = skill(tmp_path, "references/outside.md\nreferences/dangling.md")
    (folder / "references").mkdir()
    (tmp_path / "outside.md").touch()
    try:
        (folder / "references/outside.md").symlink_to(tmp_path / "outside.md")
    except OSError as exc:  # Windows without Developer Mode / admin
        pytest.skip(f"symlinks unavailable: {exc}")
    (folder / "references/dangling.md").symlink_to(folder / "references/absent.md")
    errors = checker.check(tmp_path)
    assert len(errors) == 2
    assert "escapes bundle" in errors[0]
    assert "missing resource" in errors[1]


def test_empty_inventory_fails(tmp_path):
    assert checker.check(tmp_path) == ["skills/: no SKILL.md files found"]


def test_cli_failure_stderr_and_exit_two(tmp_path):
    script = tmp_path / "scripts/check_skill_references.py"
    script.parent.mkdir()
    script.write_text(SCRIPT.read_text())
    skill(tmp_path, "references/absent.md")
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "SKILL.md:1: missing resource: references/absent.md" in result.stderr


def test_gate_wired_into_ci_and_hook():
    root = SCRIPT.parents[1]
    import yaml

    config = yaml.safe_load((root / ".pre-commit-config.yaml").read_text())
    hook = next(
        h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "skill-references"
    )
    assert hook["entry"] == "python3 scripts/check_skill_references.py"
    assert hook["pass_filenames"] is False
    # pre-commit omits deleted files, so a commit that only removes a resource must still run.
    assert hook["always_run"] is True
    import re

    for filename in [
        "skills/example/SKILL.md",
        "skills/example/references/guide.md",
        "skills/example/scripts/run.py",
        "scripts/check_skill_references.py",
        "scripts/tests/test_check_skill_references.py",
        ".pre-commit-config.yaml",
    ]:
        assert re.search(hook["files"], filename)
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    assert any(
        step.get("run") == hook["entry"] for step in workflow["jobs"]["docs-cli-examples"]["steps"]
    )
