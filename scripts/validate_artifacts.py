"""
validate_artifacts.py — Machine-checkable artifact output correctness.

Validates that JSON artifact files produced by TraderMonty skills conform to:
  AV001  artifact_type must reference a registered schema ID
  AV002  manual_review_required must be True for trade-planning artifacts
  AV003  artifact filename must follow the naming convention
  AV004  schema_version field must be present
  AV005  manual_review_status must be a valid ManualReviewStatus value
  AV006  JSON schema file defaults must match Pydantic model defaults (consistency check)

Usage
-----
    # Validate one artifact file
    python scripts/validate_artifacts.py reports/trade_plan_2026-05-27.json

    # Validate all artifact JSON files under reports/
    python scripts/validate_artifacts.py --all

    # Check schema consistency only (no artifact files needed)
    python scripts/validate_artifacts.py --check-schemas
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

SCHEMAS_JSON_DIR = REPO_ROOT / "schemas" / "json"

# Artifact types that always require manual_review_required=True
_TRADE_ARTIFACT_TYPES = frozenset({
    "trade_plan",
    "trade_thesis",
    "screen_candidate",
    "position_sizing_plan",
    "technical_validation",
    "exposure_decision",
    "portfolio_review",
    "dividend_review",
    "backtest_report",
    "strategy_review",
    "postmortem_report",
})

# Filename convention: <skill_id>_<artifact_type>_YYYY-MM-DD[_suffix].json
# or <artifact_type>_YYYY-MM-DD[_suffix].json
_FILENAME_RE = re.compile(
    r"^[a-z0-9][a-z0-9_-]*_\d{4}-\d{2}-\d{2}(_\d{6}|_[a-z0-9]+)?\.json$",
    re.IGNORECASE,
)

_VALID_REVIEW_STATUSES = frozenset({"PENDING", "IN_REVIEW", "APPROVED", "REJECTED", "WAIVED"})

# ---------------------------------------------------------------------------
# Forbidden language patterns (FL series)
# ---------------------------------------------------------------------------
# These phrases imply guaranteed outcomes, risk-free returns, or automatic
# execution — all of which are prohibited in TraderMonty output artifacts.
# Pattern format: (regex_pattern, plain_english_description)
_FORBIDDEN_PHRASES: list[tuple[str, str]] = [
    (r"\bguaranteed\s+(profits?|returns?|gains?|wins?|income|yield|money)\b",
     "guaranteed profit/return claim"),
    (r"\b(sure\s+wins?|sure\s+thing|can(not|'t)\s+lose|no\s+way\s+to\s+lose)\b",
     "sure-win / cannot-lose claim"),
    (r"\b(risk.free|zero.risk|no.risk)\b(?!\s+(disclosure|rate\b))",
     "risk-free / zero-risk claim"),
    (r"\b(place\s+this\s+trade\s+automatically|auto.execut\w*|execut\w+\s+automatically|"
     r"trades?\s+automatically|automatically\s+place|auto.trade\b)",
     "automatic trade execution claim"),
    (r"\b(100\s*%\s+accurate|always\s+profitable|never\s+los[es]|always\s+wins?)\b",
     "100% accuracy / always profitable claim"),
    (r"\b(print\s+money|money.printing\s+machine|infinite\s+returns?)\b",
     "hyperbolic profit claim"),
]

import re as _re
_FORBIDDEN_RE = _re.compile(
    "|".join(f"(?P<g{i}>{p})" for i, (p, _) in enumerate(_FORBIDDEN_PHRASES)),
    _re.IGNORECASE,
)

# Depth-limited text field extraction: scan string values in an artifact dict
def _extract_text_fields(data: dict, max_depth: int = 3) -> list[tuple[str, str]]:
    """Yield (field_path, text) for all string values in the artifact dict."""
    results: list[tuple[str, str]] = []

    def _walk(obj: object, path: str, depth: int) -> None:
        if depth > max_depth:
            return
        if isinstance(obj, str) and obj:
            results.append((path, obj))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, f"{path}.{k}" if path else k, depth + 1)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _walk(item, f"{path}[{i}]", depth + 1)

    _walk(data, "", 0)
    return results

# Backtest validation statuses that require a spec_artifact_id for lineage tracing
_BACKTEST_STATUSES_REQUIRING_SPEC = frozenset({
    "IN_SAMPLE_ONLY", "OUT_OF_SAMPLE_PASSED", "OUT_OF_SAMPLE_FAILED"
})

# Research quality score below which a PASS verdict is suspicious
_STRATEGY_PASS_MIN_RESEARCH_QUALITY = 60.0


@dataclass
class ArtifactFinding:
    code: str
    severity: str  # "error" | "warning"
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] [{self.severity.upper()}] {self.path}: {self.message}"


def _load_known_schema_ids() -> frozenset[str]:
    index_path = SCHEMAS_JSON_DIR / "index.json"
    if not index_path.is_file():
        return frozenset()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    return frozenset(e["artifact_type"] for e in index)


def validate_artifact_file(path: Path, known_schema_ids: frozenset[str] | None = None) -> list[ArtifactFinding]:
    """Validate a single artifact JSON file. Returns list of findings (empty = clean)."""
    if known_schema_ids is None:
        known_schema_ids = _load_known_schema_ids()

    findings: list[ArtifactFinding] = []
    try:
        location = str(path.relative_to(REPO_ROOT))
    except ValueError:
        location = str(path)

    # Load the JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        findings.append(ArtifactFinding("AV000", "error", location, f"Cannot parse artifact JSON: {exc}"))
        return findings

    if not isinstance(data, dict):
        findings.append(ArtifactFinding("AV000", "error", location, "Artifact must be a JSON object"))
        return findings

    # AV001: artifact_type must be registered
    artifact_type = data.get("artifact_type")
    if not artifact_type:
        findings.append(ArtifactFinding(
            "AV001", "error", location,
            "Missing 'artifact_type' field — every artifact must declare its canonical type"
        ))
    elif known_schema_ids and artifact_type not in known_schema_ids:
        findings.append(ArtifactFinding(
            "AV001", "error", location,
            f"artifact_type '{artifact_type}' is not in schemas/json/index.json"
        ))

    # AV002: manual_review_required must be True for trade-planning artifacts
    if artifact_type in _TRADE_ARTIFACT_TYPES:
        mrr = data.get("manual_review_required")
        if mrr is not True:
            findings.append(ArtifactFinding(
                "AV002", "error", location,
                f"artifact_type '{artifact_type}' must have manual_review_required=true "
                f"(got {mrr!r})"
            ))

    # AV003: filename convention
    if not _FILENAME_RE.match(path.name):
        findings.append(ArtifactFinding(
            "AV003", "warning", location,
            f"Filename '{path.name}' does not follow the naming convention "
            f"'<prefix>_YYYY-MM-DD[_suffix].json' — consider renaming for traceability"
        ))

    # AV004: schema_version must be present
    if "schema_version" not in data:
        findings.append(ArtifactFinding(
            "AV004", "warning", location,
            "Missing 'schema_version' field — artifacts should declare their schema version"
        ))

    # AV005: manual_review_status must be valid
    mrs = data.get("manual_review_status")
    if mrs is not None and mrs not in _VALID_REVIEW_STATUSES:
        findings.append(ArtifactFinding(
            "AV005", "error", location,
            f"manual_review_status '{mrs}' is not a valid value "
            f"({', '.join(sorted(_VALID_REVIEW_STATUSES))})"
        ))

    # AV007: CRITICAL blocking data gaps must not be paired with HIGH/MEDIUM confidence
    confidence = data.get("confidence")
    if confidence in ("HIGH", "MEDIUM"):
        blocking_critical = [
            g for g in data.get("data_gaps", [])
            if isinstance(g, dict)
            and g.get("severity") == "CRITICAL"
            and g.get("can_continue") is False
        ]
        if blocking_critical:
            findings.append(ArtifactFinding(
                "AV007", "error", location,
                f"Artifact has {len(blocking_critical)} CRITICAL blocking data gap(s) "
                f"but confidence='{confidence}'. "
                f"CRITICAL gaps require confidence='LOW' or None to prevent "
                f"overconfident downstream decisions. "
                f"Gap: {blocking_critical[0].get('description', '?')!r}"
            ))

    # -------------------------------------------------------------------
    # Forbidden language (FL series)
    # -------------------------------------------------------------------

    # FL001: Artifact text fields must not contain forbidden profit/execution claims
    for field_path, text in _extract_text_fields(data):
        m = _FORBIDDEN_RE.search(text)
        if m:
            # Identify which group matched to get the description
            desc = "forbidden language"
            for i, (_, human_desc) in enumerate(_FORBIDDEN_PHRASES):
                if m.group(f"g{i}") is not None:
                    desc = human_desc
                    break
            findings.append(ArtifactFinding(
                "FL001", "error", location,
                f"Forbidden language in field '{field_path}': "
                f"{desc!r} — matched {m.group()!r}. "
                f"TraderMonty outputs must not imply guaranteed outcomes, "
                f"risk-free returns, or automatic execution."
            ))
            break  # One FL001 per artifact is sufficient

    # -------------------------------------------------------------------
    # No-lookahead / leakage controls (NK series)
    # -------------------------------------------------------------------

    # NK001: BacktestSpec must declare no_lookahead_confirmed before being used
    if artifact_type == "backtest_spec":
        if data.get("no_lookahead_confirmed") is not True:
            findings.append(ArtifactFinding(
                "NK001", "warning", location,
                "BacktestSpec.no_lookahead_confirmed is not True. "
                "Set this field only after completing the No-Lookahead Checklist "
                "(all 8 items verified). A BacktestSpec with no_lookahead_confirmed=False "
                "must be treated as DRAFT and must not gate a PASS verdict."
            ))

    # NK002: BacktestReport with a validated status must reference its spec
    if artifact_type == "backtest_report":
        vs = data.get("validation_status", "UNVALIDATED")
        spec_id = data.get("spec_artifact_id")
        if vs in _BACKTEST_STATUSES_REQUIRING_SPEC and not spec_id:
            findings.append(ArtifactFinding(
                "NK002", "error", location,
                f"BacktestReport.validation_status='{vs}' claims the backtest has been "
                f"validated but spec_artifact_id is missing. Cannot verify no-lookahead "
                f"confirmation, transaction cost assumptions, or out-of-sample period "
                f"without the linked BacktestSpec."
            ))

    # NK003: BacktestReport out-of-sample metrics without an out-of-sample period is leakage
    if artifact_type == "backtest_report":
        oos_metrics = data.get("out_of_sample_metrics", {})
        # Detect non-empty out-of-sample metrics (any key with a non-None value)
        has_oos_data = any(v is not None for v in oos_metrics.values()) if isinstance(oos_metrics, dict) else bool(oos_metrics)
        spec_id = data.get("spec_artifact_id")
        # If there are OOS results but no spec, we can't verify the OOS period was defined upfront
        if has_oos_data and not spec_id:
            findings.append(ArtifactFinding(
                "NK003", "warning", location,
                "BacktestReport has out_of_sample_metrics but no spec_artifact_id. "
                "Out-of-sample results must reference a pre-defined BacktestSpec to "
                "confirm the test period was specified before seeing the data "
                "(otherwise it may be a post-hoc 'out-of-sample' selection)."
            ))

    # NK004: StrategyReview with PASS verdict but failing research quality
    if artifact_type == "strategy_review":
        verdict = data.get("verdict")
        rq_score = data.get("research_quality_score")
        if verdict == "PASS" and rq_score is not None and rq_score < _STRATEGY_PASS_MIN_RESEARCH_QUALITY:
            findings.append(ArtifactFinding(
                "NK004", "error", location,
                f"StrategyReview.verdict='PASS' but research_quality_score={rq_score:.1f} "
                f"is below the minimum threshold of {_STRATEGY_PASS_MIN_RESEARCH_QUALITY}. "
                f"A PASS verdict requires adequate research quality to prevent lookahead "
                f"and overfitting from being missed in the review."
            ))

    # NK005: StrategyReview PASS with open overfitting flags is contradictory
    if artifact_type == "strategy_review":
        verdict = data.get("verdict")
        flags = data.get("overfitting_flags", [])
        if verdict == "PASS" and flags:
            findings.append(ArtifactFinding(
                "NK005", "error", location,
                f"StrategyReview.verdict='PASS' but overfitting_flags is non-empty "
                f"({len(flags)} flag(s)): {flags[:2]}{'...' if len(flags) > 2 else ''}. "
                f"A strategy with open overfitting flags must not receive a PASS verdict."
            ))

    return findings


def validate_schema_consistency() -> list[ArtifactFinding]:
    """
    AV006 — Verify that JSON schema files in schemas/json/ are consistent with
    Pydantic model defaults.  Checks a representative set of safety-critical defaults.
    """
    findings: list[ArtifactFinding] = []

    # Safety-critical defaults: {artifact_type: {field: expected_default}}
    expected_defaults: dict[str, dict[str, object]] = {
        "trade_plan": {"manual_review_required": True},
        "backtest_spec": {
            "paper_only_until_validated": True,
            "no_lookahead_confirmed": False,
            "survivorship_bias_acknowledged": False,
        },
        "workflow_run": {"manual_review_required": True},
        "exposure_decision": {"manual_review_required": True},
        "screen_candidate": {"manual_review_required": True},
    }

    for artifact_type, checks in expected_defaults.items():
        schema_path = SCHEMAS_JSON_DIR / f"{artifact_type}.json"
        if not schema_path.is_file():
            findings.append(ArtifactFinding(
                "AV006", "error", str(schema_path),
                f"Schema file {artifact_type}.json not found — run scripts/export_json_schemas.py"
            ))
            continue

        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            findings.append(ArtifactFinding(
                "AV006", "error", str(schema_path),
                f"Cannot parse schema JSON: {exc}"
            ))
            continue

        props = schema.get("properties", {})
        for field, expected in checks.items():
            if field not in props:
                findings.append(ArtifactFinding(
                    "AV006", "error", str(schema_path),
                    f"Field '{field}' missing from {artifact_type}.json schema properties"
                ))
                continue
            actual_default = props[field].get("default")
            if actual_default != expected:
                findings.append(ArtifactFinding(
                    "AV006", "error", str(schema_path),
                    f"Field '{field}' in {artifact_type}.json has default={actual_default!r} "
                    f"but expected {expected!r} — re-export schemas to fix"
                ))

    return findings


def validate_all_reports(reports_dir: Path, known_schema_ids: frozenset[str] | None = None) -> list[ArtifactFinding]:
    """Validate all .json files under reports_dir that look like artifact outputs."""
    if known_schema_ids is None:
        known_schema_ids = _load_known_schema_ids()

    findings: list[ArtifactFinding] = []
    json_files = list(reports_dir.rglob("*.json"))
    if not json_files:
        return findings

    for json_file in sorted(json_files):
        # Skip non-artifact files (e.g., config, package manifests)
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or "artifact_type" not in data:
            continue
        findings.extend(validate_artifact_file(json_file, known_schema_ids))

    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate TraderMonty artifact JSON files for correctness",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "paths",
        nargs="*",
        metavar="FILE",
        help="Artifact JSON file(s) to validate",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Validate all artifact JSON files under reports/",
    )
    parser.add_argument(
        "--check-schemas",
        action="store_true",
        help="Check that JSON schema files match Pydantic model defaults (AV006)",
    )
    parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Suppress warnings; only print errors",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    known = _load_known_schema_ids()
    all_findings: list[ArtifactFinding] = []

    if args.check_schemas or (not args.paths and not args.all):
        all_findings.extend(validate_schema_consistency())

    if args.all:
        reports_dir = REPO_ROOT / "reports"
        if not reports_dir.exists():
            print(f"[INFO] reports/ directory not found — nothing to validate.", file=sys.stderr)
        else:
            all_findings.extend(validate_all_reports(reports_dir, known))

    for path_str in (args.paths or []):
        p = Path(path_str)
        if not p.exists():
            all_findings.append(ArtifactFinding("AV000", "error", str(p), "File not found"))
        else:
            all_findings.extend(validate_artifact_file(p, known))

    errors = [f for f in all_findings if f.severity == "error"]
    warnings = [f for f in all_findings if f.severity == "warning"]

    for finding in errors:
        print(str(finding))
    if not args.errors_only:
        for finding in warnings:
            print(str(finding))

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    if not all_findings:
        print("All artifact checks passed.")
    elif warnings:
        print(f"0 errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
