"""State caps and warnings — soft signals attached to a candidate that
*don't* exclude it from the watchlist but constrain how Phase 2 turns it
into a trade plan.

Three signals:

- ``still_in_markup``: the chart is still printing closes near session
  highs at fresh 52-week highs. Treated as a state cap (not a hard kill)
  so A/B candidates remain visible, but Phase 2 forces
  ``trade_allowed_without_manual=False`` via ``manual_reasons`` (blocking).
- ``too_early_to_short``: today closed in the top 80 % of its range with
  expanding volume. Advisory only — Phase 2 keeps the plan but flags
  ``wait_for_trigger=True`` on every entry.
- ``wait_for_first_crack``: pre-market is gapping up another 5 %+. Phase
  2 emphasises the First Red 5-min plan.
"""

from __future__ import annotations


def evaluate_state_caps(
    candidate: dict,
    *,
    high_close_pct_in_range: float = 0.80,
    volume_ratio_threshold: float = 2.0,
    premarket_gap_threshold_pct: float = 5.0,
) -> dict:
    """Return ``{"state_caps": [...], "warnings": [...]}`` for a candidate.

    Required keys on ``candidate``:
        - ``close``, ``session_high``, ``session_low``
        - ``is_at_52w_high_recently`` (bool, true if hit within 2 sessions)
        - ``volume_ratio_20d`` (latest / 20-day avg)
        - ``premarket_gap_pct`` (None if not yet computed)
    """
    state_caps: list[str] = []
    warnings: list[str] = []

    close = candidate.get("close")
    sh = candidate.get("session_high")
    sl = candidate.get("session_low")
    range_pos: float | None = None
    if close is not None and sh is not None and sl is not None and sh > sl:
        range_pos = (close - sl) / (sh - sl)

    closing_strong = range_pos is not None and range_pos >= high_close_pct_in_range
    at_52w_recent = bool(candidate.get("is_at_52w_high_recently"))

    if closing_strong and at_52w_recent:
        state_caps.append("still_in_markup")

    vol_ratio = candidate.get("volume_ratio_20d")
    if (
        closing_strong
        and vol_ratio is not None
        and vol_ratio >= volume_ratio_threshold
        and "still_in_markup" not in state_caps
    ):
        # Skip if already capped — still_in_markup is the stronger signal.
        warnings.append("too_early_to_short")

    pm_gap = candidate.get("premarket_gap_pct")
    if pm_gap is not None and pm_gap >= premarket_gap_threshold_pct:
        warnings.append("wait_for_first_crack")

    return {"state_caps": state_caps, "warnings": warnings}
