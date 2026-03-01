# Revision Loop Rules

## Overview

The review-revision feedback loop ensures strategy drafts meet quality standards
before export. Drafts cycle through review and optional revision up to a maximum
number of iterations.

## Verdict Categories

| Verdict | Meaning                                      | Next Action                  |
|---------|----------------------------------------------|------------------------------|
| PASS    | Draft meets quality standards                | Accumulated; eligible for export |
| REJECT  | Draft has fundamental flaws                  | Accumulated; no further action   |
| REVISE  | Draft needs specific improvements            | Apply revisions, re-review       |

## Loop Mechanics

1. All drafts enter the first review iteration (iter 0).
2. After each review:
   - PASS drafts are accumulated in the passed list (never re-reviewed).
   - REJECT drafts are accumulated in the rejected list (never re-reviewed).
   - REVISE drafts proceed to the revision stage.
3. Revised drafts re-enter the review stage for the next iteration.
4. After `max_review_iterations` (default: 2), any remaining REVISE drafts are
   downgraded to `research_probe` variant and marked not export-ready.

## Accumulation Rules

- PASS and REJECT lists are append-only across iterations.
- A draft that PASSed in iteration 0 remains passed even if iteration 1 runs.
- A draft that was REJECTed in iteration 0 is never revisited.
- Only REVISE drafts flow into the next iteration.

## Revision Heuristics (apply_revisions)

When a draft receives REVISE verdict with revision instructions:

| Instruction Pattern             | Action                                          |
|---------------------------------|-------------------------------------------------|
| "Reduce entry conditions"       | Keep only the first 5 entry conditions           |
| "Add volume filter"             | Append "avg_volume > 500000" to conditions       |
| "Round precise thresholds"      | Round decimal numbers in conditions to integers  |

After revision:
- `variant` remains unchanged
- `export_ready_v1` remains unchanged

## Downgrade Rules (downgrade_to_research_probe)

When a REVISE draft exhausts all iterations:
- Set `variant` = "research_probe"
- Set `export_ready_v1` = False
- Record draft_id in the downgraded list

## Export Eligibility

A draft is eligible for export when ALL conditions are met:
1. Verdict is PASS
2. `export_ready_v1` is True
3. `entry_family` is in EXPORTABLE_FAMILIES (pivot_breakout, gap_up_continuation)

## Ticket Generation for Export

- **Pre-generated tickets**: The designer stage can write exportable ticket YAMLs
  to `--exportable-tickets-dir`. These are preferred when available.
- **Revised draft tickets**: If a draft was revised (no pre-generated ticket),
  `build_export_ticket()` generates a ticket from the draft data.
- Export uses `--ticket PATH --strategies-dir DIR` CLI interface.
