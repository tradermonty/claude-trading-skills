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
  python: ">=3.9,<3.14"
  supported_os: [ubuntu-latest, windows-latest, macos-latest]
  jobs:
    compat-smoke:
      os: [ubuntu-latest, windows-latest, macos-latest]
      python: ["3.13"]
    compat-nightly:
      os: [windows-latest, macos-latest]
      python: ["3.9"]
```
"""

COMPLIANT_PYPROJECT = """\
[project]
name = "x"
requires-python = ">=3.9,<3.14"
"""

# compat-smoke: matrix OS, literal Python via setup-python.
COMPLIANT_CI = """\
jobs:
  discover-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
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
          python-version: "3.9"
"""


def _compliant_tree(root: Path) -> None:
    _write(root, "docs/dev/compatibility-matrix.md", COMPLIANT_DOC)
    _write(root, "pyproject.toml", COMPLIANT_PYPROJECT)
    _write(root, ".github/workflows/ci.yml", COMPLIANT_CI)
    _write(root, ".github/workflows/compat-nightly.yml", COMPLIANT_NIGHTLY)


def test_validate_python_bound_ok():
    assert ccm._validate_python_bound(">=3.9,<3.14")[1] == ""


def test_validate_python_bound_unbounded():
    expr, err = ccm._validate_python_bound(">=3.9")
    assert err != ""


def test_validate_python_bound_missing():
    expr, err = ccm._validate_python_bound(None)
    assert err != ""


def test_requires_python_extraction(project: Path):
    _write(project, "pyproject.toml", COMPLIANT_PYPROJECT)
    assert ccm._requires_python() == ">=3.9,<3.14"


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
    assert declared["compat-nightly"]["python"] == ["3.9"]


def test_check_passes_on_compliant_tree(project: Path, capsys: pytest.CaptureFixture):
    _compliant_tree(project)
    assert ccm.check(quiet=True) == 0
    assert capsys.readouterr().out == ""


def test_check_fails_on_python_out_of_range(project: Path, capsys: pytest.CaptureFixture):
    _compliant_tree(project)
    ci = COMPLIANT_CI.replace('python-version: "3.13"', 'python-version: "3.99"')
    _write(project, ".github/workflows/ci.yml", ci)
    assert ccm.check(quiet=True) == 1
    assert "outside supported range" in capsys.readouterr().out


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
    # Tighten the declared range so compat-nightly (3.9) falls out of bounds.
    # A checker that hardcodes 3.9..3.14 would wrongly PASS; the fix derives
    # the bounds from `requires-python` and must fail here.
    _compliant_tree(project)
    _write(
        project,
        "pyproject.toml",
        COMPLIANT_PYPROJECT.replace(">=3.9,<3.14", ">=3.10,<3.14"),
    )
    _write(
        project,
        "docs/dev/compatibility-matrix.md",
        COMPLIANT_DOC.replace('python: ">=3.9,<3.14"', 'python: ">=3.10,<3.14"'),
    )
    assert ccm.check(quiet=True) == 1
    assert "outside supported range" in capsys.readouterr().out


def test_check_fails_on_doc_header_python_mismatch(project: Path, capsys: pytest.CaptureFixture):
    # The doc's top-level `python:` must match pyproject requires-python.
    _compliant_tree(project)
    doc = COMPLIANT_DOC.replace('python: ">=3.9,<3.14"', 'python: ">=3.11,<3.14"')
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
