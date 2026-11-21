"""Regular-only 5-year average yield reconstruction (issue #834).

Pure and offline: no network, no file reads except the explicit JSON loader.
The Step 5 buy target needs a 5-year average yield whose numerator contains
regular dividends only. Provider annual ratios bundle specials, so the average
is rebuilt here from dividend rows plus daily closes:

* observation dates: last trading day of each of the 60 months ending with the
  last fully completed month on or before ``as_of``;
* price: the split-adjusted (not dividend-adjusted) ``close`` of that row;
* numerator: ``dividend_basis.analyze_dividends(..., as_of_date=t)``'s
  ``latest_declared_annualized`` (point-in-time, specials removed).

Anything that cannot be proven regular fails closed to ``WITHHELD``.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from dividend_basis import _is_explicit_special, analyze_dividends
from thresholds import (
    REGULAR_YIELD_FETCH_BUFFER_DAYS,
    REGULAR_YIELD_GAP_TOLERANCE,
    REGULAR_YIELD_MIN_COVERAGE,
    REGULAR_YIELD_OBSERVATIONS,
    REGULAR_YIELD_YEARS,
)

METHOD = "month_end_60_regular_only_v1"

_NOMINAL_DAYS = {"monthly": 30, "quarterly": 91, "semiannual": 182, "annual": 365}
_FREQUENCY_WORDS = {
    "monthly": "monthly",
    "quarterly": "quarterly",
    "semi-annual": "semiannual",
    "semiannual": "semiannual",
    "semi annual": "semiannual",
    "annual": "annual",
}
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class YieldHistoryInputError(ValueError):
    """Invalid --yield-history-json content; fail before provider calls."""


@dataclass
class RegularYieldHistory:
    status: str  # "OK" | "WITHHELD"
    avg_yield_pct: float | None = None
    observation_count: int = 0
    expected_observations: int = REGULAR_YIELD_OBSERVATIONS
    coverage_ratio: float = 0.0
    window_start: str | None = None
    window_end: str | None = None
    method: str = METHOD
    source: str | None = None
    reasons: list[str] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Row-safe view: everything except the audit observation list."""
        return {
            "status": self.status,
            "avg_yield_pct": self.avg_yield_pct,
            "observation_count": self.observation_count,
            "expected_observations": self.expected_observations,
            "coverage_ratio": self.coverage_ratio,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "method": self.method,
            "source": self.source,
            "reasons": list(self.reasons),
        }


def _parse_iso(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()[:10]
    if not _ISO_DATE.fullmatch(text):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _positive_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _shift_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # Feb 29
        return day.replace(year=day.year - years, day=28)


def fetch_window_start(as_of: str) -> str:
    """First calendar day to request prices from (5y + buffer before as_of)."""
    parsed = _parse_iso(as_of)
    if parsed is None:
        raise ValueError("as_of must be YYYY-MM-DD")
    start = _shift_years(parsed, REGULAR_YIELD_YEARS) - timedelta(
        days=REGULAR_YIELD_FETCH_BUFFER_DAYS
    )
    return start.isoformat()


def apply_frequency_special_label(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy; FMP ``frequency == "Special"`` with no label -> label special.

    "Irregular" is deliberately NOT special. The raw ``frequency`` is kept.
    """
    out = dict(row)
    freq = out.get("frequency")
    has_label = isinstance(out.get("label"), str) and out["label"].strip()
    if not has_label and isinstance(freq, str) and freq.strip().lower() == "special":
        out["label"] = "special"
    return out


def _prepare_dividend_rows(dividends: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Split-adjusted amount into ``dividend``; report whether every row had adjDividend."""
    rows: list[dict[str, Any]] = []
    all_adjusted = True
    for item in dividends or []:
        if not isinstance(item, dict):
            continue
        row = apply_frequency_special_label(item)
        adj = _positive_float(row.get("adjDividend"))
        if adj is not None:
            row["dividend"] = adj
        else:
            all_adjusted = False
        rows.append(row)
    return rows, all_adjusted


def _month_list(as_of: date) -> list[tuple[int, int]]:
    """The 60 (year, month) pairs ending with the last completed month."""
    if (as_of + timedelta(days=1)).month != as_of.month:
        last = (as_of.year, as_of.month)  # as_of is itself a month end
    else:
        last = (as_of.year, as_of.month - 1) if as_of.month > 1 else (as_of.year - 1, 12)
    index = last[0] * 12 + (last[1] - 1)
    months = []
    for offset in range(REGULAR_YIELD_OBSERVATIONS - 1, -1, -1):
        value = index - offset
        months.append((value // 12, value % 12 + 1))
    return months


def _month_end_prices(
    prices: list[dict[str, Any]],
) -> tuple[dict[tuple[int, int], tuple[date, float]], date | None]:
    best: dict[tuple[int, int], tuple[date, float]] = {}
    earliest: date | None = None
    for item in prices or []:
        if not isinstance(item, dict):
            continue
        day = _parse_iso(item.get("date"))
        close = _positive_float(item.get("close"))  # never adjClose
        if day is None or close is None:
            continue
        if earliest is None or day < earliest:
            earliest = day
        key = (day.year, day.month)
        if key not in best or day > best[key][0]:
            best[key] = (day, close)
    return best, earliest


def _invalid_kind(basis, rows: list[dict[str, Any]], t: date) -> str | None:
    if basis.status != "OK":
        return "basis_not_ok"
    if basis.cadence == "irregular":
        return "cadence_irregular"
    if basis.variable_policy_flag:
        return "variable_policy"
    if basis.pays_per_year is None or basis.latest_declared_annualized is None:
        return "pays_per_year_missing"
    used = basis.dividend_dates_used
    nominal = _NOMINAL_DAYS.get(basis.cadence)
    if len(used) < 2 or nominal is None:
        return "gap_unverifiable"
    last, prev = _parse_iso(used[-1]), _parse_iso(used[-2])
    if last is None or prev is None:
        return "gap_unverifiable"
    gap = (last - prev).days
    low, high = REGULAR_YIELD_GAP_TOLERANCE
    if not (low * nominal <= gap <= high * nominal):
        return "gap_outside_cadence"
    # FMP frequency of the latest regular row must agree with the inferred cadence.
    words = []
    for row in rows:
        if _parse_iso(row.get("date")) != last or _is_explicit_special(row.get("label")):
            continue
        freq = row.get("frequency")
        if isinstance(freq, str) and freq.strip().lower() in _FREQUENCY_WORDS:
            words.append(_FREQUENCY_WORDS[freq.strip().lower()])
    if words and basis.cadence not in words:
        return "frequency_mismatch"
    return None


def reconstruct_regular_yield(
    dividends: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    *,
    as_of: str,
    splits: list[dict[str, Any]] | None = None,
    source: str | None = None,
) -> RegularYieldHistory:
    """Rebuild the regular-only 5-year average yield, or WITHHOLD with reasons.

    ``splits=None`` means no split is known; pass the provider's split rows
    when available so an in-window split is checked against ``adjDividend``.
    """
    as_of_date = _parse_iso(as_of)
    if as_of_date is None:
        raise ValueError("as_of must be YYYY-MM-DD")

    months = _month_list(as_of_date)
    prices_by_month, earliest_price = _month_end_prices(prices)
    rows, _ = _prepare_dividend_rows(dividends)

    result = RegularYieldHistory(status="WITHHELD", source=source)
    reasons: list[str] = []

    def note(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    first_key = months[0]
    if earliest_price is None or (earliest_price.year, earliest_price.month) > first_key:
        note("price_history_shorter_than_5y")

    first_obs_date = prices_by_month[first_key][0] if first_key in prices_by_month else None
    window_floor = date(first_key[0], first_key[1], 1)
    regular_dates = []
    for row in rows:
        day = _parse_iso(row.get("date"))
        amount = _positive_float(row.get("dividend"))
        if day is None or amount is None or _is_explicit_special(row.get("label")):
            continue
        regular_dates.append(day)
    probe = first_obs_date or window_floor
    if not regular_dates or min(regular_dates) > probe:
        note("dividend_history_shorter_than_5y")

    valid: list[dict[str, Any]] = []
    for key in months:
        if key not in prices_by_month:
            note("invalid_observation:missing_price_month")
            continue
        day, close = prices_by_month[key]
        basis = analyze_dividends(rows, close, as_of_date=day.isoformat())
        kind = _invalid_kind(basis, rows, day)
        if kind:
            note(f"invalid_observation:{kind}")
            continue
        annualized = float(basis.latest_declared_annualized)
        valid.append(
            {
                "date": day.isoformat(),
                "close": close,
                "regular_annualized": annualized,
                "yield_pct": annualized / close * 100.0,
            }
        )

    result.observations = valid
    result.observation_count = len(valid)
    result.coverage_ratio = round(len(valid) / REGULAR_YIELD_OBSERVATIONS, 4)
    window_end_key = months[-1]
    result.window_start = date(first_key[0], first_key[1], 1).isoformat()
    last_day = date(
        window_end_key[0] + (window_end_key[1] == 12), window_end_key[1] % 12 + 1, 1
    ) - timedelta(days=1)
    result.window_end = last_day.isoformat()

    if result.coverage_ratio < REGULAR_YIELD_MIN_COVERAGE:
        note("coverage_below_threshold")

    # Split basis: dividend amounts must be split-adjusted like the closes.
    in_window_split = False
    for split in splits or []:
        day = _parse_iso(split.get("date")) if isinstance(split, dict) else None
        if day is not None and window_floor <= day <= last_day:
            in_window_split = True
    if in_window_split:
        floor = window_floor - timedelta(days=400)
        for row in rows:
            day = _parse_iso(row.get("date"))
            if day is None or not (floor <= day <= last_day):
                continue
            if _positive_float(row.get("adjDividend")) is None:
                note("split_basis_unverified")
                break

    result.reasons = reasons
    withhold = {
        "price_history_shorter_than_5y",
        "dividend_history_shorter_than_5y",
        "coverage_below_threshold",
        "split_basis_unverified",
    }
    if valid and not (withhold & set(reasons)):
        result.status = "OK"
        result.avg_yield_pct = round(sum(o["yield_pct"] for o in valid) / len(valid), 2)
    return result


# --- verified-input file (--yield-history-json) -------------------------------


def _fail(path: str, message: str) -> YieldHistoryInputError:
    return YieldHistoryInputError(f"Invalid --yield-history-json: {path}: {message}")


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_yield_history(path: Path) -> dict[str, dict[str, Any]]:
    """Validate the verified-input file. Never echoes raw field values."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise YieldHistoryInputError(
            "Invalid --yield-history-json: file is unreadable or not valid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise _fail("root", "expected an object keyed by ticker")

    result: dict[str, dict[str, Any]] = {}
    for raw_ticker, entry in payload.items():
        ticker = str(raw_ticker).strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-^=]{0,19}", ticker) or ticker in result:
            raise _fail("ticker", "invalid or duplicate ticker key")
        if not isinstance(entry, dict):
            raise _fail(ticker, "expected an object")
        if not _nonempty_str(entry.get("source")):
            raise _fail(f"{ticker}.source", "a non-empty source is required")
        for key in ("dividends", "prices"):
            if not isinstance(entry.get(key), list):
                raise _fail(f"{ticker}.{key}", "expected a list")
        splits = entry.get("splits", [])
        if not isinstance(splits, list):
            raise _fail(f"{ticker}.splits", "expected a list")

        prices = []
        for i, item in enumerate(entry["prices"]):
            where = f"{ticker}.prices[{i}]"
            if not isinstance(item, dict):
                raise _fail(where, "expected an object")
            if _parse_iso(item.get("date")) is None:
                raise _fail(f"{where}.date", "expected YYYY-MM-DD")
            close = _positive_float(item.get("close"))
            if close is None:
                raise _fail(f"{where}.close", "must be a positive finite number")
            prices.append({"date": item["date"].strip()[:10], "close": close})

        clean_splits = []
        for i, item in enumerate(splits):
            if not isinstance(item, dict) or _parse_iso(item.get("date")) is None:
                raise _fail(f"{ticker}.splits[{i}].date", "expected YYYY-MM-DD")
            clean_splits.append(dict(item))

        dividends = []
        for i, item in enumerate(entry["dividends"]):
            where = f"{ticker}.dividends[{i}]"
            if not isinstance(item, dict):
                raise _fail(where, "expected an object")
            if _parse_iso(item.get("date")) is None:
                raise _fail(f"{where}.date", "expected YYYY-MM-DD")
            if _positive_float(item.get("dividend")) is None:
                raise _fail(f"{where}.dividend", "must be a positive finite number")
            row = dict(item)
            kind = row.get("kind")
            if kind is not None or "kind_source" in row:
                if kind not in ("special", "exclude"):
                    raise _fail(f"{where}.kind", "must be 'special' or 'exclude'")
                if not _nonempty_str(row.get("kind_source")):
                    raise _fail(f"{where}.kind_source", "kind requires a non-empty kind_source")
                if kind == "exclude":
                    continue
                row["label"] = "special"
            dividends.append(row)

        result[ticker] = {
            "source": entry["source"].strip(),
            "dividends": dividends,
            "prices": prices,
            "splits": clean_splits,
        }
    return result
