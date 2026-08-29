"""
Market Top Detector - Shared Utilities

Common helper functions used across multiple modules.
"""

from datetime import date

from _market_calendar import count_sessions


def count_business_days(start_date: date, end_date: date) -> int:
    """Count business days between start (exclusive) and end (inclusive).

    Friday→Monday = 1 business day.
    Returns -1 if start_date > end_date (future date).
    """
    if start_date > end_date:
        return -1
    return count_sessions(
        "XNYS",
        start_date,
        end_date,
        include_start=False,
        include_end=True,
    )
