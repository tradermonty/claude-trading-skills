---
name: edge-concept-synthesizer
description: Abstract detector tickets and hints into reusable edge concepts with thesis, invalidation signals, and strategy playbooks before strategy design/export.
---

# Edge Concept Synthesizer

## Overview

Create an abstraction layer between detection and strategy implementation.
This skill clusters ticket evidence, summarizes recurring conditions, and outputs `edge_concepts.yaml` with explicit thesis and invalidation logic.

## When to Use

- You have many raw tickets and need mechanism-level structure.
- You want to avoid direct ticket-to-strategy overfitting.
- You need concept-level review before strategy drafting.

## Prerequisites

- Python 3.9+
- `PyYAML`
- Ticket YAML directory from detector output (`tickets/exportable`, `tickets/research_only`)
- Optional `hints.yaml`

## Output

- `edge_concepts.yaml` containing:
  - concept clusters
  - support statistics
  - abstract thesis
  - invalidation signals
  - export readiness flag

## Workflow

1. Collect ticket YAML files from auto-detection output.
2. Optionally provide `hints.yaml` for context matching.
3. Run `scripts/synthesize_edge_concepts.py`.
4. Review concepts and promote only high-support concepts into strategy drafting.

## Quick Commands

```bash
python3 skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py \
  --tickets-dir /tmp/edge-auto/tickets \
  --hints /tmp/edge-hints/hints.yaml \
  --output /tmp/edge-concepts/edge_concepts.yaml \
  --min-ticket-support 2
```

## Resources

- `skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py`
- `references/concept_schema.md`
