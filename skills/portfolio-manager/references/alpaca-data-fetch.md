# Alpaca Data Fetch Details

Step 1 request details, moved verbatim from `SKILL.md`.

## Step 1 detail: account, positions and portfolio history requests

**1.1 Get Account Information:**
```
Preferred: use mcp__alpaca__get_account_info to fetch:
- Account equity (total portfolio value)
- Cash balance
- Buying power
- Account status

Fallback REST endpoints:
- paper: https://paper-api.alpaca.markets/v2/account
- live:  https://api.alpaca.markets/v2/account
Headers:
- APCA-API-KEY-ID=$ALPACA_API_KEY
- APCA-API-SECRET-KEY=$ALPACA_SECRET_KEY
```

**1.2 Get Current Positions:**
```
Preferred: use mcp__alpaca__get_positions to fetch all holdings:
- Symbol ticker
- Quantity held
- Average entry price (cost basis)
- Current market price
- Current market value
- Unrealized P&L ($ and %)
- Position size as % of portfolio

Fallback REST endpoints:
- paper: https://paper-api.alpaca.markets/v2/positions
- live:  https://api.alpaca.markets/v2/positions
```

**1.3 Get Portfolio History (Optional):**
```
Preferred: use mcp__alpaca__get_portfolio_history for performance analysis:
- Historical equity values
- Time-weighted return calculation
- Drawdown analysis

Fallback REST endpoint:
- /v2/account/portfolio/history
```
