# Day Trading Agent

A fully functional local day trading agent that runs against your Alpaca
paper account. Pick a risk mode, click **Start Trading**, and the agent
scans the market every 30–120 seconds, executes long and short trades,
manages stop-losses, take-profits, and even simulates margin calls.

## Features

- **3 risk modes** (LOW / MEDIUM / HIGH) with distinct position sizing,
  leverage, stop-losses, allowed strategies, and universes.
- **7 day-trading strategies** — mean reversion (RSI), momentum,
  EMA 9/20 crossover, VWAP bounce, opening-range breakout, gap-and-go,
  and short-the-rip.
- **Short selling** (disabled in LOW, 2 shorts max in MEDIUM, 3 in HIGH).
- **Margin** — up to 1.5× leverage in MEDIUM, up to **4× in HIGH**.
- **Margin call simulation** — HIGH mode will force-liquidate the worst
  position when equity/exposure drops below 25%.
- **Daily loss circuit breaker** — halts trading automatically.
- **SQLite trade history & event log** persisted across restarts.
- **Real-time dashboard** that auto-refreshes every 5 seconds.

## Risk Modes

| Mode       | Position Size | Stop | Target | Daily Loss Cap | Shorts | Leverage | Strategies |
|------------|--------------:|-----:|-------:|---------------:|--------|---------:|------------|
| **LOW**    | 2%            | 1%   | 2%     | 2%             | ❌      | 1.0×     | mean reversion only |
| **MEDIUM** | 5%            | 2%   | 4%     | 5%             | ✅ (2) | 1.5×     | mean reversion · momentum · MA cross · VWAP bounce |
| **HIGH**   | **25%**       | 5%   | 15%    | **25%**        | ✅ (3) | **4×**   | all 7 strategies — includes gap-and-go & short-the-rip |

Margin calls kick in below 30% maintenance in MEDIUM, below **25%** in HIGH.

## Prerequisites

- Python 3.9+
- Alpaca paper account ([sign up free](https://alpaca.markets/))
- `.env` file with `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` (already
  provided in this project)

## Quick Start

```bash
cd "Claude Projects/day-trader"
./run.sh
```

Then open **http://127.0.0.1:8787**.

1. Pick a risk mode (LOW / MEDIUM / HIGH).
2. Click **Start Trading**.
3. Watch positions, P&L, and events populate live.
4. Click **Stop** to pause, **Stop & Liquidate** to close everything,
   or **Liquidate All** for panic exit.

## Architecture

```
day-trader/
├── main.py              FastAPI server + static file serving
├── trader.py            Trading loop (background thread)
├── alpaca_client.py     Alpaca paper API wrapper
├── strategies.py        7 day-trading strategies
├── risk.py              Position sizing, stops, margin-call logic
├── config.py            Risk mode definitions
├── db.py                SQLite trade/event log
├── static/
│   ├── index.html       Dashboard
│   ├── style.css
│   └── app.js
├── data/
│   └── trades.db        Persistent trade & event history
├── requirements.txt
├── run.sh               One-command launcher
└── .env                 Alpaca keys (gitignored)
```

## Strategies (summary)

1. **Mean reversion** — RSI < 30: long; RSI > 70: short.
2. **Momentum** — 30-bar return > 1.5% with rising volume and above VWAP.
3. **MA crossover** — EMA(9) crosses EMA(20) up/down.
4. **VWAP bounce** — price retests VWAP during an uptrend.
5. **Gap and go** — near HOD, above VWAP, elevated volume.
6. **Short the rip** — RSI > 78 and >2 ATR above VWAP.
7. **Breakout** — break of 15-min opening range with volume.

## API endpoints

- `GET  /api/status`        — current running state, account, positions
- `GET  /api/trades`        — trade history + win/loss stats
- `GET  /api/events`        — event log
- `GET  /api/risk-modes`    — all risk mode definitions
- `POST /api/start`         — body `{"risk_mode": "low|medium|high"}`
- `POST /api/stop`          — body `{"liquidate": false}`
- `POST /api/liquidate-all` — emergency: close everything, keep running

## Safety notes

- **Paper trading only.** The client is hard-wired to `paper=True`.
- Alpaca enforces its own regulatory margin in addition to ours.
- After 3 day trades in 5 business days with <$25k equity, Alpaca will
  flag the account as a Pattern Day Trader. This is fine on paper but
  know the rule before going live.
- Strategies use 15-min-delayed free IEX data. For live markets, scan
  cadence is intentionally slow enough (30–120s) that stale quotes
  are acceptable.
