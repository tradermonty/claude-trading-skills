---
layout: default
title: "Edge Concept Synthesizer"
grand_parent: English
parent: Skill Guides
nav_order: 23
lang_peer: /ja/skills/edge-concept-synthesizer/
permalink: /en/skills/edge-concept-synthesizer/
---

# Edge Concept Synthesizer
{: .no_toc }

Abstract detector tickets and hints into reusable edge concepts with thesis, invalidation signals, and strategy playbooks before strategy design/export.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-concept-synthesizer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-concept-synthesizer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Create an abstraction layer between detection and strategy implementation.
This skill clusters ticket evidence, summarizes recurring conditions, and outputs `edge_concepts.yaml` with explicit thesis and invalidation logic.

---

## 2. When to Use

- You have many raw tickets and need mechanism-level structure.
- You want to avoid direct ticket-to-strategy overfitting.
- You need concept-level review before strategy drafting.

---

## 3. Prerequisites

- Python 3.9+
- `PyYAML`
- Ticket YAML directory from detector output (`tickets/exportable`, `tickets/research_only`)
- Optional `hints.yaml`

---

## 4. Quick Start

1. Collect ticket YAML files from auto-detection output.
2. Optionally provide `hints.yaml` for context matching.
3. Run `scripts/synthesize_edge_concepts.py`.
4. Deduplicate concepts: merge same-hypothesis concepts with overlapping conditions (containment > threshold).
5. Review concepts and promote only high-support concepts into strategy drafting.

---

## 5. Workflow

1. Collect ticket YAML files from auto-detection output.
2. Optionally provide `hints.yaml` for context matching.
3. Run `scripts/synthesize_edge_concepts.py`.
4. Deduplicate concepts: merge same-hypothesis concepts with overlapping conditions (containment > threshold).
5. Review concepts and promote only high-support concepts into strategy drafting.

---

## 6. Resources

**References:**

- `skills/edge-concept-synthesizer/references/concept_schema.md`

**Scripts:**

- `skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py`
