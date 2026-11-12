#!/usr/bin/env python3
"""
Stockbee Exhaustion Hammer Screener

Screens US equities for Stockbee-style selling-exhaustion hammer candidates:
high-quality / liquid stocks that had prior momentum, pulled back for several
sessions, undercut or tested a short-term low, and then formed a near-close
hammer / reversal candle with manageable risk to the day low.

Input modes:
  A. FMP universe scan: --fmp-universe
  B. Explicit symbols: --symbols APP ENPH NVDA
  C. Offline OHLCV JSON: --prices-json data/daily_ohlcv.json

Output:
  - JSON: stockbee_exhaustion_hammer_YYYY-MM-DD_HHMMSS.json
  - Markdown: stockbee_exhaustion_hammer_YYYY-MM-DD_HHMMSS.md
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - environment guard
    requests = None

SKILL_NAME = "stockbee-exhaustion-hammer-screener"
SCHEMA_VERSION = "1.0"


@dataclass
class Bar:
    """Normalized daily OHLCV bar, sorted most-recent first."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class HammerProfile:
    """Geometry of the latest candle."""

    day_range: float
    day_range_pct: float
    body: float
    body_pct_of_range: float
    lower_wick: float
    lower_wick_pct_of_range: float
    upper_wick: float
    upper_wick_pct_of_range: float
    lower_wick_to_body: float
    close_location_pct: float
    recovery_from_low_pct: float
    day_gain_pct: float
    dollar_gain: float
    green_close: bool
    hammer_tags: list[str]
    primary_trigger: str


@dataclass
class PullbackProfile:
    """Prior momentum, pullback, and exhaustion context."""

    recent_high: float
    recent_high_date: str
    days_since_recent_high: int
    pullback_pct_from_high: float
    prior_low: float
    prior_low_date: str
    undercut_reclaim: bool
    low_undercut_pct: float
    down_days_10: int
    lower_closes_5: int
    consecutive_down_closes: int
    below_10dma_pct: float
    above_50dma: bool
    return_20d_pct: float
    return_60d_pct: float


@dataclass
class QualityProfile:
    """Liquidity and optional FMP/profile quality metrics."""

    avg_volume_20d: float
    avg_dollar_volume_20d: float
    volume_ratio_1d: float
    volume_ratio_20d: float
    market_cap: float
    institutional_ownership_pct: float
    mutual_fund_holders: int
    institutional_holders: int


class ApiCallBudgetExceeded(Exception):
    """Raised when the configured API call budget has been exhausted."""


_SHARED_FMP_MODULE = "_stockbee_exhaustion_hammer_screener_fmp_client"


def _load_shared_fmp():
    """Load the sibling generated client by path (never `import fmp_client`)."""
    module = sys.modules.get(_SHARED_FMP_MODULE)
    if module is None:
        path = Path(__file__).resolve().parent / "fmp_client.py"
        spec = importlib.util.spec_from_file_location(_SHARED_FMP_MODULE, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[_SHARED_FMP_MODULE] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(_SHARED_FMP_MODULE, None)
            raise
    return module


def _delegate(name: str) -> property:
    def getter(self):
        return getattr(self._client, name)

    def setter(self, value):
        setattr(self._client, name, value)

    return property(getter, setter)


class FMPClient:
    """Thin adapter over the generated stable-only FMP client (#495 Batch C)."""

    session = _delegate("session")
    api_calls_made = _delegate("api_calls_made")
    max_api_calls = _delegate("max_api_calls")
    last_call_time = _delegate("last_call_time")
    rate_limit_reached = _delegate("rate_limit_reached")

    def __init__(self, api_key: str | None = None, max_api_calls: int = 700):
        if requests is None:
            print(
                "ERROR: requests library not found. Install this skill's dependencies: "
                f"pip install -r {Path(__file__).resolve().parents[1] / 'requirements.txt'}",
                file=sys.stderr,
            )
            sys.exit(2)
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError(
                "FMP API key required. Set FMP_API_KEY or use --prices-json for offline mode."
            )
        shared = _load_shared_fmp()
        self._budget_error = shared.ApiCallBudgetExceeded
        self._client = shared.FMPClient(api_key=self.api_key, max_api_calls=max_api_calls)
        self.cache: dict[str, Any] = {}

    def _call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except self._budget_error as exc:
            raise ApiCallBudgetExceeded(str(exc)) from exc

    def get_universe(
        self,
        min_market_cap: float,
        min_price: float,
        min_volume: int,
        max_symbols: int,
    ) -> list[dict[str, Any]]:
        """Fetch a broad liquid US-equity universe from FMP's company screener."""
        cache_key = f"universe_{min_market_cap}_{min_price}_{min_volume}_{max_symbols}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        params = {
            "marketCapMoreThan": int(min_market_cap),
            "priceMoreThan": min_price,
            "volumeMoreThan": int(min_volume),
            "exchange": "NASDAQ,NYSE,AMEX",
            "limit": 10000,
        }
        data = self._call(self._client.fetch_screener_rows, params)
        if not isinstance(data, list):
            return []

        universe = []
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = normalize_symbol(item.get("symbol", ""))
            if not symbol:
                continue
            if item.get("isEtf") or item.get("isFund"):
                continue
            item = dict(item)
            item["symbol"] = symbol
            universe.append(item)

        universe.sort(key=lambda row: row.get("marketCap") or row.get("mktCap") or 0, reverse=True)
        universe = universe[:max_symbols]
        self.cache[cache_key] = universe
        return universe

    def get_historical_prices(self, symbol: str, days: int = 120) -> list[dict[str, Any]]:
        """Fetch most-recent-first daily OHLCV bars for one symbol."""
        symbol = normalize_symbol(symbol)
        cache_key = f"history_{symbol}_{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        rows = self._call(self._client.fetch_eod_rows, symbol, days, pad_days=10, quiet=False)
        bars = normalize_fmp_historical_response(rows, symbol, days)
        self.cache[cache_key] = bars
        return bars

    def get_quote_bar(self, symbol: str, asof_date: str | None = None) -> dict[str, Any] | None:
        """Fetch best-effort current-day OHLCV from FMP quote endpoint."""
        symbol = normalize_symbol(symbol)
        cache_key = f"quote_{symbol}_{asof_date or 'today'}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        row = self._call(self._client.fetch_quote_row, symbol, quiet=True)
        if not isinstance(row, dict):
            return None
        close = to_float(row.get("price") or row.get("close"))
        open_ = to_float(row.get("open"), default=close)
        high = to_float(row.get("dayHigh") or row.get("high"), default=max(open_, close))
        low = to_float(row.get("dayLow") or row.get("low"), default=min(open_, close))
        volume = to_int(row.get("volume"))
        if close <= 0 or high <= 0 or low <= 0 or high < low:
            return None
        bar = {
            "date": asof_date or self._client.et_today().isoformat(),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
        self.cache[cache_key] = bar
        return bar

    def get_api_stats(self) -> dict[str, Any]:
        return {
            "api_calls_made": self.api_calls_made,
            "max_api_calls": self.max_api_calls,
            "budget_remaining": max(0, self.max_api_calls - self.api_calls_made),
            "cache_entries": len(self.cache),
            "rate_limit_reached": self.rate_limit_reached,
        }


def normalize_symbol(value: Any) -> str:
    """Normalize a symbol string while preserving FMP-style class-share dashes."""
    if value is None:
        return ""
    symbol = str(value).strip().upper()
    if not symbol or symbol in {"NAN", "NULL", "NONE"}:
        return ""
    return symbol.replace(".", "-")


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


def safe_round(value: Any, digits: int = 2) -> float:
    return round(to_float(value), digits)


def normalize_bars(raw_bars: list[dict[str, Any]], limit: int | None = None) -> list[Bar]:
    """Normalize raw OHLCV dicts into most-recent-first Bar objects."""
    bars: list[Bar] = []
    for row in raw_bars or []:
        if not isinstance(row, dict):
            continue
        close_value = (
            row.get("close") if row.get("close") not in (None, "") else row.get("adjClose")
        )
        close = to_float(close_value)
        open_ = to_float(row.get("open"), default=close)
        high = to_float(row.get("high"), default=max(open_, close))
        low = to_float(row.get("low"), default=min(open_, close))
        bar = Bar(
            date=str(row.get("date") or row.get("timestamp") or row.get("datetime") or "")[:10],
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=to_int(row.get("volume")),
        )
        if not bar.date or min(bar.open, bar.high, bar.low, bar.close) <= 0:
            continue
        if bar.high < bar.low:
            continue
        bars.append(bar)

    dedup: dict[str, Bar] = {bar.date: bar for bar in bars}
    bars = [dedup[k] for k in sorted(dedup.keys(), reverse=True)]
    if limit is not None:
        bars = bars[:limit]
    return bars


def normalize_fmp_historical_response(data: Any, symbol: str, limit: int) -> list[dict[str, Any]]:
    """Normalize FMP stable/v3 historical responses to raw bar dicts."""
    if not data:
        return []
    if isinstance(data, list):
        rows = []
        for row in data:
            if not isinstance(row, dict):
                continue
            row_symbol = normalize_symbol(row.get("symbol") or symbol)
            if row_symbol == normalize_symbol(symbol):
                rows.append({k: v for k, v in row.items() if k != "symbol"})
        return rows[:limit]
    if isinstance(data, dict):
        if isinstance(data.get("historical"), list):
            return data["historical"][:limit]
        if isinstance(data.get("historicalStockList"), list):
            target = normalize_symbol(symbol)
            for entry in data["historicalStockList"]:
                if normalize_symbol(entry.get("symbol")) == target:
                    return (entry.get("historical") or [])[:limit]
    return []


def merge_quote_bar(bars: list[Bar], quote_bar: dict[str, Any] | None, limit: int) -> list[Bar]:
    """Insert or replace latest bar with a quote-derived current-day bar."""
    if not quote_bar:
        return bars
    quote = normalize_bars([quote_bar], limit=1)
    if not quote:
        return bars
    latest = quote[0]
    remaining = [bar for bar in bars if bar.date != latest.date]
    return normalize_bars(
        [bar_to_dict(latest)] + [bar_to_dict(bar) for bar in remaining], limit=limit
    )


def bar_to_dict(bar: Bar) -> dict[str, Any]:
    return {
        "date": bar.date,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def read_universe_file(path: str) -> list[str]:
    """Read symbols from CSV, JSON, or plain-text file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        data = json.loads(text)
        values: list[Any]
        if isinstance(data, list):
            values = data
        elif isinstance(data, dict):
            values = data.get("symbols") or data.get("universe") or data.get("tickers") or []
        else:
            values = []
        symbols = []
        for item in values:
            if isinstance(item, dict):
                symbols.append(normalize_symbol(item.get("symbol") or item.get("ticker")))
            else:
                symbols.append(normalize_symbol(item))
        return sorted({s for s in symbols if s})

    if p.suffix.lower() == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames:
            lower_fields = {f.lower(): f for f in reader.fieldnames}
            symbol_field = (
                lower_fields.get("symbol")
                or lower_fields.get("ticker")
                or lower_fields.get("tickers")
                or reader.fieldnames[0]
            )
            return sorted({normalize_symbol(row.get(symbol_field)) for row in reader if row})

    symbols = []
    for line in text.splitlines():
        token = line.split(",")[0].strip()
        if token and not token.startswith("#"):
            symbols.append(normalize_symbol(token))
    return sorted({s for s in symbols if s})


def read_prices_json(path: str) -> dict[str, list[Bar]]:
    """Read offline OHLCV JSON in one of several common shapes."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    by_symbol: dict[str, list[dict[str, Any]]] = {}

    if isinstance(data, dict) and "symbols" in data and isinstance(data["symbols"], dict):
        data = data["symbols"]
    if isinstance(data, dict) and "prices" in data and isinstance(data["prices"], dict):
        data = data["prices"]

    if isinstance(data, dict):
        for symbol, value in data.items():
            if isinstance(value, dict) and isinstance(value.get("historical"), list):
                by_symbol[normalize_symbol(symbol)] = value["historical"]
            elif isinstance(value, dict) and isinstance(value.get("bars"), list):
                by_symbol[normalize_symbol(symbol)] = value["bars"]
            elif isinstance(value, list):
                by_symbol[normalize_symbol(symbol)] = value
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = normalize_symbol(item.get("symbol") or item.get("ticker"))
            historical = item.get("historical") or item.get("bars") or item.get("prices")
            if symbol and isinstance(historical, list):
                by_symbol[symbol] = historical

    normalized: dict[str, list[Bar]] = {}
    for symbol, rows in by_symbol.items():
        bars = normalize_bars(rows)
        if symbol and bars:
            normalized[symbol] = bars
    return normalized


def read_profiles_json(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Profiles file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict) and "profiles" in data and isinstance(data["profiles"], dict):
        data = data["profiles"]
    if isinstance(data, dict):
        for symbol, row in data.items():
            if isinstance(row, dict):
                result[normalize_symbol(symbol)] = row
    elif isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            symbol = normalize_symbol(row.get("symbol") or row.get("ticker"))
            if symbol:
                result[symbol] = row
    return result


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct_change(new: float, old: float) -> float:
    if old <= 0:
        return 0.0
    return ((new / old) - 1.0) * 100.0


def close_location_pct(bar: Bar) -> float:
    day_range = bar.high - bar.low
    if day_range <= 0:
        return 50.0
    return ((bar.close - bar.low) / day_range) * 100.0


def simple_moving_average(bars: list[Bar], start: int, length: int) -> float:
    window = bars[start : start + length]
    return average([bar.close for bar in window]) if window else 0.0


def consecutive_down_closes_before_latest(bars: list[Bar], max_days: int = 7) -> int:
    streak = 0
    for idx in range(1, min(len(bars) - 1, max_days) + 1):
        if bars[idx].close < bars[idx + 1].close:
            streak += 1
        else:
            break
    return streak


def detect_hammer_profile(bars: list[Bar], args: argparse.Namespace) -> HammerProfile:
    latest = bars[0]
    prev = bars[1]
    day_range = latest.high - latest.low
    if day_range <= 0:
        day_range = 0.000001
    body = abs(latest.close - latest.open)
    lower_wick = max(0.0, min(latest.open, latest.close) - latest.low)
    upper_wick = max(0.0, latest.high - max(latest.open, latest.close))
    close_loc = close_location_pct(latest)
    lower_wick_to_body = lower_wick / body if body > 0 else 999.0
    recovery_from_low = pct_change(latest.close, latest.low)
    day_gain = pct_change(latest.close, prev.close)
    dollar_gain = latest.close - latest.open

    lower_pct = (lower_wick / day_range) * 100.0
    body_pct = (body / day_range) * 100.0
    upper_pct = (upper_wick / day_range) * 100.0
    day_range_pct = (day_range / latest.close) * 100.0 if latest.close > 0 else 0.0

    tags: list[str] = []
    if lower_pct >= args.min_lower_wick_pct:
        tags.append("long_lower_wick")
    if body_pct <= args.max_body_pct:
        tags.append("small_body")
    if close_loc >= args.min_close_location_pct:
        tags.append("strong_close_location")
    if lower_wick_to_body >= args.min_lower_wick_to_body:
        tags.append("wick_body_asymmetry")
    if recovery_from_low >= args.min_recovery_from_low_pct:
        tags.append("recovered_from_low")
    if latest.close >= latest.open:
        tags.append("green_or_flat_close")
    if upper_pct <= args.max_upper_wick_pct:
        tags.append("controlled_upper_wick")

    primary = "selling_exhaustion_hammer"
    if {"long_lower_wick", "small_body", "strong_close_location"}.issubset(set(tags)):
        primary = "confirmed_exhaustion_hammer"

    return HammerProfile(
        day_range=day_range,
        day_range_pct=day_range_pct,
        body=body,
        body_pct_of_range=body_pct,
        lower_wick=lower_wick,
        lower_wick_pct_of_range=lower_pct,
        upper_wick=upper_wick,
        upper_wick_pct_of_range=upper_pct,
        lower_wick_to_body=lower_wick_to_body,
        close_location_pct=close_loc,
        recovery_from_low_pct=recovery_from_low,
        day_gain_pct=day_gain,
        dollar_gain=dollar_gain,
        green_close=latest.close >= latest.open,
        hammer_tags=tags,
        primary_trigger=primary,
    )


def detect_pullback_profile(bars: list[Bar], args: argparse.Namespace) -> PullbackProfile:
    latest = bars[0]
    prior_window = bars[1 : 1 + args.recent_high_lookback]
    if not prior_window:
        return PullbackProfile(0, "", 0, 0, 0, "", False, 0, 0, 0, 0, 0, False, 0, 0)

    recent_high_bar = max(prior_window, key=lambda bar: bar.high)
    days_since_high = bars.index(recent_high_bar)
    pullback_pct = pct_change(latest.close, recent_high_bar.high)

    low_window = bars[1 : 1 + args.undercut_lookback]
    prior_low_bar = min(low_window, key=lambda bar: bar.low) if low_window else bars[1]
    prior_low = prior_low_bar.low
    undercut = latest.low < prior_low
    reclaim = latest.close > prior_low
    low_undercut_pct = pct_change(latest.low, prior_low) if prior_low > 0 else 0.0

    prior_10 = bars[1:11]
    down_days_10 = sum(1 for bar in prior_10 if bar.close < bar.open)
    lower_closes_5 = 0
    for idx in range(1, min(len(bars) - 1, 6)):
        if bars[idx].close < bars[idx + 1].close:
            lower_closes_5 += 1
    down_streak = consecutive_down_closes_before_latest(bars)

    ma10 = simple_moving_average(bars, 1, min(10, len(bars) - 1))
    ma50 = simple_moving_average(bars, 0, min(50, len(bars)))
    below_10dma_pct = pct_change(latest.close, ma10) if ma10 > 0 else 0.0
    above_50dma = latest.close >= ma50 if ma50 > 0 else False

    return_20d = pct_change(bars[1].close, bars[21].close) if len(bars) > 21 else 0.0
    return_60d = pct_change(bars[1].close, bars[61].close) if len(bars) > 61 else 0.0

    return PullbackProfile(
        recent_high=recent_high_bar.high,
        recent_high_date=recent_high_bar.date,
        days_since_recent_high=days_since_high,
        pullback_pct_from_high=pullback_pct,
        prior_low=prior_low,
        prior_low_date=prior_low_bar.date,
        undercut_reclaim=undercut and reclaim,
        low_undercut_pct=low_undercut_pct,
        down_days_10=down_days_10,
        lower_closes_5=lower_closes_5,
        consecutive_down_closes=down_streak,
        below_10dma_pct=below_10dma_pct,
        above_50dma=above_50dma,
        return_20d_pct=return_20d,
        return_60d_pct=return_60d,
    )


def detect_quality_profile(
    bars: list[Bar], profile_row: dict[str, Any] | None, args: argparse.Namespace
) -> QualityProfile:
    latest = bars[0]
    prev = bars[1]
    avg_volume_20d = average([float(bar.volume) for bar in bars[1:21]])
    avg_dollar_volume_20d = average([bar.close * float(bar.volume) for bar in bars[1:21]])
    volume_ratio_1d = latest.volume / prev.volume if prev.volume > 0 else 0.0
    volume_ratio_20d = latest.volume / avg_volume_20d if avg_volume_20d > 0 else 0.0
    row = profile_row or {}
    market_cap = to_float(row.get("marketCap") or row.get("mktCap") or row.get("market_cap"))
    institutional_ownership_pct = to_float(
        row.get("institutionalOwnershipPct")
        or row.get("institutionalOwnership")
        or row.get("institutional_ownership_pct")
    )
    mutual_fund_holders = to_int(
        row.get("mutualFundHolders") or row.get("mutual_fund_holders") or row.get("fundHolderCount")
    )
    institutional_holders = to_int(
        row.get("institutionalHolders")
        or row.get("institutional_holders")
        or row.get("institutionalHolderCount")
    )
    return QualityProfile(
        avg_volume_20d=avg_volume_20d,
        avg_dollar_volume_20d=avg_dollar_volume_20d,
        volume_ratio_1d=volume_ratio_1d,
        volume_ratio_20d=volume_ratio_20d,
        market_cap=market_cap,
        institutional_ownership_pct=institutional_ownership_pct,
        mutual_fund_holders=mutual_fund_holders,
        institutional_holders=institutional_holders,
    )


def quality_score(quality: QualityProfile, latest: Bar, args: argparse.Namespace) -> int:
    score = 0
    if latest.close >= args.min_price * 2:
        score += 4
    elif latest.close >= args.min_price:
        score += 3

    if quality.avg_dollar_volume_20d >= args.min_avg_dollar_volume * 3:
        score += 6
    elif quality.avg_dollar_volume_20d >= args.min_avg_dollar_volume:
        score += 5
    elif latest.volume >= args.min_volume:
        score += 2

    if quality.market_cap >= args.min_market_cap * 5:
        score += 5
    elif quality.market_cap >= args.min_market_cap:
        score += 4
    elif quality.market_cap <= 0:
        score += 2  # Unknown profile should not make offline mode unusable.

    if quality.mutual_fund_holders >= 1000 or quality.institutional_holders >= 1000:
        score += 3
    elif quality.institutional_ownership_pct >= 40:
        score += 2

    if quality.avg_volume_20d >= args.min_volume:
        score += 2
    return min(20, score)


def prior_momentum_score(pullback: PullbackProfile, args: argparse.Namespace) -> int:
    score = 0
    if args.min_days_since_high <= pullback.days_since_recent_high <= args.max_days_since_high:
        score += 5
    elif pullback.days_since_recent_high <= args.recent_high_lookback:
        score += 2

    if pullback.return_60d_pct >= 30:
        score += 5
    elif pullback.return_60d_pct >= 15:
        score += 4
    elif pullback.return_20d_pct >= 10:
        score += 3

    if pullback.above_50dma:
        score += 3
    if pullback.recent_high > 0:
        score += 2
    return min(15, score)


def pullback_exhaustion_score(
    pullback: PullbackProfile, quality: QualityProfile, args: argparse.Namespace
) -> int:
    score = 0
    depth = abs(pullback.pullback_pct_from_high)
    if args.min_pullback_pct <= depth <= min(25.0, args.max_pullback_pct):
        score += 6
    elif depth <= args.max_pullback_pct:
        score += 4

    if pullback.undercut_reclaim:
        score += 6
    elif pullback.low_undercut_pct < 0:
        score += 3

    if pullback.down_days_10 >= 5:
        score += 3
    elif pullback.down_days_10 >= 3:
        score += 2

    if pullback.lower_closes_5 >= 3 or pullback.consecutive_down_closes >= 2:
        score += 2

    if quality.volume_ratio_20d >= 1.5:
        score += 3
    elif quality.volume_ratio_20d >= 1.0:
        score += 2
    return min(20, score)


def hammer_geometry_score(hammer: HammerProfile, args: argparse.Namespace) -> int:
    score = 0
    if hammer.lower_wick_pct_of_range >= 60:
        score += 8
    elif hammer.lower_wick_pct_of_range >= args.min_lower_wick_pct:
        score += 6

    if hammer.body_pct_of_range <= 20:
        score += 5
    elif hammer.body_pct_of_range <= args.max_body_pct:
        score += 4

    if hammer.close_location_pct >= 75:
        score += 5
    elif hammer.close_location_pct >= args.min_close_location_pct:
        score += 4

    if hammer.lower_wick_to_body >= 3:
        score += 3
    elif hammer.lower_wick_to_body >= args.min_lower_wick_to_body:
        score += 2

    if hammer.recovery_from_low_pct >= args.min_recovery_from_low_pct * 2:
        score += 2
    elif hammer.recovery_from_low_pct >= args.min_recovery_from_low_pct:
        score += 1

    if hammer.green_close:
        score += 1
    if hammer.upper_wick_pct_of_range <= args.max_upper_wick_pct:
        score += 1
    return min(25, score)


def risk_distance_score(risk_pct_to_stop: float) -> int:
    if risk_pct_to_stop <= 0:
        return 0
    if risk_pct_to_stop <= 3.0:
        return 15
    if risk_pct_to_stop <= 5.0:
        return 12
    if risk_pct_to_stop <= 7.5:
        return 9
    if risk_pct_to_stop <= 10.0:
        return 6
    if risk_pct_to_stop <= 12.0:
        return 3
    return 0


def market_gate_score(market_gate: str) -> int:
    if market_gate == "allowed":
        return 5
    if market_gate == "neutral":
        return 3
    return 0


def score_to_rating(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 82:
        return "A-"
    if score >= 70:
        return "B"
    if score >= 55:
        return "Watch"
    return "Reject"


def score_to_state(score: int, market_gate: str, hard_rejected: bool) -> str:
    if hard_rejected:
        return "REJECTED"
    if market_gate == "restrictive" and score >= 70:
        return "MANUAL_REVIEW_ONLY"
    if score >= 82:
        return "ACTIONABLE_CLOSE_BUY"
    if score >= 70:
        return "MANUAL_REVIEW"
    if score >= 55:
        return "WATCH_TOMORROW"
    return "REJECTED"


def detect_soft_failure_tags(
    hammer: HammerProfile,
    pullback: PullbackProfile,
    quality: QualityProfile,
    risk_pct_to_stop: float,
    args: argparse.Namespace,
) -> list[str]:
    tags: list[str] = []
    if not pullback.undercut_reclaim:
        tags.append("no_undercut_reclaim")
    if abs(pullback.pullback_pct_from_high) > 25:
        tags.append("deep_pullback")
    if pullback.days_since_recent_high > args.max_days_since_high:
        tags.append("stale_high")
    if quality.volume_ratio_20d < 0.8:
        tags.append("weak_volume_confirmation")
    if hammer.close_location_pct < 70:
        tags.append("moderate_close_location")
    if hammer.day_gain_pct < -3:
        tags.append("still_down_big_on_day")
    if risk_pct_to_stop >= 8:
        tags.append("wide_risk")
    return tags


def analyze_symbol(
    symbol: str,
    bars: list[Bar],
    args: argparse.Namespace,
    profile_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze one symbol and return a structured result."""
    symbol = normalize_symbol(symbol)
    reject_reasons: list[str] = []
    min_history = max(30, args.recent_high_lookback + 2, args.undercut_lookback + 2)
    if len(bars) < min_history:
        return {
            "symbol": symbol,
            "state": "REJECTED",
            "rating": "Reject",
            "setup_score": 0,
            "reject_reasons": ["insufficient_history"],
        }

    latest = bars[0]
    prev = bars[1]
    if latest.close < args.min_price:
        reject_reasons.append("below_min_price")
    if latest.volume < args.min_volume:
        reject_reasons.append("below_min_volume")

    hammer = detect_hammer_profile(bars, args)
    pullback = detect_pullback_profile(bars, args)
    quality = detect_quality_profile(bars, profile_row, args)

    if quality.avg_dollar_volume_20d < args.min_avg_dollar_volume:
        reject_reasons.append("below_min_avg_dollar_volume")
    if quality.market_cap > 0 and quality.market_cap < args.min_market_cap:
        reject_reasons.append("below_min_market_cap")

    if hammer.lower_wick_pct_of_range < args.min_lower_wick_pct:
        reject_reasons.append("lower_wick_too_small")
    if hammer.body_pct_of_range > args.max_body_pct:
        reject_reasons.append("body_too_large")
    if hammer.close_location_pct < args.min_close_location_pct:
        reject_reasons.append("weak_close_location")
    if hammer.lower_wick_to_body < args.min_lower_wick_to_body:
        reject_reasons.append("weak_wick_body_asymmetry")
    if hammer.recovery_from_low_pct < args.min_recovery_from_low_pct:
        reject_reasons.append("insufficient_recovery_from_low")

    pullback_depth = abs(pullback.pullback_pct_from_high)
    if pullback_depth < args.min_pullback_pct:
        reject_reasons.append("pullback_too_shallow")
    if pullback_depth > args.max_pullback_pct:
        reject_reasons.append("pullback_too_deep")
    if pullback.days_since_recent_high < args.min_days_since_high:
        reject_reasons.append("too_close_to_recent_high")
    if pullback.days_since_recent_high > args.max_days_since_high:
        reject_reasons.append("recent_high_too_stale")
    if args.require_undercut_reclaim and not pullback.undercut_reclaim:
        reject_reasons.append("missing_undercut_reclaim")

    entry_reference = latest.close
    stop_reference = latest.low * (1.0 - args.stop_buffer_pct / 100.0)
    risk_pct_to_stop = ((entry_reference - stop_reference) / entry_reference) * 100
    if entry_reference <= stop_reference:
        reject_reasons.append("invalid_stop_reference")
    if risk_pct_to_stop > args.max_risk_pct_to_stop:
        reject_reasons.append("risk_too_wide")

    components = {
        "quality": quality_score(quality, latest, args),
        "prior_momentum": prior_momentum_score(pullback, args),
        "pullback_exhaustion": pullback_exhaustion_score(pullback, quality, args),
        "hammer_geometry": hammer_geometry_score(hammer, args),
        "risk_distance": risk_distance_score(risk_pct_to_stop),
        "market_gate": market_gate_score(args.market_gate),
    }
    composite_score = int(sum(components.values()))
    hard_rejected = bool(reject_reasons)
    rating = score_to_rating(composite_score if not hard_rejected else 0)
    state = score_to_state(composite_score, args.market_gate, hard_rejected)

    trigger_tags = sorted(set(hammer.hammer_tags + ["selling_exhaustion", "pullback_reversal"]))
    if pullback.undercut_reclaim:
        trigger_tags.append("undercut_reclaim")
    if quality.volume_ratio_20d >= 1.5:
        trigger_tags.append("volume_shock")

    return {
        "symbol": symbol,
        "date": latest.date,
        "state": state,
        "rating": rating,
        "setup_score": composite_score if not hard_rejected else 0,
        "raw_setup_score": composite_score,
        "primary_trigger": hammer.primary_trigger,
        "trigger_tags": trigger_tags,
        "day_gain_pct": safe_round(hammer.day_gain_pct),
        "dollar_gain": safe_round(hammer.dollar_gain),
        "close": safe_round(latest.close),
        "prev_close": safe_round(prev.close),
        "open": safe_round(latest.open),
        "high": safe_round(latest.high),
        "low": safe_round(latest.low),
        "volume": latest.volume,
        "prev_volume": prev.volume,
        "avg_volume_20d": safe_round(quality.avg_volume_20d, 0),
        "avg_dollar_volume_20d": safe_round(quality.avg_dollar_volume_20d, 0),
        "volume_ratio_1d": safe_round(quality.volume_ratio_1d, 2),
        "volume_ratio_20d": safe_round(quality.volume_ratio_20d, 2),
        "current_range_pct": safe_round(hammer.day_range_pct),
        "current_range_dollars": safe_round(hammer.day_range),
        "close_location_pct": safe_round(hammer.close_location_pct),
        "body_pct_of_range": safe_round(hammer.body_pct_of_range),
        "lower_wick_pct_of_range": safe_round(hammer.lower_wick_pct_of_range),
        "upper_wick_pct_of_range": safe_round(hammer.upper_wick_pct_of_range),
        "lower_wick_to_body": safe_round(hammer.lower_wick_to_body, 2),
        "recovery_from_low_pct": safe_round(hammer.recovery_from_low_pct),
        "recent_high": safe_round(pullback.recent_high),
        "recent_high_date": pullback.recent_high_date,
        "days_since_recent_high": pullback.days_since_recent_high,
        "pullback_pct_from_high": safe_round(pullback.pullback_pct_from_high),
        "prior_low": safe_round(pullback.prior_low),
        "prior_low_date": pullback.prior_low_date,
        "undercut_reclaim": pullback.undercut_reclaim,
        "low_undercut_pct": safe_round(pullback.low_undercut_pct),
        "down_days_10": pullback.down_days_10,
        "lower_closes_5": pullback.lower_closes_5,
        "consecutive_down_closes": pullback.consecutive_down_closes,
        "below_10dma_pct": safe_round(pullback.below_10dma_pct),
        "above_50dma": pullback.above_50dma,
        "return_20d_pct": safe_round(pullback.return_20d_pct),
        "return_60d_pct": safe_round(pullback.return_60d_pct),
        "market_cap": safe_round(quality.market_cap, 0),
        "institutional_ownership_pct": safe_round(quality.institutional_ownership_pct),
        "mutual_fund_holders": quality.mutual_fund_holders,
        "institutional_holders": quality.institutional_holders,
        "entry_reference": safe_round(entry_reference),
        "stop_reference": safe_round(stop_reference),
        "risk_pct_to_stop": safe_round(risk_pct_to_stop),
        "exit_template": "low_of_day_stop_then_3_to_5_day_follow_through_review",
        "components": components,
        "soft_failure_tags": detect_soft_failure_tags(
            hammer, pullback, quality, risk_pct_to_stop, args
        ),
        "reject_reasons": reject_reasons,
        "downstream_action": downstream_action(state, rating),
    }


def downstream_action(state: str, rating: str) -> str:
    if state == "ACTIONABLE_CLOSE_BUY":
        return (
            "Near-close candidate. Manually validate chart, news/earnings risk, and size from "
            "entry_reference to stop_reference before any order."
        )
    if state == "MANUAL_REVIEW":
        return "Manual chart review; consider next-day hammer-high trigger or reduced risk only if upgraded."
    if state == "MANUAL_REVIEW_ONLY":
        return "Market gate is restrictive; study/model-book only unless a documented exception is approved."
    if state == "WATCH_TOMORROW":
        return "Watch for next-day follow-through, hammer-high reclaim, or tighter risk."
    return "Do not trade from this screen; retain only for review statistics."


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stockbee Exhaustion Hammer Screener")

    # Input modes
    parser.add_argument("--api-key", help="FMP API key; defaults to FMP_API_KEY")
    parser.add_argument(
        "--fmp-universe", action="store_true", help="Fetch a broad US universe from FMP"
    )
    parser.add_argument("--symbols", nargs="*", default=[], help="Explicit symbols to scan")
    parser.add_argument("--universe-file", help="CSV, JSON, or TXT file containing symbols")
    parser.add_argument("--prices-json", help="Offline OHLCV JSON keyed by symbol")
    parser.add_argument(
        "--profiles-json",
        help="Optional JSON keyed by symbol with marketCap / holder quality metadata",
    )

    # API / universe controls
    parser.add_argument("--max-symbols", type=int, default=300, help="Maximum symbols to process")
    parser.add_argument("--history-days", type=int, default=120, help="Daily bars per symbol")
    parser.add_argument("--max-api-calls", type=int, default=700, help="FMP API call budget")
    parser.add_argument(
        "--use-quote-latest",
        action="store_true",
        help="Best-effort FMP quote override for near-close current-day OHLCV",
    )
    parser.add_argument(
        "--asof-date",
        help="Date to assign quote-derived near-close bar; defaults to the America/New_York date",
    )

    # Liquidity / quality gates
    parser.add_argument("--min-price", type=float, default=20.0, help="Minimum latest close")
    parser.add_argument("--min-volume", type=int, default=100_000, help="Minimum latest volume")
    parser.add_argument(
        "--min-avg-dollar-volume",
        type=float,
        default=20_000_000,
        help="Minimum 20-day average dollar volume",
    )
    parser.add_argument(
        "--min-market-cap", type=float, default=2_000_000_000, help="FMP/profile market cap floor"
    )

    # Pullback/exhaustion thresholds
    parser.add_argument("--recent-high-lookback", type=int, default=40)
    parser.add_argument("--min-days-since-high", type=int, default=3)
    parser.add_argument("--max-days-since-high", type=int, default=30)
    parser.add_argument("--min-pullback-pct", type=float, default=6.0)
    parser.add_argument("--max-pullback-pct", type=float, default=35.0)
    parser.add_argument("--undercut-lookback", type=int, default=5)
    parser.add_argument(
        "--require-undercut-reclaim",
        action="store_true",
        help="Hard-reject candidates that do not undercut and reclaim prior short-term low",
    )

    # Hammer geometry thresholds
    parser.add_argument("--min-lower-wick-pct", type=float, default=40.0)
    parser.add_argument("--max-body-pct", type=float, default=35.0)
    parser.add_argument("--max-upper-wick-pct", type=float, default=35.0)
    parser.add_argument("--min-close-location-pct", type=float, default=60.0)
    parser.add_argument("--min-lower-wick-to-body", type=float, default=1.5)
    parser.add_argument("--min-recovery-from-low-pct", type=float, default=2.0)

    # Risk / market controls
    parser.add_argument("--max-risk-pct-to-stop", type=float, default=12.0)
    parser.add_argument("--stop-buffer-pct", type=float, default=0.10)
    parser.add_argument(
        "--market-gate",
        choices=["allowed", "neutral", "restrictive"],
        default="neutral",
        help="Latest market-regime/exposure decision",
    )

    # Output controls
    parser.add_argument("--top", type=int, default=50, help="Top non-rejected candidates in report")
    parser.add_argument(
        "--include-rejected", action="store_true", help="Include rejected names in markdown"
    )
    parser.add_argument("--output-dir", default="reports/", help="Output directory")

    return parser.parse_args()


def build_symbol_list(args: argparse.Namespace) -> list[str]:
    symbols = {normalize_symbol(s) for s in args.symbols if normalize_symbol(s)}
    if args.universe_file:
        symbols.update(read_universe_file(args.universe_file))
    return sorted(symbols)[: args.max_symbols]


def collect_price_data(
    args: argparse.Namespace,
) -> tuple[dict[str, list[Bar]], dict[str, dict[str, Any]], dict[str, Any] | None]:
    """Collect price data from offline JSON or FMP."""
    profiles = read_profiles_json(args.profiles_json)
    if args.prices_json:
        offline = read_prices_json(args.prices_json)
        explicit_symbols = set(build_symbol_list(args))
        if explicit_symbols:
            offline = {s: bars for s, bars in offline.items() if s in explicit_symbols}
        else:
            capped_symbols = sorted(offline)[: args.max_symbols]
            offline = {symbol: offline[symbol] for symbol in capped_symbols}
        return offline, profiles, None

    client = FMPClient(api_key=args.api_key, max_api_calls=args.max_api_calls)

    if args.fmp_universe:
        universe_rows = client.get_universe(
            min_market_cap=args.min_market_cap,
            min_price=args.min_price,
            min_volume=args.min_volume,
            max_symbols=args.max_symbols,
        )
        symbols = [row["symbol"] for row in universe_rows]
        for row in universe_rows:
            profiles[row["symbol"]] = row
    else:
        symbols = build_symbol_list(args)

    if not symbols:
        raise ValueError(
            "No symbols to process. Use --fmp-universe, --symbols, --universe-file, or --prices-json."
        )

    price_data: dict[str, list[Bar]] = {}
    for idx, symbol in enumerate(symbols, 1):
        if idx % 25 == 0 or idx == len(symbols):
            print(f"  Fetching history: {idx}/{len(symbols)}", flush=True)
        try:
            raw = client.get_historical_prices(symbol, days=args.history_days)
            bars = normalize_bars(raw, limit=args.history_days)
            if args.use_quote_latest:
                quote_bar = client.get_quote_bar(symbol, asof_date=args.asof_date)
                bars = merge_quote_bar(bars, quote_bar, limit=args.history_days)
        except ApiCallBudgetExceeded:
            print(f"WARNING: API budget exhausted at {symbol}. Processing collected data.")
            break
        if bars:
            price_data[symbol] = bars

    return price_data, profiles, client.get_api_stats()


def sort_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    state_priority = {
        "ACTIONABLE_CLOSE_BUY": 0,
        "MANUAL_REVIEW": 1,
        "MANUAL_REVIEW_ONLY": 2,
        "WATCH_TOMORROW": 3,
        "REJECTED": 4,
    }
    return sorted(
        results,
        key=lambda row: (state_priority.get(row.get("state"), 9), -row.get("setup_score", 0)),
    )


def generate_json_report(
    results: list[dict[str, Any]], metadata: dict[str, Any], output_path: str
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "metadata": metadata,
        "candidates": results,
    }
    Path(output_path).write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def format_candidate_md(row: dict[str, Any]) -> str:
    tags = ", ".join(row.get("trigger_tags") or []) or "none"
    rejects = ", ".join(row.get("reject_reasons") or []) or "none"
    soft = ", ".join(row.get("soft_failure_tags") or []) or "none"

    def fmt(value: Any) -> str:
        return "n/a" if value is None else str(value)

    volume = row.get("volume")
    volume_str = f"{volume:,}" if isinstance(volume, (int, float)) else "n/a"
    return "\n".join(
        [
            f"### {row['symbol']} — {fmt(row.get('rating'))} / {fmt(row.get('setup_score'))}",
            "",
            f"- State: `{fmt(row.get('state'))}`",
            f"- Trigger: `{fmt(row.get('primary_trigger'))}` ({tags})",
            f"- Price: close {fmt(row.get('close'))}, day gain {fmt(row.get('day_gain_pct'))}%, "
            f"range {fmt(row.get('current_range_pct'))}%",
            f"- Hammer: lower wick {fmt(row.get('lower_wick_pct_of_range'))}%, "
            f"body {fmt(row.get('body_pct_of_range'))}%, close location "
            f"{fmt(row.get('close_location_pct'))}%",
            f"- Pullback: {fmt(row.get('pullback_pct_from_high'))}% from recent high "
            f"{fmt(row.get('recent_high'))} on {fmt(row.get('recent_high_date'))}; "
            f"undercut reclaim = {fmt(row.get('undercut_reclaim'))}",
            f"- Volume: {volume_str} "
            f"({fmt(row.get('volume_ratio_1d'))}x previous day, "
            f"{fmt(row.get('volume_ratio_20d'))}x 20d avg)",
            f"- Entry / stop reference: {fmt(row.get('entry_reference'))} / "
            f"{fmt(row.get('stop_reference'))} ({fmt(row.get('risk_pct_to_stop'))}% risk to stop)",
            f"- Components: {fmt(row.get('components'))}",
            f"- Soft failure tags: {soft}",
            f"- Reject reasons: {rejects}",
            f"- Downstream action: {fmt(row.get('downstream_action'))}",
            "",
        ]
    )


def generate_markdown_report(
    results: list[dict[str, Any]],
    metadata: dict[str, Any],
    output_path: str,
    top: int,
    include_rejected: bool,
) -> None:
    counts: dict[str, int] = {}
    for row in results:
        counts[row.get("state", "UNKNOWN")] = counts.get(row.get("state", "UNKNOWN"), 0) + 1

    non_rejected = [r for r in results if r.get("state") != "REJECTED"]
    displayed_candidates = non_rejected[:top]
    rejected = [r for r in results if r.get("state") == "REJECTED"]

    lines = [
        "# Stockbee Exhaustion Hammer Report",
        "",
        f"Generated at: {metadata['generated_at']}",
        f"Market gate: `{metadata['market_gate']}`",
        f"Input mode: `{metadata['input_mode']}`",
        f"Near-close quote override: `{metadata.get('use_quote_latest')}`",
        "",
        "## Summary",
        "",
        f"- Symbols processed: {metadata['symbols_processed']}",
        f"- Non-rejected candidates: {len(non_rejected)}",
        f"- Rejected candidates: {len(rejected)}",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for state in [
        "ACTIONABLE_CLOSE_BUY",
        "MANUAL_REVIEW",
        "MANUAL_REVIEW_ONLY",
        "WATCH_TOMORROW",
        "REJECTED",
    ]:
        lines.append(f"| {state} | {counts.get(state, 0)} |")

    lines.extend(["", "## Candidates", ""])
    if displayed_candidates:
        for row in displayed_candidates:
            lines.append(format_candidate_md(row))
    else:
        lines.append("No non-rejected candidates found.")
        lines.append("")

    if include_rejected and rejected:
        lines.extend(["", "## Rejected", ""])
        for row in rejected[: min(50, len(rejected))]:
            lines.append(format_candidate_md(row))

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_arguments()
    print("=" * 72)
    print("Stockbee Exhaustion Hammer Screener")
    print("=" * 72)

    try:
        price_data, profiles, api_stats = collect_price_data(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not price_data:
        print("No price data found. Exiting.")
        sys.exit(0)

    print(f"  Symbols with price data: {len(price_data)}")
    results = []
    for symbol, bars in price_data.items():
        results.append(analyze_symbol(symbol, bars, args, profile_row=profiles.get(symbol)))

    results = sort_results(results)
    input_mode = (
        "prices_json" if args.prices_json else "fmp_universe" if args.fmp_universe else "symbols"
    )
    metadata = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input_mode": input_mode,
        "symbols_processed": len(price_data),
        "market_gate": args.market_gate,
        "use_quote_latest": bool(args.use_quote_latest),
        "thresholds": {
            "min_price": args.min_price,
            "min_volume": args.min_volume,
            "min_avg_dollar_volume": args.min_avg_dollar_volume,
            "min_market_cap": args.min_market_cap,
            "min_pullback_pct": args.min_pullback_pct,
            "max_pullback_pct": args.max_pullback_pct,
            "min_lower_wick_pct": args.min_lower_wick_pct,
            "max_body_pct": args.max_body_pct,
            "min_close_location_pct": args.min_close_location_pct,
            "max_risk_pct_to_stop": args.max_risk_pct_to_stop,
        },
        "api_stats": api_stats,
    }

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_path = os.path.join(args.output_dir, f"stockbee_exhaustion_hammer_{timestamp}.json")
    md_path = os.path.join(args.output_dir, f"stockbee_exhaustion_hammer_{timestamp}.md")

    generate_json_report(results, metadata, json_path)
    generate_markdown_report(
        results, metadata, md_path, top=args.top, include_rejected=args.include_rejected
    )

    print()
    print("Screening complete")
    print(f"  JSON Report:     {json_path}")
    print(f"  Markdown Report: {md_path}")
    top = [r for r in results if r.get("state") != "REJECTED"][:5]
    if top:
        print()
        print("Top candidates:")
        for idx, row in enumerate(top, 1):
            print(
                f"  {idx}. {row['symbol']:6} {row['state']:22} "
                f"Score: {row['setup_score']:3} ({row['rating']}) "
                f"Trigger: {row['primary_trigger']}"
            )


if __name__ == "__main__":
    main()
