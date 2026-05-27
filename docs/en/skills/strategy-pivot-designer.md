---
layout: default
title: "Strategy Pivot Designer"
grand_parent: English
parent: Skill Guides
nav_order: 55
lang_peer: /ja/skills/strategy-pivot-designer/
permalink: /en/skills/strategy-pivot-designer/
---

# Strategy Pivot Designer
{: .no_toc }

Detect backtest iteration stagnation and generate structurally different strategy pivot proposals when parameter tuning reaches a local optimum.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/strategy-pivot-designer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/strategy-pivot-designer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Detect when a strategy's backtest iteration loop has stalled and propose structurally different strategy architectures. This skill acts as the feedback loop for the Edge pipeline (hint-extractor -> concept-synthesizer -> strategy-designer -> candidate-agent), breaking out of local optima by redesigning the strategy's skeleton rather than tweaking parameters.

---

## 2. When to Use

- Backtest scores have plateaued despite multiple refinement iterations.
- A strategy shows signs of overfitting (high in-sample, low robustness).
- Transaction costs defeat the strategy's thin edge.
- Tail risk or drawdown exceeds acceptable thresholds.
- You want to explore fundamentally different strategy architectures for the same market hypothesis.

---

## 3. Prerequisites

- Python 3.9+
- `PyYAML`
- Iteration history JSON (accumulated backtest-expert evaluations)
- Source strategy draft YAML (from edge-strategy-designer)

---

## 4. Quick Start

1. Accumulate backtest evaluation results into an iteration history file using `--append-eval`.
2. Run stagnation detection on the history to identify triggers (plateau, overfitting, cost defeat, tail risk).
3. If stagnation detected, generate pivot proposals using three techniques: assumption inversion, archetype switch, objective reframe.
4. Review ranked proposals (scored by quality potential + novelty).
5. For exportable proposals, ticket YAML is ready for edge-candidate-agent pipeline.
6. For research_only proposals, manual strategy design needed before pipeline integration.
7. Feed the selected pivot draft back into backtest-expert for the next iteration cycle.

---

## 5. Workflow

1. Accumulate backtest evaluation results into an iteration history file using `--append-eval`.
2. Run stagnation detection on the history to identify triggers (plateau, overfitting, cost defeat, tail risk).
3. If stagnation detected, generate pivot proposals using three techniques: assumption inversion, archetype switch, objective reframe.
4. Review ranked proposals (scored by quality potential + novelty).
5. For exportable proposals, ticket YAML is ready for edge-candidate-agent pipeline.
6. For research_only proposals, manual strategy design needed before pipeline integration.
7. Feed the selected pivot draft back into backtest-expert for the next iteration cycle.

---

## 6. Resources

**References:**

- `skills/strategy-pivot-designer/references/pivot_proposal_schema.md`
- `skills/strategy-pivot-designer/references/pivot_techniques.md`
- `skills/strategy-pivot-designer/references/stagnation_triggers.md`
- `skills/strategy-pivot-designer/references/strategy_archetypes.md`

**Scripts:**

- `skills/strategy-pivot-designer/scripts/detect_stagnation.py`
- `skills/strategy-pivot-designer/scripts/generate_pivots.py`
