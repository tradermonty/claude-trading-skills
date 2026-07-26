---
layout: default
title: Glossary
parent: English
nav_order: 7
lang_peer: /ja/glossary/
permalink: /en/glossary/
---

# Glossary
{: .no_toc }

Plain-language definitions for trading terms used across Claude Trading Skills. These definitions explain the vocabulary; they are not trading recommendations or promises of future results.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Terms

### Average True Range (ATR)
{: #atr }

Average True Range estimates how much an instrument typically moves over a chosen number of periods, including overnight gaps. It measures movement size rather than direction and is often used to scale stops or position risk to current volatility.

**Used by:** [Position Sizer]({{ '/en/skills/position-sizer/' | relative_url }})

### Breadth
{: #breadth }

Market breadth describes how widely a market move is shared across its constituent stocks. A rising index supported by many advancing stocks is broader than the same index gain driven by only a few large companies.

**Used by:** [Market Breadth Analyzer]({{ '/en/skills/market-breadth-analyzer/' | relative_url }})

### Breakout
{: #breakout }

A breakout occurs when price moves through a previously important boundary, such as resistance or the top of a trading range. Traders usually look for confirmation from volume, market conditions, and a defined failure level because crossing the boundary alone does not guarantee follow-through.

**Used by:** [Breakout Trade Planner]({{ '/en/skills/breakout-trade-planner/' | relative_url }})

### CANSLIM
{: #canslim }

CANSLIM is a growth-investing framework covering Current quarterly earnings, Annual earnings growth, something New, Supply and demand, Leader or laggard status, Institutional sponsorship, and Market direction. It combines company fundamentals with price, volume, and market context.

**Used by:** [CANSLIM Screener]({{ '/en/skills/canslim-screener/' | relative_url }})

### Catalyst
{: #catalyst }

A catalyst is an event or new piece of information that can change expectations about an instrument, such as earnings, guidance, a product launch, regulation, or a management change. A catalyst can create movement, but it does not determine whether the market reaction will be positive or lasting.

**Used by:** [Stockbee Episodic Pivot Analyzer]({{ '/en/skills/stockbee-episodic-pivot-analyzer/' | relative_url }})

### Core + Satellite
{: #core-satellite }

Core + Satellite is a portfolio structure that separates long-horizon, diversified holdings (the Core) from a smaller allocation for more active or concentrated opportunities (the Satellite). The separation helps keep short-term trades from silently changing the risk profile of the long-term portfolio.

**Used by:** [Kanchi Dividend SOP]({{ '/en/skills/kanchi-dividend-sop/' | relative_url }})

### Correlation
{: #correlation }

Correlation summarizes how two return series have moved together, commonly on a scale from -1 to +1. It is historical, can change across regimes, and does not prove that one asset causes the other to move.

**Used by:** [Pair Trade Screener]({{ '/en/skills/pair-trade-screener/' | relative_url }})

### Commitments of Traders (COT)
{: #cot }

The Commitments of Traders report is a weekly CFTC breakdown of futures positions held by categories such as commercial hedgers and managed money. Analysts use it to study positioning and crowding, usually together with price confirmation rather than as a standalone timing signal.

**Used by:** [COT Contrarian Detector]({{ '/en/skills/cot-contrarian-detector/' | relative_url }})

### Distribution Day
{: #distribution-day }

A distribution day is commonly defined as a meaningful decline in a major index on higher volume than the prior session. A cluster of recent distribution days can suggest institutional selling pressure, but one day by itself is not a complete market signal.

**Used by:** [IBD Distribution Day Monitor]({{ '/en/skills/ibd-distribution-day-monitor/' | relative_url }})

### Drawdown
{: #drawdown }

Drawdown is the decline from a portfolio or strategy's previous peak to a later low, usually expressed as a percentage. It describes the depth of a loss period and should be considered together with its duration and the recovery required to regain the peak.

**Used by:** [Drawdown Circuit Breaker]({{ '/en/skills/drawdown-circuit-breaker/' | relative_url }})

### Edge
{: #edge }

An edge is a repeatable informational, behavioral, analytical, or execution advantage that is expected to produce favorable results over many comparable decisions. It is a testable hypothesis, not certainty on any individual trade, and can weaken as market conditions change.

**Used by:** [Edge Concept Synthesizer]({{ '/en/skills/edge-concept-synthesizer/' | relative_url }})

### Entry
{: #entry }

An entry is the predefined condition or price area at which a trade may be opened. A useful entry rule also states what evidence must be present, how much can be risked, and what condition would make the setup invalid.

**Used by:** [Breakout Trade Planner]({{ '/en/skills/breakout-trade-planner/' | relative_url }})

### Episodic Pivot
{: #episodic-pivot }

An episodic pivot is a sharp price and volume change associated with a significant company-specific event, often a large earnings or guidance surprise. The event can reset expectations and start a new trend, but liquidity, follow-through, and risk limits still need separate evaluation.

**Used by:** [Stockbee Episodic Pivot Analyzer]({{ '/en/skills/stockbee-episodic-pivot-analyzer/' | relative_url }})

### Expectancy
{: #expectancy }

Expectancy is the average amount a process is expected to win or lose per trade over a sufficiently large sample. A common form combines win rate and average win, then subtracts loss rate multiplied by average loss; it does not predict the next result.

**Used by:** [Weekly Performance Digest]({{ '/en/skills/weekly-performance-digest/' | relative_url }})

### Exposure
{: #exposure }

Exposure is the amount of portfolio capital affected by market movement, often expressed as a percentage of equity and separated into long, short, gross, or net exposure. Position values alone can hide leverage, so the denominator and sign convention matter.

**Used by:** [Exposure Coach]({{ '/en/skills/exposure-coach/' | relative_url }})

### Follow-Through Day (FTD)
{: #ftd }

A follow-through day is a strong gain in a major index on higher volume after a possible market low, used in some growth-investing methods as evidence that a rally may be gaining institutional support. It is a confirmation condition, not a guarantee that the rally will continue.

**Used by:** [FTD Detector]({{ '/en/skills/ftd-detector/' | relative_url }})

### Gap
{: #gap }

A gap is a price interval between one session's trading range and the next session's opening activity where little or no trading occurred. Gaps often reflect new information, but their size, volume, location, and subsequent price response determine their practical meaning.

**Used by:** [Earnings Trade Analyzer]({{ '/en/skills/earnings-trade-analyzer/' | relative_url }})

### Hedge Ratio
{: #hedge-ratio }

A hedge ratio specifies how much of one instrument is paired against another to reduce a chosen risk, such as market or spread exposure. In a pair trade it is commonly estimated from historical prices, but estimation error and changing relationships can leave residual risk.

**Used by:** [Pair Trade Screener]({{ '/en/skills/pair-trade-screener/' | relative_url }})

### Liquidity
{: #liquidity }

Liquidity describes how easily an instrument can be bought or sold in the desired size without materially moving its price. Volume, bid-ask spread, and market depth are useful clues, and liquidity can deteriorate during volatile or off-hours trading.

**Used by:** [Pair Trade Screener]({{ '/en/skills/pair-trade-screener/' | relative_url }})

### Maximum Adverse Excursion (MAE)
{: #mae }

Maximum Adverse Excursion is the largest unrealized move against a position while it was open, measured from the entry. Reviewing MAE across comparable trades can show whether stops are too tight or losses are being allowed to grow, but it should not be optimized from a tiny sample.

**Used by:** [Trader Memory Core]({{ '/en/skills/trader-memory-core/' | relative_url }})

### Maximum Favorable Excursion (MFE)
{: #mfe }

Maximum Favorable Excursion is the largest unrealized move in a position's favor while it was open, measured from the entry. Comparing MFE with the realized result can help review exit execution without assuming that the best intratrade price was actually achievable.

**Used by:** [Trader Memory Core]({{ '/en/skills/trader-memory-core/' | relative_url }})

### Market Regime
{: #market-regime }

A market regime is a broad environment characterized by features such as trend, volatility, breadth, liquidity, and macro conditions. A process may use different exposure or setup rules in a stable uptrend than in a high-volatility decline.

**Used by:** [Macro Regime Detector]({{ '/en/skills/macro-regime-detector/' | relative_url }})

### Momentum
{: #momentum }

Momentum is the tendency for relatively strong or weak price movement to persist for some period. It can be measured over different horizons, so a stock may have strong short-term momentum while remaining weak on a longer-term basis.

**Used by:** [Stockbee Momentum Burst Screener]({{ '/en/skills/stockbee-momentum-burst-screener/' | relative_url }})

### Post-Earnings Announcement Drift (PEAD)
{: #pead }

Post-Earnings Announcement Drift is the documented tendency for prices to continue moving in the direction of an earnings surprise after the initial announcement. A PEAD setup still needs defined eligibility, entry, liquidity, and invalidation rules because not every earnings move persists.

**Used by:** [PEAD Screener]({{ '/en/skills/pead-screener/' | relative_url }})

### Position Sizing
{: #position-sizing }

Position sizing determines how many shares, contracts, or dollars to allocate to a trade. Risk-based sizing starts with the amount the portfolio can lose and the distance to the invalidation or stop level, rather than choosing size from conviction alone.

**Used by:** [Position Sizer]({{ '/en/skills/position-sizer/' | relative_url }})

### Pullback
{: #pullback }

A pullback is a temporary move against the direction of a prevailing trend, such as a decline within an uptrend. It may offer a planned entry area, but it can also be the start of a reversal, so trend quality and invalidation levels remain important.

**Used by:** [Dividend Growth Pullback Screener]({{ '/en/skills/dividend-growth-pullback-screener/' | relative_url }})

### R-Multiple
{: #r-multiple }

An R-multiple expresses a trade result relative to its initial planned risk, where +2R means a gain twice the initial risk and -1R means the planned risk was lost. It makes results more comparable across trades of different sizes, provided the initial risk was recorded consistently.

**Used by:** [Weekly Performance Digest]({{ '/en/skills/weekly-performance-digest/' | relative_url }})

### Relative Strength
{: #relative-strength }

Relative strength compares an instrument's performance with a benchmark or peer group over a chosen period. It is different from the Relative Strength Index (RSI): relative strength is a comparison, while RSI is a bounded momentum oscillator.

**Used by:** [CANSLIM Screener]({{ '/en/skills/canslim-screener/' | relative_url }})

### Risk-On / Risk-Off
{: #risk-on-risk-off }

Risk-on describes conditions in which investors broadly favor assets perceived as more sensitive to growth or market risk, while risk-off describes a shift toward capital preservation and defensive assets. These labels summarize cross-market behavior and are not binary forecasts.

**Used by:** [Market Environment Analysis]({{ '/en/skills/market-environment-analysis/' | relative_url }})

### Relative Strength Index (RSI)
{: #rsi }

The Relative Strength Index is a momentum oscillator typically scaled from 0 to 100 using the balance of recent gains and losses. Thresholds such as 70 or 30 describe the calculation's recent extreme, not an automatic instruction to sell or buy.

**Used by:** [Dividend Growth Pullback Screener]({{ '/en/skills/dividend-growth-pullback-screener/' | relative_url }})

### Stop-Loss
{: #stop-loss }

A stop-loss is a predefined price or condition for exiting when a trade no longer fits its plan. It limits intended risk but cannot guarantee the exact exit price during gaps, fast markets, or insufficient liquidity.

**Used by:** [Breakout Trade Planner]({{ '/en/skills/breakout-trade-planner/' | relative_url }})

### Support and Resistance
{: #support-resistance }

Support is an area where buying has previously absorbed selling, while resistance is an area where selling has previously absorbed buying. They are zones inferred from market behavior rather than permanent price barriers.

**Used by:** [Technical Analyst]({{ '/en/skills/technical-analyst/' | relative_url }})

### Thesis and Invalidation
{: #thesis-invalidation }

A trade thesis states why an opportunity should work and which observable evidence supports it; invalidation states what evidence would show that the reasoning is no longer acceptable. Writing both before entry makes later review less vulnerable to hindsight and shifting explanations.

**Used by:** [Trader Memory Core]({{ '/en/skills/trader-memory-core/' | relative_url }})

### Volatility
{: #volatility }

Volatility describes the magnitude and variability of price changes, not their direction. Higher volatility usually means a wider range of possible outcomes and may require smaller positions or wider risk limits to keep portfolio risk comparable.

**Used by:** [Position Sizer]({{ '/en/skills/position-sizer/' | relative_url }})

### Volatility Contraction Pattern (VCP)
{: #vcp }

A Volatility Contraction Pattern is a price structure in which successive pullbacks become smaller while supply appears to diminish near a potential pivot. It is a setup framework associated with Mark Minervini, not proof that a breakout will succeed.

**Used by:** [VCP Screener]({{ '/en/skills/vcp-screener/' | relative_url }})

### Z-Score
{: #z-score }

A z-score expresses how far a current value is from a historical mean in units of standard deviation. In spread analysis it helps describe unusual divergence, but its interpretation depends on a sufficiently stable distribution and lookback period.

**Used by:** [Pair Trade Screener]({{ '/en/skills/pair-trade-screener/' | relative_url }})
