#!/usr/bin/env python3
"""Approved-rule ledger for the pre-trade discipline gate (issue #514).

A local JSON ledger of operating rules a human approved in a monthly review.
The ledger has an explicit lifecycle (active / superseded / retired), computed
date states, and an append-only history. Standard library only; YAML parsing of
monthly artifacts lives in ``manage_approved_rules.py``.

Rules are free text. Nothing here evaluates a rule against a trade; the gate
only requires a human acknowledgement.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MONTH_RE = re.compile(r"[0-9]{4}-[0-9]{2}")

STATUSES = ("active", "superseded", "retired")
ORIGINS = (
    "coach_accepted",
    "coach_modified",
    "trade_rule_change",
    "sample_accepted",
    "manual_supersede",
)
COACH_ACTIONS = ("accept_rules", "modify_rules", "defer", "journal_only")

STATE_NOT_YET_EFFECTIVE = "not_yet_effective"
STATE_EFFECTIVE = "effective"
STATE_REVIEW_DUE = "review_due"
STATE_EXPIRED = "expired"
APPLIED_STATES = (STATE_EFFECTIVE, STATE_REVIEW_DUE)

OUTCOME_ACTIVATED = "activated"
OUTCOME_RENEWED = "renewed"
OUTCOME_REACTIVATED = "reactivated"
OUTCOME_ALREADY_APPLIED = "already_applied"

RULE_KEYS = (
    "rule_id",
    "text",
    "status",
    "effective_date",
    "review_after",
    "expires_on",
    "origin",
    "superseded_by",
    "evidence_ids",
    "history",
)


class LedgerError(ValueError):
    """Invalid ledger content or a refused ledger operation."""


# ---------------------------------------------------------------------------
# Identity and dates
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """NFKC, case-fold, collapse whitespace runs."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def rule_id_for(text: str) -> str:
    digest = hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
    return f"rule_{digest[:12]}"


def parse_date(value: Any, label: str) -> date:
    """Parse an input date: an exact YYYY-MM-DD string or a YAML date (no padding allowed)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise LedgerError(f"{label} must be a YYYY-MM-DD date, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"{label} is not a valid date: {value!r}") from exc


def norm_date(value: Any, label: str) -> str:
    """Canonical stored form of an input date."""
    return parse_date(value, label).isoformat()


def _stored_date(value: Any, label: str) -> date:
    """Stored dates must be canonical strings (never date objects or padded text)."""
    if not isinstance(value, str):
        raise LedgerError(f"{label} must be a YYYY-MM-DD string, got {value!r}")
    return parse_date(value, label)


def _opt_stored_date(value: Any, label: str) -> date | None:
    return None if value is None else _stored_date(value, label)


def _opt_date(value: Any, label: str) -> date | None:
    return None if value is None else parse_date(value, label)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Ledger validation and persistence
# ---------------------------------------------------------------------------


def empty_ledger() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "rules": []}


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_ledger(data: Any) -> dict[str, Any]:
    """Validate the whole ledger; raise LedgerError on any problem."""
    if not isinstance(data, dict):
        raise LedgerError("ledger must be a JSON object")
    version = data.get("schema_version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise LedgerError(f"ledger schema_version must be {SCHEMA_VERSION}, got {version!r}")
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise LedgerError("ledger 'rules' must be a list")

    by_id: dict[str, dict[str, Any]] = {}
    for idx, rule in enumerate(rules, start=1):
        label = f"rule #{idx}"
        if not isinstance(rule, dict):
            raise LedgerError(f"{label} must be an object")
        missing = [key for key in RULE_KEYS if key not in rule]
        if missing:
            raise LedgerError(f"{label} missing keys: {', '.join(missing)}")
        rule_id = rule["rule_id"]
        if not _is_nonempty_str(rule_id):
            raise LedgerError(f"{label} rule_id must be a non-empty string")
        label = f"rule {rule_id}"
        if rule_id in by_id:
            raise LedgerError(f"duplicate rule_id {rule_id}")
        if not _is_nonempty_str(rule["text"]):
            raise LedgerError(f"{label} text must be a non-empty string")
        if rule_id_for(rule["text"]) != rule_id:
            raise LedgerError(f"{label} rule_id does not match its text")
        if rule["status"] not in STATUSES:
            raise LedgerError(f"{label} has unknown status {rule['status']!r}")
        if rule["origin"] not in ORIGINS:
            raise LedgerError(f"{label} has unknown origin {rule['origin']!r}")
        successor = rule["superseded_by"]
        if successor is not None and not isinstance(successor, str):
            raise LedgerError(f"{label} superseded_by must be null or a string")
        effective = _stored_date(rule["effective_date"], f"{label} effective_date")
        review_after = _stored_date(rule["review_after"], f"{label} review_after")
        expires = _opt_stored_date(rule["expires_on"], f"{label} expires_on")
        if review_after < effective:
            raise LedgerError(f"{label} review_after is before effective_date")
        if expires is not None and expires < effective:
            raise LedgerError(f"{label} expires_on is before effective_date")
        evidence = rule["evidence_ids"]
        if not isinstance(evidence, list) or not all(isinstance(e, str) for e in evidence):
            raise LedgerError(f"{label} evidence_ids must be a list of strings")
        history = rule["history"]
        if not isinstance(history, list) or not history:
            raise LedgerError(f"{label} history must be a non-empty list")
        for event in history:
            if not isinstance(event, dict) or not _is_nonempty_str(event.get("event")):
                raise LedgerError(f"{label} has a malformed history event")
            if not _is_nonempty_str(event.get("at")):
                raise LedgerError(f"{label} has a history event without 'at'")
        by_id[rule_id] = rule

    for rule_id, rule in by_id.items():
        successor = rule["superseded_by"]
        if (rule["status"] == "superseded") != (successor is not None):
            raise LedgerError(
                f"rule {rule_id}: superseded_by must be set if and only if superseded"
            )
        if successor is not None and successor not in by_id:
            raise LedgerError(f"rule {rule_id}: superseded_by {successor!r} does not exist")
    for rule_id in by_id:  # reject supersession cycles
        seen = {rule_id}
        current = by_id[rule_id]["superseded_by"]
        while current is not None:
            if current in seen:
                raise LedgerError(f"rule {rule_id}: supersession chain has a cycle")
            seen.add(current)
            current = by_id[current]["superseded_by"]
    check_supersession_invariant(data, loaded=True)
    return data


def load_ledger(path: Path, *, missing_ok: bool = False) -> dict[str, Any]:
    """Read and validate a ledger. An invalid ledger is never treated as empty."""
    if not path.exists():
        if missing_ok:
            return empty_ledger()
        raise LedgerError(f"ledger not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerError(f"ledger could not be read: {exc}") from exc
    return validate_ledger(data)


def save_ledger(path: Path, data: dict[str, Any]) -> None:
    """Validate then write atomically (single-user; no cross-process locking)."""
    validate_ledger(data)
    text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    target = Path(os.path.realpath(path))  # write through a symlinked ledger
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=".approved_rules_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Computed state and the gate's view
# ---------------------------------------------------------------------------


def compute_state(rule: dict[str, Any], as_of: date) -> str:
    status = rule["status"]
    if status != "active":
        return status
    effective = date.fromisoformat(rule["effective_date"])
    review_after = date.fromisoformat(rule["review_after"])
    expires = rule["expires_on"]
    if as_of < effective:
        return STATE_NOT_YET_EFFECTIVE
    if expires is not None and as_of > date.fromisoformat(expires):
        return STATE_EXPIRED
    if as_of > review_after:
        return STATE_REVIEW_DUE
    return STATE_EFFECTIVE


def build_view(ledger: dict[str, Any], as_of: date) -> dict[str, Any]:
    """Split rules into applied / not applied for the gate, with warnings."""
    applied: list[dict[str, Any]] = []
    not_applied: list[dict[str, Any]] = []
    warnings: list[str] = []
    for rule in ledger["rules"]:
        state = compute_state(rule, as_of)
        if state in APPLIED_STATES:
            applied.append(
                {
                    "rule_id": rule["rule_id"],
                    "text": rule["text"],
                    "state": state,
                    "effective_date": rule["effective_date"],
                    "review_after": rule["review_after"],
                    "expires_on": rule["expires_on"],
                    "origin": rule["origin"],
                }
            )
        else:
            not_applied.append({"rule_id": rule["rule_id"], "state": state})
        if state == STATE_REVIEW_DUE:
            warnings.append(
                f"approved rule {rule['rule_id']} is past its review date "
                f"{rule['review_after']}; it still applies - extend, renew, or retire it"
            )
        elif state == STATE_EXPIRED:
            warnings.append(
                f"approved rule {rule['rule_id']} expired on {rule['expires_on']} "
                "and is not applied"
            )
    return {
        "as_of_date": as_of.isoformat(),
        "applied": applied,
        "not_applied": not_applied,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Activation input
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    text: str
    origin: str
    source_rule_ref: str | None = None
    source_rule_local_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ActivationInput:
    shape: str
    candidates: list[Candidate]
    source_review_id: str
    review_after: Any
    human_notes: str | None
    skipped: list[str] = field(default_factory=list)


def _validate_rule_strings(values: Any, label: str) -> list[str]:
    if not isinstance(values, list):
        raise LedgerError(f"{label} must be a list")
    for value in values:
        if not _is_nonempty_str(value):
            raise LedgerError(f"{label} must contain only non-empty strings")
    if len({normalize_text(v) for v in values}) != len(values):
        raise LedgerError(f"{label} must be unique")
    return [v.strip() for v in values]


def _validate_replay_decision(decision: Any) -> dict[str, Any]:
    if not isinstance(decision, dict):
        raise LedgerError("coach_rule_decision must be an object or null")
    missing = [
        k
        for k in ("source_review_id", "action", "accepted_rules", "human_notes")
        if k not in decision
    ]
    if missing:
        raise LedgerError(f"coach_rule_decision missing keys: {', '.join(missing)}")
    if "schema_version" in decision and (
        isinstance(decision["schema_version"], bool) or decision["schema_version"] != 1
    ):
        raise LedgerError("coach_rule_decision schema_version must be 1")
    if not _is_nonempty_str(decision["source_review_id"]):
        raise LedgerError("coach_rule_decision source_review_id must be a non-empty string")
    action = decision["action"]
    if not isinstance(action, str) or action not in COACH_ACTIONS:
        raise LedgerError(f"coach_rule_decision action must be one of {', '.join(COACH_ACTIONS)}")
    rules = _validate_rule_strings(decision["accepted_rules"], "coach_rule_decision accepted_rules")
    if action in ("accept_rules", "modify_rules") and not rules:
        raise LedgerError("coach_rule_decision accept/modify requires non-empty accepted_rules")
    if action in ("defer", "journal_only") and rules:
        raise LedgerError("coach_rule_decision defer/journal_only cannot contain accepted_rules")
    if not _is_nonempty_str(decision["human_notes"]):
        raise LedgerError("coach_rule_decision human_notes must be a non-empty string")
    return decision


def _check_no_duplicates(candidates: list[Candidate]) -> None:
    seen: set[str] = set()
    for candidate in candidates:
        key = normalize_text(candidate.text)
        if key in seen:
            raise LedgerError(f"duplicate rule text in the input file: {candidate.text!r}")
        seen.add(key)


def extract_candidates(
    data: Any,
    *,
    include_trade_rule_changes: bool = False,
    source_review_id: str | None = None,
    review_after: str | None = None,
    effective_date: str | None = None,
) -> ActivationInput:
    """Detect the artifact shape explicitly and return the activation candidates."""
    if isinstance(data, dict):
        version = data.get("schema_version")
        if (
            isinstance(version, int)
            and not isinstance(version, bool)
            and version == 1
            and "coach_rule_decision" in data
        ):
            return _extract_replay(
                data,
                include_trade_rule_changes=include_trade_rule_changes,
                source_review_id=source_review_id,
                review_after=review_after,
            )
        if version == "1.0" and "rules" in data:
            return _extract_sample(
                data,
                source_review_id=source_review_id,
                review_after=review_after,
                effective_date=effective_date,
            )
    raise LedgerError(
        "unrecognized rule-changes file. Accepted shapes: replay shape "
        "(schema_version: 1 with coach_rule_decision) or sample shape "
        '(schema_version: "1.0" with rules)'
    )


def _extract_replay(
    data: dict[str, Any],
    *,
    include_trade_rule_changes: bool,
    source_review_id: str | None,
    review_after: str | None,
) -> ActivationInput:
    if data.get("rule_activation") != "not_performed":
        raise LedgerError("replay-shape rule_activation must be 'not_performed'")
    decision_raw = data["coach_rule_decision"]
    candidates: list[Candidate] = []
    human_notes: str | None = None
    review_id = source_review_id
    if decision_raw is not None:
        decision = _validate_replay_decision(decision_raw)
        if source_review_id is not None and source_review_id != decision["source_review_id"]:
            raise LedgerError(
                "--source-review-id disagrees with coach_rule_decision source_review_id "
                f"{decision['source_review_id']!r}"
            )
        review_id = decision["source_review_id"]
        human_notes = decision["human_notes"].strip()
        origin = {"accept_rules": "coach_accepted", "modify_rules": "coach_modified"}.get(
            decision["action"]
        )
        if origin is not None:
            candidates.extend(
                Candidate(text=text, origin=origin)
                for text in _validate_rule_strings(
                    decision["accepted_rules"], "coach_rule_decision accepted_rules"
                )
            )
    if include_trade_rule_changes:
        changes = _validate_rule_strings(data.get("trade_rule_changes"), "trade_rule_changes")
        candidates.extend(Candidate(text=text, origin="trade_rule_change") for text in changes)
    if not candidates:
        raise LedgerError("nothing to activate: the file contributes no approved rules")
    if review_id is None or not review_id.strip():
        raise LedgerError("--source-review-id is required when coach_rule_decision is null")
    if review_after is None:
        raise LedgerError("--review-after is required for the replay shape")
    _check_no_duplicates(candidates)
    return ActivationInput("replay", candidates, review_id.strip(), review_after, human_notes)


def _extract_sample(
    data: dict[str, Any],
    *,
    source_review_id: str | None,
    review_after: str | None,
    effective_date: str | None,
) -> ActivationInput:
    rules = data["rules"]
    if not isinstance(rules, list):
        raise LedgerError("sample-shape 'rules' must be a list")
    if source_review_id is None or not source_review_id.strip():
        raise LedgerError("--source-review-id is required for the sample shape")
    month = data.get("effective_month")
    if not isinstance(month, str) or not MONTH_RE.match(month):
        raise LedgerError("sample-shape effective_month must be YYYY-MM")
    if effective_date is None:
        raise LedgerError(f"--effective-date must fall inside effective_month {month}")
    if not norm_date(effective_date, "--effective-date").startswith(month + "-"):
        raise LedgerError(f"--effective-date must fall inside effective_month {month}")
    candidates: list[Candidate] = []
    skipped: list[str] = []
    for idx, entry in enumerate(rules, start=1):
        if not isinstance(entry, dict):
            raise LedgerError(f"sample-shape rules[{idx}] must be an object")
        if entry.get("status") != "ACCEPTED":
            skipped.append(f"status {entry.get('status')!r} - {entry.get('rule')}")
            continue
        if not _is_nonempty_str(entry.get("rule")):
            raise LedgerError(f"sample-shape rules[{idx}] rule must be a non-empty string")
        evidence = entry.get("evidence_ids", [])
        if not isinstance(evidence, list) or not all(isinstance(e, str) for e in evidence):
            raise LedgerError(f"sample-shape rules[{idx}] evidence_ids must be a list of strings")
        ref = entry.get("source_rule_id")
        local = entry.get("rule_id")
        candidates.append(
            Candidate(
                text=entry["rule"].strip(),
                origin="sample_accepted",
                source_rule_ref=ref if isinstance(ref, str) else None,
                source_rule_local_id=local if isinstance(local, str) else None,
                evidence_ids=list(evidence),
            )
        )
    if not candidates:
        raise LedgerError("nothing to activate: the file contains no ACCEPTED rules")
    effective_review = review_after if review_after is not None else data.get("review_after")
    if effective_review is None:
        raise LedgerError("--review-after is required (the file has no review_after)")
    _check_no_duplicates(candidates)
    return ActivationInput(
        "sample", candidates, source_review_id.strip(), effective_review, None, skipped
    )


# ---------------------------------------------------------------------------
# Lifecycle operations (all work on a deep copy and return a new ledger)
# ---------------------------------------------------------------------------


def _find(ledger: dict[str, Any], rule_id: str) -> dict[str, Any]:
    for rule in ledger["rules"]:
        if rule["rule_id"] == rule_id:
            return rule
    raise LedgerError(f"rule not found: {rule_id}")


def _chain_end(ledger: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    """Follow superseded_by to the last rule of the chain."""
    current = rule
    while current["superseded_by"] is not None:
        current = _find(ledger, current["superseded_by"])
    return current


def _blocking_successor(ledger: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    """Return the chain end when it is active (it blocks restoring `rule`)."""
    end = _chain_end(ledger, rule)
    if end is not rule and end["status"] == "active":
        return end
    return None


def _chain_ids(ledger: dict[str, Any], rule: dict[str, Any]) -> list[str]:
    """Ids from a rule's successor to the end of its supersession chain."""
    ids: list[str] = []
    current = rule
    while current["superseded_by"] is not None:
        current = _find(ledger, current["superseded_by"])
        ids.append(current["rule_id"])
    return ids


def check_supersession_invariant(ledger: dict[str, Any], *, loaded: bool = False) -> None:
    """A rule revived after supersession must never be active beside its former chain.

    Reactivation and restore from `superseded` record `former_successors` in the history
    event. For every active rule, no id recorded in any of its history events may be active.
    """
    active = {r["rule_id"] for r in ledger["rules"] if r["status"] == "active"}
    for rule in ledger["rules"]:
        if rule["status"] != "active":
            continue
        for ev in rule["history"]:
            former = ev.get("former_successors")
            if not isinstance(former, list):
                continue
            for other in former:
                if other in active:
                    if loaded:
                        raise LedgerError(
                            "the ledger file violates the supersession invariant: rules "
                            f"{rule['rule_id']} and {other} are both active although "
                            f"{other} superseded {rule['rule_id']}; correct the ledger file "
                            "by hand (set one of them to retired) because the CLI cannot "
                            "open it"
                        )
                    raise LedgerError(
                        f"rule {other} cannot be active while rule {rule['rule_id']}, which it "
                        "superseded, is active; retire one of them first"
                    )


def _refuse_same_batch_supersession_pair(
    ledger: dict[str, Any], activation: ActivationInput
) -> None:
    """Refuse a batch that contains a superseded rule and a rule of its successor chain."""
    batch = {rule_id_for(c.text) for c in activation.candidates}
    for candidate in activation.candidates:
        rule_id = rule_id_for(candidate.text)
        rule = next((r for r in ledger["rules"] if r["rule_id"] == rule_id), None)
        if rule is None or rule["status"] != "superseded":
            continue
        for successor in _chain_ids(ledger, rule):
            if successor in batch:
                raise LedgerError(
                    f"rules {rule_id} and {successor} are both in this review, but {successor} "
                    f"superseded {rule_id}; approve only one of them"
                )


def _date_mismatch_note(
    rule: dict[str, Any],
    applied_idx: int,
    effective_date: str,
    review_after: str,
    expires_on: str | None,
) -> str:
    """Warn when a re-run from the same review carries different dates than were stored."""
    history = rule["history"]
    if history[applied_idx]["event"] not in ("activated", "reactivated"):
        return ""
    later_date_changes = ("extended", "renewed", "reactivated")
    if any(ev["event"] in later_date_changes for ev in history[applied_idx + 1 :]):
        return ""
    stored = {
        "effective_date": rule["effective_date"],
        "review_after": rule["review_after"],
        "expires_on": rule["expires_on"],
    }
    given = {
        "effective_date": effective_date,
        "review_after": review_after,
        "expires_on": expires_on,
    }
    diffs = [
        f"{k}: stored {stored[k]}, command {given[k]}" for k in stored if stored[k] != given[k]
    ]
    if not diffs:
        return ""
    return (
        "dates differ from the stored rule (" + "; ".join(diffs) + "); this review was already "
        "applied and nothing changed. Use 'extend' to change the dates"
    )


def _event(now: datetime, event: str, **fields: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"at": now.isoformat(), "event": event}
    row.update(fields)
    return row


def _union(existing: list[str], extra: list[str]) -> list[str]:
    merged = list(existing)
    for item in extra:
        if item not in merged:
            merged.append(item)
    return merged


@dataclass
class Outcome:
    rule_id: str
    text: str
    outcome: str
    note: str = ""


def apply_activation(
    ledger: dict[str, Any],
    activation: ActivationInput,
    *,
    effective_date: str,
    review_after: str,
    expires_on: str | None,
    source_sha256: str,
    now: datetime,
) -> tuple[dict[str, Any], list[Outcome]]:
    """Resolve every candidate in memory; raise before anything is written."""
    effective_date = norm_date(effective_date, "--effective-date")
    review_after = norm_date(review_after, "--review-after")
    expires_on = None if expires_on is None else norm_date(expires_on, "--expires-on")
    new = copy.deepcopy(ledger)
    _refuse_same_batch_supersession_pair(new, activation)
    outcomes: list[Outcome] = []
    for candidate in activation.candidates:
        rule_id = rule_id_for(candidate.text)
        existing = next((r for r in new["rules"] if r["rule_id"] == rule_id), None)
        if existing is not None and normalize_text(existing["text"]) != normalize_text(
            candidate.text
        ):
            raise LedgerError(f"rule id collision for {rule_id}")
        event_fields = {
            "origin": candidate.origin,
            "source_review_id": activation.source_review_id,
            "source_artifact_sha256": source_sha256,
            "source_rule_ref": candidate.source_rule_ref,
            "source_rule_local_id": candidate.source_rule_local_id,
            "evidence_ids": list(candidate.evidence_ids),
            "human_notes": activation.human_notes,
        }
        if existing is None:
            new["rules"].append(
                {
                    "rule_id": rule_id,
                    "text": candidate.text,
                    "status": "active",
                    "effective_date": effective_date,
                    "review_after": review_after,
                    "expires_on": expires_on,
                    "origin": candidate.origin,
                    "superseded_by": None,
                    "evidence_ids": list(candidate.evidence_ids),
                    "history": [_event(now, "activated", detail="first approval", **event_fields)],
                }
            )
            outcomes.append(Outcome(rule_id, candidate.text, OUTCOME_ACTIVATED))
            continue

        applied_idx = next(
            (
                i
                for i, ev in enumerate(existing["history"])
                if ev.get("source_review_id") == activation.source_review_id
            ),
            None,
        )
        if applied_idx is not None:
            note = _date_mismatch_note(
                existing, applied_idx, effective_date, review_after, expires_on
            )
            outcomes.append(Outcome(rule_id, candidate.text, OUTCOME_ALREADY_APPLIED, note))
            continue

        status = existing["status"]
        if status == "active":
            kept = date.fromisoformat(existing["review_after"]) >= date.fromisoformat(review_after)
            if not kept:
                existing["review_after"] = review_after
            previous_expiry = existing["expires_on"]
            existing["expires_on"] = expires_on
            detail = "renewal; review_after "
            detail += "kept the existing later date" if kept else "moved later"
            existing["evidence_ids"] = _union(existing["evidence_ids"], candidate.evidence_ids)
            existing["history"].append(_event(now, "renewed", detail=detail, **event_fields))
            note = "effective_date unchanged"
            if kept:
                note += f"; review_after kept at {existing['review_after']} (existing is later)"
            if previous_expiry is not None and expires_on is None:
                note += f"; expires_on cleared (was {previous_expiry})"
            elif previous_expiry != expires_on:
                note += f"; expires_on set to {expires_on} (was {previous_expiry})"
            outcomes.append(Outcome(rule_id, candidate.text, OUTCOME_RENEWED, note))
            continue

        former: list[str] = []
        if status == "superseded":
            blocker = _blocking_successor(new, existing)
            if blocker is not None:
                raise LedgerError(
                    f"rule {rule_id} is superseded and its successor {blocker['rule_id']} is "
                    "active; retire the successor first, or approve the successor's text instead"
                )
            former = _chain_ids(new, existing)
        if former:
            event_fields["former_successors"] = former
        existing["status"] = "active"
        existing["superseded_by"] = None
        existing["effective_date"] = effective_date
        existing["review_after"] = review_after
        existing["expires_on"] = expires_on
        existing["evidence_ids"] = _union(existing["evidence_ids"], candidate.evidence_ids)
        existing["history"].append(
            _event(now, "reactivated", detail=f"reactivated from {status}", **event_fields)
        )
        outcomes.append(Outcome(rule_id, candidate.text, OUTCOME_REACTIVATED))
    check_supersession_invariant(new)
    validate_ledger(new)
    return new, outcomes


def supersede_rule(
    ledger: dict[str, Any],
    *,
    rule_id: str,
    text: str,
    effective_date: str,
    review_after: str,
    expires_on: str | None,
    reason: str,
    now: datetime,
) -> tuple[dict[str, Any], str]:
    new = copy.deepcopy(ledger)
    if not _is_nonempty_str(text):
        raise LedgerError("--text must be a non-empty string")
    if not _is_nonempty_str(reason):
        raise LedgerError("--reason must be a non-empty string")
    old = _find(new, rule_id)
    if old["status"] != "active":
        raise LedgerError(
            f"rule {rule_id} is {old['status']}; only an active rule can be superseded"
        )
    new_text = text.strip()
    new_id = rule_id_for(new_text)
    if any(r["rule_id"] == new_id for r in new["rules"]):
        raise LedgerError(
            f"a rule with this text already exists ({new_id}); use 'restore' or a new 'activate' "
            "instead of supersede"
        )
    effective_date = norm_date(effective_date, "--effective-date")
    review_after = norm_date(review_after, "--review-after")
    expires_on = None if expires_on is None else norm_date(expires_on, "--expires-on")
    new["rules"].append(
        {
            "rule_id": new_id,
            "text": new_text,
            "status": "active",
            "effective_date": effective_date,
            "review_after": review_after,
            "expires_on": expires_on,
            "origin": "manual_supersede",
            "superseded_by": None,
            "evidence_ids": [],
            "history": [
                _event(
                    now,
                    "activated",
                    origin="manual_supersede",
                    source_review_id=None,
                    source_artifact_sha256=None,
                    source_rule_ref=None,
                    source_rule_local_id=None,
                    evidence_ids=[],
                    human_notes=None,
                    detail=f"supersedes {rule_id}: {reason.strip()}",
                    superseded_id=rule_id,
                    reason=reason.strip(),
                )
            ],
        }
    )
    old["status"] = "superseded"
    old["superseded_by"] = new_id
    old["history"].append(
        _event(
            now,
            "superseded",
            detail=f"superseded by {new_id}: {reason.strip()}",
            successor_id=new_id,
            reason=reason.strip(),
        )
    )
    validate_ledger(new)
    return new, new_id


def retire_rule(
    ledger: dict[str, Any], *, rule_id: str, reason: str, now: datetime
) -> dict[str, Any]:
    if not _is_nonempty_str(reason):
        raise LedgerError("--reason must be a non-empty string")
    new = copy.deepcopy(ledger)
    rule = _find(new, rule_id)
    if rule["status"] != "active":
        raise LedgerError(f"rule {rule_id} is {rule['status']}; only an active rule can be retired")
    rule["status"] = "retired"
    rule["history"].append(_event(now, "retired", detail=reason.strip(), reason=reason.strip()))
    validate_ledger(new)
    return new


def extend_rule(
    ledger: dict[str, Any],
    *,
    rule_id: str,
    review_after: str | None,
    expires_on: str | None,
    clear_expiry: bool,
    reason: str,
    now: datetime,
) -> dict[str, Any]:
    if review_after is None and expires_on is None and not clear_expiry:
        raise LedgerError(
            "extend needs at least one of --review-after, --expires-on, --clear-expiry"
        )
    if expires_on is not None and clear_expiry:
        raise LedgerError("--expires-on and --clear-expiry cannot be combined")
    if not _is_nonempty_str(reason):
        raise LedgerError("--reason must be a non-empty string")
    new = copy.deepcopy(ledger)
    rule = _find(new, rule_id)
    if rule["status"] != "active":
        raise LedgerError(
            f"rule {rule_id} is {rule['status']}; only an active rule can be extended"
        )
    changes: list[str] = []
    if review_after is not None:
        review_after = norm_date(review_after, "--review-after")
        target = date.fromisoformat(review_after)
        if target <= date.fromisoformat(rule["review_after"]):
            raise LedgerError(
                f"--review-after must be later than the current value {rule['review_after']}"
            )
        changes.append(f"review_after {rule['review_after']} -> {review_after}")
        rule["review_after"] = review_after
    if expires_on is not None:
        expires_on = norm_date(expires_on, "--expires-on")
        target = date.fromisoformat(expires_on)
        current = rule["expires_on"]
        if current is not None and target <= date.fromisoformat(current):
            raise LedgerError(
                f"--expires-on must be later than the current value {current}; "
                "to shorten a rule's life, retire it"
            )
        changes.append(f"expires_on {current} -> {expires_on}")
        rule["expires_on"] = expires_on
    if clear_expiry:
        changes.append(f"expires_on {rule['expires_on']} -> null")
        rule["expires_on"] = None
    rule["history"].append(
        _event(now, "extended", detail="; ".join(changes), reason=reason.strip())
    )
    validate_ledger(new)
    return new


def restore_rule(
    ledger: dict[str, Any], *, rule_id: str, reason: str, now: datetime
) -> dict[str, Any]:
    if not _is_nonempty_str(reason):
        raise LedgerError("--reason must be a non-empty string")
    new = copy.deepcopy(ledger)
    rule = _find(new, rule_id)
    status = rule["status"]
    if status == "active":
        raise LedgerError(f"rule {rule_id} is already active")
    extra: dict[str, Any] = {}
    if status == "superseded":
        blocker = _blocking_successor(new, rule)
        if blocker is not None:
            raise LedgerError(
                f"rule {rule_id} is superseded and its successor {blocker['rule_id']} is active; "
                "retire the successor first"
            )
        extra["former_successors"] = _chain_ids(new, rule)
        rule["superseded_by"] = None
    rule["status"] = "active"
    rule["history"].append(
        _event(
            now,
            "restored",
            detail=f"restored from {status}: {reason.strip()}",
            reason=reason.strip(),
            **extra,
        )
    )
    check_supersession_invariant(new)
    validate_ledger(new)
    return new
