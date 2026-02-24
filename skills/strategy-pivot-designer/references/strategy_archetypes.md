# Strategy Archetypes Catalog

Eight canonical strategy archetypes cover the primary systematic trading approaches. Each archetype defines default modules, typical failure modes, and compatible pivot targets.

---

## 1. Trend Following Breakout (`trend_following_breakout`)

**Description**: Buy when price breaks above a consolidation range with volume confirmation. Ride the trend with trailing stops.

**Default Modules**:
- hypothesis_type: breakout
- mechanism_tag: behavior
- entry_family: pivot_breakout
- horizon: medium (10-60 days)
- risk_style: wide (trailing stop 8-12%)

**Typical Failure Modes**:
- Whipsaws in range-bound markets
- Late entries after extended moves
- Gap-downs through stop levels

**Compatible Pivots From**: mean_reversion_pullback, volatility_contraction, sector_rotation_momentum

---

## 2. Mean Reversion Pullback (`mean_reversion_pullback`)

**Description**: Buy oversold pullbacks within an established uptrend. Profit from reversion to mean.

**Default Modules**:
- hypothesis_type: mean_reversion
- mechanism_tag: statistical
- entry_family: research_only
- horizon: short (3-14 days)
- risk_style: tight (stop 3-5%)

**Typical Failure Modes**:
- Catching falling knives in trend changes
- Insufficient recovery within time stop
- Sector-wide selloffs overwhelming individual stock mean reversion

**Compatible Pivots From**: trend_following_breakout, volatility_contraction, earnings_drift_pead

---

## 3. Earnings Drift PEAD (`earnings_drift_pead`)

**Description**: Exploit post-earnings announcement drift by entering after significant earnings surprises.

**Default Modules**:
- hypothesis_type: earnings_drift
- mechanism_tag: information
- entry_family: gap_up_continuation
- horizon: medium (5-30 days)
- risk_style: normal (stop 5-8%)

**Typical Failure Modes**:
- One-day gap fills that reverse the drift
- Market-wide selloffs overwhelming individual stock drift
- Late entry after drift has already occurred

**Compatible Pivots From**: event_driven_fade, trend_following_breakout, mean_reversion_pullback

---

## 4. Volatility Contraction (`volatility_contraction`)

**Description**: Enter when volatility contracts to historical lows (VCP pattern), anticipating expansion in the trend direction.

**Default Modules**:
- hypothesis_type: breakout
- mechanism_tag: structural
- entry_family: pivot_breakout
- horizon: medium (10-40 days)
- risk_style: tight (stop 3-6%)

**Typical Failure Modes**:
- False breakouts from contraction zones
- Extended contraction periods draining capital via time stops
- Volatility expanding in the wrong direction

**Compatible Pivots From**: trend_following_breakout, mean_reversion_pullback, statistical_pairs

---

## 5. Regime Conditional Carry (`regime_conditional_carry`)

**Description**: Hold positions only during favorable macro regimes, using regime detection to filter entries.

**Default Modules**:
- hypothesis_type: regime
- mechanism_tag: macro
- entry_family: research_only
- horizon: long (30-120 days)
- risk_style: normal (stop 5-8%)

**Typical Failure Modes**:
- Regime detection lag causing late entries/exits
- Whipsaws during regime transitions
- Underperformance during trending markets due to conservative entry timing

**Compatible Pivots From**: sector_rotation_momentum, event_driven_fade, statistical_pairs

---

## 6. Sector Rotation Momentum (`sector_rotation_momentum`)

**Description**: Rotate into sectors showing relative strength momentum, exit when momentum fades.

**Default Modules**:
- hypothesis_type: momentum
- mechanism_tag: behavior
- entry_family: research_only
- horizon: medium (20-60 days)
- risk_style: normal (stop 5-8%)

**Typical Failure Modes**:
- Momentum reversals during sector rotation shifts
- Crowded trades in popular sectors
- Correlation spikes during market stress nullifying diversification

**Compatible Pivots From**: trend_following_breakout, regime_conditional_carry, earnings_drift_pead

---

## 7. Event Driven Fade (`event_driven_fade`)

**Description**: Fade overreactions to scheduled or unscheduled events, betting on mean reversion after the initial move.

**Default Modules**:
- hypothesis_type: mean_reversion
- mechanism_tag: information
- entry_family: research_only
- horizon: short (1-10 days)
- risk_style: tight (stop 2-5%)

**Typical Failure Modes**:
- Events that represent genuine regime changes (not overreactions)
- Cascading events that compound the initial move
- Liquidity gaps during extreme events

**Compatible Pivots From**: earnings_drift_pead, mean_reversion_pullback, volatility_contraction

---

## 8. Statistical Pairs (`statistical_pairs`)

**Description**: Trade cointegrated pairs, going long the undervalued and short the overvalued member when spread deviates from equilibrium.

**Default Modules**:
- hypothesis_type: mean_reversion
- mechanism_tag: statistical
- entry_family: research_only
- horizon: medium (10-30 days)
- risk_style: normal (stop via z-score threshold)

**Typical Failure Modes**:
- Cointegration breakdown due to fundamental changes
- Extended spread divergence exceeding risk limits
- Execution risk on short leg (borrow costs, locate difficulty)

**Compatible Pivots From**: mean_reversion_pullback, volatility_contraction, regime_conditional_carry

---

## Archetype Compatibility Matrix

| Source Archetype | Compatible Pivot Targets |
|---|---|
| trend_following_breakout | mean_reversion_pullback, volatility_contraction, sector_rotation_momentum |
| mean_reversion_pullback | trend_following_breakout, volatility_contraction, earnings_drift_pead |
| earnings_drift_pead | event_driven_fade, trend_following_breakout, mean_reversion_pullback |
| volatility_contraction | trend_following_breakout, mean_reversion_pullback, statistical_pairs |
| regime_conditional_carry | sector_rotation_momentum, event_driven_fade, statistical_pairs |
| sector_rotation_momentum | trend_following_breakout, regime_conditional_carry, earnings_drift_pead |
| event_driven_fade | earnings_drift_pead, mean_reversion_pullback, volatility_contraction |
| statistical_pairs | mean_reversion_pullback, volatility_contraction, regime_conditional_carry |
