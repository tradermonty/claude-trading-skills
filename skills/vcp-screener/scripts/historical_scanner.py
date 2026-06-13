#!/usr/bin/env python3
"""Historical VCP Scanner — walk a single ticker's price history and detect
every VCP that formed along the way.

Companion to the cross-sectional ``screen_vcp.py`` pipeline. Unlike that
pipeline (which answers "which S&P 500 names are setting up *now*"), this
scanner answers "which VCPs has this one ticker formed in the past N years,
and what happened after each one?"

Pipeline:
  1. Fetch a long history (e.g. ~5 years) once.
  2. Walk the as-of cursor backwards in time at ``stride_days`` (default 5).
  3. At each cursor position, synthesize a quote (no future-bar peeking) and
     call ``analyze_stock(..., as_of_offset=cursor)``.
  4. For every ``valid_vcp=True`` detection, compute the forward outcome
     (breakout / stop_hit / timeout) over the next ``outcome_days`` bars.
  5. Deduplicate by (T1_high_date, last_low_date, round(pivot, 2)) so the same
     pattern isn't reported repeatedly as the cursor ages.
  6. Return detections in chronological order (oldest first).
"""

from __future__ import annotations

import os
import re
import sys

# Allow imports from the scripts/ directory when invoked as a module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import screen_vcp  # noqa: E402  — bound at module load so tests can monkeypatch
                   # `historical_scanner.screen_vcp.analyze_stock` deterministically.
from calculators.forward_outcome import calculate_forward_outcome  # noqa: E402


_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


def sanitize_ticker(symbol: str) -> str:
    """Validate that ``symbol`` matches an FMP-style ticker (letters, digits,
    dot, hyphen; starts with a letter; up to 12 chars). Returns the uppercased
    symbol. Raises ``ValueError`` on anything that could traverse a path or
    inject characters into a filename.
    """
    sym = (symbol or "").upper().strip()
    if not _TICKER_RE.match(sym):
        raise ValueError(
            f"Invalid ticker symbol: {symbol!r}. Must match {_TICKER_RE.pattern}"
        )
    return sym


def build_quote_from_history(
    historical: list[dict],
    as_of_offset: int,
    year_window_bars: int = 252,
) -> dict:
    """Synthesize a quote dict compatible with ``calculate_trend_template``
    using only bars at or older than ``historical[as_of_offset]``.

    Contract: no bar with MRF index < ``as_of_offset`` may influence any
    returned field. (Those bars are "future" relative to the as-of date.)

    Returns:
        Dict with at minimum ``price``, ``yearHigh``, ``yearLow``,
        ``avgVolume``, ``marketCap`` (defaulted to 0 — historical share count
        is not retrievable from OHLCV).
    """
    if not historical or as_of_offset < 0 or as_of_offset >= len(historical):
        return {"price": 0, "yearHigh": 0, "yearLow": 0, "avgVolume": 0, "marketCap": 0}

    as_of_bar = historical[as_of_offset]
    window = historical[as_of_offset : as_of_offset + year_window_bars]
    if not window:
        return {"price": 0, "yearHigh": 0, "yearLow": 0, "avgVolume": 0, "marketCap": 0}

    year_high = max(d.get("high", 0) for d in window)
    year_low = min(d.get("low", 0) for d in window if d.get("low", 0) > 0)
    vol_window = historical[as_of_offset : as_of_offset + 50]
    avg_volume = (
        int(sum(d.get("volume", 0) for d in vol_window) / len(vol_window))
        if vol_window
        else 0
    )

    return {
        "price": as_of_bar.get("close", 0),
        "yearHigh": year_high,
        "yearLow": year_low,
        "avgVolume": avg_volume,
        "marketCap": 0,  # historical share count not available; deliberately stubbed.
    }


def scan_history(
    symbol: str,
    historical: list[dict],
    sp500_history: list[dict],
    *,
    sector: str = "Unknown",
    company_name: str = "",
    stride_days: int = 5,
    outcome_days: int = 60,
    lookback_days: int = 120,
    analyzer_kwargs: dict | None = None,
) -> list[dict]:
    """Walk ``historical`` from oldest scannable bar to ``outcome_days`` ago,
    detect VCPs, deduplicate, and attach forward outcomes.

    Args:
        symbol: Ticker symbol (passed through to ``analyze_stock``).
        historical: Most-recent-first OHLCV bars (typically 5+ years).
        sp500_history: Most-recent-first SPY OHLCV, aligned by index with
            ``historical``. Sliced identically to keep RS comparisons fair.
        sector / company_name: Metadata for output.
        stride_days: Step size for the as-of cursor in trading days (default 5).
        outcome_days: Forward window for outcome evaluation (default 60).
        lookback_days: Window passed to the VCP calculator (default 120).
        analyzer_kwargs: Extra kwargs forwarded to ``analyze_stock`` (e.g.
            ``min_contractions``, ``t1_depth_min``, etc.).

    Returns:
        List of detection dicts (chronological), each shaped as the
        ``analyze_stock`` return value plus ``as_of_date`` and
        ``forward_outcome`` fields.
    """
    if not historical or len(historical) < lookback_days + 30:
        return []

    analyzer_kwargs = dict(analyzer_kwargs or {})
    analyzer_kwargs.pop("as_of_offset", None)  # caller cannot override the cursor

    # Largest scannable offset is len(historical) - lookback_days; smaller
    # offsets get less forward data (outcomes resolve via timeout /
    # insufficient_data branches). range() with a negative step already
    # yields descending offsets — no extra sort needed.
    max_offset = len(historical) - lookback_days
    if max_offset <= 0:
        return []
    offsets = range(max_offset, -1, -stride_days)

    seen: set[tuple[str, str, float]] = set()
    detections: list[dict] = []

    for offset in offsets:
        quote = build_quote_from_history(historical, offset)
        if quote.get("price", 0) <= 0:
            continue

        # Looked up via the screen_vcp module attribute so tests can monkeypatch
        # historical_scanner.screen_vcp.analyze_stock to inject fake results.
        result = screen_vcp.analyze_stock(
            symbol,
            historical,
            quote,
            sp500_history,
            sector=sector,
            company_name=company_name,
            lookback_days=lookback_days,
            as_of_offset=offset,
            **analyzer_kwargs,
        )
        if result is None or not result.get("valid_vcp"):
            continue

        contractions = result.get("vcp_pattern", {}).get("contractions") or []
        pivot = result.get("vcp_pattern", {}).get("pivot_price")
        if not contractions or pivot is None:
            continue

        # Dedup key: identify by the first contraction's start and the last
        # contraction's bottom, plus pivot (rounded). Fall back to chronological
        # index strings if dates are missing so two unrelated patterns don't
        # collide on the empty-string default.
        first_c = contractions[0]
        last_c = contractions[-1]
        key = (
            first_c.get("high_date") or f"idx:{first_c.get('high_idx', '')}",
            last_c.get("low_date") or f"idx:{last_c.get('low_idx', '')}",
            round(float(pivot), 2),
        )
        if key in seen:
            continue
        seen.add(key)

        outcome = calculate_forward_outcome(
            historical,
            as_of_offset=offset,
            pivot_price=float(pivot),
            stop_price=contractions[-1].get("low_price"),
            max_window_days=outcome_days,
        )

        result["as_of_date"] = historical[offset].get("date")
        result["as_of_offset"] = offset
        result["forward_outcome"] = outcome
        detections.append(result)

    # Sort chronologically oldest -> newest by as_of_date.
    detections.sort(key=lambda r: r.get("as_of_date") or "")
    return detections
