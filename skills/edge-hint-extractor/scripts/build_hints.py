#!/usr/bin/env python3
"""Build edge hints from market observations, news reactions, and optional LLM ideas."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_ENTRY_FAMILIES = {"pivot_breakout", "gap_up_continuation"}


class HintExtractionError(Exception):
    """Raised when hint extraction fails."""


def parse_as_of(raw: str | None) -> date | None:
    """Parse YYYY-MM-DD into a date object."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HintExtractionError(f"invalid --as-of format: {raw}") from exc


def safe_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float conversion."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_json(path: Path) -> Any:
    """Read JSON file."""
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HintExtractionError(f"invalid JSON: {path}") from exc


def read_market_summary(path: Path | None) -> dict[str, Any]:
    """Load market summary JSON."""
    if path is None:
        return {}
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise HintExtractionError(f"market summary must be an object: {path}")
    return payload


def read_anomalies(path: Path | None) -> list[dict[str, Any]]:
    """Load anomalies JSON list."""
    if path is None:
        return []
    payload = read_json(path)
    if not isinstance(payload, list):
        raise HintExtractionError(f"anomalies must be a JSON list: {path}")
    return [item for item in payload if isinstance(item, dict)]


def parse_timestamp_to_date(value: str | None) -> date | None:
    """Parse ISO timestamp into date."""
    if not value or not isinstance(value, str):
        return None
    fixed = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(fixed).date()
    except ValueError:
        return None


def normalize_news_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one news reaction row."""
    symbol = str(row.get("symbol", "")).strip().upper()
    if not symbol:
        return None
    return {
        "symbol": symbol,
        "timestamp": str(row.get("timestamp", "")).strip(),
        "reaction_1d": safe_float(row.get("reaction_1d")),
        "headline": str(row.get("headline", "")).strip(),
    }


def read_news_reactions(path: Path | None, as_of: date | None) -> list[dict[str, Any]]:
    """Load news reactions from CSV or JSON."""
    if path is None:
        return []

    rows: list[dict[str, Any]] = []
    suffix = path.suffix.lower()

    if suffix == ".csv":
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                if not isinstance(raw, dict):
                    continue
                normalized = normalize_news_row(raw)
                if normalized is not None:
                    rows.append(normalized)
    elif suffix == ".json":
        payload = read_json(path)
        if isinstance(payload, dict):
            data = payload.get("rows") or payload.get("data") or payload.get("news") or []
        elif isinstance(payload, list):
            data = payload
        else:
            raise HintExtractionError(f"unsupported JSON news format: {path}")

        for raw in data:
            if not isinstance(raw, dict):
                continue
            normalized = normalize_news_row(raw)
            if normalized is not None:
                rows.append(normalized)
    else:
        raise HintExtractionError(f"unsupported news reactions format: {path}")

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if as_of is not None:
            row_date = parse_timestamp_to_date(row.get("timestamp"))
            if row_date is not None and row_date != as_of:
                continue
        filtered.append(row)

    filtered.sort(key=lambda item: abs(safe_float(item.get("reaction_1d"))), reverse=True)
    return filtered


def infer_regime_label(market_summary: dict[str, Any]) -> str:
    """Infer regime label when not explicitly provided."""
    raw = market_summary.get("regime_label")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    risk_on = safe_float(market_summary.get("risk_on_score"))
    risk_off = safe_float(market_summary.get("risk_off_score"))
    if risk_on >= risk_off + 10:
        return "RiskOn"
    if risk_off >= risk_on + 10:
        return "RiskOff"
    return "Neutral"


def normalize_hint(raw_hint: dict[str, Any]) -> dict[str, Any]:
    """Normalize user/LLM/rule hint into canonical schema."""
    title = str(raw_hint.get("title") or raw_hint.get("observation") or "untitled_hint").strip()
    observation = str(raw_hint.get("observation") or title).strip()

    raw_family = raw_hint.get("preferred_entry_family")
    if isinstance(raw_family, str) and raw_family in SUPPORTED_ENTRY_FAMILIES:
        preferred_entry_family: str | None = raw_family
    else:
        preferred_entry_family = None

    symbols_input = raw_hint.get("symbols", [])
    symbols: list[str] = []
    if isinstance(symbols_input, list):
        seen: set[str] = set()
        for symbol in symbols_input:
            if not isinstance(symbol, str):
                continue
            normalized = symbol.strip().upper()
            if normalized and normalized not in seen:
                seen.add(normalized)
                symbols.append(normalized)

    normalized_hint = {
        "title": title,
        "observation": observation,
        "symbols": symbols,
        "regime_bias": str(raw_hint.get("regime_bias", "")).strip(),
        "mechanism_tag": str(raw_hint.get("mechanism_tag", "")).strip() or "behavior",
    }
    if preferred_entry_family is not None:
        normalized_hint["preferred_entry_family"] = preferred_entry_family
    raw_hypothesis = raw_hint.get("hypothesis_type")
    if isinstance(raw_hypothesis, str) and raw_hypothesis.strip():
        normalized_hint["hypothesis_type"] = raw_hypothesis.strip()
    return normalized_hint


def build_rule_hints(
    market_summary: dict[str, Any],
    anomalies: list[dict[str, Any]],
    news_rows: list[dict[str, Any]],
    max_anomaly_hints: int,
    news_threshold: float,
) -> list[dict[str, Any]]:
    """Generate deterministic hints from inputs."""
    regime = infer_regime_label(market_summary)
    hints: list[dict[str, Any]] = []

    breadth = safe_float(market_summary.get("pct_above_ma50"))
    vol_trend = safe_float(market_summary.get("vol_trend"), default=1.0)

    if regime == "RiskOn":
        hints.append(
            normalize_hint(
                {
                    "title": "Breadth-supported breakout regime",
                    "observation": (
                        f"Risk-on regime with pct_above_ma50={breadth:.3f} and vol_trend={vol_trend:.3f}."
                    ),
                    "hypothesis_type": "breakout",
                    "preferred_entry_family": "pivot_breakout",
                    "regime_bias": regime,
                    "mechanism_tag": "behavior",
                }
            )
        )
    elif regime == "RiskOff":
        hints.append(
            normalize_hint(
                {
                    "title": "Risk-off selectivity",
                    "observation": "Risk-off conditions suggest defensive and confirmation-based entries.",
                    "hypothesis_type": "regime_shift",
                    "regime_bias": regime,
                    "mechanism_tag": "risk_premium",
                }
            )
        )

    sorted_anomalies = sorted(
        [item for item in anomalies if isinstance(item, dict)],
        key=lambda item: abs(safe_float(item.get("z"), safe_float(item.get("abs_z")))),
        reverse=True,
    )

    for anomaly in sorted_anomalies[: max(max_anomaly_hints, 0)]:
        symbol = str(anomaly.get("symbol", "")).upper().strip()
        metric = str(anomaly.get("metric", "")).strip().lower()
        z_score = safe_float(anomaly.get("z"), safe_float(anomaly.get("abs_z")))
        if not symbol:
            continue

        if metric == "gap" and z_score >= 2.5:
            hints.append(
                normalize_hint(
                    {
                        "title": f"Positive gap shock in {symbol}",
                        "observation": f"{symbol} printed a large positive gap anomaly (z={z_score:.2f}).",
                        "hypothesis_type": "breakout",
                        "preferred_entry_family": "gap_up_continuation",
                        "symbols": [symbol],
                        "regime_bias": regime,
                        "mechanism_tag": "behavior",
                    }
                )
            )
        elif metric == "gap" and z_score <= -2.5:
            hints.append(
                normalize_hint(
                    {
                        "title": f"Downside overreaction watch in {symbol}",
                        "observation": f"{symbol} showed a negative gap anomaly (z={z_score:.2f}).",
                        "hypothesis_type": "panic_reversal",
                        "symbols": [symbol],
                        "regime_bias": regime,
                        "mechanism_tag": "behavior",
                    }
                )
            )
        elif metric == "rel_volume" and abs(z_score) >= 2.5:
            hints.append(
                normalize_hint(
                    {
                        "title": f"Participation spike in {symbol}",
                        "observation": f"Relative volume anomaly detected (z={z_score:.2f}).",
                        "hypothesis_type": "breakout",
                        "preferred_entry_family": "pivot_breakout",
                        "symbols": [symbol],
                        "regime_bias": regime,
                        "mechanism_tag": "flow",
                    }
                )
            )

    for row in news_rows:
        reaction = safe_float(row.get("reaction_1d"))
        if abs(reaction) < news_threshold:
            continue
        symbol = str(row.get("symbol", "")).upper().strip()
        if not symbol:
            continue

        if reaction >= 0:
            raw_hint = {
                "title": f"News drift continuation in {symbol}",
                "observation": f"{symbol} reacted +{reaction:.3f} on event day; monitor continuation.",
                "hypothesis_type": "news_reaction",
                "preferred_entry_family": "gap_up_continuation",
                "symbols": [symbol],
                "regime_bias": regime,
                "mechanism_tag": "behavior",
            }
        else:
            raw_hint = {
                "title": f"News shock reversal in {symbol}",
                "observation": f"{symbol} reacted {reaction:.3f} on event day; monitor overshoot reversal.",
                "hypothesis_type": "news_reaction",
                "symbols": [symbol],
                "regime_bias": regime,
                "mechanism_tag": "behavior",
            }
        hints.append(normalize_hint(raw_hint))

    return hints


def parse_hints_payload(raw_payload: Any) -> list[dict[str, Any]]:
    """Parse hint payload from YAML/JSON output."""
    if raw_payload is None:
        return []
    if isinstance(raw_payload, list):
        raw_hints = raw_payload
    elif isinstance(raw_payload, dict):
        maybe_hints = raw_payload.get("hints", [])
        raw_hints = maybe_hints if isinstance(maybe_hints, list) else []
    else:
        raise HintExtractionError("LLM output must be list or {hints: [...]}")

    normalized: list[dict[str, Any]] = []
    for raw in raw_hints:
        if not isinstance(raw, dict):
            continue
        normalized.append(normalize_hint(raw))
    return normalized


def generate_llm_hints(llm_command: str | None, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate hints from external LLM command."""
    if not llm_command:
        return []

    command_parts = shlex.split(llm_command)
    if not command_parts:
        raise HintExtractionError("--llm-ideas-cmd is empty")

    result = subprocess.run(
        command_parts,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise HintExtractionError(f"LLM ideas command failed: {detail}")

    stdout = result.stdout.strip()
    if not stdout:
        return []

    parsed = yaml.safe_load(stdout)
    return parse_hints_payload(parsed)


def load_llm_hints_from_file(path: Path) -> list[dict[str, Any]]:
    """Load LLM-generated hints from a pre-written YAML file."""
    text = path.read_text().strip()
    if not text:
        return []
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HintExtractionError(f"invalid YAML in --llm-ideas-file {path}: {exc}") from exc
    return parse_hints_payload(parsed)


def dedupe_hints(hints: list[dict[str, Any]], max_total: int) -> list[dict[str, Any]]:
    """Deduplicate hints by semantic identity."""
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, tuple[str, ...], str, str]] = set()

    for hint in hints:
        title = str(hint.get("title", "")).strip().lower()
        hypothesis = str(hint.get("hypothesis_type", "")).strip().lower()
        family = str(hint.get("preferred_entry_family", "")).strip().lower()
        symbols = tuple(str(item).upper() for item in hint.get("symbols", []))
        regime = str(hint.get("regime_bias", "")).strip().lower()
        mechanism = str(hint.get("mechanism_tag", "")).strip().lower()
        key = (title, hypothesis, family, symbols, regime, mechanism)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hint)
        if len(deduped) >= max(max_total, 0):
            break

    return deduped


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(
        description="Build hints.yaml from market observations/news with optional LLM augmentation.",
    )
    parser.add_argument("--market-summary", default=None, help="Optional market_summary.json path")
    parser.add_argument("--anomalies", default=None, help="Optional anomalies.json path")
    parser.add_argument(
        "--news-reactions",
        default=None,
        help="Optional news reactions CSV/JSON path with symbol,timestamp,reaction_1d",
    )
    parser.add_argument(
        "--as-of", default=None, help="Target date YYYY-MM-DD for filtering news rows"
    )
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument("--llm-ideas-cmd", default=None, help="Optional external LLM command")
    llm_group.add_argument(
        "--llm-ideas-file",
        default=None,
        metavar="PATH",
        help="Pre-written YAML file of LLM hints (use from Claude Code)",
    )
    parser.add_argument(
        "--max-anomaly-hints", type=int, default=8, help="Max anomaly-derived hints"
    )
    parser.add_argument(
        "--news-threshold", type=float, default=0.06, help="Min abs(reaction_1d) for hints"
    )
    parser.add_argument("--max-total-hints", type=int, default=25, help="Max total hints to output")
    parser.add_argument(
        "--output-dir",
        default="reports/",
        help="Output directory (default: reports/)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output hints YAML path (overrides --output-dir if specified)",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()

    market_summary_path = Path(args.market_summary).resolve() if args.market_summary else None
    anomalies_path = Path(args.anomalies).resolve() if args.anomalies else None
    news_path = Path(args.news_reactions).resolve() if args.news_reactions else None
    as_of = parse_as_of(args.as_of)

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_dir = Path(args.output_dir).resolve()
        output_path = output_dir / "edge_hint_extractor" / "hints.yaml"

    for path in [market_summary_path, anomalies_path, news_path]:
        if path is not None and not path.exists():
            print(f"[ERROR] file not found: {path}")
            return 1

    try:
        market_summary = read_market_summary(market_summary_path)
        anomalies = read_anomalies(anomalies_path)
        news_rows = read_news_reactions(news_path, as_of=as_of)

        rule_hints = build_rule_hints(
            market_summary=market_summary,
            anomalies=anomalies,
            news_rows=news_rows,
            max_anomaly_hints=max(args.max_anomaly_hints, 0),
            news_threshold=max(args.news_threshold, 0.0),
        )

        llm_payload = {
            "as_of": as_of.isoformat() if as_of else None,
            "market_summary": market_summary,
            "anomalies": anomalies[:20],
            "news_reactions": news_rows[:20],
            "instruction": (
                "Generate concise edge hints with fields: title, observation, "
                "hypothesis_type(optional: breakout|earnings_drift|news_reaction|"
                "futures_trigger|calendar_anomaly|panic_reversal|regime_shift|sector_x_stock), "
                "preferred_entry_family(optional), symbols(optional), "
                "regime_bias(optional), mechanism_tag(optional)."
            ),
        }
        if args.llm_ideas_file:
            llm_hints_path = Path(args.llm_ideas_file).resolve()
            if not llm_hints_path.exists():
                print(f"[ERROR] --llm-ideas-file not found: {llm_hints_path}")
                return 1
            llm_hints = load_llm_hints_from_file(llm_hints_path)
        else:
            llm_hints = generate_llm_hints(args.llm_ideas_cmd, llm_payload)

        hints = dedupe_hints(rule_hints + llm_hints, max_total=max(args.max_total_hints, 0))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_payload = {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "as_of": as_of.isoformat() if as_of else None,
            "hints": hints,
            "meta": {
                "rule_hints": len(rule_hints),
                "llm_hints": len(llm_hints),
                "total_hints": len(hints),
                "regime": infer_regime_label(market_summary),
            },
        }
        output_path.write_text(yaml.safe_dump(output_payload, sort_keys=False))
    except HintExtractionError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[OK] hints={len(hints)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
