"""Admin ceremony log for TraderMonty governance events.

Formal admin ceremonies — key rotation, release approvals, role assignments,
waivers, and package signing — are recorded here as a machine-checkable audit
trail.  Each ceremony entry is SHA-256 hashed, and successive entries form a
hash chain identical in structure to the workflow audit log.

Ceremony types
--------------
KEY_ROTATION          — Signing key was rotated; records actor, key_id, reason.
RELEASE_APPROVAL      — A release was approved by an authorised actor; records
                        release_tag, approver, and approval_notes.
REVIEWER_ROLE_ASSIGN  — A reviewer was assigned a role (RISK_APPROVER, ADMIN…).
WAIVER_APPROVAL       — A review waiver was explicitly approved; records run_id,
                        waiver_reason, and approver_role.
PACKAGE_SIGNING       — A signing ceremony was completed; records manifest_version
                        and key_id used.

Storage: state/ceremony-log/ceremonies.jsonl (append-only by convention)

Usage:
    from ceremony_log import CeremonyLog, CeremonyType
    log = CeremonyLog(REPO_ROOT / "state" / "ceremony-log")
    log.append(
        CeremonyType.RELEASE_APPROVAL,
        actor="alice",
        details={"release_tag": "v1.2.3", "approval_notes": "All gate checks passed"},
    )
    errors = log.verify_chain()
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

CEREMONY_LOG_DIR_NAME = "ceremony-log"
CEREMONY_LOG_FILE_NAME = "ceremonies.jsonl"
GENESIS_HASH = "0" * 64

# Required fields per ceremony type — used by machine-checks
REQUIRED_CEREMONY_FIELDS: dict[str, list[str]] = {
    "KEY_ROTATION": ["key_id", "reason"],
    "RELEASE_APPROVAL": ["release_tag", "approval_notes"],
    "REVIEWER_ROLE_ASSIGN": ["assignee", "role"],
    "WAIVER_APPROVAL": ["run_id", "waiver_reason", "approver_role"],
    "PACKAGE_SIGNING": ["manifest_version", "key_id"],
}


class CeremonyType(str, Enum):
    KEY_ROTATION = "KEY_ROTATION"
    RELEASE_APPROVAL = "RELEASE_APPROVAL"
    REVIEWER_ROLE_ASSIGN = "REVIEWER_ROLE_ASSIGN"
    WAIVER_APPROVAL = "WAIVER_APPROVAL"
    PACKAGE_SIGNING = "PACKAGE_SIGNING"


class CeremonyLog:
    """Append-only JSONL ceremony log with hash chain.

    Thread-safety: NOT thread-safe.  Use a single-process writer.
    """

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_file = log_dir / CEREMONY_LOG_FILE_NAME

    def append(
        self,
        ceremony_type: CeremonyType,
        actor: str = "unspecified",
        actor_role: str = "unspecified",
        details: dict[str, Any] | None = None,
    ) -> dict:
        """Record a ceremony entry and return the entry dict.

        Parameters
        ----------
        ceremony_type:
            One of the CeremonyType enum values.
        actor:
            Identity of the person or system performing the ceremony.
        actor_role:
            Role of the actor (e.g. ADMIN, RISK_APPROVER).
        details:
            Ceremony-specific fields.  See REQUIRED_CEREMONY_FIELDS for
            what each ceremony type expects.
        """
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Validate required fields
        det = details or {}
        missing = [
            f for f in REQUIRED_CEREMONY_FIELDS.get(ceremony_type.value, [])
            if not det.get(f)
        ]
        if missing:
            raise ValueError(
                f"Ceremony {ceremony_type.value} missing required field(s): "
                + ", ".join(missing)
            )

        prev_hash = self._last_entry_hash()
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ceremony_type": ceremony_type.value,
            "actor": actor,
            "actor_role": actor_role,
            "details": det,
            "prev_entry_hash": prev_hash,
        }
        entry["entry_hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")

        return entry

    def entries(self) -> list[dict]:
        """Return all ceremony entries in order."""
        if not self.log_file.exists():
            return []
        result = []
        for line in self.log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                result.append(json.loads(line))
        return result

    def entries_of_type(self, ceremony_type: CeremonyType) -> list[dict]:
        """Return only entries matching *ceremony_type*."""
        return [e for e in self.entries() if e.get("ceremony_type") == ceremony_type.value]

    def verify_chain(self) -> list[str]:
        """Verify the hash chain.  Returns list of errors; empty = valid."""
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
            stored_hash = entry.get("entry_hash", "")
            check = {k: v for k, v in entry.items() if k != "entry_hash"}
            expected_hash = hashlib.sha256(
                json.dumps(check, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if stored_hash != expected_hash:
                errors.append(
                    f"Entry {i} (type={entry.get('ceremony_type')}): "
                    "entry_hash mismatch — entry was modified"
                )
            prev_hash = stored_hash or expected_hash
        return errors

    def has_recent_ceremony(
        self, ceremony_type: CeremonyType, max_age_days: int | None = None
    ) -> bool:
        """Return True if at least one ceremony of *ceremony_type* exists.

        If *max_age_days* is given, only ceremonies within that window count.
        """
        entries = self.entries_of_type(ceremony_type)
        if not entries:
            return False
        if max_age_days is None:
            return True
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400
        for e in entries:
            try:
                ts = datetime.fromisoformat(e["timestamp"]).timestamp()
                if ts >= cutoff:
                    return True
            except (KeyError, ValueError):
                continue
        return False

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
