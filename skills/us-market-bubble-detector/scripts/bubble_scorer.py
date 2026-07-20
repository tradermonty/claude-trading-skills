#!/usr/bin/env python3
"""
Bubble-O-Meter: evaluate US market bubble risk with the v2.1 framework.

The v2.1 model scores six quantitative indicators at 0-2 points each
(0-12 total), then applies three strict qualitative adjustments at 0-1 point
each (0-3 total). The final score is 0-15.

Usage:
    python bubble_scorer.py --manual
    python bubble_scorer.py --scores '{"put_call_ratio":0,...,"valuation_disconnect":0}'
"""

import argparse
import json
from datetime import datetime
from typing import Optional


class BubbleScorer:
    """Bubble scoring system for the revised v2.1 contract."""

    def __init__(self) -> None:
        self.quantitative_indicators = {
            "put_call_ratio": {
                "name": "Put/Call Ratio",
                "max_score": 2,
                "description": "CBOE equity put/call ratio optimism threshold",
            },
            "volatility_suppression": {
                "name": "Volatility Suppression + New Highs",
                "max_score": 2,
                "description": "Low VIX combined with major index proximity to 52-week highs",
            },
            "leverage": {
                "name": "Leverage",
                "max_score": 2,
                "description": "FINRA margin debt growth and all-time-high behavior",
            },
            "ipo_heat": {
                "name": "IPO Market Overheating",
                "max_score": 2,
                "description": "IPO count and first-day return versus five-year averages",
            },
            "breadth_anomaly": {
                "name": "Breadth Anomaly",
                "max_score": 2,
                "description": "New highs with narrow S&P 500 participation above 50DMA",
            },
            "price_acceleration": {
                "name": "Price Acceleration",
                "max_score": 2,
                "description": "Three-month return percentile versus the past 10 years",
            },
        }
        self.qualitative_adjustments = {
            "social_penetration": {
                "name": "Social Penetration",
                "max_score": 1,
                "description": "Direct, specific, repeated non-investor recommendations",
            },
            "media_search_trends": {
                "name": "Media/Search Trends",
                "max_score": 1,
                "description": "Measured 5x+ search interest plus mainstream coverage",
            },
            "valuation_disconnect": {
                "name": "Valuation Disconnect",
                "max_score": 1,
                "description": "Documented fundamentals-ignored narrative without double-counting",
            },
        }

    @property
    def indicators(self) -> dict[str, dict]:
        """Backward-compatible combined indicator map."""
        return {**self.quantitative_indicators, **self.qualitative_adjustments}

    def calculate_score(
        self,
        quantitative_scores: dict[str, int],
        qualitative_scores: Optional[dict[str, int]] = None,
    ) -> dict:
        """
        Calculate the v2.1 bubble score.

        Args:
            quantitative_scores: Scores for the six 0-2 quantitative indicators,
                or a flat combined mapping containing all nine v2.1 score keys.
            qualitative_scores: Scores for the three 0-1 qualitative adjustments.

        Returns:
            Evaluation result dictionary.
        """
        if qualitative_scores is None:
            quantitative_scores, qualitative_scores = self._split_flat_scores(quantitative_scores)

        self._validate_scores(quantitative_scores, self.quantitative_indicators)
        self._validate_scores(qualitative_scores, self.qualitative_adjustments)

        quantitative_total = sum(quantitative_scores.values())
        qualitative_total = sum(qualitative_scores.values())
        total_score = quantitative_total + qualitative_total
        max_score = self._max_score()
        phase, risk_level, risk_budget, action = self._classify_score(total_score)

        return {
            "timestamp": datetime.now().isoformat(),
            "quantitative_score": quantitative_total,
            "qualitative_adjustment": qualitative_total,
            "total_score": total_score,
            "max_score": max_score,
            "percentage": round(total_score / max_score * 100, 1),
            "phase": phase,
            "risk_level": risk_level,
            "risk_budget": risk_budget,
            "minsky_phase": self._estimate_minsky_phase(quantitative_scores, total_score),
            "recommended_action": action,
            "quantitative_scores": quantitative_scores,
            "qualitative_scores": qualitative_scores,
            "indicator_scores": {**quantitative_scores, **qualitative_scores},
            "detailed_quantitative_indicators": self._format_indicator_details(
                quantitative_scores, self.quantitative_indicators
            ),
            "detailed_qualitative_adjustments": self._format_indicator_details(
                qualitative_scores, self.qualitative_adjustments
            ),
        }

    def _max_score(self) -> int:
        return sum(item["max_score"] for item in self.indicators.values())

    def _split_flat_scores(self, scores: dict[str, int]) -> tuple[dict[str, int], dict[str, int]]:
        quantitative = {
            key: value for key, value in scores.items() if key in self.quantitative_indicators
        }
        qualitative = {
            key: value for key, value in scores.items() if key in self.qualitative_adjustments
        }
        return quantitative, qualitative

    def _validate_scores(self, scores: dict[str, int], schema: dict[str, dict]) -> None:
        expected = set(schema)
        actual = set(scores)
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        if missing:
            raise ValueError(f"Missing score(s): {', '.join(missing)}")
        if unknown:
            raise ValueError(f"Unknown score(s): {', '.join(unknown)}")

        for key, value in scores.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{key} must be an integer")
            max_score = schema[key]["max_score"]
            if not 0 <= value <= max_score:
                raise ValueError(f"{key} must be between 0 and {max_score}")

    def _classify_score(self, total_score: int) -> tuple[str, str, str, str]:
        if total_score <= 4:
            return ("Normal", "Low", "100%", "Continue normal investment strategy")
        if total_score <= 7:
            return ("Caution", "Medium", "70-80%", "Start partial profit-taking and reduce sizing")
        if total_score <= 9:
            return (
                "Elevated Risk",
                "Medium-High",
                "50-70%",
                "Reduce risk budget and tighten trailing stops",
            )
        if total_score <= 12:
            return (
                "Euphoria",
                "High",
                "40-50%",
                "Accelerate staged profit-taking and reduce total risk budget",
            )
        return (
            "Critical",
            "Extreme",
            "20-30%",
            "Prioritize major profit-taking, hedging, and halt new entries",
        )

    def _estimate_minsky_phase(self, quantitative_scores: dict[str, int], total: int) -> str:
        price_acceleration = quantitative_scores.get("price_acceleration", 0)
        volatility = quantitative_scores.get("volatility_suppression", 0)
        breadth = quantitative_scores.get("breadth_anomaly", 0)

        if total <= 4:
            return "Displacement/Early Boom"
        if total <= 7:
            if price_acceleration >= 1 and volatility >= 1:
                return "Boom"
            return "Displacement/Early Boom"
        if total <= 9:
            return "Late Boom/Elevated Risk"
        if total <= 12:
            if price_acceleration >= 2 and breadth >= 2:
                return "Euphoria"
            return "Late Boom/Early Euphoria"
        return "Peak Euphoria/Profit Taking"

    def _format_indicator_details(
        self, scores: dict[str, int], schema: dict[str, dict]
    ) -> list[dict]:
        details = []
        for key, value in scores.items():
            indicator = schema[key]
            max_score = indicator["max_score"]
            if value == max_score:
                status = "high"
            elif value > 0:
                status = "medium"
            else:
                status = "low"
            details.append(
                {
                    "indicator": indicator["name"],
                    "score": value,
                    "max_score": max_score,
                    "status": status,
                    "description": indicator["description"],
                }
            )
        return details

    def get_scoring_guidelines(self) -> str:
        """Return concise scoring guidance for manual input."""
        return """
## Bubble-O-Meter v2.1 scoring keys

Quantitative indicators (0-2 each):
- put_call_ratio: 2 if P/C < 0.70, 1 if 0.70-0.85, 0 if > 0.85.
- volatility_suppression: 2 if VIX < 12 and index within 5% of highs,
  1 if VIX 12-15 and near highs, otherwise 0.
- leverage: 2 if margin debt YoY +20% and all-time high, 1 if +10-20%, otherwise 0.
- ipo_heat: 2 if IPO count >2x five-year average and first-day return +20%,
  1 if count >1.5x, otherwise 0.
- breadth_anomaly: 2 if new high and <45% above 50DMA, 1 if 45-60%, otherwise 0.
- price_acceleration: 2 if three-month return >95th percentile,
  1 if 85-95th percentile, otherwise 0.

Qualitative adjustments (0-1 each; +3 maximum):
- social_penetration: +1 only with direct, specific, repeated non-investor reports.
- media_search_trends: +1 only with measured 5x+ search trends plus mainstream coverage.
- valuation_disconnect: +1 only with documented fundamentals-ignored narrative.
"""

    def format_output(self, result: dict) -> str:
        """Format results for CLI display."""
        lines = [
            "=" * 60,
            "US Market Bubble Risk - Bubble-O-Meter v2.1",
            "=" * 60,
            f"Evaluated at: {result['timestamp']}",
            "",
            f"Quantitative: {result['quantitative_score']}/12",
            f"Qualitative adjustment: +{result['qualitative_adjustment']}/3",
            f"Final score: {result['total_score']}/{result['max_score']} ({result['percentage']}%)",
            f"Phase: {result['phase']} (Risk: {result['risk_level']})",
            f"Risk budget: {result['risk_budget']}",
            f"Minsky phase: {result['minsky_phase']}",
            f"Recommended action: {result['recommended_action']}",
            "",
            "Quantitative indicators:",
        ]
        for detail in result["detailed_quantitative_indicators"]:
            lines.append(
                f"- {detail['indicator']}: {detail['score']}/{detail['max_score']} "
                f"({detail['status']})"
            )
        lines.append("")
        lines.append("Qualitative adjustments:")
        for detail in result["detailed_qualitative_adjustments"]:
            lines.append(
                f"- {detail['indicator']}: +{detail['score']}/{detail['max_score']} "
                f"({detail['status']})"
            )
        lines.append("=" * 60)
        return "\n".join(lines)


def manual_assessment() -> dict[str, int]:
    """Collect manual v2.1 scores interactively."""
    scorer = BubbleScorer()
    print("\n" + "=" * 60)
    print("US Market Bubble Risk - Manual Assessment v2.1")
    print("=" * 60)
    print(scorer.get_scoring_guidelines())

    scores = {}
    for key, indicator in scorer.indicators.items():
        max_score = indicator["max_score"]
        while True:
            try:
                score = int(input(f"\n{indicator['name']} (0-{max_score}): "))
                if 0 <= score <= max_score:
                    scores[key] = score
                    break
                print(f"Enter a value between 0 and {max_score}")
            except ValueError:
                print("Enter a numeric value")
    return scores


def _scores_from_json(raw_scores: str) -> tuple[dict[str, int], Optional[dict[str, int]]]:
    parsed = json.loads(raw_scores)
    if not isinstance(parsed, dict):
        raise ValueError("--scores must be a JSON object")
    if "quantitative" in parsed or "qualitative" in parsed:
        quantitative = parsed.get("quantitative", {})
        qualitative = parsed.get("qualitative", {})
        if not isinstance(quantitative, dict) or not isinstance(qualitative, dict):
            raise ValueError("nested scores must use object values")
        return quantitative, qualitative
    return parsed, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate US market bubble risk with v2.1.")
    parser.add_argument("--manual", action="store_true", help="Run interactive manual scoring")
    parser.add_argument(
        "--scores",
        type=str,
        help="JSON score object, either flat or {'quantitative': {...}, 'qualitative': {...}}",
    )
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format")

    args = parser.parse_args()
    scorer = BubbleScorer()

    if args.manual:
        quantitative_scores, qualitative_scores = _scores_from_json(json.dumps(manual_assessment()))
    elif args.scores:
        try:
            quantitative_scores, qualitative_scores = _scores_from_json(args.scores)
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"Error: {exc}")
            return 1
    else:
        print("Error: specify --manual or --scores")
        print("\nGuidelines:")
        print(scorer.get_scoring_guidelines())
        return 1

    try:
        result = scorer.calculate_score(quantitative_scores, qualitative_scores)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    if args.output == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(scorer.format_output(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
