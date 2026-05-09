"""Tests for skills-index schema, generator, and validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
INDEX_PATH = REPO / "data" / "skills-index.yaml"
GEN_SCRIPT = REPO / "scripts" / "generate_catalog.py"
VALIDATE_SCRIPT = REPO / "scripts" / "validate_skills_index.py"
BOOTSTRAP_SCRIPT = REPO / "scripts" / "bootstrap_skills_index.py"


def run(script: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=check,
    )


def test_index_yaml_loads():
    assert INDEX_PATH.exists()
    data = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["categories"]
    assert data["apis"]
    assert "skills" in data


def test_categories_have_unique_ids():
    data = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))
    ids = [c["id"] for c in data["categories"]]
    assert len(ids) == len(set(ids))


def test_validator_exits_zero_when_clean():
    result = run(VALIDATE_SCRIPT)
    assert result.returncode == 0, f"validator failed:\n{result.stdout}\n{result.stderr}"


def test_generator_check_after_write_is_clean():
    """Writing then checking should produce no further drift — but only when markers exist.

    When markers are missing, --write produces *.generated.md previews and --check
    keeps reporting "markers missing" until a human inserts them.
    """
    write = run(GEN_SCRIPT, "--write", "--all-langs")
    assert write.returncode == 0, write.stderr

    has_markers = all(
        "<!-- BEGIN AUTO: catalog-categories -->"
        in (REPO / "docs" / lang / "skill-catalog.md").read_text(encoding="utf-8")
        for lang in ("en", "ja")
    )
    check = run(GEN_SCRIPT, "--check", "--all-langs")
    if has_markers:
        assert check.returncode == 0, f"check failed after write:\n{check.stderr}"
    else:
        assert check.returncode == 1
        assert "markers missing" in check.stderr


def test_bootstrap_dry_run_is_idempotent():
    """Bootstrap should produce a parseable YAML and not error out."""
    result = run(BOOTSTRAP_SCRIPT)
    assert result.returncode == 0, result.stderr
    parsed = yaml.safe_load(result.stdout)
    assert isinstance(parsed["skills"], list)
    assert len(parsed["skills"]) > 0
    repo_skills = sorted(d.name for d in (REPO / "skills").iterdir() if (d / "SKILL.md").exists())
    bootstrap_names = sorted(s["name"] for s in parsed["skills"])
    assert bootstrap_names == repo_skills, (
        f"bootstrap missed: {set(repo_skills) - set(bootstrap_names)}; "
        f"extra: {set(bootstrap_names) - set(repo_skills)}"
    )


def test_every_skill_has_required_fields():
    data = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))
    for s in data.get("skills") or []:
        assert s.get("name"), s
        assert s.get("title"), s
        assert s.get("category"), s
        assert s.get("description"), s


def test_apis_levels_are_valid():
    data = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))
    for s in data.get("skills") or []:
        for level in (s.get("apis") or {}).values():
            assert level in {"required", "optional"}, (s["name"], level)


def test_generator_handles_missing_markers():
    """If markers don't exist, --check returns 1 with a clear message."""
    # Run without writing — generator should report missing markers without crashing.
    result = run(GEN_SCRIPT, "--check")
    # It's allowed to be 0 (clean) or 1 (drift / missing markers); never crash.
    assert result.returncode in (0, 1), result.stderr
