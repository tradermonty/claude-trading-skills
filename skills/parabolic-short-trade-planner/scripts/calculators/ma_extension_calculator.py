"""Distance of the latest close from key SMAs.

Returns three measurements that together describe how stretched a parabolic
candidate has become from its trend:

- ``ext_*_pct``: percentage distance from the SMA, signed (positive when
  price is above the MA, negative below).
- ``ext_20dma_atr``: same distance for the 20-DMA expressed in ATR(14)
  units. Volatility-adjusted comparison across symbols.

All inputs must be in chronological order (oldest first).
"""

from __future__ import annotations

from atr_calculator import calculate_atr
from math_helpers import sma


def calculate_ma_extension(
    closes: list[float],
    highs: list[float | None] = None,
    lows: list[float | None] = None,
    atr_period: int = 14,
) -> dict:
    """Compute MA-extension metrics for the most recent close.

    Args:
        closes: Closing prices (chronological).
        highs: Optional high prices for ATR-unit calculation. If not
            provided, ``ext_20dma_atr`` is returned as ``None``.
        lows: Optional low prices, see ``highs``.
        atr_period: ATR window for the volatility-adjusted distance.

    Returns:
        Dict with keys ``ext_10dma_pct``, ``ext_20dma_pct``,
        ``ext_50dma_pct``, ``ext_20dma_atr``, ``close``, ``dma_10``,
        ``dma_20``, ``dma_50``, ``atr_14``. Any value that cannot be
        computed (insufficient history) is ``None``.
    """
    if not closes:
        return {
            "close": None,
            "dma_10": None,
            "dma_20": None,
            "dma_50": None,
            "ext_10dma_pct": None,
            "ext_20dma_pct": None,
            "ext_50dma_pct": None,
            "atr_14": None,
            "ext_20dma_atr": None,
        }

    close = closes[-1]
    dma_10 = sma(closes, 10)
    dma_20 = sma(closes, 20)
    dma_50 = sma(closes, 50)

    def _pct(ma: float | None) -> float | None:
        if ma is None or ma == 0:
            return None
        return (close - ma) / ma * 100.0

    atr_14: float | None = None
    ext_20dma_atr: float | None = None
    if highs is not None and lows is not None and dma_20 is not None:
        atr_value = calculate_atr(highs, lows, closes, period=atr_period)
        if atr_value > 0:
            atr_14 = atr_value
            ext_20dma_atr = (close - dma_20) / atr_value

    return {
        "close": close,
        "dma_10": dma_10,
        "dma_20": dma_20,
        "dma_50": dma_50,
        "ext_10dma_pct": _pct(dma_10),
        "ext_20dma_pct": _pct(dma_20),
        "ext_50dma_pct": _pct(dma_50),
        "atr_14": atr_14,
        "ext_20dma_atr": ext_20dma_atr,
    }
