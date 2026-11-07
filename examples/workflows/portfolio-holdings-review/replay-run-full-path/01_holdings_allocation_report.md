# Offline CSV holdings review

Source: local_csv; as-of: 2026-10-20T12:00:00+00:00 (operator asserted)

Gross holdings value (USD): 80
Signed net holdings value (USD): 20

| Symbol | Direction | Quantity | Gross value USD | Gross weight % | Unrealized P&L USD |
|---|---|---|---|---|---|
| FICTA | LONG | 2.5 | 50 | 62.5 | 12.5 |
| FICTB | SHORT | 1 | 30 | 37.5 | 10 |

## Limitations

- Local snapshot assertions only; identity, completeness and price freshness are unverified.
- USD equities only. Weights use gross holdings value, not account equity.
- Cash, leverage, sector/beta, historical returns and trading recommendations are unavailable.
- P&L is per position only; missing per-share cost basis means unavailable, not zero.
- No broker access, order execution, or trader-memory changes. Not a reconciliation gate.
- Limited portfolio-holdings-review path only; full brokerage review requires reconciliation.
