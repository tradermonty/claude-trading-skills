---
layout: default
title: "Crypto Regime Analyzer"
grand_parent: English
parent: Skill Guides
nav_order: 15
lang_peer: /ja/skills/crypto-regime-analyzer/
permalink: /en/skills/crypto-regime-analyzer/
generated: true
---

# Crypto Regime Analyzer
{: .no_toc }

Quantifies crypto market regime health using free, keyless public data (CoinGecko + Binance funding). Generates a 0-100 composite score across 6 components (100 = risk-on) with a posture recommendation. No API key required. Use when user asks about crypto market conditions, whether it's alt season, BTC dominance, crypto risk-on vs risk-off, funding rates, or whether crypto exposure should be increased or reduced.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/crypto-regime-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/crypto-regime-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Crypto Regime Analyzer Skill

---

## 2. When to Use

- User asks "Is crypto risk-on or risk-off right now?" or "How healthy is the crypto market?"
- User asks "Is it alt season?" or about BTC dominance direction
- User asks whether funding rates are overheated
- User wants an exposure posture for a crypto sleeve before screening individual coins
- User wants a daily crypto regime check alongside the equity `market-regime-daily` workflow

---

## 3. Prerequisites

- **Python 3.9+** with `requests` (live mode only; offline mode is stdlib-only)
- **Internet access** to `api.coingecko.com` and `fapi.binance.com` (live mode)
- **No API keys required**

---

## 4. Quick Start

```bash
mkdir -p reports/<routine-or-date>
python3 skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py \
  --output-dir reports/<routine-or-date>
```

---

## 5. Workflow

### Phase 1: Run the Analysis Script

**Live mode** (fetches CoinGecko + Binance; first run of the day takes ~2-4 minutes at the default `--top-n 20` due to free-tier rate-limit throttling; same-day re-runs hit the cache and are instant):

```bash
mkdir -p reports/<routine-or-date>
python3 skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py \
  --output-dir reports/<routine-or-date>
```

**Offline mode** (no network; snapshot schema in the methodology reference):

```bash
python3 skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py \
  --input-json snapshot.json \
  --output-dir reports/<routine-or-date>
```

Options: `--top-n <int>` universe size (default 20), `--cache-dir <path>` fetch cache location (default `.crypto_regime_cache`), `--quiet`.

### Phase 2: Interpret the Output

The script writes `crypto_regime.json` (machine-readable, for chaining into other skills) and `crypto_regime.md` (one-page report), and prints a one-line summary:

```
CRYPTO REGIME: NEUTRAL (score 68.4/100) — Mixed conditions observed; no strong regime conclusion
```

When presenting results, lead with the zone and posture, then explain the 1-2 components most responsible for the score using their `signal` strings. Flag any components reporting `data_available: false` and what that means for confidence.

### Phase 3 (optional): Feed Downstream

The JSON composite can slot into an `exposure-coach`-style posture summary as
one descriptive crypto-market input. It must not independently authorize,
block, size, or execute a trade.

---

## 6. Resources

**References:**

- `skills/crypto-regime-analyzer/references/VALIDATION.md`
- `skills/crypto-regime-analyzer/references/crypto_regime_methodology.md`

**Scripts:**

- `skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py`
- `skills/crypto-regime-analyzer/scripts/data_client.py`
- `skills/crypto-regime-analyzer/scripts/numeric_utils.py`
- `skills/crypto-regime-analyzer/scripts/report_generator.py`
- `skills/crypto-regime-analyzer/scripts/scorer.py`
