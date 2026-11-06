# Pair Trade FMP Client Migration

Tracking: #495, remaining Batch D. This slice migrates pair-trade-screener;
the tracker remains open for other skills.

Both pair adapters load their sibling generated client under a skill-specific
module name, so another skill's cached `fmp_client` cannot supply the wrong
implementation. The registry selects a budget-free family-B client and a
pair-only response guard. Existing generated clients remain byte-identical. The full-EOD response contract
now lists this generated consumer as an owner, and tests feed its recorded
fixture through both public adapters.

The sector screener now uses `/stable/company-screener` only, as in earlier
migration batches. It retains sector, market-cap and limit parameters, active
stock filtering and output mapping. The obsolete local v3 screener fallback is
removed. Failed, empty or malformed responses retain a controlled failure.

Historical calls share the canonical stable-to-v3 transport and normalization.
They intentionally request available history without a date bound, preserving
latest-N-row behavior for sparse/delisted custom symbols. The two adapters keep
their 730/365 defaults, chronological Series, ticker name, and adjusted-close
preference with close fallback. No statistical calculation is changed.

A target-only guard checks flat/wrapped row shapes, symbol types, canonical
dates and the selected price before common normalization. It emits static
reasons and advances the existing historical fallback on bad data. Client
breaker state is per invocation; earlier calls cannot globally disable later
symbols. Shared header authentication, redaction, timeout and bounded retries
replace raw requests; no live provider access or plan-tier verification occurs.

Regenerate with `python3 scripts/generate_fmp_client.py`, then package with
`python3 scripts/package_skills.py --skill pair-trade-screener`. CI and pre-commit
check this client's source and archive. Transport tests use fake Sessions and
fresh interpreters, including a foreign-client cache, sparse history, failures
and redaction.
