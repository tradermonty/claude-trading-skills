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

import csv
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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

# Public CSV contracts (format == "csv"). The canary performs one keyless GET
# per contract, so the URL host is restricted to an allowlist.
CSV_ALLOWED_HOSTS = frozenset({"tradermonty.github.io", "raw.githubusercontent.com"})
DEFAULT_CSV_MAX_BYTES = 2 * 1024 * 1024
CONTRACT_FORMATS = ("json", "csv")

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

    def summarized(self, severity: str | None = None) -> list[dict[str, Any]]:
        """Unique ``(code, severity)`` pairs with a ``count``, in first-seen order.

        ``validate_rows`` emits one anomaly per offending row; a 30k-row CSV
        with one renamed column would otherwise produce 30k identical entries.
        The canary and summary use this deduplicated form. ``severity`` limits
        the result to FATAL or DEPRECATION entries.
        """
        counts: dict[tuple[str, str], int] = {}
        for anomaly in self.anomalies:
            if severity is not None and anomaly.severity != severity:
                continue
            key = (anomaly.code, anomaly.severity)
            counts[key] = counts.get(key, 0) + 1
        return [
            {"code": code, "severity": sev, "count": count} for (code, sev), count in counts.items()
        ]


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
    # --- public CSV contracts (all default to the FMP/JSON shape) ---
    format: str = "json"
    url: str = ""
    max_bytes: Any = None  # raw JSON value; validated by validate_contract_file
    required_values: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_max_bytes(self) -> int:
        """Body-size cap for a CSV fetch (decompressed bytes)."""
        if isinstance(self.max_bytes, int) and not isinstance(self.max_bytes, bool):
            return self.max_bytes
        return DEFAULT_CSV_MAX_BYTES


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
        format=data.get("format", "json"),
        url=str(data.get("url", "") or ""),
        max_bytes=data.get("max_bytes"),
        required_values=data.get("required_values") or {},
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


def _validate_format_keys(contract: Contract, label: str) -> list[str]:
    """Check the ``format`` / ``url`` / ``max_bytes`` / ``required_values`` keys."""
    errors: list[str] = []
    fmt = contract.format
    if fmt not in CONTRACT_FORMATS:
        errors.append(f"{label}: format must be one of {list(CONTRACT_FORMATS)} (got {fmt!r})")
        return errors

    if fmt == "json":
        if contract.url:
            errors.append(f"{label}: url is only allowed on csv contracts")
        if contract.max_bytes is not None:
            errors.append(f"{label}: max_bytes is only allowed on csv contracts")
    else:
        errors.extend(_validate_csv_url(contract, label))
        max_bytes = contract.max_bytes
        if max_bytes is not None and (
            isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0
        ):
            errors.append(f"{label}: max_bytes must be a positive integer (got {max_bytes!r})")

    required_values = contract.required_values
    if not isinstance(required_values, dict):
        errors.append(f"{label}: required_values must be an object of column -> list of values")
        return errors
    for column, values in required_values.items():
        if not isinstance(values, list) or not values:
            errors.append(f"{label}: required_values['{column}'] must be a non-empty list")
        if column not in contract.required_fields:
            errors.append(f"{label}: required_values column '{column}' is not in required_fields")
    return errors


def _validate_csv_url(contract: Contract, label: str) -> list[str]:
    errors: list[str] = []
    if contract.query:
        errors.append(f"{label}: csv contracts must have an empty query (use the url path only)")
    if not contract.url:
        errors.append(f"{label}: csv contracts require a url")
        return errors
    parts = urlsplit(contract.url)
    if parts.scheme != "https":
        errors.append(f"{label}: url scheme must be https (got {parts.scheme!r})")
    if parts.hostname not in CSV_ALLOWED_HOSTS or parts.netloc != parts.hostname:
        errors.append(
            f"{label}: url host must be one of {sorted(CSV_ALLOWED_HOSTS)} with no "
            f"port or credentials (got {parts.netloc!r})"
        )
    if parts.query or parts.fragment:
        errors.append(f"{label}: url must not carry a query string or fragment")
    if contract.endpoint_path != parts.path:
        errors.append(
            f"{label}: path must equal the url path ({parts.path!r}, got "
            f"{contract.endpoint_path!r})"
        )
    return errors


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

    errors.extend(_validate_format_keys(contract, label))

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


def _is_canonical_iso_date(value: Any) -> bool:
    """True for a string in canonical YYYY-MM-DD form naming a real calendar day."""
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def validate_rows(contract: Contract, rows: Any) -> RowValidation:
    """Validate ``rows`` (a live or fixture response body) against ``contract``.

    Anomaly codes and severities are fixed (see ``docs/dev/provider-contracts.md``):
    ``empty_response``, ``not_a_list``, ``row_not_object``,
    ``missing_required_field:<f>``, ``null_required_field:<f>``,
    ``wrong_type:<f>:<got>``, ``all_null_required_field:<f>``,
    ``missing_required_value:<col>=<val>`` (a ``required_values`` entry no row carries),
    ``non_finite_required_field:<f>``, ``invalid_contract_rule:<f>:finite``,
    ``invalid_date_format:<f>``, ``invalid_contract_rule:<f>:iso_date``,
    ``invalid_contract_rule:<f>:reject_all_null`` and ``canonical_absent_legacy_present:<legacy>-><canonical>``
    are FATAL; ``legacy_alias_present:<legacy>` is a non-fatal DEPRECATION.
    """
    anomalies: list[Anomaly] = []
    for field_name, spec in contract.required_fields.items():
        if not isinstance(spec.get("reject_all_null", False), bool):
            anomalies.append(Anomaly(f"invalid_contract_rule:{field_name}:reject_all_null", FATAL))
        finite = spec.get("finite", False)
        types = spec.get("types", [])
        if not isinstance(finite, bool) or (
            finite
            and (
                not isinstance(types, list)
                or not types
                or any(not isinstance(t, str) or t not in {"int", "float"} for t in types)
            )
        ):
            anomalies.append(Anomaly(f"invalid_contract_rule:{field_name}:finite", FATAL))
        iso_date = spec.get("iso_date", False)
        if not isinstance(iso_date, bool) or (iso_date and types != ["str"]):
            anomalies.append(Anomaly(f"invalid_contract_rule:{field_name}:iso_date", FATAL))
    if any(a.code.endswith((":finite", ":iso_date")) for a in anomalies):
        # Invalid policies cannot safely validate a response body, regardless of shape.
        return RowValidation(anomalies)
    min_rows = int((contract.non_empty or {}).get("min_rows", 0) or 0)

    if rows is None or (isinstance(rows, list) and len(rows) == 0):
        if min_rows >= 1:
            anomalies.append(Anomaly("empty_response", FATAL))
        return RowValidation(anomalies)

    if not isinstance(rows, list):
        anomalies.append(Anomaly("not_a_list", FATAL))
        return RowValidation(anomalies)

    # Individual nulls can be legitimate while an entire probe losing a
    # populated field is provider drift. Missing keys / malformed rows have
    # their own fatal codes below; do not mislabel them as explicit nulls.
    for field_name, spec in contract.required_fields.items():
        if spec.get("reject_all_null", False) is True and all(
            isinstance(row, dict) and field_name in row and row[field_name] is None for row in rows
        ):
            anomalies.append(Anomaly(f"all_null_required_field:{field_name}", FATAL))

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
            elif spec.get("finite", False) is True and got in {"int", "float"}:
                try:
                    finite_value = math.isfinite(value)
                except OverflowError:
                    finite_value = False
                if not finite_value:
                    anomalies.append(Anomaly(f"non_finite_required_field:{field_name}", FATAL))
            elif spec.get("iso_date", False) is True and not _is_canonical_iso_date(value):
                anomalies.append(Anomaly(f"invalid_date_format:{field_name}", FATAL))

        for legacy_key, meta in contract.legacy_aliases.items():
            canonical = meta.get("canonical")
            if legacy_key in row and canonical and canonical in row:
                anomalies.append(Anomaly(f"legacy_alias_present:{legacy_key}", DEPRECATION))

    # A key-value CSV (e.g. Metric,Value) can lose a consumer-read row while
    # every remaining row is valid; each required value must appear somewhere.
    required_values = contract.required_values if isinstance(contract.required_values, dict) else {}
    for column, values in required_values.items():
        for value in values if isinstance(values, list) else []:
            if not any(isinstance(row, dict) and row.get(column) == value for row in rows):
                anomalies.append(Anomaly(f"missing_required_value:{column}={value}", FATAL))

    return RowValidation(anomalies)


_CSV_EXTRA_KEY = "\x00extra_cells"
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)$"
)


def _coerce_cell(cell: str | None) -> Any:
    """Coerce one CSV cell: empty -> None, bool/int/float literals, else the string.

    ``nan`` / ``inf`` / non-finite literals stay strings on purpose: the
    breadth consumer rejects them, so a numeric column holding one must show
    up as ``wrong_type`` rather than pass as a float.
    """
    if cell is None:
        return None
    text = cell.strip()
    if text == "":
        return None
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        value = float(text)
        return value if math.isfinite(value) else cell
    return cell


def parse_csv_rows(text: str) -> tuple[list[dict[str, Any]], list[Anomaly]]:
    """Parse CSV text into coerced rows plus parse-level anomalies (stdlib ``csv``).

    Strips a UTF-8 BOM, reads the header, and coerces each cell with
    ``_coerce_cell``. A short row maps its missing cells to ``None``. A row
    with extra cells yields one FATAL ``extra_cells`` anomaly and keeps only
    the header keys, so no ``None`` key ever reaches ``validate_rows``.
    A header-only (or empty) body returns ``[]``.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text), restkey=_CSV_EXTRA_KEY)
    rows: list[dict[str, Any]] = []
    anomalies: list[Anomaly] = []
    for raw in reader:
        if _CSV_EXTRA_KEY in raw:
            anomalies.append(Anomaly("extra_cells", FATAL))
            raw.pop(_CSV_EXTRA_KEY)
        rows.append({key: _coerce_cell(value) for key, value in raw.items()})
    return rows, anomalies
