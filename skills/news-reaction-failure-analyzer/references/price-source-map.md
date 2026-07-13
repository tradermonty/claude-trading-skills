# Price Source Map

## Overview

COT symbols (`ES`, `GC`, `B6`, ...) are not FMP price symbols. This skill
maps each COT symbol to a fallback chain of FMP price symbols, tried in
order via `stable/historical-price-eod/light`. A source "fails" on an HTTP
error (commonly 402, "restricted" — this endpoint's per-symbol coverage is
uneven even on a Premium+ plan) **or** on `rows == 0` — a distinct,
important failure mode where the endpoint returns HTTP 200 with an empty
body rather than an error. Both must be checked explicitly; treating only
HTTP errors as failures would silently produce an empty/misleading price
series for symbols like `VXUSD`.

**Field-name gotcha (verified live):** this endpoint's row shape uses a
`price` field for the daily settlement value, not `close` — confirmed
across futures (`ESUSD`), ETF (`QQQ`), and FX (`GBPUSD`) symbols alike, so
it's an endpoint-wide quirk, not an asset-class difference. Missing this
would silently produce an all-rows-dropped empty series (every symbol
would look like a `no_price_source` failure) rather than an obvious error.
`reaction_math.build_sorted_series()` handles this by accepting `close`
first, falling back to `price`.

The chain constant lives in `scripts/analyze_news_reaction.py`
(`PRICE_SOURCE_CHAINS`); this document records the verified status of each
entry so a human (or Claude) can tell at a glance which markets have a
working source, which fall back to an ETF proxy, and which have none.

## Status Table (live-probed 2026-07-12, on the project's FMP key)

| COT symbol | Chain (→ = fallback) | Status |
|---|---|---|
| ES | ESUSD | 200 OK |
| NQ | NQUSD → QQQ | 402 → ETF OK |
| YM | YMUSD → DIA | 402 → ETF OK |
| QR | RTYUSD → IWM | 402 → ETF OK |
| VX | VXUSD | 200, **0 rows** → `no_price_source` |
| GC | GCUSD | 200 OK |
| SI | SIUSD | 200 OK |
| HG | HGUSD → CPER | 402 → ETF OK |
| PL | PLUSD → PPLT | 402 → ETF OK |
| PA | PAUSD → PALL | 402 → ETF OK |
| CL | CLUSD → BZUSD → USO | 402 → BZUSD 200 OK (grade caveat below; USO untried since BZUSD already succeeds) |
| NG | NGUSD → UNG | 402 → ETF OK |
| RB | RBUSD → UGA | 402 → ETF OK |
| HO | HOUSD | 402, no proxy → `no_price_source` |
| ZT | ZTUSD → SHY | 402 → ETF OK |
| ZF | ZFUSD → IEI | 402 → ETF OK |
| ZN | ZNUSD → IEF | 402 → ETF OK |
| ZB | ZBUSD → TLT | 402 → ETF OK |
| ZQ | ZQUSD | 402, no proxy → `no_price_source` |
| DX | DXUSD → UUP | 402 → ETF OK |
| B6 (GBP) | GBPUSD | 200 OK |
| E6 (EUR) | EURUSD | 200 OK |
| J6 (JPY) | JPYUSD | 200 OK |
| S6 (CHF) | CHFUSD | 200 OK |
| D6 (CAD) | CADUSD | 200 OK |
| A6 (AUD) | AUDUSD | 200 OK |
| N6 (NZD) | NZDUSD | 200 OK |
| BT (Bitcoin) | BTCUSD | 200 OK |
| ZC (Corn) | ZCUSD | 200, **0 rows** → `no_price_source` (no proxy documented yet) |
| ZS (Soybeans) | ZSUSD | 200, **0 rows** → `no_price_source` |
| ZM (Soybean Meal) | ZMUSD | 402, no proxy → `no_price_source` |
| ZL (Soybean Oil) | ZLUSD | 200, **0 rows** → `no_price_source` |
| ZW (Wheat) | ZWUSD | 200, **0 rows** → `no_price_source` |

**No viable source documented (v1 limitation):** VX, ZQ, HO, and all five
agri markets probed (ZC, ZS, ZM, ZL, ZW). Every case fails closed —
`analyze_news_reaction.py` returns `verdict: INSUFFICIENT_EVIDENCE`,
reason `no_price_source`, never a crash or a misleading result from an
empty series. An ETF proxy chain can be added for any of these once a
working source is identified (grain ETFs like `CORN`/`SOYB`/`WEAT` exist
and are plausible candidates, but were not verified against this key at
implementation time — do not assume they work without probing first).

## ETF Proxy Caveats

When a chain falls back to an ETF (`kind: "etf"` in `PRICE_SOURCE_CHAINS`,
surfaced as `run_context.proxy_used: true` in the report), the reaction-
direction read is approximate, not exact:

- **Tracking error:** the ETF doesn't perfectly replicate the futures
  contract's daily return (fees, sampling, cash drag)
- **Expense drag:** a small daily headwind (typically single-digit bps
  annualized) not present in the futures contract itself
- **Roll differences:** commodity/rates ETFs that hold futures internally
  (e.g. `USO`, `UNG`) roll their own positions on a different schedule
  than the COT-tracked contract, which can diverge meaningfully during
  contango/backwardation periods — this is the largest caveat for energy
  proxies specifically

For reaction-DIRECTION testing (did the market move the "right" way
relative to news, not by how much precisely) these caveats are usually
acceptable, but the report always surfaces `proxy_used` so a downstream
consumer (e.g. a future `contrarian-setup-gate`) can weigh it rather than
treating proxy-derived and direct-futures-derived verdicts identically.

## `CL → BZUSD` Grade Caveat

`CL` (WTI crude) falls back to `BZUSD` (Brent crude) rather than an ETF —
both are crude oil futures but different grades with a real, sometimes
volatile spread (WTI-Brent). This is a closer proxy than an ETF (both are
direct futures-style feeds, not fund-wrapper products) but still not the
exact contract COT reports on. Documented here rather than silently
treated as equivalent to a direct `CLUSD` read.

## Implementation Notes

- Single constants dict: `{cot_symbol: [(price_symbol, kind, invert), ...]}`
  in `scripts/analyze_news_reaction.py`. `invert` is kept in the schema
  for future exotic/inverted pairs but is `False` for every v1 entry —
  every current market has a direct `XXXUSD`-style symbol, so no release
  gate depends on inversion handling working correctly yet.
- `--price-symbol` (CLI flag) skips the map entirely for a one-off
  override (e.g. testing a specific proxy, or a symbol not yet in the
  map).
- Status in the table above reflects a point-in-time probe (this key,
  2026-07-12). FMP's per-symbol tier gating can change; if a market that
  previously worked starts returning `no_price_source`, re-probe before
  assuming it's a bug in this skill.
