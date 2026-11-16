#!/usr/bin/env python3
"""
Blind replay of the user's own VCP decisions (issue #710).

Subcommands:
  capture          - freeze a vcp-screener candidate set plus the user's enter/wait/pass
                     decisions in a write-once local record
  replay           - draw a seeded, outcome-independent sample of captured cases and
                     write a blind view (no decisions, no later prices)
  reveal           - score the user's blind re-decisions against the recorded rule and
                     the later price path (offline OHLCV JSON)
  reconcile-ledger - repair a missing ledger line for an intact capture file

The output is practice feedback, not a trade recommendation. Standard library only.
All calendar logic uses America/New_York, like the FMP client's ``_et_today``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import random
import re
import secrets
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from build_model_book import (  # noqa: F401  (load_prices_json is patched by tests)
    calculate_window_outcome,
    future_bars_after_setup,
    load_prices_json,
    normalize_symbol,
    write_json_report,
)

SCHEMA_VERSION = "1.0"
SETUP_TYPE = "vcp"
SOURCE_SKILL = "vcp-screener"
DECISIONS = ("enter", "wait", "pass")
MARKET_GATES = ("open", "closed")
DEFAULT_STORE_DIR = "state/decision_replay"
DEFAULT_OUTPUT_DIR = "reports/"
DEFAULT_HORIZON_DAYS = 5
RALLY_THRESHOLD_PCT = 5.0
MAX_REASON_CHARS = 200
AS_OF_TOLERANCE = 0.01
CLOSE_HOUR_ET = 16
QUADRANTS = ("followed_favorable", "followed_adverse", "deviated_favorable", "deviated_adverse")
EXCLUSION_REASONS = ("pending", "unscorable", "as_of_unverified", "captured_after_path_start")
BLIND_HIDDEN_FIELDS = ("entry_ready",)
DISCLAIMER = "Practice feedback, not a trade recommendation."
BLIND_INSTRUCTIONS = (
    "Record enter, wait or pass and a one-line reason for every case before running reveal. "
    "Do not look up charts, news or prices for these symbols first."
)
SESSION_ID_RE = re.compile(r"^replay-[0-9a-f]{12}$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ISO_DATE_FULL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Rule specs are stored in every capture; scoring reads the recorded spec, never this table.
RULES: dict[str, list[dict[str, Any]]] = {
    "vcp-checklist-v1": [
        {"id": "market_gate_open", "field": "market_gate", "op": "eq", "value": "open"},
        {"id": "valid_vcp", "field": "valid_vcp", "op": "is_true", "value": None},
        {
            "id": "execution_state",
            "field": "execution_state",
            "op": "not_in",
            "value": ["Invalid", "Damaged", "Overextended", "Extended", "Early-post-breakout"],
        },
        {
            "id": "pivot_distance",
            "field": "distance_from_pivot_pct",
            "op": "between",
            "value": [-8, 3],
        },
        {"id": "risk", "field": "risk_pct", "op": "gt_lte", "value": [0, 15]},
        {"id": "volume_dry_up", "field": "dry_up_ratio", "op": "lte", "value": 1.0},
    ]
}
DEFAULT_RULE_VERSION = "vcp-checklist-v1"


class ReplayError(ValueError):
    """A user-facing validation or integrity failure (exit code 1)."""


# ---------------------------------------------------------------------------
# Time (America/New_York calendar)
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """Timezone-aware current instant; tests monkeypatch this."""
    return datetime.now(timezone.utc)


def _local_tz():
    """Timezone override for naive report timestamps; None means the system zone.

    Tests monkeypatch this. With None, ``datetime.astimezone()`` applies the system zone's
    offset in force on that date, not today's offset.
    """
    return None


def _et_tz():
    try:
        return ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError as exc:
        raise ReplayError("America/New_York timezone data is missing; pip install tzdata") from exc


def _et_date(moment: datetime) -> date:
    if moment.tzinfo is None:
        raise ReplayError("internal error: naive datetime reached the ET calendar")
    return moment.astimezone(_et_tz()).date()


def _next_weekday(day: date) -> date:
    nxt = day + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def check_capture_lag(decision_date: date, captured_at: datetime) -> None:
    """Capture must happen on/after the decision date and before the next weekday (ET)."""
    captured = _et_date(captured_at)
    if captured < decision_date:
        raise ReplayError(f"capture date {captured} is before the decision date {decision_date}")
    if captured >= _next_weekday(decision_date):
        raise ReplayError(
            f"capture date {captured} is too long after the decision date {decision_date}; "
            "decisions must be captured before the next trading day starts "
            "(process guard against hindsight, not a cryptographic proof)"
        )


def _parse_iso_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReplayError(f"{label} must be YYYY-MM-DD, got {value!r}") from exc


def _parse_generated_at(value: Any) -> datetime:
    text = str(value).strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ReplayError(f"metadata.generated_at is not a timestamp: {text!r}") from exc
    if parsed.tzinfo is None:
        tz = _local_tz()
        parsed = parsed.replace(tzinfo=tz) if tz is not None else parsed.astimezone()
    return parsed


# ---------------------------------------------------------------------------
# Hashing and write-once storage
# ---------------------------------------------------------------------------


def _canon(obj: Any) -> str:
    try:
        return json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except ValueError as exc:
        raise ReplayError(f"non-finite number (NaN/Inf) cannot be recorded: {exc}") from exc


def _sha(obj: Any) -> str:
    try:
        return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()
    except UnicodeEncodeError as exc:
        raise ReplayError(
            f"text that is not valid Unicode cannot be recorded: {exc.reason}"
        ) from exc


def capture_hash(record: dict[str, Any]) -> str:
    return _sha({k: v for k, v in record.items() if k != "capture_sha256"})


def population_hash(ids: list[str]) -> str:
    return _sha(sorted(ids))


def _write_once(path: Path | str, payload: Any) -> None:
    """Atomically create ``path``; never overwrite an existing file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = (
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n"
        )
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ReplayError(
            f"text that is not valid Unicode cannot be recorded: {exc.reason}"
        ) from exc
    except ValueError as exc:
        raise ReplayError(f"non-finite number (NaN/Inf) cannot be recorded: {exc}") from exc
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError as exc:
            raise ReplayError(f"{path.name} already exists; records are immutable") from exc
        except OSError:
            # Filesystems without hard links: exclusive create is still never-overwrite.
            try:
                with open(path, "x", encoding="utf-8") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError as exc:
                raise ReplayError(f"{path.name} already exists; records are immutable") from exc
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _read_json(path: Path, label: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise ReplayError(f"cannot read {label} {path}: {exc.strerror or exc}") from exc
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        raise ReplayError(f"{label} {path} is not valid UTF-8 JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# Rule interpreter
# ---------------------------------------------------------------------------


def get_rule(version: str) -> list[dict[str, Any]]:
    if version not in RULES:
        raise ReplayError(f"unknown rule version {version!r}; known: {', '.join(sorted(RULES))}")
    return copy.deepcopy(RULES[version])


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _eval_item(item: dict[str, Any], values: dict[str, Any]) -> str:
    op = item.get("op")
    target = item.get("value")
    value = values.get(item.get("field"))
    if op not in ("eq", "in", "not_in", "between", "gt_lte", "lte", "is_true"):
        raise ReplayError(f"unsupported rule operator {op!r}")
    if value is None:
        return "missing"
    if op == "eq":
        ok = value == target
    elif op == "in":
        ok = value in target
    elif op == "not_in":
        ok = value not in target
    elif op == "is_true":
        ok = value is True
    else:
        number = _num(value)
        if number is None:
            return "fail"
        if op == "between":
            ok = target[0] <= number <= target[1]
        elif op == "gt_lte":
            ok = target[0] < number <= target[1]
        else:
            ok = number <= target
    return "pass" if ok else "fail"


def evaluate_rule(
    items: list[dict[str, Any]], snapshot: dict[str, Any], market_gate: str
) -> dict[str, Any]:
    values = {**snapshot, "market_gate": market_gate}
    results = [{"id": item["id"], "status": _eval_item(item, values)} for item in items]
    expected = "enter" if all(r["status"] == "pass" for r in results) else "not_enter"
    return {"expected": expected, "items": results}


def adherence(decision: str, expected: str) -> str:
    if decision == "enter" and expected == "enter":
        return "followed"
    if decision in ("wait", "pass") and expected == "not_enter":
        return "followed"
    return "deviated"


def decision_outcome(decision: str, path_class: str | None) -> str | None:
    if path_class is None:
        return None
    rallied = path_class == "rallied"
    if decision == "enter":
        return "favorable" if rallied else "adverse"
    return "adverse" if rallied else "favorable"


def classify_quadrant(adherence_value: str, outcome: str | None) -> str | None:
    if outcome is None:
        return None
    return f"{adherence_value}_{outcome}"


# ---------------------------------------------------------------------------
# Snapshot and date guard
# ---------------------------------------------------------------------------


def vcp_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    """Whitelisted, structured point-in-time fields; screener free text is excluded."""
    pattern = result.get("vcp_pattern") or {}
    proximity = result.get("pivot_proximity") or {}
    volume = result.get("volume_pattern") or {}
    strength = result.get("relative_strength") or {}
    trend = result.get("trend_template") or {}
    pivot = proximity.get("pivot_price")
    if pivot is None:
        pivot = pattern.get("pivot_price")
    contractions = []
    for item in pattern.get("contractions") or []:
        if isinstance(item, dict):
            contractions.append(
                {
                    key: item.get(key)
                    for key in (
                        "label",
                        "high_date",
                        "high_price",
                        "low_date",
                        "low_price",
                        "depth_pct",
                    )
                }
            )
    return {
        "symbol": normalize_symbol(result.get("symbol")),
        "sector": result.get("sector"),
        "price": result.get("price"),
        "composite_score": result.get("composite_score"),
        "rating": result.get("rating"),
        "quality_rating": result.get("quality_rating"),
        "valid_vcp": result.get("valid_vcp"),
        "execution_state": result.get("execution_state"),
        "pattern_type": result.get("pattern_type"),
        "wide_and_loose": result.get("wide_and_loose"),
        "distance_from_pivot_pct": result.get("distance_from_pivot_pct"),
        "sma200_distance_pct": result.get("sma200_distance_pct"),
        "entry_ready": result.get("entry_ready"),
        "pivot_price": pivot,
        "num_contractions": pattern.get("num_contractions"),
        "contractions": contractions,
        "stop_loss_price": proximity.get("stop_loss_price"),
        "risk_pct": proximity.get("risk_pct"),
        "dry_up_ratio": volume.get("dry_up_ratio"),
        "rs_rank_estimate": strength.get("rs_rank_estimate"),
        "trend_template_score": trend.get("score"),
    }


def _iter_strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_strings(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _iter_strings(value)


def assert_no_future_dates(obj: Any, decision_date: str) -> None:
    """Fail when any ISO-date string in ``obj`` is later than ``decision_date``."""
    limit = _parse_iso_date(decision_date, "decision_date")
    for text in _iter_strings(obj):
        for token in DATE_RE.findall(text):
            try:
                found = date.fromisoformat(token)
            except ValueError:
                continue
            if found > limit:
                raise ReplayError(
                    f"data dated {found} is later than the decision date {limit}; "
                    "check --decision-date or the report"
                )


# ---------------------------------------------------------------------------
# Decision / answer validation
# ---------------------------------------------------------------------------


def _validate_reason(reason: Any, label: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise ReplayError(f"{label}: reason must be a non-empty string")
    reason = reason.strip()
    if "\n" in reason or "\r" in reason:
        raise ReplayError(f"{label}: reason must be a single line")
    if len(reason) > MAX_REASON_CHARS:
        raise ReplayError(f"{label}: reason is longer than {MAX_REASON_CHARS} characters")
    return reason


def validate_decision_rows(
    rows: Any, id_key: str, expected_ids: list[str], normalize=None
) -> dict[str, dict[str, str]]:
    """Require exactly one valid row per expected id."""
    if not isinstance(rows, list):
        raise ReplayError(f"expected a JSON list of {{{id_key}, decision, reason}} objects")
    parsed: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get(id_key), str):
            raise ReplayError(f"row {index}: expected an object with a string {id_key!r}")
        key = normalize(row[id_key]) if normalize else row[id_key]
        if key not in expected_ids:
            raise ReplayError(f"row {index}: unknown {id_key} {row[id_key]!r}")
        if key in parsed:
            raise ReplayError(f"row {index}: duplicate {id_key} {key!r}")
        decision = row.get("decision")
        if decision not in DECISIONS:
            raise ReplayError(f"{key}: decision must be one of {', '.join(DECISIONS)}")
        parsed[key] = {"decision": decision, "reason": _validate_reason(row.get("reason"), key)}
    missing = [i for i in expected_ids if i not in parsed]
    if missing:
        raise ReplayError(f"missing decisions for every case: {', '.join(missing)}")
    return parsed


# ---------------------------------------------------------------------------
# Store access
# ---------------------------------------------------------------------------


def _captures_dir(store: Path | str) -> Path:
    return Path(store) / "captures"


def _sessions_dir(store: Path | str) -> Path:
    return Path(store) / "sessions"


def _ledger_path(store: Path | str) -> Path:
    return _captures_dir(store) / "ledger.jsonl"


def _scan_ledger(store: Path | str) -> tuple[list[dict[str, Any]], list[int]]:
    """Return (valid entries, 1-based numbers of unparsable lines)."""
    path = _ledger_path(store)
    if not path.exists():
        return [], []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ReplayError(f"cannot read ledger {path}: {exc}") from exc
    entries: list[dict[str, Any]] = []
    bad: list[int] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            bad.append(number)
            continue
        if not isinstance(entry, dict):
            bad.append(number)
            continue
        entries.append(entry)
    return entries, bad


def _read_ledger(store: Path | str) -> list[dict[str, Any]]:
    entries, bad = _scan_ledger(store)
    if bad:
        raise ReplayError(
            f"ledger line {bad[0]} is not valid JSON (damaged or truncated); "
            "run 'decision_replay.py reconcile-ledger' to repair a truncated final line"
        )
    return entries


def _append_ledger(store: Path | str, record: dict[str, Any]) -> None:
    path = _ledger_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "capture_id": record["capture_id"],
        "capture_sha256": record["capture_sha256"],
        "captured_at": record["captured_at"],
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def persist_capture(record: dict[str, Any], store: Path | str) -> Path:
    """Write the capture file once, verify it from disk, then append the ledger line."""
    path = _captures_dir(store) / f"{record['capture_id']}.json"
    _write_once(path, record)
    written = _read_json(path, "capture")
    if capture_hash(written) != record["capture_sha256"]:
        raise ReplayError(f"capture {record['capture_id']} failed integrity check after writing")
    _append_ledger(store, written)
    return path


def load_capture(path: Path | str) -> dict[str, Any]:
    record = _read_json(Path(path), "capture")
    name = Path(path).stem
    try:
        for case in record["cases"]:
            if _sha(case["snapshot"]) != case["snapshot_sha256"]:
                raise ReplayError(f"capture {name} failed integrity check")
        if capture_hash(record) != record["capture_sha256"]:
            raise ReplayError(f"capture {name} failed integrity check")
    except (KeyError, TypeError) as exc:
        raise ReplayError(f"capture {name} failed integrity check (malformed record)") from exc
    return record


def verify_store(store: Path | str) -> list[dict[str, Any]]:
    """Load every capture, cross-checking the append-only ledger. Never mutates anything."""
    cap_dir = _captures_dir(store)
    files = sorted(cap_dir.glob("*.json")) if cap_dir.exists() else []
    captures = {p.stem: load_capture(p) for p in files}
    ledger = _read_ledger(store)
    listed = {}
    for entry in ledger:
        cid = entry.get("capture_id")
        listed[cid] = entry
        if cid not in captures:
            raise ReplayError(
                f"ledger lists capture {cid} but its file is missing; the capture store was altered"
            )
        if entry.get("capture_sha256") != captures[cid]["capture_sha256"]:
            raise ReplayError(f"capture {cid} failed integrity check (ledger hash mismatch)")
    for cid in captures:
        if cid not in listed:
            raise ReplayError(
                f"capture {cid} is not in the ledger; run 'decision_replay.py reconcile-ledger' "
                "if you created it with this tool"
            )
    return [captures[cid] for cid in sorted(captures)]


def _session_ids(store: Path | str) -> list[str]:
    directory = _sessions_dir(store)
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("replay-*.json") if SESSION_ID_RE.match(p.stem))


def _session_path(store, sid, suffix=""):
    return _sessions_dir(store) / f"{sid}{suffix}.json"


def _answered_case_ids(store: Path | str) -> set[str]:
    seen: set[str] = set()
    for sid in _session_ids(store):
        path = _session_path(store, sid, ".answers")
        if path.exists():
            seen.update(row["case_id"] for row in _read_json(path, "answers").get("answers", []))
    return seen


def load_population(
    store: Path | str, include_seen: bool = False, decided_on_or_before: str | None = None
) -> list[dict[str, Any]]:
    """Every captured case (date-only filter and seen-before exclusion; never outcomes)."""
    limit = (
        _parse_iso_date(decided_on_or_before, "--decided-on-or-before")
        if decided_on_or_before
        else None
    )
    seen = _answered_case_ids(store)
    population = []
    for capture in verify_store(store):
        if limit and date.fromisoformat(capture["decision_date"]) > limit:
            continue
        for case in capture["cases"]:
            seen_before = case["case_id"] in seen
            if seen_before and not include_seen:
                continue
            population.append(
                {
                    "case_id": case["case_id"],
                    "symbol": case["symbol"],
                    "setup_type": capture["setup_type"],
                    "decision_date": capture["decision_date"],
                    "market_gate": capture["market_gate"],
                    "snapshot": case["snapshot"],
                    "capture_id": capture["capture_id"],
                    "seen_before": seen_before,
                }
            )
    return sorted(population, key=lambda c: c["case_id"])


def select_cases(population_ids: list[str], sample_size: int, seed: int) -> list[str]:
    """Seeded sample of ids. Takes no price or outcome input by construction."""
    ids = sorted(population_ids)
    return random.Random(seed).sample(ids, min(sample_size, len(ids)))


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------


def _load_screener_report(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReplayError(f"cannot read screener report {path}: {exc.strerror or exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayError(f"screener report {path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ReplayError(
            f"{path} is not a vcp-screener report: expected a top-level 'results' list"
        )
    return payload, hashlib.sha256(raw).hexdigest()


def _resolve_decision_date(
    report: dict[str, Any], override: str | None
) -> tuple[date, datetime | None]:
    metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    generated = None
    if metadata.get("generated_at"):
        generated = _parse_generated_at(metadata["generated_at"]).astimezone(_et_tz())
    if override:
        chosen = _parse_iso_date(override, "--decision-date")
        if generated is not None:
            high = generated.date()
            if not high - timedelta(days=1) <= chosen <= high:
                raise ReplayError(
                    f"--decision-date {chosen} is outside the report's date {high} "
                    "(one day of slack allowed)"
                )
        return chosen, generated
    if generated is None:
        raise ReplayError("report has no metadata.generated_at; pass --decision-date YYYY-MM-DD")
    return generated.date(), generated


def _assert_report_not_captured(store: Path | str, source_sha: str) -> None:
    """One capture per screener report, whatever decision date was chosen."""
    cap_dir = _captures_dir(store)
    for path in sorted(cap_dir.glob("*.json")) if cap_dir.exists() else []:
        existing = _read_json(path, "capture")
        if isinstance(existing, dict) and existing.get("source_report_sha256") == source_sha:
            raise ReplayError(
                f"capture {path.stem} already exists for this report; records are immutable"
            )


def command_capture(args: argparse.Namespace) -> int:
    report, source_sha = _load_screener_report(Path(args.screener_json))
    results = report["results"]
    for position, row in enumerate(results, 1):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("symbol"), str)
            or not row["symbol"].strip()
        ):
            raise ReplayError(
                f"results row {position} has no symbol; the candidate set cannot be frozen"
            )
    if args.limit is not None:
        if args.limit < 1:
            raise ReplayError("--limit must be at least 1")
        results = results[: args.limit]
    if not results:
        raise ReplayError("the report has no candidates to capture")
    if args.horizon_days < 1:
        raise ReplayError("--horizon-days must be at least 1")
    symbols = [normalize_symbol(r["symbol"]) for r in results]
    if len(set(symbols)) != len(symbols):
        raise ReplayError("the candidate set contains a duplicate symbol")

    rows = _read_json(Path(args.decisions), "decisions")
    decisions = validate_decision_rows(rows, "symbol", symbols, normalize=normalize_symbol)

    decision_date, generated_et = _resolve_decision_date(report, args.decision_date)
    now = _now()
    check_capture_lag(decision_date, now)
    _assert_report_not_captured(args.store_dir, source_sha)
    warn_early = (
        generated_et is not None
        and generated_et.date() == decision_date
        and generated_et.time() < time(CLOSE_HOUR_ET, 0)
    )

    rule_items = get_rule(DEFAULT_RULE_VERSION)
    capture_id = f"vcp-{decision_date.isoformat()}-{source_sha[:12]}"
    cases = []
    for rank, (result, symbol) in enumerate(zip(results, symbols), 1):
        snapshot = vcp_snapshot(result)
        assert_no_future_dates(snapshot, decision_date.isoformat())
        structural = evaluate_rule(rule_items, snapshot, "open")["expected"] == "enter"
        screener_ready = snapshot.get("entry_ready")
        if snapshot.get("execution_state") is None:
            mismatch: bool | None = True
        elif screener_ready is None:
            mismatch = None  # unknown: older reports carry no entry_ready
        else:
            mismatch = bool(screener_ready) != structural
        cases.append(
            {
                "case_id": f"{capture_id}:{symbol}",
                "rank": rank,
                "symbol": symbol,
                "snapshot": snapshot,
                "snapshot_sha256": _sha(snapshot),
                "decision": decisions[symbol]["decision"],
                "reason": decisions[symbol]["reason"],
                "screener_entry_ready": screener_ready,
                "v1_structural_pass": structural,
                "rule_mismatch": mismatch,
            }
        )
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "decision_capture",
        "capture_id": capture_id,
        "setup_type": SETUP_TYPE,
        "source_skill": SOURCE_SKILL,
        "source_report": Path(args.screener_json).name,
        "source_report_sha256": source_sha,
        "decision_date": decision_date.isoformat(),
        "captured_at": now.isoformat(timespec="seconds"),
        "market_gate": args.market_gate,
        "evaluation": {
            "horizon_days": args.horizon_days,
            "rally_threshold_pct": RALLY_THRESHOLD_PCT,
            "reference": "snapshot.price",
            "stop": "snapshot.stop_loss_price",
        },
        "rule": {"version": DEFAULT_RULE_VERSION, "items": rule_items},
        "cases": cases,
    }
    record["capture_sha256"] = capture_hash(record)
    path = persist_capture(record, args.store_dir)
    if warn_early:
        print(
            "WARNING: report generated before the close; v1 supports after-close screening",
            file=sys.stderr,
        )
    print(f"Captured {len(cases)} cases as {capture_id}")
    print(f"capture_file: {path}")
    return 0


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def render_blind_markdown(view: dict[str, Any]) -> str:
    lines = [
        "# Blind Replay: Your Own VCP Decisions",
        "",
        f"Session: {view['session_id']}",
        f"Cases: {view['case_count']}",
        "",
        view["instructions"],
        "",
    ]
    for case in view["cases"]:
        snap = case["snapshot"]
        lines += [
            f"## Case {case['case_number']}: {case['symbol']}",
            "",
            f"- case_id: {case['case_id']}",
            f"- setup_type: {case['setup_type']}",
            f"- decision_date: {case['decision_date']}",
            f"- market_gate: {case['market_gate']}",
        ]
        for key in sorted(snap):
            if key not in ("contractions", "symbol"):
                lines.append(f"- {key}: {snap[key]}")
        for item in snap.get("contractions") or []:
            lines.append(
                f"- contraction {item.get('label')}: high {item.get('high_price')} "
                f"({item.get('high_date')}), low {item.get('low_price')} "
                f"({item.get('low_date')}), depth {item.get('depth_pct')}%"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _pending_sessions(store: Path | str) -> list[str]:
    pending = []
    for sid in _session_ids(store):
        if (
            not _session_path(store, sid, ".answers").exists()
            and not _session_path(store, sid, ".abandoned").exists()
        ):
            pending.append(sid)
    return pending


def command_abandon(args: argparse.Namespace) -> int:
    sid = args.abandon
    if not args.reason or not args.reason.strip():
        raise ReplayError("--abandon requires --reason")
    reason = _validate_reason(args.reason, "--reason")
    if not SESSION_ID_RE.match(sid) or not _session_path(args.store_dir, sid).exists():
        raise ReplayError(f"unknown session {sid}")
    if _session_path(args.store_dir, sid, ".answers").exists():
        raise ReplayError(f"session {sid} already has recorded answers; it cannot be abandoned")
    _write_once(
        _session_path(args.store_dir, sid, ".abandoned"),
        {
            "schema_version": SCHEMA_VERSION,
            "record_type": "replay_abandoned",
            "session_id": sid,
            "reason": reason,
            "abandoned_at": _now().isoformat(timespec="seconds"),
        },
    )
    print(f"Abandoned session {sid}")
    return 0


def command_replay(args: argparse.Namespace) -> int:
    if args.abandon:
        return command_abandon(args)
    store = args.store_dir
    verify_store(store)
    pending = _pending_sessions(store)
    if pending:
        raise ReplayError(
            f"session {pending[0]} is pending: run reveal for it or replay --abandon {pending[0]} "
            "--reason TEXT before starting a new replay"
        )
    population = load_population(store, args.include_seen, args.decided_on_or_before)
    if not population:
        print("No captured cases available for replay.")
        return 0
    by_id = {c["case_id"]: c for c in population}
    ids = sorted(by_id)
    seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
    selected = select_cases(ids, args.sample_size, seed)
    pop_hash = population_hash(ids)
    sid = (
        "replay-"
        + hashlib.sha256(f"{seed}:{pop_hash}:{args.sample_size}".encode()).hexdigest()[:12]
    )
    sess_rec = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "replay_session",
        "session_id": sid,
        "session_index": len(_session_ids(store)) + 1,
        "seed": seed,
        "sample_size": args.sample_size,
        "population_size": len(ids),
        "population_sha256": pop_hash,
        "filter": {"decided_on_or_before": args.decided_on_or_before},
        "include_seen": bool(args.include_seen),
        "selected_case_ids": selected,
        "seen_before_case_ids": [i for i in selected if by_id[i]["seen_before"]],
        "created_at": _now().isoformat(timespec="seconds"),
    }
    if _session_path(store, sid).exists():
        raise ReplayError(f"{sid}.json already exists; records are immutable")

    view_cases = []
    for number, case_id in enumerate(selected, 1):
        case = by_id[case_id]
        view_case = {
            "case_number": number,
            "case_id": case_id,
            "symbol": case["symbol"],
            "setup_type": case["setup_type"],
            "decision_date": case["decision_date"],
            "market_gate": case["market_gate"],
            # entry_ready is the screener's verdict on nearly the same checklist as rule v1,
            # so it stays in the capture but is not shown while answering.
            "snapshot": {k: v for k, v in case["snapshot"].items() if k not in BLIND_HIDDEN_FIELDS},
        }
        assert_no_future_dates(view_case, case["decision_date"])
        view_cases.append(view_case)
    view = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "replay_blind_view",
        "session_id": sid,
        "case_count": len(view_cases),
        "instructions": BLIND_INSTRUCTIONS,
        "cases": view_cases,
    }
    out_dir = Path(args.output_dir)
    json_path = out_dir / f"stockbee_setup_fluency_replay_blind_{sid}.json"
    md_path = out_dir / f"stockbee_setup_fluency_replay_blind_{sid}.md"
    try:
        json_text = json.dumps(view, indent=2, ensure_ascii=False) + "\n"
        md_text = render_blind_markdown(view)
        json_text.encode("utf-8")
        md_text.encode("utf-8")
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json_text, encoding="utf-8")
        md_path.write_text(md_text, encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise ReplayError(f"cannot write the blind view under {out_dir}: {exc}") from exc
    # The session record is written last, so a failed output never leaves a pending session.
    try:
        _write_once(_session_path(store, sid), sess_rec)
    except OSError:
        # No blind view may exist without a session record: it would bypass seen/abandon accounting.
        for leftover in (json_path, md_path):
            leftover.unlink(missing_ok=True)
        raise
    print(f"session_id: {sid}")
    print(f"cases: {len(view_cases)}")
    print(f"blind_view_json: {json_path}")
    print(f"blind_view_md: {md_path}")
    return 0


# ---------------------------------------------------------------------------
# reveal
# ---------------------------------------------------------------------------


def _bar_date(bar) -> date:
    return date.fromisoformat(bar.date)


def _case_exclusion(
    snapshot: dict[str, Any], decision_date: str, captured_date: date, bars, future, horizon: int
) -> str | None:
    if not future:
        return "pending"
    entry = snapshot.get("price")
    if _num(entry) is None or entry <= 0:
        return "unscorable"
    limit = date.fromisoformat(decision_date)
    before = [b for b in bars if _bar_date(b) <= limit]
    if not before or abs(before[-1].close / entry - 1.0) > AS_OF_TOLERANCE:
        return "as_of_unverified"
    if captured_date >= _bar_date(future[0]):
        return "captured_after_path_start"
    if len(future) < horizon:
        return "pending"
    return None


def _side(decision_row: dict[str, str], expected: str, path_class: str | None) -> dict[str, Any]:
    adherent = adherence(decision_row["decision"], expected)
    outcome = decision_outcome(decision_row["decision"], path_class)
    return {
        "decision": decision_row["decision"],
        "reason": decision_row["reason"],
        "adherence": adherent,
        "outcome": outcome,
        "quadrant": classify_quadrant(adherent, outcome),
    }


def score_case(
    capture: dict[str, Any],
    case: dict[str, Any],
    bars,
    replay_row: dict[str, str],
    seen_before: bool,
) -> dict[str, Any]:
    snapshot = case["snapshot"]
    evaluation = capture["evaluation"]
    horizon = int(evaluation["horizon_days"])
    threshold = float(evaluation["rally_threshold_pct"])
    decision_date = capture["decision_date"]
    rule = evaluate_rule(capture["rule"]["items"], snapshot, capture["market_gate"])
    future = future_bars_after_setup(bars, decision_date)
    captured_date = _et_date(datetime.fromisoformat(capture["captured_at"]))
    exclusion = _case_exclusion(snapshot, decision_date, captured_date, bars, future, horizon)

    stop = _num(snapshot.get("stop_loss_price"))
    path: dict[str, Any] = {
        "closes": [{"date": b.date, "close": round(b.close, 4)} for b in future[:horizon]]
    }
    path_class = None
    if exclusion is None:
        window = calculate_window_outcome(
            {
                "entry_reference": snapshot["price"],
                "stop_reference": stop if stop and stop > 0 else 0,
                "setup_date": decision_date,
            },
            bars,
            horizon,
        )
        for key in ("forward_return_pct", "mfe_pct", "mae_pct", "stop_hit", "stop_hit_date"):
            path[key] = window.get(key)
        rallied = (not window["stop_hit"]) and window["forward_return_pct"] >= threshold
        path_class = "rallied" if rallied else "did_not_rally"
    return {
        "case_id": case["case_id"],
        "symbol": case["symbol"],
        "decision_date": decision_date,
        "market_gate": capture["market_gate"],
        "rule_version": capture["rule"]["version"],
        "rule_items": rule["items"],
        "rule_expected": rule["expected"],
        "rule_mismatch": case.get("rule_mismatch"),
        "seen_before": seen_before,
        "stop_reference_missing": not (stop and stop > 0),
        "exclusion_reason": exclusion,
        "path_class": path_class,
        "path": path,
        "original": _side(
            {"decision": case["decision"], "reason": case["reason"]}, rule["expected"], path_class
        ),
        "replay": _side(replay_row, rule["expected"], path_class),
    }


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole * 100.0, 1) if whole else None


def summarize(
    cases: list[dict[str, Any]], sess_rec: dict[str, Any], store: Path | str
) -> dict[str, Any]:
    scored = [c for c in cases if c["exclusion_reason"] is None]
    replay_scored = [c for c in scored if not c["seen_before"]]
    answered = [c for c in cases if not c["seen_before"]]

    def quadrants(items, side):
        counts = {q: 0 for q in QUADRANTS}
        for c in items:
            counts[c[side]["quadrant"]] += 1
        return counts

    excluded = {r: sum(1 for c in cases if c["exclusion_reason"] == r) for r in EXCLUSION_REASONS}
    index = sess_rec.get("session_index", 0)
    prior = 0
    abandoned_total = 0
    abandoned_before = 0
    for sid in _session_ids(store):
        other = _read_json(_session_path(store, sid), "session")
        if other.get("session_index", 0) < index and sid != sess_rec["session_id"]:
            prior += 1
        if _session_path(store, sid, ".abandoned").exists():
            abandoned_total += 1
            if other.get("session_index", 0) < index:
                abandoned_before += 1
    return {
        "case_count": len(cases),
        "scored_count": len(scored),
        "pending": excluded["pending"],
        "excluded": excluded,
        "original": {
            "quadrants": quadrants(scored, "original"),
            "adherence_rate_pct": _rate(
                sum(1 for c in scored if c["original"]["adherence"] == "followed"), len(scored)
            ),
        },
        "replay": {
            "quadrants": quadrants(replay_scored, "replay"),
            "adherence_rate_pct": _rate(
                sum(1 for c in replay_scored if c["replay"]["adherence"] == "followed"),
                len(replay_scored),
            ),
        },
        "consistency_rate_pct": _rate(
            sum(1 for c in answered if c["replay"]["decision"] == c["original"]["decision"]),
            len(answered),
        ),
        "population_size": sess_rec.get("population_size"),
        "prior_sessions": prior,
        "abandoned_sessions": abandoned_total,
        "abandoned_before_this_session": abandoned_before,
    }


def render_reveal_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Blind Replay Reveal",
        "",
        f"> {payload['disclaimer']}",
        "",
        f"Session: {payload['session_id']}  ",
        f"Prices JSON sha256: {payload['prices_json_sha256']}  ",
        f"Prices changed since previous reveal: {payload['prices_changed_since_previous_reveal']}",
        "",
        "## Summary",
        "",
        f"- Cases: {summary['case_count']} (scored {summary['scored_count']}, pending {summary['pending']})",
        f"- Excluded: {json.dumps(summary['excluded'])}",
        f"- Original adherence: {summary['original']['adherence_rate_pct']}%",
        f"- Replay adherence: {summary['replay']['adherence_rate_pct']}%",
        f"- Consistency (replay equals original): {summary['consistency_rate_pct']}%",
        f"- Population {summary['population_size']}, prior sessions {summary['prior_sessions']}, "
        f"abandoned {summary['abandoned_sessions']}",
        "",
        "| Quadrant | Original | Replay |",
        "|---|---|---|",
    ]
    for q in QUADRANTS:
        lines.append(
            f"| {q} | {summary['original']['quadrants'][q]} | {summary['replay']['quadrants'][q]} |"
        )
    lines += ["", "## Cases", ""]
    for c in payload["cases"]:
        path = c["path"]
        lines += [
            f"### {c['symbol']} ({c['decision_date']}, gate {c['market_gate']})",
            "",
            f"- Original: {c['original']['decision']} - {c['original']['reason']} "
            f"[{c['original']['adherence']}, {c['original']['quadrant']}]",
            f"- Replay: {c['replay']['decision']} - {c['replay']['reason']} "
            f"[{c['replay']['adherence']}, {c['replay']['quadrant']}]",
            f"- Rule {c['rule_version']}: expected {c['rule_expected']}; "
            + ", ".join(f"{i['id']}={i['status']}" for i in c["rule_items"]),
            f"- Later path: {path.get('closes')}",
            f"- Forward return {path.get('forward_return_pct')}%, MFE {path.get('mfe_pct')}%, "
            f"MAE {path.get('mae_pct')}%, stop hit {path.get('stop_hit')}",
            f"- Path class: {c['path_class']}; exclusion: {c['exclusion_reason']}; "
            f"rule mismatch vs screener entry_ready: {c['rule_mismatch']}",
            "",
        ]
    lines += [payload["disclaimer"], ""]
    return "\n".join(lines)


def command_reveal(args: argparse.Namespace) -> int:
    store = args.store_dir
    sid = args.session_id
    if not SESSION_ID_RE.match(sid) or not _session_path(store, sid).exists():
        raise ReplayError(f"unknown session {sid}")
    sess_rec = _read_json(_session_path(store, sid), "session")
    if _session_path(store, sid, ".abandoned").exists():
        raise ReplayError(f"session {sid} was abandoned; it cannot be revealed")

    captures = verify_store(store)
    index = {c["case_id"]: (cap, c) for cap in captures for c in cap["cases"]}
    selected = sess_rec["selected_case_ids"]
    for case_id in selected:
        if case_id not in index:
            raise ReplayError(f"session case {case_id} is not in the capture store")

    rows = _read_json(Path(args.answers), "answers")
    answers = validate_decision_rows(rows, "case_id", selected)
    answers_sorted = [{"case_id": k, **answers[k]} for k in sorted(answers)]
    answers_sha = _sha(answers_sorted)

    out_dir = Path(args.output_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReplayError(f"cannot use output directory {out_dir}: {exc.strerror or exc}") from exc

    prices_path = Path(args.prices_json)
    prices_sha, prices = _load_prices_checked(prices_path)
    if not any(index[case_id][1]["symbol"] in prices for case_id in selected):
        raise ReplayError(
            f"prices JSON {prices_path} contains none of this session's symbols; "
            "nothing was recorded"
        )

    uncovered = sum(1 for case_id in selected if index[case_id][1]["symbol"] not in prices)
    if uncovered:
        print(
            f"WARNING: prices JSON has no bars for {uncovered} of {len(selected)} cases; "
            "they stay pending",
            file=sys.stderr,
        )

    answers_path = _session_path(store, sid, ".answers")
    answers_recorded = answers_path.exists()
    if answers_recorded:
        stored = _read_json(answers_path, "answers")
        if not isinstance(stored, dict) or stored.get("answers_sha256") != answers_sha:
            raise ReplayError(
                f"answers already recorded for session {sid}; reveal again with the identical answers"
            )

    history_path = _session_path(store, sid, ".reveals").with_suffix(".jsonl")
    previous = None
    if history_path.exists():
        lines = [x for x in history_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        if lines:
            try:
                previous = json.loads(lines[-1]).get("prices_json_sha256")
            except (json.JSONDecodeError, AttributeError) as exc:
                raise ReplayError(f"reveal history {history_path.name} is damaged") from exc

    # Score everything first; nothing is written until scoring has fully succeeded.
    seen_ids = set(sess_rec.get("seen_before_case_ids", []))
    scored_cases = []
    for case_id in selected:
        capture, case = index[case_id]
        scored_cases.append(
            score_case(
                capture, case, prices.get(case["symbol"], []), answers[case_id], case_id in seen_ids
            )
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "replay_reveal",
        "session_id": sid,
        "generated_at": _now().isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "prices_json_sha256": prices_sha,
        "prices_changed_since_previous_reveal": previous is not None and previous != prices_sha,
        "summary": summarize(scored_cases, sess_rec, store),
        "cases": scored_cases,
    }
    md_text = render_reveal_markdown(payload)

    if not answers_recorded:
        _write_once(
            answers_path,
            {
                "schema_version": SCHEMA_VERSION,
                "record_type": "replay_answers",
                "session_id": sid,
                "answers_sha256": answers_sha,
                "answers": answers_sorted,
                "recorded_at": _now().isoformat(timespec="seconds"),
            },
        )
    try:
        with open(history_path, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "prices_json_sha256": prices_sha,
                        "revealed_at": _now().isoformat(timespec="seconds"),
                    }
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        json_path = write_json_report(payload, out_dir, "stockbee_setup_fluency_replay_reveal")
        md_path = json_path.with_suffix(".md")
        md_path.write_text(md_text, encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise ReplayError(f"cannot write the reveal report under {out_dir}: {exc}") from exc
    print(f"reveal_json: {json_path}")
    print(f"reveal_md: {md_path}")
    print(DISCLAIMER)
    return 0


def _load_prices_checked(path: Path) -> tuple[str, dict[str, list]]:
    """Load offline prices, failing with ReplayError on bad bytes, JSON or bar dates."""
    try:
        raw = path.read_bytes()
        prices = load_prices_json(path)
    except OSError as exc:
        raise ReplayError(f"cannot read prices JSON {path}: {exc.strerror or exc}") from exc
    except (ValueError, TypeError, AttributeError) as exc:
        raise ReplayError(f"prices JSON {path} is not valid UTF-8 JSON price data: {exc}") from exc
    for symbol, bars in prices.items():
        for bar in bars:
            if not ISO_DATE_FULL_RE.match(bar.date):
                raise ReplayError(
                    f"prices JSON {path}: {symbol} has a bar dated {bar.date!r}; "
                    "dates must be YYYY-MM-DD"
                )
            try:
                date.fromisoformat(bar.date)
            except ValueError as exc:
                raise ReplayError(
                    f"prices JSON {path}: {symbol} has invalid date {bar.date!r}"
                ) from exc
    return hashlib.sha256(raw).hexdigest(), prices


# ---------------------------------------------------------------------------
# reconcile-ledger
# ---------------------------------------------------------------------------


def _check_truncated_tail(store: Path | str, bad: list[int]) -> list[str]:
    """Return the ledger lines to keep; refuse unless only the final line is damaged."""
    lines = _ledger_path(store).read_text(encoding="utf-8").splitlines()
    last = max(i for i, line in enumerate(lines, 1) if line.strip())
    if bad != [last]:
        raise ReplayError(
            f"ledger line {bad[0]} is damaged in the middle of the file, not just truncated at "
            "the end; restore captures/ledger.jsonl from a backup"
        )
    for capture_path in sorted(_captures_dir(store).glob("*.json")):
        load_capture(capture_path)  # raises on any integrity failure; nothing is changed yet
    return lines[: last - 1]


def _rewrite_ledger(store: Path | str, kept: list[str]) -> None:
    cap_dir = _captures_dir(store)
    fd, tmp_name = tempfile.mkstemp(dir=str(cap_dir), prefix=".tmp-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("".join(f"{line}\n" for line in kept))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_name, _ledger_path(store))


def command_reconcile(args: argparse.Namespace) -> int:
    store = args.store_dir
    cap_dir = _captures_dir(store)
    entries, bad = _scan_ledger(store)
    kept = _check_truncated_tail(store, bad) if bad else None
    listed = {e.get("capture_id") for e in entries}
    # Verify every capture that would be re-added, including its lag, before any write.
    missing = []
    for path in sorted(cap_dir.glob("*.json")) if cap_dir.exists() else []:
        if path.stem in listed:
            continue
        record = load_capture(path)
        try:
            check_capture_lag(
                date.fromisoformat(record["decision_date"]),
                datetime.fromisoformat(record["captured_at"]),
            )
        except ReplayError as exc:
            raise ReplayError(
                f"cannot reconcile capture {path.stem}: {exc}. The ledger was not changed; "
                "restore captures/ledger.jsonl from a backup"
            ) from exc
        missing.append(record)
    if kept is not None:
        _rewrite_ledger(store, kept)
    for record in missing:
        _append_ledger(store, record)
    suffix = "; dropped one truncated trailing ledger line" if kept is not None else ""
    print(f"Reconciled {len(missing)} capture(s){suffix}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Blind replay of your own VCP decisions: capture, replay, reveal."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Freeze a candidate set and your decisions")
    cap.add_argument("--screener-json", required=True, help="vcp-screener JSON report")
    cap.add_argument("--decisions", required=True, help="JSON list of {symbol, decision, reason}")
    cap.add_argument("--market-gate", required=True, choices=list(MARKET_GATES))
    cap.add_argument("--decision-date", help="YYYY-MM-DD override (default: report date in ET)")
    cap.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    cap.add_argument("--limit", type=int, help="Use only the first N candidates in report order")
    cap.add_argument("--store-dir", default=DEFAULT_STORE_DIR)

    rep = sub.add_parser("replay", help="Draw a blind, seeded sample of captured cases")
    rep.add_argument("--sample-size", type=int)
    rep.add_argument("--seed", type=int)
    rep.add_argument("--decided-on-or-before", help="YYYY-MM-DD; date-only population filter")
    rep.add_argument("--include-seen", action="store_true", help="Re-admit cases already revealed")
    rep.add_argument("--abandon", metavar="SESSION_ID", help="Abandon a pending session")
    rep.add_argument("--reason", help="Reason for --abandon")
    rep.add_argument("--store-dir", default=DEFAULT_STORE_DIR)
    rep.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)

    rev = sub.add_parser(
        "reveal", help="Score your blind answers against the recorded rule and path"
    )
    rev.add_argument("--session-id", required=True)
    rev.add_argument("--answers", required=True, help="JSON list of {case_id, decision, reason}")
    rev.add_argument("--prices-json", required=True, help="Offline OHLCV JSON for the later path")
    rev.add_argument("--store-dir", default=DEFAULT_STORE_DIR)
    rev.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)

    rec = sub.add_parser(
        "reconcile-ledger", help="Append a missing ledger line for an intact capture"
    )
    rec.add_argument("--store-dir", default=DEFAULT_STORE_DIR)
    return parser


COMMANDS = {
    "capture": command_capture,
    "replay": command_replay,
    "reveal": command_reveal,
    "reconcile-ledger": command_reconcile,
}


def _check_replay_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject replay argument combinations that do not make sense (exit 2)."""
    if args.command != "replay":
        return
    if args.abandon:
        clashes = [
            flag
            for flag, given in (
                ("--sample-size", args.sample_size is not None),
                ("--seed", args.seed is not None),
                ("--include-seen", args.include_seen),
                ("--decided-on-or-before", args.decided_on_or_before is not None),
            )
            if given
        ]
        if clashes:
            parser.error(f"--abandon cannot be combined with {', '.join(clashes)}")
        if not args.reason:
            parser.error("--abandon requires --reason")
        return
    if args.reason:
        parser.error("--reason is only valid together with --abandon")
    if args.sample_size is None or args.sample_size < 1:
        parser.error("--sample-size must be a positive integer")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _check_replay_arguments(parser, args)
    try:
        return COMMANDS[args.command](args)
    except ReplayError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: file system problem: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
