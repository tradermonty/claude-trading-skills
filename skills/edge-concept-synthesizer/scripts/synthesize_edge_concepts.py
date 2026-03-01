#!/usr/bin/env python3
"""Synthesize abstract edge concepts from detector tickets and hints."""

from __future__ import annotations

import argparse
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

EXPORTABLE_FAMILIES = {"pivot_breakout", "gap_up_continuation"}

HYPOTHESIS_TO_TITLE = {
    "breakout": "Participation-backed trend breakout",
    "earnings_drift": "Event-driven continuation drift",
    "news_reaction": "Event overreaction and drift",
    "futures_trigger": "Cross-asset propagation",
    "calendar_anomaly": "Seasonality-linked demand imbalance",
    "panic_reversal": "Shock overshoot mean reversion",
    "regime_shift": "Regime transition opportunity",
    "sector_x_stock": "Leader-laggard sector relay",
    "research_hypothesis": "Unclassified edge hypothesis",
}

HYPOTHESIS_TO_THESIS = {
    "breakout": (
        "When liquidity and participation expand during a positive regime, "
        "price expansion above structural pivots can persist for multiple sessions."
    ),
    "earnings_drift": (
        "Large information shocks can lead to underreaction, creating measurable post-event continuation."
    ),
    "news_reaction": (
        "Extreme single-day reactions often create either delayed continuation or overshoot reversion windows."
    ),
    "futures_trigger": (
        "Cross-asset futures shocks can transmit to related equities through hedging flows and risk transfer."
    ),
    "calendar_anomaly": (
        "Recurring calendar windows can produce repeatable demand-supply imbalances for specific symbols."
    ),
    "panic_reversal": (
        "Large downside shocks accompanied by exhaustion flow can set up short-horizon reversal edges."
    ),
    "regime_shift": (
        "Early inflections in breadth, correlation, and volatility can front-run major regime transitions."
    ),
    "sector_x_stock": (
        "Leadership shocks in one symbol can propagate into linked symbols through sector-level flow dynamics."
    ),
    "research_hypothesis": (
        "Observed pattern may represent a repeatable conditional edge requiring explicit validation."
    ),
}

HYPOTHESIS_TO_PLAYBOOKS = {
    "breakout": ["trend_following_breakout", "confirmation_filtered_breakout"],
    "earnings_drift": ["gap_continuation", "post_event_drift"],
    "news_reaction": ["event_drift_continuation", "event_reversal"],
    "futures_trigger": ["cross_asset_follow_through", "mapped_basket_rotation"],
    "calendar_anomaly": ["seasonal_rotation", "seasonal_overlay"],
    "panic_reversal": ["shock_reversal", "bounce_with_trend_filter"],
    "regime_shift": ["regime_transition_probe"],
    "sector_x_stock": ["leader_laggard_pair", "sector_relay_follow_through"],
    "research_hypothesis": ["research_probe"],
}

HYPOTHESIS_TO_INVALIDATIONS = {
    "breakout": [
        "Breakout fails quickly with volume contraction.",
        "Breadth weakens while correlations spike defensively.",
    ],
    "earnings_drift": [
        "Post-event day closes below event-day low.",
        "Volume confirmation disappears after day 1-2.",
    ],
    "news_reaction": [
        "Reaction mean-reverts fully within 1-2 sessions.",
        "No follow-through after confirmation filter.",
    ],
    "futures_trigger": [
        "Futures shock normalizes immediately.",
        "Mapped equities show no directional sensitivity.",
    ],
    "calendar_anomaly": [
        "Recent years break the historical seasonal pattern.",
        "Pattern only survives in illiquid tails.",
    ],
    "panic_reversal": [
        "Shock extends without stabilization signal.",
        "Reversal only appears in low-liquidity outliers.",
    ],
    "regime_shift": [
        "Breadth and volatility revert to prior regime quickly.",
        "Signal appears only during isolated macro events.",
    ],
    "sector_x_stock": [
        "Lead-lag correlation collapses out-of-sample.",
        "Propagation depends on one-off events only.",
    ],
    "research_hypothesis": [
        "Out-of-sample behavior does not replicate.",
        "Costs erase edge expectancy.",
    ],
}


KNOWN_HYPOTHESIS_TYPES: frozenset[str] = frozenset(
    {
        "breakout",
        "earnings_drift",
        "news_reaction",
        "futures_trigger",
        "calendar_anomaly",
        "panic_reversal",
        "regime_shift",
        "sector_x_stock",
    }
)
FALLBACK_HYPOTHESIS_TYPE = "research_hypothesis"

HYPOTHESIS_KEYWORDS: dict[str, list[str]] = {
    "breakout": ["breakout", "pivot", "participation", "high20"],
    "earnings_drift": ["earnings", "drift", "post-event", "post_event", "pead"],
    "news_reaction": ["news", "reaction", "headline", "catalyst"],
    "futures_trigger": ["futures", "cross-asset", "cross_asset", "propagation"],
    "calendar_anomaly": ["calendar", "seasonal", "buyback", "blackout", "rebalance", "window"],
    "panic_reversal": ["panic", "reversal", "shock", "overshoot", "mean-reversion", "bounce"],
    "regime_shift": [
        "regime",
        "transition",
        "inflection",
        "shift",
        "rotation",
        "breadth divergence",
    ],
    "sector_x_stock": ["sector", "leader", "laggard", "relay", "supply chain"],
}
SYNTHETIC_TICKET_PREFIX = "hint_promo_"
DEFAULT_SYNTHETIC_PRIORITY = 30.0


class ConceptSynthesisError(Exception):
    """Raised when concept synthesis fails."""


def infer_hypothesis_type(hint: dict[str, Any]) -> str:
    """Infer hypothesis_type from explicit field or keyword scan."""
    explicit = hint.get("hypothesis_type")
    if isinstance(explicit, str) and explicit.strip().lower() in KNOWN_HYPOTHESIS_TYPES:
        return explicit.strip().lower()
    text = (str(hint.get("title", "")) + " " + str(hint.get("observation", ""))).lower()
    best_type: str | None = None
    best_count = 0
    for hyp_type, keywords in HYPOTHESIS_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > best_count:
            best_count = count
            best_type = hyp_type
    return best_type if best_type is not None else FALLBACK_HYPOTHESIS_TYPE


def promote_hints_to_tickets(
    hints: list[dict[str, Any]],
    synthetic_priority: float,
) -> list[dict[str, Any]]:
    """Promote qualifying hints to synthetic tickets."""
    tickets: list[dict[str, Any]] = []
    for idx, hint in enumerate(hints):
        title = str(hint.get("title", "")).strip()
        if not title:
            continue

        hypothesis = infer_hypothesis_type(hint)
        mechanism = str(hint.get("mechanism_tag", "")).strip() or "uncertain"
        regime = str(hint.get("regime_bias", "")).strip() or "Unknown"

        entry_family_raw = hint.get("preferred_entry_family")
        if isinstance(entry_family_raw, str) and entry_family_raw in EXPORTABLE_FAMILIES:
            entry_family = entry_family_raw
        else:
            entry_family = "research_only"

        sanitized = sanitize_identifier(title)
        ticket_id = f"{SYNTHETIC_TICKET_PREFIX}{sanitized}_{idx}"

        observation: dict[str, Any] = {}
        symbols = hint.get("symbols", [])
        if isinstance(symbols, list) and symbols:
            first = str(symbols[0]).strip().upper()
            if first:
                observation["symbol"] = first

        tickets.append(
            {
                "id": ticket_id,
                "hypothesis_type": hypothesis,
                "mechanism_tag": mechanism,
                "regime": regime,
                "entry_family": entry_family,
                "priority_score": synthetic_priority,
                "observation": observation,
                "_synthetic": True,
            }
        )
    return tickets


def cap_synthetic_tickets(
    real_tickets: list[dict[str, Any]],
    synthetic_tickets: list[dict[str, Any]],
    max_ratio: float,
    floor: int = 3,
) -> list[dict[str, Any]]:
    """Cap synthetic ticket count relative to real ticket count.

    The allowed number of synthetic tickets is
    ``max(ceil(len(real_tickets) * max_ratio), floor)``.
    When the synthetic list exceeds this limit the highest-priority entries
    are kept.
    """
    import math

    limit = max(math.ceil(len(real_tickets) * max_ratio), floor)
    if len(synthetic_tickets) <= limit:
        return synthetic_tickets
    # Keep highest priority first
    ranked = sorted(synthetic_tickets, key=lambda t: t.get("priority_score", 0), reverse=True)
    return ranked[:limit]


def sanitize_identifier(value: str) -> str:
    """Create a safe identifier from free text."""
    lowered = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    compact = "_".join(part for part in lowered.split("_") if part)
    return compact or "concept"


def safe_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float conversion."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_hints(path: Path | None) -> list[dict[str, Any]]:
    """Read optional hints YAML."""
    if path is None:
        return []
    payload = yaml.safe_load(path.read_text())
    if payload is None:
        return []
    if isinstance(payload, list):
        hints = payload
    elif isinstance(payload, dict):
        raw = payload.get("hints", [])
        hints = raw if isinstance(raw, list) else []
    else:
        raise ConceptSynthesisError("hints file must be list or {hints: [...]} format")

    return [hint for hint in hints if isinstance(hint, dict)]


def discover_ticket_files(tickets_dir: Path) -> list[Path]:
    """Discover ticket YAML files recursively."""
    return sorted([path for path in tickets_dir.rglob("*.yaml") if path.is_file()])


def read_ticket(path: Path) -> dict[str, Any] | None:
    """Read one ticket YAML file."""
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        return None
    if "id" not in payload or "hypothesis_type" not in payload:
        return None
    return payload


def ticket_symbol(ticket: dict[str, Any]) -> str | None:
    """Extract representative symbol."""
    observation = ticket.get("observation")
    if isinstance(observation, dict):
        symbol = observation.get("symbol")
        if isinstance(symbol, str) and symbol.strip():
            return symbol.strip().upper()
    symbol = ticket.get("symbol")
    if isinstance(symbol, str) and symbol.strip():
        return symbol.strip().upper()
    return None


def ticket_conditions(ticket: dict[str, Any]) -> list[str]:
    """Collect condition strings from ticket."""
    conditions: list[str] = []

    signal_definition = ticket.get("signal_definition")
    if isinstance(signal_definition, dict):
        raw = signal_definition.get("conditions")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    conditions.append(item.strip())

    entry = ticket.get("entry")
    if isinstance(entry, dict):
        raw = entry.get("conditions")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    conditions.append(item.strip())

    return conditions


def cluster_key(ticket: dict[str, Any]) -> tuple[str, str, str]:
    """Build clustering key."""
    hypothesis = str(ticket.get("hypothesis_type", "unknown")).strip() or "unknown"
    mechanism = str(ticket.get("mechanism_tag", "uncertain")).strip() or "uncertain"
    regime = str(ticket.get("regime", "Unknown")).strip() or "Unknown"
    return hypothesis, mechanism, regime


def choose_recommended_entry_family(entry_counter: Counter[str]) -> str | None:
    """Choose recommended exportable entry family from distribution."""
    for family, _ in entry_counter.most_common():
        if family in EXPORTABLE_FAMILIES:
            return family
    return None


def match_hint_titles(
    hints: list[dict[str, Any]],
    symbols: list[str],
    regime: str,
    recommended_entry_family: str | None,
) -> list[str]:
    """Match hints relevant to concept symbols/family/regime."""
    symbol_set = set(symbols)
    titles: list[str] = []

    for hint in hints:
        title = str(hint.get("title", "")).strip()
        if not title:
            continue

        hint_symbols_raw = hint.get("symbols", [])
        hint_symbols = {
            str(symbol).strip().upper()
            for symbol in hint_symbols_raw
            if isinstance(symbol, str) and symbol.strip()
        }
        hint_regime = str(hint.get("regime_bias", "")).strip()
        hint_family = hint.get("preferred_entry_family")

        symbol_match = not hint_symbols or bool(symbol_set.intersection(hint_symbols))
        regime_match = not hint_regime or hint_regime == regime
        family_match = (
            recommended_entry_family is None
            or hint_family is None
            or hint_family == recommended_entry_family
        )

        if symbol_match and regime_match and family_match:
            titles.append(title)

    return sorted(set(titles))[:10]


def build_concept(
    key: tuple[str, str, str],
    tickets: list[dict[str, Any]],
    hints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one concept payload from clustered tickets."""
    hypothesis, mechanism, regime = key

    priority_scores = [safe_float(ticket.get("priority_score")) for ticket in tickets]
    avg_priority = statistics.mean(priority_scores) if priority_scores else 0.0

    symbols = [symbol for ticket in tickets if (symbol := ticket_symbol(ticket)) is not None]
    symbol_counter = Counter(symbols)
    top_symbols = [symbol for symbol, _ in symbol_counter.most_common(10)]

    entry_counter: Counter[str] = Counter()
    condition_counter: Counter[str] = Counter()
    ticket_ids: list[str] = []
    synthetic_ticket_ids: list[str] = []

    for ticket in tickets:
        ticket_id = str(ticket.get("id", "")).strip()
        is_synthetic = bool(ticket.get("_synthetic"))
        if ticket_id:
            if is_synthetic:
                synthetic_ticket_ids.append(ticket_id)
            else:
                ticket_ids.append(ticket_id)

        entry_family = ticket.get("entry_family")
        if (
            isinstance(entry_family, str)
            and entry_family.strip()
            and entry_family != "research_only"
            and not is_synthetic
        ):
            entry_counter[entry_family.strip()] += 1

        for condition in ticket_conditions(ticket):
            condition_counter[condition] += 1

    recommended_entry_family = choose_recommended_entry_family(entry_counter)
    export_ready_v1 = recommended_entry_family in EXPORTABLE_FAMILIES

    concept_id = sanitize_identifier(f"edge_concept_{hypothesis}_{mechanism}_{regime}")
    title = HYPOTHESIS_TO_TITLE.get(hypothesis, f"{hypothesis} concept")
    thesis = HYPOTHESIS_TO_THESIS.get(
        hypothesis,
        "Observed pattern may represent a repeatable conditional edge requiring explicit validation.",
    )

    hint_titles = match_hint_titles(
        hints=hints,
        symbols=top_symbols,
        regime=regime,
        recommended_entry_family=recommended_entry_family,
    )

    has_synthetic = bool(synthetic_ticket_ids)

    support_block: dict[str, Any] = {
        "ticket_count": len(tickets),
        "avg_priority_score": round(avg_priority, 2),
        "symbols": top_symbols,
        "entry_family_distribution": dict(entry_counter),
        "representative_conditions": [
            condition for condition, _ in condition_counter.most_common(6)
        ],
    }
    if has_synthetic:
        support_block["real_ticket_count"] = len(ticket_ids)
        support_block["synthetic_ticket_count"] = len(synthetic_ticket_ids)

    evidence_block: dict[str, Any] = {
        "ticket_ids": ticket_ids,
        "matched_hint_titles": hint_titles,
    }
    if has_synthetic:
        evidence_block["synthetic_ticket_ids"] = synthetic_ticket_ids

    return {
        "id": concept_id,
        "title": title,
        "hypothesis_type": hypothesis,
        "mechanism_tag": mechanism,
        "regime": regime,
        "support": support_block,
        "abstraction": {
            "thesis": thesis,
            "invalidation_signals": HYPOTHESIS_TO_INVALIDATIONS.get(
                hypothesis,
                ["Out-of-sample behavior does not replicate.", "Costs erase edge expectancy."],
            ),
        },
        "strategy_design": {
            "playbooks": HYPOTHESIS_TO_PLAYBOOKS.get(hypothesis, ["research_probe"]),
            "recommended_entry_family": recommended_entry_family,
            "export_ready_v1": bool(export_ready_v1),
        },
        "evidence": evidence_block,
    }


# ---------------------------------------------------------------------------
# Concept deduplication
# ---------------------------------------------------------------------------


def condition_overlap_ratio(conds_a: list[str], conds_b: list[str]) -> float:
    """Compute containment overlap: |A ∩ B| / min(|A|, |B|).

    Returns 0.0 when either list is empty.
    """
    if not conds_a or not conds_b:
        return 0.0
    set_a = {c.strip().lower() for c in conds_a}
    set_b = {c.strip().lower() for c in conds_b}
    intersection = len(set_a & set_b)
    return intersection / min(len(set_a), len(set_b))


def merge_concepts(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    """Merge two concepts.  The one with more tickets becomes *primary*.

    Returns a new concept dict with combined support and evidence.
    """
    p_count = primary.get("support", {}).get("ticket_count", 0)
    s_count = secondary.get("support", {}).get("ticket_count", 0)
    if s_count > p_count:
        primary, secondary = secondary, primary
        p_count, s_count = s_count, p_count

    total_count = p_count + s_count
    p_priority = primary.get("support", {}).get("avg_priority_score", 0.0)
    s_priority = secondary.get("support", {}).get("avg_priority_score", 0.0)
    avg_priority = round(
        (p_priority * p_count + s_priority * s_count) / total_count if total_count else 0.0,
        2,
    )

    # Symbols: union preserving order
    p_symbols = list(primary.get("support", {}).get("symbols", []))
    s_symbols = secondary.get("support", {}).get("symbols", [])
    seen = set(p_symbols)
    for sym in s_symbols:
        if sym not in seen:
            p_symbols.append(sym)
            seen.add(sym)

    # Mechanism tag
    p_mech = str(primary.get("mechanism_tag", "uncertain"))
    s_mech = str(secondary.get("mechanism_tag", "uncertain"))
    if p_mech != s_mech:
        merged_mechanism = "+".join(sorted([p_mech, s_mech]))
    else:
        merged_mechanism = p_mech

    # Entry family distribution (Counter merge)
    p_dist = dict(primary.get("support", {}).get("entry_family_distribution", {}))
    for k, v in secondary.get("support", {}).get("entry_family_distribution", {}).items():
        p_dist[k] = p_dist.get(k, 0) + v

    # Representative conditions: union, cap at 6
    p_conds = list(primary.get("support", {}).get("representative_conditions", []))
    s_conds = secondary.get("support", {}).get("representative_conditions", [])
    conds_lower_seen = {c.strip().lower() for c in p_conds}
    for c in s_conds:
        if c.strip().lower() not in conds_lower_seen:
            p_conds.append(c)
            conds_lower_seen.add(c.strip().lower())
    p_conds = p_conds[:6]

    # Entry family: primary preferred, fallback to secondary
    p_family = primary.get("strategy_design", {}).get("recommended_entry_family")
    s_family = secondary.get("strategy_design", {}).get("recommended_entry_family")
    recommended = p_family if p_family is not None else s_family
    export_ready = recommended in EXPORTABLE_FAMILIES if recommended else False

    # Evidence: ticket_ids union
    p_ticket_ids = list(primary.get("evidence", {}).get("ticket_ids", []))
    s_ticket_ids = secondary.get("evidence", {}).get("ticket_ids", [])
    all_ticket_ids = p_ticket_ids + [t for t in s_ticket_ids if t not in set(p_ticket_ids)]

    # Evidence: hint titles union
    p_hints = set(primary.get("evidence", {}).get("matched_hint_titles", []))
    s_hints = set(secondary.get("evidence", {}).get("matched_hint_titles", []))
    all_hints = sorted(p_hints | s_hints)

    # ID regeneration
    hypothesis = str(primary.get("hypothesis_type", "unknown"))
    regime = str(primary.get("regime", "Unknown"))
    concept_id = sanitize_identifier(f"edge_concept_{hypothesis}_{merged_mechanism}_{regime}")

    # Build support block
    support_block: dict[str, Any] = {
        "ticket_count": total_count,
        "avg_priority_score": avg_priority,
        "symbols": p_symbols,
        "entry_family_distribution": p_dist,
        "representative_conditions": p_conds,
    }

    # Synthetic fields
    p_real = primary.get("support", {}).get("real_ticket_count")
    s_real = secondary.get("support", {}).get("real_ticket_count")
    p_synth = primary.get("support", {}).get("synthetic_ticket_count")
    s_synth = secondary.get("support", {}).get("synthetic_ticket_count")
    if p_real is not None or s_real is not None:
        support_block["real_ticket_count"] = (p_real or 0) + (s_real or 0)
    if p_synth is not None or s_synth is not None:
        support_block["synthetic_ticket_count"] = (p_synth or 0) + (s_synth or 0)

    evidence_block: dict[str, Any] = {
        "ticket_ids": all_ticket_ids,
        "matched_hint_titles": all_hints,
    }
    p_synth_ids = primary.get("evidence", {}).get("synthetic_ticket_ids", [])
    s_synth_ids = secondary.get("evidence", {}).get("synthetic_ticket_ids", [])
    if p_synth_ids or s_synth_ids:
        evidence_block["synthetic_ticket_ids"] = list(p_synth_ids) + [
            t for t in s_synth_ids if t not in set(p_synth_ids)
        ]

    merged = {
        "id": concept_id,
        "title": primary.get("title", ""),
        "hypothesis_type": hypothesis,
        "mechanism_tag": merged_mechanism,
        "regime": regime,
        "support": support_block,
        "abstraction": dict(primary.get("abstraction", {})),
        "strategy_design": {
            "playbooks": list(primary.get("strategy_design", {}).get("playbooks", [])),
            "recommended_entry_family": recommended,
            "export_ready_v1": bool(export_ready),
        },
        "evidence": evidence_block,
        "merged_from": [secondary.get("id", "unknown")],
    }
    return merged


def deduplicate_concepts(
    concepts: list[dict[str, Any]],
    overlap_threshold: float = 0.75,
) -> tuple[list[dict[str, Any]], int]:
    """Greedy pairwise deduplication within same hypothesis_type.

    Returns ``(deduplicated_list, merge_count)``.
    """
    if len(concepts) <= 1:
        return list(concepts), 0

    merged_indices: set[int] = set()
    result: list[dict[str, Any]] = []
    merge_count = 0

    for i in range(len(concepts)):
        if i in merged_indices:
            continue
        current = concepts[i]
        for j in range(i + 1, len(concepts)):
            if j in merged_indices:
                continue
            candidate = concepts[j]
            if current.get("hypothesis_type") != candidate.get("hypothesis_type"):
                continue
            conds_a = current.get("support", {}).get("representative_conditions", [])
            conds_b = candidate.get("support", {}).get("representative_conditions", [])
            if condition_overlap_ratio(conds_a, conds_b) > overlap_threshold:
                current = merge_concepts(current, candidate)
                merged_indices.add(j)
                merge_count += 1
        result.append(current)

    return result, merge_count


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(
        description="Synthesize abstract edge concepts from detector tickets.",
    )
    parser.add_argument(
        "--tickets-dir", required=True, help="Directory containing ticket YAML files"
    )
    parser.add_argument("--hints", default=None, help="Optional hints YAML path")
    parser.add_argument(
        "--output",
        default="reports/edge_concepts/edge_concepts.yaml",
        help="Output concept YAML path",
    )
    parser.add_argument(
        "--min-ticket-support",
        type=int,
        default=1,
        help="Minimum ticket count required to keep a concept",
    )
    parser.add_argument(
        "--promote-hints",
        action="store_true",
        default=False,
        help="Promote qualifying hints to synthetic tickets for concept creation",
    )
    parser.add_argument(
        "--synthetic-priority",
        type=float,
        default=DEFAULT_SYNTHETIC_PRIORITY,
        help="Priority score for synthetic tickets (default: 30.0)",
    )
    parser.add_argument(
        "--max-synthetic-ratio",
        type=float,
        default=None,
        help="Max synthetic/real ticket ratio (e.g. 1.5); uncapped when omitted",
    )
    parser.add_argument(
        "--overlap-threshold",
        type=float,
        default=0.75,
        help="Condition overlap threshold for concept deduplication (default: 0.75)",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        default=False,
        help="Disable concept deduplication",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    tickets_dir = Path(args.tickets_dir).resolve()
    hints_path = Path(args.hints).resolve() if args.hints else None
    output_path = Path(args.output).resolve()

    if not tickets_dir.exists():
        print(f"[ERROR] tickets dir not found: {tickets_dir}")
        return 1
    if hints_path is not None and not hints_path.exists():
        print(f"[ERROR] hints file not found: {hints_path}")
        return 1

    try:
        hints = read_hints(hints_path)
        ticket_files = discover_ticket_files(tickets_dir)

        tickets: list[dict[str, Any]] = []
        for ticket_file in ticket_files:
            ticket = read_ticket(ticket_file)
            if ticket is not None:
                tickets.append(ticket)

        synthetic_tickets: list[dict[str, Any]] = []
        if args.promote_hints and hints:
            synthetic_tickets = promote_hints_to_tickets(
                hints=hints,
                synthetic_priority=args.synthetic_priority,
            )
            if args.max_synthetic_ratio is not None:
                synthetic_tickets = cap_synthetic_tickets(
                    real_tickets=tickets,
                    synthetic_tickets=synthetic_tickets,
                    max_ratio=args.max_synthetic_ratio,
                )
            tickets = tickets + synthetic_tickets

        if not tickets:
            raise ConceptSynthesisError("no valid ticket files found")

        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for ticket in tickets:
            grouped[cluster_key(ticket)].append(ticket)

        concepts: list[dict[str, Any]] = []
        for key, cluster_tickets in grouped.items():
            if len(cluster_tickets) < max(args.min_ticket_support, 1):
                continue
            concepts.append(build_concept(key=key, tickets=cluster_tickets, hints=hints))

        # Deduplication
        if not args.no_dedup:
            concepts, dedup_merged_count = deduplicate_concepts(concepts, args.overlap_threshold)
        else:
            dedup_merged_count = 0

        concepts.sort(
            key=lambda item: (
                safe_float(item.get("support", {}).get("avg_priority_score")),
                safe_float(item.get("support", {}).get("ticket_count")),
            ),
            reverse=True,
        )

        if not concepts:
            raise ConceptSynthesisError("no concepts passed min-ticket-support filter")

        candidate_dates = [str(ticket.get("date")) for ticket in tickets if ticket.get("date")]
        as_of = max(candidate_dates) if candidate_dates else None

        source_block: dict[str, Any] = {
            "tickets_dir": str(tickets_dir),
            "hints_path": str(hints_path) if hints_path else None,
            "ticket_file_count": len(ticket_files),
            "ticket_count": len(tickets),
        }
        if args.promote_hints:
            source_block["promote_hints"] = True
            source_block["real_ticket_count"] = len(tickets) - len(synthetic_tickets)
            source_block["synthetic_ticket_count"] = len(synthetic_tickets)

        source_block["dedup_enabled"] = not args.no_dedup
        source_block["overlap_threshold"] = args.overlap_threshold
        source_block["dedup_merged_count"] = dedup_merged_count

        payload = {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "as_of": as_of,
            "source": source_block,
            "concept_count": len(concepts),
            "concepts": concepts,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    except ConceptSynthesisError as exc:
        print(f"[ERROR] {exc}")
        return 1

    synth_msg = f" synthetic_tickets={len(synthetic_tickets)}" if synthetic_tickets else ""
    print(f"[OK] concepts={len(concepts)}{synth_msg} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
