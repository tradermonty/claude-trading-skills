"""The trading agent.

Runs in its own thread. When .start() is called from the dashboard, it loops:
  1. Check market clock, account status, margin call.
  2. Evaluate stops/targets on existing positions.
  3. Scan universe for new signals per allowed strategies.
  4. Rank signals, size positions, submit orders.
  5. Log everything to SQLite so the dashboard can show it.
"""
from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone

from alpaca_client import AlpacaPaperClient, PositionSnapshot
from config import RISK_MODES, RiskMode, get_risk_mode
from db import log_event, record_trade, set_state
from risk import (
    can_open_new_position,
    daily_loss_breached,
    margin_call_triggered,
    minutes_until_close,
    position_size,
    should_stagnation_exit,
    should_stop,
    should_trailing_stop,
)
from strategies import Signal, scan


class TradingAgent:
    def __init__(self) -> None:
        self._client: AlpacaPaperClient | None = None
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()

        self.running: bool = False
        self.risk_mode: RiskMode = get_risk_mode("medium")
        self.starting_equity: float | None = None
        self.last_scan_ts: str | None = None
        self.last_error: str | None = None
        self.halted_reason: str | None = None
        self.position_meta: dict[str, dict] = {}  # symbol -> {strategy, side, entry}

    # ---------------------- public control ----------------------

    @property
    def client(self) -> AlpacaPaperClient:
        if self._client is None:
            self._client = AlpacaPaperClient()
        return self._client

    def start(self, risk_mode_name: str) -> dict:
        with self._lock:
            if self.running:
                return {"ok": False, "error": "already running"}
            self.risk_mode = get_risk_mode(risk_mode_name)
            self._stop_flag.clear()
            # capture starting equity for daily-loss math
            acct = self.client.account()
            self.starting_equity = acct.equity
            self.halted_reason = None
            self.last_error = None
            set_state("risk_mode", self.risk_mode.name)
            set_state("starting_equity", str(self.starting_equity))
            log_event("info",
                      f"Trading started (mode={self.risk_mode.name}, equity=${acct.equity:,.2f})",
                      risk_mode=self.risk_mode.name)
            self._thread = threading.Thread(target=self._run, daemon=True)
            self.running = True
            self._thread.start()
            return {"ok": True, "risk_mode": self.risk_mode.name, "starting_equity": acct.equity}

    def stop(self, liquidate: bool = False) -> dict:
        with self._lock:
            if not self.running:
                return {"ok": False, "error": "not running"}
            self._stop_flag.set()
            self.running = False
            log_event("info", "Trading stopped by user", risk_mode=self.risk_mode.name)
            if liquidate:
                try:
                    self.client.cancel_all_orders()
                    self.client.close_all_positions(cancel_orders=True)
                    log_event("info", "All positions liquidated.", risk_mode=self.risk_mode.name)
                except Exception as e:
                    log_event("error", f"Liquidation error: {e}", risk_mode=self.risk_mode.name)
            return {"ok": True}

    def status(self) -> dict:
        try:
            acct = self.client.account()
            positions = self.client.positions()
            clock = self.client.market_clock()
        except Exception as e:
            return {
                "running": self.running,
                "risk_mode": self.risk_mode.name,
                "error": str(e),
                "halted_reason": self.halted_reason,
                "account": None,
                "positions": [],
                "market": {"is_open": False},
            }
        return {
            "running": self.running,
            "halted_reason": self.halted_reason,
            "risk_mode": self.risk_mode.name,
            "risk_mode_config": {
                "max_position_pct": self.risk_mode.max_position_pct,
                "max_concurrent_positions": self.risk_mode.max_concurrent_positions,
                "min_trade_dollars": self.risk_mode.min_trade_dollars,
                "stop_loss_pct": self.risk_mode.stop_loss_pct,
                "take_profit_pct": self.risk_mode.take_profit_pct,
                "max_daily_loss_pct": self.risk_mode.max_daily_loss_pct,
                "trailing_activation_pct": self.risk_mode.trailing_activation_pct,
                "trailing_retrace_pct": self.risk_mode.trailing_retrace_pct,
                "stagnation_minutes": self.risk_mode.stagnation_minutes,
                "eod_flatten_minutes": self.risk_mode.eod_flatten_minutes,
                "allow_shorts": self.risk_mode.allow_shorts,
                "max_leverage": self.risk_mode.max_leverage,
                "margin_call_threshold": self.risk_mode.margin_call_threshold,
                "allowed_strategies": self.risk_mode.allowed_strategies,
                "universe_size": len(self.risk_mode.universe),
            },
            "starting_equity": self.starting_equity,
            "last_scan_ts": self.last_scan_ts,
            "last_error": self.last_error,
            "account": {
                "equity": acct.equity,
                "cash": acct.cash,
                "buying_power": acct.buying_power,
                "portfolio_value": acct.portfolio_value,
                "long_market_value": acct.long_market_value,
                "short_market_value": acct.short_market_value,
                "maintenance_margin": acct.maintenance_margin,
                "pattern_day_trader": acct.pattern_day_trader,
            } if acct else None,
            "positions": [{
                "symbol": p.symbol,
                "qty": p.qty,
                "avg_entry_price": p.avg_entry_price,
                "current_price": p.current_price,
                "market_value": p.market_value,
                "unrealized_pl": p.unrealized_pl,
                "unrealized_plpc": p.unrealized_plpc,
                "side": p.side,
                "strategy": self.position_meta.get(p.symbol, {}).get("strategy"),
            } for p in positions],
            "market": clock,
        }

    # ---------------------- main loop ----------------------

    def _run(self) -> None:
        try:
            while not self._stop_flag.is_set():
                try:
                    self._tick()
                except Exception as e:
                    tb = traceback.format_exc()
                    self.last_error = str(e)
                    log_event("error", f"Tick error: {e}\n{tb[:600]}", risk_mode=self.risk_mode.name)
                # sleep in small chunks so stop() reacts fast
                for _ in range(max(1, self.risk_mode.scan_interval_sec)):
                    if self._stop_flag.is_set():
                        return
                    time.sleep(1)
        finally:
            self.running = False

    def _tick(self) -> None:
        self.last_scan_ts = datetime.now(timezone.utc).isoformat()

        acct = self.client.account()
        positions = self.client.positions()

        # --- safety gates ---------------------------------------------------
        if acct.trading_blocked:
            self._halt("account trading blocked")
            return

        # Margin call check — liquidates before Alpaca would
        triggered, msg = margin_call_triggered(acct, self.risk_mode)
        if triggered:
            log_event("margin_call", msg, risk_mode=self.risk_mode.name)
            self._liquidate_weakest(positions, acct)
            return

        # Daily loss circuit breaker
        if self.starting_equity:
            breached, loss = daily_loss_breached(self.starting_equity, acct.equity, self.risk_mode)
            if breached:
                log_event("info",
                          f"Daily loss cap hit ({loss*100:.2f}%) — liquidating and halting.",
                          risk_mode=self.risk_mode.name)
                self._flatten_all()
                self._halt(f"daily loss cap hit ({loss*100:.2f}%)")
                return

        # End-of-day flatten — close everything N minutes before close
        clock = self.client.market_clock()
        mins_left = minutes_until_close(clock)
        if mins_left is not None and mins_left <= self.risk_mode.eod_flatten_minutes:
            if positions:
                log_event("info",
                          f"EOD flatten: {mins_left:.1f} min to close, "
                          f"closing {len(positions)} position(s).",
                          risk_mode=self.risk_mode.name)
                for p in positions:
                    self._close(p, f"eod_flatten ({mins_left:.1f}min to close)")
            return

        # --- manage open positions: 4 exit checks in priority order --------
        for p in positions:
            meta = self.position_meta.setdefault(p.symbol, {})
            # Backfill entry_ts for positions opened before this agent-run
            if "entry_ts" not in meta:
                meta["entry_ts"] = datetime.now(timezone.utc).isoformat()
                meta.setdefault("trail_armed", False)
                meta.setdefault("trail_hwm", 0.0)
            # 1. hard stop-loss / take-profit
            hit, why = should_stop(p, self.risk_mode)
            if hit:
                self._close(p, why)
                continue
            # 2. trailing stop (after position has run in our favor)
            hit, why = should_trailing_stop(p, self.risk_mode, meta)
            if hit:
                self._close(p, why)
                continue
            # 3. stagnation — capital trapped with no movement
            hit, why = should_stagnation_exit(p, self.risk_mode, meta)
            if hit:
                self._close(p, why)
                continue

        # --- scan for new signals if market is open -------------------------
        if not self.client.is_market_open():
            return  # we keep monitoring positions even when closed

        positions = self.client.positions()  # refresh
        open_symbols = {p.symbol for p in positions}

        candidates: list[Signal] = []
        for symbol in self.risk_mode.universe:
            if symbol in open_symbols:
                continue
            df = self.client.bars(symbol, timeframe="5Min", lookback_minutes=240)
            if df.empty or len(df) < 25:
                continue
            for sig in scan(symbol, df, self.risk_mode.allowed_strategies):
                candidates.append(sig)

        candidates.sort(key=lambda s: s.confidence, reverse=True)

        for sig in candidates:
            # Re-check caps each iteration
            positions = self.client.positions()
            open_symbols = {p.symbol for p in positions}
            if sig.symbol in open_symbols:
                continue
            allowed, reason = can_open_new_position(self.risk_mode, positions, sig.side)
            if not allowed:
                log_event("info", f"Skipped {sig.symbol} {sig.side}: {reason}",
                          symbol=sig.symbol, risk_mode=self.risk_mode.name)
                break  # no point checking more if cap is hit

            self._open(sig, acct)

    # ---------------------- order helpers ----------------------

    def _open(self, sig: Signal, account_snapshot) -> None:
        # refresh account to get latest buying power
        acct = self.client.account()
        qty, mult = position_size(
            self.risk_mode, acct, sig.entry_price, confidence=sig.confidence
        )
        if qty <= 0:
            log_event("info",
                      f"Size=0 for {sig.symbol} (conf={sig.confidence:.2f}, mult={mult:.2f}x) — skipping",
                      symbol=sig.symbol, risk_mode=self.risk_mode.name)
            return

        side = "buy" if sig.side == "long" else "sell"
        try:
            order = self.client.market_order(sig.symbol, qty, side=side)
        except Exception as e:
            log_event("error", f"Order rejected for {sig.symbol} {side} {qty}: {e}",
                      symbol=sig.symbol, risk_mode=self.risk_mode.name)
            return

        fill = order["filled_avg_price"] or sig.entry_price
        self.position_meta[sig.symbol] = {
            "strategy": sig.strategy,
            "side": sig.side,
            "entry": fill,
            "confidence": sig.confidence,
            "size_mult": mult,
            "entry_ts": datetime.now(timezone.utc).isoformat(),
            "trail_armed": False,
            "trail_hwm": 0.0,
        }
        notes = f"conf={sig.confidence:.2f} mult={mult:.2f}x | {sig.reason}"
        record_trade(
            symbol=sig.symbol, side=("short" if sig.side == "short" else "buy"),
            qty=qty, price=fill, order_id=order["id"],
            strategy=sig.strategy, risk_mode=self.risk_mode.name, pnl=0.0,
            notes=notes,
        )
        log_event("entry",
                  f"{sig.side.upper()} {qty} {sig.symbol} @ ~${fill:.2f} "
                  f"(conf={sig.confidence:.2f} → {mult*100:.0f}% size) "
                  f"[{sig.strategy}] — {sig.reason}",
                  symbol=sig.symbol, risk_mode=self.risk_mode.name)

    def _close(self, pos: PositionSnapshot, reason: str) -> None:
        try:
            self.client.close_position(pos.symbol)
        except Exception as e:
            log_event("error", f"Close failed for {pos.symbol}: {e}",
                      symbol=pos.symbol, risk_mode=self.risk_mode.name)
            return
        meta = self.position_meta.pop(pos.symbol, {})
        side = "cover" if pos.side == "short" else "sell"
        record_trade(
            symbol=pos.symbol, side=side, qty=abs(pos.qty),
            price=pos.current_price, strategy=meta.get("strategy"),
            risk_mode=self.risk_mode.name, pnl=pos.unrealized_pl,
            notes=reason,
        )
        kind = "stop" if "stop_loss" in reason else "exit"
        log_event(kind,
                  f"CLOSE {pos.symbol} @ ~${pos.current_price:.2f} "
                  f"PnL=${pos.unrealized_pl:+.2f} ({pos.unrealized_plpc*100:+.2f}%) — {reason}",
                  symbol=pos.symbol, risk_mode=self.risk_mode.name)

    def _liquidate_weakest(self, positions: list[PositionSnapshot], acct) -> None:
        """On margin call, close the worst-performing position first and re-check."""
        if not positions:
            return
        worst = min(positions, key=lambda p: p.unrealized_pl)
        self._close(worst, "margin_call liquidation")

    def _flatten_all(self) -> None:
        try:
            self.client.cancel_all_orders()
            self.client.close_all_positions(cancel_orders=True)
        except Exception as e:
            log_event("error", f"Flatten-all failed: {e}", risk_mode=self.risk_mode.name)

    def _halt(self, reason: str) -> None:
        self.halted_reason = reason
        self._stop_flag.set()
        self.running = False
        log_event("info", f"HALTED: {reason}", risk_mode=self.risk_mode.name)


# singleton
agent = TradingAgent()
