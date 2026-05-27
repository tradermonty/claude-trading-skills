---
layout: default
title: "Edge Signal Aggregator"
grand_parent: English
parent: Skill Guides
nav_order: 26
lang_peer: /ja/skills/edge-signal-aggregator/
permalink: /en/skills/edge-signal-aggregator/
---

# Edge Signal Aggregator
{: .no_toc }

Aggregate and rank signals from multiple edge-finding skills (edge-candidate-agent, theme-detector, sector-analyst, institutional-flow-tracker) into a prioritized conviction dashboard with weighted scoring, deduplication, and contradiction detection.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-signal-aggregator.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-signal-aggregator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Combine outputs from multiple upstream edge-finding skills into a single weighted conviction dashboard. This skill applies configurable signal weights, deduplicates overlapping themes, flags contradictions between skills, and ranks composite edge ideas by aggregate confidence score. The result is a prioritized edge shortlist with provenance links to each contributing skill.

---

## 2. When to Use

- After running multiple edge-finding skills and wanting a unified view
- When consolidating signals from edge-candidate-agent, theme-detector, sector-analyst, and institutional-flow-tracker
- Before making portfolio allocation decisions based on multiple signal sources
- To identify contradictions between different analysis approaches
- When prioritizing which edge ideas deserve deeper research

---

## 3. Prerequisites

- Python 3.9+
- No API keys required (processes local JSON/YAML files from other skills)
- Dependencies: `pyyaml` (standard in most environments)

---

## 4. Quick Start

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --edge-concepts reports/edge_concepts_*.yaml \
  --themes reports/theme_detector_*.json \
  --sectors reports/sector_analyst_*.json \
  --institutional reports/institutional_flow_*.json \
  --hints reports/edge_hints_*.yaml \
  --output-dir reports/
```

---

## 5. Workflow

### Step 1: Gather Upstream Skill Outputs

Collect output files from the upstream skills you want to aggregate:
- `reports/edge_candidate_*.json` from edge-candidate-agent
- `reports/edge_concepts_*.yaml` from edge-concept-synthesizer
- `reports/theme_detector_*.json` from theme-detector
- `reports/sector_analyst_*.json` from sector-analyst
- `reports/institutional_flow_*.json` from institutional-flow-tracker
- `reports/edge_hints_*.yaml` from edge-hint-extractor

### Step 2: Run Signal Aggregation

Execute the aggregator script with paths to upstream outputs:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --edge-concepts reports/edge_concepts_*.yaml \
  --themes reports/theme_detector_*.json \
  --sectors reports/sector_analyst_*.json \
  --institutional reports/institutional_flow_*.json \
  --hints reports/edge_hints_*.yaml \
  --output-dir reports/
```

Optional: Use a custom weights configuration:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --weights-config skills/edge-signal-aggregator/assets/custom_weights.yaml \
  --output-dir reports/
```

### Step 3: Review Aggregated Dashboard

Open the generated report to review:
1. **Ranked Edge Ideas** - Sorted by composite conviction score
2. **Signal Provenance** - Which skills contributed to each idea
3. **Contradictions** - Conflicting signals flagged for manual review
4. **Deduplication Log** - Merged overlapping themes

### Step 4: Act on High-Conviction Signals

Filter the shortlist by minimum conviction threshold:

```bash
python3 skills/edge-signal-aggregator/scripts/aggregate_signals.py \
  --edge-candidates reports/edge_candidate_agent_*.json \
  --min-conviction 0.7 \
  --output-dir reports/
```

---

## 6. Resources

**References:**

- `skills/edge-signal-aggregator/references/signal-weighting-framework.md`

**Scripts:**

- `skills/edge-signal-aggregator/scripts/aggregate_signals.py`
