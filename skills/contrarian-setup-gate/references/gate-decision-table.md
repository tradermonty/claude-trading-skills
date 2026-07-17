# Contrarian Setup Gate -- Decision Table

## Purpose

This gate combines three normalized states -- crowding (C), news failure (N), and price action (P) -- into one `setup_status` via SEQUENTIAL pipeline-order evaluation. Each of N and P is one of five states: `CONFIRMED`, `NOT_CONFIRMED`, `INSUFFICIENT`, `PENDING` (the report file was not provided), or `INVALID` (a report was provided but is unusable). C shares the same five states, except it is never `PENDING` -- the detector report is always required.

Each step is evaluated **in pipeline order** -- crowding, then news, then price-action -- and each step FULLY SETTLES (reaches a determination) before the next step's state is even inspected. This document is the authoritative spec the test suite (`scripts/tests/test_gate_logic.py`) checks against.

## Why sequential, not "any-X across both downstream steps" (v4, PR #249 P1-3)

An earlier design (v3) evaluated the two downstream steps AS A GROUP: "any provided N or P that is INVALID" was checked before "any N or P that is NOT_CONFIRMED," scanning both steps for each condition before moving to the next condition. That aggregation let a LATER step's problem soften an EARLIER step's definitive verdict -- e.g. news already NOT_CONFIRMED (a hard rejection) got downgraded to INSUFFICIENT_EVIDENCE merely because price-action's file happened to be corrupted, even though price-action was never going to be consulted once news had already rejected the setup. This is the same softening-principle violation already fixed twice elsewhere in this gate (the loader path in v1, the consistency path in v2/v3) -- now caught a third time, in cross-step aggregation, by an independent user review. The sequential model makes the principle structural: once a step settles, later steps simply aren't looked at for that decision.

## Precedence Rules

1. **Crowding, evaluated first and exclusively.**
   - C is `INVALID` or `INSUFFICIENT` -> `INSUFFICIENT_EVIDENCE`.
   - C is `NOT_CONFIRMED` (classification `NEUTRAL`) -> `REJECTED`, **regardless of N or P's state** -- N/P are never even inspected for this decision. N/P are still echoed in the `inputs` audit block, but never change this status.
   - C is `CONFIRMED` -> continue to step 2.
2. **News, evaluated next -- if provided (state != `PENDING`).** The same four-way settlement: `INVALID` -> `INSUFFICIENT_EVIDENCE`; `NOT_CONFIRMED` -> `REJECTED`; `INSUFFICIENT` -> `INSUFFICIENT_EVIDENCE`; `CONFIRMED` -> continue to step 3. **Price-action is not inspected at all until news has settled as `CONFIRMED`** (or is `PENDING`, handled by step 3's out-of-order case below).
3. **Price-action, evaluated last.** If news was `CONFIRMED`: the same four-way settlement on price-action, with `PENDING` -> `WATCHING_PRICE` and `CONFIRMED` -> `READY_FOR_PLAN`. **Out-of-order use** (price-action provided while news is still `PENDING`): price-action is still fully evaluated here with the same four-way settlement (`INVALID`/`NOT_CONFIRMED`/`INSUFFICIENT` resolve normally), but a `CONFIRMED` price-action caps the status at `CROWDED` with warning `out_of_order_price_action` instead of advancing to `READY_FOR_PLAN`, since news was never actually confirmed. If both news and price-action are `PENDING` -> `CROWDED` (crowding only).

Pipeline order therefore **refines**, rather than simply restates, "any explicit NOT_CONFIRMED rejects": a later step's `NOT_CONFIRMED` can be masked by an EARLIER step's own settlement first (see the symmetric pin below) -- each later step's validity is premised on the earlier ones having already passed, mirroring how technical-analyst itself refuses to run its own confirmation pass against a `NEUTRAL` (unconfirmed) detector.

## Full State Table

C has 5 reachable labels: `CROWDED_LONG` and `CROWDED_SHORT` (both `CONFIRMED`, differing only in fade direction), `NOT_CONFIRMED`, `INSUFFICIENT`, `INVALID`. N and P each have 5 reachable labels: `CONFIRMED`, `NOT_CONFIRMED`, `INSUFFICIENT`, `PENDING`, `INVALID`. All 125 combinations are exhaustively unit-tested; the table below collapses them by which step settles the decision.

| C state | N state | P state | Result |
|---|---|---|---|
| `INVALID` or `INSUFFICIENT` | any | any | `INSUFFICIENT_EVIDENCE` (step 1 only) |
| `NOT_CONFIRMED` | any | any | `REJECTED` (step 1 only) |
| `CONFIRMED` | `INVALID` | any | `INSUFFICIENT_EVIDENCE` (step 2; P never inspected) |
| `CONFIRMED` | `NOT_CONFIRMED` | any | `REJECTED` (step 2; P never inspected) |
| `CONFIRMED` | `INSUFFICIENT` | any | `INSUFFICIENT_EVIDENCE` (step 2; P never inspected) |
| `CONFIRMED` | `PENDING` | `INVALID` | `INSUFFICIENT_EVIDENCE` (step 3, out-of-order) |
| `CONFIRMED` | `PENDING` | `NOT_CONFIRMED` | `REJECTED` (step 3, out-of-order) |
| `CONFIRMED` | `PENDING` | `INSUFFICIENT` | `INSUFFICIENT_EVIDENCE` (step 3, out-of-order) |
| `CONFIRMED` | `PENDING` | `CONFIRMED` | `CROWDED` (+ `out_of_order_price_action` warning) |
| `CONFIRMED` | `PENDING` | `PENDING` | `CROWDED` |
| `CONFIRMED` | `CONFIRMED` | `INVALID` | `INSUFFICIENT_EVIDENCE` (step 3) |
| `CONFIRMED` | `CONFIRMED` | `NOT_CONFIRMED` | `REJECTED` (step 3) |
| `CONFIRMED` | `CONFIRMED` | `INSUFFICIENT` | `INSUFFICIENT_EVIDENCE` (step 3) |
| `CONFIRMED` | `CONFIRMED` | `PENDING` | `WATCHING_PRICE` |
| `CONFIRMED` | `CONFIRMED` | `CONFIRMED` | `READY_FOR_PLAN` |

## Named Precedence Pins

These specific combinations are individually pinned in the test suite because they resolve an ambiguity a naive implementation could get wrong:

- **C=`NOT_CONFIRMED` + N=`INVALID` (unreadable)** -> `REJECTED`. Crowding's own conclusion is never softened by a corrupted downstream file.
- **C=`NOT_CONFIRMED` + N=`INVALID` (symbol_mismatch)** -> `REJECTED`. A consistency-check failure is a PER-INPUT `INVALID`, never a global override -- it cannot soften crowding's own conclusion either.
- **C=`NOT_CONFIRMED` + P=`NOT_CONFIRMED`** -> `REJECTED`, with crowding named as the rejector (not price action).
- **C=`INVALID` + N=`NOT_CONFIRMED`** -> `INSUFFICIENT_EVIDENCE` (step 1 settles before N is even inspected).
- **C=`INSUFFICIENT` + N=`NOT_CONFIRMED`** -> `INSUFFICIENT_EVIDENCE` (same).
- **C=`CONFIRMED` + N=`INVALID` + P=`NOT_CONFIRMED`** -> `INSUFFICIENT_EVIDENCE` (news settles at step 2; price is never reached).
- **C=`CONFIRMED` + N=`NOT_CONFIRMED` + P=`INSUFFICIENT`** -> `REJECTED` (news settles at step 2; price is never reached).
- **C=`CONFIRMED` + N=`NOT_CONFIRMED` + P=`INVALID`(unreadable/binary)** -> `REJECTED`, **not** `INSUFFICIENT_EVIDENCE` (v4, PR #249 P1-3 -- this is the exact combination the v3 aggregate rule got wrong: news's definitive rejection at step 2 means price-action's corruption at step 3 is never even inspected).
- **Symmetric case: C=`CONFIRMED` + N=`INSUFFICIENT` + P=`NOT_CONFIRMED`** -> `INSUFFICIENT_EVIDENCE`, **not** `REJECTED` (news settles first as INSUFFICIENT; price's NOT_CONFIRMED is never reached).
- **Out-of-order P without N, P `CONFIRMED`** -> `CROWDED` + warning.
- **Out-of-order P without N, P `NOT_CONFIRMED`** -> `REJECTED` (price-action is still fully evaluated in the out-of-order branch -- out-of-order capping only applies to a `CONFIRMED` price-action).

## Cross-Input Consistency (PER-INPUT INVALID)

A consistency failure marks the **exhibiting input** `INVALID` with a named reason and flows into the precedence rules above exactly like a loader failure -- it is never a global override.

- `symbol` in a provided news or price-action report that does not match `--symbol` -> that input `INVALID` (`news_symbol_mismatch` / `price_action_symbol_mismatch`). For the detector, `--symbol` simply not being found in `markets[]` is the existing `INSUFFICIENT` path (`detector_missing_symbol`), not a mismatch.
- `direction` in a provided news or price-action report that does not equal the detector's `classification` -> that input `INVALID` (`news_direction_mismatch` / `price_action_direction_mismatch`). Evaluated **only** when the detector row itself is usable (crowding state `CONFIRMED`) -- an unusable detector has no classification to compare against. A `direction` value of `null` is never treated as a mismatch: it is the report's own upstream fail-closed exit (e.g. NRF's `no_direction_provided`), so it normalizes to `INSUFFICIENT` with that upstream `verdict_reason` when present, or `<input>_malformed` when it is not -- comparing `null` against the detector's classification would otherwise always be unequal and misreport a legitimate upstream insufficiency as a mismatch.
- A missing `direction` key in a provided news or price-action report -> `<input>_malformed` (a required key, checked alongside `symbol`/`verdict`/`confidence`).
- `schema_version` outside major version `1` -> that input `INVALID` (`<input>_schema_unsupported`). Read locations differ per input: the detector and news reports carry `schema_version` at the **top level**; the price-action report carries it **only** at `run_context.schema_version` -- there is no top-level key on that report, so reading the top level there would silently disable the check.
- Duplicate `symbol` rows in the detector's `markets[]` -> the **first** match wins (the same `next()` pattern the detector itself uses internally).

## Reason-Token Glossary

### Crowding (cot-contrarian-detector)

| Reason | State | Meaning |
|---|---|---|
| `detector_unreadable` | INVALID | File missing, unreadable, or not valid UTF-8 |
| `detector_parse_error` | INVALID | File read but is not valid JSON |
| `detector_non_finite` | INVALID | Valid JSON, but the parsed structure contains a non-finite float (`inf`/`-inf`/`nan`) SOMEWHERE, at any depth, in any field -- including a syntactically valid JSON number that overflows to `inf` on parse (e.g. `1e309`), and the bare `Infinity`/`-Infinity`/`NaN` literals `json.loads` accepts by default as a non-standard extension. Detected by a whole-file iterative scan in the CLI's `load_json_file`, BEFORE the data is ever handed to `normalize_crowding` -- not scoped to fields the gate reads. See "Why the non-finite scan is whole-file" below (PR #249 user-review round 3) |
| `detector_malformed` | INVALID | Valid JSON but the top level is not an object |
| `detector_schema_unsupported` | INVALID | `schema_version` major is not `1` |
| `detector_missing_symbol` | INSUFFICIENT | Symbol absent from `markets[]`, or present in `skipped[]` |
| `detector_missing_data_date` | INVALID | `run_context.data_date` missing or empty |
| `detector_invalid_data_date` | INVALID | `data_date` not a string, or unparsable |
| `detector_future_data_date` | INVALID | `data_date` is after `--as-of` |
| `detector_json_stale` | INVALID | `data_date` age exceeds `--max-detector-age-days` |
| `detector_unknown_classification` | INVALID | `classification` is not a string, or is a string not one of `CROWDED_LONG` / `CROWDED_SHORT` / `NEUTRAL`. Type-checked before the allowlist membership test -- an unhashable value (a JSON list/dict) would otherwise crash that check instead of failing closed (PR #249 P1-1) |
| `detector_not_crowded` | NOT_CONFIRMED | `classification` is `NEUTRAL` -- measurably not crowded, an explicit negative |

### News Failure (news-reaction-failure-analyzer) and Price Action (technical-analyst)

Both reports share the same reason-token shape, prefixed `news_` / `price_action_` respectively:

| Reason (news / price_action) | State | Meaning |
|---|---|---|
| `_unreadable` | INVALID | File missing, unreadable, or not valid UTF-8 |
| `_parse_error` | INVALID | File read but is not valid JSON |
| `_non_finite` | INVALID | Valid JSON, but a non-finite float exists somewhere in the parsed structure -- same whole-file scan as `detector_non_finite` above, run before this report's data reaches `normalize_news` / `normalize_price_action` |
| `_malformed` | INVALID | Top level is not an object; `symbol`/`direction`/`verdict`/`confidence` is missing; `direction` is present but neither `null` nor a string; or `verdict`/`confidence` is present but not a string (a JSON list/dict/number/bool/`null` where a string is required) |
| `_symbol_mismatch` | INVALID | Report's `symbol` does not equal `--symbol` |
| `_schema_unsupported` | INVALID | `schema_version` major is not `1` |
| `_direction_mismatch` | INVALID | Report's `direction` is a non-null string that does not equal the detector's `classification` (checked only when crowding is usable). A `null` `direction` is never a mismatch -- see "Cross-Input Consistency" above. A non-string, non-null `direction` is `_malformed`, not a mismatch (PR #249 P1-1) |
| `_missing_as_of` | INVALID | `run_context.as_of` missing or empty |
| `_invalid_as_of` | INVALID | `as_of` not a string, or unparsable |
| `_future_as_of` | INVALID | `as_of` is after `--as-of` |
| `_json_stale` | INVALID | `as_of` age exceeds `--max-report-age-days` |
| `_unknown_verdict` | INVALID | `verdict` is a string but not one of the three known values for that report type. (A non-string `verdict` is `_malformed` instead, checked first -- `verdict not in valid_verdicts` requires a hashable operand, so type-checking first avoids a crash on an unhashable value like a JSON list; PR #249 P1-1, the reported repro) |
| `_unknown_confidence` | INVALID | `confidence` is a string but not one of `HIGH` / `MEDIUM` / `LOW`. Same type-check-first pattern as `_unknown_verdict` (PR #249 P1-1/P1-2 -- an unvalidated confidence used to reach `gate_confidence` in the output verbatim, e.g. `"BANANA"`). `LOW` is accepted: both upstreams document it as a reserved token they never actually emit, ranked weakest in `gate_confidence`'s weakest-link computation |
| (upstream `verdict_reason`) | NOT_CONFIRMED / INSUFFICIENT | The upstream report's own `verdict_reason` is carried through unchanged (e.g. `no_reversal_evidence`, `no_usable_events`) |

### Price-Action's CONFIRMED path: two more checks, and an asymmetry with news

`price_action_missing_stop_reference` (INVALID) fires when `verdict` is `CONFIRMED` but neither `handoff.price_action.stop_reference` nor the top-level `swing_levels.stop_reference` provided any non-null value. `price_action_invalid_stop_reference` (INVALID) fires when a source DID provide an explicit, non-null value that is unusable: not an `int`/`float`, a JSON boolean (`isinstance(True, int)` is `True` in Python, so a bare `true` must be excluded explicitly), zero, or negative (PR #249 user-review round 2, P1-B). A non-finite value (`Infinity`/`-Infinity`/`NaN`, including a syntactically valid JSON number like `1e309` that overflows to `inf` on parse) never reaches this check at all as of round 3 -- see "Why the non-finite scan is whole-file" below; it is caught earlier, at load time, as `price_action_non_finite`. An explicit-but-invalid value in `handoff.price_action.stop_reference` does **not** fall back to `swing_levels.stop_reference` -- an explicit garbage value is a real report bug, not an absence to paper over; the fallback is for when `handoff` provides no value at all.

`price_action_unknown_reason` (INVALID) and a stricter `price_action_malformed` fire on the CONFIRMED path's `verdict_reason`: a non-string or empty value is `price_action_malformed`; a well-typed string outside `{key_reversal, failed_extreme, failed_breakout}` (technical-analyst's `weekly_price_action.CHECK_REASON_MAP` values -- pinned by a cross-skill consistency test that imports TA's own source, so upstream drift there is caught, not silently trusted) is `price_action_unknown_reason` (PR #249 user-review round 2, P1-A). This is an intentional **asymmetry with news**: news's `verdict_reason` stays type-checked-but-display-only (a non-string value degrades to a generic fallback token, never rejects the input) because NRF's reason vocabulary is open-ended and the gate never *acts* on it. Price-action's CONFIRMED `verdict_reason` is different -- it feeds directly into `entry_trigger`, part of the actionable `READY_FOR_PLAN` output -- so it is allowlisted against TA's actual contract rather than merely type-checked.

**`READY_FOR_PLAN` invariant:** whenever `setup_status` is `READY_FOR_PLAN`, `entry_trigger` is guaranteed to be a non-empty string and `invalidation_level` is guaranteed to be a finite, positive number. This is enforced twice: primarily by `normalize_price_action`'s CONFIRMED-path validation above (which can never return `CONFIRMED` without both being valid), and defensively by an assertion inside `build_gate_result` itself, as a second independent guard against a future regression.

### Why the non-finite scan is whole-file, not field-scoped

`gate_logic.normalize_*` intentionally echoes some raw-but-invalid values verbatim into a `NormalizedInput` for audit transparency -- e.g. an unknown `classification` is still stored so the written report shows exactly what bad value was present. The CLI's JSON writer also uses `json.dumps(..., allow_nan=False)` as a defense against ever emitting a non-standard `Infinity`/`-Infinity`/`NaN` token. Those two design choices collided in a real regression (PR #249 user-review round 3): `classification: 1e309` parses to Python's `inf`, normalizes correctly to `detector_unknown_classification` -- but that INVALID `NormalizedInput` still echoed the raw `inf` value, and writing the report then crashed on `allow_nan=False` with `ValueError`, breaking the exit-0-always-writes-a-report contract on a code path entirely different from the one that determined the input was bad.

The fix is a whole-file scan (`run_contrarian_setup_gate.py`'s `_contains_non_finite`, called from `load_json_file` immediately after `json.loads`) that rejects a report if a non-finite float exists ANYWHERE in it -- even in a field the gate's decision logic never reads (a `skipped[]` entry's incidental note, a deeply-nested `run_context` field, ...). This is deliberately coarser than validating only the specific fields the gate consumes: it guarantees no raw non-finite value can ever reach `gate_logic` at all, so no future echo site anywhere in the module needs to remember to individually guard against this -- the loader closes the class of bug structurally, once, rather than requiring every current and future audit-echo field to defend itself. `allow_nan=False` remains in place as a second, now-normally-unreachable defense layer.

**`_contains_non_finite` is iterative, not recursive** (PR #249 user-review round 4): a legitimate, ordinary JSON document can be nested hundreds of levels deep -- an array-of-arrays field the gate never reads, say -- and is perfectly valid input, not an attack. A recursive walker over that structure raises `RecursionError` well before Python's default limit would suggest (confirmed empirically: each JSON nesting level costs more than one Python call frame once the `any(... for ...)` generator-expression overhead is counted, so a plain recursive version of this function starts failing around depth ~500), which used to crash the CLI with exit 1 on a file that should have produced a completely ordinary result. The iterative version uses an explicit stack instead -- no call-stack depth limit, bounded only by memory, O(n) over the structure.

`json.loads` itself can also raise `RecursionError` on sufficiently extreme nesting, independent of this module's own scan -- confirmed empirically in this environment: the C-accelerated decoder handles depth 100,000 without issue but raises `RecursionError` ("Stack overflow ... while decoding a JSON array") around depth 200,000. `RecursionError` is not a subclass of `json.JSONDecodeError` or `ValueError`, so `load_json_file` catches it explicitly and routes it to the same `<input>_parse_error` class as any other unparsable file -- exit 0, a report is still written, never an uncaught crash.

## Warnings (Never Change the Status)

- `price_action_confidence_medium` / `news_confidence_medium` -- fires only at `READY_FOR_PLAN` when that input's confidence is `MEDIUM` (single-signal weakness).
- `<input>_near_stale` -- fires when an input's age is within 2 days of its configured max age (and not already over it, which would instead be `INVALID`/`_json_stale`).
- `detector_data_date_divergence` -- the crowding market row's own `data_date` differs from `run_context.data_date` (the run's vintage, which is what staleness is evaluated against).
- `out_of_order_price_action` -- see rule 5 above.

## Worked Example: Real B6 REJECTED Case

Regenerated live against `cot-contrarian-detector` on 2026-07-12 (`--symbols B6,BT,D6 --as-of 2026-07-12`): B6 (British Pound) came back `CROWDED_SHORT` with `cot_index_3y=7.2`, `run_context.data_date=2026-07-07`. Running the gate with `--as-of 2026-07-15` (detector age 8 days, under the default 10-day max) and a news-reaction-failure-analyzer report whose `verdict` is `NOT_CONFIRMED`:

- Crowding normalizes to `CONFIRMED`, `classification=CROWDED_SHORT`, `direction=LONG` (step 1 does not stop the pipeline -- crowding is usable).
- News normalizes to `NOT_CONFIRMED` and settles the decision at step 2 -- price-action is never inspected at all for this run (there isn't one provided in this example anyway).
- `setup_status = REJECTED`, `missing_confirmations = [{"step": "news_failure", "state": "NOT_CONFIRMED", "reason": "<the news report's own verdict_reason>"}]`.
- `direction` remains `LONG` in the output (crowding was confirmed, even though the overall setup was rejected) -- an audit trail of what crowd was being faded, not an actionable signal.

Running the same detector report with `--as-of` set to a later date pushes the detector's age past `--max-detector-age-days`, which instead produces `INSUFFICIENT_EVIDENCE` with reason `detector_json_stale` -- crowding itself becomes unusable at step 1, before news is ever inspected.
