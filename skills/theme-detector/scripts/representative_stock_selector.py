#!/usr/bin/env python3
"""
Representative Stock Selector - Dynamic stock selection for theme detection.

Selects representative stocks for market themes using a fallback chain:
1. FINVIZ Elite industry screener (paid API)
2. FINVIZ Public screener (finvizfinance, free)
3. FMP ETF Holdings (paid API)
4. Static stocks (config fallback)
"""

import csv
import io
import logging
import time
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from finvizfinance.screener.overview import Overview
except ImportError:
    Overview = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_FAILURES = 3

# ---------------------------------------------------------------------------
# FINVIZ filter mappings
# ---------------------------------------------------------------------------

# finvizfinance filter_dict option names (public screener)
CAP_FILTER_MAP = {
    "micro": "+Micro (over $50mln)",
    "small": "+Small (over $300mln)",
    "mid": "+Mid (over $2bln)",
}

# FINVIZ Elite URL filter codes
CAP_ELITE_MAP = {
    "micro": "cap_microover",
    "small": "cap_smallover",
    "mid": "cap_midover",
}

# Industry name -> Elite URL code (lowercase, spaces/punctuation removed)
# Derived from finvizfinance.screener.base.filter_dict["Industry"]["option"]
_INDUSTRY_CODE_CACHE: dict[str, str] = {}


def _industry_to_code(industry: str) -> str:
    """Convert FINVIZ industry name to Elite URL code."""
    if industry in _INDUSTRY_CODE_CACHE:
        return _INDUSTRY_CODE_CACHE[industry]
    code = industry.lower()
    for ch in " &-/,'()":
        code = code.replace(ch, "")
    _INDUSTRY_CODE_CACHE[industry] = code
    return code


# ---------------------------------------------------------------------------
# Source state tracking
# ---------------------------------------------------------------------------


class _SourceState:
    """Track per-source failure state for circuit breaker."""

    def __init__(self):
        self.consecutive_failures: int = 0
        self.total_failures: int = 0
        self.total_queries: int = 0
        self.disabled: bool = False


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _parse_market_cap(value) -> int:
    """Parse FINVIZ Market Cap string to integer.

    "2.8T" -> 2_800_000_000_000
    "150B" -> 150_000_000_000
    "500M" -> 500_000_000
    "-"    -> 0
    None   -> 0
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    s = str(value).strip()
    if not s or s == "-":
        return 0

    multiplier = 1
    if s.endswith("T"):
        multiplier = 1_000_000_000_000
        s = s[:-1]
    elif s.endswith("B"):
        multiplier = 1_000_000_000
        s = s[:-1]
    elif s.endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]

    try:
        return int(float(s) * multiplier)
    except (ValueError, TypeError):
        return 0


def _parse_change(value) -> Optional[float]:
    """Parse FINVIZ Change value to float percentage.

    "12.50%"  -> 12.50
    "-3.20%"  -> -3.20
    0.125     -> 12.5   (finvizfinance 0-1 range)
    12.5      -> 12.5   (abs > 1, already percent)
    "-"       -> None
    None      -> None
    """
    if value is None:
        return None

    if isinstance(value, str):
        s = value.strip()
        if not s or s == "-":
            return None
        s = s.replace("%", "")
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    if isinstance(value, (int, float)):
        f = float(value)
        # finvizfinance returns 0.125 for 12.5%; detect by abs <= 1
        if abs(f) <= 1.0:
            return f * 100.0
        return f

    return None


def _parse_volume(value) -> Optional[int]:
    """Parse FINVIZ Volume value to integer.

    "1,234,567" -> 1234567
    1234567     -> 1234567
    "1.2M"      -> 1200000
    "-"         -> None
    None        -> None
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return int(value)

    s = str(value).strip()
    if not s or s == "-":
        return None

    # Handle M suffix
    if s.upper().endswith("M"):
        try:
            return int(float(s[:-1]) * 1_000_000)
        except (ValueError, TypeError):
            return None

    # Handle comma-separated
    s = s.replace(",", "")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


class RepresentativeStockSelector:
    """Select representative stocks for themes dynamically.

    Fallback chain: FINVIZ Elite -> FINVIZ Public -> FMP ETF Holdings -> static_stocks
    """

    def __init__(
        self,
        finviz_elite_key: Optional[str] = None,
        fmp_api_key: Optional[str] = None,
        finviz_mode: str = "public",
        rate_limit_sec: float = 1.0,
        max_per_industry: int = 4,
        min_cap: str = "small",
    ):
        self._finviz_elite_key = finviz_elite_key
        self._fmp_api_key = fmp_api_key
        self._finviz_mode = finviz_mode
        self._rate_limit_sec = rate_limit_sec
        self._max_per_industry = max_per_industry
        self._min_cap = min_cap
        self._industry_cache: dict[tuple[str, bool], list[dict]] = {}
        self._etf_cache: dict[str, list[dict]] = {}
        self._last_request_time: float = 0.0
        self._source_states: dict[str, _SourceState] = {
            "elite": _SourceState(),
            "public": _SourceState(),
            "fmp": _SourceState(),
        }

    # -- Public properties ---------------------------------------------------

    @property
    def query_count(self) -> int:
        return sum(s.total_queries for s in self._source_states.values())

    @property
    def failure_count(self) -> int:
        return sum(s.total_failures for s in self._source_states.values())

    @property
    def source_states(self) -> dict[str, _SourceState]:
        return self._source_states

    @property
    def _active_sources(self) -> list[str]:
        """Sources actually available given current config."""
        sources: list[str] = []
        if self._finviz_mode == "elite" and self._finviz_elite_key:
            sources.append("elite")
        sources.append("public")  # always available
        if self._fmp_api_key:
            sources.append("fmp")
        return sources

    @property
    def status(self) -> str:
        """Overall health: active / degraded / circuit_broken."""
        active = self._active_sources
        disabled_count = sum(1 for name in active if self._source_states[name].disabled)
        if disabled_count == 0:
            return "active"
        elif disabled_count < len(active):
            return "degraded"
        else:
            return "circuit_broken"

    # -- Main entry point ----------------------------------------------------

    def select_stocks(self, theme: dict, max_stocks: int = 10) -> list[dict]:
        """Select representative stocks for a theme.

        Returns list of dicts with keys:
            symbol, source, market_cap, matched_industries, reasons, composite_score
        """
        is_bearish = theme.get("direction") == "bearish"
        candidates: list[dict] = []
        industries = [ind.get("name", "") for ind in theme.get("matching_industries", [])]

        # Priority 1: FINVIZ (Elite or Public) per industry
        for industry in industries:
            cache_key = (industry, is_bearish)
            if cache_key in self._industry_cache:
                candidates.extend(self._industry_cache[cache_key][: self._max_per_industry])
                continue

            stocks: list[dict] = []
            fetch_limit = max(max_stocks, self._max_per_industry * 2)

            # Elite attempt
            if (
                self._finviz_mode == "elite"
                and self._finviz_elite_key
                and not self._source_states["elite"].disabled
            ):
                stocks = self._fetch_finviz_elite(
                    industry, limit=fetch_limit, is_bearish=is_bearish
                )

            # Public fallback
            if not stocks and not self._source_states["public"].disabled:
                stocks = self._fetch_finviz_public(
                    industry, limit=fetch_limit, is_bearish=is_bearish
                )

            # Score and cache
            stocks = self._compute_composite_score(stocks, is_bearish)
            self._industry_cache[cache_key] = stocks
            candidates.extend(stocks[: self._max_per_industry])

        # Priority 1.5: 2nd pass - fill from cache for single-industry themes
        unique_syms = set(c["symbol"] for c in candidates)
        if len(unique_syms) < max_stocks:
            for industry in industries:
                cache_key = (industry, is_bearish)
                cached = self._industry_cache.get(cache_key, [])
                for stock in cached[self._max_per_industry :]:
                    if stock["symbol"] not in unique_syms:
                        candidates.append(stock)
                        unique_syms.add(stock["symbol"])
                        if len(unique_syms) >= max_stocks:
                            break
                if len(unique_syms) >= max_stocks:
                    break

        # Priority 2: FMP ETF Holdings
        unique_count = len(set(c["symbol"] for c in candidates))
        if (
            unique_count < max_stocks
            and self._fmp_api_key
            and not self._source_states["fmp"].disabled
        ):
            for etf in theme.get("proxy_etfs", []):
                if etf in self._etf_cache:
                    candidates.extend(self._etf_cache[etf])
                    continue
                holdings = self._fetch_etf_holdings(etf, limit=max_stocks)
                self._etf_cache[etf] = holdings
                candidates.extend(holdings)

        # Priority 3: static_stocks fallback
        if not candidates:
            for sym in theme.get("static_stocks", [])[:max_stocks]:
                candidates.append(
                    {
                        "symbol": sym,
                        "source": "static",
                        "market_cap": 0,
                        "matched_industries": [],
                        "reasons": ["Static fallback"],
                        "composite_score": 0,
                    }
                )

        return self._merge_and_rank(candidates, max_stocks)

    # -- Fetch methods -------------------------------------------------------

    def _fetch_finviz_elite(self, industry: str, limit: int, is_bearish: bool) -> list[dict]:
        """Fetch stocks via FINVIZ Elite CSV export."""
        if requests is None:
            return []

        self._rate_limit()
        self._source_states["elite"].total_queries += 1

        ind_code = _industry_to_code(industry)
        cap_code = CAP_ELITE_MAP.get(self._min_cap, "cap_smallover")
        perf_code = "ta_perf2_4wdown" if is_bearish else "ta_perf2_4wup"
        filter_str = f"ind_{ind_code},{cap_code},sh_avgvol_o100,sh_price_o10,{perf_code}"
        url = (
            f"https://elite.finviz.com/export.ashx"
            f"?v=151&f={filter_str}&ft=4&auth={self._finviz_elite_key}"
        )

        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code in (401, 403):
                logger.warning("FINVIZ Elite auth failed (%s)", resp.status_code)
                self._record_failure("elite")
                return []
            if resp.status_code != 200:
                self._record_failure("elite")
                return []

            reader = csv.DictReader(io.StringIO(resp.text))
            stocks: list[dict] = []
            for row in reader:
                ticker = row.get("Ticker", "").strip()
                if not ticker:
                    continue
                stocks.append(
                    {
                        "symbol": ticker,
                        "source": "finviz_elite",
                        "market_cap": _parse_market_cap(row.get("Market Cap")),
                        "change": _parse_change(row.get("Change")),
                        "volume": _parse_volume(row.get("Volume")),
                        "matched_industries": [industry],
                        "reasons": [f"Elite screener: {industry}"],
                    }
                )
                if len(stocks) >= limit:
                    break

            self._record_success("elite")
            return stocks

        except Exception:
            logger.exception("FINVIZ Elite fetch failed for %s", industry)
            self._record_failure("elite")
            return []

    def _fetch_finviz_public(self, industry: str, limit: int, is_bearish: bool) -> list[dict]:
        """Fetch stocks via finvizfinance public screener."""
        if Overview is None:
            logger.warning("finvizfinance not installed")
            self._record_failure("public")
            return []

        self._rate_limit()
        self._source_states["public"].total_queries += 1

        perf_filter = "Month Down" if is_bearish else "Month Up"
        filters_dict = {
            "Industry": industry,
            "Market Cap.": CAP_FILTER_MAP.get(self._min_cap, "+Small (over $300mln)"),
            "Average Volume": "Over 100K",
            "Price": "Over $10",
            "Performance 2": perf_filter,
        }

        try:
            o = Overview()
            o.set_filter(filters_dict=filters_dict)
            df = o.screener_view(order="Market Cap.", limit=limit, verbose=0, ascend=False)

            if df is None or df.empty:
                self._record_success("public")  # Empty result is not a failure
                return []

            stocks: list[dict] = []
            for _, row in df.iterrows():
                ticker = str(row.get("Ticker", "")).strip()
                if not ticker:
                    continue
                stocks.append(
                    {
                        "symbol": ticker,
                        "source": "finviz_public",
                        "market_cap": _parse_market_cap(row.get("Market Cap")),
                        "change": _parse_change(row.get("Change")),
                        "volume": _parse_volume(row.get("Volume")),
                        "matched_industries": [industry],
                        "reasons": [f"Public screener: {industry}"],
                    }
                )

            self._record_success("public")
            return stocks

        except Exception:
            logger.exception("FINVIZ public fetch failed for %s", industry)
            self._record_failure("public")
            return []

    def _fetch_etf_holdings(self, etf_symbol: str, limit: int) -> list[dict]:
        """Fetch top ETF holdings via FMP API."""
        if requests is None or not self._fmp_api_key:
            return []

        self._rate_limit()
        self._source_states["fmp"].total_queries += 1

        # stable: /etf/holdings?symbol= ; v3 fallback (legacy keys): /etf-holder/{symbol}.
        # Both return a list of holdings with `asset` (ticker) and `marketValue`.
        endpoints = [
            ("https://financialmodelingprep.com/stable/etf/holdings", {"symbol": etf_symbol}),
            (f"https://financialmodelingprep.com/api/v3/etf-holder/{etf_symbol}", None),
        ]

        try:
            data = None
            for url, params in endpoints:
                resp = requests.get(
                    url, params=params, headers={"apikey": self._fmp_api_key}, timeout=15
                )
                if resp.status_code != 200:
                    continue
                payload = resp.json()
                if isinstance(payload, list) and payload:
                    data = payload
                    break

            if not data:
                self._record_failure("fmp")
                return []

            stocks: list[dict] = []
            for item in data[:limit]:
                ticker = item.get("asset", "").strip()
                if not ticker:
                    continue
                stocks.append(
                    {
                        "symbol": ticker,
                        "source": "etf_holdings",
                        "composite_score": 0,
                        "market_cap": _parse_market_cap(item.get("marketValue")),
                        "change": None,
                        "volume": None,
                        "matched_industries": [],
                        "reasons": [f"Held by {etf_symbol}"],
                    }
                )

            self._record_success("fmp")
            return stocks

        except Exception:
            logger.exception("FMP ETF holdings fetch failed for %s", etf_symbol)
            self._record_failure("fmp")
            return []

    # -- Scoring & ranking ---------------------------------------------------

    def _compute_composite_score(self, stocks: list[dict], is_bearish: bool) -> list[dict]:
        """Compute composite score: 0.4*cap_rank + 0.3*change_rank + 0.3*vol_rank.

        Missing fields are excluded and weights re-normalized.
        """
        if not stocks:
            return []

        n = len(stocks)
        if n == 1:
            stocks[0]["composite_score"] = 1.0
            return stocks

        # Build ranks for each metric (1 = best, n = worst)
        # market_cap: larger is better
        cap_vals = [(i, s.get("market_cap") or 0) for i, s in enumerate(stocks)]
        cap_sorted = sorted(cap_vals, key=lambda x: x[1], reverse=True)
        cap_rank = {idx: rank + 1 for rank, (idx, _) in enumerate(cap_sorted)}

        # change: direction-aware
        change_vals = []
        has_change = False
        for i, s in enumerate(stocks):
            c = s.get("change")
            if c is not None:
                has_change = True
                directional = abs(c) if is_bearish else c
                change_vals.append((i, directional))
            else:
                change_vals.append((i, None))

        change_rank: dict[int, Optional[int]] = {}
        if has_change:
            valid = [(i, v) for i, v in change_vals if v is not None]
            valid_sorted = sorted(valid, key=lambda x: x[1], reverse=True)
            for rank, (idx, _) in enumerate(valid_sorted):
                change_rank[idx] = rank + 1
            for i, v in change_vals:
                if v is None:
                    change_rank[i] = None
        else:
            for i in range(n):
                change_rank[i] = None

        # volume: larger is better
        vol_vals = []
        has_volume = False
        for i, s in enumerate(stocks):
            v = s.get("volume")
            if v is not None:
                has_volume = True
                vol_vals.append((i, v))
            else:
                vol_vals.append((i, None))

        vol_rank: dict[int, Optional[int]] = {}
        if has_volume:
            valid = [(i, v) for i, v in vol_vals if v is not None]
            valid_sorted = sorted(valid, key=lambda x: x[1], reverse=True)
            for rank, (idx, _) in enumerate(valid_sorted):
                vol_rank[idx] = rank + 1
            for i, v in vol_vals:
                if v is None:
                    vol_rank[i] = None
        else:
            for i in range(n):
                vol_rank[i] = None

        # Compute composite with re-normalization
        for i, s in enumerate(stocks):
            weights = {}
            ranks = {}

            # Cap is always available
            weights["cap"] = 0.4
            ranks["cap"] = cap_rank[i]

            cr = change_rank.get(i)
            if cr is not None:
                weights["change"] = 0.3
                ranks["change"] = cr

            vr = vol_rank.get(i)
            if vr is not None:
                weights["vol"] = 0.3
                ranks["vol"] = vr

            total_weight = sum(weights.values())

            # Normalized rank score: (n - rank + 1) / n => 1.0 for rank 1
            # Count of valid items for each metric
            valid_counts = {
                "cap": n,
                "change": sum(1 for _, v in change_vals if v is not None) if has_change else 0,
                "vol": sum(1 for _, v in vol_vals if v is not None) if has_volume else 0,
            }

            score = 0.0
            for key, w in weights.items():
                count = valid_counts.get(key, n)
                if count > 0:
                    normalized = (count - ranks[key] + 1) / count
                    score += (w / total_weight) * normalized

            s["composite_score"] = round(score, 4)

        # Sort by composite score descending
        stocks.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
        return stocks

    def _merge_and_rank(self, candidates: list[dict], max_stocks: int) -> list[dict]:
        """Deduplicate by symbol, merge industries/reasons, rank by score."""
        merged: dict[str, dict] = {}
        for c in candidates:
            sym = c["symbol"]
            if sym in merged:
                for ind in c.get("matched_industries", []):
                    if ind not in merged[sym]["matched_industries"]:
                        merged[sym]["matched_industries"].append(ind)
                merged[sym]["reasons"].extend(c.get("reasons", []))
                merged[sym]["composite_score"] = max(
                    merged[sym].get("composite_score", 0),
                    c.get("composite_score", 0),
                )
            else:
                merged[sym] = {
                    **c,
                    "composite_score": c.get("composite_score", 0),
                    "matched_industries": list(c.get("matched_industries", [])),
                    "reasons": list(c.get("reasons", [])),
                }

        ranked = sorted(
            merged.values(),
            key=lambda x: x.get("composite_score", 0),
            reverse=True,
        )
        return ranked[:max_stocks]

    # -- Rate limiting & circuit breaker -------------------------------------

    def _rate_limit(self):
        """Enforce minimum interval between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit_sec:
            time.sleep(self._rate_limit_sec - elapsed)
        self._last_request_time = time.time()

    def _record_success(self, source: str):
        """Record successful query for source."""
        state = self._source_states[source]
        state.consecutive_failures = 0

    def _record_failure(self, source: str):
        """Record failed query for source. Disable after consecutive limit."""
        state = self._source_states[source]
        state.consecutive_failures += 1
        state.total_failures += 1
        if state.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            state.disabled = True
            logger.warning(
                "Source %s disabled after %d consecutive failures",
                source,
                _MAX_CONSECUTIVE_FAILURES,
            )
