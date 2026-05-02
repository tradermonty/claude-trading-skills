"""Compute risk and position-size constraints (the "size recipe").

We deliberately do NOT emit a final share count here. ORL / first-red /
VWAP-fail entries only know their entry and stop after the trigger fires
intraday, so Phase 2 must hand the trader a *recipe* — risk_usd,
max_position_value_usd, and a shares formula — that gets evaluated at
trigger time. This sidesteps the v0.1 plan's bug where Phase 2 baked in
``shares: 200`` from a guessed entry/stop pair.
"""

from __future__ import annotations

SIZING_RULE = "fixed_fractional"
SHARES_FORMULA = (
    "floor(min(risk_usd / (stop_actual - entry_actual), max_position_value_usd / entry_actual))"
)


def build_size_recipe(
    *,
    account_size: float,
    risk_bps: int,
    max_position_pct: float,
    max_short_exposure_pct: float,
    current_short_exposure: float = 0.0,
) -> dict:
    """Return the recipe Phase 3 evaluates at trigger time.

    Args:
        account_size: total account equity in USD.
        risk_bps: per-trade risk in basis points (50 = 0.5 %).
        max_position_pct: per-symbol cap on position dollar value, % of account.
        max_short_exposure_pct: aggregate short book cap, % of account.
        current_short_exposure: current dollar value of open shorts.

    Returns:
        ``size_recipe`` dict shaped for the v1.0 Phase 2 schema.
    """
    if account_size <= 0:
        raise ValueError(f"account_size must be positive, got {account_size}")
    if risk_bps <= 0:
        raise ValueError(f"risk_bps must be positive, got {risk_bps}")
    if max_position_pct <= 0:
        raise ValueError(f"max_position_pct must be positive, got {max_position_pct}")
    if max_short_exposure_pct <= 0:
        raise ValueError(f"max_short_exposure_pct must be positive, got {max_short_exposure_pct}")

    risk_usd = account_size * (risk_bps / 10_000)
    max_position_value_usd = account_size * (max_position_pct / 100)
    max_short_exposure_usd = account_size * (max_short_exposure_pct / 100)

    remaining_short_exposure_capacity = max_short_exposure_usd - current_short_exposure
    exposure_check_passed = remaining_short_exposure_capacity >= max_position_value_usd
    exposure_cap_applied = False
    if remaining_short_exposure_capacity > 0 and not exposure_check_passed:
        # Cap max_position_value_usd at the remaining short-book capacity
        # so the plan still produces a tradeable size. Setting
        # exposure_cap_applied=True flags downstream readers that the
        # per-symbol cap was tightened from the user-supplied default.
        max_position_value_usd = max(0.0, remaining_short_exposure_capacity)
        exposure_cap_applied = True
    elif remaining_short_exposure_capacity <= 0:
        max_position_value_usd = 0.0
        exposure_cap_applied = True

    return {
        "risk_usd": round(risk_usd, 2),
        "max_position_value_usd": round(max_position_value_usd, 2),
        "shares_formula": SHARES_FORMULA,
        "sizing_rule_applied": SIZING_RULE,
        "max_short_exposure_check_passed": exposure_check_passed,
        "exposure_cap_applied": exposure_cap_applied,
        "max_short_exposure_usd": round(max_short_exposure_usd, 2),
        "current_short_exposure_usd": round(current_short_exposure, 2),
        "remaining_short_exposure_capacity_usd": round(
            max(0.0, remaining_short_exposure_capacity), 2
        ),
    }
