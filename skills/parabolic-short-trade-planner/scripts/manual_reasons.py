"""Split manual confirmation reasons into ``blocking`` and ``advisory``.

The screener originally folded everything into a single
``requires_manual_confirmation`` flag, which made every plan look equally
risky. By separating reasons we keep ``trade_allowed_without_manual``
meaningful: it stays True when only advisory reasons (e.g. "go run the
locate ticket at the broker") are present.

Inputs are the ingredient dicts produced by the broker adapter, the SSR
state tracker, ``state_caps``, and the FMP aftermarket quote. Outputs
travel into the Phase 2 JSON unchanged.
"""

from __future__ import annotations


def build_manual_reasons(
    broker_inventory: dict | None,
    ssr_state: dict | None,
    state_caps: list[str] | None,
    warnings: list[str] | None,
    premarket_levels: dict | None,
) -> dict:
    """Return ``{"blocking": [...], "advisory": [...]}``."""
    blocking: list[str] = []
    advisory: list[str] = []

    if broker_inventory is not None:
        if not broker_inventory.get("can_open_new_short", True):
            blocking.append("borrow_inventory_unavailable")
        if broker_inventory.get("borrow_fee_manual_check_required"):
            blocking.append("htb_borrow_fee_unknown")
        if broker_inventory.get("manual_locate_required"):
            advisory.append("manual_locate_required")

    if ssr_state is not None:
        if ssr_state.get("ssr_triggered_today"):
            blocking.append("ssr_active_today")
        if ssr_state.get("ssr_carryover_from_prior_day"):
            blocking.append("ssr_carryover")

    for cap in state_caps or []:
        blocking.append(f"state_cap:{cap}")
    for warn in warnings or []:
        advisory.append(f"warning:{warn}")

    if premarket_levels is not None:
        if (
            premarket_levels.get("premarket_high") is None
            or premarket_levels.get("premarket_low") is None
        ):
            blocking.append("premarket_high_low_unavailable")

    return {"blocking": blocking, "advisory": advisory}


def trade_allowed_without_manual(reasons: dict) -> bool:
    """True iff there are no blocking reasons (advisory-only is OK)."""
    return not reasons.get("blocking")


def requires_manual_confirmation(reasons: dict) -> bool:
    """True iff there is at least one reason of any kind."""
    return bool(reasons.get("blocking") or reasons.get("advisory"))
