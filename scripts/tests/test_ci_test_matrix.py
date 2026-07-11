from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ci_test_matrix import (
    MatrixError,
    TestEntry,
    aggregate,
    build_entries,
    discover,
    install,
    main,
    matrix,
    run,
)


def _test_file(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_ok():\n    assert True\n", encoding="utf-8")


def test_discover_supports_both_direct_skill_layouts_and_repo_tests(tmp_path):
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")
    _test_file(tmp_path, "skills/beta/tests/test_beta.py")
    _test_file(tmp_path, "scripts/tests/test_repo.py")

    entries = discover(tmp_path)

    assert list(entries) == ["alpha", "beta", "repo-scripts"]
    assert entries["alpha"].test_paths == ("skills/alpha/scripts/tests",)
    assert entries["beta"].test_paths == ("skills/beta/tests",)


def test_discover_ignores_empty_and_nested_noncanonical_tests(tmp_path):
    (tmp_path / "skills/empty/scripts/tests").mkdir(parents=True)
    _test_file(tmp_path, "skills/outer/examples/skills/nested/scripts/tests/test_nested.py")

    assert discover(tmp_path) == {}


def test_new_skill_is_automatically_included_in_matrix(tmp_path):
    _test_file(tmp_path, "skills/new-skill/scripts/tests/test_new.py")

    entries = build_entries(tmp_path, policy={})

    assert matrix(entries) == {"include": [{"id": "new-skill", "allowed_failure": False}]}


def test_exception_policy_requires_reason(tmp_path):
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")

    with pytest.raises(MatrixError, match="requires a reason"):
        build_entries(tmp_path, {"alpha": {"excluded": True}})


def test_unknown_policy_and_missing_override_path_fail_closed(tmp_path):
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")

    with pytest.raises(MatrixError, match="undiscovered"):
        build_entries(tmp_path, {"ghost": {"reason": "not real"}})
    with pytest.raises(MatrixError, match="invalid test path"):
        build_entries(
            tmp_path,
            {"alpha": {"test_paths": ("missing.py",), "reason": "partial contract"}},
        )


def test_zero_runnable_rows_fail(tmp_path):
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")

    with pytest.raises(MatrixError, match="no runnable"):
        build_entries(tmp_path, {"alpha": {"excluded": True, "reason": "known failure"}})


def test_matrix_json_is_compact_and_contains_no_paths(tmp_path):
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")
    payload = json.dumps(matrix(build_entries(tmp_path, {})), separators=(",", ":"))

    assert payload == '{"include":[{"id":"alpha","allowed_failure":false}]}'
    assert "skills/" not in payload


def test_install_uses_safe_argv_and_double_dash(monkeypatch):
    calls = []
    monkeypatch.setattr("scripts.ci_test_matrix.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "scripts.ci_test_matrix.subprocess.run",
        lambda command, check: calls.append((command, check)),
    )
    entry = TestEntry("alpha", ("tests",), "scripts", requirements=("safe-package>=1",))

    install(entry)

    assert calls == [([sys.executable, "-m", "pip", "install", "--", "safe-package>=1"], True)]


def test_run_always_writes_manifest_with_test_result_and_coverage(monkeypatch, tmp_path):
    def fake_run(command, cwd, env, check):
        Path(env["COVERAGE_FILE"]).write_text("coverage", encoding="utf-8")
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr("scripts.ci_test_matrix.subprocess.run", fake_run)
    entry = TestEntry("alpha", ("tests",), "scripts")

    assert run(entry, tmp_path, tmp_path / "artifacts") == 3
    manifest = json.loads((tmp_path / "artifacts/manifest.alpha.json").read_text())
    assert manifest == {
        "allowed_failure": False,
        "coverage_created": True,
        "id": "alpha",
        "test_exit": 3,
    }


def _artifact(tmp_path: Path, entry_id: str, **overrides) -> None:
    payload = {
        "id": entry_id,
        "allowed_failure": False,
        "test_exit": 0,
        "coverage_created": True,
        **overrides,
    }
    (tmp_path / f"manifest.{entry_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    if payload["coverage_created"]:
        (tmp_path / f"coverage.{entry_id}").write_text("data", encoding="utf-8")


def test_aggregate_rejects_failed_blocking_manifest(tmp_path):
    _artifact(tmp_path, "alpha", test_exit=1)
    entries = {"alpha": TestEntry("alpha", ("tests",), "scripts")}

    with pytest.raises(MatrixError, match="tests failed"):
        aggregate(entries, tmp_path, tmp_path / "combined")


def test_aggregate_rejects_manifest_policy_and_coverage_mismatch(tmp_path):
    entries = {"alpha": TestEntry("alpha", ("tests",), "scripts")}
    _artifact(tmp_path, "alpha", allowed_failure=True)
    with pytest.raises(MatrixError, match="allowed-failure mismatch"):
        aggregate(entries, tmp_path, tmp_path / "combined")

    (tmp_path / "manifest.alpha.json").unlink()
    (tmp_path / "coverage.alpha").unlink()
    _artifact(tmp_path, "alpha", coverage_created=False)
    (tmp_path / "coverage.alpha").write_text("unexpected", encoding="utf-8")
    with pytest.raises(MatrixError, match="coverage manifest mismatch"):
        aggregate(entries, tmp_path, tmp_path / "combined")


def test_aggregate_warns_for_missing_allowed_row_and_combines_blocking_row(
    monkeypatch, tmp_path, capsys
):
    _artifact(tmp_path, "alpha")
    entries = {
        "alpha": TestEntry("alpha", ("tests",), "scripts"),
        "known": TestEntry("known", ("tests",), "scripts", allowed_failure=True),
    }
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scripts.ci_test_matrix.subprocess.run", fake_run)

    assert aggregate(entries, tmp_path, tmp_path / "combined") == 0
    assert "allowed-failure row known" in capsys.readouterr().err
    assert calls[0][3] == "combine"
    assert str(tmp_path / "coverage.alpha") in calls[0]
    assert calls[1][3:5] == ["report", "--fail-under=40"]


def test_cli_unknown_id_is_nonzero(monkeypatch, tmp_path, capsys):
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")
    monkeypatch.setattr("scripts.ci_test_matrix.ROOT", tmp_path)
    monkeypatch.setattr("scripts.ci_test_matrix.POLICY", {})

    assert main(["run", "missing"]) == 1
    assert "unknown test id" in capsys.readouterr().err
