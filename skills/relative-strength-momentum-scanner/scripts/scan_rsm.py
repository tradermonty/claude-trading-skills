#!/usr/bin/env python3
"""Relative Strength Momentum Scanner.

Pure-function screener: computes IBD-style RS scores from local OHLCV bars
and emits a Candidate JSON + markdown report.

Usage:
    python3 scan_rsm.py \
        --bars-dir data/bars/ \
        --output-dir reports/

    python3 scan_rsm.py \
        --tickers-file universes/tech200.txt \
        --bars-dir data/bars/ \
        --benchmark QQQ \
        --as-of 2026-03-31 \
        --output-dir reports/replay_screens/
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_UNIVERSE = Path(__file__).resolve().parents[1] / "references" / "sp500.txt"
DEFAULT_SECTOR_MAP = REPO_ROOT / "config" / "sector_map.yaml"


# ---------- Bar loading ----------


def load_bars(bars_dir: Path, ticker: str) -> list[dict[str, Any]]:
    """Return OHLCV rows sorted ascending by date."""
    path = bars_dir / f"{ticker.upper()}.csv"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append(
                    {
                        "date": dt.date.fromisoformat(r["date"]),
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": float(r.get("volume", 0)),
                    }
                )
            except (KeyError, ValueError):
                continue
    rows.sort(key=lambda x: x["date"])
    return rows


def load_universe(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text().splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        out.append(t.upper())
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in out:
        if t not in seen:
            unique.append(t)
            seen.add(t)
    return unique


def load_sector_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).upper(): str(v) for k, v in data.items()}


# ---------- Core metrics ----------


def trim_to_as_of(rows: list[dict[str, Any]], as_of: dt.date | None) -> list[dict[str, Any]]:
    if as_of is None:
        return rows
    return [r for r in rows if r["date"] <= as_of]


def return_over_n(rows: list[dict[str, Any]], n: int) -> float | None:
    """Percent return from N trading days ago to latest row.

    Requires at least N+1 rows (need both endpoints).
    """
    if len(rows) <= n:
        return None
    start = rows[-(n + 1)]["close"]
    end = rows[-1]["close"]
    if start <= 0:
        return None
    return (end - start) / start * 100.0


def moving_average(rows: list[dict[str, Any]], n: int) -> float | None:
    if len(rows) < n:
        return None
    return sum(r["close"] for r in rows[-n:]) / n


def high_over_n(rows: list[dict[str, Any]], n: int) -> float | None:
    if len(rows) < 1:
        return None
    subset = rows[-n:] if len(rows) >= n else rows
    return max(r["high"] for r in subset)


def swing_low_over_n(rows: list[dict[str, Any]], n: int) -> float | None:
    if len(rows) < 1:
        return None
    subset = rows[-n:] if len(rows) >= n else rows
    return min(r["low"] for r in subset)


def composite_rs(rel_63: float, rel_126: float, rel_189: float, rel_252: float) -> float:
    """IBD-style weighted composite — raw score, not yet percentile-ranked."""
    return 0.40 * rel_63 + 0.20 * rel_126 + 0.20 * rel_189 + 0.20 * rel_252


def percentile_rank(values: list[float]) -> dict[int, int]:
    """Return {index: rank_1_to_99} where higher value → higher rank."""
    if not values:
        return {}
    n = len(values)
    # Sort indices by value ascending
    order = sorted(range(n), key=lambda i: values[i])
    ranks: dict[int, int] = {}
    for rank_pos, idx in enumerate(order):
        # Percentile: 1..99 scaled
        pct = rank_pos / max(n - 1, 1)  # 0.0..1.0
        ranks[idx] = max(1, min(99, int(round(1 + pct * 98))))
    return ranks


# ---------- Gating + signal ----------


def passes_trend_filter(
    close: float, ma50: float | None, ma200: float | None, high_52w: float | None
) -> bool:
    if ma50 is None or ma200 is None or high_52w is None:
        return False
    if not (close > ma50 and close > ma200):
        return False
    if not (ma50 > ma200):
        return False
    # Within 10% of 52-week high (leadership gate)
    if close < 0.90 * high_52w:
        return False
    return True


def is_pullback_ready(close: float, ma20: float | None, ma50: float | None) -> bool:
    if ma20 is None or ma50 is None:
        return False
    if ma20 <= ma50:
        return False
    # Within 2% of MA20 (pullback trigger)
    return abs(close - ma20) / ma20 <= 0.02


# ---------- Per-ticker compute ----------


def compute_ticker(
    rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Compute all metrics for one ticker. Returns None if insufficient data."""
    if len(rows) < 252:
        return None

    latest = rows[-1]
    close = latest["close"]

    ret_63 = return_over_n(rows, 63)
    ret_126 = return_over_n(rows, 126)
    ret_189 = return_over_n(rows, 189)
    ret_252 = return_over_n(rows, 252)
    if None in (ret_63, ret_126, ret_189, ret_252):
        return None

    bench_63 = return_over_n(benchmark_rows, 63) or 0.0
    bench_126 = return_over_n(benchmark_rows, 126) or 0.0
    bench_189 = return_over_n(benchmark_rows, 189) or 0.0
    bench_252 = return_over_n(benchmark_rows, 252) or 0.0

    rel_63 = ret_63 - bench_63  # type: ignore[operator]
    rel_126 = ret_126 - bench_126  # type: ignore[operator]
    rel_189 = ret_189 - bench_189  # type: ignore[operator]
    rel_252 = ret_252 - bench_252  # type: ignore[operator]

    ma20 = moving_average(rows, 20)
    ma50 = moving_average(rows, 50)
    ma200 = moving_average(rows, 200)
    high_52w = high_over_n(rows, 252)
    swing_20 = swing_low_over_n(rows, 20)

    return {
        "close": close,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "high_52w": high_52w,
        "swing_low_20d": swing_20,
        "ret_63": ret_63,
        "ret_126": ret_126,
        "ret_189": ret_189,
        "ret_252": ret_252,
        "rel_63": rel_63,
        "rel_126": rel_126,
        "rel_189": rel_189,
        "rel_252": rel_252,
        "composite_raw": composite_rs(rel_63, rel_126, rel_189, rel_252),
        "as_of": latest["date"].isoformat(),
    }


# ---------- Candidate packaging ----------


def build_candidate(
    ticker: str, metrics: dict[str, Any], rs_score: int, sector: str | None
) -> dict[str, Any]:
    close = metrics["close"]
    ma50 = metrics["ma50"]
    swing = metrics["swing_low_20d"]
    # Stop = 99% of whichever is higher (closer to price) of MA50 or swing low
    # We want a tight stop just below recent support.
    stop_base = max(ma50, swing) if ma50 and swing else (ma50 or swing)
    stop_loss = round(stop_base * 0.99, 4) if stop_base else round(close * 0.92, 4)
    entry_price = round(close, 4)
    risk = entry_price - stop_loss
    target = round(entry_price + 2 * risk, 4) if risk > 0 else round(entry_price * 1.15, 4)

    trend_ok = passes_trend_filter(close, ma50, metrics["ma200"], metrics["high_52w"])
    pullback_ok = is_pullback_ready(close, metrics["ma20"], ma50)
    if trend_ok and pullback_ok:
        status = "entry_ready"
    elif trend_ok:
        status = "watchlist"
    else:
        status = "filtered"

    # Distance to 52w high, expressed as R-multiples to target
    r_to_high = None
    if risk > 0 and metrics["high_52w"]:
        r_to_high = round((metrics["high_52w"] - entry_price) / risk, 2)

    confidence = 0.5 + 0.3 * (rs_score / 99.0)  # 0.5 .. 0.8
    if pullback_ok:
        confidence += 0.05
    confidence = round(min(confidence, 0.9), 3)

    return {
        "ticker": ticker,
        "rs_score": rs_score,
        "rel_ret_63": round(metrics["rel_63"], 2),
        "rel_ret_126": round(metrics["rel_126"], 2),
        "rel_ret_189": round(metrics["rel_189"], 2),
        "rel_ret_252": round(metrics["rel_252"], 2),
        "ma20": round(metrics["ma20"], 4) if metrics["ma20"] else None,
        "ma50": round(ma50, 4) if ma50 else None,
        "ma200": round(metrics["ma200"], 4) if metrics["ma200"] else None,
        "high_52w": round(metrics["high_52w"], 4) if metrics["high_52w"] else None,
        "close": entry_price,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "r_multiple_to_52w_high": r_to_high,
        "status": status,
        "sector": sector,
        "side": "buy",
        "entry_type": "market",
        "primary_screener": "rsm-scanner",
        "supporting_screeners": [],
        "strategy_score": rs_score,
        "confidence": confidence,
        "notes": f"RS {rs_score} leader" + (" at MA20 pullback" if pullback_ok else " (watchlist)"),
    }


# ---------- Driver ----------


def run_scan(
    tickers: list[str],
    bars_dir: Path,
    benchmark: str,
    as_of: dt.date | None,
    sector_map: dict[str, str],
) -> dict[str, Any]:
    bench_rows = trim_to_as_of(load_bars(bars_dir, benchmark), as_of)
    if len(bench_rows) < 252:
        raise SystemExit(f"error: benchmark {benchmark} has {len(bench_rows)} bars, need >= 252")

    per_ticker: list[tuple[str, dict[str, Any]]] = []
    for tkr in tickers:
        rows = trim_to_as_of(load_bars(bars_dir, tkr), as_of)
        m = compute_ticker(rows, bench_rows)
        if m is None:
            continue
        per_ticker.append((tkr, m))

    # Percentile rank composite across surviving universe
    composites = [m["composite_raw"] for _, m in per_ticker]
    ranks = percentile_rank(composites)

    candidates: list[dict[str, Any]] = []
    for idx, (tkr, m) in enumerate(per_ticker):
        rs_score = ranks.get(idx, 1)
        cand = build_candidate(tkr, m, rs_score, sector_map.get(tkr))
        if cand["status"] == "filtered":
            continue
        candidates.append(cand)

    candidates.sort(key=lambda c: (-c["rs_score"], c["ticker"]))

    as_of_str = (as_of or (bench_rows[-1]["date"] if bench_rows else dt.date.today())).isoformat()

    return {
        "as_of": as_of_str,
        "benchmark": benchmark,
        "universe_size": len(tickers),
        "evaluated": len(per_ticker),
        "candidates_count": len(candidates),
        "entry_ready_count": sum(1 for c in candidates if c["status"] == "entry_ready"),
        "watchlist_count": sum(1 for c in candidates if c["status"] == "watchlist"),
        "candidates": candidates,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Relative Strength Momentum Scan — {payload['as_of']}",
        "",
        f"**Benchmark:** {payload['benchmark']}",
        f"**Universe:** {payload['universe_size']} tickers ({payload['evaluated']} with ≥252 bars)",
        f"**Entry-ready:** {payload['entry_ready_count']}  "
        f"| **Watchlist:** {payload['watchlist_count']}",
        "",
        "## Top Candidates",
        "",
        "| Rank | Ticker | RS | Status | Close | Entry | Stop | Target | Sector |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(payload["candidates"][:50], 1):
        lines.append(
            f"| {i} | {c['ticker']} | {c['rs_score']} | {c['status']} "
            f"| ${c['close']:.2f} | ${c['entry_price']:.2f} "
            f"| ${c['stop_loss']:.2f} | ${c['target']:.2f} "
            f"| {c.get('sector') or '—'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bars-dir", type=Path, required=True)
    ap.add_argument("--tickers", default=None, help="Comma-separated ticker list")
    ap.add_argument("--tickers-file", type=Path, default=None)
    ap.add_argument("--benchmark", default="SPY")
    ap.add_argument("--as-of", type=lambda s: dt.date.fromisoformat(s), default=None)
    ap.add_argument("--sector-map", type=Path, default=DEFAULT_SECTOR_MAP)
    ap.add_argument("--output-dir", type=Path, default=REPO_ROOT / "reports")
    args = ap.parse_args()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.tickers_file:
        tickers = load_universe(args.tickers_file)
    else:
        tickers = load_universe(DEFAULT_UNIVERSE)

    if not tickers:
        print("error: no tickers to scan", file=sys.stderr)
        return 2

    sector_map = load_sector_map(args.sector_map)
    payload = run_scan(tickers, args.bars_dir, args.benchmark, args.as_of, sector_map)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tag = payload["as_of"]
    (args.output_dir / f"rsm_scanner_{tag}.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )
    (args.output_dir / f"rsm_scanner_{tag}.md").write_text(render_markdown(payload))

    print(
        f"RSM scan {tag}: evaluated={payload['evaluated']} "
        f"entry_ready={payload['entry_ready_count']} "
        f"watchlist={payload['watchlist_count']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
