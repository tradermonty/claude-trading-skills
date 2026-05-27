# TraderMonty Research-Grade Audit

**Generated:** 2026-05-26
**Status:** Initial audit — Phase 1 of 15-phase hardening mission
**Scope:** Full repository; all 54 skills, 5 workflows, all scripts, all docs

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Skills by Purpose](#2-skills-by-purpose)
3. [Workflows and Dependencies](#3-workflows-and-dependencies)
4. [External API Requirements](#4-external-api-requirements)
5. [Manual-Only Skills (No Code)](#5-manual-only-skills-no-code)
6. [Code/Script-Executing Skills](#6-codescript-executing-skills)
7. [Generated Artifacts Inventory](#7-generated-artifacts-inventory)
8. [Gaps in Schemas and Contracts](#8-gaps-in-schemas-and-contracts)
9. [Duplicated Concepts](#9-duplicated-concepts)
10. [Prose-Only Outputs](#10-prose-only-outputs)
11. [Data Gap Handling Gaps](#11-data-gap-handling-gaps)
12. [Overfitting and Hindsight-Bias Risks](#12-overfitting-and-hindsight-bias-risks)
13. [Missing Tests and Validators](#13-missing-tests-and-validators)
14. [Prioritized Hardening Plan](#14-prioritized-hardening-plan)

---

## 1. Executive Summary

TraderMonty is a well-conceived decision-support toolkit for solo traders. The project vision, PROJECT_VISION.md, is strong and clearly establishes the "decision-support OS, not a signal service" principle. The five core workflow manifests (market-regime-daily, swing-opportunity-daily, core-portfolio-weekly, trade-memory-loop, monthly-performance-review) follow a solid structure with explicit decision gates, manual review items, and journal destinations.

**What is working well:**
- Clear project vision and disclaimer language in PROJECT_VISION.md
- 5 workflow manifests with decision gates, manual review, and journal destinations
- `skills-index.yaml` as canonical SSoT with validator (`validate_skills_index.py`)
- Pre-commit hooks enforcing frontmatter, docs completeness, and no absolute paths
- Many skills produce both JSON and Markdown output
- Existing test infrastructure (462 Python files across ~40 skill test dirs)
- Workflow validator (WF001–WF012 error codes) and index validator (IDX001–IDX012)

**Critical gaps requiring Phase 2–15 work:**
1. **No canonical artifact schemas** — JSON shape is defined per-skill in prose, not enforced by shared schema classes. Consuming skills cannot rely on field contracts.
2. **No shared Data Gap Protocol** — each skill handles missing data differently; some silently continue with neutral assumptions.
3. **No structured TradeThesis / JournalEntry / PostmortemReport schemas** — trader-memory-core output format is documented in prose.
4. **Backtest/research skills lack mandatory overfitting guards** — no-lookahead checklist, survivorship bias warning, and out-of-sample requirement are absent from SKILL.md files.
5. **Trade planning skills lack mandatory structured TradePlan output** — candidates are described in prose without a required JSON contract.
6. **Workflow validator does not check artifact schema IDs** — artifacts are identified only by string name, not by a typed schema.
7. **No local workflow runner** — workflows must be followed manually with no tooling support; no `WorkflowRun` artifact is ever saved.
8. **Skill packages are not hash-validated** — `skill-packages/` may contain stale ZIPs without detection.
9. **Seven skills produce prose-only output** without any JSON artifact (see §10).
10. **Portfolio review skills lack explicit concentration/tax-disclaimer language** in structured form.

---

## 2. Skills by Purpose

### 2.1 Market Regime (11 skills)

| Skill ID | Script? | API | Output Types | Notes |
|---|---|---|---|---|
| `market-breadth-analyzer` | Yes | None (CSV) | JSON + Markdown | 6-component 0-100 score; solid structured output |
| `uptrend-analyzer` | Yes | None (CSV) | JSON + Markdown | 5-component 0-100; solid |
| `ftd-detector` | Yes | FMP required | JSON + Markdown | State machine; solid |
| `ibd-distribution-day-monitor` | Yes | FMP required | JSON + Markdown | TQQQ/QQQ exposure; detailed |
| `market-top-detector` | Yes | FMP required | JSON + Markdown | 0-100 top probability |
| `macro-regime-detector` | Yes | FMP required | JSON + Markdown | 1-2yr structural; 6 components |
| `breadth-chart-analyst` | Yes | None (image/CSV) | Markdown only | **No JSON output defined** |
| `sector-analyst` | Yes | None (CSV/image) | Markdown only | **No JSON output defined** |
| `market-environment-analysis` | Yes (utils only) | WebSearch | Markdown only | **Prose-only; WebSearch** |
| `us-market-bubble-detector` | Yes | WebSearch/manual | Markdown only | **Prose-only; subjective** |
| `scenario-analyzer` | No | WebSearch | Markdown (Japanese) | Multi-agent orchestrator |

**Gaps:** `breadth-chart-analyst`, `sector-analyst`, `market-environment-analysis`, and `us-market-bubble-detector` produce no structured JSON artifact. Downstream skills that consume their outputs (exposure-coach) cannot reliably parse them.

### 2.2 Core Portfolio (7 skills)

| Skill ID | Script? | API | Output Types | Notes |
|---|---|---|---|---|
| `portfolio-manager` | Yes | Alpaca MCP | Markdown/JSON | Alpaca-dependent; portfolio review |
| `kanchi-dividend-sop` | Yes | FMP optional | JSON + Markdown | 5-step dividend SOP |
| `kanchi-dividend-review-monitor` | Yes | FMP optional | JSON + Markdown | T1-T5 anomaly checks |
| `kanchi-dividend-us-tax-accounting` | No | None | Markdown only | **Prose-only; tax guidance** |
| `value-dividend-screener` | Yes | FMP required | JSON + Markdown | 2-stage screening |
| `dividend-growth-pullback-screener` | Yes | FMP required | JSON + Markdown | RSI-filtered growth |
| `earnings-calendar` | Yes | FMP required | Markdown | Calendar output; structured? TBD |

**Gaps:** `kanchi-dividend-us-tax-accounting` is prose-only and lacks explicit "not tax advice" structured disclaimer. `portfolio-manager` concentration/allocation metrics are not output in a standard schema.

### 2.3 Swing Opportunity (8 skills)

| Skill ID | Script? | API | Output Types | Notes |
|---|---|---|---|---|
| `vcp-screener` | Yes | FMP required | JSON + Markdown | Solid; many tunable params |
| `canslim-screener` | Yes | FMP required | JSON + Markdown | 7-factor CANSLIM |
| `technical-analyst` | No | Image input | Markdown only | **Prose-only; chart images** |
| `breakout-trade-planner` | Yes | None (calc) | JSON + Markdown | Alpaca order templates |
| `position-sizer` | Yes | None (calc) | JSON + Markdown | Kelly/ATR/stop-loss modes |
| `pead-screener` | Yes | FMP required | JSON + Markdown | Post-earnings drift |
| `earnings-trade-analyzer` | Yes | FMP required | JSON + Markdown | 5-factor scoring |
| `finviz-screener` | Yes | FINVIZ optional | URL output | **Opens browser; no artifact** |

**Gaps:** `technical-analyst` is chart-image-only with no structured output. `finviz-screener` opens a browser URL — it produces no storable artifact. None of the screeners currently output a `ScreenCandidate` schema with all required fields (setup type, entry trigger, invalidation, stop, target, R/R, position size, risk dollars, portfolio heat, earnings risk, regime permission, manual review status).

### 2.4 Trade Planning (4 skills)

| Skill ID | Script? | API | Output Types | Notes |
|---|---|---|---|---|
| `parabolic-short-trade-planner` | Yes | FMP + Alpaca opt | JSON + Markdown | 3-phase pipeline; most complete |
| `options-strategy-advisor` | Yes | FMP optional | JSON + Markdown | Black-Scholes; theoretical |
| `downtrend-duration-analyzer` | TBD | None (calc) | Markdown | Duration analysis |
| `pair-trade-screener` | Yes | FMP required | JSON + Markdown | Cointegration; z-score |

**Gaps:** `parabolic-short-trade-planner` is the most complete trade-plan skill but Phase 2 plan output lacks a standard `TradePlan` schema. Options and pairs also lack canonical schema.

### 2.5 Trade Memory (5 skills)

| Skill ID | Script? | API | Output Types | Notes |
|---|---|---|---|---|
| `trader-memory-core` | Yes | FMP optional | JSON + Markdown | Full thesis lifecycle |
| `signal-postmortem` | Yes | None (calc) | JSON + Markdown | Good/bad process matrix |
| `trade-hypothesis-ideator` | No | None | Markdown | Prose-only hypothesis gen |
| `exposure-coach` | Yes | FMP optional | JSON + Markdown | Unified posture synthesis |
| `economic-calendar-fetcher` | Yes | FMP required | Markdown | Calendar events |

**Gaps:** `trader-memory-core` thesis lifecycle only has IDEA/ENTRY_READY/ACTIVE/CLOSED states — missing CANDIDATE, PLANNED, MANAGED, POSTMORTEM_DONE, ARCHIVED. Journal entry and postmortem schemas are prose-documented, not Python dataclasses. `trade-hypothesis-ideator` produces no structured artifact.

### 2.6 Strategy Research (9 skills)

| Skill ID | Script? | API | Output Types | Notes |
|---|---|---|---|---|
| `backtest-expert` | No | None (guidance) | Markdown | **Prose-only; no overfitting guards** |
| `edge-pipeline-orchestrator` | Yes | None (local) | JSON + Markdown | Good pipeline; 7 stages |
| `edge-candidate-agent` | Yes | FMP optional | JSON + Markdown | Ticket + market summary |
| `edge-hint-extractor` | Yes | None (calc) | JSON + Markdown | Hints from observations |
| `edge-concept-synthesizer` | Yes | None (calc) | JSON + Markdown | Concept extraction |
| `edge-strategy-designer` | Yes | None (calc) | YAML + Markdown | Strategy drafts |
| `edge-strategy-reviewer` | Yes | None (calc) | YAML + Markdown | PASS/REVISE/REJECT |
| `edge-signal-aggregator` | TBD | None | Markdown | Signal aggregation |
| `strategy-pivot-designer` | No | None | Markdown | **Prose-only pivot proposals** |

**Gaps:** `backtest-expert` contains no mandatory no-lookahead checklist, survivorship bias warning, transaction cost/slippage assumptions, or out-of-sample requirement. `edge-strategy-reviewer` scoring is deterministic but lacks explicit overfitting checks as a requirement category. `strategy-pivot-designer` is entirely prose.

### 2.7 Advanced Satellite (3 skills)

| Skill ID | Script? | API | Output Types | Notes |
|---|---|---|---|---|
| `institutional-flow-tracker` | Yes | FMP required | JSON + Markdown | 13F data |
| `theme-detector` | Yes | FINVIZ opt/FMP opt | JSON + Markdown | Theme lifecycle |
| `stanley-druckenmiller-investment` | No | None | Markdown | **Prose-only** |

**Gaps:** `stanley-druckenmiller-investment` is entirely prose with no structured artifact.

### 2.8 Meta / Tooling (11 skills)

| Skill ID | Script? | API | Output Types | Notes |
|---|---|---|---|---|
| `trading-skills-navigator` | No | None (local YAML) | Markdown | Interactive guide |
| `skill-designer` | No | None | Markdown | Scaffold generator |
| `skill-idea-miner` | Yes | None (local files) | YAML + Markdown | Session log mining |
| `dual-axis-skill-reviewer` | Yes | None (calc) | JSON + Markdown | 5-cat deterministic |
| `skill-integration-tester` | Yes | None | Markdown | Contract validation |
| `data-quality-checker` | Yes | None (calc) | JSON + Markdown | Markdown validation |
| `market-news-analyst` | No | WebSearch | Markdown | No structured artifact |
| `macro-regime-detector` | Yes | FMP required | JSON + Markdown | (listed also in market-regime) |
| `uptrend-analyzer` | Yes | None (CSV) | JSON + Markdown | (also market-regime) |
| `market-breadth-analyzer` | Yes | None (CSV) | JSON + Markdown | (also market-regime) |
| `scenario-analyzer` | No | WebSearch | Markdown (JP) | Agent orchestrator |

---

## 3. Workflows and Dependencies

### 3.1 Defined Workflows

| ID | Cadence | Minutes | Skills | Decision Gates | Artifacts |
|---|---|---|---|---|---|
| `market-regime-daily` | daily | 15 | 5 (3 req, 2 opt) | 1 | 4 |
| `swing-opportunity-daily` | daily | 30 | 7 (4 req, 3 opt) | 2 | 7 |
| `core-portfolio-weekly` | weekly | 60 | 5 (2 req, 3 opt) | 2 | 5 |
| `trade-memory-loop` | ad-hoc | 30 | 3 (2 req, 1 opt) | 1 | 4 |
| `monthly-performance-review` | monthly | 90 | 4 (2 req, 2 opt) | 2 | 7 |

### 3.2 Inter-Workflow Dependency Graph

```
market-regime-daily
    └─ produces: exposure_decision
          └─► swing-opportunity-daily (prerequisite)
                └─ produces: trade_plans, candidate_journal_entry
                      └─► trade-memory-loop (per closed position)
                            └─ produces: postmortem_findings, lessons_log_entry
                                  └─► monthly-performance-review

core-portfolio-weekly
    └─ produces: weekly_journal_entry
          └─► monthly-performance-review (aggregate)
```

### 3.3 Missing Workflows

The following workflows are described in PROJECT_VISION.md as needed but do not yet have YAML manifests:
- `risk-off-short-daily` (parabolic-short-trade-planner, ibd-distribution-day-monitor)
- `earnings-weekly` (earnings-trade-analyzer, pead-screener, technical-analyst)
- `macro-morning-brief` (macro-regime-detector, market-environment-analysis)
- `strategy-research-pipeline` (edge-pipeline-orchestrator, backtest-expert)

### 3.4 Skills Not In Any Workflow

The following production skills are not referenced by any current workflow manifest:
- `breadth-chart-analyst` (manual chart analysis)
- `sector-analyst`
- `market-environment-analysis`
- `macro-regime-detector`
- `ibd-distribution-day-monitor`
- `ftd-detector`
- `us-market-bubble-detector`
- `canslim-screener` (optional in swing-opportunity-daily but not in required list)
- `earnings-trade-analyzer`
- `pead-screener`
- `parabolic-short-trade-planner`
- `options-strategy-advisor`
- `pair-trade-screener`
- `institutional-flow-tracker`
- `theme-detector`
- `stanley-druckenmiller-investment`
- `scenario-analyzer`
- `finviz-screener`
- `downtrend-duration-analyzer`
- All edge-pipeline sub-skills

---

## 4. External API Requirements

| API | Requirement Level | Skills Using It |
|---|---|---|
| FMP (Financial Modeling Prep) | Required | ftd-detector, ibd-distribution-day-monitor, market-top-detector, macro-regime-detector, vcp-screener, canslim-screener, pead-screener, earnings-trade-analyzer, earnings-calendar, economic-calendar-fetcher, institutional-flow-tracker, pair-trade-screener, parabolic-short-trade-planner (Phase 1), value-dividend-screener, dividend-growth-pullback-screener, kanchi-dividend-sop, kanchi-dividend-review-monitor |
| FMP (Financial Modeling Prep) | Optional | exposure-coach, options-strategy-advisor, edge-candidate-agent, theme-detector, macro-regime-detector, trader-memory-core |
| FINVIZ Elite | Optional | finviz-screener, value-dividend-screener, dividend-growth-pullback-screener, theme-detector |
| Alpaca Brokerage MCP | Required | portfolio-manager |
| Alpaca Brokerage MCP | Optional | parabolic-short-trade-planner (Phase 2 borrow check) |
| WebSearch / WebFetch | Required | market-news-analyst, market-environment-analysis, us-market-bubble-detector, scenario-analyzer (via agents) |
| GitHub CSV (public) | Required | market-breadth-analyzer, uptrend-analyzer, sector-analyst, breadth-chart-analyst |

---

## 5. Manual-Only Skills (No Code)

These skills contain no Python scripts. They operate entirely through Claude's language capabilities, WebSearch, chart image analysis, or agent invocation.

| Skill | Mechanism | Structured Output? |
|---|---|---|
| `backtest-expert` | LLM guidance | No |
| `technical-analyst` | Chart image analysis | No |
| `trading-skills-navigator` | LLM + local YAML | No |
| `skill-designer` | LLM scaffold generation | No |
| `trade-hypothesis-ideator` | LLM ideation | No |
| `strategy-pivot-designer` | LLM proposals | No |
| `stanley-druckenmiller-investment` | LLM synthesis | No |
| `kanchi-dividend-us-tax-accounting` | LLM guidance | No |
| `market-news-analyst` | WebSearch + LLM | No (prose only) |
| `market-environment-analysis` | WebSearch + LLM | No (prose only) |
| `us-market-bubble-detector` | Manual data + LLM | No (prose only) |
| `scenario-analyzer` | Agent orchestration | No (prose, Japanese) |
| `finviz-screener` | URL generation | No (browser URL only) |

---

## 6. Code/Script-Executing Skills

These skills execute Python scripts to produce structured output.

### Tier A — Full JSON + Markdown Output (production-grade)
- `market-breadth-analyzer`, `uptrend-analyzer`, `ftd-detector`, `ibd-distribution-day-monitor`, `market-top-detector`, `macro-regime-detector`
- `vcp-screener`, `canslim-screener`, `pead-screener`, `earnings-trade-analyzer`, `parabolic-short-trade-planner`
- `value-dividend-screener`, `dividend-growth-pullback-screener`, `kanchi-dividend-sop`, `kanchi-dividend-review-monitor`
- `trader-memory-core`, `signal-postmortem`, `exposure-coach`
- `edge-pipeline-orchestrator`, `edge-candidate-agent`, `edge-concept-synthesizer`, `edge-hint-extractor`, `edge-strategy-designer`, `edge-strategy-reviewer`
- `dual-axis-skill-reviewer`, `data-quality-checker`, `position-sizer`, `breakout-trade-planner`

### Tier B — Markdown Primary, JSON Inconsistent
- `breadth-chart-analyst` (CSV + optional image; Markdown only)
- `sector-analyst` (CSV + optional image; Markdown only)
- `earnings-calendar`, `economic-calendar-fetcher` (Markdown calendar tables)
- `institutional-flow-tracker`, `pair-trade-screener`, `theme-detector` (JSON exists but no canonical schema)
- `portfolio-manager` (Alpaca MCP; report format unspecified)

### Tier C — URL Output Only
- `finviz-screener` (builds browser URL; no stored artifact)

---

## 7. Generated Artifacts Inventory

### 7.1 Known Artifact File Patterns

| Skill | JSON Pattern | Markdown Pattern |
|---|---|---|
| market-breadth-analyzer | `market_breadth_YYYY-MM-DD_HHMMSS.json` | `market_breadth_YYYY-MM-DD_HHMMSS.md` |
| uptrend-analyzer | `uptrend_analysis_YYYY-MM-DD_HHMMSS.json` | `uptrend_analysis_YYYY-MM-DD_HHMMSS.md` |
| ftd-detector | `ftd_detector_YYYY-MM-DD_HHMMSS.json` | `ftd_detector_YYYY-MM-DD_HHMMSS.md` |
| ibd-distribution-day-monitor | `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.json` | `ibd_distribution_day_monitor_YYYY-MM-DD_HHMMSS.md` |
| market-top-detector | `top_risk_YYYY-MM-DD_HHMMSS.json` | `top_risk_YYYY-MM-DD_HHMMSS.md` |
| macro-regime-detector | `macro_regime_YYYY-MM-DD_HHMMSS.json` | `macro_regime_YYYY-MM-DD_HHMMSS.md` |
| vcp-screener | `vcp_screener_YYYY-MM-DD_HHMMSS.json` | `vcp_screener_YYYY-MM-DD_HHMMSS.md` |
| earnings-trade-analyzer | `earnings_trade_YYYY-MM-DD_HHMMSS.json` | `earnings_trade_YYYY-MM-DD_HHMMSS.md` |
| pead-screener | `pead_YYYY-MM-DD_HHMMSS.json` | `pead_YYYY-MM-DD_HHMMSS.md` |
| parabolic-short | `parabolic_short_YYYY-MM-DD.json` | `parabolic_short_YYYY-MM-DD.md` |
| exposure-coach | `exposure_posture_YYYY-MM-DD_HHMMSS.json` | `exposure_posture_YYYY-MM-DD_HHMMSS.md` |
| trader-memory-core | `thesis_*.json` | various |

### 7.2 Artifact Schema Status

No canonical Python schema classes exist. Each skill defines its own JSON shape in SKILL.md prose. There is no shared `schemas/` directory, no Pydantic models, no JSON Schema files, and no inter-skill field contract enforcement.

**Required schemas not yet defined:**
- `DataGap` — severity, affected decision, remediation, can_continue
- `DataQualityReport` — wraps DataGap list
- `MarketRegimeReport` — composite score, zone, regime type, components
- `ExposureDecision` — ceiling_pct, recommendation, confidence, bias, rationale
- `BreadthAssessment` — score, zone, components, staleness
- `UptrendAssessment` — score, zone, sector_heatmap, warnings
- `MarketTopRiskReport` — score, risk_zone, distribution_days, components
- `MacroRegimeReport` — regime_type, components, confidence, horizon
- `ScreenCandidate` — ticker, setup_type, entry_trigger, stop, target, r_r, size, risk_dollars, portfolio_heat, earnings_risk, regime_permission, chart_review_status, data_gaps, rejection_reason
- `TechnicalValidation` — ticker, setup_quality, stage, base_type, manual_review_done
- `PositionSizingPlan` — ticker, shares, risk_dollars, portfolio_heat, method, inputs
- `TradePlan` — extends ScreenCandidate with entry_plan, stop, target, order_type
- `TradeThesis` — id, symbol, lifecycle_state, setup, market_regime, entry_plan, risk_plan, position_size, screenshots, emotions, rule_deviations, exit_reason, outcome, lessons
- `JournalEntry` — workflow_run_id, date, entries[], summary
- `PostmortemReport` — thesis_id, process_quality (good/bad), outcome_quality (good/bad), classification, root_cause, lessons, rule_changes
- `BacktestSpec` — strategy, universe, period, in_sample, out_of_sample, costs, slippage, lookahead_check
- `BacktestReport` — spec, metrics, regime_breakdown, overfitting_warnings, out_of_sample_required
- `StrategyReview` — draft_id, scores, pass_fail, overfitting_flags, recommendation
- `PortfolioReview` — holdings, allocation_by_class, sector_concentration, single_name_concentration, dividend_risk, rebalance_candidates, do_nothing_option, disclaimer
- `DividendReview` — ticker, anomaly_flags, t1_t5_checks, review_queue
- `ScenarioAnalysis` — headline, scenarios (base/bull/bear), sector_impacts, stock_impacts, confidence, horizon
- `WorkflowRun` — run_id, workflow_id, started_at, completed_at, steps[], artifacts[], decision_gate_answers[], status

---

## 8. Gaps in Schemas and Contracts

### 8.1 No Canonical Artifact Schema Layer

**Gap:** Skills output JSON with shape documented only in SKILL.md prose. No Python dataclasses, Pydantic models, or JSON Schema files exist. No validation of inter-skill artifact compatibility.

**Impact:** `exposure-coach` accepts JSON from up to 8 upstream skills; if any skill changes its output shape, the coach silently gets wrong data. `swing-opportunity-daily` expects `exposure_decision` from `market-regime-daily` but has no way to validate the format.

**Fix (Phase 2):** Add `schemas/artifacts.py` with Pydantic models or dataclasses + JSON Schema export for all ~25 artifact types.

### 8.2 Workflow Artifact IDs Are Strings, Not Typed

**Gap:** In `workflows/*.yaml`, artifact IDs like `exposure_decision`, `vcp_candidates`, `trade_plans` are plain strings. No link to a schema class.

**Impact:** The workflow validator (WF001–WF012) checks artifact name consistency but cannot verify field-level contracts.

**Fix (Phase 4):** Add `schema_id` field to each workflow artifact entry; validator checks against `schemas/artifacts.py` exports.

### 8.3 `consumes:` Steps Have No Field Mapping

**Gap:** When a step declares `consumes: [exposure_decision]`, there is no mapping of which fields from that artifact it actually reads.

**Impact:** Silent breakage when upstream artifact shape changes; no way to detect during validation.

**Fix (Phase 4):** Add optional `consumes_fields:` to step definitions for documentation (not necessarily enforced).

### 8.4 `trader-memory-core` Thesis Schema Is Prose-Only

**Gap:** The thesis lifecycle (IDEA → ENTRY_READY → ACTIVE → CLOSED) is documented in SKILL.md but not in a Python class. The JSON output files are not validated against a schema.

**Impact:** Postmortem and monthly-review skills consuming `closed_thesis_record` must guess the field names.

**Fix (Phase 9):** Define `TradeThesis` Pydantic model; update `thesis_ingest.py` and `thesis_store.py` to validate against it.

### 8.5 `exposure-coach` Input Contract Is Underdefined

**Gap:** `exposure-coach/scripts/calculate_exposure.py` accepts `--breadth`, `--uptrend`, etc. as file paths but does not validate the JSON schema of each file.

**Impact:** Partial inputs reduce confidence but do not block execution — which is by design — but missing required fields within an existing file are silently ignored.

**Fix (Phase 3):** Add input schema validation to `calculate_exposure.py`; emit `DataGap` records for missing fields.

---

## 9. Duplicated Concepts

### 9.1 Breadth Analysis (Three Overlapping Skills)

`market-breadth-analyzer`, `uptrend-analyzer`, and `breadth-chart-analyst` all measure market breadth. They use different data sources (CSV via script, CSV via script, CSV/image via LLM), different scoring systems (6-component 0-100, 5-component 0-100, qualitative), and different output formats.

**Issue:** `exposure-coach` accepts all three as optional inputs, but the weight given to each is not calibrated against each other. A high score from one and low from another is unresolved.

**Recommendation:** Define a `BreadthAssessment` canonical schema that all three emit. `exposure-coach` then has a typed input contract.

### 9.2 Market Top / Distribution Day (Two Overlapping Skills)

`market-top-detector` and `ibd-distribution-day-monitor` both count distribution days and assess market deterioration risk. They use the same underlying FMP data and partially overlapping logic.

**Issue:** They may give conflicting signals without a reconciliation layer.

**Recommendation:** Document the intended relationship: `ibd-distribution-day-monitor` is the raw daily signal; `market-top-detector` is the composite tactical 0-100 score. Make `market-top-detector` optionally consume `ibd-distribution-day-monitor` output.

### 9.3 Entry Planning (Three Overlapping Skills)

`breakout-trade-planner`, `parabolic-short-trade-planner`, and `options-strategy-advisor` all generate entry plans for specific setups. They each define stop/target/size in their own format.

**Recommendation:** Define a canonical `TradePlan` schema that all three populate, differing only in the `setup_type` field.

### 9.4 Postmortem (Two Skills)

`signal-postmortem` and `trade-hypothesis-ideator` both deal with trade outcome analysis. `signal-postmortem` is structured; `trade-hypothesis-ideator` is prose-only ideation.

**Recommendation:** Keep both but ensure `signal-postmortem` defines the canonical `PostmortemReport` schema.

### 9.5 Skill Review (Two Meta-Skills)

`dual-axis-skill-reviewer` (deterministic + LLM scoring) and `skill-integration-tester` (contract validation) both review skill quality. Their scopes differ but overlap.

**Recommendation:** Document distinct scopes: `dual-axis-skill-reviewer` reviews skill *quality*; `skill-integration-tester` reviews *workflow contract* compatibility.

---

## 10. Prose-Only Outputs

These skills produce no structured JSON artifact. Any downstream skill or workflow step consuming their output must parse free-form markdown or prose.

| Skill | Why Prose-Only | Risk |
|---|---|---|
| `backtest-expert` | LLM guidance skill; no script | HIGH — backtest conclusions can't be programmatically parsed |
| `technical-analyst` | Chart image analysis; inherently qualitative | MEDIUM — can be addressed with `TechnicalValidation` JSON output |
| `kanchi-dividend-us-tax-accounting` | Tax guidance; deliberately educational | LOW — add disclaimer JSON wrapper |
| `market-news-analyst` | WebSearch synthesis | MEDIUM — impact scores could be JSON |
| `market-environment-analysis` | WebSearch synthesis | MEDIUM — risk-on/risk-off signal could be JSON |
| `us-market-bubble-detector` | Manual scoring + LLM | MEDIUM — bubble score could be JSON |
| `stanley-druckenmiller-investment` | LLM synthesis | MEDIUM — investment posture could be JSON |
| `trade-hypothesis-ideator` | LLM ideation | MEDIUM — hypothesis could emit `TradeThesis` JSON stub |
| `strategy-pivot-designer` | LLM proposals | MEDIUM — pivot proposal could emit `StrategyReview` JSON |
| `breadth-chart-analyst` | Chart + CSV analysis; Markdown only | HIGH — fed to exposure-coach via opaque file |
| `sector-analyst` | Chart + CSV analysis; Markdown only | HIGH — no downstream consumer can parse it |
| `scenario-analyzer` | Multi-agent Japanese output | LOW — standalone use; no downstream schema dependency |

**Requirement (Phase 3):** Every skill in a production workflow must produce a structured JSON artifact alongside its Markdown narrative. Prose-only skills used in workflows must add a minimal JSON wrapper containing at minimum: skill_id, artifact_type, created_at, summary_signal, confidence, data_gaps[], manual_review_required, disclaimer.

---

## 11. Data Gap Handling Gaps

### 11.1 No Shared Data Gap Protocol

There is no shared `docs/dev/data-gap-protocol.md` or shared Python utility for emitting `DataGap` records. Each skill defines (or ignores) data gap handling individually.

### 11.2 Known Problematic Patterns

| Skill | Problematic Pattern |
|---|---|
| `exposure-coach` | Missing inputs reduce `confidence` but do not block execution — **correct behavior** but no `DataGap` records are emitted to the output artifact |
| `market-environment-analysis` | Uses WebSearch; if search returns no data, analysis continues with "information is limited" — **silent neutral conclusion** |
| `us-market-bubble-detector` | Some indicators are manual (user provides); if not provided, scoring continues without them — **undisclosed assumption** |
| `backtest-expert` | No minimum sample size check; short backtest periods receive no warning — **overfitting risk** |
| `vcp-screener` | `--full-sp500` requires paid FMP tier; on free tier with fewer results, no staleness warning is emitted for the truncated universe — **scope gap** |
| `macro-regime-detector` | If FMP returns empty for any of the 9 ETFs, component score defaults to 0 — **may be documented but should be explicit DataGap** |
| `canslim-screener` | API rate limit handling uses backoff but may return partial results without flagging — **data completeness gap** |
| `trader-memory-core` | MAE/MFE calculation requires FMP; if API key missing, silently skips — **undisclosed data gap in postmortem** |

### 11.3 Required Data Gap Scenarios (Phase 6)

Every skill must explicitly handle and document:
1. API key missing — CRITICAL; fail with actionable error
2. API returns empty — HIGH; emit DataGap, do not continue with neutral assumption
3. Data too stale (>N days old) — severity depends on skill cadence
4. Sample size too small — HIGH for backtests, MEDIUM for screeners
5. Market regime unclear — MEDIUM; flag in exposure decision
6. Conflicting signals — MEDIUM; flag in exposure decision
7. Chart screenshot missing (image-based skills) — HIGH; cannot proceed
8. CSV missing (breadth/uptrend/sector) — CRITICAL for those skills
9. Liquidity too low — HIGH for trade plans
10. Risk budget unavailable — HIGH; block trade plan generation

---

## 12. Overfitting and Hindsight-Bias Risks

### 12.1 `backtest-expert`

**Current state:** LLM guidance only; no enforcement of any backtest discipline.

**Risks:**
- No requirement for in-sample / out-of-sample split
- No lookahead bias checklist
- No survivorship bias warning
- No minimum sample size (trades/years)
- No transaction cost / slippage assumption
- No parameter stability check
- No regime segmentation requirement
- No false discovery risk warning

**Required additions (Phase 7):**
```
## Backtest Quality Checklist (MANDATORY)
- [ ] No-lookahead checklist completed (signals use only data available at signal time)
- [ ] Survivorship bias acknowledged (universe includes delisted stocks)
- [ ] Transaction costs assumed: __ bps per trade
- [ ] Slippage assumed: __ bps per trade
- [ ] Liquidity filter: min avg volume __ shares/day
- [ ] In-sample period: [date range]
- [ ] Out-of-sample period: [date range] (required before live use)
- [ ] Minimum sample size: __ trades (min 30 recommended)
- [ ] Parameter stability: sensitivity tested ±20% from each parameter
- [ ] Regime segmentation: results broken out by bull/bear/neutral
- [ ] False discovery risk: is this one of many tested configurations?
- [ ] Recommendation: PAPER ONLY until out-of-sample validates
```

### 12.2 `edge-strategy-reviewer`

**Current state:** 5-category deterministic scoring (completeness, evidence quality, risk controls, operationality, testability). Does not include an overfitting/lookahead category.

**Risk:** A strategy draft can score PASS without any lookahead check or out-of-sample requirement.

**Required addition (Phase 7):** Add `research_quality` as a required scoring category checking for no-lookahead, out-of-sample plan, and survivorship bias acknowledgment.

### 12.3 `edge-strategy-designer`

**Current state:** Converts edge concepts into strategy drafts. No constraint on parameter count relative to sample size.

**Risk:** Complex strategies with many parameters can be generated without Bonferroni correction or holdout set requirements.

### 12.4 `vcp-screener` Tunable Parameters

**Current state:** 13 tunable parameters exposed via CLI flags. The scoring system can be tuned to overfit historical data.

**Risk:** Users can back-test with different parameter combinations until they find one that works historically — classic overfitting.

**Required addition (Phase 7):** Add parameter stability warning to SKILL.md; recommend walk-forward validation.

### 12.5 `canslim-screener`, `pead-screener`, `earnings-trade-analyzer`

All score candidates against thresholds that were derived from historical research. No explicit acknowledgment that:
- The scoring weights may not hold in different market regimes
- The sample period used to calibrate may not be representative
- Back-testing the screener output against the same period it was calibrated on is hindsight bias

---

## 13. Missing Tests and Validators

### 13.1 Tests Present

The repository has 462 Python files in scripts directories and a `conftest.py` at root. The following have explicit test directories:
- `kanchi-dividend-sop/scripts/tests`
- `exposure-coach/scripts/tests`
- `macro-regime-detector/scripts/tests`
- `kanchi-dividend-review-monitor/scripts/tests`
- `institutional-flow-tracker/scripts/tests`
- `earnings-trade-analyzer/scripts/tests`
- `edge-strategy-designer/scripts/tests`
- `stanley-druckenmiller-investment/scripts/tests`
- `parabolic-short-trade-planner/scripts/tests`
- `edge-pipeline-orchestrator/scripts/tests`
- `scripts/tests/` — orchestrator and generator tests

### 13.2 Missing Tests

| Gap | Priority |
|---|---|
| Schema validation tests (Pydantic/dataclass round-trips) | HIGH (Phase 2) |
| `DataGap` protocol compliance tests per skill | HIGH (Phase 6) |
| Workflow artifact chain validation (schema_id linkage) | HIGH (Phase 4) |
| `validate_skills_index.py --strict` passes with all 54 skills | HIGH (run now) |
| No execution language in SKILL.md files | MEDIUM (Phase 14) |
| Filename convention tests for artifact outputs | MEDIUM (Phase 14) |
| Skill package hash freshness vs. source | MEDIUM (Phase 12) |
| `BacktestSpec` no-lookahead checklist required fields | HIGH (Phase 7) |
| `TradePlan` required fields (stop, target, R/R, size) | HIGH (Phase 8) |
| `PostmortemReport` process × outcome classification | MEDIUM (Phase 9) |
| Journal entry schema round-trip | MEDIUM (Phase 9) |
| `WorkflowRun` artifact serialization | MEDIUM (Phase 13) |
| Portfolio review disclaimer presence | MEDIUM (Phase 10) |

### 13.3 Validators Missing

| Validator | Status |
|---|---|
| `validate_skills_index.py --strict` | Exists; run status unknown |
| Workflow manifest validator (WF001-WF012) | Exists in `validate_skills_index.py` |
| Artifact schema ID validator | Does not exist |
| Data gap protocol presence checker | Does not exist |
| Execution language scanner (no "buy now" / "place order") | Does not exist |
| Backtest checklist completeness checker | Does not exist |
| Skill package freshness checker | Does not exist |
| Docs completeness (pre-commit hook) | Exists (`docs-completeness` hook) |
| No-absolute-paths checker | Exists |
| SKILL.md frontmatter checker | Exists (`skill-frontmatter` hook) |

---

## 14. Prioritized Hardening Plan

Work should proceed in the order below. Each phase produces independently useful artifacts.

### Phase 2 — Canonical Artifact Schemas (HIGH IMPACT, BLOCKING)

**Why first:** All other phases depend on having typed artifact definitions. Without schemas, contract validation (Phase 4) and data gap enforcement (Phase 6) cannot be implemented.

**Deliverables:**
- `schemas/artifacts.py` — Pydantic models or dataclasses for all ~25 artifact types
- `schemas/export_json_schemas.py` — exports JSON Schema files to `schemas/json/`
- Each model includes: `schema_version`, `artifact_id`, `created_at`, `skill_id`, `workflow_id`, `symbols`, `data_sources_used`, `data_gaps`, `assumptions`, `confidence`, `manual_review_required`, `next_actions`, `disclaimer`

**Estimated effort:** 2-3 days

### Phase 6 — Data Gap Protocol (HIGH IMPACT)

**Why second:** Data gaps are a fundamental correctness issue. Silent neutral conclusions undermine the entire decision-support premise.

**Deliverables:**
- `docs/dev/data-gap-protocol.md` — 10 gap scenarios, severity levels, remediation steps
- `schemas/data_gap.py` — `DataGap` and `DataQualityReport` models
- Update top-5 production skills to emit `DataGap` records

**Estimated effort:** 1-2 days

### Phase 8 — Trade Planning Quality Gates (HIGH IMPACT for primary use case)

**Why third:** The swing-opportunity-daily workflow is the primary daily use case. Hardening trade plan output directly improves the most-used path.

**Deliverables:**
- `ScreenCandidate` and `TradePlan` schemas from Phase 2 populated
- Update `vcp-screener`, `breakout-trade-planner`, `position-sizer` to emit structured output
- Add quality gate checklist to SKILL.md for each trade planning skill
- Remove any "buy now" language

**Estimated effort:** 3-4 days

### Phase 4 — Workflow Contract Validation (MEDIUM IMPACT)

**Why fourth:** Once schemas exist, the validator can enforce typed artifact contracts.

**Deliverables:**
- Add `schema_id` field to workflow artifact definitions
- Update `validate_skills_index.py` to check `schema_id` against `schemas/artifacts.py`
- New validator error codes WF013–WF020

**Estimated effort:** 1-2 days

### Phase 7 — Backtest and Research Quality (HIGH IMPACT for research path)

**Why fifth:** Strategy research path is currently weakest on overfitting guards.

**Deliverables:**
- Mandatory `BacktestSpec` and `BacktestReport` schemas
- Mandatory no-lookahead checklist in `backtest-expert/SKILL.md`
- `research_quality` scoring category in `edge-strategy-reviewer`
- "Paper only until validated" language in all research skills

**Estimated effort:** 2-3 days

### Phase 9 — Trader Memory and Postmortem (MEDIUM IMPACT)

**Deliverables:**
- Extended lifecycle states (IDEA → CANDIDATE → PLANNED → ENTERED → MANAGED → EXITED → POSTMORTEM_DONE → ARCHIVED)
- `TradeThesis`, `JournalEntry`, `PostmortemReport` Pydantic models
- 2×2 postmortem classification (process quality × outcome quality)
- Journal schema tests

**Estimated effort:** 2-3 days

### Phase 3 — Structured Output for Core Skills (MEDIUM IMPACT)

**Deliverables:**
- JSON output wrapper for all prose-only skills in production workflows
- `decision_support_only` disclaimer field in every artifact
- Data gap behavior documented in each SKILL.md

**Estimated effort:** 3-4 days

### Phase 13 — Local Workflow Runner (MEDIUM IMPACT)

**Deliverables:**
- `scripts/workflow_runner.py` with list/validate/start/status commands
- `WorkflowRun` artifact saved to `state/workflow-runs/`
- No trade execution capability

**Estimated effort:** 2-3 days

### Phase 5 — Skill Index Hardening (LOW IMPACT, CLEANUP)

**Deliverables:**
- Add `artifact_schema_ids` to `skills-index.yaml` skill entries
- `validate_skills_index.py --strict` checks artifact schema references
- Stale package detection

**Estimated effort:** 1 day

### Phases 10, 11, 12, 14, 15 — Portfolio, Docs, Packages, Tests, Final

Proceed after the above phases are stable.

---

## Appendix A — Skills Count by Category

| Category | Count | Production |
|---|---|---|
| market-regime | 11 | 11 |
| core-portfolio | 7 | 7 |
| swing-opportunity | 8 | 8 |
| trade-planning | 4 | 4 |
| trade-memory | 5 | 5 |
| strategy-research | 9 | 9 |
| advanced-satellite | 3 | 3 |
| meta | 11 | 11 |
| **Total** | **54** | **54** |

Note: `macro-regime-detector` and a few others serve dual categories.

## Appendix B — Current Validator Status

Run to verify current state:
```bash
python scripts/validate_skills_index.py --strict-metadata --strict-workflows
```

Known gaps that will fail `--strict-metadata`:
- Skills missing `timeframe` or `difficulty` (filled in 2026-05-12 per PROJECT_VISION.md)
- Skills missing `inputs` or `outputs` list entries

Run to check docs completeness:
```bash
python scripts/generate_skill_docs.py --overwrite
pre-commit run docs-completeness --all-files
```

## Appendix C — Disclaimer (Canonical)

The following disclaimer text should appear in all structured artifact outputs as `disclaimer.text`:

> "This artifact is produced by TraderMonty, a decision-support and trading-process toolkit. It is NOT financial advice, investment advisory, a trading signal, or a guarantee of profitability. All trading decisions, position sizing, risk management, and broker execution decisions remain solely the user's responsibility. Review all outputs manually before acting."
