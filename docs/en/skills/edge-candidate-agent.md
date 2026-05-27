---
layout: default
title: "Edge Candidate Agent"
grand_parent: English
parent: Skill Guides
nav_order: 22
lang_peer: /ja/skills/edge-candidate-agent/
permalink: /en/skills/edge-candidate-agent/
---

# Edge Candidate Agent
{: .no_toc }

Generate and prioritize US equity long-side edge research tickets from EOD observations, then export pipeline-ready candidate specs for trade-strategy-pipeline Phase I. Use when users ask to turn hypotheses/anomalies into reproducible research tickets, convert validated ideas into `strategy.yaml` + `metadata.json`, or preflight-check interface compatibility (`edge-finder-candidate/v1`) before running pipeline backtests.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span> <span class="badge badge-optional">FMP Optional</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-candidate-agent.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-candidate-agent){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Convert daily market observations into reproducible research tickets and Phase I-compatible candidate specs.
Prioritize signal quality and interface compatibility over aggressive strategy proliferation.
This skill can run end-to-end standalone, but in the split workflow it primarily serves the final export/validation stage.

---

## 2. When to Use

- Convert market observations, anomalies, or hypotheses into structured research tickets.
- Run daily auto-detection to discover new edge candidates from EOD OHLCV and optional hints.
- Export validated tickets as `strategy.yaml` + `metadata.json` for `trade-strategy-pipeline` Phase I.
- Run preflight compatibility checks for `edge-finder-candidate/v1` before pipeline execution.

---

## 3. Prerequisites

- Python 3.9+ with `PyYAML` installed.
- Access to the target `trade-strategy-pipeline` repository for schema/stage validation.
- `uv` available when running pipeline-managed validation via `--pipeline-root`.

---

## 4. Quick Start

Recommended split workflow:

1. `skills/edge-hint-extractor`: observations/news -> `hints.yaml`
2. `skills/edge-concept-synthesizer`: tickets/hints -> `edge_concepts.yaml`
3. `skills/edge-strategy-designer`: concepts -> `strategy_drafts` + exportable ticket YAML
4. `skills/edge-candidate-agent` (this skill): export + validate for pipeline handoff

---

## 5. Workflow

Recommended split workflow:

1. `skills/edge-hint-extractor`: observations/news -> `hints.yaml`
2. `skills/edge-concept-synthesizer`: tickets/hints -> `edge_concepts.yaml`
3. `skills/edge-strategy-designer`: concepts -> `strategy_drafts` + exportable ticket YAML
4. `skills/edge-candidate-agent` (this skill): export + validate for pipeline handoff

---

## 6. Resources

**References:**

- `skills/edge-candidate-agent/references/ideation_loop.md`
- `skills/edge-candidate-agent/references/pipeline_if_v1.md`
- `skills/edge-candidate-agent/references/research_ticket_schema.md`
- `skills/edge-candidate-agent/references/signal_mapping.md`

**Scripts:**

- `skills/edge-candidate-agent/scripts/auto_detect_candidates.py`
- `skills/edge-candidate-agent/scripts/candidate_contract.py`
- `skills/edge-candidate-agent/scripts/export_candidate.py`
- `skills/edge-candidate-agent/scripts/validate_candidate.py`
