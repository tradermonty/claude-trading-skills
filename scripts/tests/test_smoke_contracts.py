"""Tests for SMOKE_CONTRACTS (issue #349) — offline, table-validation only.

Contract *execution* happens only in the nightly clean-room venvs
(scripts/smoke_contracts_runner.py); these tests intentionally never run a
skill script, never create a venv, and never touch the network.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import check_skill_deps as deps  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent


def _declared_third_party() -> list[str]:
    """Executable skills whose manifest declares required third-party dists."""
    ids = []
    for manifest in sorted((REPO_ROOT / "skills").glob("*/requirements.txt")):
        entries, errors = deps.parse_requirements(manifest)
        if errors:
            continue
        if any(not entry.optional for entry in entries.values()):
            ids.append(manifest.parent.name)
    return ids


def _skipped(skill_id: str) -> list[deps.SmokeContract]:
    return [contract for contract in deps.SMOKE_CONTRACTS.get(skill_id, []) if contract.skip_reason]


def test_contract_scripts_exist_and_are_well_formed() -> None:
    problems = deps.validate_smoke_contracts(REPO_ROOT)
    assert not problems, "\n".join(problems)


def test_every_contract_compile_checks_offline() -> None:
    """Contracts must point at compilable scripts, never executed here."""
    for skill_id, contracts in deps.SMOKE_CONTRACTS.items():
        for contract in contracts:
            assert contract.script or contract.skip_reason, skill_id
            if contract.script:
                source = (REPO_ROOT / contract.script).read_text(encoding="utf-8")
                compile(source, contract.script, "exec")


def test_wave1_coverage_or_recorded_skip() -> None:
    """Every third-party skill has contracts, a recorded skip, or is listed
    in PENDING_SMOKE_CONTRACTS (wave-2 follow-up, non-failing)."""
    covered = _declared_third_party()
    for skill_id in covered:
        assert deps.SMOKE_CONTRACTS.get(skill_id) or skill_id in deps.PENDING_SMOKE_CONTRACTS, (
            f"no contract and not recorded as pending: {skill_id}"
        )
    # Pending list is exactly the complement: no silent coverage growth or
    # silent pending growth.
    assert set(deps.PENDING_SMOKE_CONTRACTS) == set(covered) - set(deps.SMOKE_CONTRACTS)


def test_skip_entries_carry_reason() -> None:
    for skill_id, contracts in deps.SMOKE_CONTRACTS.items():
        for contract in contracts:
            if not contract.script:
                assert contract.skip_reason, f"{skill_id}: skip needs a reason"
                assert not contract.args


def test_fixture_expectations_reference_existing_files() -> None:
    for skill_id, contracts in deps.SMOKE_CONTRACTS.items():
        for contract in contracts:
            if contract.fixture:
                assert (REPO_ROOT / contract.fixture).is_file(), (
                    f"{skill_id}: fixture {contract.fixture} missing"
                )


def test_table_imports_without_pyyaml() -> None:
    """The nightly heredoc may import this module with pyyaml absent; a
    top-level `import yaml` would recreate the #456 masked crash."""
    code = (
        "import sys\n"
        "sys.modules['yaml'] = None\n"
        f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "import check_skill_deps as deps\n"
        "assert isinstance(deps.SMOKE_CONTRACTS, dict)\n"
        "assert deps.SMOKE_CONTRACTS['macro-regime-detector']\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_golden_macro_regime_contract_preserved() -> None:
    contracts = deps.SMOKE_CONTRACTS["macro-regime-detector"]
    assert any(
        "macro_regime_detector.py" in c.script and "--help" in c.args
        for c in contracts
        if not c.skip_reason
    )
