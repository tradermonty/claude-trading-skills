# FTD lifecycle and instrument identity (#765)

## Contract

The implementation explicitly uses the rally Day 1 intraday low as its failure
reference. IBD's generic downtrend-low description, a selected closing swing
low, and the FTD candle low must not be treated as interchangeable. An FTD-low
close breach warns; a later intraday Day 1 breach fails. Equality holds. Missing
low evidence is unavailable. Historical event evidence is retained after a real
failure, and a warning alone does not zero the technical quality score.

The Day 4–10 window and score weights remain bounded model choices, not universal
IBD definitions. This change does not calibrate signal probabilities or the
separate DD/TQQQ risk policy tracked in #676.

## JSON migration

FTD metadata schema version is now 2. The default Nasdaq instrument is ^IXIC;
QQQ requires explicit --nasdaq-symbol QQQ. index_prices.nasdaq replaces the
ambiguous index_prices.qqq key. metadata.instruments gives symbol, label and
index/ETF-proxy kind. Source price and volume always use the same symbol; no
silent fallback was added.

quality_score.exposure_range is always "Not assessed". A numerical technical
quality score is not a position-sizing recommendation. Structured position_sizing
lists the unassessed breadth, leadership and portfolio risk context. A valid
FTD under pressure is distinguished by signal and lifecycle warning, while its
market state remains FTD_CONFIRMED. Failure uses FTD_INVALIDATED and retains the
FTD date. Missing lifecycle evidence yields unavailable quality and NO_SIGNAL.

DD keeps its explicit QQQ/SPY strategy defaults. Known instrument labels now
identify the ETFs, and audit metadata/report text make the evidence basis
explicit even if a configuration supplies an ambiguous custom benchmark name.
The mechanical DD counters and TQQQ policy thresholds are unchanged.

## Regression evidence

Tests use fictional bars and fixed offline report fixtures, not the supplied
November market prices. They cover warning without failure, exact equality,
intraday failure despite a recovered close, missing low/anchor evidence, full
state-machine event retention, no automatic allocation at score boundaries and
selected-symbol identity across both data requests and rendered reports.

Old fixtures intended to model true failure now breach the rally reference,
rather than merely the FTD candle low. Missing-low tests no longer bless a
closing-price substitution. Golden artifacts were updated for the explicit QQQ
proxy fixture and reviewed for reference/identity fields and removal of sizing
and unsupported success-rate claims.

The supplied local November 14 report is not modified or revalidated against
fresh provider data by this implementation. No provider/broker live action was
used to establish these regression results.
