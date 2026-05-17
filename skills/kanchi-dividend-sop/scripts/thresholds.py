"""Single source of truth (SSOT) for Kanchi SOP thresholds.

Per improvement plan v2 MJ-8: thresholds live here, not duplicated across
SKILL.md / default-thresholds.md / inline script args. The markdown references
are human-readable mirrors of these values, not independent definitions.

Schema version is bumped whenever the build_entry_signals.py JSON output
contract changes (MJ-10), so downstream consumers (kanchi-dividend-review-monitor)
can detect and tolerate schema evolution.
"""

from __future__ import annotations

# JSON output contract version (WS-1 / MJ-10).
SCHEMA_VERSION = 2

# --- Step 1: yield floor + entry alpha ---
DEFAULT_ALPHA_PP = 0.5

# Profile-specific yield floors (default-thresholds.md "Objective Tuning").
YIELD_FLOOR_BY_PROFILE = {
    "income-now": 4.0,
    "balanced": 3.0,
    "growth-first": 1.5,
}

# --- Data Freshness Gate (v2.1, makes D5 explicit) ---
# If the latest-declared-dividend yield is within this band of the floor,
# the Step-1 decision is too sensitive to stale dividend data: force a
# STEP1-RECHECK (never a hard FAIL) until the latest declared dividend is
# confirmed from an authoritative source.
FLOOR_FRESHNESS_BAND_PP = 0.20

# --- WS-1: dividend-action detection ---
# A pay above this multiple of the trailing-median regular pay is treated
# as a special/supplemental dividend (amount-outlier path, label-independent).
SPECIAL_OUTLIER_MULTIPLE = 1.5
# An extreme isolated spike (>= this x trailing-local median) is a special
# on magnitude alone (e.g. ORI's ~7x annual special), even at the series
# end where no later pay exists to confirm a reversion.
SPECIAL_EXTREME_MULTIPLE = 3.0
# Between 1.5x and 3x it is a special ONLY if a later pay reverts to near
# the trailing-local median (a one-off), distinguishing it from ordinary
# steep dividend growth which does not revert.
SPECIAL_REVERT_MULTIPLE = 1.2

# Coefficient of variation of the 12-month-normalized *residual* (post-special)
# dividend stream above which the issuer is treated as a variable-dividend
# payer (e.g. CALM pays ~1/3 of net income).
VARIABLE_POLICY_COV = 0.35

# Equality epsilon for freeze/cut comparison of annualized dividend totals
# (absolute USD per share). Below this, two annual totals are "equal".
DIVIDEND_EQUALITY_EPS = 0.005

# Grace period (days) added to the inferred increase cadence before a
# same-amount window is treated as a freeze rather than "just hasn't raised
# yet this cycle" (v2.1 R-2, reduces annual-raiser false positives).
FREEZE_GRACE_DAYS = 45

# Minimum number of regular dividend pays required before statistical
# detection (CoV / freeze) is meaningful. Below this -> ASSUMPTION-REQUIRED.
MIN_REGULAR_PAYS = 4

# --- WS-2: payout triad + one-off divergence ---
ADJ_EPS_PAYOUT_CAUTION = 0.70  # 0.70-0.85 = caution band
ADJ_EPS_PAYOUT_MAX = 0.85
FCF_PAYOUT_MAX = 0.80
FCF_PAYOUT_HIGH_RISK = 1.00

# Sector-module thresholds (5th-review F2 — deepen bank/utility/insurer).
BANK_DEPOSIT_BETA_HIGH = 0.50  # deposit cost passes through fast -> margin risk
UTILITY_FFO_DEBT_MIN = 0.13  # below this, regulated leverage is stretched
INSURER_OP_EPS_PAYOUT_MAX = 0.85  # operating-EPS payout hard ceiling
# GAAP vs Adjusted EPS divergence above which a Step-4 one-off flag fires.
# Marked calibratable (MN-4): initial value, revisit with a payout-gap
# distribution study across Dividend Aristocrats.
GAAP_ADJ_DIVERGENCE = 0.25

# --- WS-3: structural-event materiality (v2.1 R-4) ---
MNA_TX_VALUE_PCT_MCAP = 0.10
MNA_SHARE_ISSUANCE_PCT = 0.10
MNA_LEVERAGE_DELTA_EBITDA = 0.5
# A completed merger within this many trailing quarters presumes GAAP EPS
# is distorted -> force the adjusted-EPS path (WS-2 linkage, FITB/Comerica).
COMPLETED_MNA_LOOKBACK_QUARTERS = 4

# --- WS-6: portfolio constraints (default-thresholds.md mirror) ---
MAX_SINGLE_POSITION_PCT = 8.0
MAX_SECTOR_PCT = 25.0
# Sector cluster-risk warning: >= this many same-sector PASS names share one
# macro beta (NEW-4, e.g. many small banks).
SECTOR_CLUSTER_WARN_COUNT = 4

# --- Verdict tier (WS-5, v2.1) ---
VERDICTS = (
    "CLEAN-PASS",
    "PASS-CAUTION",
    "CONDITIONAL-PASS",
    "HOLD-REVIEW",
    "STEP1-RECHECK",
    "FAIL",
)
