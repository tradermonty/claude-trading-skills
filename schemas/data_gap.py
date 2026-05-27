"""
Data gap utility for TraderMonty skills.

Skills use DataGapCollector to accumulate DataGap records as they run,
then embed the collected gaps in their output artifact.

Usage
-----
    from schemas.data_gap import DataGapCollector

    collector = DataGapCollector(skill_id="vcp-screener")

    if not api_key:
        collector.add(
            severity="CRITICAL",
            description="FMP_API_KEY not set",
            affected_decision="All screening results",
            remediation="Set FMP_API_KEY environment variable and retry",
            can_continue=False,
            source="environment",
        )

    # Embed in output
    artifact["data_gaps"] = collector.to_list()
    artifact["confidence"] = collector.derive_confidence()
"""

from __future__ import annotations

import uuid
from typing import Literal

# Keep this file independent of the full Pydantic models so it can be imported
# in skill scripts that may not have pydantic installed as a runtime dep.
# The returned dicts are schema-compatible with DataGap.

SeverityLiteral = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _confidence_from_severity(max_severity: str | None) -> str:
    if max_severity is None:
        return "HIGH"
    rank = _SEVERITY_RANK.get(max_severity, 0)
    if rank >= 3:
        return "LOW"
    if rank >= 2:
        return "MEDIUM"
    return "HIGH"


class DataGapCollector:
    """
    Accumulate DataGap records during skill execution.

    Call .add() whenever data is missing, stale, or unreliable.
    Call .to_list() to get the list of dicts for embedding in the artifact.
    Call .derive_confidence() to get HIGH/MEDIUM/LOW based on worst gap.
    Call .can_continue() to check whether any CRITICAL gap was recorded.
    """

    def __init__(self, skill_id: str) -> None:
        self.skill_id = skill_id
        self._gaps: list[dict] = []

    def add(
        self,
        severity: SeverityLiteral,
        description: str,
        affected_decision: str,
        remediation: str,
        can_continue: bool,
        source: str | None = None,
    ) -> None:
        """Record a data gap."""
        self._gaps.append(
            {
                "gap_id": str(uuid.uuid4())[:8],
                "severity": severity,
                "description": description,
                "affected_decision": affected_decision,
                "remediation": remediation,
                "can_continue": can_continue,
                "source": source or self.skill_id,
            }
        )

    def add_api_key_missing(self, api_name: str, env_var: str) -> None:
        """Convenience: record a CRITICAL gap for a missing API key."""
        self.add(
            severity="CRITICAL",
            description=f"{api_name} API key not set",
            affected_decision=f"All outputs requiring {api_name}",
            remediation=f"Set {env_var} environment variable and retry",
            can_continue=False,
            source="environment",
        )

    def add_api_empty_response(
        self, api_name: str, endpoint: str, symbol: str | None = None
    ) -> None:
        """Convenience: record a HIGH gap for an empty API response."""
        sym_str = f" for {symbol}" if symbol else ""
        self.add(
            severity="HIGH",
            description=f"{api_name} returned empty response from {endpoint}{sym_str}",
            affected_decision=f"Signal components depending on {endpoint}",
            remediation=(
                f"Check {api_name} API tier limits and daily call budget; "
                "verify the symbol/endpoint is valid; retry during market hours"
            ),
            can_continue=False,
            source=api_name.lower().replace(" ", "_"),
        )

    def add_stale_data(
        self, source: str, age_days: float, threshold_days: float
    ) -> None:
        """Convenience: record a gap for stale data."""
        severity: SeverityLiteral = "HIGH" if age_days > threshold_days * 2 else "MEDIUM"
        self.add(
            severity=severity,
            description=f"{source} data is {age_days:.1f} days old (threshold: {threshold_days} days)",
            affected_decision="Time-sensitive signal components",
            remediation=f"Re-run data fetch for {source}; check upstream data source availability",
            can_continue=True,
            source=source,
        )

    def add_small_sample(self, n_trades: int, minimum: int = 30) -> None:
        """Convenience: record a gap for small backtest sample."""
        severity: SeverityLiteral = "HIGH" if n_trades < minimum else "MEDIUM"
        self.add(
            severity=severity,
            description=(
                f"Backtest sample size is {n_trades} trades "
                f"(minimum recommended: {minimum})"
            ),
            affected_decision="Strategy validity conclusions and out-of-sample requirements",
            remediation=(
                "Extend the backtest period, widen the universe, "
                "or reduce parameter specificity to increase sample size"
            ),
            can_continue=True,
            source="backtest_engine",
        )

    def add_low_liquidity(self, ticker: str, avg_volume: int, threshold: int = 500_000) -> None:
        """Convenience: record a HIGH gap for insufficient liquidity."""
        severity: SeverityLiteral = "CRITICAL" if avg_volume < 100_000 else "HIGH"
        self.add(
            severity=severity,
            description=(
                f"{ticker} average daily volume ({avg_volume:,}) "
                f"is below threshold ({threshold:,})"
            ),
            affected_decision="Trade plan feasibility and position sizing",
            remediation=f"Exclude {ticker} from trade plan candidates; use for research only",
            can_continue=severity == "HIGH",
            source="liquidity_check",
        )

    def to_list(self) -> list[dict]:
        """Return all gap records as a list of dicts (schema-compatible with DataGap)."""
        return list(self._gaps)

    def derive_confidence(self) -> str:
        """Return HIGH / MEDIUM / LOW based on the worst gap severity."""
        if not self._gaps:
            return "HIGH"
        worst = max(
            (g["severity"] for g in self._gaps),
            key=lambda s: _SEVERITY_RANK.get(s, 0),
        )
        return _confidence_from_severity(worst)

    def can_continue(self) -> bool:
        """Return False if any CRITICAL gap or any non-continuable gap was recorded."""
        return all(g["can_continue"] for g in self._gaps)

    def has_critical(self) -> bool:
        """Return True if any CRITICAL gap was recorded."""
        return any(g["severity"] == "CRITICAL" for g in self._gaps)

    def summary(self) -> str:
        """One-line summary for logging."""
        if not self._gaps:
            return "No data gaps"
        counts = {}
        for g in self._gaps:
            counts[g["severity"]] = counts.get(g["severity"], 0) + 1
        parts = [f"{s}:{n}" for s, n in sorted(counts.items(), key=lambda x: -_SEVERITY_RANK[x[0]])]
        return f"{len(self._gaps)} data gap(s): {', '.join(parts)}"

    def __len__(self) -> int:
        return len(self._gaps)

    def __bool__(self) -> bool:
        return bool(self._gaps)
