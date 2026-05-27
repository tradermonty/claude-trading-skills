# Data Gap Protocol

**Version:** 1.0
**Status:** Canonical — all production skills must follow this protocol.
**Companion code:** `schemas/data_gap.py`

---

## Why This Protocol Exists

A decision-support tool that silently replaces missing data with neutral assumptions is
*more dangerous* than one that refuses to run. TraderMonty skills must make data gaps
explicit, not hide them.

If data is unavailable, the skill must:
1. Record a `DataGap` entry in the output artifact.
2. State the severity.
3. State which decision is affected.
4. State whether the workflow can continue.
5. **Never replace missing data with a neutral-default assumption without documenting it.**

---

## Severity Levels

| Level | Meaning | Example |
|---|---|---|
| `CRITICAL` | Skill cannot produce any meaningful output. Must abort or return minimal artifact with gap only. | API key missing entirely; required CSV not reachable |
| `HIGH` | Output is produced but a key signal is missing or unreliable. Must be flagged prominently; downstream workflows must gate on it. | API returns empty for the primary ticker; image not provided to an image-required skill |
| `MEDIUM` | Output is produced but confidence is reduced. User should verify before acting. | API returned partial results; CSV is 6 days stale; backtest sample under minimum |
| `LOW` | Output is produced; gap is informational. User may act but should note the gap. | Optional upstream skill output not provided; minor data staleness |

---

## Ten Required Scenarios

Every skill MUST document how it handles each applicable scenario in its SKILL.md under a
`## Data Gap Behavior` section.

### Scenario 1 — API Key Missing

- **Severity:** `CRITICAL`
- **Affected decision:** All decisions that depend on the API
- **Remediation:** Set `FMP_API_KEY` / `ALPACA_API_KEY` environment variable and retry
- **Can continue:** `false` — exit with error code 1 and a clear message
- **Implementation:** Check key before making any API call; do not proceed if absent

```python
if not api_key:
    emit_data_gap(severity="CRITICAL", description="FMP_API_KEY not set", ...)
    sys.exit(1)
```

### Scenario 2 — API Returns Empty

- **Severity:** `HIGH`
- **Affected decision:** The specific component that relies on this API call
- **Remediation:** Check API tier limits; verify ticker/symbol is valid; retry during market hours
- **Can continue:** `false` for primary signals; `true` for optional components with gap recorded
- **Implementation:** If primary endpoint returns empty list or null, emit `DataGap` and
  either abort or reduce confidence — do not substitute a "neutral" default value

```python
if not data:
    emit_data_gap(severity="HIGH", description=f"API returned empty for {symbol}", ...)
    return None  # not 0, not neutral
```

### Scenario 3 — Data Too Stale

- **Severity:** `MEDIUM` if within 2× expected cadence; `HIGH` if beyond
- **Affected decision:** Time-sensitive signals (breadth, uptrend, top risk)
- **Remediation:** Re-run the data fetch; check upstream data source availability
- **Can continue:** `true` with staleness flag; expose `data_age_days` in output
- **Thresholds by cadence:**

| Skill cadence | MEDIUM threshold | HIGH threshold |
|---|---|---|
| daily | >3 days | >7 days |
| weekly | >10 days | >21 days |
| research | >30 days | >90 days |

### Scenario 4 — Chart/Image Missing (Image-required skills)

- **Severity:** `CRITICAL` for image-only analysis; `HIGH` for hybrid CSV+image
- **Affected decision:** All chart-based assessments
- **Remediation:** Provide a screenshot of the relevant chart
- **Can continue:** `false` for image-only; `true` with CSV-only mode if available
- **Note:** `breadth-chart-analyst` and `sector-analyst` support CSV-only mode

### Scenario 5 — CSV Missing (CSV-based skills)

- **Severity:** `CRITICAL`
- **Affected decision:** All scoring components that depend on the CSV
- **Remediation:** Check internet connectivity to GitHub Pages; verify URL
- **Can continue:** `false`
- **Affected skills:** `market-breadth-analyzer`, `uptrend-analyzer`, `sector-analyst`

### Scenario 6 — Sample Size Too Small (Backtest/Research)

- **Severity:** `HIGH` if below minimum; `MEDIUM` if between minimum and recommended
- **Affected decision:** Strategy validity conclusions; out-of-sample requirements
- **Remediation:** Extend backtest period; widen universe; reduce parameter specificity
- **Thresholds:**
  - Below 30 trades → `HIGH` — results not statistically meaningful
  - 30–99 trades → `MEDIUM` — results are suggestive only
  - 100+ trades → no gap (recommended minimum met)
- **Can continue:** `true` but must flag in `BacktestReport.overfitting_warnings`

### Scenario 7 — Market Regime Unclear

- **Severity:** `MEDIUM`
- **Affected decision:** `ExposureDecision` ceiling and recommendation
- **Remediation:** Wait for clearer signal; default to conservative (lower) exposure ceiling
- **Can continue:** `true` with `confidence = "LOW"` and conservative defaults
- **Implementation:** If signals conflict (breadth bullish, top-risk bearish),
  set `confidence = "LOW"`, default `recommendation = "REDUCE_ONLY"`, document in `rationale`

### Scenario 8 — Conflicting Signals

- **Severity:** `MEDIUM`
- **Affected decision:** Depends on which signals conflict
- **Remediation:** Document the conflict in `assumptions`; apply conservative resolution
- **Can continue:** `true` with explicit conflict noted
- **Rule:** When primary signals conflict, always resolve conservatively:
  - For exposure: take the lower ceiling
  - For trade plans: require chart_review_status = PASS before acting
  - For backtest conclusions: flag as `false_discovery_risk = "HIGH"`

### Scenario 9 — Liquidity Too Low

- **Severity:** `HIGH` for trade plans
- **Affected decision:** Position sizing; trade feasibility
- **Remediation:** Filter out illiquid candidates; do not generate trade plans for them
- **Thresholds:**
  - Average daily volume < 500,000 shares → `HIGH` — candidate not tradeable at normal size
  - Average daily volume < 100,000 shares → `CRITICAL` — do not generate a trade plan
- **Can continue:** `false` for trade plans; `true` for research/watchlist use

### Scenario 10 — Risk Budget Unavailable

- **Severity:** `HIGH`
- **Affected decision:** Position sizing; portfolio heat calculation
- **Remediation:** Provide account size and current portfolio heat to position-sizer
- **Can continue:** `false` for `PositionSizingPlan`; `true` for watchlist screening
- **Implementation:** `position-sizer` must require `--account-size` before emitting a
  `PositionSizingPlan`; if missing, emit gap and return sizing without dollar amounts

---

## Implementation Guide

### In Python scripts

Import and use the helper from `schemas/data_gap.py`:

```python
from schemas.data_gap import emit_gap, DataGapCollector

collector = DataGapCollector(skill_id="vcp-screener")

# Record a gap
collector.add(
    severity="HIGH",
    description="FMP API returned empty for SPY historical data",
    affected_decision="Trend template validation for all candidates",
    remediation="Check FMP_API_KEY and daily call limit",
    can_continue=False,
    source="fmp_api",
)

# Include gaps in output artifact
output = {
    "schema_version": "1.0",
    "skill_id": "vcp-screener",
    ...
    "data_gaps": collector.to_list(),
}
```

### In SKILL.md

Add a `## Data Gap Behavior` section:

```markdown
## Data Gap Behavior

| Scenario | Severity | Action |
|---|---|---|
| FMP_API_KEY missing | CRITICAL | Exit with error; do not continue |
| API returns empty for SPY/QQQ | HIGH | Emit DataGap; abort screening |
| Data older than 3 days | MEDIUM | Emit DataGap; continue with warning |
| Full S&P 500 unavailable (free tier) | MEDIUM | Emit DataGap; screen top 100 only |
```

---

## What Is Forbidden

1. **Replacing missing data with `0` or `50` (neutral)** without documenting it as an
   assumption and emitting a `DataGap`.

2. **Continuing an analysis silently** when a primary data source returned empty.

3. **Concluding "no issue"** when data was actually unavailable — the absence of a gap
   record must mean "data was available and checked," not "I didn't look."

4. **Suppressing gaps** to produce a cleaner-looking report.

---

## Relationship to Artifact Schemas

Every `ArtifactBase` subclass has a `data_gaps: list[DataGap]` field.
An empty `data_gaps` list means: "All required data was available and used."
A non-empty list means: "Some data was missing or degraded; see records."

The `confidence` field in each artifact reflects the overall data gap state:
- `HIGH` — no gaps
- `MEDIUM` — one or more LOW/MEDIUM gaps
- `LOW` — one or more HIGH gaps
- `None` / omitted — skill did not assess confidence (gap in implementation)
