"""Tests for scripts/ceremony_log.py — admin ceremony log."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from ceremony_log import (  # noqa: E402
    CeremonyLog,
    CeremonyType,
    GENESIS_HASH,
    REQUIRED_CEREMONY_FIELDS,
)


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "ceremony-log"


@pytest.fixture
def ceremony_log(log_dir: Path) -> CeremonyLog:
    return CeremonyLog(log_dir)


# ---------------------------------------------------------------------------
# Required fields validation
# ---------------------------------------------------------------------------

class TestRequiredCeremonyFields:
    def test_key_rotation_requires_key_id_and_reason(self, ceremony_log: CeremonyLog) -> None:
        with pytest.raises(ValueError, match="key_id"):
            ceremony_log.append(CeremonyType.KEY_ROTATION, actor="admin")

    def test_key_rotation_passes_with_required_fields(self, ceremony_log: CeremonyLog) -> None:
        entry = ceremony_log.append(
            CeremonyType.KEY_ROTATION,
            actor="admin",
            actor_role="ADMIN",
            details={"key_id": "abc12345", "reason": "Annual rotation"},
        )
        assert entry["ceremony_type"] == "KEY_ROTATION"

    def test_release_approval_requires_tag_and_notes(self, ceremony_log: CeremonyLog) -> None:
        with pytest.raises(ValueError, match="release_tag"):
            ceremony_log.append(CeremonyType.RELEASE_APPROVAL, actor="admin")

    def test_release_approval_passes(self, ceremony_log: CeremonyLog) -> None:
        entry = ceremony_log.append(
            CeremonyType.RELEASE_APPROVAL,
            actor="alice",
            actor_role="ADMIN",
            details={
                "release_tag": "v1.2.3",
                "approval_notes": "Gate checks all passed",
            },
        )
        assert entry["ceremony_type"] == "RELEASE_APPROVAL"

    def test_reviewer_role_assign_requires_assignee_and_role(
        self, ceremony_log: CeremonyLog
    ) -> None:
        with pytest.raises(ValueError, match="assignee"):
            ceremony_log.append(CeremonyType.REVIEWER_ROLE_ASSIGN, actor="admin")

    def test_reviewer_role_assign_passes(self, ceremony_log: CeremonyLog) -> None:
        entry = ceremony_log.append(
            CeremonyType.REVIEWER_ROLE_ASSIGN,
            actor="admin",
            actor_role="ADMIN",
            details={"assignee": "carol", "role": "RISK_APPROVER"},
        )
        assert entry["ceremony_type"] == "REVIEWER_ROLE_ASSIGN"

    def test_waiver_approval_requires_all_fields(self, ceremony_log: CeremonyLog) -> None:
        with pytest.raises(ValueError, match="run_id"):
            ceremony_log.append(CeremonyType.WAIVER_APPROVAL, actor="admin")

    def test_waiver_approval_passes(self, ceremony_log: CeremonyLog) -> None:
        entry = ceremony_log.append(
            CeremonyType.WAIVER_APPROVAL,
            actor="admin",
            actor_role="ADMIN",
            details={
                "run_id": "run_abc123",
                "waiver_reason": "Non-trade analysis report",
                "approver_role": "ADMIN",
            },
        )
        assert entry["ceremony_type"] == "WAIVER_APPROVAL"

    def test_package_signing_requires_manifest_version_and_key_id(
        self, ceremony_log: CeremonyLog
    ) -> None:
        with pytest.raises(ValueError, match="manifest_version"):
            ceremony_log.append(CeremonyType.PACKAGE_SIGNING, actor="ci")

    def test_package_signing_passes(self, ceremony_log: CeremonyLog) -> None:
        entry = ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING,
            actor="ci",
            actor_role="ADMIN",
            details={"manifest_version": "3.0", "key_id": "deadbeef"},
        )
        assert entry["ceremony_type"] == "PACKAGE_SIGNING"


# ---------------------------------------------------------------------------
# Entry count and retrieval
# ---------------------------------------------------------------------------

class TestEntries:
    def test_entries_empty_initially(self, ceremony_log: CeremonyLog) -> None:
        assert ceremony_log.entries() == []

    def test_entries_returns_all_appended(self, ceremony_log: CeremonyLog) -> None:
        ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        ceremony_log.append(
            CeremonyType.RELEASE_APPROVAL, actor="alice",
            details={"release_tag": "v1.0", "approval_notes": "ok"},
        )
        assert len(ceremony_log.entries()) == 2

    def test_entries_of_type_filters_correctly(self, ceremony_log: CeremonyLog) -> None:
        ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        ceremony_log.append(
            CeremonyType.RELEASE_APPROVAL, actor="alice",
            details={"release_tag": "v1.0", "approval_notes": "ok"},
        )
        signing = ceremony_log.entries_of_type(CeremonyType.PACKAGE_SIGNING)
        assert len(signing) == 1
        assert signing[0]["ceremony_type"] == "PACKAGE_SIGNING"


# ---------------------------------------------------------------------------
# Hash chain
# ---------------------------------------------------------------------------

class TestHashChain:
    def test_first_entry_uses_genesis_hash(self, ceremony_log: CeremonyLog) -> None:
        entry = ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        assert entry["prev_entry_hash"] == GENESIS_HASH

    def test_second_entry_references_first_hash(self, ceremony_log: CeremonyLog) -> None:
        first = ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        second = ceremony_log.append(
            CeremonyType.RELEASE_APPROVAL, actor="alice",
            details={"release_tag": "v1.0", "approval_notes": "ok"},
        )
        assert second["prev_entry_hash"] == first["entry_hash"]

    def test_verify_chain_empty_log(self, ceremony_log: CeremonyLog) -> None:
        assert ceremony_log.verify_chain() == []

    def test_verify_chain_valid(self, ceremony_log: CeremonyLog) -> None:
        for i in range(3):
            ceremony_log.append(
                CeremonyType.PACKAGE_SIGNING, actor="ci",
                details={"manifest_version": "3.0", "key_id": f"key{i}"},
            )
        assert ceremony_log.verify_chain() == []

    def test_verify_chain_detects_tampered_entry(self, ceremony_log: CeremonyLog) -> None:
        ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        # Corrupt the file
        lines = ceremony_log.log_file.read_text().splitlines()
        entry = json.loads(lines[0])
        entry["actor"] = "mallory"
        lines[0] = json.dumps(entry, separators=(",", ":"))
        ceremony_log.log_file.write_text("\n".join(lines) + "\n")

        errors = ceremony_log.verify_chain()
        assert len(errors) > 0

    def test_verify_chain_detects_deleted_entry(self, ceremony_log: CeremonyLog) -> None:
        for i in range(3):
            ceremony_log.append(
                CeremonyType.PACKAGE_SIGNING, actor="ci",
                details={"manifest_version": "3.0", "key_id": f"k{i}"},
            )
        lines = [l for l in ceremony_log.log_file.read_text().splitlines() if l.strip()]
        lines.pop(1)  # delete middle entry
        ceremony_log.log_file.write_text("\n".join(lines) + "\n")

        errors = ceremony_log.verify_chain()
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# has_recent_ceremony
# ---------------------------------------------------------------------------

class TestHasRecentCeremony:
    def test_returns_false_when_no_ceremonies(self, ceremony_log: CeremonyLog) -> None:
        assert ceremony_log.has_recent_ceremony(CeremonyType.PACKAGE_SIGNING) is False

    def test_returns_true_after_appending(self, ceremony_log: CeremonyLog) -> None:
        ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        assert ceremony_log.has_recent_ceremony(CeremonyType.PACKAGE_SIGNING) is True

    def test_returns_false_for_different_type(self, ceremony_log: CeremonyLog) -> None:
        ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        assert ceremony_log.has_recent_ceremony(CeremonyType.RELEASE_APPROVAL) is False

    def test_max_age_days_accepts_recent_entry(self, ceremony_log: CeremonyLog) -> None:
        ceremony_log.append(
            CeremonyType.PACKAGE_SIGNING, actor="ci",
            details={"manifest_version": "3.0", "key_id": "abc"},
        )
        # Entry was just written — should be within any reasonable window
        assert ceremony_log.has_recent_ceremony(CeremonyType.PACKAGE_SIGNING, max_age_days=1) is True
