"""Convert Phase 2's ``size_recipe`` + Phase 3 trigger prices into a
concrete share count.

Why this is its own module: Phase 2 emits ``size_recipe.shares_formula``
as a **string** for documentation / postmortem clarity. Phase 3 must
NOT eval that string (no ``eval``, no ``exec``, no ``asteval``) — the
formula is implemented here in code, and the contract is:

    floor(min(risk_usd / (stop_actual - entry_actual),
              max_position_value_usd / entry_actual))

If anyone changes the formula, both ``size_recipe_builder.SHARES_FORMULA``
and this implementation must change together. ``test_intraday_size_resolver.py
::test_size_recipe_string_matches_resolver`` enforces the link.
"""

from __future__ import annotations

import math


def resolve_shares(
    *,
    entry_actual: float,
    stop_actual: float,
    risk_usd: float,
    max_position_value_usd: float,
) -> int:
    """Return the integer share count for this short trigger.

    Short side requires ``stop_actual > entry_actual`` (the stop sits
    above the entry, so a buy-to-cover at the stop loses
    ``stop - entry`` per share). Inputs must all be positive.
    """
    if entry_actual <= 0:
        raise ValueError(f"entry_actual must be positive: {entry_actual!r}")
    if stop_actual <= entry_actual:
        raise ValueError(
            "short trigger requires stop_actual > entry_actual; "
            f"got stop={stop_actual!r}, entry={entry_actual!r}"
        )
    if risk_usd <= 0:
        raise ValueError(f"risk_usd must be positive: {risk_usd!r}")
    if max_position_value_usd <= 0:
        raise ValueError(f"max_position_value_usd must be positive: {max_position_value_usd!r}")

    risk_per_share = stop_actual - entry_actual
    shares_by_risk = risk_usd / risk_per_share
    shares_by_cap = max_position_value_usd / entry_actual
    return math.floor(min(shares_by_risk, shares_by_cap))


def resolve_size_recipe(
    size_recipe: dict,
    *,
    entry_actual: float,
    stop_actual: float,
) -> dict:
    """Resolve a Phase 2 ``size_recipe`` dict into the Phase 3
    ``size_recipe_resolved`` dict that goes on the intraday plan."""
    shares = resolve_shares(
        entry_actual=entry_actual,
        stop_actual=stop_actual,
        risk_usd=float(size_recipe["risk_usd"]),
        max_position_value_usd=float(size_recipe["max_position_value_usd"]),
    )
    risk_per_share = stop_actual - entry_actual
    risk_at_trigger_usd = round(shares * risk_per_share, 2)
    return {
        "shares_formula": size_recipe["shares_formula"],
        "shares_actual": shares,
        "risk_at_trigger_usd": risk_at_trigger_usd,
    }
