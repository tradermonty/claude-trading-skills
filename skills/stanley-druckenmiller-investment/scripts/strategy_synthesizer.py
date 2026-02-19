#!/usr/bin/env python3
"""
Druckenmiller Strategy Synthesizer - Main Orchestrator

Integrates outputs from 8 upstream analysis skills (5 required + 3 optional)
into a unified conviction score, pattern classification, and allocation
recommendation based on Stanley Druckenmiller's investment philosophy.

Usage:
    python3 strategy_synthesizer.py --reports-dir reports/
    python3 strategy_synthesizer.py --reports-dir reports/ --output-dir reports/ --max-age 72

Output:
    - JSON: druckenmiller_strategy_YYYY-MM-DD_HHMMSS.json
    - Markdown: druckenmiller_strategy_YYYY-MM-DD_HHMMSS.md
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from report_loader import load_all_reports, extract_signal, REQUIRED_SKILLS, OPTIONAL_SKILLS
from scorer import calculate_composite_conviction, classify_pattern
from allocation_engine import generate_allocation, calculate_position_sizing
from report_generator import generate_json_report, generate_markdown_report


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Druckenmiller Strategy Synthesizer - Meta-Skill Orchestrator"
    )
    parser.add_argument(
        "--reports-dir", default="reports/",
        help="Directory containing upstream skill JSON reports (default: reports/)"
    )
    parser.add_argument(
        "--output-dir", default="reports/",
        help="Directory for output reports (default: reports/)"
    )
    parser.add_argument(
        "--max-age", type=float, default=72,
        help="Maximum age (hours) for input reports (default: 72)"
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    print("=" * 70)
    print("Druckenmiller Strategy Synthesizer")
    print("8-Skill Integration | Conviction Scoring | Pattern Classification")
    print("=" * 70)
    print()

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    # ========================================================================
    # Step 1: Load Input Reports
    # ========================================================================
    print("Step 1: Loading Input Reports")
    print("-" * 70)

    try:
        reports = load_all_reports(args.reports_dir, max_age_hours=args.max_age)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    required_count = sum(1 for k in reports if k in REQUIRED_SKILLS)
    optional_count = sum(1 for k in reports if k in OPTIONAL_SKILLS)
    print(f"  Loaded {len(reports)} reports ({required_count} required + {optional_count} optional)")

    for skill_name in reports:
        marker = "REQ" if skill_name in REQUIRED_SKILLS else "OPT"
        print(f"  [{marker}] {skill_name}")
    print()

    # ========================================================================
    # Step 2: Extract Signals
    # ========================================================================
    print("Step 2: Extracting Normalized Signals")
    print("-" * 70)

    signals = {}
    for skill_name, report_data in reports.items():
        sig = extract_signal(skill_name, report_data)
        signals[skill_name] = sig

        # Print key metric per skill
        if "composite_score" in sig:
            print(f"  {skill_name}: score={sig['composite_score']}")
        elif "derived_score" in sig:
            print(f"  {skill_name}: derived={sig['derived_score']}")
        elif "quality_score" in sig:
            print(f"  {skill_name}: quality={sig['quality_score']}, state={sig.get('state', 'N/A')}")

    print()

    # ========================================================================
    # Step 3: Calculate Composite Conviction
    # ========================================================================
    print("Step 3: Calculating Composite Conviction")
    print("-" * 70)

    conviction = calculate_composite_conviction(signals)
    score = conviction["conviction_score"]
    zone = conviction["zone"]

    print(f"  Conviction Score: {score}/100")
    print(f"  Zone: {zone}")
    print(f"  Exposure Range: {conviction['exposure_range']}")
    print(f"  Strongest: {conviction['strongest_component']['label']} "
          f"({conviction['strongest_component']['score']})")
    print(f"  Weakest: {conviction['weakest_component']['label']} "
          f"({conviction['weakest_component']['score']})")
    print()

    # ========================================================================
    # Step 4: Classify Pattern
    # ========================================================================
    print("Step 4: Pattern Classification")
    print("-" * 70)

    pattern = classify_pattern(signals, conviction["component_scores"], score)
    print(f"  Pattern: {pattern['label']} (match: {pattern['match_strength']}%)")
    print(f"  Description: {pattern['description']}")
    print()

    # ========================================================================
    # Step 5: Generate Allocation
    # ========================================================================
    print("Step 5: Generating Target Allocation")
    print("-" * 70)

    regime = signals.get("macro_regime", {}).get("regime", "transitional")
    target_alloc = generate_allocation(
        conviction_score=score,
        zone=zone,
        pattern=pattern["pattern"],
        regime=regime,
    )
    sizing = calculate_position_sizing(conviction_score=score, zone=zone)

    print(f"  Equity: {target_alloc['equity']}%")
    print(f"  Bonds: {target_alloc['bonds']}%")
    print(f"  Alternatives: {target_alloc['alternatives']}%")
    print(f"  Cash: {target_alloc['cash']}%")
    print(f"  Max Single Position: {sizing['max_single_position']}%")
    print()

    # ========================================================================
    # Step 6: Generate Reports
    # ========================================================================
    print("Step 6: Generating Reports")
    print("-" * 70)

    analysis = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reports_dir": args.reports_dir,
            "max_age_hours": args.max_age,
            "skills_loaded": len(reports),
            "required_count": required_count,
            "optional_count": optional_count,
            "skills_list": list(reports.keys()),
        },
        "conviction": conviction,
        "pattern": pattern,
        "allocation": {
            "target": target_alloc,
            "regime": regime,
            "pattern": pattern["pattern"],
            "zone": zone,
        },
        "position_sizing": sizing,
        "input_summary": signals,
    }

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"druckenmiller_strategy_{timestamp}.json")
    md_file = os.path.join(args.output_dir, f"druckenmiller_strategy_{timestamp}.md")

    generate_json_report(analysis, json_file)
    generate_markdown_report(analysis, md_file)

    print()
    print("=" * 70)
    print("Strategy Synthesis Complete")
    print("=" * 70)
    print(f"  Conviction: {score}/100 ({zone})")
    print(f"  Pattern: {pattern['label']}")
    print(f"  Equity Target: {target_alloc['equity']}%")
    print(f"  JSON: {json_file}")
    print(f"  Markdown: {md_file}")
    print()


if __name__ == "__main__":
    main()
