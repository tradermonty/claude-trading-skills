"""Append-only workflow audit log with hash chain.

Every significant workflow event is recorded as a JSONL entry.
Each entry includes a SHA-256 hash of the previous entry, forming a
tamper-evident hash chain.  Verifying the chain detects log truncation
or entry deletion.  Entry modification is also detectable because the
next entry's prev_entry_hash would be invalid.

Log file: state/audit-log/workflow-audit.jsonl (append-only by convention)

Export format
-------------
``AuditLog.export_log(dest_path)`` writes a directory containing:
  - ``workflow-audit.jsonl``   — copy of all log entries
  - ``export-manifest.json``   — metadata: entry_count, final_chain_hash,
    exported_at, source_log_path, schema_version

Pass ``compress=True`` to write a ``.tar.gz`` archive instead.

Use ``AuditLog.verify_export(export_path)`` to verify the chain and
manifest of an exported archive (directory or ``.tar.gz``).

Usage:
    from audit_log import AuditLog, AuditEventType
    log = AuditLog(REPO_ROOT / "state" / "audit-log")
    log.append(AuditEventType.WORKFLOW_STARTED, actor="Alice", run_id="run_abc123")

    # Export
    manifest = log.export_log(Path("/tmp/audit-export"))
    # Verify export
    errors = AuditLog.verify_export(Path("/tmp/audit-export"))
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import tarfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

AUDIT_LOG_DIR_NAME = "audit-log"
AUDIT_LOG_FILE_NAME = "workflow-audit.jsonl"
GENESIS_HASH = "0" * 64  # Sentinel for the first entry


class AuditEventType(str, Enum):
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    DECISION_GATE_ANSWERED = "DECISION_GATE_ANSWERED"
    ARTIFACT_RECORDED = "ARTIFACT_RECORDED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    REVIEW_REJECTED = "REVIEW_REJECTED"
    REVIEW_WAIVED = "REVIEW_WAIVED"
    PROMOTION_BLOCKED = "PROMOTION_BLOCKED"
    PROMOTION_APPROVED = "PROMOTION_APPROVED"
    PACKAGE_SIGNED = "PACKAGE_SIGNED"
    PACKAGE_VERIFIED = "PACKAGE_VERIFIED"


class AuditLog:
    """Append-only JSONL audit log with hash chain.

    Thread-safety: NOT thread-safe. Use a single-process workflow runner.
    """

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_file = log_dir / AUDIT_LOG_FILE_NAME

    def append(
        self,
        event_type: AuditEventType,
        actor: str = "unspecified",
        run_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict:
        """Append a new audit event and return the entry dict."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

        prev_hash = self._last_entry_hash()
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type.value,
            "actor": actor,
            "run_id": run_id or "",
            "details": details or {},
            "prev_entry_hash": prev_hash,
        }
        # entry_hash covers everything except itself
        entry["entry_hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")

        return entry

    def entries(self) -> list[dict]:
        """Return all log entries in order."""
        if not self.log_file.exists():
            return []
        result = []
        for line in self.log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                result.append(json.loads(line))
        return result

    def verify_chain(self) -> list[str]:
        """Verify the hash chain. Returns list of error strings; empty = valid."""
        entries = self.entries()
        if not entries:
            return []
        errors = []
        prev_hash = GENESIS_HASH
        for i, entry in enumerate(entries):
            stored_prev = entry.get("prev_entry_hash", "")
            if stored_prev != prev_hash:
                errors.append(
                    f"Entry {i}: prev_entry_hash mismatch "
                    f"(expected {prev_hash[:12]}… got {stored_prev[:12]}…)"
                )
            # Verify the entry's own hash
            stored_hash = entry.get("entry_hash", "")
            check = dict(entry)
            check.pop("entry_hash", None)
            expected_hash = hashlib.sha256(
                json.dumps(check, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if stored_hash != expected_hash:
                errors.append(
                    f"Entry {i} (type={entry.get('event_type')}): "
                    f"entry_hash mismatch — entry was modified"
                )
            prev_hash = stored_hash or expected_hash
        return errors

    def export_log(self, dest_path: Path, compress: bool = False) -> dict:
        """Export the audit log to *dest_path* with a manifest.

        Parameters
        ----------
        dest_path:
            Directory path to write the export.  Created if absent.
            If *compress* is True, a ``.tar.gz`` archive is written at
            ``dest_path`` (the path should end with ``.tar.gz``).
        compress:
            If True, write a ``tar.gz`` archive instead of a plain directory.

        Returns
        -------
        dict
            The export manifest dict (also written as ``export-manifest.json``).
        """
        entries = self.entries()
        errors = self.verify_chain()

        # Build manifest
        final_hash = entries[-1]["entry_hash"] if entries else GENESIS_HASH
        manifest = {
            "schema_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source_log_path": str(self.log_file),
            "entry_count": len(entries),
            "final_chain_hash": final_hash,
            "chain_valid_at_export": len(errors) == 0,
            "chain_errors_at_export": errors,
        }

        jsonl_bytes = (
            "\n".join(json.dumps(e, separators=(",", ":")) for e in entries) + "\n"
            if entries
            else ""
        ).encode("utf-8")
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")

        if compress:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(dest_path, "w:gz") as tar:
                _add_bytes_to_tar(tar, AUDIT_LOG_FILE_NAME, jsonl_bytes)
                _add_bytes_to_tar(tar, "export-manifest.json", manifest_bytes)
        else:
            dest_path.mkdir(parents=True, exist_ok=True)
            (dest_path / AUDIT_LOG_FILE_NAME).write_bytes(jsonl_bytes)
            (dest_path / "export-manifest.json").write_bytes(manifest_bytes)

        return manifest

    @staticmethod
    def verify_export(export_path: Path) -> list[str]:
        """Verify the hash chain and manifest of an exported audit log.

        Parameters
        ----------
        export_path:
            Directory (plain export) or ``.tar.gz`` archive (compressed export).

        Returns
        -------
        list[str]
            List of error strings.  Empty = valid.
        """
        errors: list[str] = []

        # Load entries and manifest from export
        if export_path.is_dir():
            jsonl_path = export_path / AUDIT_LOG_FILE_NAME
            manifest_path = export_path / "export-manifest.json"
            if not jsonl_path.exists():
                return [f"Export missing {AUDIT_LOG_FILE_NAME}"]
            if not manifest_path.exists():
                return [f"Export missing export-manifest.json"]
            raw_jsonl = jsonl_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        elif str(export_path).endswith(".tar.gz") and export_path.exists():
            raw_jsonl, manifest = _read_tar_export(export_path)
            if raw_jsonl is None:
                return [f"Could not read archive {export_path}"]
        else:
            return [f"Export path not found or unrecognised format: {export_path}"]

        # Parse entries
        entries: list[dict] = []
        for i, line in enumerate(raw_jsonl.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append(f"Entry {i}: JSON decode error — {exc}")

        # Verify manifest entry_count
        expected_count = manifest.get("entry_count", -1)
        if expected_count != len(entries):
            errors.append(
                f"Manifest entry_count={expected_count} but found {len(entries)} entries "
                "(entries may have been added or removed after export)"
            )

        # Re-verify hash chain
        if not entries:
            return errors

        prev_hash = GENESIS_HASH
        for i, entry in enumerate(entries):
            stored_prev = entry.get("prev_entry_hash", "")
            if stored_prev != prev_hash:
                errors.append(
                    f"Entry {i}: prev_entry_hash mismatch "
                    f"(expected {prev_hash[:12]}… got {stored_prev[:12]}…)"
                )
            stored_hash = entry.get("entry_hash", "")
            check = {k: v for k, v in entry.items() if k != "entry_hash"}
            expected_hash = hashlib.sha256(
                json.dumps(check, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if stored_hash != expected_hash:
                errors.append(
                    f"Entry {i} (type={entry.get('event_type')}): "
                    "entry_hash mismatch — entry was modified after export"
                )
            prev_hash = stored_hash or expected_hash

        # Verify final_chain_hash matches
        actual_final = entries[-1].get("entry_hash", "") if entries else GENESIS_HASH
        expected_final = manifest.get("final_chain_hash", "")
        if expected_final and actual_final != expected_final:
            errors.append(
                f"final_chain_hash mismatch: manifest says {expected_final[:16]}… "
                f"but computed {actual_final[:16]}…"
            )

        return errors

    def _last_entry_hash(self) -> str:
        """Return the hash of the last entry, or GENESIS_HASH if log is empty."""
        if not self.log_file.exists():
            return GENESIS_HASH
        last_line = ""
        try:
            with self.log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
        except OSError:
            return GENESIS_HASH
        if not last_line:
            return GENESIS_HASH
        try:
            entry = json.loads(last_line)
            return entry.get("entry_hash", GENESIS_HASH)
        except json.JSONDecodeError:
            return GENESIS_HASH


# ---------------------------------------------------------------------------
# Archive helpers
# ---------------------------------------------------------------------------

def _add_bytes_to_tar(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    """Add raw bytes as a named file to an open tarfile."""
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _read_tar_export(archive_path: Path) -> tuple[str | None, dict | None]:
    """Read JSONL and manifest from a tar.gz export archive."""
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            jsonl_data = _extract_tar_member(tar, AUDIT_LOG_FILE_NAME)
            manifest_data = _extract_tar_member(tar, "export-manifest.json")
        if jsonl_data is None or manifest_data is None:
            return None, None
        return jsonl_data.decode("utf-8"), json.loads(manifest_data.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None, None


def _extract_tar_member(tar: tarfile.TarFile, name: str) -> bytes | None:
    """Extract a member from a TarFile by name, return bytes or None."""
    try:
        member = tar.getmember(name)
        f = tar.extractfile(member)
        return f.read() if f else None
    except KeyError:
        return None
