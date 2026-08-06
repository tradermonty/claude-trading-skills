#!/usr/bin/env python3
"""Parse a MetaTrader 5 single-backtest HTML report (EN or ES).

Extracts the summary metrics and, crucially, reconstructs the **balance time
series from the deals table** so we can compute what the summary omits:

  * % of positive calendar months
  * whether every calendar year is positive
  * the longest gap, in months, before the balance makes a new high
    (months to a new high)

Plus summary fields: net profit, initial deposit, the worst drawdown % (the
larger of balance/equity, maximal or relative), LR Correlation, profit factor,
Sharpe, trades.

CLI:
    python3 parse_mt5_report.py report.htm --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

try:
    from mt5_common import html_table_rows, read_text, to_float
except ImportError:  # pragma: no cover - import shim
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mt5_common import html_table_rows, read_text, to_float

# A number possibly using a space thousands separator: "8 869.51", "-12 310.55".
_NUM = r"([-+]?\d{1,3}(?:[  ]\d{3})*(?:[.,]\d+)?|[-+]?\d+(?:[.,]\d+)?)"


def _flat(rows: list[list[str]]) -> str:
    return "  ".join(" ".join(r) for r in rows)


def _search_num(flat: str, labels: list[str], want_pct: bool = False) -> float | None:
    """Find the first number (or percentage) following any of ``labels``."""
    for label in labels:
        pat = re.escape(label) + r"[:\s]*"
        if want_pct:
            # First number that is immediately followed by % near the label.
            m = re.search(pat + r"[^%]{0,40}?" + _NUM + r"\s*%", flat, flags=re.I)
        else:
            m = re.search(pat + _NUM, flat, flags=re.I)
        if m:
            return to_float(m.group(1))
    return None


def parse_summary(rows: list[list[str]]) -> dict:
    flat = _flat(rows)
    net_profit = _search_num(flat, ["Total Net Profit", "Beneficio Neto", "Beneficio neto"])
    deposit = _search_num(flat, ["Initial Deposit", "Depósito inicial", "Deposito inicial"])
    lr = _search_num(flat, ["LR Correlation"])
    profit_factor = _search_num(
        flat, ["Profit Factor", "Factor de beneficio", "Factor de rentabilidad"]
    )
    sharpe = _search_num(flat, ["Sharpe Ratio", "Ratio de Sharpe"])
    trades = _search_num(
        flat, ["Total Trades", "Total de operaciones ejecutadas", "Total de operaciones"]
    )

    # Drawdown %: capture every variant and keep the worst (largest).
    dd_labels = [
        "Balance Drawdown Maximal",
        "Reducción máxima del balance",
        "Reduccion maxima del balance",
        "Balance Drawdown Relative",
        "Reducción relativa del balance",
        "Reduccion relativa del balance",
        "Equity Drawdown Maximal",
        "Reducción máxima de la equity",
        "Reducción máxima del capital",
        "Equity Drawdown Relative",
        "Reducción relativa de la equity",
        "Reducción relativa del capital",
    ]
    dd_values = [
        v for v in (_search_num(flat, [lbl], want_pct=True) for lbl in dd_labels) if v is not None
    ]
    dd_max_pct = max(dd_values) if dd_values else None

    return {
        "net_profit": net_profit,
        "deposit": deposit,
        "lr_correlation": lr,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "total_trades": int(trades) if trades is not None else None,
        "drawdown_max_pct": dd_max_pct,
        "drawdown_pcts": dd_values,
    }


_DATE_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")


def _parse_dt(cell: str) -> dt.date | None:
    m = _DATE_RE.search(cell)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_deals(rows: list[list[str]]) -> list[tuple[dt.date, float]]:
    """Reconstruct (date, running_balance) points from the deals table.

    Locates the deals header (a row containing a Balance column and a time
    column) and reads following rows whose time cell holds a date and whose
    balance cell is numeric.
    """
    time_tokens = ("hora", "fecha", "time", "tiempo")
    for i, cells in enumerate(rows):
        lower = [c.strip().lower() for c in cells]
        if "balance" not in lower:  # the deals table has an exact "Balance" column
            continue
        # Time column header varies by build/language: "Hora", "Fecha/Hora", "Time"...
        time_col = next(
            (j for j, c in enumerate(lower) if any(tok in c for tok in time_tokens)), None
        )
        bal_col = lower.index("balance")
        if time_col is None:
            continue
        points: list[tuple[dt.date, float]] = []
        for row in rows[i + 1 :]:
            if bal_col >= len(row) or time_col >= len(row):
                continue
            date = _parse_dt(row[time_col])
            balance = to_float(row[bal_col])
            if date is not None and balance is not None:
                points.append((date, balance))
        if points:
            return points
    return []


def _month_key(d: dt.date) -> tuple[int, int]:
    return (d.year, d.month)


def _iter_months(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) <= end:
        yield (y, m)
        m += 1
        if m > 12:
            y, m = y + 1, 1


def timeseries_metrics(
    points: list[tuple[dt.date, float]],
    deposit: float | None,
    period_start: dt.date | None = None,
    period_end: dt.date | None = None,
) -> dict:
    """Compute monthly/yearly/underwater metrics from the balance series."""
    if not points and (period_start is None or period_end is None):
        return {
            "pct_positive_months": None,
            "all_years_positive": None,
            "max_months_to_new_high": None,
            "months_analyzed": 0,
        }

    points = sorted(points, key=lambda p: p[0])
    if deposit is None and not points:
        return {
            "pct_positive_months": None,
            "all_years_positive": None,
            "max_months_to_new_high": None,
            "months_analyzed": 0,
        }
    start_balance = deposit if deposit is not None else points[0][1]

    # Month-end balance across every calendar month in range (carry forward).
    last_bal_in_month: dict[tuple[int, int], float] = {}
    for d, bal in points:
        last_bal_in_month[_month_key(d)] = bal

    first_m = _month_key(period_start or points[0][0])
    last_m = _month_key(period_end or points[-1][0])
    if first_m > last_m:
        raise ValueError("period_start must not be after period_end")
    month_end: list[tuple[tuple[int, int], float]] = []
    running = start_balance
    for ym in _iter_months(first_m, last_m):
        if ym in last_bal_in_month:
            running = last_bal_in_month[ym]
        month_end.append((ym, running))

    # Monthly P&L (vs previous month-end, seeded with the initial deposit).
    prev = start_balance
    positive_months = 0
    for _, bal in month_end:
        if bal - prev > 0:
            positive_months += 1
        prev = bal
    months_analyzed = len(month_end)
    pct_positive_months = 100.0 * positive_months / months_analyzed if months_analyzed else None

    # Yearly P&L.
    year_end: dict[int, float] = {}
    for (y, _m), bal in month_end:
        year_end[y] = bal
    prev = start_balance
    all_years_positive = True
    yearly = {}
    for y in sorted(year_end):
        pnl = year_end[y] - prev
        yearly[y] = pnl
        if pnl <= 0:
            all_years_positive = False
        prev = year_end[y]

    # Longest run of months without a new balance high.
    peak = start_balance
    gap = 0
    max_gap = 0
    for _, bal in month_end:
        if bal > peak:
            peak = bal
            gap = 0
        else:
            gap += 1
            max_gap = max(max_gap, gap)

    return {
        "pct_positive_months": pct_positive_months,
        "positive_months": positive_months,
        "months_analyzed": months_analyzed,
        "all_years_positive": all_years_positive,
        "yearly_pnl": {str(y): round(v, 2) for y, v in yearly.items()},
        "max_months_to_new_high": max_gap,
    }


def _coerce_date(value: str | dt.date | None) -> dt.date | None:
    if value is None or isinstance(value, dt.date):
        return value
    normalized = str(value).strip().replace("-", ".").replace("/", ".")
    return _parse_dt(normalized)


def parse_report_file(
    path: str | Path,
    period_start: str | dt.date | None = None,
    period_end: str | dt.date | None = None,
) -> dict:
    """Parse a backtest report: summary + reconstructed time-series metrics."""
    rows = html_table_rows(read_text(path))
    summary = parse_summary(rows)
    deals = parse_deals(rows)
    ts = timeseries_metrics(
        deals,
        summary.get("deposit"),
        _coerce_date(period_start),
        _coerce_date(period_end),
    )
    result = {**summary, **ts, "deals_count": len(deals), "report_file": str(path)}
    if summary.get("net_profit") is not None and summary.get("deposit"):
        result["profit_pct"] = 100.0 * summary["net_profit"] / summary["deposit"]
    else:
        result["profit_pct"] = None
    return result


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse an MT5 backtest report.")
    parser.add_argument("report")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.report)
    if not path.exists():
        print(f"error: report not found: {path}", file=sys.stderr)
        return 1

    metrics = parse_report_file(path)
    if args.json:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
    else:
        for key, value in metrics.items():
            print(f"{key:>24}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
