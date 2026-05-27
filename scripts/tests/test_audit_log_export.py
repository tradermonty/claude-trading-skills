"""Tests for AuditLog.export_log and AuditLog.verify_export."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from audit_log import AuditLog, AuditEventType, GENESIS_HASH  # noqa: E402


@pytest.fixture
def populated_log(tmp_path: Path) -> AuditLog:
    """An AuditLog with 3 events already appended."""
    log = AuditLog(tmp_path / "audit-log")
    log.append(AuditEventType.WORKFLOW_STARTED, actor="alice", run_id="run_001")
    log.append(AuditEventType.STEP_COMPLETED, actor="alice", run_id="run_001")
    log.append(AuditEventType.REVIEW_APPROVED, actor="bob", run_id="run_001")
    return log


# ---------------------------------------------------------------------------
# Plain-directory export
# ---------------------------------------------------------------------------

class TestExportLogDirectory:
    def test_export_creates_dest_directory(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        assert dest.is_dir()

    def test_export_creates_jsonl_file(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        assert (dest / "workflow-audit.jsonl").exists()

    def test_export_creates_manifest_file(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        assert (dest / "export-manifest.json").exists()

    def test_export_manifest_entry_count_correct(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        manifest = populated_log.export_log(dest)
        assert manifest["entry_count"] == 3

    def test_export_manifest_chain_valid(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        manifest = populated_log.export_log(dest)
        assert manifest["chain_valid_at_export"] is True
        assert manifest["chain_errors_at_export"] == []

    def test_export_manifest_final_hash_matches_last_entry(
        self, populated_log: AuditLog, tmp_path: Path
    ) -> None:
        dest = tmp_path / "export"
        manifest = populated_log.export_log(dest)
        entries = populated_log.entries()
        assert manifest["final_chain_hash"] == entries[-1]["entry_hash"]

    def test_export_empty_log(self, tmp_path: Path) -> None:
        log = AuditLog(tmp_path / "audit-log")
        dest = tmp_path / "export"
        manifest = log.export_log(dest)
        assert manifest["entry_count"] == 0
        assert manifest["final_chain_hash"] == GENESIS_HASH


# ---------------------------------------------------------------------------
# Compressed (.tar.gz) export
# ---------------------------------------------------------------------------

class TestExportLogCompressed:
    def test_compress_creates_tar_gz(self, populated_log: AuditLog, tmp_path: Path) -> None:
        archive = tmp_path / "export.tar.gz"
        populated_log.export_log(archive, compress=True)
        assert archive.exists()
        assert archive.stat().st_size > 0

    def test_compressed_export_verifies_ok(
        self, populated_log: AuditLog, tmp_path: Path
    ) -> None:
        archive = tmp_path / "export.tar.gz"
        populated_log.export_log(archive, compress=True)
        errors = AuditLog.verify_export(archive)
        assert errors == []

    def test_compressed_export_entry_count(
        self, populated_log: AuditLog, tmp_path: Path
    ) -> None:
        archive = tmp_path / "export.tar.gz"
        manifest = populated_log.export_log(archive, compress=True)
        assert manifest["entry_count"] == 3


# ---------------------------------------------------------------------------
# verify_export — valid cases
# ---------------------------------------------------------------------------

class TestVerifyExportValid:
    def test_valid_export_returns_no_errors(
        self, populated_log: AuditLog, tmp_path: Path
    ) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        errors = AuditLog.verify_export(dest)
        assert errors == []

    def test_empty_log_export_verifies_ok(self, tmp_path: Path) -> None:
        log = AuditLog(tmp_path / "audit-log")
        dest = tmp_path / "export"
        log.export_log(dest)
        errors = AuditLog.verify_export(dest)
        assert errors == []


# ---------------------------------------------------------------------------
# verify_export — tamper detection
# ---------------------------------------------------------------------------

class TestVerifyExportTampering:
    def test_tampered_entry_fails(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        jsonl_path = dest / "workflow-audit.jsonl"
        lines = jsonl_path.read_text().splitlines()
        # Modify actor in the first entry
        entry = json.loads(lines[0])
        entry["actor"] = "mallory"
        lines[0] = json.dumps(entry, separators=(",", ":"))
        jsonl_path.write_text("\n".join(lines) + "\n")

        errors = AuditLog.verify_export(dest)
        assert len(errors) > 0
        assert any("entry_hash mismatch" in e or "prev_entry_hash mismatch" in e for e in errors)

    def test_missing_entry_fails(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        jsonl_path = dest / "workflow-audit.jsonl"
        # Remove the middle entry
        lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
        lines.pop(1)
        jsonl_path.write_text("\n".join(lines) + "\n")

        errors = AuditLog.verify_export(dest)
        assert len(errors) > 0

    def test_reordered_entries_fail(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        jsonl_path = dest / "workflow-audit.jsonl"
        lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
        assert len(lines) >= 2
        # Swap first two entries
        lines[0], lines[1] = lines[1], lines[0]
        jsonl_path.write_text("\n".join(lines) + "\n")

        errors = AuditLog.verify_export(dest)
        assert len(errors) > 0

    def test_hash_chain_break_detected(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        jsonl_path = dest / "workflow-audit.jsonl"
        lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
        # Corrupt the prev_entry_hash on entry 1 and recompute its entry_hash
        entry = json.loads(lines[1])
        entry["prev_entry_hash"] = "a" * 64  # bad hash
        # Recompute entry_hash so the "modified" flag doesn't also fire
        import hashlib
        check = {k: v for k, v in entry.items() if k != "entry_hash"}
        entry["entry_hash"] = hashlib.sha256(
            json.dumps(check, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        lines[1] = json.dumps(entry, separators=(",", ":"))
        jsonl_path.write_text("\n".join(lines) + "\n")

        errors = AuditLog.verify_export(dest)
        assert any("prev_entry_hash mismatch" in e for e in errors)

    def test_final_hash_mismatch_detected(self, populated_log: AuditLog, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        populated_log.export_log(dest)
        manifest_path = dest / "export-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["final_chain_hash"] = "b" * 64  # wrong hash
        manifest_path.write_text(json.dumps(manifest, indent=2))

        errors = AuditLog.verify_export(dest)
        assert any("final_chain_hash mismatch" in e for e in errors)

    def test_missing_jsonl_returns_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        dest.mkdir()
        (dest / "export-manifest.json").write_text("{}")
        errors = AuditLog.verify_export(dest)
        assert len(errors) == 1
        assert "workflow-audit.jsonl" in errors[0]

    def test_missing_manifest_returns_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "export"
        dest.mkdir()
        (dest / "workflow-audit.jsonl").write_text("")
        errors = AuditLog.verify_export(dest)
        assert len(errors) == 1
        assert "export-manifest.json" in errors[0]

    def test_nonexistent_path_returns_error(self, tmp_path: Path) -> None:
        errors = AuditLog.verify_export(tmp_path / "does-not-exist")
        assert len(errors) > 0
