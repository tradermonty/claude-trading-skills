# pivot_monitor.py
from __future__ import annotations

import asyncio
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from alpaca_client import AlpacaClient
from settings_manager import SettingsManager

NEGATIVE_KEYWORDS = {
    "sec", "fraud", "bankrupt", "lawsuit", "miss", "downgrade",
    "fda rejection", "recall", "warning", "investigation", "halt",
}
POSITIVE_KEYWORDS = {
    "beat", "upgrade", "bullish", "strong guidance", "approval",
    "partnership", "accumulation", "buy rating",
}
PIVOT_BUFFER = 1.001  # price must cross pivot × 1.001 to trigger


def _default_search_fn(symbol: str) -> list[str]:
    """No external search configured — return empty (no news = CLEAR)."""
    return []


class PivotWatchlistMonitor:
    """Monitors VCP candidates for pivot breakouts and fires bracket orders in Auto mode.

    Inject _search_fn for Stage 1/2 news checks (default = no-op).
    Inject _data_stream for tests (avoids real Alpaca WebSocket).
    """

    def __init__(
        self,
        alpaca_client: AlpacaClient,
        settings_manager: SettingsManager,
        cache_dir: Path,
        rule_store=None,
        multiplier_store=None,
        pdt_tracker=None,
        drawdown_tracker=None,
        earnings_blackout=None,
        _search_fn: Optional[Callable[[str], list[str]]] = None,
        _data_stream=None,
    ):
        self._alpaca = alpaca_client
        self._settings = settings_manager
        self._cache_dir = cache_dir
        self._rule_store = rule_store
        self._multiplier_store = multiplier_store
        self._pdt_tracker = pdt_tracker
        self._drawdown_tracker = drawdown_tracker
        self._earnings_blackout = earnings_blackout
        self._search_fn = _search_fn or _default_search_fn
        self._data_stream = _data_stream
        self._candidates: list[dict] = []
        self._triggered: set[str] = set()
        self._lock = threading.Lock()

    # ── Candidate loading ────────────────────────────────────────────────────

    def load_candidates(self) -> list[dict]:
        """Read VCP cache, return [{symbol, pivot_price}] list."""
        vcp_file = self._cache_dir / "vcp-screener.json"
        if not vcp_file.exists():
            return []
        try:
            data = json.loads(vcp_file.read_text())
            candidates = []
            for r in data.get("results", []):
                symbol = r.get("symbol")
                pivot_price = (r.get("vcp_pattern") or {}).get("pivot_price")
                if symbol and pivot_price:
                    candidates.append({"symbol": symbol, "pivot_price": float(pivot_price)})
            return candidates
        except (json.JSONDecodeError, OSError):
            return []

    # ── Stage 1: Pre-market confidence tagging ────────────────────────────

    def run_stage1_check(self, candidates: list[dict]) -> list[dict]:
        """Tag each candidate: HIGH_CONVICTION / CLEAR / UNCERTAIN / BLOCKED."""
        earnings_soon = self._get_earnings_soon_symbols()
        inst_flow = self._get_institutional_accumulation_symbols()

        tagged = []
        for c in candidates:
            tag = self._tag_candidate(c["symbol"], earnings_soon, inst_flow)
            tagged.append({**c, "confidence_tag": tag})

        if self._rule_store:
            tagged = self._rule_store.apply(tagged)

        return tagged

    def _tag_candidate(self, symbol: str, earnings_soon: set, inst_flow: set) -> str:
        headlines = self._search_fn(symbol)
        text = " ".join(headlines).lower()
        has_negative = any(kw in text for kw in NEGATIVE_KEYWORDS)
        has_positive = any(kw in text for kw in POSITIVE_KEYWORDS)

        if has_negative:
            return "BLOCKED"
        if symbol in inst_flow and has_positive:
            return "HIGH_CONVICTION"
        if symbol in earnings_soon:
            return "UNCERTAIN"
        if has_positive or symbol in inst_flow:
            return "HIGH_CONVICTION"
        return "CLEAR"

    def _get_earnings_soon_symbols(self) -> set:
        earnings_file = self._cache_dir / "earnings-calendar.json"
        if not earnings_file.exists():
            return set()
        try:
            data = json.loads(earnings_file.read_text())
            today = datetime.now(ZoneInfo("America/New_York")).date()
            symbols = set()
            for e in data.get("events", []):
                try:
                    edate = datetime.fromisoformat(e["date"]).date()
                    if 0 <= (edate - today).days <= 3:
                        symbols.add(e.get("symbol", "").upper())
                except Exception:
                    continue
            return symbols
        except (json.JSONDecodeError, OSError, KeyError):
            return set()

    def _get_institutional_accumulation_symbols(self) -> set:
        flow_file = self._cache_dir / "institutional-flow-tracker.json"
        if not flow_file.exists():
            return set()
        try:
            data = json.loads(flow_file.read_text())
            return {s.upper() for s in data.get("accumulation_symbols", [])}
        except (json.JSONDecodeError, OSError):
            return set()

    # ── Breakout detection ─────────────────────────────────────────────────

    def _check_breakout(self, bar, candidates: list[dict]) -> None:
        """Called for each bar event. Fires order if pivot breakout detected."""
        for c in candidates:
            if c["symbol"] != bar.symbol:
                continue
            if c["symbol"] in self._triggered:
                continue

            tag = c.get("confidence_tag", "CLEAR")
            if tag == "BLOCKED":
                continue

            trigger_price = c["pivot_price"] * PIVOT_BUFFER
            if bar.close < trigger_price:
                continue

            # Breakout detected — run guard rails
            allowed, reason = self._guard_rails_allow(c, tag=tag)
            if not allowed:
                print(f"[pivot_monitor] {c['symbol']} guard: {reason}", file=sys.stderr)
                continue

            # Stage 2 for UNCERTAIN
            if tag == "UNCERTAIN":
                headlines = self._search_fn(c["symbol"])
                text = " ".join(headlines).lower()
                if any(kw in text for kw in NEGATIVE_KEYWORDS):
                    print(f"[pivot_monitor] {c['symbol']} Stage 2 blocked: negative news", file=sys.stderr)
                    continue

            with self._lock:
                self._triggered.add(c["symbol"])
            self._fire_order(c, tag)

    def _guard_rails_allow(self, candidate: dict, tag: str = "CLEAR") -> tuple[bool, str]:
        """Check all guard rails. Returns (allowed, reason)."""
        if not _market_is_open_now():
            return False, "outside market hours"

        # Market Top Detector pause
        mt_file = self._cache_dir / "market-top-detector.json"
        if mt_file.exists():
            try:
                data = json.loads(mt_file.read_text())
                risk_score = data.get("risk_score", 0)
                if risk_score >= 65:
                    return False, f"Market Top risk={risk_score} ≥ 65 — Auto paused"
            except (json.JSONDecodeError, OSError):
                pass

        # Max positions
        settings = self._settings.load()
        try:
            positions = self._alpaca.get_positions()
            max_pos = settings.get("max_positions", 5)
            if len(positions) >= max_pos:
                return False, f"max_positions={max_pos} reached"
        except Exception:  # fail closed — any Alpaca error blocks the order
            return False, "could not check positions"

        # PDT selectivity
        if self._pdt_tracker is not None:
            from datetime import date as _date
            allowed_tags = self._pdt_tracker.get_allowed_tags(_date.today())
            if not allowed_tags:
                return False, "PDT: 3 day trades used — no new entries"
            if tag not in allowed_tags:
                return False, f"PDT: {len(allowed_tags)} slot(s) left — {tag} not allowed"

        # Drawdown circuit breaker
        if self._drawdown_tracker is not None:
            settings = self._settings.load()
            try:
                acct = self._alpaca.get_account()
                portfolio_value = float(acct["portfolio_value"])
                max_weekly = settings.get("max_weekly_drawdown_pct", 10.0)
                max_daily = settings.get("max_daily_loss_pct", 5.0)
                from datetime import date as _date
                self._drawdown_tracker.update(portfolio_value, _date.today())
                if self._drawdown_tracker.is_weekly_limit_breached(portfolio_value, max_weekly):
                    return False, f"drawdown: weekly limit {max_weekly}% breached"
                if self._drawdown_tracker.is_daily_limit_breached(portfolio_value, max_daily):
                    return False, f"drawdown: daily limit {max_daily}% breached"
            except Exception as e:
                print(f"[pivot_monitor] drawdown check error: {e}", file=sys.stderr)

        # Earnings blackout
        if self._earnings_blackout is not None:
            settings = self._settings.load()
            blackout_days = settings.get("earnings_blackout_days", 5)
            symbol = candidate.get("symbol", "")
            from datetime import date as _date
            if self._earnings_blackout.is_blacked_out(symbol, _date.today(), blackout_days):
                return False, f"earnings blackout: {symbol} reports within {blackout_days} days"

        # Volume confirmation
        min_vol_ratio = settings.get("min_volume_ratio", 1.5)
        if min_vol_ratio > 0:
            avg_vol = candidate.get("avg_volume_20d")
            if avg_vol:
                try:
                    current_vol = self._alpaca.get_current_volume(candidate["symbol"])
                    if current_vol < avg_vol * min_vol_ratio:
                        return False, (
                            f"volume {current_vol}/{int(avg_vol)} "
                            f"below {min_vol_ratio}x threshold"
                        )
                except Exception:
                    pass  # fail open

        # Time-of-day soft lock
        avoid_min = settings.get("avoid_open_close_minutes", 30)
        if avoid_min > 0:
            now_et = datetime.now(ZoneInfo("America/New_York"))
            market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            minutes_since_open = (now_et - market_open).total_seconds() / 60
            minutes_to_close = (market_close - now_et).total_seconds() / 60
            in_soft_lock = minutes_since_open < avoid_min or minutes_to_close < avoid_min
            if in_soft_lock and tag != "HIGH_CONVICTION":
                return False, f"time-of-day soft lock: {tag} blocked in open/close window"

        return True, ""

    def _get_current_regime(self) -> str:
        """Extract current_regime string from macro-regime-detector cache."""
        try:
            data = json.loads((self._cache_dir / "macro-regime-detector.json").read_text())
            regime_data = data.get("regime", {})
            if isinstance(regime_data, dict):
                return regime_data.get("current_regime", "unknown")
            return str(regime_data).lower() if regime_data else "unknown"
        except Exception:
            return "unknown"

    def _fire_order(self, candidate: dict, tag: str) -> None:
        """Fetch live price, look up learned multiplier, place bracket order, log trade."""
        symbol = candidate["symbol"]
        try:
            entry_price = self._alpaca.get_last_price(symbol)
            stop_price = round(entry_price * 0.97, 2)
            qty = self._calc_qty(entry_price, stop_price, high_conviction=(tag == "HIGH_CONVICTION"))
            if qty <= 0:
                print(f"[pivot_monitor] {symbol}: qty=0, skipping", file=sys.stderr)
                return

            regime = self._get_current_regime()
            multiplier = 2.0
            if self._multiplier_store is not None:
                bucket_key = f"vcp+{tag}+{regime}"
                multiplier = self._multiplier_store.get(bucket_key)
            take_profit_price = round(entry_price + (entry_price - stop_price) * multiplier, 2)

            result = self._alpaca.place_bracket_order(
                symbol=symbol, qty=qty, limit_price=entry_price, stop_price=stop_price,
                take_profit_price=take_profit_price,
            )
            print(
                f"[pivot_monitor] ORDER: {symbol} {qty}sh @ {entry_price} "
                f"tp={take_profit_price} ({multiplier:.1f}x) | {result}",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"[pivot_monitor] {symbol} order error: {e}", file=sys.stderr)
            return
        try:
            self._log_trade(candidate, result["id"], entry_price, stop_price, qty, tag)
        except Exception as e:
            print(f"[pivot_monitor] {symbol} log error (order placed): {e}", file=sys.stderr)

    def _calc_qty(self, entry_price: float, stop_price: float, high_conviction: bool) -> int:
        """Calculate share count based on risk % settings and account value."""
        settings = self._settings.load()
        risk_pct = settings.get("default_risk_pct", 1.0)
        if high_conviction:
            risk_pct = min(risk_pct * 1.5, 5.0)
        max_pos_pct = settings.get("max_position_size_pct", 10.0)
        if high_conviction:
            max_pos_pct = min(max_pos_pct * 1.5, 25.0)

        try:
            portfolio_value = self._alpaca.get_account()["portfolio_value"]
        except Exception:
            return 0

        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            return 0

        dollar_risk = portfolio_value * (risk_pct / 100)
        qty = int(dollar_risk / risk_per_share)

        max_dollar = portfolio_value * (max_pos_pct / 100)
        max_qty_by_size = int(max_dollar / entry_price)
        raw_qty = min(qty, max_qty_by_size)
        breadth_mult = self._get_breadth_multiplier()
        return max(1, int(raw_qty * breadth_mult))

    def _log_trade(
        self, candidate: dict, order_id: str,
        entry_price: float, stop_price: float, qty: int, tag: str,
    ) -> None:
        """Append trade context to cache/auto_trades.json for pattern extraction.

        Captures full market state snapshot at entry so PatternExtractor can
        build multi-factor rules (breadth, market top, macro regime, etc.).
        """
        trades_file = self._cache_dir / "auto_trades.json"
        try:
            trades = json.loads(trades_file.read_text()) if trades_file.exists() else {"trades": []}
        except (json.JSONDecodeError, OSError):
            trades = {"trades": []}

        # Read market state snapshot from cache files (best-effort; missing = None)
        market_top_score = self._read_cache_field("market-top-detector.json", "risk_score")
        breadth_score = self._read_cache_field("market-breadth-analyzer.json", "breadth_score")
        ftd_score = self._read_cache_field("ftd-detector.json", "ftd_score")
        settings = self._settings.load()
        risk_pct = settings.get("default_risk_pct", 1.0)
        if tag == "HIGH_CONVICTION":
            risk_pct = min(risk_pct * 1.5, 5.0)

        trades["trades"].append({
            "symbol": candidate["symbol"],
            "order_id": order_id,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "entry_price": entry_price,
            "stop_price": stop_price,
            "qty": qty,
            "confidence_tag": tag,
            "pivot_price": candidate["pivot_price"],
            "risk_pct": risk_pct,
            # Market state snapshot for multi-factor rule extraction
            "market_top_score": market_top_score,
            "breadth_score": breadth_score,
            "ftd_score": ftd_score,
            "regime": self._get_current_regime(),
            "screener": "vcp",
            # Outcome populated later by PatternExtractor.refresh_trade_outcomes()
            "outcome": None,
        })
        trades_file.write_text(json.dumps(trades, indent=2))

    def _read_cache_field(self, filename: str, field: str):
        """Read a single field from a cache JSON file. Returns None on any error."""
        try:
            data = json.loads((self._cache_dir / filename).read_text())
            return data.get(field)
        except Exception:
            return None

    def _get_breadth_multiplier(self) -> float:
        """Returns size multiplier based on market breadth. 1.0 = full size."""
        settings = self._settings.load()
        threshold = settings.get("breadth_threshold_pct", 60.0)
        reduction = settings.get("breadth_size_reduction_pct", 50.0)
        try:
            data = json.loads((self._cache_dir / "market-breadth.json").read_text())
            pct_above_50ma = float(data.get("pct_above_50ma", 100.0))
            if pct_above_50ma < threshold:
                return 1.0 - (reduction / 100.0)
        except Exception:
            pass
        return 1.0

    # ── Alpaca data WebSocket subscription ────────────────────────────────

    async def start(self, candidates: list[dict]) -> None:
        """Subscribe to Alpaca data WebSocket for candidates and run breakout monitor."""
        with self._lock:
            self._candidates = [c for c in candidates if c.get("confidence_tag") != "BLOCKED"]
            self._triggered.clear()

        if not self._candidates:
            return
        if not self._alpaca.is_configured:
            return

        if self._data_stream is not None:
            stream = self._data_stream
        else:
            from alpaca.data.live import StockDataStream
            stream = StockDataStream(
                api_key=self._alpaca.api_key,
                secret_key=self._alpaca.secret_key,
            )

        symbols = [c["symbol"] for c in self._candidates]
        monitor = self  # capture for closure

        async def handle_bar(bar):
            monitor._check_breakout(bar, monitor._candidates)

        stream.subscribe_bars(handle_bar, *symbols)

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, stream.run)
        except Exception as e:
            print(f"[pivot_monitor] stream disconnected: {e}", file=sys.stderr)


_MARKET_OPEN = datetime.strptime("09:30", "%H:%M").time()
_MARKET_CLOSE = datetime.strptime("16:00", "%H:%M").time()


def _market_is_open_now() -> bool:
    """Check if current ET time is within market hours (Mon-Fri 9:30-16:00)."""
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    return _MARKET_OPEN <= now.time() < _MARKET_CLOSE
