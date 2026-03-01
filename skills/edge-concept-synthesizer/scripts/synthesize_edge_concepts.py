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
