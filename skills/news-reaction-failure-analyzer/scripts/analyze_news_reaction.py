#!/usr/bin/env python3
"""
News Reaction Failure Analyzer

Step 2 of Jason Shapiro's COT contrarian process: judge whether a market
FAILED to react to news favorable to the crowded side (a "news failure").
Generic beyond COT/futures -- consumes a COT-crowding detector's output (or
an explicit --direction) plus a Claude-curated events JSON, fetches the
underlying price series with a documented fallback chain, and produces a
fail-closed 3-value verdict (CONFIRMED / NOT_CONFIRMED / INSUFFICIENT_EVIDENCE)
using the drift-significance test implemented in reaction_math.py.

Data source notes (verified live against the FMP stable API, 2026-07):
  - `stable/historical-price-eod/light` per-symbol coverage on a Premium+
    key is uneven: some futures symbols (indices ES, metals GC/SI, all FX
    majors, Brent BZ, BTC) return 200 with data; most others (rates, most
    energy, most metals, DX, other equity indices) return 402. A few
    (VX, and several agri commodities) return 200 with ZERO rows -- a
    distinct failure mode from HTTP errors that must be checked explicitly
    (`rows == 0` is treated as a source failure, same as a 402/5xx).
  - ETF proxies (plain stock EOD) work on all FMP tiers and are used as a
    documented fallback for symbols with no working futures price feed.
    Proxy use is recorded in run_context.proxy_used and echoed in the
    Markdown report footer (tracking error / expense drag / roll caveat).
  - The `light` EOD endpoint's row shape uses a `price` field, NOT `close`
    -- verified across futures, ETF, and FX symbols alike. reaction_math's
    build_sorted_series() accepts `close` (other endpoints) or falls back
    to `price` (this endpoint) so this doesn't need special-casing here.
  - COT symbols (ES, GC, B6, ...) are NOT FMP price symbols; PRICE_SOURCE_CHAINS
    is the explicit map, verified live at implementation time (see
    references/price-source-map.md for the full per-market status table).
  - No reliable FMP news endpoint exists for futures; events are curated by
    Claude via WebSearch into an events JSON (see references/news-failure-
    patterns.md for the curation guide and 4-tier source hierarchy).

Redaction: dual-layer (value-based primary + pattern-family secondary), a
self-contained copy of the proven cot-contrarian-detector pattern -- see
`_redact()` below.

Output:
  - JSON: nrf_<symbol>_YYYY-MM-DD.json
  - Markdown: nrf_<symbol>_YYYY-MM-DD.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - environment guard
    requests = None

from reaction_math import (
    DRIFT_Z_DEFAULT,
    MIN_EVENTS_DEFAULT,
    Z_THRESHOLD_DEFAULT,
    build_sorted_series,
    classify_reaction,
    compute_daily_stdev,
    compute_effective_date,
    compute_returns,
    compute_zscore_1d,
    compute_zscore_3d,
    direction_adjusted_zscore,
    expected_direction_for,
    find_date_index,
    synthesize_result,
)

SKILL_NAME = "news-reaction-failure-analyzer"
SCHEMA_VERSION = "1.0"

STABLE_EOD_URL = "https://financialmodelingprep.com/stable/historical-price-eod/light"

WINDOW_DAYS_DEFAULT = 10
MAX_DETECTOR_AGE_DAYS_DEFAULT = 10

# Extra calendar days fetched before/after the nominal window so effective-
# date snapping and the 60-trading-day daily_stdev lookback both have real
# bars to work with, without a second round-trip. The lookahead fetch is
# deliberately over-requested and then clipped to --as-of by
# fetch_price_series()'s cutoff filter -- it only pays off on a
# live/current --as-of run, where "after as_of" simply doesn't exist yet in
# FMP's data; on a backdated --as-of it fetches real future-relative-to-
# as_of bars that the cutoff filter then discards, to avoid lookahead bias.
PRICE_FETCH_LOOKBACK_DAYS = 130
PRICE_FETCH_LOOKAHEAD_DAYS = 10

# --- Price-source map (verified live, 2026-07-12; see
# references/price-source-map.md for the full status table and caveats).
# {cot_symbol: [(price_symbol, kind, invert), ...]} -- tried in order; a
# source fails on HTTP error OR rows == 0; first success wins.
PRICE_SOURCE_CHAINS: dict[str, list[tuple[str, str, bool]]] = {
    "ES": [("ESUSD", "futures", False)],
    "NQ": [("NQUSD", "futures", False), ("QQQ", "etf", False)],
    "YM": [("YMUSD", "futures", False), ("DIA", "etf", False)],
    "QR": [("RTYUSD", "futures", False), ("IWM", "etf", False)],
    "VX": [("VXUSD", "futures", False)],  # 200/0 rows on this key -> no_price_source
    "GC": [("GCUSD", "futures", False)],
    "SI": [("SIUSD", "futures", False)],
    "HG": [("HGUSD", "futures", False), ("CPER", "etf", False)],
    "PL": [("PLUSD", "futures", False), ("PPLT", "etf", False)],
    "PA": [("PAUSD", "futures", False), ("PALL", "etf", False)],
    "CL": [("CLUSD", "futures", False), ("BZUSD", "futures", False), ("USO", "etf", False)],
    "NG": [("NGUSD", "futures", False), ("UNG", "etf", False)],
    "RB": [("RBUSD", "futures", False), ("UGA", "etf", False)],
    "HO": [("HOUSD", "futures", False)],  # no proxy -> no_price_source
    "ZT": [("ZTUSD", "futures", False), ("SHY", "etf", False)],
    "ZF": [("ZFUSD", "futures", False), ("IEI", "etf", False)],
    "ZN": [("ZNUSD", "futures", False), ("IEF", "etf", False)],
    "ZB": [("ZBUSD", "futures", False), ("TLT", "etf", False)],
    "ZQ": [("ZQUSD", "futures", False)],  # no proxy -> no_price_source
    "DX": [("DXUSD", "futures", False), ("UUP", "etf", False)],
    "B6": [("GBPUSD", "futures", False)],
    "E6": [("EURUSD", "futures", False)],
    "J6": [("JPYUSD", "futures", False)],
    "S6": [("CHFUSD", "futures", False)],
    "D6": [("CADUSD", "futures", False)],
    "A6": [("AUDUSD", "futures", False)],
    "N6": [("NZDUSD", "futures", False)],
    "BT": [("BTCUSD", "futures", False)],
    # Agri: probed at implementation time -- all 0 rows or 402 on this key,
    # no ETF proxy documented -> every agri market is no_price_source (v1
    # limitation; a proxy chain can be added once a working source is found).
    "ZC": [("ZCUSD", "futures", False)],
    "ZS": [("ZSUSD", "futures", False)],
    "ZM": [("ZMUSD", "futures", False)],
    "ZL": [("ZLUSD", "futures", False)],
    "ZW": [("ZWUSD", "futures", False)],
}


# --- Redaction (self-contained copy of the cot-contrarian-detector pattern)
#
# `requests` exceptions embed the full request URL -- including `?apikey=...`
# -- in their str(). Pattern-based redaction alone only catches shapes with
# an "apikey" marker; value-based redaction (passing the known `secret`)
# also catches a bare key with no marker at all (e.g. echoed into an HTML
# error page body). Both layers are applied; neither is sufficient alone.
_APIKEY_PATTERNS = (
    re.compile(r"apikey\s*=\s*[^&\s'\"]+", re.IGNORECASE),
    re.compile(r'"apikey"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r"'apikey'\s*:\s*'[^']*'", re.IGNORECASE),
    re.compile(r"apikey%3d[^&\s'\"]+", re.IGNORECASE),
)


def _redact(text: str | None, secret: str | None = None) -> str | None:
    """Redact the FMP API key from an error/exception string. See
    cot-contrarian-detector/scripts/screen_cot_crowding.py for the proven
    original of this pattern (self-contained copy here, not imported, so
    this skill has no cross-skill dependency)."""
    if not text:
        return text
    if secret:
        text = text.replace(secret, "***REDACTED***")
    for pattern in _APIKEY_PATTERNS:
        text = pattern.sub("apikey=***REDACTED***", text)
    return text


def get_api_key(cli_key: str | None) -> str | None:
    """Resolve the FMP API key: --api-key argument takes priority over env."""
    if cli_key:
        return cli_key
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        print("Warning: FMP_API_KEY environment variable not set", file=sys.stderr)
    return api_key


def _request_with_backoff(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    max_retries: int = 4,
    base_delay: float = 1.0,
) -> tuple[Any, str | None]:
    """GET JSON with exponential backoff retry on 429 / 5xx. Non-retryable
    4xx (401/402/403/404/...) fail immediately -- a 402 is expected/routine
    here (advances the fallback chain), not something to retry."""
    secret = params.get("apikey") if isinstance(params, dict) else None
    delay = base_delay
    error = "unknown error"
    for attempt in range(max_retries + 1):
        try:
            response = session.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException as exc:
            error = _redact(f"request exception: {exc}", secret=secret)
        else:
            if response.status_code == 200:
                try:
                    return response.json(), None
                except ValueError as exc:
                    error = _redact(f"invalid JSON response: {exc}", secret=secret)
            elif response.status_code == 429 or response.status_code >= 500:
                error = f"HTTP {response.status_code}"
            else:
                return None, _redact(
                    f"HTTP {response.status_code}: {response.text[:200]}", secret=secret
                )

        if attempt < max_retries:
            print(
                f"WARN: {error}; retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay *= 2
    return None, error


class PriceClient:
    """Thin client for FMP's stable EOD price endpoint with rate limiting."""

    def __init__(self, api_key: str, sleep_seconds: float = 0.25):
        if requests is None:
            print(
                "ERROR: requests library not found. Install with: pip install requests",
                file=sys.stderr,
            )
            sys.exit(1)
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.session = requests.Session()
        self.last_call_time = 0.0
        self.api_calls_made = 0

    def get_eod_rows(
        self, symbol: str, from_date: str, to_date: str
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        """Fetch daily EOD rows for one symbol. Returns (rows, None) on
        success -- rows may be an EMPTY list (a distinct, documented failure
        mode, e.g. VXUSD on this key: 200 OK but zero rows) -- or
        (None, error) on an HTTP/transport failure."""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.sleep_seconds:
            time.sleep(self.sleep_seconds - elapsed)
        params = {"symbol": symbol, "from": from_date, "to": to_date, "apikey": self.api_key}
        data, error = _request_with_backoff(self.session, STABLE_EOD_URL, params)
        self.last_call_time = time.time()
        self.api_calls_made += 1
        if error:
            return None, error
        return data if isinstance(data, list) else [], None


def fetch_price_series(
    client: PriceClient,
    chain: list[tuple[str, str, bool]],
    from_date: str,
    to_date: str,
    as_of: str,
) -> dict[str, Any]:
    """Try each (price_symbol, kind, invert) in `chain` in order. A source
    fails on HTTP error OR `rows == 0` (a distinct, documented failure mode
    -- some symbols return 200 with an empty body rather than an HTTP
    error). First success wins.

    `as_of` is an INFORMATION CUTOFF, not just a report label: any bar
    dated after it is dropped before a source is considered successful.
    Without this, a backdated --as-of run would see prices that hadn't
    happened yet at that date (lookahead bias) -- the caller intentionally
    over-requests `to_date` past `as_of` (see PRICE_FETCH_LOOKAHEAD_DAYS)
    so a live/current-date run has real bars near the window edge; this is
    what actually enforces the cutoff for a backdated run. A source whose
    rows are entirely after `as_of` degrades the same way as "0 rows".

    Returns a dict:
      success: {"error": None, "series": [(date, close), ...], "price_symbol",
                "source_kind", "proxy_used", "inverted", "attempts": [...]}
      all fail: {"error": "no_price_source", "series": [], "price_symbol": None,
                 "attempts": [...]}
    `attempts` is a list of {"price_symbol", "kind", "status"} for
    transparency (used in the report's run_context / dropped reasoning).
    """
    attempts: list[dict[str, Any]] = []
    for price_symbol, kind, invert in chain:
        rows, error = client.get_eod_rows(price_symbol, from_date, to_date)
        if error:
            attempts.append(
                {"price_symbol": price_symbol, "kind": kind, "status": f"error: {error}"}
            )
            continue
        if not rows:
            attempts.append({"price_symbol": price_symbol, "kind": kind, "status": "0 rows"})
            continue
        series = build_sorted_series(rows)
        series = [(d, c) for d, c in series if d <= as_of]
        if not series:
            attempts.append({"price_symbol": price_symbol, "kind": kind, "status": "0 rows"})
            continue
        attempts.append({"price_symbol": price_symbol, "kind": kind, "status": "ok"})
        return {
            "error": None,
            "series": series,
            "price_symbol": price_symbol,
            "source_kind": kind,
            "proxy_used": kind == "etf",
            "inverted": invert,
            "attempts": attempts,
        }
    return {
        "error": "no_price_source",
        "series": [],
        "price_symbol": None,
        "source_kind": None,
        "proxy_used": False,
        "inverted": False,
        "attempts": attempts,
    }


# --- Detector-json handling --------------------------------------------------


def load_json_file(path: str) -> tuple[dict[str, Any] | None, str | None]:
    """Read and parse a JSON file. Returns (data, None) or (None, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read {path}: {exc}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc}"


def resolve_direction_from_detector(
    detector_data: Any,
    symbol: str,
    as_of: str,
    max_age_days: int,
) -> tuple[str | None, str | None, dict[str, Any]]:
    """Implements the CLI's --detector-json lookup algorithm (plan §2):

    (a) symbol not in markets[], or present in skipped[] -> refuse with
        reason `detector_missing_symbol`.
    (b) classification == NEUTRAL -> refuse with reason `not_crowded`
        (fail-closed; only an explicit --direction overrides this).
    (c) detector run_context.data_date / run_context.as_of missing,
        unparsable, or dated AFTER --as-of -> reason
        `detector_missing_data_date` / `detector_invalid_data_date` /
        `detector_future_data_date` respectively (all fail-closed -- a
        detector-json's classification is meaningless without a
        trustworthy vintage). Older than --max-detector-age-days vs
        --as-of -> reason `detector_json_stale`.

    `detector_data` is untrusted, parsed JSON: valid JSON but the wrong
    shape (top-level list/string/null, `markets`/`skipped` not lists, list
    items not dicts, ...) must never crash -- it degrades to
    `malformed_detector_json` (top-level) or to treating the bad field as
    absent (per-field), exactly like every other fail-closed path here.

    Returns (direction, refusal_reason, detector_context). `direction` is
    None whenever `refusal_reason` is set.
    """
    if not isinstance(detector_data, dict):
        return None, "malformed_detector_json", {}

    run_context = detector_data.get("run_context")
    if not isinstance(run_context, dict):
        run_context = {}
    data_date = run_context.get("data_date") or run_context.get("as_of")
    ctx = {"run_context": run_context, "data_date": data_date}

    markets_raw = detector_data.get("markets")
    markets = markets_raw if isinstance(markets_raw, list) else []
    skipped_raw = detector_data.get("skipped")
    skipped_list = skipped_raw if isinstance(skipped_raw, list) else []
    skipped_symbols = {s.get("symbol") for s in skipped_list if isinstance(s, dict)}
    market_row = next(
        (m for m in markets if isinstance(m, dict) and m.get("symbol") == symbol), None
    )

    if market_row is None or symbol in skipped_symbols:
        return None, "detector_missing_symbol", ctx

    if not data_date:
        return None, "detector_missing_data_date", ctx
    try:
        as_of_dt = datetime.strptime(as_of, "%Y-%m-%d").date()
        data_dt = datetime.strptime(data_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return None, "detector_invalid_data_date", ctx
    age_days = (as_of_dt - data_dt).days
    ctx["detector_age_days"] = age_days
    if age_days < 0:
        return None, "detector_future_data_date", ctx
    if age_days > max_age_days:
        return None, "detector_json_stale", ctx

    classification = market_row.get("classification")
    if classification == "NEUTRAL":
        return None, "not_crowded", ctx
    if classification not in ("CROWDED_LONG", "CROWDED_SHORT"):
        return None, "detector_missing_symbol", ctx
    return classification, None, ctx


# --- Events JSON validation ---------------------------------------------------

VALID_EXPECTED_IMPACTS = {"BULLISH", "BEARISH"}

# 4-tier source hierarchy per references/news-failure-patterns.md.
VALID_SOURCE_TIERS = {"primary", "official", "wire", "portal"}


def validate_events(
    events_raw: Any, as_of: str, window_days: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate structural completeness and window membership. An event
    missing source_url / expected_impact / a parsable event_time, or
    outside [as_of - window_days, as_of], is moved to dropped_events[] with
    a reason -- never silently ignored. Returns (valid_events, dropped).

    `events_raw` is untrusted, parsed JSON -- items that aren't dicts (e.g.
    `{"events": [1, 2, 3]}`) are dropped individually with reason
    `malformed_event_item` rather than crashing; `events_raw` not being a
    list at all is a caller-level (main()) concern, not this function's
    (see the `malformed_events_json` top-level check in main()).

    An unrecognized `source_tier` (not one of the 4-tier hierarchy) does
    NOT affect the verdict math, so the event is kept -- but flagged with
    `source_tier_invalid: True` rather than silently treated as valid.
    """
    as_of_dt = datetime.strptime(as_of, "%Y-%m-%d").date()
    window_start = as_of_dt - timedelta(days=window_days)

    valid: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for event in events_raw:
        if not isinstance(event, dict):
            dropped.append({"event_id": "?", "reason": "malformed_event_item"})
            continue

        event_id = event.get("event_id", "?")

        if not event.get("source_url"):
            dropped.append({"event_id": event_id, "reason": "missing_source_url"})
            continue
        if event.get("expected_impact") not in VALID_EXPECTED_IMPACTS:
            dropped.append({"event_id": event_id, "reason": "missing_expected_impact"})
            continue

        event_time = event.get("event_time")
        try:
            dt = datetime.fromisoformat(event_time) if event_time else None
        except (TypeError, ValueError):
            dt = None
        if dt is None or dt.tzinfo is None:
            dropped.append({"event_id": event_id, "reason": "unparsable_event_time"})
            continue

        event_date = dt.date()
        if not (window_start <= event_date <= as_of_dt):
            dropped.append({"event_id": event_id, "reason": "outside_window"})
            continue

        if event.get("source_tier") not in VALID_SOURCE_TIERS:
            event = {**event, "source_tier_invalid": True}
        valid.append(event)

    return valid, dropped


# --- Per-event price computation glue ----------------------------------------


def build_event_record(
    event: dict[str, Any], series: list[tuple[str, float]], direction: str
) -> dict[str, Any]:
    """Combine reaction_math primitives into one evidence record for a
    single event. `usable=False` (+ `reason`) when any required piece
    (effective date, both return horizons, daily_stdev) is unavailable --
    the caller drops such events with the given reason rather than feeding
    partial data into the verdict."""
    event_id = event.get("event_id", "?")
    trading_dates = [d for d, _ in series]

    try:
        effective_date = compute_effective_date(event["event_time"], trading_dates)
    except (ValueError, KeyError) as exc:
        return {"event_id": event_id, "usable": False, "reason": f"effective_date_error: {exc}"}

    if effective_date is None:
        return {"event_id": event_id, "usable": False, "reason": "no_trading_day_on_or_after_event"}

    returns = compute_returns(series, effective_date)
    if returns["return_1d"] is None or returns["return_3d"] is None:
        return {"event_id": event_id, "usable": False, "reason": "insufficient_price_window"}

    daily_stdev = compute_daily_stdev(series, effective_date)
    if daily_stdev is None:
        return {"event_id": event_id, "usable": False, "reason": "insufficient_stdev_history"}

    zscore_1d = compute_zscore_1d(returns["return_1d"], daily_stdev)
    zscore_3d = compute_zscore_3d(returns["return_3d"], daily_stdev)
    adjusted_z3 = direction_adjusted_zscore(zscore_3d, direction)
    reaction = classify_reaction(adjusted_z3) if adjusted_z3 is not None else None

    return {
        "event_id": event_id,
        "usable": True,
        "reason": None,
        "effective_date": effective_date,
        "effective_date_index": find_date_index(series, effective_date),
        "return_1d": returns["return_1d"],
        "return_3d": returns["return_3d"],
        "daily_stdev": daily_stdev,
        "zscore_1d": zscore_1d,
        "zscore_3d": zscore_3d,
        "zscore_3d_adjusted": adjusted_z3,
        "reaction": reaction,
    }


# --- Report assembly -----------------------------------------------------


def build_run_context(
    price_symbol: str | None,
    price_source: str | None,
    proxy_used: bool,
    inverted: bool,
    window_days: int,
    min_events: int,
    z_threshold: float,
    drift_z: float,
    as_of: str,
    detector_json: str | None,
    detector_age_days: int | None,
) -> dict[str, Any]:
    return {
        "price_symbol": price_symbol,
        "price_source": price_source,
        "proxy_used": proxy_used,
        "inverted": inverted,
        "window_days": window_days,
        "min_events": min_events,
        "z_threshold": z_threshold,
        "drift_z": drift_z,
        "thresholds_doc": "references/news-failure-patterns.md#verdict-thresholds",
        "as_of": as_of,
        "detector_json": detector_json,
        "detector_age_days": detector_age_days,
    }


def generate_json_report(output: dict[str, Any], output_path: str) -> None:
    Path(output_path).write_text(json.dumps(output, indent=2, sort_keys=False), encoding="utf-8")


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def generate_markdown_report(output: dict[str, Any], output_path: str) -> None:
    run_context = output.get("run_context", {})
    aggregate = output.get("aggregate", {})
    evidence = output.get("evidence", [])
    dropped = output.get("dropped_events", [])
    clusters = output.get("clusters", [])

    lines = [
        "# News Reaction Failure Report",
        "",
        f"Symbol: {output.get('symbol')}",
        f"Direction: `{output.get('direction')}`  (expected: {output.get('expected_direction')})",
        f"As-of date: {run_context.get('as_of')}",
        f"Price source: `{run_context.get('price_symbol')}` "
        f"({run_context.get('price_source')}, proxy_used={run_context.get('proxy_used')})",
        "",
        "## Verdict",
        "",
        f"**{output.get('verdict')}** (confidence: {output.get('confidence')})",
        f"Actual reaction: **{output.get('actual_reaction')}**",
        f"Relevant events used: {output.get('relevant_events_used')}",
        "",
        "## Aggregate Statistics",
        "",
        f"- mean_z3: {_fmt(aggregate.get('mean_z3'))}",
        f"- drift_stat: {_fmt(aggregate.get('drift_stat'))}",
        f"- responded_ratio: {_fmt(aggregate.get('responded_ratio'))}",
        "",
        "## Evidence",
        "",
    ]
    if evidence:
        lines += [
            "| Event | Date | Impact | Return 1d/3d | z1d/z3d | Reaction | Source |",
            "|---|---|---|---|---|---|---|",
        ]
        for e in evidence:
            tier_label = e.get("source_tier") or "source"
            if e.get("source_tier_invalid"):
                tier_label = f"{tier_label}*"
            lines.append(
                f"| {e.get('event')} | {e.get('effective_date')} | {e.get('expected_impact')} | "
                f"{_fmt(e.get('return_1d'))}% / {_fmt(e.get('return_3d'))}% | "
                f"{_fmt(e.get('zscore_1d'))} / {_fmt(e.get('zscore_3d'))} | "
                f"{e.get('reaction')} | [{tier_label}]({e.get('source_url')}) |"
            )
        if any(e.get("source_tier_invalid") for e in evidence):
            lines.append("")
            lines.append(
                "\\* source_tier not in {primary, official, wire, portal} -- flagged, "
                "not excluded (tier doesn't affect the verdict math)."
            )
    else:
        lines.append("None.")

    clustered = [c for c in clusters if len(c.get("cluster_members", [])) > 1]
    if clustered:
        lines += [
            "",
            "## Clustered Events",
            "",
            "Overlapping-window events collapsed into one cluster for the verdict "
            "(independence guard). Each cluster's own z3 -- the earliest member's "
            "window z3, not an average -- is what drives drift_stat; other members "
            "are shown for transparency only.",
            "",
            "| Cluster Date | Cluster z3 (used) | Members (event_id: z3) |",
            "|---|---|---|",
        ]
        for c in clustered:
            members_str = ", ".join(
                f"{m['event_id']}: {_fmt(m.get('zscore_3d_adjusted'))}"
                for m in c.get("cluster_members", [])
            )
            lines.append(
                f"| {c.get('effective_date')} | {_fmt(c.get('zscore_3d_adjusted'))} | {members_str} |"
            )

    lines += ["", "## Dropped Events", ""]
    if dropped:
        lines += ["| Event ID | Reason |", "|---|---|"]
        for d in dropped:
            lines.append(f"| {d.get('event_id')} | {d.get('reason')} |")
    else:
        lines.append("None.")

    if run_context.get("proxy_used"):
        lines += [
            "",
            "## Proxy Data Caveat",
            "",
            f"Price data for this analysis used an ETF proxy (`{run_context.get('price_symbol')}`) "
            "because the underlying futures symbol had no usable price feed on this key. ETF "
            "proxies carry tracking error, expense drag, and roll-timing differences versus the "
            "actual futures contract -- treat the reaction-direction read as approximate.",
        ]

    lines += [
        "",
        "## Methodology",
        "",
        "Verdict is a drift-significance test on direction-adjusted 3-day z-scores of "
        "relevant (expected_impact-matching) events, clustered to guard independence. "
        "See `references/news-failure-patterns.md` for the full methodology and "
        "`references/price-source-map.md` for the price-source fallback chain used. "
        "This is a crowding-confirmation screen only -- not a standalone trade signal.",
        "",
    ]

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


# --- CLI -----------------------------------------------------------------


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Judge whether a market failed to react to news favorable to the "
        "crowded side (Jason Shapiro contrarian process, step 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", required=True, help="COT symbol, e.g. ES, GC, B6")
    parser.add_argument("--price-symbol", help="Override the price-source map (skips the chain)")
    parser.add_argument("--direction", choices=["CROWDED_LONG", "CROWDED_SHORT"])
    parser.add_argument("--detector-json", help="cot-contrarian-detector JSON report path")
    parser.add_argument("--max-detector-age-days", type=int, default=MAX_DETECTOR_AGE_DAYS_DEFAULT)
    parser.add_argument("--events-json", help="Curated events JSON (required for a verdict)")
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS_DEFAULT)
    parser.add_argument("--min-events", type=int, default=MIN_EVENTS_DEFAULT)
    parser.add_argument("--z-threshold", type=float, default=Z_THRESHOLD_DEFAULT)
    parser.add_argument("--drift-z", type=float, default=DRIFT_Z_DEFAULT)
    parser.add_argument("--as-of", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--output-dir", default="reports/")
    parser.add_argument("--format", choices=["json", "md", "both"], default="both")
    parser.add_argument(
        "--api-key", help="FMP API key (overrides FMP_API_KEY environment variable)"
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    return parser.parse_args()


def _insufficient_evidence_output(
    symbol: str, direction: str | None, reason: str, args: argparse.Namespace, run_context: dict
) -> dict[str, Any]:
    expected_direction = expected_direction_for(direction) if direction else None
    return {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "symbol": symbol,
        "direction": direction,
        "expected_direction": expected_direction,
        "actual_reaction": "NO_DATA",
        "verdict": "INSUFFICIENT_EVIDENCE",
        "confidence": "MEDIUM",
        "relevant_events_used": 0,
        "aggregate": {"mean_z3": None, "drift_stat": None, "responded_ratio": None},
        "evidence": [],
        "clusters": [],
        "dropped_events": [],
        "verdict_reason": reason,
        "run_context": run_context,
    }


def main() -> None:
    args = parse_arguments()
    print("=" * 72)
    print("News Reaction Failure Analyzer")
    print("=" * 72)

    symbol = args.symbol.upper()
    os.makedirs(args.output_dir, exist_ok=True)
    json_path = os.path.join(args.output_dir, f"nrf_{symbol}_{args.as_of}.json")
    md_path = os.path.join(args.output_dir, f"nrf_{symbol}_{args.as_of}.md")

    def emit(output: dict[str, Any]) -> None:
        if args.format in ("json", "both"):
            generate_json_report(output, json_path)
        if args.format in ("md", "both"):
            generate_markdown_report(output, md_path)
        print(f"Verdict: {output['verdict']} (confidence: {output['confidence']})")
        if args.format in ("json", "both"):
            print(f"  JSON Report: {json_path}")
        if args.format in ("md", "both"):
            print(f"  Markdown Report: {md_path}")

    # --- Resolve direction ---------------------------------------------
    direction = args.direction
    detector_age_days = None
    if direction is None and args.detector_json:
        detector_data, error = load_json_file(args.detector_json)
        if error:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)
        direction, reason, ctx = resolve_direction_from_detector(
            detector_data, symbol, args.as_of, args.max_detector_age_days
        )
        detector_age_days = ctx.get("detector_age_days")
        if direction is None:
            run_context = build_run_context(
                None,
                None,
                False,
                False,
                args.window_days,
                args.min_events,
                args.z_threshold,
                args.drift_z,
                args.as_of,
                args.detector_json,
                detector_age_days,
            )
            emit(_insufficient_evidence_output(symbol, None, reason, args, run_context))
            sys.exit(0)

    if direction is None:
        run_context = build_run_context(
            None,
            None,
            False,
            False,
            args.window_days,
            args.min_events,
            args.z_threshold,
            args.drift_z,
            args.as_of,
            args.detector_json,
            None,
        )
        emit(
            _insufficient_evidence_output(symbol, None, "no_direction_provided", args, run_context)
        )
        sys.exit(0)

    # --- Events JSON (required for a verdict) ---------------------------
    if not args.events_json:
        run_context = build_run_context(
            None,
            None,
            False,
            False,
            args.window_days,
            args.min_events,
            args.z_threshold,
            args.drift_z,
            args.as_of,
            args.detector_json,
            detector_age_days,
        )
        emit(
            _insufficient_evidence_output(
                symbol, direction, "no_events_provided", args, run_context
            )
        )
        sys.exit(0)

    events_data, error = load_json_file(args.events_json)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    # events_data is untrusted, parsed JSON: valid JSON but the wrong shape
    # (top-level list/string/null, or "events" not a list at all) must
    # never crash -- degrade to malformed_events_json, exactly like every
    # other fail-closed path here. Per-item shape problems (an item in a
    # valid list not being a dict) are handled inside validate_events()
    # instead, as individual dropped_events entries.
    if not isinstance(events_data, dict) or not isinstance(events_data.get("events"), list):
        run_context = build_run_context(
            None,
            None,
            False,
            False,
            args.window_days,
            args.min_events,
            args.z_threshold,
            args.drift_z,
            args.as_of,
            args.detector_json,
            detector_age_days,
        )
        emit(
            _insufficient_evidence_output(
                symbol, direction, "malformed_events_json", args, run_context
            )
        )
        sys.exit(0)
    events_raw = events_data["events"]
    valid_events, dropped_events = validate_events(events_raw, args.as_of, args.window_days)

    # --- Price data (fallback chain) ------------------------------------
    api_key = get_api_key(args.api_key)
    if not api_key:
        print("Error: FMP API key is required. Set FMP_API_KEY or use --api-key.", file=sys.stderr)
        sys.exit(1)

    if args.price_symbol:
        chain = [(args.price_symbol, "explicit_override", False)]
    else:
        chain = PRICE_SOURCE_CHAINS.get(symbol)
        if not chain:
            run_context = build_run_context(
                None,
                None,
                False,
                False,
                args.window_days,
                args.min_events,
                args.z_threshold,
                args.drift_z,
                args.as_of,
                args.detector_json,
                detector_age_days,
            )
            emit(
                _insufficient_evidence_output(
                    symbol, direction, "no_price_source", args, run_context
                )
            )
            sys.exit(0)

    client = PriceClient(api_key=api_key, sleep_seconds=args.sleep_seconds)
    as_of_date = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    from_date = (as_of_date - timedelta(days=PRICE_FETCH_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    to_date = (as_of_date + timedelta(days=PRICE_FETCH_LOOKAHEAD_DAYS)).strftime("%Y-%m-%d")
    price_result = fetch_price_series(client, chain, from_date, to_date, as_of=args.as_of)

    run_context = build_run_context(
        price_result["price_symbol"],
        price_result.get("source_kind"),
        price_result["proxy_used"],
        price_result["inverted"],
        args.window_days,
        args.min_events,
        args.z_threshold,
        args.drift_z,
        args.as_of,
        args.detector_json,
        detector_age_days,
    )

    if price_result["error"]:
        emit(_insufficient_evidence_output(symbol, direction, "no_price_source", args, run_context))
        sys.exit(0)

    # --- Build evidence, filter relevant, cluster + verdict --------------
    expected_direction = expected_direction_for(direction)
    all_evidence = []
    usable_relevant = []
    for event in valid_events:
        record = build_event_record(event, price_result["series"], direction)
        is_relevant = event.get("expected_impact") == expected_direction
        if not record["usable"]:
            dropped_events.append(
                {"event_id": event.get("event_id", "?"), "reason": record["reason"]}
            )
            continue
        all_evidence.append({**event, **record, "is_relevant": is_relevant})
        if is_relevant:
            usable_relevant.append(record | {"event_id": event.get("event_id", "?")})

    if not all_evidence and not usable_relevant:
        emit(
            _insufficient_evidence_output(symbol, direction, "no_usable_events", args, run_context)
        )
        sys.exit(0)

    result = synthesize_result(
        usable_relevant, direction, args.min_events, args.drift_z, args.z_threshold
    )

    evidence_out = [
        {
            "event_id": e.get("event_id"),
            "event": e.get("event"),
            "source_url": e.get("source_url"),
            "event_time": e.get("event_time"),
            "expected_impact": e.get("expected_impact"),
            "source_tier": e.get("source_tier"),
            "source_tier_invalid": e.get("source_tier_invalid", False),
            "effective_date": e.get("effective_date"),
            "return_1d": round(e["return_1d"] * 100, 2) if e.get("return_1d") is not None else None,
            "return_3d": round(e["return_3d"] * 100, 2) if e.get("return_3d") is not None else None,
            "zscore_1d": round(e["zscore_1d"], 2) if e.get("zscore_1d") is not None else None,
            "zscore_3d": round(e["zscore_3d"], 2) if e.get("zscore_3d") is not None else None,
            "reaction": e.get("reaction"),
            "is_relevant": e.get("is_relevant"),
        }
        for e in all_evidence
    ]

    # Cluster transparency: member events (including each one's own,
    # never-averaged z3) are always shown, even though only the earliest
    # member's z3 drives drift_stat (see reaction_math.cluster_events()).
    clusters_out = [
        {
            "effective_date": c["effective_date"],
            "zscore_3d_adjusted": round(c["zscore_3d_adjusted"], 2),
            "cluster_members": [
                {"event_id": m["event_id"], "zscore_3d_adjusted": round(m["zscore_3d_adjusted"], 2)}
                for m in c["cluster_members"]
            ],
        }
        for c in result["clusters"]
    ]

    output = {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "symbol": symbol,
        "direction": direction,
        "expected_direction": expected_direction,
        "actual_reaction": result["actual_reaction"],
        "verdict": result["verdict"],
        "confidence": result["confidence"],
        "relevant_events_used": result["n"],
        "aggregate": {
            "mean_z3": round(result["mean_z3"], 2) if result["mean_z3"] is not None else None,
            "drift_stat": round(result["drift_stat"], 2)
            if result["drift_stat"] is not None
            else None,
            "responded_ratio": result["responded_ratio"],
        },
        "evidence": evidence_out,
        "clusters": clusters_out,
        "dropped_events": dropped_events,
        "verdict_reason": result.get("verdict_reason"),
        "run_context": run_context,
    }
    emit(output)


if __name__ == "__main__":
    main()
