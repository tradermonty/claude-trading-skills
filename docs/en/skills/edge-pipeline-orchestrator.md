---
layout: default
title: "Edge Pipeline Orchestrator"
grand_parent: English
parent: Skill Guides
nav_order: 25
lang_peer: /ja/skills/edge-pipeline-orchestrator/
permalink: /en/skills/edge-pipeline-orchestrator/
---

# Edge Pipeline Orchestrator
{: .no_toc }

Orchestrate the full edge research pipeline from candidate detection through strategy design, review, revision, and export. Use when coordinating multi-stage edge research workflows end-to-end.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-pipeline-orchestrator.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-pipeline-orchestrator){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Edge Pipeline Orchestrator

---

## 2. When to Use

- Run the full edge pipeline from tickets (or OHLCV) to exported strategies
- Resume a partially completed pipeline from the drafts stage
- Review and revise existing strategy drafts with feedback loop
- Dry-run the pipeline to preview results without exporting

---

## 3. Prerequisites

- Orchestrates edge pipeline subskills via subprocess
- Python 3.9+ recommended

---

## 4. Quick Start

```bash
# Full pipeline from tickets
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --tickets-dir /path/to/tickets/ \
  --market-summary /path/to/market_summary.json \
  --anomalies /path/to/anomalies.json \
  --output-dir reports/edge_pipeline/

# Review-only mode with existing drafts
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --review-only \
  --drafts-dir reports/edge_strategy_drafts/ \
  --output-dir reports/edge_pipeline/

# Dry-run (no export)
python3 skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py \
  --tickets-dir /path/to/tickets/ \
  --output-dir reports/edge_pipeline/ --dry-run
```

---

## 5. Workflow

1. Load pipeline configuration from CLI arguments
2. Run auto_detect stage if --from-ohlcv is provided (generates tickets from raw OHLCV data)
3. Run hints stage to extract edge hints from market summary and anomalies
4. Run concepts stage to synthesize abstract edge concepts from tickets and hints
5. Run drafts stage to design strategy drafts from concepts
6. Run review-revision feedback loop:
   - Review all drafts (max 2 iterations)
   - PASS verdicts accumulated; REJECT verdicts accumulated
   - REVISE verdicts trigger apply_revisions and re-review
   - Remaining REVISE after max iterations downgraded to research_probe
7. Export eligible drafts (PASS + export_ready_v1 + exportable entry_family)
8. Write pipeline_run_manifest.json with full execution trace

---

## 6. Resources

**References:**

- `skills/edge-pipeline-orchestrator/references/pipeline_flow.md`
- `skills/edge-pipeline-orchestrator/references/revision_loop_rules.md`

**Scripts:**

- `skills/edge-pipeline-orchestrator/scripts/orchestrate_edge_pipeline.py`
