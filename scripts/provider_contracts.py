"""Provider response contracts: loader, validator, and anomaly model (Issue #332).

Stdlib only at import time — this module is imported by
``scripts/check_provider_contracts.py`` in the CI ``metadata`` job, which
installs only ``pyyaml`` and ``packaging`` (no ``requests``). Anything that
needs ``requests`` (the live canary HTTP call) lives in the CLI and imports it
lazily inside the function that needs it.

A "contract" is a versioned JSON file under
``config/provider-contracts/<provider>/<endpoint>.v<N>.json`` recording a
sanitized, real provider response shape: which fields consumers actually
read (``required_fields``), which fields are informational
(``optional_fields``), which legacy/renamed field names a stale response
might carry (``legacy_aliases``), and a fixture of real (sanitized) rows.

The #328 failure class this guards against: the provider returns HTTP 200
with a response that silently dropped/renamed a field a consumer reads, and
nothing catches it until a downstream report goes quietly empty. See
``docs/dev/provider-contracts.md`` for the full contract schema, the
anomaly/severity table, and the manual fixture-refresh procedure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "config" / "provider-contracts"


class ContractLoadError(Exception):
    """Raised by ``load_contracts`` on malformed JSON or a duplicate endpoint.

    Callers (the ``check``/``canary`` CLI) catch this and print a clean
    ``ERROR:`` line instead of letting a data-authoring bug surface as a
    traceback.
    """


# Anomaly severities. `ok` (see RowValidation.ok) is "no anomaly with
# severity FATAL is present" — a DEPRECATION-only result is still ok=True.
FATAL = "fatal"
DEPRECATION = "deprecation"

_APIKEY_RE = re.compile(r"([?&](?:apikey|api_key)=)[^&\s]+", re.IGNORECASE)


def redact_url(url: str) -> str:
    """Replace any ``apikey=`` / ``api_key=`` query value with ``REDACTED``.

    Applied to every URL before it is logged or written to a report so the
    FMP key never leaks into stderr or a committed/uploaded artifact.
    """
    return _APIKEY_RE.sub(r"\1REDACTED", url)


@dataclass(frozen=True)
class Anomaly:
    """A single contract violation (or informational deprecation) found in a row."""

    code: str
    severity: str  # FATAL | DEPRECATION

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity}


@dataclass
class RowValidation:
    """Result of validating a list of rows against one contract."""

    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no anomaly has FATAL severity (DEPRECATION-only is ok)."""
        return not any(a.severity == FATAL for a in self.anomalies)

    @property
    def fatal_anomalies(self) -> list[Anomaly]:
        return [a for a in self.anomalies if a.severity == FATAL]

    @property
    def deprecations(self) -> list[Anomaly]:
        return [a for a in self.anomalies if a.severity == DEPRECATION]


@dataclass
class Contract:
    """One loaded ``config/provider-contracts/<provider>/<endpoint>.v<N>.json`` file."""

    file_path: Path
    schema_version: int
    provider: str
    endpoint: str
    endpoint_path: str  # the JSON file's "path" key, e.g. "/stable/profile"
    query: dict[str, Any]
    contract_version: int
    recorded_on: str
    recording: str
    owners: list[str]
    tier_notes: str
    required_fields: dict[str, dict[str, Any]]
    optional_fields: list[str]
    legacy_aliases: dict[str, dict[str, str]]
    known_gaps: list[dict[str, Any]]
    non_empty: dict[str, Any]
    fixture: list[dict[str, Any]]


def _type_name(value: Any) -> str:
    """JSON-ish type name for a Python value, distinguishing bool from int."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _contract_from_data(file_path: Path, data: dict[str, Any]) -> Contract:
    return Contract(
        file_path=file_path,
        schema_version=int(data.get("schema_version", 0)),
        provider=str(data.get("provider", "")),
        endpoint=str(data.get("endpoint", "")),
        endpoint_path=str(data.get("path", "")),
        query=dict(data.get("query") or {}),
        contract_version=int(data.get("contract_version", 0)),
        recorded_on=str(data.get("recorded_on", "")),
        recording=str(data.get("recording", "")),
        owners=list(data.get("owners") or []),
        tier_notes=str(data.get("tier_notes", "")),
        required_fields=dict(data.get("required_fields") or {}),
        optional_fields=list(data.get("optional_fields") or []),
        legacy_aliases=dict(data.get("legacy_aliases") or {}),
        known_gaps=list(data.get("known_gaps") or []),
        non_empty=dict(data.get("non_empty") or {}),
        fixture=list(data.get("fixture") or []),
    )


def load_contracts(root: Path | str | None = None) -> dict[str, Contract]:
    """Load every ``config/provider-contracts/<provider>/*.v*.json`` file.

    Keyed by ``endpoint`` (the JSON file's ``endpoint`` field, which matches
    the contract file's stem minus the ``.vN`` suffix). Returns an empty
    dict when the directory tree does not exist or holds no contract files.

    Raises ``ContractLoadError`` (naming the offending file) on malformed JSON
    or when two contract files declare the same ``endpoint`` — either is a
    data-authoring bug the caller should surface as a clean error, not a
    traceback.
    """
    import json

    base = Path(root) if root is not None else ROOT
    contracts_dir = base / "config" / "provider-contracts"
    contracts: dict[str, Contract] = {}
    if not contracts_dir.is_dir():
        return contracts
    for provider_dir in sorted(p for p in contracts_dir.iterdir() if p.is_dir()):
        for file_path in sorted(provider_dir.glob("*.v*.json")):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ContractLoadError(f"{file_path}: malformed JSON ({exc})") from exc
            contract = _contract_from_data(file_path, data)
            if contract.endpoint in contracts:
                other = contracts[contract.endpoint].file_path
                raise ContractLoadError(
                    f"duplicate endpoint '{contract.endpoint}': {other} and {file_path} "
                    "both declare it"
                )
            contracts[contract.endpoint] = contract
    return contracts


def validate_contract_file(contract: Contract, skills_index_ids: Any) -> list[str]:
    """Static/structural checks on one contract file (no network, no rows-vs-live).

    Returns a list of human-readable error strings (empty = valid). Checks:
    schema_version, non-empty owners that all exist in ``skills-index.yaml``,
    a non-empty fixture whose rows satisfy ``required_fields`` and carry no
    ``legacy_aliases`` key, and that ``known_gaps`` is only populated on the
    ``earnings-calendar`` endpoint.
    """
    errors: list[str] = []
    label = contract.endpoint or contract.file_path.name

    if contract.schema_version != 1:
        errors.append(f"{label}: schema_version must be 1 (got {contract.schema_version!r})")
    if not contract.provider:
        errors.append(f"{label}: provider must not be empty")
    if not contract.endpoint:
        errors.append(f"{label}: endpoint must not be empty")
    if contract.contract_version < 1:
        errors.append(f"{label}: contract_version must be >= 1")
    if not contract.owners:
        errors.append(f"{label}: owners must not be empty")

    known_ids = set(skills_index_ids or [])
    for owner in contract.owners:
        if owner not in known_ids:
            errors.append(f"{label}: owner '{owner}' is not a skill in skills-index.yaml")

    if not contract.fixture:
        errors.append(f"{label}: fixture must have at least one row")

    for i, row in enumerate(contract.fixture):
        if not isinstance(row, dict):
            errors.append(f"{label}: fixture row {i} is not an object")
            continue
        for legacy_key in contract.legacy_aliases:
            if legacy_key in row:
                errors.append(
                    f"{label}: fixture row {i} contains legacy_aliases key '{legacy_key}' "
                    "(fixtures must record the canonical stable shape)"
                )

    row_validation = validate_rows(contract, contract.fixture)
    if not row_validation.ok:
        codes = ", ".join(a.code for a in row_validation.fatal_anomalies)
        errors.append(f"{label}: fixture rows fail contract validation: {codes}")

    if contract.known_gaps and contract.endpoint != "earnings-calendar":
        errors.append(f"{label}: known_gaps is only allowed on the earnings-calendar endpoint")
    for gap in contract.known_gaps:
        if not isinstance(gap, dict) or not isinstance(gap.get("issue"), int):
            errors.append(f"{label}: known_gaps entry must carry an integer 'issue': {gap!r}")

    return errors


def validate_rows(contract: Contract, rows: Any) -> RowValidation:
    """Validate ``rows`` (a live or fixture response body) against ``contract``.

    Anomaly codes and severities are fixed (see ``docs/dev/provider-contracts.md``):
    ``empty_response``, ``not_a_list``, ``row_not_object``,
    ``missing_required_field:<f>``, ``null_required_field:<f>``,
    ``wrong_type:<f>:<got>`` and ``canonical_absent_legacy_present:<legacy>-><canonical>``
    are FATAL; ``legacy_alias_present:<legacy>` is a non-fatal DEPRECATION.
    """
    anomalies: list[Anomaly] = []
    min_rows = int((contract.non_empty or {}).get("min_rows", 0) or 0)

    if rows is None or (isinstance(rows, list) and len(rows) == 0):
        if min_rows >= 1:
            anomalies.append(Anomaly("empty_response", FATAL))
        return RowValidation(anomalies)

    if not isinstance(rows, list):
        anomalies.append(Anomaly("not_a_list", FATAL))
        return RowValidation(anomalies)

    legacy_for_canonical: dict[str, list[str]] = {}
    for legacy_key, meta in contract.legacy_aliases.items():
        canonical = meta.get("canonical")
        if canonical:
            legacy_for_canonical.setdefault(canonical, []).append(legacy_key)

    for row in rows:
        if not isinstance(row, dict):
            anomalies.append(Anomaly("row_not_object", FATAL))
            continue

        for field_name, spec in contract.required_fields.items():
            if field_name not in row:
                legacy_candidates = legacy_for_canonical.get(field_name, [])
                found_legacy = next((lk for lk in legacy_candidates if lk in row), None)
                if found_legacy:
                    anomalies.append(
                        Anomaly(
                            f"canonical_absent_legacy_present:{found_legacy}->{field_name}",
                            FATAL,
                        )
                    )
                else:
                    anomalies.append(Anomaly(f"missing_required_field:{field_name}", FATAL))
                continue

            value = row[field_name]
            if value is None:
                if not spec.get("nullable", False):
                    anomalies.append(Anomaly(f"null_required_field:{field_name}", FATAL))
                continue

            allowed_types = spec.get("types", [])
            got = _type_name(value)
            if got not in allowed_types:
                anomalies.append(Anomaly(f"wrong_type:{field_name}:{got}", FATAL))

        for legacy_key, meta in contract.legacy_aliases.items():
            canonical = meta.get("canonical")
            if legacy_key in row and canonical and canonical in row:
                anomalies.append(Anomaly(f"legacy_alias_present:{legacy_key}", DEPRECATION))

    return RowValidation(anomalies)
