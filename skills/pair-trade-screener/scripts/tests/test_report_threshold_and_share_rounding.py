"""Regression tests for issue #909: report direction at the entry threshold and
fractional share counts.

Both defects live in ``analyze_spread.print_analysis_report``: a z-score exactly
equal to ``+entry_zscore`` fell through to the LONG SPREAD branch (and the
position-sizing block did the same), and the sizing lines printed whole share
counts while showing dollar amounts computed from the fractional sizes.

Written with the stdlib ``unittest`` runner so the behavior can be replayed
without pytest; the repository's pytest suite collects ``TestCase`` classes too.
"""

import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analyze_spread
import numpy as np
import pandas as pd

BETA = 1.2
ENTRY = 2.0
ALLOCATION = 10000.0


def _price_series(length=150, seed=909):
    """Two price series whose spread varies, so the rolling z-score is finite."""
    index = pd.date_range("2025-01-01", periods=length, freq="D")
    rng = np.random.default_rng(seed)
    prices_b = pd.Series(48.0 + np.cumsum(rng.normal(0, 0.3, length)), index=index, name="BBB")
    noise = np.zeros(length)
    for position in range(1, length):
        noise[position] = 0.4 * noise[position - 1] + rng.normal(0, 0.2)
    noise[-1] = 2.0
    prices_a = pd.Series(BETA * prices_b.to_numpy() + noise + 20.0, index=index, name="AAA")
    return prices_a, prices_b


def render_report(current_zscore, entry=ENTRY):
    """Render the report for an explicit current z-score and return its output."""
    prices_a, prices_b = _price_series()
    spread = prices_a - BETA * prices_b
    zscore = analyze_spread.calculate_zscore_series(spread, window=90)
    cointegration = {
        "adf_statistic": -4.5,
        "p_value": 0.001,
        "critical_values": {"1%": -3.5, "5%": -2.9, "10%": -2.6},
        "is_cointegrated": True,
    }
    beta_result = {"beta": BETA, "r_value": 0.97, "r_squared": 0.94}
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        analyze_spread.print_analysis_report(
            "AAA",
            "BBB",
            prices_a,
            prices_b,
            beta_result,
            spread,
            cointegration,
            20.0,
            zscore,
            current_zscore,
            entry,
            0.5,
        )
    return buffer.getvalue(), prices_a, prices_b


class ThresholdDirectionTest(unittest.TestCase):
    def test_positive_threshold_is_short_spread(self):
        out, _, _ = render_report(ENTRY)

        self.assertIn("Signal: 🔻 SHORT SPREAD", out)
        self.assertIn("Action: Short AAA, Long BBB", out)
        self.assertNotIn("Signal: 🔺 LONG SPREAD", out)
        self.assertIn("[ POSITION SIZING ]", out)
        self.assertIn("SHORT AAA:", out)
        self.assertIn("LONG BBB:", out)

    def test_negative_threshold_is_long_spread(self):
        out, _, _ = render_report(-ENTRY)

        self.assertIn("Signal: 🔺 LONG SPREAD", out)
        self.assertIn("Action: Long AAA, Short BBB", out)
        self.assertNotIn("Signal: 🔻 SHORT SPREAD", out)
        self.assertIn("[ POSITION SIZING ]", out)
        self.assertIn("LONG AAA:", out)
        self.assertIn("SHORT BBB:", out)


class ShareCountRenderingTest(unittest.TestCase):
    def test_fractional_share_counts_keep_the_hedge_ratio_and_notionals(self):
        out, prices_a, prices_b = render_report(2.4)
        sizing = analyze_spread.calculate_position_sizing(
            float(prices_a.iloc[-1]), float(prices_b.iloc[-1]), BETA, ALLOCATION
        )
        self.assertIsNotNone(sizing)
        assert sizing is not None
        legs = re.findall(r"\$([\d,]+) \((\d+\.\d{2}) shares @ \$[\d.]+\)", out)
        self.assertEqual(len(legs), 2, out)
        printed = {shares: int(dollars.replace(",", "")) for dollars, shares in legs}

        expected_a = f"{sizing['shares_a']:.2f}"
        expected_b = f"{sizing['shares_b']:.2f}"
        self.assertEqual(set(printed), {expected_a, expected_b})

        # The printed share counts still hedge beta once rounded to 2 decimals.
        self.assertAlmostEqual(float(expected_b) / float(expected_a), BETA, delta=0.01)

        # And each printed notional matches share count x price at whole dollars.
        price_by_shares = {
            expected_a: float(prices_a.iloc[-1]),
            expected_b: float(prices_b.iloc[-1]),
        }
        for shares, dollars in printed.items():
            self.assertLessEqual(abs(round(float(shares) * price_by_shares[shares]) - dollars), 2)

        self.assertIn("Share counts are fractional, shown to 2 decimals", out)
        self.assertIn("dollar amounts use the unrounded sizes", out)


if __name__ == "__main__":
    unittest.main()
