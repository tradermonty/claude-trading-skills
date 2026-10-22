# NSE Intraday Analysis Rules

## Market and timeframe
- Market: NSE cash equities only.
- Analyse 5-minute candles for setups and 1-minute candles only when finer entry timing is needed.
- Use verified, timestamped market data from the configured source.
- Clearly distinguish completed candles from candles still forming.

## Analysis
- Assess market direction, opening range, VWAP, relative volume, support and resistance, and price structure.
- Identify potential breakout, pullback or rejection setups only when the available evidence supports them.
- State the entry trigger as a condition, not an unconditional market order.
- Identify invalidation, a possible stop-loss level, target zones, and risk/reward.
- Report missing inputs and conflicting indicators instead of guessing.

## Risk management
- Ask for available trading capital and maximum risk per trade if not configured.
- Calculate quantity using risk per share and the applicable lot or quantity constraints.
- Include estimated brokerage, taxes, fees, slippage and liquidity considerations where data is available.
- Reject a plan if the stop-loss, quantity or maximum risk cannot be validated.
- Never promise a win rate or guaranteed profit.

## Output
For each candidate, report:
1. Symbol and data timestamp.
2. Market context and setup.
3. Entry trigger and invalidation.
4. Stop-loss and target scenarios.
5. Quantity and estimated rupee risk.
6. Risk/reward ratio and key assumptions.
7. Reasons to skip the trade.

Do not place, modify or cancel orders. I will verify the live price and execute manually in Groww.
