# What Is Priced In — Framework for Translating Research Into Trades

The most common way that a fundamental analyst loses money is having the right
directional view and still losing money because the market already agreed with them.
Being right about the thesis is not sufficient — the question is always whether
*more* than the consensus expects will occur.

Source: Institutional commodity and equity trading practice; distilled from
approaches at major multi-manager hedge funds.

---

## The Three Translation Frameworks

### Framework 1: Score-and-Rank (Quantitative Approach)

**Used by:** Systematic funds (DE Shaw, Two Sigma, Citadel Equities)

**How it works:**
1. Build a model that outputs a signal score for each asset in a universe
2. Rank assets by score
3. Position size is proportional to rank (or a function of rank)
4. Long the top decile, short the bottom decile (or long-only the top quintile)

**Equity swing trader application:**
- Your screener outputs scores (VCP score, CANSLIM score, momentum rank)
- You are implicitly using Framework 1 when you trade the top-ranked setups
- The edge is in the *model* (which stocks score high correlates with future outperformance)
- The decision rule is mechanical: if it scores above threshold, you buy

**Weakness for discretionary traders:**
Score-based approaches do not tell you *why* the stock ranks highly or whether the
underlying driver is already priced in. A stock can rank highly because the move
already happened.

---

### Framework 2: Fair Value Gap (Expectational Approach)

**Used by:** Fundamental quants (Millennium, Point72 Equities)

**How it works:**
1. Build a model that outputs what you think the *price should be*
2. Compare your model price to the market price
3. Large positive gap (your price > market price) → go long
4. Large negative gap → go short
5. The trade thesis is that the market will converge to your model price

**Equity swing trader application:**
This is what you are doing when you use earnings estimates, DCF models, or
comparable multiples:
- "FMP data shows EPS estimates of $2.50. I think they will print $3.20. That's
  a $0.70 beat on a stock trading at 20x earnings → $14 of upside not priced in."
- "Consensus expects 15% revenue growth. My channel checks suggest 25%. Gap = 10
  points on a $50B revenue base = $5B surprise."

**Critical discipline — the "maybe I'm wrong" check:**
When your gap is unusually large (e.g., you think the stock is 30% undervalued),
you must ask: **what does the market know that my model doesn't?**
The larger the gap, the higher the probability that you are missing something
the market has already priced. Never size your conviction proportionally to the
size of the gap — size it proportionally to your *confidence in your edge over consensus*.

**Kill condition for Framework 2 trades:**
If the market moves in the direction of your thesis but your model price does
not change (i.e., the gap closed via price, not via improving fundamentals),
the trade is done. Take the gain.

---

### Framework 3: What Is Priced In (Fundamental Discretionary Approach)

**Used by:** Long-only and long-short fundamental funds (Tiger Cubs, Coatue,
Lone Pine, Druckenmiller-style)

**How it works:**
1. Build a model for a *specific measurable metric* (revenue, EPS, unit volume,
   ASP, subscriber count, same-store sales, bookings)
2. Determine what the *market is currently expecting* for that metric
3. Assess where your estimate sits relative to the market expectation
4. Size the trade based on: (your estimate − consensus estimate) × expected stock
   reaction per unit of surprise × your confidence

**This is the most nuanced framework** and the most important for pre-earnings
or pre-catalyst positioning.

---

## Applying "What Is Priced In" Step by Step

### Step 1 — Identify the swing variable

Not all metrics matter equally for a given stock at a given moment. Identify which
one number the market is most focused on:
- For a growth stock: revenue growth rate or subscriber adds
- For a commodity producer: realized price per unit (ASP)
- For a retailer: comparable store sales growth
- For an IPP/generator: capacity auction clearing price + spark spread
- For a biotech: clinical trial read-through probability

### Step 2 — Anchor to the consensus estimate

Sources for consensus:
- Analyst estimates (visible in FMP, Yahoo Finance, FINVIZ)
- Implied by the stock's current valuation multiple (reverse-engineer what growth rate
  is baked into the current P/E or EV/EBITDA)
- Options pricing (implied move at earnings = market's expectation of uncertainty)

**Implied consensus from valuation:**
If a stock trades at 30x forward earnings and the sector average is 20x, the market
is implicitly pricing in significantly higher-than-average growth. The *spread*
between the stock multiple and the sector multiple tells you what premium is priced in.

### Step 3 — Estimate your number

Derive your estimate from first principles, not from anchoring to consensus:
- Channel checks, industry data, government statistics, competitor disclosures
- Extrapolate from known data points (e.g., EIA demand data → power company volumes)
- Management commentary from prior quarter + any updated guidance

### Step 4 — Measure the gap

Gap = your estimate − consensus estimate

Express the gap in terms of stock impact:
- What is the historical stock reaction per unit of earnings surprise for this stock?
- What does a 10% revenue beat typically do to the stock on earnings day?

Example from energy sector:
> "PJM capacity auction cleared at $269/MW-day (consensus was ~$150). VST gets
> ~20,000 MW into PJM. That's $219M of incremental annual revenue vs. consensus.
> At VST's ~10x EBITDA multiple, that's ~$2.2B of incremental market cap vs.
> current ~$30B. Roughly 7% upside from this catalyst alone, before any power
> price improvement."

### Step 5 — Assess what percentage of your view is already priced in

This is the hardest step. Ask:
1. Has the stock moved significantly toward your thesis already? (i.e., is the gap
   already closed in price even though the print hasn't happened yet)
2. Are other smart investors publicly talking about this thesis? (crowded)
3. Is the options market pricing an unusually large implied move? (market knows
   something big is coming but direction is uncertain)

If the stock has already moved 20% in your direction before the catalyst, you must
decide whether there is still a gap or whether you are now buying into a fully-priced thesis.

### Step 6 — Size based on confidence, not gap size

| Confidence Level | Sizing |
|---|---|
| High (proprietary edge, data advantage) | Full position, defined risk |
| Medium (consensus-adjacent, strong setup) | Half position, add on confirmation |
| Low (thesis right but timing uncertain) | Small position or watch only |

**Never size proportionally to gap size alone.** A 50% gap with 20% confidence
is worth less than a 10% gap with 90% confidence.

---

## Common "What Is Priced In" Mistakes

**1. Anchoring to your own prior estimate**
If consensus has moved toward you since you formed the thesis, recalculate the gap.
The trade may already be over.

**2. Ignoring the reaction function**
Even if you are right about the metric, the stock may not react the way you expect.
Stocks can have "buy the rumor, sell the news" dynamics especially after large run-ups.
Verify historical earnings reaction patterns for the specific stock (use Earnings Trade
Analyzer output for this).

**3. Confusing directional accuracy with edge**
Being right 60% of the time matters less than being right by a *large* amount when
you are right and wrong by a *small* amount when you are wrong. What is priced in
analysis should help you find situations where the upside surprise can be much
larger than the downside surprise.

**4. Treating consensus as static**
Consensus moves daily. When you see analyst estimate revisions (positive or negative)
accelerating, that itself is a signal that consensus is catching up to a surprise.
You want to be positioned *before* that revision cycle completes, not after.

---

## Integration with TraderMonty Workflow

| TraderMonty Tool | Framework Connection |
|---|---|
| Earnings Trade Analyzer | Measures post-earnings drift — quantifies historical reaction function |
| PEAD Screener | Finds stocks where initial earnings gap undershot the fundamental move |
| VCP Screener / CANSLIM | Framework 1 (score/rank) applied to technical setups |
| Technical Analyst | Timing entry after you've completed the "what's priced in" assessment |
| Trader Memory Core | Records your estimate, consensus, and actual outcome for postmortem calibration |
| Signal Postmortem | Calibrates your personal reaction function over time |

**Best practice:** Before any earnings-driven position, write your estimate, the consensus
estimate, the gap, and your expected stock reaction in the Trader Memory Core thesis.
After the print, the postmortem will tell you whether your estimating process is
systematically biased high or low — that calibration is worth more than any single trade.
