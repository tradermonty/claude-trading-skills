"""Step adapters for the multi-asset-opportunity-daily workflow."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths, _latest_report
from .common import (
    ReplayError,
    _assert_finite_json,
    _load_json,
    _load_module_from_path,
    _parse_rfc3339,
    _repo_module,
    _run_cli,
    _schema_error_details,
    _write_json,
    load_yaml,
)
from .constants import MULTI_ASSET_REPLAY_SCHEMA
from .normalize import _canonicalize, _file_sha256
from .steps_kanchi import _kanchi_artifact_link


def _validate_multi_asset_contract(payload: Any, definition: str) -> Mapping[str, Any]:
    schema = _load_json(MULTI_ASSET_REPLAY_SCHEMA, "multi-asset replay contract schema")
    selected = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    errors = _schema_error_details(selected, payload)
    if errors:
        raise ReplayError(f"invalid multi-asset {definition} contract:\n- " + "\n- ".join(errors))
    _assert_finite_json(payload, f"multi-asset {definition}")
    return payload


def _multi_asset_fixed_date(spec: Mapping[str, Any]) -> str:
    return _parse_rfc3339(spec["fixed_timestamp"], "fixed_timestamp").date().isoformat()


def _multi_macro_modules(repo_root: Path) -> tuple[Any, Any]:
    scripts_dir = repo_root / "skills" / "macro-regime-detector" / "scripts"
    scorer = _load_module_from_path(scripts_dir / "scorer.py", "multi_asset_macro_scorer")
    reporter = _load_module_from_path(
        scripts_dir / "report_generator.py", "multi_asset_macro_reporter"
    )
    return scorer, reporter


def _multi_macro_regime(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if consumed:
        raise ReplayError("multi-asset macro regime must not consume prior artifacts")
    fixture = _validate_multi_asset_contract(
        _load_json(inputs["macro_components"], "macro components fixture"), "macro_components"
    )
    fixed_date = _multi_asset_fixed_date(spec)
    if fixture["as_of"] != fixed_date:
        raise ReplayError("macro components as_of must match fixed_timestamp date")
    components = fixture["components"]
    scorer, reporter = _multi_macro_modules(repo_root)

    def _analyze() -> dict[str, Any]:
        component_scores = {key: value["score"] for key, value in components.items()}
        data_availability = {key: value["data_available"] for key, value in components.items()}
        composite = scorer.calculate_composite_score(component_scores, data_availability)
        regime = scorer.classify_regime(components)
        regime["consistency"] = scorer.check_regime_consistency(
            regime["current_regime"], components
        )
        return {
            "metadata": {
                "generated_at": spec["fixed_timestamp"],
                "data_source": "fixture",
                "data_mode": "offline",
                "as_of": fixed_date,
            },
            "composite": composite,
            "regime": regime,
            "components": components,
        }

    first = _analyze()
    if first != _analyze():
        raise ReplayError("native macro regime synthesis was non-deterministic")
    if not first["regime"].get("regime_label"):
        raise ReplayError("native macro regime synthesis produced no regime label")
    if first["composite"].get("composite_score") is None:
        raise ReplayError("native macro regime synthesis produced no composite score")
    artifacts = _artifact_paths(stage, step["output_files"])
    draft = work / "macro_regime_brief.json"
    try:
        reporter.generate_json_report(first, str(draft))
    except Exception as exc:
        raise ReplayError(f"macro regime native report API failed: {exc}") from exc
    produced = _load_json(draft, "macro regime generated brief")
    if produced != first:
        raise ReplayError("macro regime native report did not round-trip the analysis")
    _assert_finite_json(produced, "macro regime brief")
    _write_json(Path(artifacts["macro_regime_brief"]["files"]["canonical"]), produced)
    return artifacts


def _multi_theme(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"macro_regime_brief"}:
        raise ReplayError(f"multi-asset theme received unexpected artifacts: {sorted(consumed)}")
    brief_path = Path(consumed["macro_regime_brief"]["files"]["canonical"])
    brief = _load_json(brief_path, "macro regime brief handoff")
    evidence = _validate_multi_asset_contract(
        _load_json(inputs["theme_evidence"], "theme evidence fixture"), "theme_evidence"
    )
    if evidence["as_of"] != _multi_asset_fixed_date(spec):
        raise ReplayError("theme evidence as_of must match fixed_timestamp date")
    if evidence["regime_label"] != brief["regime"]["regime_label"]:
        raise ReplayError("theme evidence regime_label does not match the macro regime brief")
    names = [theme["name"] for theme in evidence["themes"]]
    if len(names) != len(set(names)):
        raise ReplayError("theme evidence theme names must be unique")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["hot_themes"]["files"]["canonical"]), evidence)
    return artifacts


def _multi_news_brief(
    _repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"hot_themes"}:
        raise ReplayError(
            f"multi-asset news brief received unexpected artifacts: {sorted(consumed)}"
        )
    hot_path = Path(consumed["hot_themes"]["files"]["canonical"])
    hot = _load_json(hot_path, "hot themes handoff")
    brief = _validate_multi_asset_contract(load_yaml(inputs["news_brief"]), "news_brief")
    if brief["as_of"] != _multi_asset_fixed_date(spec):
        raise ReplayError("news brief as_of must match fixed_timestamp date")
    known = {theme["name"] for theme in hot["themes"]}
    unknown = set(brief["based_on_themes"]) - known
    if unknown:
        raise ReplayError(
            f"news brief references themes missing from hot_themes: {sorted(unknown)}"
        )
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["catalyst_news_brief"]["files"]["canonical"]), brief)
    return artifacts


def _require_unique_ids(ids: Sequence[str], label: str) -> None:
    """Fail closed when a hypothesis id list contains duplicates.

    Primary guard for lists the schema cannot constrain: native ideator
    output and uniqueness across the actionable + excluded arrays. The human
    decision lists also carry schema uniqueItems, which fires first; calling
    it there too keeps the partition checks correct if that schema is relaxed.
    """
    seen: set[str] = set()
    dups: set[str] = set()
    for value in ids:
        if value in seen:
            dups.add(value)
        seen.add(value)
    if dups:
        raise ReplayError(f"{label} contain duplicate hypothesis ids: {sorted(dups)}")


def _multi_hypotheses(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if "catalyst_news_brief" in consumed:
        expected_consumed = {"macro_regime_brief", "hot_themes", "catalyst_news_brief"}
    else:
        expected_consumed = {"macro_regime_brief", "hot_themes"}
    if set(consumed) != expected_consumed:
        raise ReplayError(
            f"multi-asset hypotheses received unexpected artifacts: {sorted(consumed)}"
        )
    bundle = _validate_multi_asset_contract(
        _load_json(inputs["hypotheses_bundle"], "hypotheses bundle"), "hypotheses_bundle"
    )
    raw = _validate_multi_asset_contract(
        _load_json(inputs["raw_hypotheses"], "raw hypotheses"), "raw_hypotheses"
    )
    raw_by_id = {card["hypothesis_id"]: card for card in raw["hypotheses"]}
    if len(raw_by_id) != len(raw["hypotheses"]):
        raise ReplayError("raw hypotheses contain duplicate hypothesis ids")
    decision = _validate_multi_asset_contract(load_yaml(inputs["gate_decision"]), "gate_decision")
    binding = bundle["source_binding"]
    for artifact_id in ("macro_regime_brief", "hot_themes"):
        actual = _file_sha256(Path(consumed[artifact_id]["files"]["canonical"]))
        if binding[artifact_id] != actual:
            raise ReplayError(
                f"hypotheses bundle source_binding mismatch for {artifact_id}: "
                f"expected {binding[artifact_id]}, actual {actual}"
            )
    if "catalyst_news_brief" in consumed:
        actual = _file_sha256(Path(consumed["catalyst_news_brief"]["files"]["canonical"]))
        if binding["catalyst_news_brief"] != actual:
            raise ReplayError(
                "hypotheses bundle source_binding mismatch for catalyst_news_brief: "
                f"expected {binding['catalyst_news_brief']}, actual {actual}"
            )
    # When the optional step 3 is disabled (required-only), the shared bundle's
    # catalyst binding is simply not checked; the full-path run above enforces it.

    reports = work / "reports"
    reports.mkdir(parents=True)
    ideator = (
        repo_root / "skills" / "trade-hypothesis-ideator" / "scripts" / "run_hypothesis_ideator.py"
    )
    _run_cli(
        [
            sys.executable,
            str(ideator),
            "--input",
            str(inputs["hypotheses_bundle"]),
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    _run_cli(
        [
            sys.executable,
            str(ideator),
            "--input",
            str(inputs["hypotheses_bundle"]),
            "--hypotheses",
            str(inputs["raw_hypotheses"]),
            "--output-dir",
            str(reports),
        ],
        repo_root,
    )
    bundle_out = _load_json(
        _latest_report(reports, "output_bundle.json"), "hypothesis output bundle"
    )
    if "generated_at_utc" in bundle_out:
        bundle_out["generated_at_utc"] = spec["fixed_timestamp"]
    _assert_finite_json(bundle_out, "hypothesis output bundle")
    output_ids = [card["hypothesis_id"] for card in bundle_out["hypotheses"]]
    _require_unique_ids(output_ids, "hypothesis output bundle")
    if set(output_ids) != set(raw_by_id) or len(output_ids) != len(raw_by_id):
        raise ReplayError("hypothesis output bundle does not preserve the raw hypothesis cards")
    accepted = decision["accepted"]
    rejected = decision["rejected"]
    _require_unique_ids(accepted, "gate_decision.accepted")
    _require_unique_ids(rejected, "gate_decision.rejected")
    if set(accepted) | set(rejected) != set(output_ids) or set(accepted) & set(rejected):
        raise ReplayError("gate decision must partition exactly the output hypothesis cards")
    actionable: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for card in bundle_out["hypotheses"]:
        raw_card = raw_by_id[card["hypothesis_id"]]
        merged = {
            **card,
            "ticker": raw_card.get("ticker"),
            "asset_class": raw_card.get("asset_class", "equity"),
            "research_only": bool(raw_card.get("research_only", False)),
        }
        if card["hypothesis_id"] in set(accepted):
            if merged["asset_class"] == "forex":
                raise ReplayError(
                    f"actionable hypothesis {card['hypothesis_id']} is forex: research-only output must never be sized"
                )
            actionable.append(merged)
        else:
            excluded.append(merged)
    for card in actionable + excluded:
        if card["asset_class"] == "forex" and not card["research_only"]:
            raise ReplayError(
                f"forex hypothesis {card['hypothesis_id']} must carry research_only=true"
            )
    if not actionable:
        raise ReplayError("hypothesis gate produced no actionable cards")
    cards = {
        "schema_version": 1,
        "as_of": _multi_asset_fixed_date(spec),
        "hypotheses": actionable,
        "excluded": excluded,
    }
    _validate_multi_asset_contract(cards, "hypothesis_cards")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["hypothesis_cards"]["files"]["canonical"]), cards)
    return artifacts


def _multi_position_size(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"hypothesis_cards"}:
        raise ReplayError(
            f"multi-asset position sizing received unexpected artifacts: {sorted(consumed)}"
        )
    cards_path = Path(consumed["hypothesis_cards"]["files"]["canonical"])
    cards_doc = _validate_multi_asset_contract(
        _load_json(cards_path, "hypothesis cards handoff"), "hypothesis_cards"
    )
    # The schema cannot express cross-array uniqueness, so the union of
    # actionable and excluded ids is checked here explicitly.
    _require_unique_ids(
        [card["hypothesis_id"] for card in cards_doc["hypotheses"]]
        + [card["hypothesis_id"] for card in cards_doc.get("excluded", [])],
        "hypothesis cards handoff",
    )
    params = _validate_multi_asset_contract(
        _load_json(inputs["sizing_params"], "sizing parameters"), "sizing_params"
    )
    actionable = cards_doc["hypotheses"]
    param_by_id = {row["hypothesis_id"]: row for row in params["cards"]}
    if len(param_by_id) != len(params["cards"]):
        raise ReplayError("sizing parameters contain duplicate hypothesis ids")
    if set(param_by_id) != {card["hypothesis_id"] for card in actionable}:
        raise ReplayError("sizing parameters must cover exactly the actionable hypothesis cards")
    reports = work / "reports"
    reports.mkdir(parents=True)
    sizer = repo_root / "skills" / "position-sizer" / "scripts" / "position_sizer.py"
    sized: list[dict[str, Any]] = []
    for index, card in enumerate(actionable):
        entry = param_by_id[card["hypothesis_id"]]
        card_dir = reports / f"card-{index}"
        card_dir.mkdir(parents=True)
        command = [
            sys.executable,
            str(sizer),
            "--account-size",
            str(params["account_size"]),
            "--entry",
            str(entry["entry"]),
            "--stop",
            str(entry["stop"]),
            "--risk-pct",
            str(params["risk_pct"]),
        ]
        if params.get("max_position_pct") is not None:
            command.extend(["--max-position-pct", str(params["max_position_pct"])])
        command.extend(["--output-dir", str(card_dir)])
        _run_cli(command, repo_root)
        native = _load_json(
            _latest_report(card_dir, "position_sizer_*.json"), "position sizer report"
        )
        canonical = _canonicalize(native, spec["fixed_timestamp"], {})
        _assert_finite_json(canonical, "position sizer report")
        sized.append(
            {
                "hypothesis_id": card["hypothesis_id"],
                "ticker": card.get("ticker"),
                "entry": entry["entry"],
                "stop": entry["stop"],
                "shares": canonical.get("final_recommended_shares"),
                "position_value": canonical.get("final_position_value"),
                "risk_dollars": canonical.get("final_risk_dollars"),
                "constraints_applied": canonical.get("constraints_applied"),
            }
        )
    if any(row["shares"] is None or row["position_value"] is None for row in sized):
        raise ReplayError("position sizer report is missing shares or position value")
    # Defense in depth: re-verify the sizer's cap instead of trusting its
    # output. An absent max_position_pct means the sizer applies no cap, so
    # this check falls back to 100% of account (no leverage).
    max_position_value = params["account_size"] * params.get("max_position_pct", 100.0) / 100.0
    for row in sized:
        if row["position_value"] > max_position_value + 1e-9:
            raise ReplayError(
                f"sized hypothesis {row['hypothesis_id']} breaches the max position cap"
            )
    payload = {
        "schema_version": 1,
        "as_of": _multi_asset_fixed_date(spec),
        "account": {
            "account_size": params["account_size"],
            "risk_pct": params["risk_pct"],
            "max_position_pct": params.get("max_position_pct"),
        },
        "sized": sized,
    }
    _validate_multi_asset_contract(payload, "sized_hypotheses")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["sized_hypotheses"]["files"]["canonical"]), payload)
    return artifacts


def _multi_register(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"hypothesis_cards", "sized_hypotheses"}:
        raise ReplayError(
            f"multi-asset registration received unexpected artifacts: {sorted(consumed)}"
        )
    decision = _validate_multi_asset_contract(
        load_yaml(inputs["register_decision"]), "register_decision"
    )
    fixed_date = _multi_asset_fixed_date(spec)
    cards_path = Path(consumed["hypothesis_cards"]["files"]["canonical"])
    cards_doc = _validate_multi_asset_contract(
        _load_json(cards_path, "hypothesis cards handoff"), "hypothesis_cards"
    )
    # The schema cannot express cross-array uniqueness, so the union of
    # actionable and excluded ids is checked here explicitly.
    _require_unique_ids(
        [card["hypothesis_id"] for card in cards_doc["hypotheses"]]
        + [card["hypothesis_id"] for card in cards_doc.get("excluded", [])],
        "hypothesis cards handoff",
    )
    sized_path = Path(consumed["sized_hypotheses"]["files"]["canonical"])
    sized_doc = _validate_multi_asset_contract(
        _load_json(sized_path, "sized hypotheses handoff"), "sized_hypotheses"
    )
    actionable_ids = [card["hypothesis_id"] for card in cards_doc["hypotheses"]]
    excluded_ids = [card["hypothesis_id"] for card in cards_doc.get("excluded", [])]
    idea = decision["idea"]
    entry_ready = decision["entry_ready"]
    rejected = decision["rejected"]
    # Duplicates are otherwise caught only incidentally by the sorted-list
    # comparisons below; check explicitly for a clear failure message.
    _require_unique_ids(idea, "register_decision.idea")
    _require_unique_ids(entry_ready, "register_decision.entry_ready")
    _require_unique_ids(rejected, "register_decision.rejected")
    if set(idea) & set(entry_ready):
        raise ReplayError("register_decision.idea and register_decision.entry_ready overlap")
    if sorted(idea + entry_ready) != sorted(actionable_ids) or len(
        set(idea) | set(entry_ready)
    ) != len(actionable_ids):
        raise ReplayError("register decision must partition exactly the actionable hypotheses")
    if sorted(rejected) != sorted(excluded_ids):
        raise ReplayError("register decision rejected must match the gate-excluded hypotheses")
    sized_ids = {row["hypothesis_id"] for row in sized_doc["sized"]}
    if set(actionable_ids) != sized_ids:
        raise ReplayError("sized hypotheses must cover exactly the actionable hypothesis cards")
    card_by_id = {card["hypothesis_id"]: card for card in cards_doc["hypotheses"]}

    scripts_dir = repo_root / "skills" / "trader-memory-core" / "scripts"
    thesis_ingest = _repo_module(repo_root, "thesis_ingest", scripts_dir)
    thesis_store = _repo_module(repo_root, "thesis_store", scripts_dir)
    records = []
    for hypothesis_id in idea + entry_ready:
        card = card_by_id[hypothesis_id]
        if not card.get("ticker"):
            raise ReplayError(f"hypothesis {hypothesis_id} has no ticker for thesis registration")
        records.append(
            {
                "ticker": card["ticker"],
                "thesis_statement": card.get("thesis") or card.get("title") or hypothesis_id,
                "thesis_type": decision["thesis_type"],
                "as_of": fixed_date,
            }
        )
    state_dir = work / "multi-asset-state"
    state_dir.mkdir(parents=True)
    ingest_path = work / "manual_theses.json"
    _write_json(ingest_path, records)
    thesis_ids = thesis_ingest.ingest("manual", str(ingest_path), str(state_dir))
    if len(thesis_ids) != len(records):
        raise ReplayError("native thesis ingest did not register every expected thesis")
    theses = [thesis_store.get(state_dir, thesis_id) for thesis_id in thesis_ids]
    if sorted(row["ticker"] for row in theses) != sorted(
        card_by_id[hypothesis_id]["ticker"] for hypothesis_id in idea + entry_ready
    ):
        raise ReplayError("native thesis ingest did not register the expected tickers")

    linked_specs = [
        (
            "trade-hypothesis-ideator",
            _kanchi_artifact_link(consumed, "hypothesis_cards", "canonical", stage),
        ),
        ("position-sizer", _kanchi_artifact_link(consumed, "sized_hypotheses", "canonical", stage)),
    ]
    for thesis in theses:
        for skill, token in linked_specs:
            thesis_store.link_report(state_dir, thesis["thesis_id"], skill, token, fixed_date)

    entries = []
    registered_tickers = [
        card_by_id[hypothesis_id]["ticker"] for hypothesis_id in idea + entry_ready
    ]
    if len(set(registered_tickers)) != len(registered_tickers):
        raise ReplayError("registered hypotheses must have unique tickers")
    thesis_id_by_ticker = {row["ticker"]: row["thesis_id"] for row in theses}
    for hypothesis_id in actionable_ids:
        card = card_by_id[hypothesis_id]
        status = "ENTRY_READY" if hypothesis_id in set(entry_ready) else "IDEA"
        reloaded = thesis_store.get(state_dir, thesis_id_by_ticker[card["ticker"]])
        if reloaded["status"] != "IDEA":
            raise ReplayError("multi-asset registration must never leave IDEA status")
        if card.get("asset_class") == "forex" and not card.get("research_only"):
            raise ReplayError(f"forex hypothesis {hypothesis_id} must carry research_only=true")
        linked = reloaded.get("linked_reports") or []
        entries.append(
            {
                "hypothesis_id": hypothesis_id,
                "ticker": card.get("ticker"),
                "status": status,
                "thesis_id": None,
                "research_only": bool(card.get("research_only", False)),
                "linked_reports": linked,
            }
        )
    for card in cards_doc.get("excluded", []):
        hypothesis_id = card["hypothesis_id"]
        if card.get("asset_class") == "forex" and not card.get("research_only"):
            raise ReplayError(f"forex hypothesis {hypothesis_id} must carry research_only=true")
        entries.append(
            {
                "hypothesis_id": hypothesis_id,
                "ticker": card.get("ticker"),
                "status": "rejected",
                "thesis_id": None,
                "research_only": bool(card.get("research_only", False)),
                "linked_reports": [],
            }
        )
    entries.sort(key=lambda row: row["hypothesis_id"])
    record = {
        "schema_version": 1,
        "workflow_id": "multi-asset-opportunity-daily",
        "recorded_at": spec["fixed_timestamp"],
        "entries": entries,
        "provenance": {
            "execution_mode": "composite",
            "components": ["manual_contract", "native_api"],
            "native_component": "trader-memory-core.thesis_ingest + thesis_store.link_report",
            "source_date": fixed_date,
            "limitation": (
                "Human register decision is a fixture; no broker fill exists, so every "
                "thesis stays IDEA and no order is placed. ENTRY_READY is a recorded "
                "human decision, not a thesis transition. Thesis IDs are intentionally "
                "nulled because the state is disposable and never published."
            ),
        },
    }
    _validate_multi_asset_contract(record, "opportunity_journal_entries")
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["opportunity_journal_entries"]["files"]["canonical"]), record)
    return artifacts
