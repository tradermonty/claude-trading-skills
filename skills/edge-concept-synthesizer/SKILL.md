---
name: edge-concept-synthesizer
description: "Use when the user wants to create trading strategies from detector tickets, synthesize market edge concepts, group signal patterns into reusable templates, or prepare structured edge definitions before strategy design. Clusters raw detector tickets and optional hints into deduplicated edge concepts with thesis statements, invalidation signals, and export-readiness flags, outputting edge_concepts.yaml."
---

# Edge Concept Synthesizer

## Overview

Create an abstraction layer between detection and strategy implementation.
This skill clusters ticket evidence, summarizes recurring conditions, and outputs `edge_concepts.yaml` with explicit thesis and invalidation logic.

## When to Use

- You have many raw detector tickets and want to group them into reusable trading edge definitions.
- You want to synthesize market signals into structured concept templates before drafting strategies.
- You need to avoid direct ticket-to-strategy overfitting by adding a concept-level review step.
- You are building or refining an edge research pipeline and need concept clustering.

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
4. **Validate output:** Verify `edge_concepts.yaml` contains expected concept clusters, each with a non-empty `thesis` field and at least one invalidation signal. If any cluster has zero ticket support, investigate missing or malformed input tickets.
5. Deduplicate concepts: merge same-hypothesis concepts with overlapping conditions (containment > threshold).
6. **Error recovery:** If synthesis fails due to malformed YAML input, validate ticket files with `python3 -c "import yaml; yaml.safe_load(open('ticket.yaml'))"`. If insufficient ticket support produces empty output, lower `--min-ticket-support` or add `--promote-hints`.
7. Review concepts and promote only high-support concepts into strategy drafting.

## Quick Commands

```bash
python3 skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py \
  --tickets-dir /tmp/edge-auto/tickets \
  --hints /tmp/edge-hints/hints.yaml \
  --output /tmp/edge-concepts/edge_concepts.yaml \
  --min-ticket-support 2

# With hint promotion and synthetic cap
python3 skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py \
  --tickets-dir /tmp/edge-auto/tickets \
  --hints /tmp/edge-hints/hints.yaml \
  --output /tmp/edge-concepts/edge_concepts.yaml \
  --promote-hints \
  --max-synthetic-ratio 1.5

# With custom dedup threshold (or disable dedup)
python3 skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py \
  --tickets-dir /tmp/edge-auto/tickets \
  --output /tmp/edge-concepts/edge_concepts.yaml \
  --overlap-threshold 0.6

python3 skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py \
  --tickets-dir /tmp/edge-auto/tickets \
  --output /tmp/edge-concepts/edge_concepts.yaml \
  --no-dedup
```

## Resources

- `skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py`
- `references/concept_schema.md`
