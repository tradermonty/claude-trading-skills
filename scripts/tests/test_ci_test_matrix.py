from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.ci_test_matrix import (
    POLICY_GATE_ID,
    CoverageWaiver,
    DatedException,
    MatrixError,
    SkillMetadata,
    TestEntry,
    TestPolicy,
    aggregate,
    build_entries,
    discover,
    executable_test_inventory,
    install,
    load_policy,
    main,
    matrix,
    run,
    validate_executable_test_coverage,
)

TODAY = date(2026, 8, 10)


def _test_file(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_ok():\n    assert True\n", encoding="utf-8")


def _script_file(root: Path, skill_id: str, name: str = "run.py") -> None:
    path = root / "skills" / skill_id / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def main():\n    return 0\n", encoding="utf-8")


def _write_index(root: Path, skills: dict[str, dict[str, object]]) -> None:
    payload = {
        "skills": [
            {"id": skill_id, "status": values.get("status", "production"), **values}
            for skill_id, values in skills.items()
        ]
    }
    (root / "skills-index.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")


def _base_policy() -> dict[str, object]:
    return {
        "schema_version": 1,
        "aggregate_coverage": {"target": 75, "waiver": None},
        "coverage": {"default_target": 70, "tiers": {}, "waivers": {}},
        "allowed_failures": {},
        "matrix": {},
    }


def _write_policy(root: Path, payload: dict[str, object] | None = None) -> None:
    path = root / "config/ci-test-policy.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload or _base_policy(), sort_keys=False), encoding="utf-8")


def _policy(*, aggregate_floor: int | None = None, aggregate_target: int = 75) -> TestPolicy:
    aggregate_waiver = (
        None
        if aggregate_floor is None
        else CoverageWaiver(
            floor=aggregate_floor,
            target=aggregate_target,
            expires_on=date(2026, 10, 31),
            issue=293,
            reason="ratchet",
        )
    )
    return TestPolicy(
        aggregate_target=aggregate_target,
        aggregate_waiver=aggregate_waiver,
        default_target=70,
        tier_targets={},
        coverage_waivers={},
        allowed_failures={},
        matrix_overrides={},
    )


def test_executable_inventory_requires_tests_for_every_status(tmp_path):
    for skill_id in ("covered", "beta-missing", "empty", "nested-only"):
        _script_file(tmp_path, skill_id)
    _test_file(tmp_path, "skills/covered/scripts/tests/test_covered.py")
    (tmp_path / "skills/empty/scripts/tests").mkdir(parents=True)
    (tmp_path / "skills/empty/scripts/tests/test_directory.py").mkdir()
    _test_file(tmp_path, "skills/nested-only/examples/scripts/tests/test_nested.py")
    metadata = {
        "covered": SkillMetadata("production"),
        "beta-missing": SkillMetadata("beta"),
        "empty": SkillMetadata("production"),
        "nested-only": SkillMetadata("experimental"),
    }

    assert executable_test_inventory(tmp_path) == {
        "beta-missing": False,
        "covered": True,
        "empty": False,
        "nested-only": False,
    }
    with pytest.raises(
        MatrixError,
        match="skills with executable scripts lack canonical tests: beta-missing, empty, nested-only",
    ):
        validate_executable_test_coverage(tmp_path, metadata)


def test_knowledge_only_is_explicit_and_cannot_hide_executable_code(tmp_path):
    _script_file(tmp_path, "executable")
    _test_file(tmp_path, "skills/executable/scripts/tests/test_run.py")
    (tmp_path / "skills/knowledge/scripts/tests").mkdir(parents=True)

    with pytest.raises(MatrixError, match="must set knowledge_only"):
        validate_executable_test_coverage(
            tmp_path,
            {
                "executable": SkillMetadata("production"),
                "knowledge": SkillMetadata("production"),
            },
        )

    validate_executable_test_coverage(
        tmp_path,
        {
            "executable": SkillMetadata("production"),
            "knowledge": SkillMetadata("production", knowledge_only=True),
        },
    )

    with pytest.raises(MatrixError, match="knowledge_only must identify script-free"):
        validate_executable_test_coverage(
            tmp_path,
            {
                "executable": SkillMetadata("production", knowledge_only=True),
                "knowledge": SkillMetadata("production", knowledge_only=True),
            },
        )


def test_nested_executable_requires_tests_and_cannot_be_knowledge_only(tmp_path):
    _script_file(tmp_path, "nested", "pkg/run.py")
    metadata = {"nested": SkillMetadata("production", knowledge_only=True)}

    with pytest.raises(MatrixError, match="lack canonical tests: nested"):
        validate_executable_test_coverage(tmp_path, metadata)

    _test_file(tmp_path, "skills/nested/scripts/tests/test_run.py")
    with pytest.raises(MatrixError, match="knowledge_only must identify script-free"):
        validate_executable_test_coverage(tmp_path, metadata)


def test_inventory_rejects_missing_or_unsafe_skills_directory(tmp_path):
    with pytest.raises(MatrixError, match="skills directory is missing"):
        executable_test_inventory(tmp_path)

    _script_file(tmp_path, "Unsafe")
    with pytest.raises(MatrixError, match="unsafe skill id"):
        executable_test_inventory(tmp_path)


def test_discover_supports_both_skill_layouts_and_repo_tests(tmp_path):
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")
    _test_file(tmp_path, "skills/beta/tests/test_beta.py")
    _test_file(tmp_path, "scripts/tests/test_repo.py")

    entries = discover(tmp_path)

    assert list(entries) == ["alpha", "beta", "repo-scripts"]
    assert entries["alpha"].test_paths == ("skills/alpha/scripts/tests",)
    assert entries["beta"].test_paths == ("skills/beta/tests",)


def test_policy_rejects_expired_or_unlinked_allowed_failure(tmp_path):
    policy = _base_policy()
    policy["allowed_failures"] = {
        "alpha": {"expires_on": "2026-08-09", "issue": 293, "reason": "known failure"}
    }
    _write_policy(tmp_path, policy)
    with pytest.raises(MatrixError, match="expired on 2026-08-09"):
        load_policy(tmp_path, today=TODAY)

    policy["allowed_failures"]["alpha"]["expires_on"] = "2026-08-11"
    policy["allowed_failures"]["alpha"]["issue"] = 0
    _write_policy(tmp_path, policy)
    with pytest.raises(MatrixError, match="issue must be an integer"):
        load_policy(tmp_path, today=TODAY)


def test_policy_rejects_unknown_keys_and_target_mismatch(tmp_path):
    policy = _base_policy()
    policy["unexpected"] = True
    _write_policy(tmp_path, policy)
    with pytest.raises(MatrixError, match="unknown keys"):
        load_policy(tmp_path, today=TODAY)

    policy = _base_policy()
    policy["coverage"]["waivers"] = {
        "alpha": {
            "floor": 40,
            "target": 85,
            "expires_on": "2026-08-11",
            "issue": 293,
            "reason": "ratchet",
        }
    }
    _write_policy(tmp_path, policy)
    with pytest.raises(MatrixError, match="target mismatch"):
        load_policy(tmp_path, today=TODAY)


def test_policy_rejects_duplicate_yaml_keys(tmp_path):
    _write_policy(tmp_path)
    path = tmp_path / "config/ci-test-policy.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "matrix: {}\n", encoding="utf-8")

    with pytest.raises(MatrixError, match="duplicate YAML key: 'matrix'"):
        load_policy(tmp_path, today=TODAY)


def test_build_entries_applies_targets_waivers_and_dated_allowed_failure(tmp_path):
    for skill_id in ("alpha", "core"):
        _script_file(tmp_path, skill_id)
        _test_file(tmp_path, f"skills/{skill_id}/scripts/tests/test_run.py")
    _write_index(tmp_path, {"alpha": {"status": "beta"}, "core": {"status": "production"}})
    policy = _base_policy()
    policy["coverage"] = {
        "default_target": 70,
        "tiers": {"core": {"target": 85, "skills": ["core"]}},
        "waivers": {
            "alpha": {
                "floor": 60,
                "target": 70,
                "expires_on": "2026-08-11",
                "issue": 293,
                "reason": "ratchet",
            }
        },
    }
    policy["allowed_failures"] = {
        "alpha": {"expires_on": "2026-08-11", "issue": 999, "reason": "known failure"}
    }
    _write_policy(tmp_path, policy)

    entries = build_entries(tmp_path, load_policy(tmp_path, today=TODAY))

    assert entries["alpha"].coverage_target == 70
    assert entries["alpha"].coverage_floor == 60
    assert entries["alpha"].allowed_failure is True
    assert entries["core"].coverage_target == entries["core"].coverage_floor == 85
    assert matrix(entries) == {
        "include": [
            {"id": "alpha", "allowed_failure": True},
            {"id": "core", "allowed_failure": False},
        ]
    }


def test_unknown_matrix_id_unsafe_requirement_and_missing_path_fail_closed(tmp_path):
    _script_file(tmp_path, "alpha")
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")
    _write_index(tmp_path, {"alpha": {}})

    policy = _base_policy()
    policy["matrix"] = {"ghost": {"reason": "not real"}}
    _write_policy(tmp_path, policy)
    with pytest.raises(MatrixError, match="matrix references unknown"):
        build_entries(tmp_path, load_policy(tmp_path, today=TODAY))

    policy["matrix"] = {"alpha": {"reason": "bad dependency", "requirements": ["--index-url"]}}
    _write_policy(tmp_path, policy)
    with pytest.raises(MatrixError, match="unsafe requirement"):
        build_entries(tmp_path, load_policy(tmp_path, today=TODAY))

    policy["matrix"] = {"alpha": {"reason": "missing path", "test_paths": ["missing.py"]}}
    _write_policy(tmp_path, policy)
    with pytest.raises(MatrixError, match="invalid test path"):
        build_entries(tmp_path, load_policy(tmp_path, today=TODAY))


@pytest.mark.parametrize(
    "requirement",
    [
        "file:///tmp/pkg",
        "../../pkg",
        "git+https://example.invalid/repo.git",
        "demo @ https://example.invalid/demo.whl",
    ],
)
def test_matrix_rejects_url_vcs_and_local_requirements(tmp_path, requirement):
    _script_file(tmp_path, "alpha")
    _test_file(tmp_path, "skills/alpha/scripts/tests/test_alpha.py")
    _write_index(tmp_path, {"alpha": {}})
    policy = _base_policy()
    policy["matrix"] = {"alpha": {"reason": "unsafe source", "requirements": [requirement]}}
    _write_policy(tmp_path, policy)

    with pytest.raises(MatrixError, match="unsafe requirement"):
        build_entries(tmp_path, load_policy(tmp_path, today=TODAY))


def test_cli_matrix_emits_blocking_policy_row_for_untested_beta(monkeypatch, tmp_path, capsys):
    _script_file(tmp_path, "untested")
    _write_index(tmp_path, {"untested": {"status": "beta"}})
    _write_policy(tmp_path)
    monkeypatch.setattr("scripts.ci_test_matrix.ROOT", tmp_path)

    assert main(["matrix"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "include": [{"id": POLICY_GATE_ID, "allowed_failure": False}]
    }
    assert "skills with executable scripts lack canonical tests: untested" in captured.err


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


def test_run_writes_policy_bound_manifest_even_when_tests_fail(monkeypatch, tmp_path):
    def fake_run(command, cwd, env, check):
        Path(env["COVERAGE_FILE"]).write_text("coverage", encoding="utf-8")
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr("scripts.ci_test_matrix.subprocess.run", fake_run)
    entry = TestEntry(
        "alpha",
        ("tests",),
        "scripts",
        coverage_target=70,
        coverage_floor=60,
        policy_signature="abc123",
    )

    assert run(entry, tmp_path, tmp_path / "artifacts") == 3
    manifest = json.loads((tmp_path / "artifacts/manifest.alpha.json").read_text())
    assert manifest == {
        "allowed_failure": False,
        "coverage_created": True,
        "coverage_floor": 60,
        "coverage_target": 70,
        "id": "alpha",
        "policy_signature": "abc123",
        "test_exit": 3,
    }


def _artifact(root: Path, entry: TestEntry, **overrides: object) -> None:
    payload = {
        "id": entry.id,
        "allowed_failure": entry.allowed_failure,
        "coverage_created": True,
        "coverage_floor": entry.coverage_floor,
        "coverage_target": entry.coverage_target,
        "policy_signature": entry.policy_signature,
        "test_exit": 0,
        **overrides,
    }
    (root / f"manifest.{entry.id}.json").write_text(json.dumps(payload), encoding="utf-8")
    if payload["coverage_created"]:
        (root / f"coverage.{entry.id}").write_text("data", encoding="utf-8")


def _fake_coverage_run(percentages: dict[str, float], calls: list[list[str]]):
    def fake_run(command, **kwargs):
        calls.append(command)
        if "combine" in command:
            Path(kwargs["env"]["COVERAGE_FILE"]).write_text("combined", encoding="utf-8")
        elif "json" in command:
            output = Path(command[command.index("-o") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps({"totals": {"percent_covered": percentages[output.name]}}),
                encoding="utf-8",
            )
        return SimpleNamespace(returncode=0)

    return fake_run


def _covered_entry() -> TestEntry:
    waiver = CoverageWaiver(
        floor=60,
        target=70,
        expires_on=date(2026, 10, 31),
        issue=293,
        reason="ratchet",
    )
    return TestEntry(
        "alpha",
        ("tests",),
        "skills/alpha/scripts",
        coverage_target=70,
        coverage_floor=60,
        coverage_waiver=waiver,
        policy_signature="signed",
    )


def test_aggregate_writes_reports_before_returning_floor_failure(monkeypatch, tmp_path):
    entry = _covered_entry()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _artifact(artifacts, entry)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "scripts.ci_test_matrix.subprocess.run",
        _fake_coverage_run({"alpha.json": 59.5, "repository-coverage.json": 71.5}, calls),
    )
    output = tmp_path / "combined"

    assert (
        aggregate(
            {"alpha": entry},
            _policy(aggregate_floor=72),
            artifacts,
            output,
            root=tmp_path,
            today=TODAY,
        )
        == 1
    )

    summary = json.loads((output / "per-skill-coverage.json").read_text())
    assert summary["aggregate"]["status"] == "floor_failed"
    assert summary["skills"][0]["status"] == "floor_failed"
    assert len(summary["violations"]) == 2
    assert (output / "per-skill-coverage.md").is_file()
    json_calls = [command for command in calls if "json" in command]
    assert all("--omit=*/tests/*" in command for command in json_calls)
    assert all("--fail-under=0" in command for command in json_calls)


def test_aggregate_reports_active_waivers_without_failing(monkeypatch, tmp_path):
    entry = _covered_entry()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _artifact(artifacts, entry)
    monkeypatch.setattr(
        "scripts.ci_test_matrix.subprocess.run",
        _fake_coverage_run({"alpha.json": 65.0, "repository-coverage.json": 73.0}, []),
    )
    output = tmp_path / "combined"

    assert (
        aggregate(
            {"alpha": entry},
            _policy(aggregate_floor=72),
            artifacts,
            output,
            root=tmp_path,
            today=TODAY,
        )
        == 0
    )
    summary = json.loads((output / "per-skill-coverage.json").read_text())
    assert summary["aggregate"]["status"] == "waiver_active"
    assert summary["skills"][0]["status"] == "waiver_active"
    assert summary["violations"] == []


def _allowed_entry() -> TestEntry:
    allowed = DatedException(
        expires_on=date(2026, 9, 1), issue=999, reason="temporary known failure"
    )
    return TestEntry(
        "known",
        ("tests",),
        "skills/known/scripts",
        allowed_failure=True,
        allowed_failure_policy=allowed,
        coverage_target=70,
        coverage_floor=70,
        policy_signature="allowed-signed",
    )


def test_aggregate_skips_failed_allowed_row_and_marks_partial_report(monkeypatch, tmp_path):
    normal = _covered_entry()
    allowed = _allowed_entry()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _artifact(artifacts, normal)
    _artifact(artifacts, allowed, test_exit=1)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "scripts.ci_test_matrix.subprocess.run",
        _fake_coverage_run({"alpha.json": 75.0, "repository-coverage.json": 80.0}, calls),
    )
    output = tmp_path / "combined"

    assert (
        aggregate(
            {"alpha": normal, "known": allowed},
            _policy(),
            artifacts,
            output,
            root=tmp_path,
            today=TODAY,
        )
        == 0
    )

    summary = json.loads((output / "per-skill-coverage.json").read_text())
    assert summary["skipped_allowed_failures"] == ["known"]
    assert summary["aggregate"]["status"] == "partial_allowed_failure"
    assert {row["id"]: row["status"] for row in summary["skills"]} == {
        "alpha": "target_met",
        "known": "allowed_failure",
    }
    combine = next(command for command in calls if "combine" in command)
    assert str(artifacts / "coverage.known") not in combine


def test_aggregate_only_missing_allowed_row_is_nonblocking_and_reported(monkeypatch, tmp_path):
    allowed = _allowed_entry()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    monkeypatch.setattr(
        "scripts.ci_test_matrix.subprocess.run",
        lambda *args, **kwargs: pytest.fail("coverage subprocess must not run"),
    )
    output = tmp_path / "combined"

    assert (
        aggregate({"known": allowed}, _policy(), artifacts, output, root=tmp_path, today=TODAY) == 0
    )
    summary = json.loads((output / "per-skill-coverage.json").read_text())
    assert summary["aggregate"]["actual"] is None
    assert summary["aggregate"]["status"] == "not_measured"
    assert summary["skills"][0]["status"] == "allowed_failure"
    assert (output / "per-skill-coverage.md").is_file()


def test_aggregate_rejects_failed_or_stale_manifest(tmp_path):
    entry = _covered_entry()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _artifact(artifacts, entry, test_exit=1)
    with pytest.raises(MatrixError, match="tests failed"):
        aggregate({"alpha": entry}, _policy(), artifacts, tmp_path / "out")

    (artifacts / "manifest.alpha.json").unlink()
    _artifact(artifacts, entry, policy_signature="stale")
    with pytest.raises(MatrixError, match="policy-signature mismatch"):
        aggregate({"alpha": entry}, _policy(), artifacts, tmp_path / "out")


def test_current_policy_has_no_allowed_failures_and_enforces_all_tiers():
    policy = load_policy(today=TODAY)
    entries = build_entries(policy=policy)

    assert policy.aggregate_target == 75
    assert policy.aggregate_waiver is not None
    assert policy.aggregate_waiver.floor == 72
    assert policy.allowed_failures == {}
    assert entries["theme-detector"].allowed_failure is False
    assert entries["futures-position-sizer"].coverage_target == 85
    assert entries["drawdown-circuit-breaker"].coverage_target == 85
    assert entries["position-sizer"].coverage_target == 85
    assert entries["position-sizer"].coverage_floor == 85
    assert entries["position-sizer"].coverage_waiver is None
    assert entries["mt5-robot-tester"].coverage_target == 70
    assert entries["options-strategy-advisor"].coverage_floor == 70
    assert entries["signal-postmortem"].coverage_floor == 40
    assert entries["pair-trade-screener"].requirements == ("statsmodels>=0.14,<0.15",)
    assert entries["market-news-analyst"].coverage_target is None


@pytest.mark.parametrize("installed", ["1.0", "2.0"])
def test_install_check_verifies_version_without_installing(monkeypatch, installed):
    monkeypatch.setattr("scripts.ci_test_matrix.metadata.version", lambda name: installed)
    monkeypatch.setattr(
        "scripts.ci_test_matrix.subprocess.run",
        lambda *args, **kwargs: pytest.fail("check mode must not install"),
    )
    entry = TestEntry("alpha", ("tests",), "scripts", requirements=("safe-package>=1",))
    install(entry, check=True)


def test_install_check_rejects_missing_distribution(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr("scripts.ci_test_matrix.metadata.version", missing)
    entry = TestEntry("alpha", ("tests",), "scripts", requirements=("missing-package>=1",))
    with pytest.raises(MatrixError, match="missing requirement"):
        install(entry, check=True)


def test_install_check_rejects_incompatible_version(monkeypatch):
    monkeypatch.setattr("scripts.ci_test_matrix.metadata.version", lambda name: "0.9")
    entry = TestEntry("alpha", ("tests",), "scripts", requirements=("safe-package>=1",))
    with pytest.raises(MatrixError, match="needs safe-package>=1"):
        install(entry, check=True)


def test_install_check_skips_inapplicable_markers(monkeypatch):
    monkeypatch.setattr(
        "scripts.ci_test_matrix.metadata.version", lambda name: pytest.fail("inactive marker")
    )
    entry = TestEntry(
        "alpha", ("tests",), "scripts", requirements=('safe-package; python_version < "2"',)
    )
    install(entry, check=True)


@pytest.mark.parametrize("requirement", ["safe[extra]>=1", "safe @ https://example.com/safe.whl"])
def test_install_check_fails_closed_on_unverifiable_requirement(requirement):
    entry = TestEntry("alpha", ("tests",), "scripts", requirements=(requirement,))
    with pytest.raises(MatrixError, match="cannot verify"):
        install(entry, check=True)


def test_install_check_cli_forwards_check_flag(monkeypatch):
    entry = TestEntry("alpha", ("tests",), "scripts", requirements=("safe>=1",))
    monkeypatch.setattr("scripts.ci_test_matrix.load_policy", lambda root: None)
    monkeypatch.setattr("scripts.ci_test_matrix.load_skill_metadata", lambda root: {})
    monkeypatch.setattr("scripts.ci_test_matrix.build_entries", lambda *args: {"alpha": entry})
    calls = []
    monkeypatch.setattr(
        "scripts.ci_test_matrix.install", lambda item, *, check: calls.append((item, check))
    )
    assert main(["install", "--check", "alpha"]) == 0
    assert calls == [(entry, True)]
