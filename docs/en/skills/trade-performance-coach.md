---
layout: default
title: "Trade Performance Coach"
grand_parent: English
parent: Skill Guides
nav_order: 61
lang_peer: /ja/skills/trade-performance-coach/
permalink: /en/skills/trade-performance-coach/
generated: true
---

# Trade Performance Coach
{: .no_toc }

Review closed trades, partial exits, and monthly trade aggregates for process adherence, risk discipline, execution quality, and evidence-based trading behavior patterns. Use after trader-memory-core and signal-postmortem have produced records, or when the user asks for a post-trade coach, risk-manager style review, rule-adherence review, next-session operating rules, or psychology-aware trading behavior feedback. This skill does not provide buy/sell advice, therapy, or broker execution.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/trade-performance-coach.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/trade-performance-coach){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Trade Performance Coach reviews recorded trade outcomes and journal evidence to
help a human trader improve their decision process. It converts closed-trade
records, postmortem findings, risk rules, and optional market-regime context into
an evidence-based coaching report covering:

- process adherence
- risk discipline
- execution quality
- possible trading-behavior patterns
- next-session operating rules
- coach questions for reflection

This skill is intended to fill the support role that a risk manager, desk lead,
or trading coach might provide in a professional trading environment. It is
strictly a process-review skill: it never recommends entering, exiting, buying,
selling, shorting, holding, or sizing a specific security.

---

## 2. When to Use

Use this skill when any of the following are true:

- A trade has been closed and the user wants a post-trade coaching review.
- A partial close occurred and the user wants to inspect sizing, stop, or exit behavior.
- The user has `trader-memory-core` thesis records and `signal-postmortem` findings and wants next-session operating rules.
- The user wants a monthly review of recurring process, risk, execution, or behavior patterns.
- The user asks for a risk-manager style review of their own recorded trades.
- The user asks whether a loss was a process error, execution error, market environment issue, or acceptable variance.
- The user wants possible FOMO, revenge-trade, overconfidence, hesitation, stop-moving, or size-creep patterns flagged with evidence.

---

## 3. Prerequisites

Recommended upstream records:

- `trader-memory-core` closed thesis record or journal entry
- `signal-postmortem` postmortem findings
- original trade plan or trade ticket
- actual entry / exit / partial-close actions
- user-defined risk plan, if available
- optional `market-regime-daily` / `exposure-coach` context

No paid API key is required. The deterministic script works from local JSON/YAML-like records.

---

## 4. Quick Start

```bash
python3 skills/trade-performance-coach/scripts/review_trade_performance.py \
  --input reports/trade_memory/closed_thesis_EXMPL.json \
  --output-dir reports/trade-performance-coach
```

---

## 5. Workflow

### Step 1 — Collect source records

Collect the most recent closed trade record, postmortem, risk plan, and journal notes.

```bash
python3 skills/trade-performance-coach/scripts/review_trade_performance.py \
  --input reports/trade_memory/closed_thesis_EXMPL.json \
  --output-dir reports/trade-performance-coach
```

### Step 2 — Evaluate process adherence

Compare actual actions against the user's documented plan and rules. Check for:

- missing pre-entry thesis
- setup confirmation skipped
- trade taken against market-regime gate
- stop moved without a pre-defined rule
- exit / partial close inconsistent with plan
- incomplete record quality

### Step 3 — Evaluate risk discipline

Compare actual risk and heat against the risk plan. Check for:

- per-trade risk above max
- portfolio heat above max
- weekly loss or consecutive-loss escalation
- oversized trade after a winner or loser
- correlated exposure if provided

### Step 4 — Evaluate execution quality

Classify entry, stop, exit, add, trim, and review behavior. Separate clean-process losses from execution mistakes.

### Step 5 — Detect possible behavior patterns

Use evidence from journal notes and action flags to tag possible trading behavior patterns. Always tie a tag to evidence and use non-diagnostic language.

Supported MVP tags:

- `fomo_entry`
- `revenge_trade`
- `premature_exit`
- `overconfidence_after_winner`
- `stop_moved`
- `size_creep`
- `hesitation`
- `rule_drift`
- `no_pattern_detected`

### Step 6 — Produce next-session operating rules

Convert findings into temporary, concrete guardrails. Examples:

- require thesis record and screenshot before the next entry
- cap risk at 0.5R for the next two trades after a rule violation
- switch to review-only mode after repeated revenge-trade evidence
- do not chase a missed entry; add to watchlist for the next valid setup

### Step 7 — Human decision gate

End every report with a human decision gate. The default action is `journal_only`.

Allowed actions:

```text
accept_rules / modify_rules / defer / journal_only
```

---

## 6. Resources

**References:**

- `skills/trade-performance-coach/references/behavior-tags.md`
- `skills/trade-performance-coach/references/hermes-integration.md`
- `skills/trade-performance-coach/references/output-contract.md`
- `skills/trade-performance-coach/references/review-framework.md`
- `skills/trade-performance-coach/references/risk-review-checklist.md`

**Scripts:**

- `skills/trade-performance-coach/scripts/review_trade_performance.py`
