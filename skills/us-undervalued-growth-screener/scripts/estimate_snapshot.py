"""Persistent full-universe estimate snapshot (v3.7 sharded collection).

A snapshot freezes the listing universe at creation time and then accumulates
per-symbol estimate rows shard by shard across multiple runs/days, within each
run's API budget. ``screen-full-snapshot`` (a later stage) may only run once
every shard is complete and every frozen symbol is classified — that is what
finally justifies ``ranking_scope: final_marketwide``.

Layout inside ``--snapshot-dir``::

    snapshot-manifest.json   # id, frozen universe hash/count, shard states
    universe.jsonl           # the frozen listing universe (normalized rows)
    shard-<i>.jsonl          # per-symbol records: listing + estimates + class

Design invariants (round-7 review additions to issue #345):

- The universe is FROZEN by ``snapshot_id``; new listings/delistings go to
  the next snapshot, never mixed in.
- Every shard records its own ``as_of``; the spread between the oldest and
  newest shard is bounded by ``max_shard_age_spread_days`` before screening.
- Classification counts must sum exactly to the frozen universe count.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MANIFEST_NAME = "snapshot-manifest.json"
UNIVERSE_NAME = "universe.jsonl"
ENUMERATION_AUDIT_NAME = "listing-enumeration-audit.json"
SNAPSHOT_SCHEMA_VERSION = 2

# Per-symbol classification buckets. Precedence when several apply:
# excluded > unit_mismatch > no_estimates > negative_eps > evaluable.
# unit_mismatch dominates the estimate-derived buckets because a row whose
# listing/statement units cannot be reconciled is unusable even WITH
# estimates (fail closed, round-8 semantics).
CLASSIFICATIONS = ("evaluable", "no_estimates", "negative_eps", "unit_mismatch", "excluded")


def stable_shard(symbol: str, shard_count: int) -> int:
    """Deterministic shard assignment: the same symbol always lands together."""
    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    digest = hashlib.sha256(symbol.strip().upper().encode("utf-8")).hexdigest()
    return int(digest, 16) % shard_count


def _universe_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    hasher = hashlib.sha256()
    for row in rows:
        hasher.update(
            json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        hasher.update(b"\n")
    return hasher.hexdigest()


def create_snapshot(
    snapshot_dir: Path,
    universe_rows: Sequence[Mapping[str, Any]],
    *,
    shard_count: int,
    as_of: datetime,
    enumeration_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze the universe and initialize an empty manifest."""
    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    if not universe_rows:
        raise ValueError("cannot freeze an empty universe")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if (snapshot_dir / MANIFEST_NAME).exists():
        raise ValueError(f"snapshot already exists at {snapshot_dir}")
    ordered = sorted(universe_rows, key=lambda row: str(row.get("symbol") or ""))
    with (snapshot_dir / UNIVERSE_NAME).open("w", encoding="utf-8") as handle:
        for row in ordered:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    sha = _universe_sha256(ordered)
    enumeration_sha256: str | None = None
    if enumeration_audit is not None:
        enumeration_bytes = (
            json.dumps(dict(enumeration_audit), indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        (snapshot_dir / ENUMERATION_AUDIT_NAME).write_bytes(enumeration_bytes)
        enumeration_sha256 = hashlib.sha256(enumeration_bytes).hexdigest()
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": (
            f"snap-{as_of.astimezone(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{sha[:12]}"
        ),
        "created_at": as_of.astimezone(timezone.utc).isoformat(),
        "universe_sha256": sha,
        "universe_count": len(ordered),
        "listing_enumeration_audit_sha256": enumeration_sha256,
        "normalization_policy": "current_only_per_retrieval",
        "shard_count": shard_count,
        "shards": {
            str(index): {"status": "pending", "attempted": 0, "classified": {}}
            for index in range(shard_count)
        },
    }
    write_manifest(snapshot_dir, manifest)
    return manifest


def load_manifest(snapshot_dir: Path) -> dict[str, Any]:
    return json.loads((snapshot_dir / MANIFEST_NAME).read_text(encoding="utf-8"))


def write_manifest(snapshot_dir: Path, manifest: Mapping[str, Any]) -> None:
    path = snapshot_dir / MANIFEST_NAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_universe(snapshot_dir: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in (snapshot_dir / UNIVERSE_NAME).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return rows


def load_verified_universe(snapshot_dir: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Load the frozen universe and verify it against the manifest.

    Refuses — before any API access or shard append — when the manifest
    schema is unknown, the row count differs, symbols are missing/duplicated,
    or the canonical SHA-256 no longer matches: a silently swapped
    ``universe.jsonl`` would otherwise break the freeze guarantee while
    keeping ``classification_matches_universe`` true.
    """
    if int(manifest.get("schema_version") or 0) != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported snapshot manifest schema_version {manifest.get('schema_version')!r}"
        )
    rows = load_universe(snapshot_dir)
    expected_count = int(manifest.get("universe_count") or -1)
    if len(rows) != expected_count:
        raise ValueError(
            f"universe.jsonl has {len(rows)} rows but the manifest froze {expected_count}"
        )
    symbols = [str(row.get("symbol") or "") for row in rows]
    if "" in symbols or len(set(symbols)) != len(symbols):
        raise ValueError("universe.jsonl symbols are missing or not unique")
    sha = _universe_sha256(rows)
    if sha != manifest.get("universe_sha256"):
        raise ValueError(
            "universe.jsonl does not match the frozen universe_sha256 — the snapshot "
            "universe may have been modified; create a new snapshot instead"
        )
    return rows


def load_verified_enumeration(
    snapshot_dir: Path, manifest: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    """Load and semantically verify the listing-enumeration proof bound by the manifest."""
    path = snapshot_dir / ENUMERATION_AUDIT_NAME
    data = path.read_bytes()
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != manifest.get("listing_enumeration_audit_sha256"):
        raise ValueError("listing enumeration audit SHA-256 does not match the manifest")
    audit = json.loads(data)
    if not isinstance(audit, Mapping):
        raise ValueError("listing enumeration audit is not a JSON object")
    audit = dict(audit)
    requested = [str(value).upper() for value in (audit.get("requested_exchanges") or [])]
    retrieved = [str(value).upper() for value in (audit.get("retrieved_exchanges") or [])]
    bands = [dict(row) for row in (audit.get("bands") or []) if isinstance(row, Mapping)]
    band_exchanges = {str(row.get("exchange") or "").upper() for row in bands}
    try:
        minimum = float(audit["requested_min_market_cap"])
        maximum = float(audit["requested_max_market_cap"])
        min_price = float(audit["min_price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("listing enumeration audit lacks an explicit numeric scope") from exc
    bands_well_formed = True
    ranges_by_exchange: dict[str, list[tuple[float, float]]] = {
        exchange: [] for exchange in requested
    }
    for row in bands:
        exchange = str(row.get("exchange") or "").upper()
        try:
            band_minimum = float(row["min_market_cap"])
            band_maximum = float(row["max_market_cap"])
        except (KeyError, TypeError, ValueError):
            bands_well_formed = False
            continue
        if (
            exchange not in ranges_by_exchange
            or band_minimum >= band_maximum
            or row.get("provider_exhausted") is not True
        ):
            bands_well_formed = False
            continue
        ranges_by_exchange[exchange].append((band_minimum, band_maximum))

    def covers_requested_range(ranges: Sequence[tuple[float, float]]) -> bool:
        cursor = minimum
        for band_minimum, band_maximum in sorted(ranges):
            if band_maximum < minimum or band_minimum > maximum:
                continue
            clipped_minimum = max(band_minimum, minimum)
            clipped_maximum = min(band_maximum, maximum)
            if clipped_minimum > cursor:
                return False
            cursor = max(cursor, clipped_maximum)
        return cursor >= maximum

    bands_cover_scope = bands_well_formed and all(
        covers_requested_range(ranges_by_exchange[exchange]) for exchange in requested
    )
    valid = (
        audit.get("method") == "adaptive_market_cap_bands"
        and audit.get("retrieval_scope_explicit") is True
        and audit.get("pagination_exhausted") is True
        and audit.get("enumeration_verified") is True
        and int(audit.get("saturated_leaf_count") or 0) == 0
        and int(audit.get("row_count") or -1) == int(manifest.get("universe_count") or -2)
        and bool(requested)
        and sorted(set(requested)) == sorted(set(retrieved))
        and set(requested).issubset(band_exchanges)
        and bool(bands)
        and bands_cover_scope
        and minimum < maximum
        and min_price >= 0
    )
    if not valid:
        raise ValueError("listing enumeration audit does not prove the complete requested scope")
    return audit, actual_sha


def shard_path(snapshot_dir: Path, shard_index: int) -> Path:
    return snapshot_dir / f"shard-{shard_index}.jsonl"


def load_shard_rows(snapshot_dir: Path, shard_index: int) -> list[dict[str, Any]]:
    path = shard_path(snapshot_dir, shard_index)
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def append_shard_rows(
    snapshot_dir: Path, shard_index: int, rows: Sequence[Mapping[str, Any]]
) -> None:
    with shard_path(snapshot_dir, shard_index).open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def classify_symbol(
    listing: Mapping[str, Any],
    normalized: Mapping[str, Any],
    *,
    requires_unit_reconciliation: Any,
    minimum_plausible_forward_pe: float = 2.0,
) -> str:
    """Classify one frozen-universe symbol after an estimate-acquisition attempt."""
    if listing.get("is_actively_trading") is False or listing.get("is_common_stock") is False:
        return "excluded"
    if requires_unit_reconciliation(listing):
        return "unit_mismatch"
    forward_pe = normalized.get("forward_pe")
    if isinstance(forward_pe, (int, float)) and 0 < forward_pe < minimum_plausible_forward_pe:
        return "unit_mismatch"
    # The normalizer NULLS a non-positive FY1 (reason non_positive_fy1_eps)
    # before it ever reaches fy1_eps, so the raw candidate / reason list is
    # the only way this bucket is reachable from real pipeline output.
    reasons = normalized.get("estimate_normalization_reasons") or []
    raw_candidate = normalized.get("raw_forward_candidate")
    raw_eps = raw_candidate.get("eps") if isinstance(raw_candidate, Mapping) else None
    if "non_positive_fy1_eps" in reasons or (isinstance(raw_eps, (int, float)) and raw_eps <= 0):
        return "negative_eps"
    periods = normalized.get("estimate_periods")
    if not periods:
        return "no_estimates"
    fy1 = normalized.get("fy1_eps")
    if isinstance(fy1, (int, float)) and fy1 <= 0:
        return "negative_eps"
    if fy1 is None:
        return "no_estimates"
    return "evaluable"


def update_shard(
    snapshot_dir: Path,
    manifest: dict[str, Any],
    shard_index: int,
    *,
    status: str,
    as_of: str,
    calls_used: int,
    classified: Mapping[str, int],
    attempted: int,
    expected: int,
    fetch_failed: int = 0,
    oldest_retrieved_at: str | None = None,
    newest_retrieved_at: str | None = None,
    retrieval_time_unknown: int = 0,
    oldest_normalization_as_of: str | None = None,
    newest_normalization_as_of: str | None = None,
    normalization_time_unknown: int = 0,
) -> dict[str, Any]:
    if status not in {"pending", "partial", "complete"}:
        raise ValueError(f"unknown shard status {status!r}")
    path = shard_path(snapshot_dir, shard_index)
    shard_sha256 = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    entry = {
        "status": status,
        "as_of": as_of,
        "attempted": attempted,
        "expected": expected,
        "calls_used": calls_used,
        "fetch_failed": fetch_failed,
        "oldest_retrieved_at": oldest_retrieved_at,
        "newest_retrieved_at": newest_retrieved_at,
        "retrieval_time_unknown": retrieval_time_unknown,
        "oldest_normalization_as_of": oldest_normalization_as_of,
        "newest_normalization_as_of": newest_normalization_as_of,
        "normalization_time_unknown": normalization_time_unknown,
        "shard_sha256": shard_sha256,
        "classified": dict(sorted(classified.items())),
    }
    manifest["shards"][str(shard_index)] = entry
    write_manifest(snapshot_dir, manifest)
    return manifest


def snapshot_status(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate readiness: complete shards, totals, and the exact-count invariant."""
    shards = manifest.get("shards") or {}
    totals: dict[str, int] = {name: 0 for name in CLASSIFICATIONS}
    complete = 0
    attempted_total = 0
    fetch_failed_total = 0
    retrieval_time_unknown_total = 0
    normalization_time_unknown_total = 0
    oldest_retrieved: str | None = None
    newest_retrieved: str | None = None
    for entry in shards.values():
        if entry.get("status") == "complete":
            complete += 1
        attempted_total += int(entry.get("attempted") or 0)
        fetch_failed_total += int(entry.get("fetch_failed") or 0)
        retrieval_time_unknown_total += int(entry.get("retrieval_time_unknown") or 0)
        normalization_time_unknown_total += int(entry.get("normalization_time_unknown") or 0)
        oldest = entry.get("oldest_retrieved_at")
        if (
            isinstance(oldest, str)
            and oldest
            and (oldest_retrieved is None or oldest < oldest_retrieved)
        ):
            oldest_retrieved = oldest
        newest = entry.get("newest_retrieved_at")
        if (
            isinstance(newest, str)
            and newest
            and (newest_retrieved is None or newest > newest_retrieved)
        ):
            newest_retrieved = newest
        for name, count in (entry.get("classified") or {}).items():
            totals[name] = totals.get(name, 0) + int(count or 0)
    universe_count = int(manifest.get("universe_count") or 0)
    classified_total = sum(totals.values())
    all_shards_complete = complete == int(manifest.get("shard_count") or 0)
    classification_matches_universe = classified_total == universe_count
    # Round-4 review: collection completeness and freshness provenance are
    # SEPARATE readiness axes — a shard full of unknown-provenance rows must
    # never look screenable, and staleness is judged from the ACTUAL
    # oldest/newest retrieval stamps, not the operator-supplied as_of.
    freshness_provenance_complete = (
        retrieval_time_unknown_total == 0
        and normalization_time_unknown_total == 0
        and (
            attempted_total == 0 or (oldest_retrieved is not None and newest_retrieved is not None)
        )
    )
    return {
        "snapshot_id": manifest.get("snapshot_id"),
        "shard_count": int(manifest.get("shard_count") or 0),
        "complete_shards": complete,
        "all_shards_complete": all_shards_complete,
        "attempted_total": attempted_total,
        "fetch_failed_total": fetch_failed_total,
        "retrieval_time_unknown_total": retrieval_time_unknown_total,
        "normalization_time_unknown_total": normalization_time_unknown_total,
        "oldest_retrieved_at": oldest_retrieved,
        "newest_retrieved_at": newest_retrieved,
        "classified_totals": totals,
        "classified_total": classified_total,
        "universe_count": universe_count,
        # The round-7 invariant: every frozen symbol is classified, exactly.
        "classification_matches_universe": classification_matches_universe,
        "freshness_provenance_complete": freshness_provenance_complete,
        # Manifest-level aggregation ONLY: says nothing about the shard
        # files' actual contents or staleness. ready_for_screening comes
        # exclusively from verify_snapshot(), which re-reads and verifies
        # every shard row against the frozen universe.
        "collection_ready": (
            all_shards_complete
            and classification_matches_universe
            and fetch_failed_total == 0
            and freshness_provenance_complete
        ),
    }


def _rows_from_bytes(data: bytes, *, path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(data.decode("utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, Mapping):
            raise ValueError(f"{path}:{line_no} is not a JSON object")
        rows.append(dict(value))
    return rows


def load_verified_snapshot(
    snapshot_dir: Path,
    *,
    screening_as_of: datetime,
    max_staleness_days: float,
    clock_skew_seconds: float = 300.0,
) -> dict[str, Any]:
    """Return a verification verdict and the rows read by that verification.

    ``snapshot_status`` trusts the manifest's own counters; a tampered,
    truncated or swapped ``shard-*.jsonl`` would sail through it. This
    function reads each artifact exactly once, verifies it symbol by symbol,
    and returns only those in-memory rows.  The consumer therefore cannot
    verify one set of bytes and later screen a different set of shard bytes.

    The returned ``verification_digest`` binds the exact manifest bytes, the
    canonical frozen-universe SHA-256, and every actual shard SHA-256.

    Verification checks:

    - the frozen universe itself (schema/count/uniqueness/SHA-256);
    - each shard file's SHA-256 against the manifest;
    - no duplicate symbols within or across shards;
    - every symbol belongs to its shard per ``stable_shard``;
    - every symbol is in the frozen universe, and the union of shard
      symbols covers the frozen universe EXACTLY;
    - every classification is an allowed value, and per-shard counts match
      the manifest;
    - retrieval stamps re-aggregated from the ROWS themselves and bounded on
      BOTH sides: ``screening_as_of - max_staleness_days <= oldest`` and
      ``newest <= screening_as_of + clock_skew_seconds`` — an historical
      ``screening_as_of`` must never see data fetched after it (look-ahead).

    ``ready_for_screening`` is true ONLY when all of the above hold and the
    manifest-level ``collection_ready`` aggregation agrees.
    """
    if max_staleness_days <= 0:
        raise ValueError("max_staleness_days must be positive")
    manifest_path = snapshot_dir / MANIFEST_NAME
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, Mapping):
        raise ValueError(f"{manifest_path} is not a JSON object")
    manifest = dict(manifest)
    if int(manifest.get("schema_version") or 0) != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported snapshot manifest schema_version {manifest.get('schema_version')!r}"
        )
    problems: list[str] = []
    try:
        universe_path = snapshot_dir / UNIVERSE_NAME
        universe = _rows_from_bytes(universe_path.read_bytes(), path=universe_path)
        expected_count = int(manifest.get("universe_count") or -1)
        if len(universe) != expected_count:
            raise ValueError(
                f"universe.jsonl has {len(universe)} rows but the manifest froze {expected_count}"
            )
        universe_symbols = [str(row.get("symbol") or "") for row in universe]
        if "" in universe_symbols or len(set(universe_symbols)) != len(universe_symbols):
            raise ValueError("universe.jsonl symbols are missing or not unique")
        universe_sha = _universe_sha256(universe)
        if universe_sha != manifest.get("universe_sha256"):
            raise ValueError(
                "universe.jsonl does not match the frozen universe_sha256 — the snapshot "
                "universe may have been modified; create a new snapshot instead"
            )
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        universe = []
        universe_sha = None
        problems.append(str(exc))
    expected_symbols = {str(row.get("symbol") or "") for row in universe}
    shard_count = int(manifest.get("shard_count") or 0)
    seen: dict[str, int] = {}
    row_stamps: list[datetime] = []
    unknown_stamp_rows = 0
    normalization_stamps: list[datetime] = []
    unknown_normalization_rows = 0
    verified_rows: list[dict[str, Any]] = []
    actual_shard_hashes: dict[str, str | None] = {}
    try:
        enumeration_audit, enumeration_sha = load_verified_enumeration(snapshot_dir, manifest)
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        enumeration_audit = {}
        enumeration_sha = None
        problems.append(str(exc))
    for index in range(shard_count):
        entry = (manifest.get("shards") or {}).get(str(index)) or {}
        path = shard_path(snapshot_dir, index)
        if not path.exists():
            actual_shard_hashes[str(index)] = None
            if int(entry.get("attempted") or 0) > 0:
                problems.append(f"shard {index}: file missing but manifest records rows")
            continue
        shard_bytes = path.read_bytes()
        recorded_sha = entry.get("shard_sha256")
        actual_sha = hashlib.sha256(shard_bytes).hexdigest()
        actual_shard_hashes[str(index)] = actual_sha
        if not (isinstance(recorded_sha, str) and recorded_sha):
            # A shard collected before SHA recording existed must be
            # backfilled (a zero-collect --resume re-records it) or
            # re-collected; readiness never accepts an unpinned shard.
            problems.append(f"shard {index}: manifest lacks shard_sha256")
        elif recorded_sha != actual_sha:
            problems.append(f"shard {index}: file SHA-256 does not match the manifest")
        recount: dict[str, int] = {}
        shard_normalization_stamps: list[str] = []
        shard_unknown_normalization = 0
        shard_rows = _rows_from_bytes(shard_bytes, path=path)
        expected_in_shard = sum(
            1 for symbol in expected_symbols if stable_shard(symbol, shard_count) == index
        )
        if int(entry.get("attempted") or 0) != len(shard_rows):
            problems.append(f"shard {index}: manifest attempted count does not match the file")
        if int(entry.get("expected") or 0) != expected_in_shard:
            problems.append(f"shard {index}: manifest expected count does not match the universe")
        for row in shard_rows:
            symbol = str(row.get("symbol") or "")
            if not symbol:
                problems.append(f"shard {index}: row without a symbol")
                continue
            if symbol in seen:
                problems.append(f"shard {index}: duplicate symbol {symbol}")
                continue
            seen[symbol] = index
            if expected_symbols and symbol not in expected_symbols:
                problems.append(f"shard {index}: {symbol} is not in the frozen universe")
            if shard_count and stable_shard(symbol, shard_count) != index:
                problems.append(f"shard {index}: {symbol} belongs to another shard")
            if row.get("snapshot_shard") != index:
                problems.append(f"shard {index}: {symbol} carries the wrong snapshot_shard")
            name = str(row.get("snapshot_classification") or "")
            if name not in CLASSIFICATIONS:
                problems.append(f"shard {index}: {symbol} has classification {name!r}")
            recount[name] = recount.get(name, 0) + 1
            stamp = row.get("snapshot_retrieved_at")
            if isinstance(stamp, str) and stamp:
                try:
                    stamp_dt = datetime.fromisoformat(stamp)
                except ValueError:
                    problems.append(f"shard {index}: {symbol} has unparsable snapshot_retrieved_at")
                else:
                    if stamp_dt.tzinfo is None:
                        stamp_dt = stamp_dt.replace(tzinfo=timezone.utc)
                    row_stamps.append(stamp_dt)
            else:
                unknown_stamp_rows += 1
            normalization_stamp = row.get("snapshot_normalization_as_of")
            if isinstance(normalization_stamp, str) and normalization_stamp:
                try:
                    normalization_dt = datetime.fromisoformat(normalization_stamp)
                except ValueError:
                    problems.append(
                        f"shard {index}: {symbol} has unparsable snapshot_normalization_as_of"
                    )
                else:
                    if normalization_dt.tzinfo is None:
                        normalization_dt = normalization_dt.replace(tzinfo=timezone.utc)
                    normalization_stamps.append(normalization_dt)
                    shard_normalization_stamps.append(normalization_dt.isoformat())
            else:
                unknown_normalization_rows += 1
                shard_unknown_normalization += 1
            verified_rows.append(row)
        recorded = {key: int(value or 0) for key, value in (entry.get("classified") or {}).items()}
        if recorded != recount:
            problems.append(f"shard {index}: manifest classification counts do not match the file")
        recorded_oldest_normalization = entry.get("oldest_normalization_as_of")
        recorded_newest_normalization = entry.get("newest_normalization_as_of")
        actual_shard_oldest = (
            min(shard_normalization_stamps) if shard_normalization_stamps else None
        )
        actual_shard_newest = (
            max(shard_normalization_stamps) if shard_normalization_stamps else None
        )
        if (
            recorded_oldest_normalization != actual_shard_oldest
            or recorded_newest_normalization != actual_shard_newest
            or int(entry.get("normalization_time_unknown") or 0) != shard_unknown_normalization
        ):
            problems.append(
                f"shard {index}: manifest normalization provenance does not match the file"
            )
    missing = expected_symbols - set(seen)
    if missing:
        problems.append(
            f"{len(missing)} frozen-universe symbols never collected (e.g. {sorted(missing)[:5]})"
        )
    if unknown_stamp_rows:
        problems.append(f"{unknown_stamp_rows} rows carry no retrieval stamp (unknown provenance)")
    if unknown_normalization_rows:
        problems.append(
            f"{unknown_normalization_rows} rows carry no normalization as-of (unknown provenance)"
        )
    status = snapshot_status(manifest)
    # Freshness is judged from the stamps RE-AGGREGATED out of the shard
    # rows themselves (the manifest's own bounds are informational only),
    # and bounded on BOTH sides: old data is stale, and data fetched after
    # screening_as_of is look-ahead — fatal for historical/as-of runs.
    actual_oldest = min(row_stamps) if row_stamps else None
    actual_newest = max(row_stamps) if row_stamps else None
    staleness_ok = actual_oldest is not None and actual_oldest >= screening_as_of - timedelta(
        days=float(max_staleness_days)
    )
    no_future_retrievals = actual_newest is not None and actual_newest <= (
        screening_as_of + timedelta(seconds=float(clock_skew_seconds))
    )
    actual_oldest_normalization = min(normalization_stamps) if normalization_stamps else None
    actual_newest_normalization = max(normalization_stamps) if normalization_stamps else None
    normalization_current = (
        actual_oldest_normalization is not None
        and actual_oldest_normalization
        >= screening_as_of - timedelta(days=float(max_staleness_days))
    )
    no_future_normalization = (
        actual_newest_normalization is not None
        and actual_newest_normalization
        <= screening_as_of + timedelta(seconds=float(clock_skew_seconds))
    )
    binding = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "universe_sha256": universe_sha,
        "listing_enumeration_audit_sha256": enumeration_sha,
        "shard_sha256": actual_shard_hashes,
    }
    verification_digest = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    contents_verified = not problems
    verdict = {
        **status,
        "screening_as_of": screening_as_of.astimezone(timezone.utc).isoformat(),
        "max_staleness_days": float(max_staleness_days),
        "clock_skew_seconds": float(clock_skew_seconds),
        "verified_oldest_retrieved_at": actual_oldest.isoformat() if actual_oldest else None,
        "verified_newest_retrieved_at": actual_newest.isoformat() if actual_newest else None,
        "verified_oldest_normalization_as_of": (
            actual_oldest_normalization.isoformat() if actual_oldest_normalization else None
        ),
        "verified_newest_normalization_as_of": (
            actual_newest_normalization.isoformat() if actual_newest_normalization else None
        ),
        "staleness_ok": staleness_ok,
        "no_future_retrievals": no_future_retrievals,
        "normalization_current": normalization_current,
        "no_future_normalization": no_future_normalization,
        "listing_enumeration": enumeration_audit,
        "listing_enumeration_verified": bool(enumeration_audit),
        "problem_count": len(problems),
        "problems": problems[:50],
        "contents_verified": contents_verified,
        "snapshot_verification_digest": verification_digest,
        "verification_binding": binding,
        "ready_for_screening": (
            contents_verified
            and bool(status.get("collection_ready"))
            and staleness_ok
            and no_future_retrievals
            and normalization_current
            and no_future_normalization
        ),
    }
    return {
        "verdict": verdict,
        "verification_digest": verification_digest,
        "rows": verified_rows if verdict["ready_for_screening"] else [],
    }


def verify_snapshot(
    snapshot_dir: Path,
    *,
    screening_as_of: datetime,
    max_staleness_days: float,
    clock_skew_seconds: float = 300.0,
) -> dict[str, Any]:
    """Deep readiness verdict; use ``load_verified_snapshot`` when screening."""
    return load_verified_snapshot(
        snapshot_dir,
        screening_as_of=screening_as_of,
        max_staleness_days=max_staleness_days,
        clock_skew_seconds=clock_skew_seconds,
    )["verdict"]
