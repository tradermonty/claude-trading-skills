from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.check_platform_compatibility import (
    CompatibilityError,
    check_runtime,
    load_policy,
    main,
    matrix,
    probe_runtime,
    validate_repository_contract,
)

ROOT = Path(__file__).resolve().parents[2]


def _policy_payload() -> dict[str, object]:
    return yaml.safe_load((ROOT / "config/platform-compatibility.yaml").read_text(encoding="utf-8"))


def _write_policy(root: Path, payload: dict[str, object] | None = None) -> None:
    path = root / "config/platform-compatibility.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload or _policy_payload(), sort_keys=False), encoding="utf-8")
    for relative in (payload or _policy_payload())["test_paths"]:
        test_path = root / relative
        test_path.parent.mkdir(parents=True, exist_ok=True)
        if Path(relative).suffix:
            test_path.write_text("def test_placeholder(): pass\n", encoding="utf-8")
        else:
            test_path.mkdir(parents=True, exist_ok=True)


def test_repository_policy_has_pr_and_nightly_profiles():
    policy = load_policy(ROOT)

    assert policy.python_requires == ">=3.9,<3.15"
    assert policy.best_effort == ("3.10", "3.11", "3.12")
    assert policy.profiles["pull_request"] == (
        "ubuntu-py39",
        "ubuntu-py314",
        "windows-py313",
    )
    assert set(policy.profiles["nightly"]) == set(policy.rows)


def test_matrix_emits_os_neutral_runner_contract():
    policy = load_policy(ROOT)

    payload = matrix(policy, "pull_request")

    assert [row["id"] for row in payload["include"]] == list(policy.profiles["pull_request"])
    assert payload["include"][0]["runner"] == "ubuntu-latest"
    assert payload["include"][2]["runner"] == "windows-latest"
    assert "skills/macro-regime-detector/scripts/tests" in payload["include"][2]["pytest_paths"]
    assert "skills/exposure-coach/scripts/tests" in payload["include"][2]["pytest_paths"]

    with pytest.raises(CompatibilityError, match="unknown compatibility profile"):
        matrix(policy, "missing")


@pytest.mark.parametrize("version", [(3, 8), (3, 15)])
def test_runtime_rejects_python_outside_supported_range(version):
    with pytest.raises(CompatibilityError, match="unsupported Python"):
        check_runtime(load_policy(ROOT), sys_platform="linux", version_info=version)


def test_runtime_rejects_unknown_os_and_non_cpython():
    policy = load_policy(ROOT)
    with pytest.raises(CompatibilityError, match="unsupported operating system"):
        check_runtime(policy, sys_platform="freebsd", version_info=(3, 14))
    with pytest.raises(CompatibilityError, match="CPython is required"):
        check_runtime(
            policy,
            sys_platform="linux",
            version_info=(3, 14),
            implementation="pypy",
        )


def test_runtime_distinguishes_best_effort_and_matrix_rows():
    policy = load_policy(ROOT)

    assert "best-effort" in check_runtime(policy, sys_platform="darwin", version_info=(3, 12))
    assert (
        check_runtime(
            policy,
            matrix_id="windows-py313",
            sys_platform="win32",
            version_info=(3, 13),
        )
        == "supported matrix runtime: windows-py313"
    )

    with pytest.raises(CompatibilityError, match="unknown compatibility matrix id"):
        check_runtime(policy, matrix_id="missing", sys_platform="linux", version_info=(3, 14))
    with pytest.raises(CompatibilityError, match="runtime mismatch"):
        check_runtime(
            policy,
            matrix_id="windows-py313",
            sys_platform="linux",
            version_info=(3, 13),
        )


def test_policy_rejects_duplicate_and_unknown_fields(tmp_path):
    _write_policy(tmp_path)
    path = tmp_path / "config/platform-compatibility.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "rows: {}\n", encoding="utf-8")
    with pytest.raises(CompatibilityError, match="duplicate YAML key"):
        load_policy(tmp_path)

    payload = _policy_payload()
    payload["unexpected"] = True
    _write_policy(tmp_path, payload)
    with pytest.raises(CompatibilityError, match="unknown keys"):
        load_policy(tmp_path)


def test_policy_rejects_profile_gaps_and_invalid_test_paths(tmp_path):
    payload = _policy_payload()
    payload["profiles"]["nightly"] = payload["profiles"]["nightly"][:-1]
    _write_policy(tmp_path, payload)
    with pytest.raises(CompatibilityError, match="nightly profile must exercise every"):
        load_policy(tmp_path)

    payload = _policy_payload()
    payload["test_paths"] = ["missing/tests"]
    _write_policy(tmp_path)
    (tmp_path / "config/platform-compatibility.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(CompatibilityError, match="invalid compatibility test path"):
        load_policy(tmp_path)


def test_policy_requires_every_os_python_boundaries_and_windows_regression(tmp_path):
    payload = _policy_payload()
    payload["rows"].pop("macos-py314")
    payload["profiles"]["nightly"].remove("macos-py314")
    _write_policy(tmp_path, payload)
    with pytest.raises(CompatibilityError, match="do not exercise platforms: macos"):
        load_policy(tmp_path)

    payload = _policy_payload()
    payload["rows"].pop("ubuntu-py39")
    payload["profiles"]["pull_request"].remove("ubuntu-py39")
    payload["profiles"]["nightly"].remove("ubuntu-py39")
    _write_policy(tmp_path, payload)
    with pytest.raises(CompatibilityError, match="boundary versions: 3.9"):
        load_policy(tmp_path)

    payload = _policy_payload()
    payload["rows"].pop("windows-py313")
    payload["profiles"]["pull_request"].remove("windows-py313")
    payload["profiles"]["nightly"].remove("windows-py313")
    _write_policy(tmp_path, payload)
    with pytest.raises(CompatibilityError, match="Windows/Python 3.13"):
        load_policy(tmp_path)


def test_repository_contract_detects_pyproject_lock_and_docs_drift(tmp_path):
    _write_policy(tmp_path)
    policy = load_policy(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.9,<3.15"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text(
        'version = 1\nrequires-python = ">=3.9,<3.15"\n', encoding="utf-8"
    )
    for relative in ("docs/dev/platform-support.md", "docs/dev/platform-support.ja.md"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")

    validate_repository_contract(policy, tmp_path)

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.9"\n', encoding="utf-8"
    )
    with pytest.raises(CompatibilityError, match="pyproject requires-python drift"):
        validate_repository_contract(policy, tmp_path)


@pytest.mark.parametrize(
    "old,new",
    (
        ("`macos-latest`", "`ubuntu-latest`"),
        (
            "| 3.14 | no | yes | Latest macOS boundary |",
            "| 3.13 | no | yes | Latest macOS boundary |",
        ),
        (
            "| 3.14 | no | yes | Latest Windows boundary |",
            "| 3.14 | yes | yes | Latest Windows boundary |",
        ),
    ),
)
def test_repository_contract_detects_documented_matrix_drift(tmp_path, old, new):
    _write_policy(tmp_path)
    policy = load_policy(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.9,<3.15"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text(
        'version = 1\nrequires-python = ">=3.9,<3.15"\n', encoding="utf-8"
    )
    for relative in ("docs/dev/platform-support.md", "docs/dev/platform-support.ja.md"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    english = tmp_path / "docs/dev/platform-support.md"
    text = english.read_text(encoding="utf-8")
    assert old in text
    english.write_text(text.replace(old, new), encoding="utf-8")

    with pytest.raises(CompatibilityError, match="matrix table drift"):
        validate_repository_contract(policy, tmp_path)


def test_probe_round_trips_cross_platform_boundaries():
    result = probe_runtime()

    assert result["utf8_lf"] == "passed"
    assert result["crlf"] == "passed"
    assert result["unicode_space_path"] == "passed"
    assert result["argv_subprocess"] == "passed"
    assert result["executable_bit"] in {"passed", "not-applicable-on-windows"}


def test_cli_matrix_is_machine_readable(monkeypatch, capsys):
    monkeypatch.setattr("scripts.check_platform_compatibility.ROOT", ROOT)

    assert main(["matrix", "--profile", "pull_request"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["include"][0]["id"] == "ubuntu-py39"


def test_workflows_are_wired_to_versioned_profiles():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    nightly = (ROOT / ".github/workflows/compatibility-nightly.yml").read_text(encoding="utf-8")

    assert "matrix --profile pull_request" in ci
    assert "matrix --profile nightly" in nightly
    assert "schedule:" in nightly and "workflow_dispatch:" in nightly
    assert ".venv/bin" not in ci[ci.index("  compatibility:") : ci.index("  discover-tests:")]
    nightly_compatibility = nightly[nightly.index("  compatibility:") :]
    assert ".venv/bin" not in nightly_compatibility
    for workflow in (ci, nightly):
        assert "check_platform_compatibility.py check --matrix-id" in workflow
        assert "check_platform_compatibility.py probe" in workflow
        assert "${{ matrix.pytest_paths }}" in workflow


def test_shell_only_automation_has_guards_and_python_alternatives():
    generation = (ROOT / "scripts/run_skill_generation.sh").read_text(encoding="utf-8")
    improvement = (ROOT / "scripts/run_skill_improvement.sh").read_text(encoding="utf-8")
    runner = (ROOT / "scripts/run_all_tests.sh").read_text(encoding="utf-8")

    assert '"$(uname -s)" != "Darwin"' in generation
    assert "run_skill_generation_pipeline.py" in generation
    assert '"$(uname -s)" != "Darwin"' in improvement
    assert "isolated clean checkout" in improvement
    assert "run_all_tests.py" in runner
