"""Session-anchored Volume-Weighted Average Price helper.

Phase 3 evaluators consume *cumulative session* VWAP, NOT a rolling
window VWAP. The cumulative form is the standard one quoted on chart
software for intraday short-side decisions: it resets at 09:30 ET and
includes every regular-session bar through ``ts``.

Contract:
- Input ``bars`` is the same chronological list of dicts the adapter
  produces (``{"ts_et", "o", "h", "l", "c", "v"}``), already filtered
  to the regular session.
- ``vwap_for_each_bar(bars)`` returns a list of equal length, where
  ``out[i]`` is the cumulative VWAP through ``bars[0..i]`` inclusive.
- Typical bar VWAP input is the bar's ``c`` (close); we use ``c``
  because the playbook references "5-min close vs VWAP" decisions.
  Some software uses ``hlc/3`` — that's a different convention; we
  pin to close so the FSM matches the bar-close trigger semantics.
"""

from __future__ import annotations


def vwap_for_each_bar(bars: list[dict]) -> list[float]:
    """Return cumulative VWAP through each bar (close-based).

    Bars with ``v == 0`` are tolerated: they don't contribute to either
    numerator or denominator, and the running VWAP carries forward.
    """
    out: list[float] = []
    cum_pv = 0.0
    cum_v = 0
    for bar in bars:
        v = int(bar["v"])
        c = float(bar["c"])
        cum_pv += c * v
        cum_v += v
        if cum_v == 0:
            # Pre-print or null-volume run; VWAP undefined → echo close.
            out.append(c)
        else:
            out.append(cum_pv / cum_v)
    return out
