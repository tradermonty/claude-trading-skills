"""Validate user-asserted, sourced financial metrics without fetching documents."""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import date
from pathlib import Path

# unit, minimum (inclusive except income anchors), maximum, allowed enum values
RULES = {
    "adjusted_eps": ("USD/share", 0, None, None),
    "bank_metrics.cet1": ("fraction", 0, 1, None),
    "bank_metrics.cre_concentration": (
        "category",
        None,
        None,
        {"low", "moderate", "medium", "high"},
    ),
    "bank_metrics.npl_trend": ("category", None, None, {"improving", "stable", "deteriorating"}),
    "bank_metrics.nco_trend": ("category", None, None, {"improving", "stable", "deteriorating"}),
    "bank_metrics.deposit_beta": ("fraction", 0, None, None),
    "utility_metrics.ffo_to_debt": ("fraction", 0, None, None),
    "utility_metrics.allowed_roe_trend": (
        "category",
        None,
        None,
        {"rising", "stable", "falling", "adverse"},
    ),
    "utility_metrics.rate_case_status": (
        "category",
        None,
        None,
        {"constructive", "neutral", "pending", "adverse", "pending_adverse"},
    ),
    "utility_metrics.equity_issuance_risk": (
        "category",
        None,
        None,
        {"low", "moderate", "high", "dilutive"},
    ),
    "insurer_metrics.combined_ratio": ("fraction", 0, None, None),
    "insurer_metrics.reserve_development": (
        "category",
        None,
        None,
        {"favorable", "neutral", "adverse"},
    ),
    "insurer_metrics.statutory_capital": ("category", None, None, {"strong", "adequate", "weak"}),
    "reit_metrics.affo_per_share": ("USD/share", 0, None, None),
}
GROUPS = {key.split(".")[0] for key in RULES if "." in key}


class FinancialsInputError(ValueError):
    """Invalid file structure; fail before making provider calls."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FinancialsInputError("duplicate JSON key")
        result[key] = value
    return result


def _iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("expected YYYY-MM-DD")
    return date.fromisoformat(value)


def _metric_error(record, rule, run_date):
    if not isinstance(record, dict) or set(record) != {
        "value",
        "unit",
        "source",
        "as_of",
        "document_ref",
    }:
        return "invalid_record"
    if any(
        not isinstance(record[key], str) or not record[key].strip()
        for key in ("source", "document_ref")
    ):
        return "missing_provenance"
    try:
        if _iso_date(record["as_of"]) > run_date:
            return "future_as_of"
    except (ValueError, TypeError):
        return "invalid_as_of"
    unit, minimum, maximum, choices = rule
    if record["unit"] != unit:
        return "invalid_unit"
    value = record["value"]
    if choices is not None:
        return None if isinstance(value, str) and value in choices else "invalid_category"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "invalid_number"
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < minimum or (maximum is not None and value > maximum):
        return "invalid_range"
    if unit == "USD/share" and value <= 0:
        return "non_positive_income"
    return None


def load_financials(path: Path, as_of: str) -> dict:
    """Return validated per-ticker values/provenance/errors; never trust raw fields."""
    try:
        run_date = _iso_date(as_of)
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "tickers"}:
            raise FinancialsInputError("invalid root")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise FinancialsInputError("invalid schema version")
        if not isinstance(payload["tickers"], dict):
            raise FinancialsInputError("invalid ticker mapping")
        result = {}
        for raw_ticker, fields in payload["tickers"].items():
            ticker = raw_ticker.strip().upper()
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-^=]{0,19}", ticker) or ticker in result:
                raise FinancialsInputError("invalid or duplicate ticker")
            entry = {"values": {}, "provenance": {}, "errors": []}
            result[ticker] = entry
            if not isinstance(fields, dict) or not fields:
                entry["errors"].append("manual_financials:invalid_ticker_record")
                continue
            flattened = {}
            for key, record in fields.items():
                if "." in key:
                    entry["errors"].append("manual_financials:unknown:unknown_metric")
                    continue
                if key in GROUPS and isinstance(record, dict) and record:
                    flattened.update({f"{key}.{name}": value for name, value in record.items()})
                else:
                    flattened[key] = record
            for key, record in flattened.items():
                # Never echo arbitrary field names or invalid raw values into diagnostics.
                error = (
                    _metric_error(record, RULES[key], run_date)
                    if key in RULES
                    else "unknown_metric"
                )
                if error:
                    label = key if key in RULES else "unknown"
                    entry["errors"].append(f"manual_financials:{label}:{error}")
                    continue
                entry["values"][key] = record["value"]
                entry["provenance"][key] = dict(record, input_method="MANUAL")
        return result
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise FinancialsInputError("Invalid --financials-json file or --as-of date.") from exc


def merge_financials(base: dict, supplied: dict | None) -> dict:
    """Apply only validated inputs, preserving FMP data and explicit validation failures."""
    result = copy.deepcopy(base)
    if supplied is None:
        return result
    for key, value in supplied["values"].items():
        if "." in key:
            group, field = key.split(".")
            if not isinstance(result.get(group), dict):
                result[group] = {}
            result[group][field] = value
        else:
            result[key] = value
        if key == "adjusted_eps":
            result["adjusted_eps_source"] = "MANUAL"
    result["manual_financials_provenance"] = supplied["provenance"]
    result["manual_financials_errors"] = supplied["errors"]
    return result
