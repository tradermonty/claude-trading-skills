"""Trader Memory Core — skill output → thesis conversion (register only).

Each adapter transforms a skill's JSON output into a thesis_data dict
suitable for thesis_store.register().
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Allow imports from sibling modules
sys.path.insert(0, str(Path(__file__).resolve().parent))

import thesis_store  # noqa: E402

logger = logging.getLogger(__name__)

# -- Adapter registry ---------------------------------------------------------

_ADAPTERS: dict[str, callable] = {}


def _adapter(source_name: str):
    """Decorator to register an ingest adapter."""

    def wrapper(fn):
        _ADAPTERS[source_name] = fn
        return fn

    return wrapper


# -- Individual Adapters ------------------------------------------------------


@_adapter("kanchi-dividend-sop")
def ingest_kanchi(record: dict, input_file: str) -> dict:
    """Transform kanchi-dividend-sop output into thesis data."""
    ticker = record.get("ticker")
    if not ticker:
        raise ValueError("Missing required field 'ticker' in kanchi record")

    thesis_data = {
        "ticker": ticker,
        "thesis_type": "dividend_income",
        "thesis_statement": (f"{ticker} dividend income thesis from Kanchi screening"),
        "setup_type": record.get("setup_type", "kanchi_5step"),
        "_register_reason": "screened by kanchi-dividend-sop",
        "entry": {},
        "exit": {},
        "origin": {
            "skill": "kanchi-dividend-sop",
            "output_file": input_file,
            "screening_grade": record.get("grade"),
            "screening_score": record.get("score"),
            "raw_provenance": {k: v for k, v in record.items()},
        },
    }

    # Map buy_target_price → entry.target_price
    if "buy_target_price" in record:
        thesis_data["entry"]["target_price"] = record["buy_target_price"]

    # Map stop_loss if present
    if "stop_loss" in record:
        thesis_data["exit"]["stop_loss"] = record["stop_loss"]

    # Copy evidence fields
    if "evidence" in record:
        thesis_data["evidence"] = record["evidence"]

    if "kill_criteria" in record:
        thesis_data["kill_criteria"] = record["kill_criteria"]

    if "catalyst" in record:
        thesis_data["catalyst"] = record["catalyst"]

    return thesis_data


_VALID_THESIS_TYPES = (
    "dividend_income",
    "growth_momentum",
    "mean_reversion",
    "earnings_drift",
    "pivot_breakout",
)


def _manual_source_date(record: dict) -> str | None:
    """Date-only (YYYY-MM-DD) source date for a manual record.

    register() builds the IDEA history stamp as
    ``f"{_source_date}T00:00:00+00:00"``, so _source_date MUST be date-only —
    a full ISO entry_date would yield a broken double-suffixed timestamp.
    Mirrors _extract_source_date()'s ``[:10]`` slice; handles missing/typed
    values defensively.
    """
    for key in ("entry_date", "as_of"):
        val = record.get(key)
        if val and isinstance(val, str):
            return val[:10]  # "YYYY-MM-DD" or "YYYY-MM-DDTHH:..."
    return None


@_adapter("manual")
def ingest_manual(record: dict, input_file: str) -> dict:
    """Transform a hand-entered (free-form) position record into thesis data.

    For trades that did not come from a screener adapter (fractional-share
    brokers, manual journaling). Creates an IDEA thesis only — exactly like
    every other adapter. An already-open broker position reaches ACTIVE via
    the explicit CLI sequence: transition → open-position (both accept
    --event-date for backdating). No status mutation here.

    Required: ticker, thesis_statement, thesis_type.
    Optional: entry_price, entry_date, shares, stop_price/stop_loss,
    target_price/take_profit, setup_type, notes. entry_price/entry_date/shares
    are recorded in origin.raw_provenance only — the authoritative
    entry.actual_* / position.shares are set later by `open-position`.
    """
    ticker = record.get("ticker")
    if not ticker:
        raise ValueError("Missing required field 'ticker' in manual record")

    thesis_statement = record.get("thesis_statement")
    if not thesis_statement:
        raise ValueError(f"Missing required field 'thesis_statement' in manual record for {ticker}")

    thesis_type = record.get("thesis_type")
    if thesis_type not in _VALID_THESIS_TYPES:
        raise ValueError(
            f"Invalid or missing 'thesis_type' for {ticker}: {thesis_type!r}. "
            f"Expected one of {', '.join(_VALID_THESIS_TYPES)}"
        )

    thesis_data = {
        "ticker": ticker,
        "thesis_type": thesis_type,
        "thesis_statement": thesis_statement,
        "setup_type": record.get("setup_type"),
        "_register_reason": "manually entered",
        "entry": {},
        "exit": {},
        "origin": {
            "skill": "manual",
            "output_file": input_file,
            "raw_provenance": {k: v for k, v in record.items()},
        },
    }

    # Optional risk levels → existing schema fields only (entry/exit are
    # additionalProperties:false). entry_price/entry_date/shares intentionally
    # NOT mapped to entry.* — they live in origin.raw_provenance; the
    # authoritative values are set by `open-position`.
    stop = record.get("stop_loss", record.get("stop_price"))
    if stop is not None:
        thesis_data["exit"]["stop_loss"] = stop
    target = record.get("take_profit", record.get("target_price"))
    if target is not None:
        thesis_data["exit"]["take_profit"] = target

    source_date = _manual_source_date(record)
    if source_date:
        thesis_data["_source_date"] = source_date

    return thesis_data


@_adapter("earnings-trade-analyzer")
def ingest_earnings(record: dict, input_file: str) -> dict:
    """Transform earnings-trade-analyzer result into thesis data."""
    ticker = record.get("symbol")
    if not ticker:
        raise ValueError("Missing required field 'symbol' in earnings record")

    thesis_data = {
        "ticker": ticker,
        "thesis_type": "earnings_drift",
        "thesis_statement": (
            f"{ticker} earnings drift thesis — "
            f"grade {record.get('grade', '?')}, "
            f"gap {record.get('gap_pct', '?')}%"
        ),
        "_register_reason": "screened by earnings-trade-analyzer",
        "entry": {},
        "exit": {},
        "market_context": {},
        "origin": {
            "skill": "earnings-trade-analyzer",
            "output_file": input_file,
            "screening_grade": record.get("grade"),
            "screening_score": record.get("composite_score"),
            "raw_provenance": {k: v for k, v in record.items()},
        },
    }

    if "sector" in record:
        thesis_data["market_context"]["sector"] = record["sector"]

    return thesis_data


@_adapter("vcp-screener")
def ingest_vcp(record: dict, input_file: str) -> dict:
    """Transform vcp-screener result into thesis data."""
    ticker = record.get("symbol")
    if not ticker:
        raise ValueError("Missing required field 'symbol' in VCP record")

    thesis_data = {
        "ticker": ticker,
        "thesis_type": "pivot_breakout",
        "thesis_statement": (
            f"{ticker} VCP pivot breakout — "
            f"distance from pivot {record.get('distance_from_pivot_pct', '?')}%"
        ),
        "_register_reason": "screened by vcp-screener",
        "entry": {},
        "exit": {},
        "origin": {
            "skill": "vcp-screener",
            "output_file": input_file,
            "screening_grade": record.get("rating"),
            "screening_score": record.get("composite_score"),
            "raw_provenance": {k: v for k, v in record.items()},
        },
    }

    return thesis_data


@_adapter("pead-screener")
def ingest_pead(record: dict, input_file: str) -> dict:
    """Transform pead-screener result into thesis data."""
    ticker = record.get("symbol")
    if not ticker:
        raise ValueError("Missing required field 'symbol' in PEAD record")

    thesis_data = {
        "ticker": ticker,
        "thesis_type": "earnings_drift",
        "thesis_statement": (f"{ticker} PEAD earnings drift — status {record.get('status', '?')}"),
        "_register_reason": "screened by pead-screener",
        "entry": {},
        "exit": {},
        "origin": {
            "skill": "pead-screener",
            "output_file": input_file,
            "screening_grade": record.get("grade"),
            "screening_score": record.get("composite_score"),
            "raw_provenance": {k: v for k, v in record.items()},
        },
    }

    if "entry_price" in record:
        thesis_data["entry"]["target_price"] = record["entry_price"]
    if "stop_loss" in record:
        thesis_data["exit"]["stop_loss"] = record["stop_loss"]

    return thesis_data


@_adapter("canslim-screener")
def ingest_canslim(record: dict, input_file: str) -> dict:
    """Transform canslim-screener result into thesis data."""
    ticker = record.get("symbol")
    if not ticker:
        raise ValueError("Missing required field 'symbol' in CANSLIM record")

    thesis_data = {
        "ticker": ticker,
        "thesis_type": "growth_momentum",
        "thesis_statement": (
            f"{ticker} CANSLIM growth momentum — rating {record.get('rating', '?')}"
        ),
        "_register_reason": "screened by canslim-screener",
        "entry": {},
        "exit": {},
        "origin": {
            "skill": "canslim-screener",
            "output_file": input_file,
            "screening_grade": record.get("rating"),
            "screening_score": record.get("composite_score"),
            "raw_provenance": {k: v for k, v in record.items()},
        },
    }

    return thesis_data


@_adapter("edge-candidate-agent")
def ingest_edge(record: dict, input_file: str) -> dict | None:
    """Transform edge-candidate-agent ticket into thesis data.

    Phase 1 constraints:
    - research_only=True tickets are skipped (returns None)
    - Tickets without a single ticker/symbol are skipped (returns None)
    """
    # Check research_only
    if record.get("research_only", False):
        logger.warning(
            "Skipping edge ticket %s: research_only=True",
            record.get("id", "unknown"),
        )
        return None

    # Extract ticker — check multiple possible fields
    ticker = record.get("ticker") or record.get("symbol")
    if not ticker:
        # Check if it's a market basket or multi-ticker
        universe = record.get("universe")
        if isinstance(universe, str) and universe.upper() == "MARKET_BASKET":
            logger.warning(
                "Skipping edge ticket %s: MARKET_BASKET (no single ticker)",
                record.get("id", "unknown"),
            )
            return None
        logger.warning(
            "Skipping edge ticket %s: no single ticker/symbol found",
            record.get("id", "unknown"),
        )
        return None

    # Determine thesis_type from hypothesis_type / entry_family
    entry_family = record.get("entry_family", "")
    hypothesis_type = record.get("hypothesis_type", "")

    if "breakout" in entry_family or "breakout" in hypothesis_type:
        thesis_type = "pivot_breakout"
    elif "gap" in entry_family or "drift" in hypothesis_type:
        thesis_type = "earnings_drift"
    elif "reversion" in hypothesis_type or "mean" in hypothesis_type:
        thesis_type = "mean_reversion"
    elif "momentum" in hypothesis_type or "growth" in hypothesis_type:
        thesis_type = "growth_momentum"
    else:
        thesis_type = "pivot_breakout"  # default for edge strategies

    thesis_data = {
        "ticker": ticker,
        "thesis_type": thesis_type,
        "thesis_statement": (
            f"{ticker} edge strategy — {record.get('name', hypothesis_type or 'unknown')}"
        ),
        "mechanism_tag": record.get("mechanism_tag"),
        "_register_reason": "screened by edge-candidate-agent",
        "entry": {},
        "exit": {},
        "origin": {
            "skill": "edge-candidate-agent",
            "output_file": input_file,
            "screening_grade": None,
            "screening_score": None,
            "raw_provenance": {k: v for k, v in record.items()},
        },
    }

    # Map entry/exit — ticket schema uses top-level entry/exit (not signals.entry)
    entry_data = record.get("entry", {})
    exit_data = record.get("exit", {})
    if isinstance(entry_data, dict):
        if "conditions" in entry_data:
            thesis_data["entry"]["conditions"] = entry_data["conditions"]
        if "target_price" in entry_data:
            thesis_data["entry"]["target_price"] = entry_data["target_price"]
    if isinstance(exit_data, dict):
        if "stop_loss" in exit_data:
            thesis_data["exit"]["stop_loss"] = exit_data["stop_loss"]
        if "stop_loss_pct" in exit_data:
            thesis_data["exit"]["stop_loss_pct"] = exit_data["stop_loss_pct"]
        if "take_profit_rr" in exit_data:
            thesis_data["exit"]["take_profit_rr"] = exit_data["take_profit_rr"]
        if "time_stop_days" in exit_data:
            thesis_data["exit"]["time_stop_days"] = exit_data["time_stop_days"]

    return thesis_data


# -- Public API ---------------------------------------------------------------


def ingest(
    source: str,
    input_file: str,
    state_dir: str = "state/theses",
) -> list[str]:
    """Ingest skill output and register theses.

    Args:
        source: Source skill name (e.g., "kanchi-dividend-sop").
        input_file: Path to JSON file with skill output.
        state_dir: Path to thesis state directory.

    Returns:
        List of registered thesis IDs.

    Raises:
        ValueError: If source is unknown or input is invalid.
        FileNotFoundError: If input file doesn't exist.
    """
    if source not in _ADAPTERS:
        raise ValueError(f"Unknown source: {source}. Available: {sorted(_ADAPTERS.keys())}")

    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    with open(input_path) as f:
        data = json.load(f)

    adapter = _ADAPTERS[source]
    state_path = Path(state_dir)

    # Extract source date from top-level metadata (as_of, generated_at, etc.)
    source_date = _extract_source_date(data)

    # Handle both single-record and multi-record (results array) formats
    records = _extract_records(data, source)

    thesis_ids = []
    for record in records:
        try:
            thesis_data = adapter(record, input_file)
        except ValueError as e:
            logger.error("Adapter error for %s: %s", source, e)
            continue
        if thesis_data is None:
            continue  # skipped (e.g., edge research_only)
        # Inject source date so thesis_id and created_at reflect the report date
        if source_date and "_source_date" not in thesis_data:
            thesis_data["_source_date"] = source_date
        try:
            tid = thesis_store.register(state_path, thesis_data)
            thesis_ids.append(tid)
        except ValueError as e:
            logger.error("Failed to register from %s: %s", source, e)

    return thesis_ids


def _extract_source_date(data: dict | list) -> str | None:
    """Extract report date from top-level metadata.

    Checks as_of, generated_at, and date fields.
    Returns YYYY-MM-DD string or None.
    """
    if isinstance(data, list):
        return None
    # as_of is the canonical source date (kanchi, earnings-trade-analyzer)
    as_of = data.get("as_of")
    if as_of and isinstance(as_of, str):
        return as_of[:10]  # "YYYY-MM-DD" or "YYYY-MM-DDTHH:..."
    # generated_at as fallback
    gen = data.get("generated_at")
    if gen and isinstance(gen, str):
        return gen[:10]
    return None


def _extract_records(data: dict | list, source: str) -> list[dict]:
    """Extract individual records from various output formats."""
    if isinstance(data, list):
        return data

    # Manual entry is free-form: a single dict is always one record, so the
    # manual adapter (not _extract_records) owns required-field validation and
    # can emit a clear "Missing required field 'ticker'" message.
    if source == "manual" and isinstance(data, dict):
        return [data]

    # Common patterns: {results: [...]}, {candidates: [...]}, {rows: [...]}, ...
    for key in ("results", "candidates", "rows"):
        if key in data and isinstance(data[key], list):
            return data[key]

    # Single record (e.g., edge ticket)
    if "id" in data or "ticker" in data or "symbol" in data:
        return [data]

    raise ValueError(
        f"Cannot extract records from {source} output. "
        "Expected list, or dict with 'results'/'candidates' key."
    )


# -- CLI entry point ----------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Ingest skill output into Trader Memory Core")
    parser.add_argument("--source", required=True, help="Source skill name")
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    parser.add_argument("--state-dir", default="state/theses", help="Thesis state directory")
    args = parser.parse_args()

    ids = ingest(args.source, args.input, args.state_dir)
    if ids:
        print(f"Registered {len(ids)} thesis(es): {', '.join(ids)}")
    else:
        print("No theses registered.")
        sys.exit(1)
