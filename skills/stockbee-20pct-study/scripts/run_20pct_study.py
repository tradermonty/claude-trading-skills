#!/usr/bin/env python3
"""
Stockbee 20% Study

Build and maintain a daily +20%/-20% mover event study for US equities.
The script is intentionally research-oriented: it creates study records,
updates forward outcomes, and summarizes cohorts. It never places orders or
outputs broker instructions.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Union

try:  # Optional live-data path.
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None

SCHEMA_VERSION = "1.0"
SKILL_NAME = "stockbee-20pct-study"
DEFAULT_STATE_FILE = "state/stockbee/20pct_study_events.jsonl"
DEFAULT_OUTPUT_DIR = "reports"
DEFAULT_HORIZONS = (1, 3, 5, 10, 20)
DEFAULT_GROUP_BY = (
    "direction,catalyst.label,technical_context.pattern_label,technical_context.close_quality"
)
PCT_EPSILON = 1e-9
BACKFILL_SURVIVORSHIP_BIAS_FLAG = "CURRENT_UNIVERSE_BACKFILL_SURVIVORSHIP_BIAS"
PathLike = Union[str, Path]


@dataclass(frozen=True)
class Bar:
    """Normalized daily OHLCV bar sorted oldest -> newest."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


class ApiCallBudgetExceeded(Exception):
    """Raised when max_api_calls is exhausted."""


class FMPClient:
    """Small FMP client for optional universe and OHLCV retrieval."""

    STABLE_URL = "https://financialmodelingprep.com/stable"
    V3_URL = "https://financialmodelingprep.com/api/v3"
    RATE_LIMIT_DELAY = 0.30

    def __init__(self, api_key: str | None = None, max_api_calls: int = 500):
        if requests is None:
            raise RuntimeError("requests is not installed; use --prices-json or install requests")
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError("FMP API key required. Set FMP_API_KEY or pass --api-key.")
        self.session = requests.Session()
        self.max_api_calls = max_api_calls
        self.api_calls_made = 0
        self.last_call_time = 0.0
        self.cache: dict[str, Any] = {}

    def _get(self, url: str, params: dict[str, Any] | None = None, quiet: bool = False) -> Any:
        if self.api_calls_made >= self.max_api_calls:
            raise ApiCallBudgetExceeded(
                f"API budget exhausted: {self.api_calls_made}/{self.max_api_calls} calls used"
            )
        params = dict(params or {})
        params.setdefault("apikey", self.api_key)
        elapsed = time.time() - self.last_call_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        try:
            response = self.session.get(url, params=params, timeout=30)
            self.last_call_time = time.time()
            self.api_calls_made += 1
            if response.status_code == 200:
                return response.json()
            if not quiet:
                print(
                    f"ERROR: FMP request failed: HTTP {response.status_code} - {response.text[:200]}",
                    file=sys.stderr,
                )
        except Exception as exc:  # pragma: no cover - defensive live-data path
            if not quiet:
                print(f"ERROR: FMP request exception: {exc}", file=sys.stderr)
        return None

    def _stable_then_v3(self, stable_url: str, v3_url: str, params: dict[str, Any]) -> Any:
        stable = self._get(stable_url, params, quiet=True)
        if stable not in (None, [], {}):
            return stable
        return self._get(v3_url, params, quiet=False)

    def get_stock_list(self, limit: int | None = None) -> list[str]:
        cache_key = f"stock_list:{limit}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        params = {
            "exchange": "NASDAQ,NYSE,AMEX",
            "priceMoreThan": 0,
            "limit": max(int(limit or 10000), 10000),
        }
        payload = self._stable_then_v3(
            f"{self.STABLE_URL}/company-screener",
            f"{self.V3_URL}/stock-screener",
            params,
        )
        symbols: list[str] = []
        if isinstance(payload, list):
            for row in payload:
                if not isinstance(row, dict):
                    continue
                symbol = normalize_symbol(row.get("symbol"))
                exchange = str(row.get("exchangeShortName") or row.get("exchange") or "").upper()
                stock_type = str(row.get("type") or "stock").lower()
                price = to_float(row.get("price"), default=0)
                if not symbol:
                    continue
                if row.get("isEtf") or row.get("isFund"):
                    continue
                if exchange and exchange not in {"NASDAQ", "NYSE", "AMEX", "NYSEARCA"}:
                    continue
                if stock_type and stock_type not in {"stock", "common stock", "etf"}:
                    continue
                if price <= 0:
                    continue
                symbols.append(symbol)
        result = sorted(dict.fromkeys(symbols))
        if limit:
            result = result[:limit]
        self.cache[cache_key] = result
        return result

    def get_historical_prices(self, symbol: str, days: int = 320) -> list[dict[str, Any]]:
        symbol = normalize_symbol(symbol)
        cache_key = f"history:{symbol}:{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        today = date.today()
        params = {
            "symbol": symbol,
            "from": (today - timedelta(days=days * 2 + 20)).isoformat(),
            "to": today.isoformat(),
        }
        payload = self._get(f"{self.STABLE_URL}/historical-price-eod/full", params, quiet=True)
        bars = normalize_price_bars(payload, symbol=symbol)
        if not bars:
            payload = self._get(
                f"{self.V3_URL}/historical-price-full/{symbol}", {"timeseries": days}
            )
            bars = normalize_price_bars(payload, symbol=symbol)
        result = [bar_to_dict(bar) for bar in bars[-days:]]
        self.cache[cache_key] = result
        return result

    def stats(self) -> dict[str, Any]:
        return {
            "api_calls_made": self.api_calls_made,
            "max_api_calls": self.max_api_calls,
            "budget_remaining": max(0, self.max_api_calls - self.api_calls_made),
        }


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def ensure_dir(path: PathLike) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def bar_to_dict(bar: Bar) -> dict[str, Any]:
    return {
        "date": bar.date,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def normalize_price_bars(payload: Any, symbol: str | None = None) -> list[Bar]:
    """Normalize common OHLCV shapes into oldest -> newest bars.

    Supported shapes:
    - [{date, open, high, low, close, volume}, ...]
    - {"historical": [...]}
    - {"bars": [...]}
    - FMP stable flat list containing optional symbol fields
    """
    rows: Any
    if isinstance(payload, dict) and "historical" in payload:
        rows = payload.get("historical") or []
    elif isinstance(payload, dict) and "bars" in payload:
        rows = payload.get("bars") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        return []

    bars: list[Bar] = []
    target = normalize_symbol(symbol) if symbol else None
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = (
            normalize_symbol(row.get("symbol") or row.get("ticker"))
            if row.get("symbol") or row.get("ticker")
            else None
        )
        if target and row_symbol and row_symbol != target:
            continue
        raw_date = row.get("date") or row.get("datetime") or row.get("time")
        if not raw_date:
            continue
        try:
            normalized_date = parse_date(str(raw_date)).isoformat()
        except ValueError:
            continue
        open_ = to_float(row.get("open") or row.get("o"))
        high = to_float(row.get("high") or row.get("h"))
        low = to_float(row.get("low") or row.get("l"))
        close = to_float(
            row.get("close") or row.get("c") or row.get("adjClose") or row.get("adj_close")
        )
        volume = to_int(row.get("volume") or row.get("v"))
        if min(open_, high, low, close) <= 0:
            continue
        if high < low:
            continue
        bars.append(Bar(normalized_date, open_, high, low, close, volume))

    dedup: dict[str, Bar] = {bar.date: bar for bar in bars}
    return [dedup[d] for d in sorted(dedup)]


def load_prices_json(path: PathLike) -> dict[str, list[Bar]]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)

    prices: dict[str, list[Bar]] = {}

    def add_symbol(symbol: str, rows: Any) -> None:
        normalized = normalize_symbol(symbol)
        bars = normalize_price_bars(rows, symbol=normalized)
        if bars:
            prices[normalized] = bars

    if isinstance(payload, dict):
        container = payload.get("prices") or payload.get("data") or payload.get("ohlcv")
        if isinstance(container, dict):
            for symbol, rows in container.items():
                add_symbol(symbol, rows)
        elif isinstance(container, list):
            prices = rows_to_prices_by_symbol(container)
        else:
            # Treat a top-level mapping of symbol -> rows as a valid shape.
            for symbol, rows in payload.items():
                if isinstance(rows, list):
                    add_symbol(symbol, rows)
    elif isinstance(payload, list):
        prices = rows_to_prices_by_symbol(payload)

    return {symbol: bars for symbol, bars in prices.items() if bars}


def rows_to_prices_by_symbol(rows: list[Any]) -> dict[str, list[Bar]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol") or row.get("ticker"))
        if symbol:
            grouped[symbol].append(row)
    result: dict[str, list[Bar]] = {}
    for symbol, items in grouped.items():
        bars = normalize_price_bars(items, symbol=symbol)
        if bars:
            result[symbol] = bars
    return result


def fetch_prices_from_fmp(
    args: argparse.Namespace, days: int = 320
) -> tuple[dict[str, list[Bar]], dict[str, Any]]:
    client = FMPClient(api_key=args.api_key, max_api_calls=args.max_api_calls)
    if args.fmp_universe:
        symbols = client.get_stock_list(limit=args.max_symbols)
    else:
        symbols = [normalize_symbol(symbol) for symbol in (args.symbols or [])]
    prices: dict[str, list[Bar]] = {}
    for symbol in symbols:
        try:
            bars = normalize_price_bars(
                client.get_historical_prices(symbol, days=days), symbol=symbol
            )
        except ApiCallBudgetExceeded:
            raise
        except Exception as exc:  # pragma: no cover - defensive live-data path
            print(f"WARN: failed to fetch {symbol}: {exc}", file=sys.stderr)
            continue
        if bars:
            prices[symbol] = bars
    return prices, client.stats()


def load_state(path: PathLike) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(row, dict):
                records.append(row)
    return records


def write_state(path: PathLike, records: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_records = sorted(
        records,
        key=lambda r: (r.get("event_date", ""), r.get("symbol", ""), r.get("record_id", "")),
    )
    with open(path, "w", encoding="utf-8") as handle:
        for record in sorted_records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def upsert_records(
    existing: list[dict[str, Any]], new_records: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {str(record.get("record_id")): record for record in existing if record.get("record_id")}
    for record in new_records:
        record_id = str(record.get("record_id"))
        previous = by_id.get(record_id, {})
        merged = deep_merge(previous, record)
        by_id[record_id] = merged
    return list(by_id.values())


def deep_merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    result = dict(old)
    for key, value in new.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        elif value is not None:
            result[key] = value
    return result


def find_as_of_index(bars: list[Bar], as_of: str | None) -> int | None:
    if not bars:
        return None
    if as_of is None:
        return len(bars) - 1
    target = parse_date(as_of)
    eligible = [idx for idx, bar in enumerate(bars) if parse_date(bar.date) <= target]
    if not eligible:
        return None
    return eligible[-1]


def pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return (current / previous - 1.0) * 100.0


def safe_pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator * 100.0


def close_location_pct(bar: Bar) -> float:
    if bar.high <= bar.low:
        return 50.0
    return max(0.0, min(100.0, (bar.close - bar.low) / (bar.high - bar.low) * 100.0))


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def median(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None and not math.isnan(value)]
    if not clean:
        return None
    return statistics.median(clean)


def determine_episode_id(
    symbol: str,
    event_date: str,
    direction: str,
    existing_records: list[dict[str, Any]],
    episode_gap_days: int,
) -> str:
    current = parse_date(event_date)
    candidates = []
    for record in existing_records:
        if normalize_symbol(record.get("symbol")) != symbol:
            continue
        if record.get("direction") != direction:
            continue
        other_date_raw = record.get("event_date")
        if not other_date_raw:
            continue
        try:
            other_date = parse_date(str(other_date_raw))
        except ValueError:
            continue
        gap = abs((current - other_date).days)
        if gap <= episode_gap_days and record.get("episode_id"):
            candidates.append((other_date, str(record["episode_id"])))
    if candidates:
        return sorted(candidates, key=lambda item: item[0])[0][1]
    return f"{symbol}:{event_date}:{direction}"


def detect_twenty_pct_events(
    prices: dict[str, list[Bar]],
    as_of: str | None,
    lookback_days: int,
    min_abs_return_pct: float,
    min_price: float,
    min_dollar_volume: float,
    include_down_movers: bool,
    existing_records: list[dict[str, Any]] | None = None,
    episode_gap_days: int = 5,
    extra_data_quality_flags: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    existing_records = existing_records or []
    extra_quality_flags = [str(flag) for flag in (extra_data_quality_flags or []) if flag]
    events: list[dict[str, Any]] = []
    skipped = defaultdict(int)
    effective_dates: list[str] = []

    for symbol, bars in sorted(prices.items()):
        idx = find_as_of_index(bars, as_of)
        if idx is None:
            skipped["no_as_of_bar"] += 1
            continue
        if idx < lookback_days:
            skipped["insufficient_lookback"] += 1
            continue
        current_bar = bars[idx]
        lookback_bar = bars[idx - lookback_days]
        previous_bar = bars[idx - 1] if idx > 0 else lookback_bar
        return_pct = pct_change(current_bar.close, lookback_bar.close)
        direction: str | None = None
        if return_pct + PCT_EPSILON >= min_abs_return_pct:
            direction = "UP"
        elif include_down_movers and return_pct - PCT_EPSILON <= -min_abs_return_pct:
            direction = "DOWN"
        if direction is None:
            skipped["threshold_not_met"] += 1
            continue
        if current_bar.close < min_price:
            skipped["below_min_price"] += 1
            continue
        dollar_volume = current_bar.close * current_bar.volume
        if dollar_volume < min_dollar_volume:
            skipped["below_min_dollar_volume"] += 1
            continue

        history_20 = bars[max(0, idx - 20) : idx]
        history_252 = bars[max(0, idx - 252) : idx + 1]
        avg_volume_20 = average([bar.volume for bar in history_20])
        avg_dollar_volume_20 = average([bar.close * bar.volume for bar in history_20])
        volume_ratio_20 = current_bar.volume / avg_volume_20 if avg_volume_20 else 0.0
        high_52w = max([bar.high for bar in history_252], default=current_bar.high)
        low_52w = min([bar.low for bar in history_252], default=current_bar.low)
        distance_to_52w_high_pct = pct_change(current_bar.close, high_52w)
        distance_to_52w_low_pct = pct_change(current_bar.close, low_52w)
        prior_20d_return_pct = (
            pct_change(previous_bar.close, bars[max(0, idx - 21)].close) if idx >= 21 else 0.0
        )
        prior_50d_return_pct = (
            pct_change(previous_bar.close, bars[max(0, idx - 51)].close) if idx >= 51 else 0.0
        )
        close_loc = close_location_pct(current_bar)
        range_pct = safe_pct(current_bar.high - current_bar.low, previous_bar.close)
        gap_pct = pct_change(current_bar.open, previous_bar.close)
        pattern_label = classify_chart_pattern(
            direction=direction,
            close_location=close_loc,
            gap_pct=gap_pct,
            range_pct=range_pct,
            return_pct=return_pct,
            distance_to_52w_high_pct=distance_to_52w_high_pct,
            volume_ratio_20=volume_ratio_20,
            prior_20d_return_pct=prior_20d_return_pct,
        )
        close_quality = classify_close_quality(close_loc, direction)
        extension_risk = classify_extension_risk(
            abs(return_pct), abs(prior_20d_return_pct), close_loc
        )
        data_quality_flags = data_quality_flags_for_event(
            bars=bars,
            idx=idx,
            current_bar=current_bar,
            return_pct=return_pct,
            avg_dollar_volume_20=avg_dollar_volume_20,
        )
        data_quality_flags = list(dict.fromkeys([*data_quality_flags, *extra_quality_flags]))
        catalyst = default_catalyst(direction)
        scores = score_event(
            direction=direction,
            catalyst=catalyst,
            dollar_volume=dollar_volume,
            volume_ratio_20=volume_ratio_20,
            close_location=close_loc,
            distance_to_52w_high_pct=distance_to_52w_high_pct,
            pattern_label=pattern_label,
            extension_risk=extension_risk,
            data_quality_flags=data_quality_flags,
        )
        event_date = current_bar.date
        episode_id = determine_episode_id(
            symbol, event_date, direction, existing_records + events, episode_gap_days
        )
        record_id = f"{symbol}:{event_date}:{direction}:{lookback_days}D"
        event = {
            "schema_version": SCHEMA_VERSION,
            "source_skill": SKILL_NAME,
            "record_id": record_id,
            "episode_id": episode_id,
            "symbol": symbol,
            "event_date": event_date,
            "direction": direction,
            "window_days": lookback_days,
            "event_day_index": episode_day_index(
                episode_id, symbol, direction, current_bar.date, existing_records + events
            ),
            "price_snapshot": {
                "open": round(current_bar.open, 4),
                "high": round(current_bar.high, 4),
                "low": round(current_bar.low, 4),
                "close": round(current_bar.close, 4),
                "previous_close": round(previous_bar.close, 4),
                "lookback_close": round(lookback_bar.close, 4),
                "return_pct": round(return_pct, 4),
                "day_return_pct": round(pct_change(current_bar.close, previous_bar.close), 4),
                "gap_pct": round(gap_pct, 4),
                "range_pct": round(range_pct, 4),
                "close_location_pct": round(close_loc, 2),
            },
            "liquidity": {
                "volume": current_bar.volume,
                "avg_volume_20d": round(avg_volume_20, 2),
                "volume_ratio_20d": round(volume_ratio_20, 3),
                "dollar_volume": round(dollar_volume, 2),
                "avg_dollar_volume_20d": round(avg_dollar_volume_20, 2),
                "price_pass": current_bar.close >= min_price,
                "liquidity_pass": dollar_volume >= min_dollar_volume,
            },
            "technical_context": {
                "distance_to_52w_high_pct": round(distance_to_52w_high_pct, 4),
                "distance_to_52w_low_pct": round(distance_to_52w_low_pct, 4),
                "prior_20d_return_pct": round(prior_20d_return_pct, 4),
                "prior_50d_return_pct": round(prior_50d_return_pct, 4),
                "base_length_days": estimate_base_length(bars, idx),
                "base_depth_pct": round(estimate_base_depth_pct(bars, idx), 4),
                "pattern_label": pattern_label,
                "close_quality": close_quality,
                "extension_risk": extension_risk,
            },
            "catalyst": catalyst,
            "theme_context": {
                "theme_label": "UNKNOWN",
                "theme_cluster_count": 0,
                "sector": None,
                "industry": None,
            },
            "scores": scores,
            "labels": labels_for_event(
                direction, pattern_label, close_quality, extension_risk, scores
            ),
            "handoffs": handoff_flags(direction, catalyst["label"], pattern_label, scores),
            "outcomes": {f"{h}d": None for h in DEFAULT_HORIZONS},
            "data_quality": {
                "flags": data_quality_flags,
                "data_quality_score": scores["data_quality_score"],
            },
            "human_review": {
                "reviewed": False,
                "label_override": None,
                "notes": None,
            },
            "raw": {
                "as_of_requested": as_of,
                "as_of_effective": event_date,
                "lookback_bar_date": lookback_bar.date,
            },
        }
        events.append(event)
        effective_dates.append(event_date)

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "source_skill": SKILL_NAME,
        "as_of_requested": as_of,
        "as_of_effective_dates": sorted(set(effective_dates)),
        "lookback_days": lookback_days,
        "min_abs_return_pct": min_abs_return_pct,
        "min_price": min_price,
        "min_dollar_volume": min_dollar_volume,
        "include_down_movers": include_down_movers,
        "events_detected": len(events),
        "skipped": dict(skipped),
    }
    return events, metadata


def episode_day_index(
    episode_id: str,
    symbol: str,
    direction: str,
    event_date: str,
    records: list[dict[str, Any]],
) -> int:
    dates = {event_date}
    for record in records:
        if record.get("episode_id") != episode_id:
            continue
        if (
            normalize_symbol(record.get("symbol")) == symbol
            and record.get("direction") == direction
            and record.get("event_date")
        ):
            dates.add(str(record["event_date"]))
    return sorted(dates).index(event_date) + 1


def classify_close_quality(close_loc: float, direction: str) -> str:
    if direction == "UP":
        if close_loc >= 80:
            return "STRONG_CLOSE"
        if close_loc >= 55:
            return "MID_CLOSE"
        return "WEAK_CLOSE"
    if close_loc <= 20:
        return "WEAK_CLOSE_DOWN"
    if close_loc <= 45:
        return "MID_CLOSE_DOWN"
    return "REVERSAL_CLOSE"


def classify_extension_risk(
    abs_return_pct: float, abs_prior_20d_return_pct: float, close_loc: float
) -> str:
    score = 0
    if abs_return_pct >= 60:
        score += 2
    elif abs_return_pct >= 35:
        score += 1
    if abs_prior_20d_return_pct >= 50:
        score += 2
    elif abs_prior_20d_return_pct >= 25:
        score += 1
    if close_loc < 45:
        score += 1
    if score >= 4:
        return "HIGH"
    if score >= 2:
        return "MODERATE"
    return "LOW"


def classify_chart_pattern(
    direction: str,
    close_location: float,
    gap_pct: float,
    range_pct: float,
    return_pct: float,
    distance_to_52w_high_pct: float,
    volume_ratio_20: float,
    prior_20d_return_pct: float,
) -> str:
    if direction == "DOWN":
        if close_location >= 65:
            return "DOWN_GAP_REVERSAL_CANDIDATE"
        if abs(return_pct) >= 35 and close_location <= 25:
            return "STRUCTURAL_BREAKDOWN"
        return "BREAKDOWN_EVENT"
    # UP patterns
    near_52w_high = distance_to_52w_high_pct >= -5.0
    if gap_pct >= 8 and close_location >= 75 and volume_ratio_20 >= 2:
        return "GAP_AND_GO"
    if near_52w_high and close_location >= 70 and volume_ratio_20 >= 1.5:
        return "BASE_BREAKOUT"
    if return_pct >= 50 and close_location < 55:
        return "CLIMAX_EXTENSION"
    if close_location < 45:
        return "FAILED_BREAKOUT"
    if prior_20d_return_pct > 40:
        return "EXTENDED_MOMENTUM"
    return "MOMENTUM_EVENT"


def estimate_base_length(bars: list[Bar], idx: int, max_lookback: int = 80) -> int:
    if idx <= 0:
        return 0
    current_close = bars[idx].close
    threshold = current_close * 0.75
    count = 0
    for bar in reversed(bars[max(0, idx - max_lookback) : idx]):
        if bar.close < threshold:
            break
        count += 1
    return count


def estimate_base_depth_pct(bars: list[Bar], idx: int, lookback: int = 50) -> float:
    segment = bars[max(0, idx - lookback) : idx]
    if not segment:
        return 0.0
    high = max(bar.high for bar in segment)
    low = min(bar.low for bar in segment)
    return safe_pct(high - low, high)


def default_catalyst(direction: str) -> dict[str, Any]:
    return {
        "label": "NO_CLEAR_NEWS",
        "confidence": 0.0,
        "source_type": "price_only",
        "summary": f"{direction} 20% mover detected from price/volume data; catalyst not enriched.",
    }


def data_quality_flags_for_event(
    bars: list[Bar],
    idx: int,
    current_bar: Bar,
    return_pct: float,
    avg_dollar_volume_20: float,
) -> list[str]:
    flags: list[str] = []
    if len(bars) < 260:
        flags.append("SHORT_HISTORY_LT_260_BARS")
    if avg_dollar_volume_20 and avg_dollar_volume_20 < 5_000_000:
        flags.append("LOW_AVG_DOLLAR_VOLUME")
    if current_bar.volume <= 0:
        flags.append("MISSING_VOLUME")
    if abs(return_pct) > 200:
        flags.append("EXTREME_MOVE_CHECK_SPLIT_OR_CORPORATE_ACTION")
    if idx > 0:
        previous = bars[idx - 1]
        if current_bar.open > previous.close * 4 or current_bar.open < previous.close * 0.25:
            flags.append("POSSIBLE_SPLIT_OR_SPECIAL_DISTRIBUTION")
    return flags


def score_event(
    direction: str,
    catalyst: dict[str, Any],
    dollar_volume: float,
    volume_ratio_20: float,
    close_location: float,
    distance_to_52w_high_pct: float,
    pattern_label: str,
    extension_risk: str,
    data_quality_flags: list[str],
) -> dict[str, int]:
    catalyst_points_by_label = {
        "EARNINGS_REVALUATION": 24,
        "GUIDANCE_RAISE": 24,
        "M&A": 22,
        "CONTRACT_ORDER": 18,
        "FDA_CLINICAL": 14,
        "ANALYST_UPGRADE": 12,
        "SHORT_SQUEEZE": 8,
        "THEME_SYMPATHY": 14,
        "NO_CLEAR_NEWS": 3,
        "LOW_FLOAT_SPECULATION": 0,
        "CAPITAL_STRUCTURE": 0,
    }
    catalyst_label = str(catalyst.get("label") or "NO_CLEAR_NEWS")
    catalyst_quality = catalyst_points_by_label.get(catalyst_label, 5)
    liquidity_score = min(15, int(dollar_volume / 20_000_000 * 10))
    volume_score = min(10, int(volume_ratio_20 * 3))
    close_score = (
        int(close_location / 100 * 15)
        if direction == "UP"
        else int((100 - close_location) / 100 * 15)
    )
    setup_score = (
        12
        if pattern_label in {"BASE_BREAKOUT", "GAP_AND_GO"}
        else 8
        if "MOMENTUM" in pattern_label
        else 3
    )
    high_score = 10 if direction == "UP" and distance_to_52w_high_pct >= -5 else 4
    if direction == "DOWN":
        high_score = 5
    extension_penalty = {"LOW": 0, "MODERATE": -5, "HIGH": -12}.get(extension_risk, -5)
    data_quality_score = max(0, 100 - len(data_quality_flags) * 15)
    data_quality_component = int(data_quality_score / 100 * 10)
    continuation_quality_score = max(
        0,
        min(
            100,
            catalyst_quality
            + liquidity_score
            + volume_score
            + close_score
            + setup_score
            + high_score
            + data_quality_component
            + extension_penalty,
        ),
    )
    reversal_risk_score = 0
    if catalyst_label in {"NO_CLEAR_NEWS", "LOW_FLOAT_SPECULATION", "CAPITAL_STRUCTURE"}:
        reversal_risk_score += 25
    if extension_risk == "HIGH":
        reversal_risk_score += 25
    elif extension_risk == "MODERATE":
        reversal_risk_score += 12
    if direction == "UP" and close_location < 50:
        reversal_risk_score += 25
    if dollar_volume < 20_000_000:
        reversal_risk_score += 15
    if data_quality_flags:
        reversal_risk_score += min(20, len(data_quality_flags) * 8)
    study_priority_score = max(
        0, min(100, continuation_quality_score + 20 - abs(50 - reversal_risk_score) // 3)
    )
    return {
        "continuation_quality_score": int(continuation_quality_score),
        "reversal_risk_score": int(min(100, reversal_risk_score)),
        "study_priority_score": int(study_priority_score),
        "data_quality_score": int(data_quality_score),
    }


def labels_for_event(
    direction: str,
    pattern_label: str,
    close_quality: str,
    extension_risk: str,
    scores: dict[str, int],
) -> list[str]:
    labels = [direction, pattern_label, close_quality]
    if extension_risk != "LOW":
        labels.append(f"{extension_risk}_EXTENSION_RISK")
    if scores.get("continuation_quality_score", 0) >= 75:
        labels.append("A_REVALUATION_OR_HIGH_QUALITY_EVENT")
    elif scores.get("continuation_quality_score", 0) >= 60:
        labels.append("B_MOMENTUM_EVENT")
    elif scores.get("reversal_risk_score", 0) >= 65:
        labels.append("D_LOW_QUALITY_OR_REVERSAL_RISK")
    else:
        labels.append("C_STUDY_ONLY")
    return labels


def handoff_flags(
    direction: str, catalyst_label: str, pattern_label: str, scores: dict[str, int]
) -> dict[str, bool]:
    return {
        "stockbee_episodic_pivot": direction == "UP"
        and pattern_label in {"GAP_AND_GO", "BASE_BREAKOUT"},
        "pead_screener": catalyst_label in {"EARNINGS_REVALUATION", "GUIDANCE_RAISE"},
        "theme_detector": catalyst_label == "THEME_SYMPATHY"
        or scores.get("study_priority_score", 0) >= 80,
        "edge_candidate_agent": scores.get("study_priority_score", 0) >= 85,
        "parabolic_short_watch": direction == "UP" and scores.get("reversal_risk_score", 0) >= 70,
    }


def load_news_events(path: PathLike | None) -> dict[str, list[dict[str, Any]]]:
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("events"), list):
            rows = [row for row in payload["events"] if isinstance(row, dict)]
        else:
            for symbol, items in payload.items():
                if isinstance(items, list):
                    for row in items:
                        if isinstance(row, dict):
                            item = dict(row)
                            item.setdefault("symbol", symbol)
                            rows.append(item)
    elif isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = normalize_symbol(row.get("symbol") or row.get("ticker"))
        if symbol:
            grouped[symbol].append(row)
    return dict(grouped)


def classify_catalyst_from_text(text: str) -> tuple[str, float]:
    lower = text.lower()
    keyword_map = [
        ("EARNINGS_REVALUATION", ["earnings", "revenue", "eps", "quarter", "profit", "results"]),
        ("GUIDANCE_RAISE", ["guidance", "raises outlook", "raised outlook", "forecast", "outlook"]),
        (
            "M&A",
            ["acquire", "acquisition", "merger", "buyout", "takeover", "strategic alternatives"],
        ),
        ("FDA_CLINICAL", ["fda", "phase 1", "phase 2", "phase 3", "clinical", "trial", "pdufa"]),
        (
            "CONTRACT_ORDER",
            ["contract", "order", "award", "partnership", "customer", "supply agreement"],
        ),
        ("ANALYST_UPGRADE", ["upgrade", "price target", "initiates", "overweight", "buy rating"]),
        ("SHORT_SQUEEZE", ["short squeeze", "short interest", "squeeze", "borrow", "float"]),
        (
            "THEME_SYMPATHY",
            ["sympathy", "sector", "theme", "ai", "crypto", "nuclear", "quantum", "defense"],
        ),
        (
            "CAPITAL_STRUCTURE",
            ["offering", "warrant", "dilution", "reverse split", "convertible", "atm"],
        ),
    ]
    for label, keywords in keyword_map:
        matches = sum(1 for keyword in keywords if keyword in lower)
        if matches:
            return label, min(0.95, 0.45 + 0.15 * matches)
    return "NO_CLEAR_NEWS", 0.1 if text.strip() else 0.0


def pick_news_for_event(
    symbol_events: list[dict[str, Any]], event_date: str, max_lag_days: int = 3
) -> dict[str, Any] | None:
    target = parse_date(event_date)
    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in symbol_events:
        raw_date = (
            row.get("date")
            or row.get("publishedDate")
            or row.get("published_at")
            or row.get("datetime")
        )
        if not raw_date:
            continue
        try:
            row_date = parse_date(str(raw_date))
        except ValueError:
            continue
        lag = (target - row_date).days
        if 0 <= lag <= max_lag_days:
            candidates.append((lag, row))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def enrich_events_with_news(
    events: list[dict[str, Any]], news_events_by_symbol: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for event in events:
        symbol = normalize_symbol(event.get("symbol"))
        news = pick_news_for_event(
            news_events_by_symbol.get(symbol, []), str(event.get("event_date"))
        )
        updated = dict(event)
        if news:
            text = " ".join(
                str(news.get(key) or "")
                for key in ("title", "headline", "summary", "text", "description", "category")
            )
            label, confidence = classify_catalyst_from_text(text)
            updated["catalyst"] = {
                "label": label,
                "confidence": confidence,
                "source_type": "news_events_json",
                "summary": " ".join(text.split())[:500],
                "raw_event": news,
            }
            updated["scores"] = score_event(
                direction=str(updated.get("direction")),
                catalyst=updated["catalyst"],
                dollar_volume=to_float(updated.get("liquidity", {}).get("dollar_volume")),
                volume_ratio_20=to_float(updated.get("liquidity", {}).get("volume_ratio_20d")),
                close_location=to_float(
                    updated.get("price_snapshot", {}).get("close_location_pct")
                ),
                distance_to_52w_high_pct=to_float(
                    updated.get("technical_context", {}).get("distance_to_52w_high_pct")
                ),
                pattern_label=str(updated.get("technical_context", {}).get("pattern_label")),
                extension_risk=str(updated.get("technical_context", {}).get("extension_risk")),
                data_quality_flags=list(updated.get("data_quality", {}).get("flags") or []),
            )
            updated["labels"] = labels_for_event(
                str(updated.get("direction")),
                str(updated.get("technical_context", {}).get("pattern_label")),
                str(updated.get("technical_context", {}).get("close_quality")),
                str(updated.get("technical_context", {}).get("extension_risk")),
                updated["scores"],
            )
            updated["handoffs"] = handoff_flags(
                str(updated.get("direction")),
                label,
                str(updated.get("technical_context", {}).get("pattern_label")),
                updated["scores"],
            )
        enriched.append(updated)
    return enriched


def update_forward_outcomes(
    records: list[dict[str, Any]],
    prices: dict[str, list[Bar]],
    horizons: Iterable[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    updated_records: list[dict[str, Any]] = []
    counts = defaultdict(int)
    for record in records:
        updated = dict(record)
        symbol = normalize_symbol(record.get("symbol"))
        event_date = str(record.get("event_date") or "")
        direction = str(record.get("direction") or "UP")
        bars = prices.get(symbol, [])
        idx = None
        for i, bar in enumerate(bars):
            if bar.date == event_date:
                idx = i
                break
        if idx is None:
            counts["missing_event_bar"] += 1
            updated_records.append(updated)
            continue
        entry_close = bars[idx].close
        outcomes = dict(updated.get("outcomes") or {})
        for horizon in horizons:
            horizon = int(horizon)
            key = f"{horizon}d"
            if idx + horizon >= len(bars):
                outcomes[key] = {
                    "status": "PENDING",
                    "horizon_days": horizon,
                    "reason": "insufficient_future_bars",
                    "future_bars_available": max(0, len(bars) - idx - 1),
                }
                counts["pending"] += 1
                continue
            future = bars[idx + 1 : idx + horizon + 1]
            close_bar = bars[idx + horizon]
            high = max(bar.high for bar in future)
            low = min(bar.low for bar in future)
            close_return = pct_change(close_bar.close, entry_close)
            mfe = pct_change(high, entry_close)
            mae = pct_change(low, entry_close)
            if direction == "DOWN":
                directional_close = -close_return
                directional_mfe = safe_pct(entry_close - low, entry_close)
                directional_mae = safe_pct(entry_close - high, entry_close)
            else:
                directional_close = close_return
                directional_mfe = mfe
                directional_mae = mae
            outcome_tag = classify_outcome(
                direction,
                close_return,
                directional_close,
                directional_mfe,
                directional_mae,
                horizon,
            )
            outcomes[key] = {
                "status": "MATURED",
                "horizon_days": horizon,
                "entry_close": round(entry_close, 4),
                "close_date": close_bar.date,
                "close": round(close_bar.close, 4),
                "close_return_pct": round(close_return, 4),
                "mfe_pct": round(mfe, 4),
                "mae_pct": round(mae, 4),
                "directional_close_return_pct": round(directional_close, 4),
                "directional_mfe_pct": round(directional_mfe, 4),
                "directional_mae_pct": round(directional_mae, 4),
                "outcome_tag": outcome_tag,
            }
            counts["matured"] += 1
        updated["outcomes"] = outcomes
        updated["matured"] = any(
            isinstance(value, dict) and value.get("status") == "MATURED"
            for value in outcomes.values()
        )
        updated_records.append(updated)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "source_skill": SKILL_NAME,
        "records_processed": len(records),
        "horizons": [int(h) for h in horizons],
        "counts": dict(counts),
    }
    return updated_records, metadata


def classify_outcome(
    direction: str,
    close_return: float,
    directional_close: float,
    directional_mfe: float,
    directional_mae: float,
    horizon: int,
) -> str:
    if direction == "UP":
        if directional_close >= 8 or directional_mfe >= 12:
            return "STRONG_CONTINUATION"
        if directional_close >= 4 or directional_mfe >= 6:
            return "CONTINUED"
        if close_return <= -4:
            return "FAILED_FADE"
        if directional_mae <= -8 and directional_close < 2:
            return "CHOPPY_FAILURE"
        return "NEUTRAL"
    # DOWN: directional positive means the breakdown continued lower.
    if directional_close >= 8 or directional_mfe >= 12:
        return "STRONG_BREAKDOWN_CONTINUATION"
    if directional_close >= 4 or directional_mfe >= 6:
        return "BREAKDOWN_CONTINUED"
    if close_return >= 6:
        return "REVERSAL_BOUNCE"
    if horizon >= 5 and close_return >= 3:
        return "PARTIAL_REVERSAL"
    return "NEUTRAL"


def get_nested(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def summarize_cohorts(
    records: list[dict[str, Any]],
    group_by: list[str],
    min_sample: int,
    horizon: int = 5,
) -> dict[str, Any]:
    key = f"{horizon}d"
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        outcome = (record.get("outcomes") or {}).get(key)
        if not isinstance(outcome, dict) or outcome.get("status") != "MATURED":
            continue
        group_key = tuple(get_nested(record, path) for path in group_by)
        groups[group_key].append(record)

    cohorts = []
    rule_candidates = []
    for group_key, items in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        directional_returns = [
            to_float(
                ((item.get("outcomes") or {}).get(key) or {}).get("directional_close_return_pct")
            )
            for item in items
        ]
        close_returns = [
            to_float(((item.get("outcomes") or {}).get(key) or {}).get("close_return_pct"))
            for item in items
        ]
        mfe_values = [
            to_float(((item.get("outcomes") or {}).get(key) or {}).get("directional_mfe_pct"))
            for item in items
        ]
        mae_values = [
            to_float(((item.get("outcomes") or {}).get(key) or {}).get("directional_mae_pct"))
            for item in items
        ]
        continuation_wins = sum(1 for value in directional_returns if value > 0)
        win_rate = continuation_wins / len(directional_returns) if directional_returns else 0.0
        outcome_tags = defaultdict(int)
        data_quality_flag_counts = defaultdict(int)
        for item in items:
            tag = ((item.get("outcomes") or {}).get(key) or {}).get("outcome_tag") or "UNKNOWN"
            outcome_tags[str(tag)] += 1
            flags = list((item.get("data_quality") or {}).get("flags") or [])
            if not flags:
                data_quality_flag_counts["NO_FLAGS"] += 1
            for flag in sorted({str(flag) for flag in flags if flag}):
                data_quality_flag_counts[flag] += 1
        cohort = {
            "group": {path: value for path, value in zip(group_by, group_key)},
            "sample_size": len(items),
            "horizon": key,
            "win_rate_directional": round(win_rate, 4),
            "median_directional_return_pct": round_or_none(median(directional_returns)),
            "median_close_return_pct": round_or_none(median(close_returns)),
            "median_directional_mfe_pct": round_or_none(median(mfe_values)),
            "median_directional_mae_pct": round_or_none(median(mae_values)),
            "outcome_tag_counts": dict(sorted(outcome_tags.items())),
            "data_quality_flag_counts": dict(sorted(data_quality_flag_counts.items())),
            "representative_symbols": sorted({str(item.get("symbol")) for item in items})[:10],
        }
        cohorts.append(cohort)
        if len(items) >= min_sample:
            rule = candidate_rule_from_cohort(cohort)
            if rule:
                rule_candidates.append(rule)

    return {
        "schema_version": SCHEMA_VERSION,
        "source_skill": SKILL_NAME,
        "group_by": group_by,
        "min_sample": min_sample,
        "horizon": key,
        "records_matured": sum(len(v) for v in groups.values()),
        "cohorts": cohorts,
        "rule_candidates": rule_candidates,
    }


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def candidate_rule_from_cohort(cohort: dict[str, Any]) -> dict[str, Any] | None:
    n = int(cohort.get("sample_size") or 0)
    win_rate = to_float(cohort.get("win_rate_directional"))
    median_return = cohort.get("median_directional_return_pct")
    if median_return is None:
        return None
    median_return = to_float(median_return)
    median_mae = to_float(cohort.get("median_directional_mae_pct"))
    if win_rate >= 0.58 and median_return >= 2.0:
        status = "candidate_for_review"
        thesis = "Continuation-favorable cohort; promote only after representative chart review and out-of-sample validation."
    elif win_rate <= 0.42 and median_return <= -2.0:
        status = "avoid_or_fade_study"
        thesis = "Weak continuation cohort; useful as avoid filter or fade hypothesis, not an automatic short signal."
    else:
        return None
    data_quality_flag_counts = dict(cohort.get("data_quality_flag_counts") or {})
    required_review = [
        "Inspect representative winner and failure charts.",
        "Check year-by-year stability and market-regime splits.",
        "Confirm realistic entry, slippage, liquidity, and borrow assumptions where applicable.",
    ]
    if data_quality_flag_counts.get(BACKFILL_SURVIVORSHIP_BIAS_FLAG):
        required_review.append(
            "Split current-universe backfills from survivorship-complete records before promotion."
        )
    return {
        "id": slugify("_".join(str(v) for v in cohort.get("group", {}).values()))[:80],
        "status": status,
        "thesis": thesis,
        "evidence": {
            "sample_size": n,
            "win_rate_directional": win_rate,
            "median_directional_return_pct": median_return,
            "median_directional_mae_pct": median_mae,
            "data_quality_flag_counts": data_quality_flag_counts,
        },
        "group": cohort.get("group", {}),
        "required_review": required_review,
    }


def slugify(value: str) -> str:
    chars = []
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
        elif char in {" ", "-", "_", ":", "/"}:
            chars.append("_")
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "cohort"


def build_daily_report(events: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    lines = [
        f"# Stockbee 20% Study — {metadata.get('as_of_requested') or 'latest'}",
        "",
        "## Scan Summary",
        f"- Events detected: {metadata.get('events_detected', len(events))}",
        f"- Lookback days: {metadata.get('lookback_days')}",
        f"- Threshold: ±{metadata.get('min_abs_return_pct')}%",
        f"- Min price: {metadata.get('min_price')}",
        f"- Min dollar volume: {metadata.get('min_dollar_volume')}",
        "",
    ]
    if metadata.get("skipped"):
        lines.append("## Skipped Counts")
        for reason, count in sorted(metadata["skipped"].items()):
            lines.append(f"- {reason}: {count}")
        lines.append("")
    for direction in ("UP", "DOWN"):
        subset = [event for event in events if event.get("direction") == direction]
        lines.append(f"## {direction} Movers")
        if not subset:
            lines.append("No events.")
            lines.append("")
            continue
        lines.append(
            "| Symbol | Event Date | Return | Pattern | Close | Quality | Risk | Catalyst |"
        )
        lines.append("|---|---:|---:|---|---|---:|---:|---|")
        for event in sorted(
            subset,
            key=lambda e: abs(to_float(e.get("price_snapshot", {}).get("return_pct"))),
            reverse=True,
        ):
            ps = event.get("price_snapshot", {})
            tc = event.get("technical_context", {})
            scores = event.get("scores", {})
            catalyst = event.get("catalyst", {})
            lines.append(
                f"| {event.get('symbol')} | {event.get('event_date')} | {to_float(ps.get('return_pct')):.2f}% | "
                f"{tc.get('pattern_label')} | {tc.get('close_quality')} | "
                f"{scores.get('continuation_quality_score')} | {scores.get('reversal_risk_score')} | {catalyst.get('label')} |"
            )
        lines.append("")
    lines.append("## Interpretation Notes")
    lines.append(
        "- Treat this report as an observation/model-book artifact, not as a buy/sell signal."
    )
    lines.append("- Review representative charts before promoting any pattern into a trade rule.")
    return "\n".join(lines) + "\n"


def build_outcome_report(
    metadata: dict[str, Any], records: list[dict[str, Any]], horizons: list[int]
) -> str:
    lines = [
        "# Stockbee 20% Study Outcome Update",
        "",
        "## Update Summary",
        f"- Records processed: {metadata.get('records_processed')}",
        f"- Counts: `{json.dumps(metadata.get('counts', {}), sort_keys=True)}`",
        "",
        "## Recently Matured Records",
        "| Symbol | Event Date | Direction | Horizon | Close Return | Directional Return | Outcome |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    rows_added = 0
    for record in sorted(
        records, key=lambda r: (r.get("event_date", ""), r.get("symbol", "")), reverse=True
    ):
        for horizon in horizons:
            outcome = (record.get("outcomes") or {}).get(f"{horizon}d")
            if not isinstance(outcome, dict) or outcome.get("status") != "MATURED":
                continue
            lines.append(
                f"| {record.get('symbol')} | {record.get('event_date')} | {record.get('direction')} | {horizon}d | "
                f"{to_float(outcome.get('close_return_pct')):.2f}% | "
                f"{to_float(outcome.get('directional_close_return_pct')):.2f}% | {outcome.get('outcome_tag')} |"
            )
            rows_added += 1
            if rows_added >= 40:
                break
        if rows_added >= 40:
            break
    if rows_added == 0:
        lines.append("| — | — | — | — | — | — | No matured outcomes yet |")
    return "\n".join(lines) + "\n"


def build_cohort_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Stockbee 20% Study Cohort Summary",
        "",
        "## Summary",
        f"- Group by: {', '.join(summary.get('group_by', []))}",
        f"- Horizon: {summary.get('horizon')}",
        f"- Matured records: {summary.get('records_matured')}",
        f"- Rule candidates: {len(summary.get('rule_candidates', []))}",
        "",
        "## Cohorts",
        "| Group | N | Win Rate | Median Dir Ret | Median MFE | Median MAE | Top Tags |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for cohort in summary.get("cohorts", [])[:50]:
        group = ", ".join(f"{k}={v}" for k, v in cohort.get("group", {}).items())
        tags = ", ".join(
            f"{k}:{v}" for k, v in list(cohort.get("outcome_tag_counts", {}).items())[:4]
        )
        lines.append(
            f"| {group} | {cohort.get('sample_size')} | {to_float(cohort.get('win_rate_directional')):.2f} | "
            f"{fmt_pct(cohort.get('median_directional_return_pct'))} | {fmt_pct(cohort.get('median_directional_mfe_pct'))} | "
            f"{fmt_pct(cohort.get('median_directional_mae_pct'))} | {tags} |"
        )
    lines.extend(["", "## Rule Candidates"])
    if not summary.get("rule_candidates"):
        lines.append("No rule candidates met the current sample-size and expectancy thresholds.")
    else:
        for rule in summary["rule_candidates"]:
            lines.append(f"### {rule.get('id')}")
            lines.append(f"- Status: {rule.get('status')}")
            lines.append(f"- Thesis: {rule.get('thesis')}")
            lines.append(f"- Evidence: `{json.dumps(rule.get('evidence', {}), sort_keys=True)}`")
            lines.append("")
    lines.append("## Guardrails")
    lines.append("- Treat rule candidates as research prompts, not execution rules.")
    lines.append("- Require out-of-sample validation and representative chart review.")
    return "\n".join(lines) + "\n"


def fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{to_float(value):.2f}%"


def write_json(path: Path, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def load_events_json(path: PathLike) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    raise ValueError(f"Could not find event list in {path}")


def parse_horizons(value: str) -> list[int]:
    horizons = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        horizon = int(part)
        if horizon <= 0:
            raise ValueError("horizons must be positive integers")
        horizons.append(horizon)
    return sorted(dict.fromkeys(horizons))


def load_prices_for_args(
    args: argparse.Namespace, days: int = 320
) -> tuple[dict[str, list[Bar]], dict[str, Any]]:
    if getattr(args, "prices_json", None):
        return load_prices_json(args.prices_json), {
            "source": "prices_json",
            "path": args.prices_json,
        }
    if getattr(args, "fmp_universe", False) or getattr(args, "symbols", None):
        prices, stats = fetch_prices_from_fmp(args, days=days)
        stats["source"] = "fmp"
        return prices, stats
    raise ValueError("Provide --prices-json, --symbols, or --fmp-universe.")


def command_scan(args: argparse.Namespace) -> int:
    output_dir = ensure_dir(args.output_dir)
    state = load_state(args.state_file)
    prices, source_meta = load_prices_for_args(args)
    events, metadata = detect_twenty_pct_events(
        prices=prices,
        as_of=args.as_of,
        lookback_days=args.lookback_days,
        min_abs_return_pct=args.min_abs_return_pct,
        min_price=args.min_price,
        min_dollar_volume=args.min_dollar_volume,
        include_down_movers=args.include_down_movers,
        existing_records=state,
        episode_gap_days=args.episode_gap_days,
    )
    metadata["data_source"] = source_meta
    state = upsert_records(state, events)
    write_state(args.state_file, state)
    stamp = now_stamp()
    json_path = output_dir / f"stockbee_20pct_events_{stamp}.json"
    md_path = output_dir / f"stockbee_20pct_daily_report_{stamp}.md"
    write_json(json_path, {"metadata": metadata, "events": events})
    write_text(md_path, build_daily_report(events, metadata))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Updated {args.state_file}")
    return 0


def command_enrich(args: argparse.Namespace) -> int:
    output_dir = ensure_dir(args.output_dir)
    state = load_state(args.state_file)
    events = load_events_json(args.events_json)
    news_events = load_news_events(args.news_json)
    enriched = enrich_events_with_news(events, news_events)
    state = upsert_records(state, enriched)
    write_state(args.state_file, state)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "source_skill": SKILL_NAME,
        "events_processed": len(events),
        "news_symbols": len(news_events),
    }
    stamp = now_stamp()
    json_path = output_dir / f"stockbee_20pct_enriched_{stamp}.json"
    md_path = output_dir / f"stockbee_20pct_enriched_report_{stamp}.md"
    write_json(json_path, {"metadata": metadata, "events": enriched})
    write_text(
        md_path,
        build_daily_report(
            enriched,
            {
                **metadata,
                "as_of_requested": "enriched",
                "lookback_days": "n/a",
                "min_abs_return_pct": "n/a",
                "events_detected": len(enriched),
            },
        ),
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Updated {args.state_file}")
    return 0


def command_update_outcomes(args: argparse.Namespace) -> int:
    output_dir = ensure_dir(args.output_dir)
    records = load_state(args.state_file)
    if not records:
        raise ValueError(f"No records found in {args.state_file}")
    prices, source_meta = load_prices_for_args(args)
    horizons = parse_horizons(args.horizons)
    updated, metadata = update_forward_outcomes(records, prices, horizons)
    metadata["data_source"] = source_meta
    write_state(args.state_file, updated)
    stamp = now_stamp()
    json_path = output_dir / f"stockbee_20pct_outcome_update_{stamp}.json"
    md_path = output_dir / f"stockbee_20pct_outcome_update_{stamp}.md"
    write_json(json_path, {"metadata": metadata, "records": updated})
    write_text(md_path, build_outcome_report(metadata, updated, horizons))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Updated {args.state_file}")
    return 0


def command_summarize(args: argparse.Namespace) -> int:
    output_dir = ensure_dir(args.output_dir)
    records = load_state(args.state_file)
    if not records:
        raise ValueError(f"No records found in {args.state_file}")
    group_by = [item.strip() for item in args.group_by.split(",") if item.strip()]
    summary = summarize_cohorts(
        records, group_by=group_by, min_sample=args.min_sample, horizon=args.horizon
    )
    stamp = now_stamp()
    json_path = output_dir / f"stockbee_20pct_cohort_summary_{stamp}.json"
    md_path = output_dir / f"stockbee_20pct_cohort_summary_{stamp}.md"
    yaml_path = output_dir / f"stockbee_20pct_edge_hints_{stamp}.yaml"
    write_json(json_path, summary)
    write_text(md_path, build_cohort_report(summary))
    # JSON is valid YAML 1.2 and avoids requiring PyYAML.
    write_json(
        yaml_path,
        {
            "schema_version": 1,
            "source_skill": SKILL_NAME,
            "edge_hints": summary.get("rule_candidates", []),
        },
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {yaml_path}")
    return 0


def command_backfill(args: argparse.Namespace) -> int:
    output_dir = ensure_dir(args.output_dir)
    state = load_state(args.state_file)
    if not args.prices_json:
        raise ValueError(
            "backfill currently requires --prices-json to avoid uncontrolled live API scans"
        )
    prices = load_prices_json(args.prices_json)
    start = parse_date(args.from_date)
    end = parse_date(args.to_date)
    all_dates = sorted(
        {
            bar.date
            for bars in prices.values()
            for bar in bars
            if start <= parse_date(bar.date) <= end
        }
    )
    all_events: list[dict[str, Any]] = []
    skipped_total = defaultdict(int)
    extra_flags = [] if args.survivorship_complete else [BACKFILL_SURVIVORSHIP_BIAS_FLAG]
    for as_of in all_dates:
        events, metadata = detect_twenty_pct_events(
            prices=prices,
            as_of=as_of,
            lookback_days=args.lookback_days,
            min_abs_return_pct=args.min_abs_return_pct,
            min_price=args.min_price,
            min_dollar_volume=args.min_dollar_volume,
            include_down_movers=args.include_down_movers,
            existing_records=state + all_events,
            episode_gap_days=args.episode_gap_days,
            extra_data_quality_flags=extra_flags,
        )
        all_events.extend(events)
        for reason, count in metadata.get("skipped", {}).items():
            skipped_total[reason] += count
    state = upsert_records(state, all_events)
    write_state(args.state_file, state)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "source_skill": SKILL_NAME,
        "from": args.from_date,
        "to": args.to_date,
        "dates_scanned": len(all_dates),
        "events_detected": len(all_events),
        "skipped": dict(skipped_total),
        "survivorship_complete": bool(args.survivorship_complete),
        "record_data_quality_flags_added": extra_flags,
        "data_quality_note": (
            "Backfill records were marked as current-universe survivorship-biased. "
            "Pass --survivorship-complete only when the supplied OHLCV includes delisted symbols."
            if extra_flags
            else "Backfill was declared survivorship-complete by the caller."
        ),
    }
    stamp = now_stamp()
    json_path = output_dir / f"stockbee_20pct_backfill_{stamp}.json"
    md_path = output_dir / f"stockbee_20pct_backfill_{stamp}.md"
    write_json(json_path, {"metadata": metadata, "events": all_events})
    write_text(
        md_path,
        build_daily_report(
            all_events[:200],
            {
                **metadata,
                "as_of_requested": f"{args.from_date}..{args.to_date}",
                "lookback_days": args.lookback_days,
                "min_abs_return_pct": args.min_abs_return_pct,
                "min_price": args.min_price,
                "min_dollar_volume": args.min_dollar_volume,
            },
        ),
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Updated {args.state_file}")
    return 0


def add_common_data_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--prices-json",
        help="Offline OHLCV JSON. Supports {'prices': {'AAPL': [bars]}} or row-list shapes.",
    )
    parser.add_argument(
        "--symbols", nargs="*", help="Symbols to fetch via FMP when --prices-json is not provided."
    )
    parser.add_argument(
        "--fmp-universe",
        action="store_true",
        help="Fetch a broad US universe from FMP. Use --max-symbols to cap API usage.",
    )
    parser.add_argument(
        "--max-symbols", type=int, default=300, help="Maximum FMP universe symbols to fetch."
    )
    parser.add_argument("--api-key", help="FMP API key. Defaults to FMP_API_KEY.")
    parser.add_argument(
        "--max-api-calls", type=int, default=500, help="Safety cap for FMP API calls."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stockbee-style +20%%/-20%% mover event study")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan for +20%%/-20%% movers and upsert event records")
    add_common_data_args(scan)
    scan.add_argument("--as-of", help="As-of date YYYY-MM-DD. Defaults to latest available bar.")
    scan.add_argument("--lookback-days", type=int, default=5)
    scan.add_argument("--min-abs-return-pct", type=float, default=20.0)
    scan.add_argument("--min-price", type=float, default=5.0)
    scan.add_argument("--min-dollar-volume", type=float, default=20_000_000.0)
    scan.add_argument("--include-down-movers", action="store_true")
    scan.add_argument("--episode-gap-days", type=int, default=5)
    scan.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    scan.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    scan.set_defaults(func=command_scan)

    enrich = sub.add_parser(
        "enrich", help="Enrich scanned events with optional structured news/catalyst JSON"
    )
    enrich.add_argument("--events-json", required=True)
    enrich.add_argument("--news-json")
    enrich.add_argument(
        "--market-regime",
        help="Reserved for future market-regime enrichment; accepted for workflow compatibility.",
    )
    enrich.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    enrich.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    enrich.set_defaults(func=command_enrich)

    update = sub.add_parser(
        "update-outcomes", help="Update forward outcomes for records in the state file"
    )
    add_common_data_args(update)
    update.add_argument("--horizons", default=",".join(str(h) for h in DEFAULT_HORIZONS))
    update.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    update.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    update.set_defaults(func=command_update_outcomes)

    summarize = sub.add_parser(
        "summarize", help="Summarize matured event cohorts and export edge hints"
    )
    summarize.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    summarize.add_argument("--group-by", default=DEFAULT_GROUP_BY)
    summarize.add_argument("--min-sample", type=int, default=10)
    summarize.add_argument("--horizon", type=int, default=5)
    summarize.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    summarize.set_defaults(func=command_summarize)

    backfill = sub.add_parser(
        "backfill", help="Backfill historical +20%%/-20%% events from offline OHLCV JSON"
    )
    backfill.add_argument("--from", dest="from_date", required=True)
    backfill.add_argument("--to", dest="to_date", required=True)
    backfill.add_argument("--prices-json", required=True)
    backfill.add_argument("--lookback-days", type=int, default=5)
    backfill.add_argument("--min-abs-return-pct", type=float, default=20.0)
    backfill.add_argument("--min-price", type=float, default=5.0)
    backfill.add_argument("--min-dollar-volume", type=float, default=20_000_000.0)
    backfill.add_argument("--include-down-movers", action="store_true")
    backfill.add_argument("--episode-gap-days", type=int, default=5)
    backfill.add_argument(
        "--survivorship-complete",
        action="store_true",
        help=(
            "Declare the supplied OHLCV includes delisted symbols and historical universe "
            "coverage; suppresses the current-universe survivorship-bias flag."
        ),
    )
    backfill.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    backfill.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    backfill.set_defaults(func=command_backfill)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
