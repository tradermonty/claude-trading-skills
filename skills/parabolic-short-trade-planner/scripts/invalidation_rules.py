"""Hard invalidation rules — applied before scoring to drop candidates that
should never appear on a Parabolic Short watchlist regardless of how
"parabolic" their chart looks.

Mode-aware: ``safe_largecap`` rejects more candidates (market cap < $2B,
ADV < $20M); ``classic_qm`` is permissive on size (cap < $300M, ADV < $5M)
to keep the small-cap blow-offs that Qullamaggie targets in scope.

Each rule reports its own reason string so the screener can render an
auditable rejection log.
"""

from __future__ import annotations

MODE_THRESHOLDS = {
    "safe_largecap": {
        "min_market_cap_usd": 2_000_000_000,
        "min_adv_usd": 20_000_000,
        "min_price_usd": 5.00,
        "min_days_listed": 60,
        "earnings_blackout_days": 2,
    },
    "classic_qm": {
        "min_market_cap_usd": 300_000_000,
        "min_adv_usd": 5_000_000,
        "min_price_usd": 5.00,
        "min_days_listed": 60,
        "earnings_blackout_days": 2,
    },
}


def check_invalidation(
    candidate: dict,
    mode: str = "safe_largecap",
    override: dict | None = None,
) -> dict:
    """Decide whether a candidate is excluded from scoring.

    Args:
        candidate: dict with keys ``ticker``, ``close``, ``market_cap_usd``,
            ``adv_20d_usd``, ``days_listed``, ``earnings_within_days``,
            ``catalyst_blackout`` (optional bool).
        mode: ``safe_largecap`` (default) or ``classic_qm``.
        override: per-rule threshold overrides (e.g. ``{"min_adv_usd": 1e7}``).

    Returns:
        dict with ``is_invalid`` (bool) and ``reasons`` (list[str]).
    """
    if mode not in MODE_THRESHOLDS:
        raise ValueError(f"unknown mode: {mode!r}")
    thresholds = dict(MODE_THRESHOLDS[mode])
    if override:
        thresholds.update(override)

    reasons: list[str] = []

    earnings_within = candidate.get("earnings_within_days")
    if earnings_within is not None and earnings_within <= thresholds["earnings_blackout_days"]:
        reasons.append(
            f"earnings_within_{earnings_within}d_blackout_{thresholds['earnings_blackout_days']}d"
        )

    market_cap = candidate.get("market_cap_usd")
    if market_cap is not None and market_cap < thresholds["min_market_cap_usd"]:
        reasons.append(f"market_cap_{market_cap:.0f}_below_{thresholds['min_market_cap_usd']:.0f}")

    adv = candidate.get("adv_20d_usd")
    if adv is not None and adv < thresholds["min_adv_usd"]:
        reasons.append(f"adv_{adv:.0f}_below_{thresholds['min_adv_usd']:.0f}")

    close = candidate.get("close")
    if close is not None and close < thresholds["min_price_usd"]:
        reasons.append(f"price_{close:.2f}_below_{thresholds['min_price_usd']:.2f}")

    days_listed = candidate.get("days_listed")
    if days_listed is not None and days_listed < thresholds["min_days_listed"]:
        reasons.append(f"listed_only_{days_listed}d_below_{thresholds['min_days_listed']}d")

    if candidate.get("catalyst_blackout"):
        reasons.append("catalyst_blackout_user_csv")

    return {"is_invalid": bool(reasons), "reasons": reasons}
