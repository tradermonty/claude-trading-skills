"""Report generation for IBD Distribution Day Monitor.

- UTF-8 only (encoding="utf-8")
- JSON uses ensure_ascii=False so Japanese explanations are preserved as-is.
- Sensitive keys are redacted via lowercase comparison (H4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# H4: lowercase only. Compared via k.lower() in SENSITIVE_KEYS.
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "fmp_api_key",
    "secret",
    "client_secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
}
REDACTED = "***REDACTED***"


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: (REDACTED if isinstance(k, str) and k.lower() in SENSITIVE_KEYS else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def write_json(payload: dict, path: str | Path) -> None:
    safe = _redact(payload)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2, default=str)


def write_markdown(payload: dict, path: str | Path) -> None:
    safe = _redact(payload)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    text = render_markdown(safe)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def render_markdown(payload: dict) -> str:
    """Render the analysis payload as a human-readable markdown report."""
    state = payload.get("market_distribution_state", {})
    action = payload.get("portfolio_action", {})
    audit = payload.get("audit", {})

    lines: list[str] = []
    lines.append("# IBD Distribution Day Monitor Report")
    lines.append("")
    lines.append(f"- **As of:** {state.get('as_of', 'N/A')}")
    lines.append(f"- **Overall Risk Level:** **{state.get('overall_risk_level', 'N/A')}**")
    lines.append(f"- **Primary Signal Symbol:** {state.get('primary_signal_symbol', 'N/A')}")
    lines.append(f"- **Generated At:** {state.get('generated_at', 'N/A')}")
    lines.append("")

    lines.append("## Index Results")
    lines.append("")
    for idx in state.get("index_results", []) or []:
        lines.append(f"### {idx.get('symbol')} — risk: **{idx.get('risk_level')}**")
        lines.append("")
        lines.append(f"- Today is Distribution Day: {idx.get('is_distribution_day_today')}")
        lines.append(
            f"- d5 / d15 / d25 = {idx.get('d5_count')} / {idx.get('d15_count')} / {idx.get('d25_count')}"
        )
        cluster = idx.get("cluster_state") or {}
        if cluster:
            lines.append(f"- Cluster: {cluster.get('cluster_description', '')}")
        trend = idx.get("trend_filters") or {}
        if trend:
            lines.append(
                "- Trend filters: "
                f"close_above_21ema={trend.get('close_above_21ema')}, "
                f"close_above_50sma={trend.get('close_above_50sma')}, "
                f"market_below_21ema_or_50ma={trend.get('market_below_21ema_or_50ma')}"
            )
        explanation = idx.get("explanation") or ""
        if explanation:
            lines.append("")
            lines.append(f"> {explanation}")

        active = idx.get("active_distribution_days") or []
        if active:
            lines.append("")
            lines.append("#### Active Distribution Days")
            lines.append("")
            lines.append(
                "| date | close | pct_change | volume_change_pct | age | expires_in |"
                " high_since | invalidation_price |"
            )
            lines.append(
                "|------|-------|------------|-------------------|-----|------------|"
                "------------|---------------------|"
            )
            for r in active:
                lines.append(
                    "| {date} | {close} | {pc} | {vc} | {age} | {exp} | {hs} | {inv} |".format(
                        date=r.get("date"),
                        close=r.get("close"),
                        pc=_fmt_pct(r.get("pct_change")),
                        vc=_fmt_pct(r.get("volume_change_pct")),
                        age=r.get("age_sessions"),
                        exp=r.get("expires_in_sessions"),
                        hs=r.get("high_since"),
                        inv=r.get("invalidation_price"),
                    )
                )
        lines.append("")

    lines.append("## Portfolio Action")
    lines.append("")
    if action:
        lines.append(f"- **Instrument:** {action.get('instrument')}")
        lines.append(f"- **Recommended Action:** {action.get('recommended_action')}")
        lines.append(
            "- **Exposure:** "
            f"current {action.get('current_exposure_pct')}% → "
            f"target {action.get('target_exposure_pct')}% "
            f"(delta {action.get('exposure_delta_pct')}%)"
        )
        lines.append(f"- **Trailing Stop:** {action.get('trailing_stop_pct')}%")
        if action.get("alternative_action"):
            lines.append(f"- **Alternative:** {action.get('alternative_action')}")
        rationale = action.get("rationale") or ""
        if rationale:
            lines.append("")
            lines.append(f"> {rationale}")
    lines.append("")

    lines.append("## Audit")
    lines.append("")
    lines.append(f"- **Data Source:** {audit.get('data_source', 'N/A')}")
    lines.append(f"- **Symbols:** {', '.join(audit.get('symbols_loaded', []) or [])}")
    unavailable = audit.get("symbols_unavailable") or []
    if unavailable:
        reasons = "; ".join(
            f"{item.get('symbol')} ({item.get('reason', 'unavailable')})"
            for item in unavailable
        )
        lines.append(f"- **Unavailable Symbols:** {reasons} (the results below exclude them)")
    for item in audit.get("instrument_identity", []):
        lines.append(
            f"- **Instrument {item['symbol']}:** {item.get('instrument_name', item['symbol'])}"
        )
    lines.append(
        "- **Evidence basis:** price and volume belong to each named symbol. ETF DD counts are not Nasdaq Composite or S&P 500 index counts."
    )
    lines.append(f"- **Audit Flags:** {audit.get('audit_flags', [])}")
    lines.append(f"- **Rule Version:** {audit.get('rule_version', 'N/A')}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _fmt_pct(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{value * 100:.2f}%"
    except (TypeError, ValueError):
        return str(value)
