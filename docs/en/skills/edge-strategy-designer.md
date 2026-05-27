---
layout: default
title: "Edge Strategy Designer"
grand_parent: English
parent: Skill Guides
nav_order: 27
lang_peer: /ja/skills/edge-strategy-designer/
permalink: /en/skills/edge-strategy-designer/
---

# Edge Strategy Designer
{: .no_toc }

Convert abstract edge concepts into strategy draft variants and optional exportable ticket YAMLs for edge-candidate-agent export/validation.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-strategy-designer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-strategy-designer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Translate concept-level hypotheses into concrete strategy draft specs.
This skill sits after concept synthesis and before pipeline export validation.

---

## 2. When to Use

- You have `edge_concepts.yaml` and need strategy candidates.
- You want multiple variants (core/conservative/research-probe) per concept.
- You want optional exportable ticket files for interface v1 families.

---

## 3. Prerequisites

- Python 3.9+
- `PyYAML`
- `edge_concepts.yaml` produced by concept synthesis

---

## 4. Quick Start

1. Load `edge_concepts.yaml`.
2. Choose risk profile (`conservative`, `balanced`, `aggressive`).
3. Generate per-concept variants with hypothesis-type exit calibration.
4. Apply `HYPOTHESIS_EXIT_OVERRIDES` to adjust stop-loss, reward-to-risk, time-stop, and trailing-stop per hypothesis type (breakout, earnings_drift, panic_reversal, etc.).
5. Clamp reward-to-risk at `RR_FLOOR=1.5` to prevent C5 review failures.
6. Export v1-ready ticket YAML when applicable.
7. Hand off exportable tickets to `skills/edge-candidate-agent/scripts/export_candidate.py`.

---

## 5. Workflow

1. Load `edge_concepts.yaml`.
2. Choose risk profile (`conservative`, `balanced`, `aggressive`).
3. Generate per-concept variants with hypothesis-type exit calibration.
4. Apply `HYPOTHESIS_EXIT_OVERRIDES` to adjust stop-loss, reward-to-risk, time-stop, and trailing-stop per hypothesis type (breakout, earnings_drift, panic_reversal, etc.).
5. Clamp reward-to-risk at `RR_FLOOR=1.5` to prevent C5 review failures.
6. Export v1-ready ticket YAML when applicable.
7. Hand off exportable tickets to `skills/edge-candidate-agent/scripts/export_candidate.py`.

---

## 6. Resources

**References:**

- `skills/edge-strategy-designer/references/strategy_draft_schema.md`

**Scripts:**

- `skills/edge-strategy-designer/scripts/design_strategy_drafts.py`
