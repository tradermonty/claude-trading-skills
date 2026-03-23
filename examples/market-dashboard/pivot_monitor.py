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

from broker_client import BrokerClient
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
        broker_client: "BrokerClient",
        settings_manager: SettingsManager,
        cache_dir: Path,
        market_config: dict | None = None,
        pdt_enabled: bool = True,
        calendar_file: Path | None = None,
        rule_store=None,
        multiplier_store=None,
        pdt_tracker=None,
        drawdown_tracker=None,
        earnings_blackout=None,
        _search_fn: Optional[Callable[[str], list[str]]] = None,
        _data_stream=None,
    ):
        self._broker = broker_client
        self._market_config = market_config or {
            "id": "us",
            "tz": "America/New_York",
            "open": "09:30",
            "close": "16:00",
        }
        self._pdt_enabled = pdt_enabled
        self._calendar_file = calendar_file
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
        if self._calendar_file is not None:
            earnings_file = Path(self._calendar_file)
        else:
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
        if not self._is_market_open_now():
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
            positions = self._broker.get_positions()
            max_pos = settings.get("max_positions", 5)
            if len(positions) >= max_pos:
                return False, f"max_positions={max_pos} reached"
        except Exception:  # fail closed — any Alpaca error blocks the order
            return False, "could not check positions"

        # PDT selectivity
        if self._pdt_enabled and self._pdt_tracker is not None:
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
                acct = self._broker.get_account()
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
                    current_vol = self._broker.get_current_volume(candidate["symbol"])
                    if current_vol < avg_vol * min_vol_ratio:
                        return False, (
                            f"volume {current_vol}/{int(avg_vol)} "
                            f"below {min_vol_ratio}x threshold"
                        )
                except Exception:
                    pass  # fail open

        # Time-of-day soft lock — uses market_config hours and timezone
        avoid_min = settings.get("avoid_open_close_minutes", 30)
        if avoid_min > 0:
            tz_str = self._market_config.get("tz", "America/New_York")
            open_str = self._market_config.get("open", "09:30")
            close_str = self._market_config.get("close", "16:00")
            open_h, open_m = int(open_str.split(":")[0]), int(open_str.split(":")[1])
            close_h, close_m = int(close_str.split(":")[0]), int(close_str.split(":")[1])
            now_local = datetime.now(ZoneInfo(tz_str))
            market_open = now_local.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
            market_close = now_local.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
            minutes_since_open = (now_local - market_open).total_seconds() / 60
            minutes_to_close = (market_close - now_local).total_seconds() / 60
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
            entry_price = self._broker.get_last_price(symbol)
            stop_price = round(entry_price * 0.97, 2)
            regime = self._get_current_regime()
            bucket_key = f"vcp+{tag}+{regime}"
            qty = self._calc_qty(entry_price, stop_price, high_conviction=(tag == "HIGH_CONVICTION"), bucket_key=bucket_key)
            if qty <= 0:
                print(f"[pivot_monitor] {symbol}: qty=0, skipping", file=sys.stderr)
                return

            multiplier = 2.0
            if self._multiplier_store is not None:
                multiplier = self._multiplier_store.get(bucket_key)
            take_profit_price = round(entry_price + (entry_price - stop_price) * multiplier, 2)

            result = self._broker.place_bracket_order(
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

    def _calc_qty(
        self,
        entry_price: float,
        stop_price: float,
        high_conviction: bool,
        bucket_key: str = "",
    ) -> int:
        """Calculate share count based on risk % settings, Kelly, and VIX."""
        settings = self._settings.load()
        risk_pct = settings.get("default_risk_pct", 1.0)
        if high_conviction:
            risk_pct = min(risk_pct * 1.5, 5.0)
        max_pos_pct = settings.get("max_position_size_pct", 10.0)
        if high_conviction:
            max_pos_pct = min(max_pos_pct * 1.5, 25.0)

        try:
            portfolio_value = self._broker.get_account()["portfolio_value"]
        except Exception:
            return 0

        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            return 0

        dollar_risk = portfolio_value * (risk_pct / 100)
        qty = int(dollar_risk / risk_per_share)

        max_dollar = portfolio_value * (max_pos_pct / 100)
        max_qty_by_size = int(max_dollar / entry_price)

        # Apply Kelly multiplier (opt-in — needs accumulated trade history)
        kelly_mult = 1.0
        if settings.get("kelly_sizing_enabled", False) and self._multiplier_store is not None:
            kelly_max = settings.get("kelly_max_multiplier", 2.0)
            kelly_mult = self._multiplier_store.get_kelly_multiplier(bucket_key, risk_pct, kelly_max)

        # Apply VIX multiplier (automatic — reads from cache, fails open)
        vix_mult = self._get_vix_multiplier()

        regime_conf_mult = self._get_regime_confidence_multiplier()
        final_qty = max(1, int(qty * kelly_mult * vix_mult))
        return min(max(1, int(final_qty * regime_conf_mult)), max_qty_by_size)

    def _log_trade(
        self, candidate: dict, order_id: str,
        entry_price: float, stop_price: float, qty: int, tag: str,
    ) -> None:
        """Append trade context to cache/auto_trades.json for pattern extraction.

        Captures full market state snapshot at entry so PatternExtractor can
        build multi-factor rules (breadth, market top, macro regime, etc.).
        """
        market_id = self._market_config.get("id", "us")
        trades_file = self._cache_dir / f"{market_id}-auto_trades.json"
        # Backward-compatible read: if us-auto_trades.json missing, check auto_trades.json
        if market_id == "us" and not trades_file.exists():
            legacy_file = self._cache_dir / "auto_trades.json"
            if legacy_file.exists():
                trades_file = legacy_file
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
            "market": market_id,
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

    def _check_exit_management(self) -> None:
        if not self._is_market_open_now():
            return
        settings = self._settings.load()
        trades_file = self._cache_dir / "auto_trades.json"
        if not trades_file.exists():
            return
        try:
            data = json.loads(trades_file.read_text())
        except (json.JSONDecodeError, OSError):
            return
        open_trades = [t for t in data.get("trades", []) if t.get("outcome") is None]
        if not open_trades:
            return
        changed = False
        for trade in open_trades:
            try:
                changed |= self._apply_trailing_stop(trade, settings)
                changed |= self._apply_partial_exit(trade, settings)
                changed |= self._apply_time_stop(trade, settings)
            except Exception as e:
                print(f"[exit_mgmt] {trade.get('symbol')} error: {e}", file=sys.stderr)
        if changed:
            trades_file.write_text(json.dumps(data, indent=2))

    def _apply_trailing_stop(self, trade: dict, settings: dict) -> bool:
        if not settings.get("trailing_stop_enabled", True):
            return False
        entry = trade.get("entry_price")
        stop = trade.get("stop_price")
        stop_order_id = trade.get("stop_order_id")
        if not all([entry, stop, stop_order_id]):
            return False
        try:
            current_price = self._broker.get_last_price(trade["symbol"])
        except Exception:
            return False
        risk = entry - stop
        if risk <= 0:
            return False
        current_r = (current_price - entry) / risk
        new_stop = None
        if current_r >= 2.0 and stop < entry + risk:
            new_stop = round(entry + risk, 2)
        elif current_r >= 1.0 and stop < entry:
            new_stop = entry
        if new_stop is not None and new_stop > stop:
            try:
                self._broker.replace_order_stop(stop_order_id, new_stop)
                trade["stop_price"] = new_stop
                trade["trailing_stop_level"] = new_stop
                return True
            except Exception as e:
                print(f"[trailing_stop] {trade['symbol']} replace failed: {e}", file=sys.stderr)
        return False

    def _apply_partial_exit(self, trade: dict, settings: dict) -> bool:
        if not settings.get("partial_exit_enabled", True):
            return False
        if trade.get("partial_exit_done"):
            return False
        entry = trade.get("entry_price")
        stop = trade.get("stop_price")
        qty = trade.get("qty")
        if not all([entry, stop, qty]):
            return False
        try:
            current_price = self._broker.get_last_price(trade["symbol"])
        except Exception:
            return False
        risk = entry - stop
        if risk <= 0:
            return False
        target_r = settings.get("partial_exit_at_r", 1.0)
        current_r = (current_price - entry) / risk
        if current_r < target_r:
            return False
        exit_pct = settings.get("partial_exit_pct", 50)
        shares_to_sell = max(1, int(qty * exit_pct / 100))
        try:
            self._broker.place_market_sell(trade["symbol"], shares_to_sell)
            trade["partial_exit_done"] = True
            trade["partial_exit_price"] = current_price
            trade["partial_exit_qty"] = shares_to_sell
            return True
        except Exception as e:
            print(f"[partial_exit] {trade['symbol']} sell failed: {e}", file=sys.stderr)
            trade["partial_exit_done"] = True
        return False

    def _apply_time_stop(self, trade: dict, settings: dict) -> bool:
        time_stop_days = settings.get("time_stop_days", 5)
        if time_stop_days == 0:
            return False
        entry_time_str = trade.get("entry_time")
        if not entry_time_str:
            return False
        entry_dt = datetime.fromisoformat(entry_time_str)
        now = datetime.now(timezone.utc)
        days_open = (now - entry_dt).days
        if days_open < time_stop_days:
            return False
        entry = trade.get("entry_price")
        stop = trade.get("stop_price")
        qty = trade.get("qty")
        if not all([entry, stop, qty]):
            return False
        try:
            current_price = self._broker.get_last_price(trade["symbol"])
        except Exception:
            return False
        risk = entry - stop
        if risk <= 0:
            return False
        current_r = abs((current_price - entry) / risk)
        if current_r > 0.5:
            return False
        try:
            self._broker.place_market_sell(trade["symbol"], qty)
            trade["outcome"] = "time_stop"
            trade["exit_price"] = current_price
            return True
        except Exception as e:
            print(f"[time_stop] {trade['symbol']} exit failed: {e}", file=sys.stderr)
        return False

    def _get_vix_multiplier(self) -> float:
        """Returns size multiplier based on VIX. Lower VIX = full size. Fails open (1.0)."""
        settings = self._settings.load()
        if not settings.get("vix_sizing_enabled", True):
            return 1.0
        try:
            for fname in ["us-market-bubble-detector.json", "macro-regime-detector.json"]:
                fpath = self._cache_dir / fname
                if fpath.exists():
                    data = json.loads(fpath.read_text())
                    vix = (
                        data.get("vix")
                        or data.get("VIX")
                        or (data.get("indicators") or {}).get("vix")
                    )
                    if vix is not None:
                        vix = float(vix)
                        if vix < 20:
                            return 1.0
                        elif vix < 25:
                            return 0.75
                        elif vix < 30:
                            return 0.50
                        else:
                            return 0.25
        except Exception:
            pass
        return 1.0  # fail open — no VIX data = no penalty

    def _get_regime_confidence_multiplier(self) -> float:
        """Returns size multiplier based on regime signal confidence (0-100 score)."""
        try:
            data = json.loads((self._cache_dir / "macro-regime-detector.json").read_text())
            regime_data = data.get("regime", {})
            score = None
            if isinstance(regime_data, dict):
                score = regime_data.get("score")
            if score is None:
                return 1.0
            score = float(score)
            if score >= 75:
                return 1.0
            elif score >= 50:
                return 0.75
            elif score >= 25:
                return 0.5
            else:
                return 0.25
        except Exception:
            return 1.0

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

    def _is_market_open_now(self) -> bool:
        """Check if current time is within market hours using market_config."""
        tz_str = self._market_config.get("tz", "America/New_York")
        open_str = self._market_config.get("open", "09:30")
        close_str = self._market_config.get("close", "16:00")
        open_h, open_m = int(open_str.split(":")[0]), int(open_str.split(":")[1])
        close_h, close_m = int(close_str.split(":")[0]), int(close_str.split(":")[1])
        now = datetime.now(ZoneInfo(tz_str))
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        t = now.time()
        from datetime import time as _time
        market_open = _time(open_h, open_m)
        market_close = _time(close_h, close_m)
        return market_open <= t < market_close

    # ── Broker data WebSocket subscription ────────────────────────────────

    async def start(self, candidates: list[dict]) -> None:
        """Subscribe to Alpaca data WebSocket for candidates and run breakout monitor."""
        with self._lock:
            self._candidates = [c for c in candidates if c.get("confidence_tag") != "BLOCKED"]
            self._triggered.clear()

        if not self._candidates:
            return
        if not self._broker.is_configured:
            return

        symbols = [c["symbol"] for c in self._candidates]

        async def handle_bar(bar):
            self._check_breakout(bar, self._candidates)

        if self._data_stream is not None:
            # Test injection: simulate stream with a mock object that has subscribe_bars/run
            stream = self._data_stream
            stream.subscribe_bars(handle_bar, *symbols)
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, stream.run)
            except Exception as e:
                print(f"[pivot_monitor] stream disconnected: {e}", file=sys.stderr)
        else:
            try:
                await self._broker.subscribe_bars(symbols, handle_bar)
            except Exception as e:
                print(f"[pivot_monitor] subscribe_bars error: {e}", file=sys.stderr)


_MARKET_OPEN = datetime.strptime("09:30", "%H:%M").time()
_MARKET_CLOSE = datetime.strptime("16:00", "%H:%M").time()


def _market_is_open_now() -> bool:
    """Check if current ET time is within market hours (Mon-Fri 9:30-16:00)."""
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    return _MARKET_OPEN <= now.time() < _MARKET_CLOSE
