# FTD technical model and limitations

An O'Neil-style follow-through is a substantial up session on greater volume than the previous session, from rally Day 4 onward. It is evidence of renewed demand, not a guaranteed market bottom. See [IBD/MarketSmith Q&A](https://shop.investors.com/Images/promotional/Wizards-QA.pdf).

## This implementation

- Search a 60-session window for a correction and rally attempt. Day 1 is the first up close or upper-half-range close after the selected swing low.
- Explicitly record Day 1's intraday low. Subsequent intraday lows must not strictly undercut it. Missing low evidence is unavailable, not a closing-price substitute.
- Qualify an FTD on Day 4–10 with gain at least 1.25% and volume greater than the previous session. The 1.5%/2.0% tiers and bounded upper day limit are model choices, not universal IBD rules. Above-average volume is a point-in-time bonus, not mandatory.
- Preserve the FTD event through later health changes. Close below the FTD-day low is a warning; breach of the Day 1 low is failure. The report exposes the reference rather than treating distinct lows as interchangeable.
- Analyze S&P 500 `^GSPC` and Nasdaq Composite `^IXIC` by default. An explicit `--nasdaq-symbol QQQ` analyzes a Nasdaq-100 ETF proxy. Both price and volume must belong to the named instrument; no silent fallback or Composite-volume/ETF-price splice.

## Heuristic quality

The retained score gives 60 base points for Day 4–7 or 50 for Day 8–10, 5/10/15 for 1.25%/1.5%/2.0% gains, 10 for above-average volume and 15 for dual confirmation. Subsequent distribution can increase caution. A rally failure overrides quality to zero; missing required data yields an unavailable zero. FTD-low warning is reported separately as `FTD under pressure`.

These weights are not an empirically calibrated success probability. There is no asserted universal 25% success rate. Portfolio exposure is `Not assessed`; breadth, leadership and portfolio context must be evaluated separately. The separate DD policy and its calibration work (#676) are not validated by an FTD score.
