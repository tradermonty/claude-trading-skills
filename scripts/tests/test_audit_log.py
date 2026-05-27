"""Tests for scripts/audit_log.py — append-only audit log with hash chain."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is on the path
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from audit_log import AuditLog, AuditEventType, GENESIS_HASH  # noqa: E402


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "audit-log"


@pytest.fixture
def audit_log(log_dir: Path) -> AuditLog:
    return AuditLog(log_dir)


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------

class TestFileCreation:
    def test_append_creates_dir_and_file(self, audit_log: AuditLog) -> None:
        assert not audit_log.log_file.exists()
        audit_log.append(AuditEventType.WORKFLOW_STARTED)
        assert audit_log.log_file.exists()

    def test_log_dir_created_on_first_append(self, log_dir: Path) -> None:
        assert not log_dir.exists()
        log = AuditLog(log_dir)
        log.append(AuditEventType.WORKFLOW_STARTED)
        assert log_dir.exists()


# ---------------------------------------------------------------------------
# Entry count
# ---------------------------------------------------------------------------

class TestEntryCount:
    def test_entries_empty_before_first_append(self, audit_log: AuditLog) -> None:
        assert audit_log.entries() == []

    def test_append_increments_entry_count(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED)
        assert len(audit_log.entries()) == 1
        audit_log.append(AuditEventType.STEP_COMPLETED)
        assert len(audit_log.entries()) == 2

    def test_entries_returns_list(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.REVIEW_APPROVED)
        result = audit_log.entries()
        assert isinstance(result, list)

    def test_entries_returns_correct_count(self, audit_log: AuditLog) -> None:
        for _ in range(5):
            audit_log.append(AuditEventType.STEP_COMPLETED, actor="alice")
        assert len(audit_log.entries()) == 5


# ---------------------------------------------------------------------------
# Entry content
# ---------------------------------------------------------------------------

class TestEntryContent:
    def test_event_type_recorded_correctly(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.REVIEW_APPROVED, actor="bob", run_id="run_123")
        entry = audit_log.entries()[0]
        assert entry["event_type"] == "REVIEW_APPROVED"

    def test_actor_recorded_correctly(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED, actor="charlie")
        entry = audit_log.entries()[0]
        assert entry["actor"] == "charlie"

    def test_run_id_recorded_correctly(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED, run_id="run_abc999")
        entry = audit_log.entries()[0]
        assert entry["run_id"] == "run_abc999"

    def test_details_recorded_correctly(self, audit_log: AuditLog) -> None:
        audit_log.append(
            AuditEventType.DECISION_GATE_ANSWERED,
            details={"step": 3, "answer": "yes"},
        )
        entry = audit_log.entries()[0]
        assert entry["details"]["step"] == 3
        assert entry["details"]["answer"] == "yes"

    def test_default_actor_is_unspecified(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED)
        entry = audit_log.entries()[0]
        assert entry["actor"] == "unspecified"

    def test_empty_run_id_when_not_provided(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED)
        entry = audit_log.entries()[0]
        assert entry["run_id"] == ""

    def test_timestamp_present(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED)
        entry = audit_log.entries()[0]
        assert "timestamp" in entry
        assert entry["timestamp"]  # non-empty

    def test_append_returns_entry_dict(self, audit_log: AuditLog) -> None:
        result = audit_log.append(AuditEventType.WORKFLOW_STARTED, actor="dave")
        assert isinstance(result, dict)
        assert result["event_type"] == "WORKFLOW_STARTED"
        assert "entry_hash" in result


# ---------------------------------------------------------------------------
# Genesis hash
# ---------------------------------------------------------------------------

class TestGenesisHash:
    def test_genesis_hash_sentinel_value(self) -> None:
        assert GENESIS_HASH == "0" * 64

    def test_first_entry_prev_hash_is_genesis(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED)
        entry = audit_log.entries()[0]
        assert entry["prev_entry_hash"] == GENESIS_HASH


# ---------------------------------------------------------------------------
# Hash chain
# ---------------------------------------------------------------------------

class TestHashChain:
    def test_verify_chain_passes_on_clean_log(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED, actor="alice", run_id="run_1")
        audit_log.append(AuditEventType.STEP_COMPLETED, actor="alice", run_id="run_1")
        audit_log.append(AuditEventType.REVIEW_APPROVED, actor="bob", run_id="run_1")
        errors = audit_log.verify_chain()
        assert errors == []

    def test_verify_chain_passes_on_empty_log(self, audit_log: AuditLog) -> None:
        errors = audit_log.verify_chain()
        assert errors == []

    def test_verify_chain_passes_on_single_entry(self, audit_log: AuditLog) -> None:
        audit_log.append(AuditEventType.WORKFLOW_STARTED)
        errors = audit_log.verify_chain()
        assert errors == []

    def test_hash_chain_links_correctly(self, audit_log: AuditLog) -> None:
        """Each entry's prev_entry_hash should match the previous entry's entry_hash."""
        for i in range(4):
            audit_log.append(AuditEventType.STEP_COMPLETED, actor=f"user{i}")
        entries = audit_log.entries()
        assert entries[0]["prev_entry_hash"] == GENESIS_HASH
        for i in range(1, len(entries)):
            assert entries[i]["prev_entry_hash"] == entries[i - 1]["entry_hash"]

    def test_verify_chain_detects_tampered_entry(self, audit_log: AuditLog) -> None:
        """Modifying an entry's content should be detected."""
        audit_log.append(AuditEventType.WORKFLOW_STARTED, actor="alice")
        audit_log.append(AuditEventType.STEP_COMPLETED, actor="alice")
        audit_log.append(AuditEventType.REVIEW_APPROVED, actor="bob")

        # Read the raw JSONL and tamper with the first entry
        lines = audit_log.log_file.read_text(encoding="utf-8").splitlines()
        entry0 = json.loads(lines[0])
        entry0["actor"] = "mallory"  # tampered!
        lines[0] = json.dumps(entry0, separators=(",", ":"))
        audit_log.log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        errors = audit_log.verify_chain()
        assert len(errors) >= 1
        # Should detect entry 0's hash mismatch
        assert any("entry_hash mismatch" in e for e in errors)

    def test_verify_chain_detects_deleted_entry(self, audit_log: AuditLog) -> None:
        """Deleting a middle entry (truncation) should break the chain."""
        audit_log.append(AuditEventType.WORKFLOW_STARTED, actor="alice", run_id="run_1")
        audit_log.append(AuditEventType.STEP_COMPLETED, actor="alice", run_id="run_1")
        audit_log.append(AuditEventType.REVIEW_APPROVED, actor="bob", run_id="run_1")
        audit_log.append(AuditEventType.PROMOTION_APPROVED, actor="carol", run_id="run_1")

        # Remove line 1 (the second entry) to simulate deletion
        lines = audit_log.log_file.read_text(encoding="utf-8").splitlines()
        del lines[1]
        audit_log.log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        errors = audit_log.verify_chain()
        # After removing line 1, entry at index 1 (originally index 2)
        # will have a prev_entry_hash pointing to entry 0's hash, but
        # the chain now has entry 0 → (deleted) → entry 2, so chain is broken.
        assert len(errors) >= 1

    def test_entry_hash_covers_all_fields(self, audit_log: AuditLog) -> None:
        """entry_hash should change if any payload field changes."""
        import hashlib as _hashlib

        entry = audit_log.append(AuditEventType.WORKFLOW_STARTED, actor="alice")
        check = dict(entry)
        check.pop("entry_hash")
        expected = _hashlib.sha256(
            json.dumps(check, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert entry["entry_hash"] == expected
