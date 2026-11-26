"""Regression tests for missing price-bar values in month-end downsampling (issue #655)."""

import math
import unittest

from calculators.utils import calculate_ratio, downsample_to_monthly


class PriceBarGapTest(unittest.TestCase):
    def test_unusable_adjclose_falls_back_to_close(self):
        bars = [
            {"date": "2026-02-27", "adjClose": None, "close": 110.0},
            {"date": "2026-01-30", "adjClose": math.nan, "close": 100.0},
        ]
        monthly = downsample_to_monthly(bars)
        self.assertEqual([b["close"] for b in monthly], [110.0, 100.0])

    def test_month_without_usable_close_is_skipped(self):
        for bad in ("100", True, 0, -5, math.inf, -math.inf, math.nan):
            with self.subTest(value=bad):
                self.assertEqual(
                    downsample_to_monthly(
                        [
                            {"date": "2026-03-31", "adjClose": bad, "close": bad},
                            {"date": "2026-02-27", "close": 100.0},
                        ]
                    ),
                    [{"date": "2026-02-27", "close": 100.0}],
                )

    def test_ratio_stays_finite_after_a_dropped_month(self):
        ratios = calculate_ratio(
            downsample_to_monthly(
                [
                    {"date": "2026-02-27", "adjClose": None, "close": 110.0},
                    {"date": "2026-01-30", "adjClose": math.nan, "close": math.nan},
                ]
            ),
            downsample_to_monthly(
                [
                    {"date": "2026-02-27", "adjClose": math.nan, "close": 90.0},
                    {"date": "2026-01-30", "close": 80.0},
                ]
            ),
        )
        self.assertEqual([i["date"] for i in ratios], ["2026-02-27"])
        self.assertTrue(all(math.isfinite(i["value"]) for i in ratios))


if __name__ == "__main__":
    unittest.main()
