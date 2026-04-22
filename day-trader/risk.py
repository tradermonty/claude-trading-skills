"""Risk management: position sizing, stop losses, margin call detection."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from alpaca_client import AccountSnapshot, PositionSnapshot
from config import RiskMode


def confidence_multiplier(confidence: float) -> float:
    """Map signal confidence (0.5-1.0) to a size multiplier (0.4-1.0).

    Linear ramp: conf=0.5 → 40% size, conf=0.75 → 70% size, conf=1.0 → 100% size.
    Below 0.5 confidence, multiplier floors at 0.4 (still tradeable but small).
    """
    scaled = 0.4 + (confidence - 0.5) * 1.2
    return max(0.4, min(1.0, scaled))


def position_size(
    risk_mode: RiskMode,
    account: AccountSnapshot,
    entry_price: float,
    confidence: float = 1.0,
) -> tuple[int, float]:
    """Return (shares, multiplier_used) for a new position.

    Max $ per trade = equity × max_position_pct × max_leverage × confidence_multiplier.
    Then capped by actual buying power so orders don't get rejected.
    Returns (0, multiplier) if below the risk mode's min_trade_dollars threshold.
    """
    mult = confidence_multiplier(confidence)
    if entry_price <= 0:
        return 0, mult

    # Max $ per trade — leverage × confidence scaling
    position_dollars = (
        account.equity
        * risk_mode.max_position_pct
        * risk_mode.max_leverage
        * mult
    )

    # Cap by actual buying power to avoid insufficient-funds rejections
    position_dollars = min(position_dollars, account.buying_power * 0.95)

    # Enforce minimum trade size — avoid sub-$2k "dust" trades
    if position_dollars < risk_mode.min_trade_dollars:
        return 0, mult

    shares = math.floor(position_dollars / entry_price)
    if shares * entry_price < risk_mode.min_trade_dollars:
        return 0, mult
    return max(shares, 0), mult


def stop_price(entry_price: float, side: str, risk_mode: RiskMode) -> float:
    if side == "long":
        return entry_price * (1 - risk_mode.stop_loss_pct)
    return entry_price * (1 + risk_mode.stop_loss_pct)


def take_profit_price(entry_price: float, side: str, risk_mode: RiskMode) -> float:
    if side == "long":
        return entry_price * (1 + risk_mode.take_profit_pct)
    return entry_price * (1 - risk_mode.take_profit_pct)


def should_stop(position: PositionSnapshot, risk_mode: RiskMode) -> tuple[bool, str]:
    """Check if stop-loss or take-profit hit for a position."""
    pct = position.unrealized_plpc  # already as fraction (0.01 = 1%)
    # Alpaca returns this as signed for both long and short (good P&L is positive)
    if pct <= -risk_mode.stop_loss_pct:
        return True, f"stop_loss hit ({pct*100:.2f}%)"
    if pct >= risk_mode.take_profit_pct:
        return True, f"take_profit hit (+{pct*100:.2f}%)"
    return False, ""


def should_trailing_stop(
    position: PositionSnapshot,
    risk_mode: RiskMode,
    meta: dict,
) -> tuple[bool, str]:
    """Close position if it has retraced from its high-water-mark after arming.

    The trailing stop arms only once unrealized PnL% >= trailing_activation_pct.
    Once armed, we track the highest PnL% seen; if current PnL% drops by
    trailing_retrace_pct from that peak, exit.

    `meta` is the per-symbol dict in trader.position_meta — we mutate it
    to persist the HWM across ticks.
    """
    pct = position.unrealized_plpc
    armed = meta.get("trail_armed", False)
    hwm = meta.get("trail_hwm", pct)

    # Arm once we're in profit by the activation threshold
    if not armed and pct >= risk_mode.trailing_activation_pct:
        meta["trail_armed"] = True
        meta["trail_hwm"] = pct
        return False, ""

    if not armed:
        return False, ""

    # Update HWM if we set a new high
    if pct > hwm:
        meta["trail_hwm"] = pct
        return False, ""

    # Exit if we've retraced enough from HWM
    if hwm - pct >= risk_mode.trailing_retrace_pct:
        return True, (
            f"trailing_stop (peak {hwm*100:+.2f}% → {pct*100:+.2f}%, "
            f"retrace {(hwm-pct)*100:.2f}%)"
        )
    return False, ""


def should_stagnation_exit(
    position: PositionSnapshot,
    risk_mode: RiskMode,
    meta: dict,
) -> tuple[bool, str]:
    """Close position if it has been open > stagnation_minutes with tiny PnL.

    "Tiny" = |PnL%| < 0.3%. A sideways position is capital that could be
    deployed into a better signal.
    """
    entry_ts = meta.get("entry_ts")
    if not entry_ts:
        return False, ""
    if isinstance(entry_ts, str):
        try:
            entry_ts = datetime.fromisoformat(entry_ts)
        except ValueError:
            return False, ""
    now = datetime.now(timezone.utc)
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.replace(tzinfo=timezone.utc)
    age = now - entry_ts
    if age < timedelta(minutes=risk_mode.stagnation_minutes):
        return False, ""
    if abs(position.unrealized_plpc) < 0.003:
        return True, (
            f"stagnation_exit ({age.total_seconds()/60:.0f}min, "
            f"PnL {position.unrealized_plpc*100:+.2f}%)"
        )
    return False, ""


def minutes_until_close(market_clock: dict) -> float | None:
    """Return minutes until market close, or None if not open/unknown."""
    if not market_clock.get("is_open"):
        return None
    nc = market_clock.get("next_close")
    if not nc:
        return None
    try:
        close_dt = datetime.fromisoformat(nc.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    if close_dt.tzinfo is None:
        close_dt = close_dt.replace(tzinfo=timezone.utc)
    delta = (close_dt - now).total_seconds() / 60
    return delta


def daily_loss_breached(
    starting_equity: float,
    current_equity: float,
    risk_mode: RiskMode,
) -> tuple[bool, float]:
    if starting_equity <= 0:
        return False, 0.0
    loss_pct = (starting_equity - current_equity) / starting_equity
    return loss_pct >= risk_mode.max_daily_loss_pct, loss_pct


def margin_call_triggered(account: AccountSnapshot, risk_mode: RiskMode) -> tuple[bool, str]:
    """Simulate a margin call.

    Alpaca already enforces regulatory margin, but we add our own stricter
    threshold so HIGH mode can actually experience "margin calls" that
    force-liquidate positions before Alpaca would.
    """
    if risk_mode.max_leverage <= 1.0:
        return False, ""  # cash mode — no margin call possible

    # Total exposure (longs + shorts as absolute)
    exposure = abs(account.long_market_value) + abs(account.short_market_value)
    if exposure <= 0:
        return False, ""

    equity_ratio = account.equity / exposure
    if equity_ratio < risk_mode.margin_call_threshold:
        return True, (
            f"MARGIN CALL: equity/exposure={equity_ratio*100:.1f}% "
            f"below {risk_mode.margin_call_threshold*100:.0f}% threshold"
        )
    return False, ""


def can_open_new_position(
    risk_mode: RiskMode,
    positions: list[PositionSnapshot],
    intended_side: str,
) -> tuple[bool, str]:
    # Total concurrent cap
    if len(positions) >= risk_mode.max_concurrent_positions:
        return False, f"max concurrent positions ({risk_mode.max_concurrent_positions}) reached"

    # Short-specific limits
    if intended_side == "short":
        if not risk_mode.allow_shorts:
            return False, "shorts not allowed in this risk mode"
        shorts_open = sum(1 for p in positions if p.side == "short")
        if shorts_open >= risk_mode.max_short_positions:
            return False, f"max shorts ({risk_mode.max_short_positions}) reached"

    return True, ""
