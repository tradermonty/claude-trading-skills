#!/usr/bin/env python3
"""
Edge Signal Aggregator

Combine outputs from multiple upstream edge-finding skills into a single
weighted conviction dashboard with deduplication and contradiction detection.
"""

import argparse
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# Default weights if no config provided
DEFAULT_WEIGHTS = {
    "edge_candidate_agent": 0.25,
    "edge_concept_synthesizer": 0.20,
    "theme_detector": 0.15,
    "sector_analyst": 0.15,
    "institutional_flow_tracker": 0.15,
    "edge_hint_extractor": 0.10,
}

DEFAULT_CONFIG = {
    "weights": DEFAULT_WEIGHTS,
    "deduplication": {
        "similarity_threshold": 0.80,
        "ticker_overlap_threshold": 0.50,
        "merge_bonus_per_duplicate": 0.05,
    },
    "agreement": {
        "two_skills_bonus": 0.10,
        "three_plus_skills_bonus": 0.20,
        "max_score": 1.00,
    },
    "recency": {
        "within_24h": 1.00,
        "days_1_to_3": 0.95,
        "days_3_to_7": 0.90,
        "days_7_plus": 0.85,
    },
    "confidence_factors": {
        "multi_skill_agreement": 0.35,
        "signal_strength": 0.40,
        "recency": 0.25,
    },
    "min_conviction": 0.50,
}


def load_config(config_path: str | None) -> dict[str, Any]:
    """Load weights configuration from YAML file or use defaults."""
    if config_path is None:
        return DEFAULT_CONFIG.copy()

    path = Path(config_path)
    if not path.exists():
        print(f"Warning: Config file not found: {config_path}, using defaults", file=sys.stderr)
        return DEFAULT_CONFIG.copy()

    if not YAML_AVAILABLE:
        print("Warning: PyYAML not installed, using default config", file=sys.stderr)
        return DEFAULT_CONFIG.copy()

    with open(path) as f:
        config = yaml.safe_load(f)

    # Merge with defaults for any missing keys
    merged = DEFAULT_CONFIG.copy()
    if config:
        for key, value in config.items():
            if isinstance(value, dict) and key in merged:
                merged[key] = {**merged.get(key, {}), **value}
            else:
                merged[key] = value
    return merged


def load_json_files(pattern: str | None) -> list[dict[str, Any]]:
    """Load all JSON files matching the glob pattern."""
    if not pattern:
        return []
    files = glob.glob(pattern)
    results = []
    for f in files:
        try:
            with open(f) as fp:
                data = json.load(fp)
                data["_source_file"] = f
                results.append(data)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to load {f}: {e}", file=sys.stderr)
    return results


def load_yaml_files(pattern: str | None) -> list[dict[str, Any]]:
    """Load all YAML files matching the glob pattern."""
    if not pattern:
        return []
    if not YAML_AVAILABLE:
        print("Warning: PyYAML not installed, cannot load YAML files", file=sys.stderr)
        return []
    files = glob.glob(pattern)
    results = []
    for f in files:
        try:
            with open(f) as fp:
                data = yaml.safe_load(fp)
                if data:
                    data["_source_file"] = f
                    results.append(data)
        except (OSError, yaml.YAMLError) as e:
            print(f"Warning: Failed to load {f}: {e}", file=sys.stderr)
    return results


def normalize_score(score: float | str | None, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Normalize a score to [0, 1] range."""
    if score is None:
        return 0.0
    if isinstance(score, str):
        # Handle letter grades
        grade_map = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.2}
        return grade_map.get(score.upper(), 0.0)
    try:
        val = float(score)
        if max_val == min_val:
            return 1.0 if val >= max_val else 0.0
        return max(0.0, min(1.0, (val - min_val) / (max_val - min_val)))
    except (TypeError, ValueError):
        return 0.0


def calculate_recency_factor(timestamp_str: str | None, recency_config: dict[str, float]) -> float:
    """Calculate recency adjustment factor based on signal age."""
    if not timestamp_str:
        return recency_config.get("days_7_plus", 0.85)

    try:
        # Try ISO format first
        if "T" in timestamp_str:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            ts = datetime.strptime(timestamp_str, "%Y-%m-%d")
            ts = ts.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_days = (now - ts).days

        if age_days < 1:
            return recency_config.get("within_24h", 1.0)
        elif age_days <= 3:
            return recency_config.get("days_1_to_3", 0.95)
        elif age_days <= 7:
            return recency_config.get("days_3_to_7", 0.90)
        else:
            return recency_config.get("days_7_plus", 0.85)
    except (ValueError, TypeError):
        return recency_config.get("days_7_plus", 0.85)


def extract_signals_from_edge_candidates(data: list[dict]) -> list[dict]:
    """Extract signals from edge-candidate-agent output."""
    signals = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        # Handle tickets array
        tickets = doc.get("tickets", [])
        if not tickets and "anomalies" in doc:
            tickets = doc.get("anomalies", [])

        for ticket in tickets:
            signal = {
                "skill": "edge_candidate_agent",
                "signal_ref": ticket.get("ticket_id", ticket.get("id", "unknown")),
                "title": ticket.get("title", ticket.get("description", "Unnamed signal")),
                "raw_score": normalize_score(ticket.get("score", ticket.get("confidence", 0.5))),
                "tickers": ticket.get("tickers", ticket.get("symbols", [])),
                "direction": ticket.get("direction", "NEUTRAL"),
                "time_horizon": ticket.get("time_horizon", "unknown"),
                "timestamp": ticket.get("timestamp", ticket.get("date")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals


def extract_signals_from_concepts(data: list[dict]) -> list[dict]:
    """Extract signals from edge-concept-synthesizer output."""
    signals = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        concepts = doc.get("concepts", doc.get("edge_concepts", []))

        for concept in concepts:
            signal = {
                "skill": "edge_concept_synthesizer",
                "signal_ref": concept.get("concept_id", concept.get("id", "unknown")),
                "title": concept.get("title", concept.get("name", "Unnamed concept")),
                "raw_score": normalize_score(concept.get("confidence", concept.get("score", 0.5))),
                "tickers": concept.get("tickers", concept.get("symbols", [])),
                "direction": concept.get("direction", "NEUTRAL"),
                "time_horizon": concept.get("time_horizon", "medium-term"),
                "timestamp": concept.get("timestamp", doc.get("generated_at")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals


def extract_signals_from_themes(data: list[dict]) -> list[dict]:
    """Extract signals from theme-detector output."""
    signals = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        themes = doc.get("themes", doc.get("detected_themes", []))

        for theme in themes:
            signal = {
                "skill": "theme_detector",
                "signal_ref": theme.get("theme_id", theme.get("id", "unknown")),
                "title": theme.get("theme_name", theme.get("name", "Unnamed theme")),
                "raw_score": normalize_score(theme.get("strength", theme.get("score", 0.5))),
                "tickers": theme.get("tickers", theme.get("related_symbols", [])),
                "direction": theme.get("direction", "LONG"),
                "time_horizon": theme.get("horizon", "3-6 months"),
                "timestamp": doc.get("generated_at", doc.get("timestamp")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals


def extract_signals_from_sectors(data: list[dict]) -> list[dict]:
    """Extract signals from sector-analyst output."""
    signals = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        sectors = doc.get("sectors", doc.get("sector_analysis", []))

        for sector in sectors:
            direction = "NEUTRAL"
            if sector.get("rotation_phase") in ["accumulation", "markup"]:
                direction = "LONG"
            elif sector.get("rotation_phase") in ["distribution", "markdown"]:
                direction = "SHORT"

            signal = {
                "skill": "sector_analyst",
                "signal_ref": sector.get("sector_name", sector.get("sector", "unknown")),
                "title": f"{sector.get('sector_name', sector.get('sector', 'Unknown'))} Sector",
                "raw_score": normalize_score(sector.get("strength", sector.get("score", 0.5))),
                "tickers": sector.get("top_stocks", sector.get("tickers", [])),
                "direction": direction,
                "time_horizon": "1-3 months",
                "timestamp": doc.get("generated_at", doc.get("timestamp")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals


def extract_signals_from_institutional(data: list[dict]) -> list[dict]:
    """Extract signals from institutional-flow-tracker output."""
    signals = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        flows = doc.get("flows", doc.get("institutional_flows", []))

        for flow in flows:
            direction = "NEUTRAL"
            if flow.get("action") in ["BUY", "INCREASE"]:
                direction = "LONG"
            elif flow.get("action") in ["SELL", "DECREASE"]:
                direction = "SHORT"

            signal = {
                "skill": "institutional_flow_tracker",
                "signal_ref": flow.get(
                    "flow_id",
                    f"{flow.get('institution', 'unknown')}_{flow.get('ticker', 'unknown')}",
                ),
                "title": f"{flow.get('institution', 'Unknown')} - {flow.get('ticker', 'Unknown')}",
                "raw_score": normalize_score(flow.get("confidence", flow.get("magnitude", 0.5))),
                "tickers": [flow.get("ticker")] if flow.get("ticker") else [],
                "direction": direction,
                "time_horizon": "3-12 months",
                "timestamp": flow.get("filing_date", doc.get("generated_at")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals


def extract_signals_from_hints(data: list[dict]) -> list[dict]:
    """Extract signals from edge-hint-extractor output."""
    signals = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        hints = doc.get("hints", doc.get("edge_hints", []))

        for hint in hints:
            signal = {
                "skill": "edge_hint_extractor",
                "signal_ref": hint.get("hint_id", hint.get("id", "unknown")),
                "title": hint.get("hint", hint.get("description", "Unnamed hint")),
                "raw_score": normalize_score(hint.get("relevance", hint.get("score", 0.3))),
                "tickers": hint.get("tickers", hint.get("symbols", [])),
                "direction": hint.get("direction", "NEUTRAL"),
                "time_horizon": hint.get("horizon", "unknown"),
                "timestamp": doc.get("generated_at", doc.get("timestamp")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals


def calculate_ticker_overlap(tickers_a: list[str], tickers_b: list[str]) -> float:
    """Calculate Jaccard similarity between two ticker lists."""
    if not tickers_a or not tickers_b:
        return 0.0
    set_a = set(t.upper() for t in tickers_a)
    set_b = set(t.upper() for t in tickers_b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def calculate_text_similarity(text_a: str, text_b: str) -> float:
    """Calculate simple word-based Jaccard similarity."""
    if not text_a or not text_b:
        return 0.0
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0


def are_signals_similar(sig_a: dict, sig_b: dict, config: dict) -> bool:
    """Determine if two signals should be considered duplicates."""
    dedup_config = config.get("deduplication", {})
    similarity_threshold = dedup_config.get("similarity_threshold", 0.80)
    ticker_threshold = dedup_config.get("ticker_overlap_threshold", 0.50)

    # Different directions are not duplicates
    if sig_a.get("direction") != sig_b.get("direction"):
        return False

    ticker_sim = calculate_ticker_overlap(sig_a.get("tickers", []), sig_b.get("tickers", []))
    text_sim = calculate_text_similarity(sig_a.get("title", ""), sig_b.get("title", ""))

    # Either high ticker overlap or high text similarity
    return ticker_sim >= ticker_threshold or text_sim >= similarity_threshold


def deduplicate_signals(signals: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    """
    Deduplicate signals, merging similar ones.
    Returns (deduplicated_signals, dedup_log).
    """
    if not signals:
        return [], []

    # Sort by raw score descending so we keep highest-scoring as primary
    sorted_signals = sorted(signals, key=lambda s: s.get("raw_score", 0), reverse=True)

    merged = []
    dedup_log = []
    used_indices = set()

    for i, sig in enumerate(sorted_signals):
        if i in used_indices:
            continue

        # Find all signals similar to this one
        duplicates = []
        for j, other in enumerate(sorted_signals):
            if j != i and j not in used_indices:
                if are_signals_similar(sig, other, config):
                    duplicates.append((j, other))
                    used_indices.add(j)

        # Create merged signal
        merged_signal = sig.copy()
        merged_signal["contributing_skills"] = [
            {
                "skill": sig["skill"],
                "signal_ref": sig["signal_ref"],
                "raw_score": sig["raw_score"],
            }
        ]
        merged_signal["merged_from"] = []

        # Merge duplicates
        for dup_idx, dup in duplicates:
            merged_signal["contributing_skills"].append(
                {
                    "skill": dup["skill"],
                    "signal_ref": dup["signal_ref"],
                    "raw_score": dup["raw_score"],
                }
            )
            merged_signal["merged_from"].append(f"{dup['skill']}:{dup['signal_ref']}")

            # Merge tickers
            existing_tickers = set(t.upper() for t in merged_signal.get("tickers", []))
            new_tickers = set(t.upper() for t in dup.get("tickers", []))
            merged_signal["tickers"] = list(existing_tickers | new_tickers)

        if duplicates:
            dedup_log.append(
                {
                    "merged_into": f"{sig['skill']}:{sig['signal_ref']}",
                    "duplicates_removed": merged_signal["merged_from"],
                    "similarity_score": 0.90,  # Simplified
                }
            )

        merged.append(merged_signal)
        used_indices.add(i)

    return merged, dedup_log


def detect_contradictions(signals: list[dict]) -> list[dict]:
    """Detect contradictions between signals."""
    contradictions = []

    # Group signals by ticker
    ticker_signals: dict[str, list[dict]] = defaultdict(list)
    for sig in signals:
        for ticker in sig.get("tickers", []):
            ticker_signals[ticker.upper()].append(sig)

    # Check for opposing directions
    for ticker, sigs in ticker_signals.items():
        long_sigs = [s for s in sigs if s.get("direction") == "LONG"]
        short_sigs = [s for s in sigs if s.get("direction") == "SHORT"]

        for long_sig in long_sigs:
            for short_sig in short_sigs:
                # Skip if same skill (handled differently)
                if long_sig["skill"] == short_sig["skill"]:
                    severity = "HIGH"
                    resolution = "Same skill opposite signals - exclude both"
                else:
                    severity = "MEDIUM"
                    resolution = "Check timeframe mismatch (short-term vs long-term)"

                contradictions.append(
                    {
                        "contradiction_id": f"contra_{ticker}_{len(contradictions)}",
                        "ticker": ticker,
                        "description": f"Conflicting direction on {ticker}",
                        "severity": severity,
                        "skill_a": {
                            "skill": long_sig["skill"],
                            "signal": long_sig["title"],
                            "direction": "LONG",
                        },
                        "skill_b": {
                            "skill": short_sig["skill"],
                            "signal": short_sig["title"],
                            "direction": "SHORT",
                        },
                        "resolution_hint": resolution,
                    }
                )

    return contradictions


def calculate_composite_score(signal: dict, config: dict) -> dict:
    """Calculate composite conviction score for a signal."""
    weights = config.get("weights", DEFAULT_WEIGHTS)
    agreement_config = config.get("agreement", {})
    recency_config = config.get("recency", {})
    confidence_factors = config.get("confidence_factors", {})
    dedup_config = config.get("deduplication", {})

    contributing = signal.get(
        "contributing_skills",
        [
            {
                "skill": signal["skill"],
                "signal_ref": signal["signal_ref"],
                "raw_score": signal["raw_score"],
            }
        ],
    )

    # Calculate weighted score from contributing skills
    weighted_sum = 0.0
    total_weight = 0.0
    for contrib in contributing:
        skill = contrib["skill"]
        weight = weights.get(skill, 0.10)
        weighted_sum += contrib["raw_score"] * weight
        total_weight += weight
        contrib["weighted_contribution"] = round(contrib["raw_score"] * weight, 4)

    base_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Agreement bonus
    num_skills = len(set(c["skill"] for c in contributing))
    if num_skills >= 3:
        agreement_bonus = agreement_config.get("three_plus_skills_bonus", 0.20)
    elif num_skills == 2:
        agreement_bonus = agreement_config.get("two_skills_bonus", 0.10)
    else:
        agreement_bonus = 0.0

    # Merge bonus
    num_merged = len(signal.get("merged_from", []))
    merge_bonus = num_merged * dedup_config.get("merge_bonus_per_duplicate", 0.05)

    # Recency factor
    recency_factor = calculate_recency_factor(signal.get("timestamp"), recency_config)

    # Composite score with cap
    max_score = agreement_config.get("max_score", 1.0)
    composite = min(max_score, (base_score + agreement_bonus + merge_bonus) * recency_factor)

    # Confidence breakdown
    agreement_weight = confidence_factors.get("multi_skill_agreement", 0.35)
    strength_weight = confidence_factors.get("signal_strength", 0.40)
    recency_weight = confidence_factors.get("recency", 0.25)

    avg_raw_score = sum(c["raw_score"] for c in contributing) / len(contributing)

    confidence_breakdown = {
        "multi_skill_agreement": round(agreement_bonus / 0.20 * agreement_weight, 2),
        "signal_strength": round(avg_raw_score * strength_weight, 2),
        "recency": round(recency_factor * recency_weight, 2),
    }

    return {
        "composite_score": round(composite, 4),
        "contributing_skills": contributing,
        "confidence_breakdown": confidence_breakdown,
    }


def aggregate_signals(
    edge_candidates: list[dict],
    edge_concepts: list[dict],
    themes: list[dict],
    sectors: list[dict],
    institutional: list[dict],
    hints: list[dict],
    config: dict,
) -> dict:
    """Main aggregation function."""
    # Extract signals from all sources
    all_signals = []
    all_signals.extend(extract_signals_from_edge_candidates(edge_candidates))
    all_signals.extend(extract_signals_from_concepts(edge_concepts))
    all_signals.extend(extract_signals_from_themes(themes))
    all_signals.extend(extract_signals_from_sectors(sectors))
    all_signals.extend(extract_signals_from_institutional(institutional))
    all_signals.extend(extract_signals_from_hints(hints))

    total_input = len(all_signals)

    # Deduplicate
    deduped_signals, dedup_log = deduplicate_signals(all_signals, config)

    # Detect contradictions
    contradictions = detect_contradictions(deduped_signals)

    # Calculate composite scores
    ranked_signals = []
    for sig in deduped_signals:
        score_data = calculate_composite_score(sig, config)
        ranked_signal = {
            "signal_id": f"sig_{len(ranked_signals):03d}",
            "title": sig["title"],
            "composite_score": score_data["composite_score"],
            "contributing_skills": score_data["contributing_skills"],
            "tickers": sig.get("tickers", []),
            "direction": sig.get("direction", "NEUTRAL"),
            "time_horizon": sig.get("time_horizon", "unknown"),
            "confidence_breakdown": score_data["confidence_breakdown"],
        }
        ranked_signals.append(ranked_signal)

    # Sort by composite score
    ranked_signals.sort(key=lambda s: s["composite_score"], reverse=True)

    # Assign ranks
    for i, sig in enumerate(ranked_signals):
        sig["rank"] = i + 1

    # Filter by minimum conviction
    min_conviction = config.get("min_conviction", 0.50)
    signals_above_threshold = [s for s in ranked_signals if s["composite_score"] >= min_conviction]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "weights": config.get("weights", DEFAULT_WEIGHTS),
            "min_conviction": min_conviction,
            "dedup_similarity_threshold": config.get("deduplication", {}).get(
                "similarity_threshold", 0.80
            ),
        },
        "summary": {
            "total_input_signals": total_input,
            "unique_signals_after_dedup": len(deduped_signals),
            "contradictions_found": len(contradictions),
            "signals_above_threshold": len(signals_above_threshold),
        },
        "ranked_signals": ranked_signals,
        "contradictions": contradictions,
        "deduplication_log": dedup_log,
    }


def generate_markdown_report(result: dict) -> str:
    """Generate markdown dashboard from aggregation result."""
    lines = [
        "# Edge Signal Aggregator Dashboard",
        f"**Generated:** {result['generated_at']}",
        "",
        "## Summary",
        f"- Total Input Signals: {result['summary']['total_input_signals']}",
        f"- Unique After Dedup: {result['summary']['unique_signals_after_dedup']}",
        f"- Contradictions: {result['summary']['contradictions_found']}",
        f"- High Conviction (>{result['config']['min_conviction']}): {result['summary']['signals_above_threshold']}",
        "",
    ]

    # Top signals
    min_conv = result["config"]["min_conviction"]
    top_signals = [s for s in result["ranked_signals"] if s["composite_score"] >= min_conv][:10]

    if top_signals:
        lines.append("## Top Edge Ideas by Conviction")
        lines.append("")

        for sig in top_signals:
            lines.append(f"### {sig['rank']}. {sig['title']} (Score: {sig['composite_score']:.2f})")
            tickers = ", ".join(sig["tickers"]) if sig["tickers"] else "N/A"
            lines.append(f"- **Tickers:** {tickers}")
            lines.append(
                f"- **Direction:** {sig['direction']} | **Horizon:** {sig['time_horizon']}"
            )
            lines.append("- **Contributing Skills:**")
            for contrib in sig["contributing_skills"]:
                lines.append(
                    f"  - {contrib['skill']}: {contrib['raw_score']:.2f} ({contrib['signal_ref']})"
                )
            cb = sig["confidence_breakdown"]
            lines.append(
                f"- **Confidence:** Agreement {cb['multi_skill_agreement']:.2f} | Strength {cb['signal_strength']:.2f} | Recency {cb['recency']:.2f}"
            )
            lines.append("")

    # Contradictions
    if result["contradictions"]:
        lines.append("## Contradictions Requiring Review")
        lines.append("")
        for contra in result["contradictions"]:
            lines.append(f"### {contra['description']} ({contra['severity']})")
            lines.append(
                f"- **{contra['skill_a']['skill']}:** {contra['skill_a']['signal']} ({contra['skill_a']['direction']})"
            )
            lines.append(
                f"- **{contra['skill_b']['skill']}:** {contra['skill_b']['signal']} ({contra['skill_b']['direction']})"
            )
            lines.append(f"- **Hint:** {contra['resolution_hint']}")
            lines.append("")

    # Deduplication summary
    if result["deduplication_log"]:
        lines.append("## Deduplication Summary")
        total_merged = sum(len(d["duplicates_removed"]) for d in result["deduplication_log"])
        lines.append(
            f"- {total_merged} signals merged into {len(result['deduplication_log'])} unique themes"
        )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Aggregate signals from multiple edge-finding skills"
    )
    parser.add_argument(
        "--edge-candidates",
        help="Glob pattern for edge-candidate-agent JSON files",
    )
    parser.add_argument(
        "--edge-concepts",
        help="Glob pattern for edge-concept-synthesizer YAML files",
    )
    parser.add_argument(
        "--themes",
        help="Glob pattern for theme-detector JSON files",
    )
    parser.add_argument(
        "--sectors",
        help="Glob pattern for sector-analyst JSON files",
    )
    parser.add_argument(
        "--institutional",
        help="Glob pattern for institutional-flow-tracker JSON files",
    )
    parser.add_argument(
        "--hints",
        help="Glob pattern for edge-hint-extractor YAML files",
    )
    parser.add_argument(
        "--weights-config",
        help="Path to custom weights YAML configuration",
    )
    parser.add_argument(
        "--min-conviction",
        type=float,
        help="Minimum conviction score for output filtering (overrides config)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/",
        help="Output directory for reports (default: reports/)",
    )
    parser.add_argument(
        "--output-prefix",
        default="edge_signal_aggregator",
        help="Prefix for output filenames",
    )

    args = parser.parse_args()

    # Check if at least one input is provided
    if not any(
        [
            args.edge_candidates,
            args.edge_concepts,
            args.themes,
            args.sectors,
            args.institutional,
            args.hints,
        ]
    ):
        print("Error: At least one input source must be provided", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 1

    # Load configuration
    config = load_config(args.weights_config)
    if args.min_conviction is not None:
        config["min_conviction"] = args.min_conviction

    # Load input files
    edge_candidates = load_json_files(args.edge_candidates)
    edge_concepts = load_yaml_files(args.edge_concepts)
    themes = load_json_files(args.themes)
    sectors = load_json_files(args.sectors)
    institutional = load_json_files(args.institutional)
    hints = load_yaml_files(args.hints)

    # Run aggregation
    result = aggregate_signals(
        edge_candidates=edge_candidates,
        edge_concepts=edge_concepts,
        themes=themes,
        sectors=sectors,
        institutional=institutional,
        hints=hints,
        config=config,
    )

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # Write JSON report
    json_path = output_dir / f"{args.output_prefix}_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"JSON report written to: {json_path}")

    # Write Markdown report
    md_content = generate_markdown_report(result)
    md_path = output_dir / f"{args.output_prefix}_{timestamp}.md"
    with open(md_path, "w") as f:
        f.write(md_content)
    print(f"Markdown report written to: {md_path}")

    # Print summary to stdout
    print("\n--- Aggregation Summary ---")
    print(f"Total input signals: {result['summary']['total_input_signals']}")
    print(f"Unique after dedup: {result['summary']['unique_signals_after_dedup']}")
    print(f"Contradictions found: {result['summary']['contradictions_found']}")
    print(
        f"Above threshold ({config['min_conviction']}): {result['summary']['signals_above_threshold']}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
