"""Unit tests for scripts/check_compat_matrix.py (issue #333 compat matrix drift)."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.check_compat_matrix as ccm


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the checker at a throwaway project tree and return its root."""
    monkeypatch.setattr(ccm, "ROOT", tmp_path)
    return tmp_path


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


COMPLIANT_DOC = """\
# Compatibility matrix

<VALUE

```yaml
compat_matrix:
  python: ">=3.10,<3.14"
  supported_os: [ubuntu-latest, windows-latest, macos-latest]
  jobs:
    compat-smoke:
      os: [ubuntu-latest, windows-latest, macos-latest]
      python: ["3.13"]
    compat-nightly:
      os: [windows-latest, macos-latest]
      python: ["3.10"]
```
"""

COMPLIANT_PYPROJECT = """\
[project]
name = "x"
requires-python = ">=3.10,<3.14"
"""

# compat-smoke: matrix OS, literal Python via setup-python.
COMPLIANT_CI = """\
jobs:
  discover-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
  metadata:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/dependency-review-action@v4
  compat-smoke:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
"""

COMPLIANT_NIGHTLY = """\
jobs:
  compat-nightly:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
"""


def _compliant_tree(root: Path) -> None:
    _write(root, "docs/dev/compatibility-matrix.md", COMPLIANT_DOC)
    _write(root, "pyproject.toml", COMPLIANT_PYPROJECT)
    _write(
        root,
        "config/python-support.json",
        '{"schema_version":1,"root_project":">=3.10,<3.14","standalone_skills_minimum":"3.9","standalone_workflow_jobs":["ci.yml:market-calendar-compat","packaged-deps-nightly.yml:smoke"]}\n',
    )
    _write(root, ".github/workflows/ci.yml", COMPLIANT_CI)
    _write(root, ".github/workflows/compat-nightly.yml", COMPLIANT_NIGHTLY)


def test_validate_python_bound_ok():
    assert ccm._validate_python_bound(">=3.10,<3.14")[1] == ""


def test_validate_python_bound_unbounded():
    expr, err = ccm._validate_python_bound(">=3.10")
    assert err != ""


def test_validate_python_bound_missing():
    expr, err = ccm._validate_python_bound(None)
    assert err != ""


def test_requires_python_extraction(project: Path):
    _write(project, "pyproject.toml", COMPLIANT_PYPROJECT)
    assert ccm._requires_python() == ">=3.10,<3.14"


def test_extract_matrix_job_combos(project: Path):
    _write(project, ".github/workflows/ci.yml", COMPLIANT_CI)
    results = ccm._extract_jobs(ccm._load_workflow("ci.yml"))
    smoke = results["compat-smoke"]
    assert smoke.used_matrix is True
    assert {c.os for c in smoke.combos} == {"ubuntu-latest", "windows-latest", "macos-latest"}
    assert {c.python for c in smoke.combos} == {"3.13"}


def test_extract_no_setup_python_job(project: Path):
    _write(project, ".github/workflows/ci.yml", COMPLIANT_CI)
    results = ccm._extract_jobs(ccm._load_workflow("ci.yml"))
    dep_rev = results["dependency-review"]
    assert {c.os for c in dep_rev.combos} == {"ubuntu-latest"}
    assert {c.python for c in dep_rev.combos} == {None}


def test_doc_parse(project: Path):
    _write(project, "docs/dev/compatibility-matrix.md", COMPLIANT_DOC)
    declared = ccm._declared_from_doc()
    assert declared["compat-smoke"]["os"] == sorted(
        ["ubuntu-latest", "windows-latest", "macos-latest"]
    )
    assert declared["compat-nightly"]["python"] == ["3.10"]


def test_check_passes_on_compliant_tree(project: Path, capsys: pytest.CaptureFixture):
    _compliant_tree(project)
    assert ccm.check(quiet=True) == 0
    assert capsys.readouterr().out == ""


def test_check_fails_on_python_out_of_range(project: Path, capsys: pytest.CaptureFixture):
    _compliant_tree(project)
    ci = COMPLIANT_CI.replace('python-version: "3.13"', 'python-version: "3.109"')
    _write(project, ".github/workflows/ci.yml", ci)
    assert ccm.check(quiet=True) == 1
    assert "outside supported range" in capsys.readouterr().out


def test_standalone_job_may_use_python39_but_root_job_may_not(
    project: Path, capsys: pytest.CaptureFixture
):
    _compliant_tree(project)
    _write(
        project,
        ".github/workflows/packaged-deps-nightly.yml",
        """jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
""",
    )
    assert ccm.check(quiet=True) == 0
    _write(
        project,
        ".github/workflows/root-extra.yml",
        """jobs:
  root-extra:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
""",
    )
    assert ccm.check(quiet=True) == 1
    assert "root-extra.yml:root-extra" in capsys.readouterr().out


def test_check_fails_on_os_out_of_supported_set(project: Path, capsys: pytest.CaptureFixture):
    _compliant_tree(project)
    ci = COMPLIANT_CI.replace("windows-latest", "cool-os")
    _write(project, ".github/workflows/ci.yml", ci)
    assert ccm.check(quiet=True) == 1
    assert "outside supported set" in capsys.readouterr().out


def test_check_fails_on_doc_drift(project: Path, capsys: pytest.CaptureFixture):
    _compliant_tree(project)
    declared = COMPLIANT_DOC.replace('python: ["3.13"]', 'python: ["3.11"]')
    _write(project, "docs/dev/compatibility-matrix.md", declared)
    assert ccm.check(quiet=True) == 1
    assert "documented Python" in capsys.readouterr().out


def test_check_json_report(project: Path, capsys: pytest.CaptureFixture):
    _compliant_tree(project)
    assert ccm.check(quiet=True, as_json=True) == 0
    payload = capsys.readouterr().out
    assert '"ok": true' in payload


def test_missing_workflow_fails(project: Path, capsys: pytest.CaptureFixture):
    _write(project, "docs/dev/compatibility-matrix.md", COMPLIANT_DOC)
    _write(project, "pyproject.toml", COMPLIANT_PYPROJECT)
    _write(project, ".github/workflows/ci.yml", COMPLIANT_CI)
    assert ccm.check(quiet=True) == 1
    assert "not found" in capsys.readouterr().out


def test_check_enforces_pyproject_bounds_not_hardcoded(
    project: Path, capsys: pytest.CaptureFixture
):
    # Tighten the declared range so compat-nightly (3.10) falls out of bounds after the floor is raised to 3.11.
    # A checker that hardcodes 3.10..3.14 would wrongly PASS; the fix derives
    # the bounds from `requires-python` and must fail here.
    _compliant_tree(project)
    _write(
        project,
        "pyproject.toml",
        COMPLIANT_PYPROJECT.replace(">=3.10,<3.14", ">=3.11,<3.14"),
    )
    _write(
        project,
        "docs/dev/compatibility-matrix.md",
        COMPLIANT_DOC.replace('python: ">=3.10,<3.14"', 'python: ">=3.11,<3.14"'),
    )
    assert ccm.check(quiet=True) == 1
    assert "outside supported range" in capsys.readouterr().out


def test_check_fails_on_doc_header_python_mismatch(project: Path, capsys: pytest.CaptureFixture):
    # The doc's top-level `python:` must match pyproject requires-python.
    _compliant_tree(project)
    doc = COMPLIANT_DOC.replace('python: ">=3.10,<3.14"', 'python: ">=3.11,<3.14"')
    _write(project, "docs/dev/compatibility-matrix.md", doc)
    assert ccm.check(quiet=True) == 1
    assert "declares python" in capsys.readouterr().out


def test_check_fails_on_doc_supported_os_mismatch(project: Path, capsys: pytest.CaptureFixture):
    # The doc's top-level `supported_os:` must match the policy set.
    _compliant_tree(project)
    doc = COMPLIANT_DOC.replace(
        "supported_os: [ubuntu-latest, windows-latest, macos-latest]",
        "supported_os: [ubuntu-latest, windows-latest]",
    )
    _write(project, "docs/dev/compatibility-matrix.md", doc)
    assert ccm.check(quiet=True) == 1
    assert "supported_os" in capsys.readouterr().out


def test_extract_matrix_exclude_removes_os(project: Path):
    # A matrix `exclude: [{os: windows-latest}]` must drop the whole Windows
    # axis from the resolved combos, so the declared-vs-actual match fails.
    _write(project, ".github/workflows/ci.yml", COMPLIANT_CI)
    ci = COMPLIANT_CI.replace(
        "        os: [ubuntu-latest, windows-latest, macos-latest]",
        "        os: [ubuntu-latest, windows-latest, macos-latest]\n        exclude:\n          - os: windows-latest",
    )
    _write(project, ".github/workflows/ci.yml", ci)
    results = ccm._extract_jobs(ccm._load_workflow("ci.yml"))
    assert {c.os for c in results["compat-smoke"].combos} == {"ubuntu-latest", "macos-latest"}


def test_check_fails_on_matrix_exclude_dropping_os(project: Path, capsys: pytest.CaptureFixture):
    # Excluding Windows from compat-smoke changes the actual OS set, which must
    # be caught as doc drift even though runs-on stays on a supported OS.
    _compliant_tree(project)
    ci = COMPLIANT_CI.replace(
        "        os: [ubuntu-latest, windows-latest, macos-latest]",
        "        os: [ubuntu-latest, windows-latest, macos-latest]\n        exclude:\n          - os: windows-latest",
    )
    _write(project, ".github/workflows/ci.yml", ci)
    assert ccm.check(quiet=True) == 1
    assert "documented OS" in capsys.readouterr().out


def test_extract_matrix_include_adds_os(project: Path):
    # An `include` entry with a concrete `os`+`python` must be added even when
    # the base product does not contain it.
    _write(project, ".github/workflows/ci.yml", COMPLIANT_CI)
    ci = COMPLIANT_CI.replace(
        "        os: [ubuntu-latest, windows-latest, macos-latest]",
        "        os: [ubuntu-latest, macos-latest]\n        include:\n          - os: windows-latest\n            python: '3.13'",
    )
    _write(project, ".github/workflows/ci.yml", ci)
    results = ccm._extract_jobs(ccm._load_workflow("ci.yml"))
    combos = {(c.os, c.python) for c in results["compat-smoke"].combos}
    assert ("windows-latest", "3.13") in combos


def test_check_scans_all_workflows_for_policy(project: Path, capsys: pytest.CaptureFixture):
    # The policy leg globs every workflow, so a brand-new workflow running a job
    # on an unsupported OS / out-of-range Python is caught, not silently skipped.
    _compliant_tree(project)
    extra = (
        "jobs:\n"
        "  extra:\n"
        "    strategy:\n"
        "      fail-fast: false\n"
        "      matrix:\n"
        "        os: [windows-latest]\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    steps:\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: '3.15'\n"
    )
    _write(project, ".github/workflows/extra-nightly.yml", extra)
    assert ccm.check(quiet=True) == 1
    assert "extra" in capsys.readouterr().out


def test_check_fails_on_missing_doc_python(project: Path, capsys: pytest.CaptureFixture):
    # A doc that omits the top-level `python:` declaration must fail closed.
    _compliant_tree(project)
    doc = COMPLIANT_DOC.replace('  python: ">=3.10,<3.14"\n', "")
    _write(project, "docs/dev/compatibility-matrix.md", doc)
    assert ccm.check(quiet=True) == 1
    assert "python" in capsys.readouterr().out


def test_check_fails_on_missing_doc_supported_os(project: Path, capsys: pytest.CaptureFixture):
    # A doc that omits the top-level `supported_os:` declaration must fail closed.
    _compliant_tree(project)
    doc = COMPLIANT_DOC.replace(
        "  supported_os: [ubuntu-latest, windows-latest, macos-latest]\n", ""
    )
    _write(project, "docs/dev/compatibility-matrix.md", doc)
    assert ccm.check(quiet=True) == 1
    assert "supported_os" in capsys.readouterr().out


def test_matrix_os_literal_runs_on_wins_over_matrix(project: Path):
    # P2#1: hardcoding `runs-on: ubuntu-latest` while a stale `matrix.os` lists
    # all three must resolve the ACTUAL OS to the literal runner, not the
    # matrix axis. Otherwise the checker would keep crediting Windows/macOS
    # even though `runs-on` no longer dispatches on them (doc drift would pass).
    wf = (
        "jobs:\n"
        "  my-job:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os: [ubuntu-latest, windows-latest, macos-latest]\n"
        "        python: ['3.10', '3.13']\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: ${{ matrix.python }}\n"
    )
    _write(project, ".github/workflows/extra.yml", wf)
    results = ccm._extract_jobs(ccm._load_workflow("extra.yml"))
    assert {c.os for c in results["my-job"].combos} == {"ubuntu-latest"}
    assert {c.python for c in results["my-job"].combos} == {"3.10", "3.13"}


def test_matrix_os_expression_still_expands_from_matrix(project: Path):
    # A matrix-expression `runs-on: ${{ matrix.os }}` still expands to the OS
    # axis, so the compliant compat jobs keep resolving all three.
    wf = (
        "jobs:\n"
        "  my-job:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os: [ubuntu-latest, windows-latest]\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    steps:\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: '3.13'\n"
    )
    _write(project, ".github/workflows/extra.yml", wf)
    results = ccm._extract_jobs(ccm._load_workflow("extra.yml"))
    assert {c.os for c in results["my-job"].combos} == {"ubuntu-latest", "windows-latest"}


def test_matrix_python_resolves_python_version_axis(project: Path):
    # Medium#1: a `setup-python` bound to `${{ matrix.python-version }}` with a
    # `python-version` matrix axis must resolve each version, not pass through
    # as an unresolved expression.
    wf = (
        "jobs:\n"
        "  my-job:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os: [ubuntu-latest]\n"
        "        python-version: ['3.10', '3.11']\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    steps:\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: ${{ matrix.python-version }}\n"
    )
    _write(project, ".github/workflows/extra.yml", wf)
    results = ccm._extract_jobs(ccm._load_workflow("extra.yml"))
    assert {c.python for c in results["my-job"].combos} == {"3.10", "3.11"}


def test_check_fails_when_job_python_unresolvable(project: Path, capsys: pytest.CaptureFixture):
    # Medium#1: a job with only `runs-on` (no setup-python and no matrix) must
    # now fail closed instead of silently skipping the Python range check.
    _compliant_tree(project)
    extra = (
        "jobs:\n"
        "  rogue:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
    )
    _write(project, ".github/workflows/extra.yml", extra)
    assert ccm.check(quiet=True) == 1
    assert "rogue: could not resolve a Python version" in capsys.readouterr().out


def test_validate_python_bound_message_not_hardcoded():
    # Low#4: the unbounded-range error must not hardcode the current bound.
    _, err = ccm._validate_python_bound(">=3.10")
    assert ">=3.10,<3.14" not in err
