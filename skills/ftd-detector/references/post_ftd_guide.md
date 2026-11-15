# Post-FTD health guide

A follow-through is a historical event, not a portfolio allocation or guaranteed bottom.
Keep these observations separate:

1. **Distribution:** a decline of at least 0.2% on volume above the previous session for the same instrument. An ETF count is not the Composite count. Early distributions weaken technical health; they do not by themselves erase the FTD event.
2. **Warning:** a close below the FTD candle's low. Report its date and reference price. The rally may still hold its own reference low.
3. **Failure:** a subsequent intraday low strictly below the explicitly recorded rally Day 1 low. Report the breached reference, session low and date. A recovered close does not undo the breach.
4. **Unavailable:** missing/non-finite/nonpositive reference or low/close evidence. Do not infer valid health or failure from a substitute closing price.

The Day 1 reference is an explicit implementation choice. IBD's general description refers to undercutting the low of the downtrend; do not conflate Day 1, the correction's intraday low, its closing low and the FTD candle low. Source: [IBD/MarketSmith Q&A](https://shop.investors.com/Images/promotional/Wizards-QA.pdf).

## Technical score and portfolio decisions

The existing 0–100 heuristic scores timing, advance, volume, dual-index confirmation and subsequent distribution. It is not calibrated to a success probability. A warning is shown as `FTD under pressure`; a rally failure has score zero and preserves the event evidence. A zero with `data_gap: true` means unavailable, not observed failure.

No universal FTD success/failure rate is asserted. Empirical rates require a specified universe, dates, event definition and outcome horizon.

`exposure_range` is always `Not assessed`. Do not map technical quality to a 25%, 75% or 100% portfolio allocation. Breadth, leadership, stock setup quality, portfolio limits and operator decisions are separate inputs. An individual stop or a custom conservative risk policy must not be relabeled as a market-wide FTD failure rule.
