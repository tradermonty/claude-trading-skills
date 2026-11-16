"""Markdown rendering and report output for evaluate_candidates."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation_candidate import _best_low_case_upside, _preferred_three_year_upside
from evaluation_common import (
    SCORE_LIMITS,
    InputError,
    _format_number,
    _format_pct,
    _format_price,
    _integer,
    _list,
    _mapping,
    _text,
    parse_iso8601,
)


def _label(language: str, en: str, ja: str) -> str:
    return ja if language == "ja" else en


def _missing(language: str) -> str:
    return "確認できず" if language == "ja" else "not verified"


def _md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ") if value is not None else ""


def _scenario_value(result: Mapping[str, Any], scenario: str, horizon: str, key: str) -> Any:
    return _mapping(_mapping(_mapping(result.get("valuation")).get(scenario)).get(horizon)).get(key)


def _render_list(values: Any, missing: str) -> str:
    rows = [str(value).strip() for value in _list(values) if str(value).strip()]
    return "; ".join(rows) if rows else missing


def _render_latest_earnings(language: str, records: Mapping[str, Any], missing: str) -> list[str]:
    lines: list[str] = []
    for key, en, ja in (
        ("quarter", "Latest quarter", "直近四半期"),
        ("full_year", "Latest full year", "直近通期"),
    ):
        record = _mapping(records.get(key))
        if not record:
            continue
        metrics = _mapping(record.get("metrics"))
        lines.append(f"**{_label(language, en, ja)} — {record.get('period', missing)}**")
        lines.extend(
            [
                f"- **{_label(language, 'Period end / published', '期末／発表日時')}:** {record.get('period_end', missing)} / {record.get('published_at', missing)}",
                f"- **{_label(language, 'Revenue / YoY', '売上高／前年比')}:** {_format_number(metrics.get('revenue'), 1, missing)} / {_format_pct(metrics.get('revenue_yoy_pct'), 1, missing)}",
                f"- **{_label(language, 'GAAP operating income / margin', 'GAAP営業利益／利益率')}:** {_format_number(metrics.get('gaap_operating_income'), 1, missing)} / {_format_pct(metrics.get('gaap_operating_margin_pct'), 1, missing)}",
                f"- **GAAP / Adjusted EPS:** {_format_number(metrics.get('gaap_eps'), 2, missing)} / {_format_number(metrics.get('adjusted_eps'), 2, missing)}",
                f"- **{_label(language, 'OCF / standard FCF', '営業CF／標準FCF')}:** {_format_number(metrics.get('operating_cash_flow'), 1, missing)} / {_format_number(metrics.get('standard_fcf'), 1, missing)}",
                f"- **{_label(language, 'Growth state', '成長状態')}:** {record.get('growth_state') or record.get('derived_growth_state') or missing}",
                f"- **{_label(language, 'Guidance', 'ガイダンス')}:** {_render_list(record.get('guidance'), missing)}",
                f"- **KPI:** {_render_list(record.get('key_kpis'), missing)}",
                f"- **{_label(language, 'One-time items', '一時項目')}:** {_render_list(record.get('one_time_items'), missing)}",
            ]
        )
    return lines or [missing]


def _render_peers(language: str, peers: Sequence[Any], missing: str) -> list[str]:
    lines = [
        "| Ticker | Company | Multiple | Basis | Period | Selection reason |",
        "|---|---|---:|---|---|---|",
    ]
    if not peers:
        lines.append(f"| {missing} | {missing} | {missing} | {missing} | {missing} | {missing} |")
        return lines
    for item in peers:
        peer = _mapping(item)
        lines.append(
            "| {symbol} | {company} | {multiple} | {basis} | {period} | {reason} |".format(
                symbol=_md_escape(peer.get("symbol", missing)),
                company=_md_escape(peer.get("company_name", missing)),
                multiple=_format_number(peer.get("multiple"), 2, missing),
                basis=_md_escape(peer.get("metric_basis", missing)),
                period=_md_escape(peer.get("multiple_period_kind", missing)),
                reason=_md_escape(peer.get("selection_reason", missing)),
            )
        )
    return lines


def _render_score_table(row: Mapping[str, Any], missing: str) -> list[str]:
    components = _mapping(row.get("score_components"))
    penalties = _mapping(row.get("penalties"))
    lines = ["| Component | Score | Maximum |", "|---|---:|---:|"]
    for key, maximum in SCORE_LIMITS.items():
        lines.append(f"| {key} | {_format_number(components.get(key), 1, missing)} | {maximum:g} |")
    lines.append(f"| Raw score | {_format_number(row.get('raw_score'), 1, missing)} | 100 |")
    lines.append(f"| Penalties | -{_format_number(row.get('total_penalty'), 1, missing)} | — |")
    lines.append(f"| Final score | {_format_number(row.get('final_score'), 1, missing)} | 100 |")
    lines.append("")
    lines.append(
        "**Penalty breakdown:** " + ", ".join(f"{key}={value}" for key, value in penalties.items())
    )
    return lines


def _render_candidate_detail(language: str, row: Mapping[str, Any]) -> list[str]:
    missing = _missing(language)
    identity = _mapping(row.get("identity"))
    metrics = _mapping(row.get("financial_metrics"))
    cash_flow = _mapping(metrics.get("cash_flow_ttm"))
    valuation = _mapping(row.get("valuation"))
    periods = _mapping(valuation.get("periods"))
    qualitative = _mapping(row.get("qualitative"))
    latest_records = _mapping(row.get("latest_earnings_records"))
    cyclicality = _mapping(row.get("cyclicality"))
    lines: list[str] = []

    lines.append(f"### {row.get('rank')}. {row.get('company_name')} ({row.get('symbol')})")
    lines.append("")
    lines.append(f"#### 1. {_label(language, 'Basic Information', '基本情報')}")
    lines.extend(
        [
            f"- **{_label(language, 'Exchange / sector / industry', '取引所／セクター／業種')}:** {identity.get('exchange', missing)} / {identity.get('sector', missing)} / {identity.get('industry', missing)}",
            f"- **{_label(language, 'Price / market cap', '株価／時価総額')}:** {_format_price(identity.get('price'), identity.get('currency', 'USD'), missing)} / {_format_number(identity.get('market_cap'), 1, missing)}",
            f"- **{_label(language, 'Liquidity', '流動性')}:** {_format_number(identity.get('average_daily_dollar_volume'), 1, missing)}",
            f"- **{_label(language, 'Business overview', '企業概要')}:** {qualitative.get('business_overview', missing)}",
        ]
    )
    lines.append("")
    lines.append(f"#### 2. {_label(language, 'Investment Thesis', '投資仮説')}")
    lines.append(str(qualitative.get("investment_thesis") or missing))
    lines.append("")
    lines.append(f"#### 3. {_label(language, 'Valuation', 'バリュエーション')}")
    lines.extend(
        [
            f"- **{_label(language, 'Valuation basis', '評価基準')}:** {valuation.get('basis', missing)} / {valuation.get('current_metric_basis', missing)} / {valuation.get('current_period_kind', missing)}",
            f"- **{_label(language, 'Current metric / multiple', '現在指標／倍率')}:** {_format_number(valuation.get('current_metric'), 2, missing)} / {_format_number(valuation.get('current_multiple'), 2, missing)}x",
            f"- **{_label(language, 'Peer median multiple', '同業中央値倍率')}:** {_format_number(valuation.get('peer_median_multiple'), 2, missing)}x",
            f"- **{_label(language, 'EV/FCF', 'EV/FCF')}:** {_format_number(metrics.get('ev_to_fcf'), 2, missing)}x",
            f"- **{_label(language, 'Enterprise value / cash definition', '企業価値／現金定義')}:** {_format_number(metrics.get('enterprise_value'), 1, missing)} / {metrics.get('cash_definition', missing)}",
            f"- **{_label(language, 'Standard / SBC-adjusted FCF yield', '標準／SBC調整後FCF利回り')}:** {_format_pct(metrics.get('fcf_yield_pct'), 1, missing)} / {_format_pct(metrics.get('sbc_adjusted_fcf_yield_pct'), 1, missing)}",
        ]
    )
    lines.append("")
    lines.append(f"#### 4. {_label(language, 'Growth History and Forecasts', '成長実績と予想')}")
    lines.extend(
        [
            f"- **{_label(language, 'Revenue CAGR', '売上CAGR')}:** {_format_pct(metrics.get('revenue_cagr_pct'), 1, missing)}",
            f"- **{_label(language, 'GAAP EPS CAGR', 'GAAP EPS CAGR')}:** {_format_pct(metrics.get('gaap_eps_cagr_pct'), 1, missing)}",
            f"- **{_label(language, 'FCF/share CAGR', 'FCF per share CAGR')}:** {_format_pct(metrics.get('fcf_per_share_cagr_pct'), 1, missing)}",
            f"- **{_label(language, 'Current / year-2 / year-3 metric', '現在／2年後／3年後指標')}:** {_format_number(_mapping(periods.get('current')).get('metric'), 2, missing)} / {_format_number(_mapping(periods.get('year_2')).get('metric'), 2, missing)} / {_format_number(_mapping(periods.get('year_3')).get('metric'), 2, missing)}",
            f"- **{_label(language, 'Forecast bridge', '予想ブリッジ')}:** {'PASS' if valuation.get('forecast_bridge_valid') else 'FAIL'}",
        ]
    )
    lines.append("")
    lines.append(f"#### 5. {_label(language, 'Latest Earnings', '直近決算')}")
    lines.extend(_render_latest_earnings(language, latest_records, missing))
    lines.append("")
    lines.append(f"#### 6. {_label(language, 'Growth Drivers', '成長ドライバー')}")
    lines.append(_render_list(qualitative.get("growth_drivers"), missing))
    lines.append("")
    lines.append(f"#### 7. {_label(language, 'Peer Comparison', '同業他社比較')}")
    lines.extend(_render_peers(language, _list(row.get("peers")), missing))
    lines.append("")
    lines.append(f"#### 8. {_label(language, 'Why the Stock Is Discounted', 'なぜ割安なのか')}")
    lines.extend(
        [
            f"- **{_label(language, 'Market concerns', '市場の懸念')}:** {_render_list(qualitative.get('discount_reasons'), missing)}",
            f"- **{_label(language, 'Temporary or structural', '一時的か構造的か')}:** {qualitative.get('discount_classification', missing)}",
            f"- **{_label(language, 'How the market may be right', '市場評価が妥当な可能性')}:** {qualitative.get('market_may_be_right', missing)}",
            f"- **{_label(language, 'Conditions for discount closure', 'ディスカウント縮小条件')}:** {_render_list(qualitative.get('rerating_conditions'), missing)}",
        ]
    )
    lines.append("")
    lines.append(
        f"#### 9. {_label(language, 'Constant-Multiple Scenario', '倍率据え置きシナリオ')}"
    )
    lines.append("| Item | Current | Year 2 | Year 3 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        f"| Metric | {_format_number(valuation.get('current_metric'), 2, missing)} | {_format_number(_mapping(periods.get('year_2')).get('metric'), 2, missing)} | {_format_number(_mapping(periods.get('year_3')).get('metric'), 2, missing)} |"
    )
    lines.append(
        f"| Multiple | {_format_number(valuation.get('current_multiple'), 2, missing)}x | {_format_number(valuation.get('current_multiple'), 2, missing)}x | {_format_number(valuation.get('current_multiple'), 2, missing)}x |"
    )
    lines.append(
        f"| Implied price | {_format_price(identity.get('price'), identity.get('currency', 'USD'), missing)} | {_format_price(_scenario_value(row, 'constant_multiple', 'year_2', 'implied_price'), identity.get('currency', 'USD'), missing)} | {_format_price(_scenario_value(row, 'constant_multiple', 'year_3', 'implied_price'), identity.get('currency', 'USD'), missing)} |"
    )
    lines.append(
        f"| Upside | — | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_2', 'upside_pct'), 1, missing)} | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_3', 'upside_pct'), 1, missing)} |"
    )
    lines.append(
        f"| Annualized return | — | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_2', 'cagr_pct'), 1, missing)} | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_3', 'cagr_pct'), 1, missing)} |"
    )
    lines.append("")
    lines.append(
        f"#### 10. {_label(language, '20% Multiple-Contraction Scenario', '倍率20％低下シナリオ')}"
    )
    lines.append(
        f"- **2-year:** {_format_price(_scenario_value(row, 'multiple_contraction', 'year_2', 'implied_price'), identity.get('currency', 'USD'), missing)} / {_format_pct(_scenario_value(row, 'multiple_contraction', 'year_2', 'upside_pct'), 1, missing)}"
    )
    lines.append(
        f"- **3-year:** {_format_price(_scenario_value(row, 'multiple_contraction', 'year_3', 'implied_price'), identity.get('currency', 'USD'), missing)} / {_format_pct(_scenario_value(row, 'multiple_contraction', 'year_3', 'upside_pct'), 1, missing)}"
    )
    lines.append("")
    lines.append(f"#### 11. {_label(language, 'Catalysts', 'カタリスト')}")
    lines.append(_render_list(qualitative.get("catalysts"), missing))
    lines.append("")
    lines.append(f"#### 12. {_label(language, 'Largest Risk', '最大のリスク')}")
    lines.append(str(qualitative.get("maximum_risk") or missing))
    lines.append("")
    lines.append(f"#### 13. {_label(language, 'Invalidation Conditions', '投資仮説の無効化条件')}")
    lines.append(_render_list(qualitative.get("invalidation_conditions"), missing))
    lines.append("")
    lines.append(f"#### 14. {_label(language, 'Cyclicality', 'シクリカル評価')}")
    lines.extend(
        [
            f"- **{_label(language, 'Cyclicality score', 'シクリカル度')}:** {cyclicality.get('score', missing)}/5",
            f"- **{_label(language, 'Cycle position', '現在のサイクル位置')}:** {cyclicality.get('position', missing)}",
            f"- **{_label(language, 'Peak-profit risk', 'ピーク利益リスク')}:** {cyclicality.get('peak_profit_risk', missing)}",
            f"- **{_label(language, 'Normalized metric', '平準化指標')}:** {_format_number(_mapping(cyclicality.get('normalization')).get('normalized_metric'), 2, missing)}",
        ]
    )
    lines.append("")
    lines.append(f"#### 15. {_label(language, 'Overall Score', '総合評価')}")
    lines.extend(_render_score_table(row, missing))
    lines.append("")
    lines.append(
        f"#### 16. {_label(language, 'Cash-Flow and Evidence Audit', 'キャッシュフロー・証拠監査')}"
    )
    lines.extend(
        [
            f"- **{_label(language, 'TTM method', 'TTM再構築方法')}:** {cash_flow.get('method', missing)}",
            f"- **{_label(language, 'OCF / capex / standard FCF', '営業CF／設備投資／標準FCF')}:** {_format_number(cash_flow.get('operating_cash_flow'), 1, missing)} / {_format_number(cash_flow.get('capex_cash_outflow'), 1, missing)} / {_format_number(cash_flow.get('standard_fcf'), 1, missing)}",
            f"- **{_label(language, 'Company adjusted FCF', '会社Adjusted FCF')}:** {_format_number(cash_flow.get('company_adjusted_fcf'), 1, missing)} ({cash_flow.get('company_adjusted_fcf_definition', missing)})",
            f"- **{_label(language, 'Data quality', 'データ品質')}:** {row.get('data_quality_score')}/100",
            f"- **{_label(language, 'Cash consistency', '現金・負債整合性')}:** {_md_escape(row.get('cash_consistency'))}",
            f"- **{_label(language, 'Warnings', '警告')}:** {_render_list(row.get('warnings'), missing)}",
            f"- **{_label(language, 'Unresolved', '未解決')}:** {_render_list(row.get('unresolved_fields'), missing)}",
        ]
    )
    lines.append("")
    return lines


def render_markdown(report: Mapping[str, Any], *, language: str = "en") -> str:
    missing = _missing(language)
    ranked = _list(report.get("ranked_candidates"))
    conditional = _list(report.get("conditional"))
    review = _list(report.get("review_required"))
    screened_out = _list(report.get("screened_out"))
    excluded = _list(report.get("excluded"))
    broad = _mapping(report.get("broad_screen"))
    broad_counts = _mapping(broad.get("counts"))
    counts = _mapping(report.get("counts"))
    funnel = _mapping(report.get("screening_funnel"))
    price_basis = _mapping(report.get("price_basis"))
    lines: list[str] = []

    title = _label(
        language,
        "US Undervalued Growth Screening Report",
        "米国株・割安成長株スクリーニングレポート",
    )
    coverage = _mapping(report.get("coverage"))
    ranking_scope = _text(report.get("ranking_scope"))
    if ranking_scope == "final_scoped":
        evaluated = coverage.get("economic_attempt_count", "?")
        listed = coverage.get("listing_universe_count", "?")
        title += _label(
            language,
            f" — Scoped Pilot ({evaluated} of {listed} listed names economically attempted)",
            f" — 限定パイロット（上場{listed}銘柄中{evaluated}銘柄のみ経済評価を試行）",
        )
    elif ranking_scope == "diagnostic":
        title += _label(language, " — DIAGNOSTIC (incomplete scope)", " — 診断用（範囲未完了）")
    if report.get("ranking_status") != "final":
        title += _label(language, " — PROVISIONAL", " — 暫定")
    lines.append(f"# {title}")
    lines.append("")
    if ranking_scope and ranking_scope != "final_marketwide":
        attempt_pct = coverage.get("economic_attempt_coverage_pct")
        attempt_pct_text = f"{float(attempt_pct):.2f}%" if attempt_pct is not None else missing
        evaluable_pct = coverage.get("economically_evaluable_coverage_pct")
        evaluable_pct_text = (
            f"{float(evaluable_pct):.2f}%" if evaluable_pct is not None else missing
        )
        lines.append(
            f"- **{_label(language, 'Ranking scope', 'ランキング範囲')}:** {ranking_scope} — "
            + _label(
                language,
                (
                    f"conclusions bind ONLY to the {coverage.get('economic_attempt_count', '?')} names whose estimate "
                    f"acquisition was attempted ({attempt_pct_text} of "
                    f"{coverage.get('listing_universe_count', '?')} listed; economically evaluable {coverage.get('economically_evaluable_count', '?')} = {evaluable_pct_text}; quality probe {coverage.get('quality_probe_count', '?')}, "
                    f"deep dive {coverage.get('deep_dive_count', '?')}). This is NOT a market-wide ranking."
                ),
                (
                    f"結論は予想取得を試行した{coverage.get('economic_attempt_count', '?')}銘柄"
                    f"（上場{coverage.get('listing_universe_count', '?')}銘柄の{attempt_pct_text}、"
                    f"評価可能{coverage.get('economically_evaluable_count', '?')}銘柄・{evaluable_pct_text}、品質プローブ{coverage.get('quality_probe_count', '?')}銘柄、詳細分析{coverage.get('deep_dive_count', '?')}銘柄）"
                    "に限定され、市場全体ランキングではありません。"
                ),
            )
        )
    lines.append(
        f"- **{_label(language, 'Analysis as of', '分析実施日時')}:** {report.get('analysis_as_of')}"
    )
    lines.append(
        f"- **{_label(language, 'Price basis', '株価基準')}:** {price_basis.get('as_of', missing)} / {price_basis.get('session', missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Ranking status', 'ランキング状態')}:** {report.get('ranking_status')}"
    )
    lines.append(
        f"- **{_label(language, 'Strict mode', '厳格モード')}:** {report.get('strict_mode')}"
    )
    lines.append(
        f"- **{_label(language, 'Deep-dive input / ranked / conditional / review / screened out / excluded', '詳細調査入力／ランキング／条件付き／要確認／スクリーニング落ち／除外')}:** {counts.get('input_candidates')} / {counts.get('ranked')} / {counts.get('conditional', 0)} / {counts.get('review_required')} / {counts.get('screened_out')} / {counts.get('excluded')}"
    )
    lines.append(
        f"- **{_label(language, 'Broad-screen selected / deferred / unresolved / screened out / excluded / unavailable', '一次選定／予算繰越／未解決／一次落ち／除外／取得不能')}:** {broad_counts.get('selected', 0)} / {broad_counts.get('deferred_by_budget', 0)} / {broad_counts.get('review_required', 0)} / {broad_counts.get('screened_out', 0)} / {broad_counts.get('excluded', 0)} / {broad_counts.get('unavailable_after_enrichment', 0)}"
    )
    lines.append("")

    lines.append(
        f"## {_label(language, 'Screening Funnel and Market Context', 'スクリーニング・ファネルと市場前提')}"
    )
    lines.append("")
    lines.append(f"- **Listing universe:** {funnel.get('universe_count', missing)}")
    lines.append(f"- **Listing rows in scope:** {funnel.get('listing_in_scope_count', missing)}")
    lines.append(
        f"- **Fundamental/estimate candidate pool:** {funnel.get('candidate_pool_count', missing)}"
    )
    lines.append(
        f"- **Discovery-evaluable candidates:** {funnel.get('discovery_evaluable_count', missing)}"
    )
    lines.append(f"- **Deep dives selected:** {funnel.get('deep_dive_selected_count', missing)}")
    lines.append(
        f"- **Corporate-action preflight passed:** {funnel.get('preflight_passed_count', missing)}"
    )
    lines.append(f"- **Deep dives completed:** {funnel.get('deep_dive_completed_count', missing)}")
    market = _mapping(report.get("market_context"))
    audit = _mapping(report.get("screening_audit"))
    scope = _mapping(audit.get("scope"))
    lines.append(
        f"- **{_label(language, 'Candidate-generation mode', '候補生成モード')}:** {audit.get('candidate_generation_mode', missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Candidate-pool status', '候補プール状態')}:** {audit.get('candidate_pool_status', missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Selection outcome', '候補選定結果')}:** {audit.get('selection_outcome', missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Listing-data coverage', '上場・価格データカバレッジ')}:** {_format_pct(audit.get('actual_listing_data_complete_pct'), 1, missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Candidate-pool discovery coverage', '候補プール経済評価可能カバレッジ')}:** {_format_pct(audit.get('actual_candidate_pool_discovery_evaluable_pct'), 1, missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Candidate-pool full-fundamental coverage (informational)', '候補プール完全財務カバレッジ（参考）')}:** {_format_pct(audit.get('actual_candidate_pool_fundamental_complete_pct'), 1, missing)}"
    )
    lines.append(
        f"- **{_label(language, 'Listing enumeration', 'リスティング列挙')}:** complete={scope.get('scope_complete', False)} / requested ${scope.get('requested_min_market_cap', missing)}-${scope.get('requested_max_market_cap', missing)} / retrieved ${scope.get('retrieval_min_market_cap', missing)}-${scope.get('retrieval_max_market_cap', missing)}"
    )
    generation = _mapping(_mapping(audit.get("candidate_pool")).get("generation_audit"))
    if generation:
        universe_total = _integer(_mapping(audit.get("universe")).get("row_count"))
        mode = _text(generation.get("estimate_acquisition_mode")) or missing
        bulk = _mapping(generation.get("bulk_estimate_audit"))
        covered = _integer(bulk.get("covered_symbol_count"))
        seeds = _integer(generation.get("economic_attempt_count"))
        if mode == "analyst_estimates_bulk" and covered is not None and universe_total:
            coverage = f"{covered} / {universe_total} ({covered / universe_total * 100.0:.1f}%)"
            status = "complete" if covered >= universe_total else "partial"
        elif seeds is not None and universe_total:
            coverage = f"{seeds} / {universe_total} ({seeds / universe_total * 100.0:.1f}%)"
            status = "partial"
        else:
            coverage = missing
            status = "partial"
        lines.append(
            f"- **{_label(language, 'Economic estimate coverage', '経済スクリーン範囲')}:** {status} / mode={mode} / {coverage} -- {_label(language, 'never a market-wide conclusion under', '以下の範囲での結論に限定')} conclusion_scope={audit.get('conclusion_scope', missing)}"
        )
    lines.append(
        f"- **{_label(language, 'Market assumptions', '市場前提')}:** {market.get('summary', missing)}"
    )
    lines.append(
        f"- **Policy / 10Y / Inflation / Market Fwd P/E:** {_format_pct(market.get('policy_rate_pct'), 2, missing)} / {_format_pct(market.get('treasury_10y_yield_pct'), 2, missing)} / {_format_pct(market.get('inflation_yoy_pct'), 2, missing)} / {_format_number(market.get('market_forward_pe'), 2, missing)}x"
    )
    lines.append(
        f"- **{_label(language, 'Universe audit SHA-256', '上場母集団監査SHA-256')}:** {audit.get('actual_universe_sha256', missing)}"
    )
    enrichment = _mapping(audit.get("enrichment"))
    lines.append(
        f"- **{_label(language, 'Candidate-pool audit SHA-256', '候補プール監査SHA-256')}:** {audit.get('actual_candidate_pool_sha256', missing)} / valid={audit.get('valid', False)}"
    )
    lines.append(
        f"- **{_label(language, 'Enrichment resolved / unresolved / exhausted', 'エンリッチメント解決済み／未解決／プール枯渇')}:** {audit.get('actual_enrichment_resolved_count', missing)} / {audit.get('actual_enrichment_unresolved_count', missing)} / {audit.get('actual_candidate_pool_exhausted', False)}"
    )
    lines.append(
        f"- **{_label(language, 'Next action', '次の処理')}:** {enrichment.get('next_action', missing)}"
    )
    lines.append("")

    lines.append(f"## A. {_label(language, 'Ranking', 'ランキング一覧')}")
    lines.append("")
    if ranked:
        lines.append(
            "| Rank | Company | Ticker | Price | Market Cap | Forward Basis | Forward Multiple | EV/FCF | FCF Yield | ROIC | Diluted Share CAGR | Cyclicality | Rankable 3Y/2Y Upside | Score | DQ |"
        )
        lines.append("|---:|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in ranked:
            identity = _mapping(row.get("identity"))
            metrics = _mapping(row.get("financial_metrics"))
            valuation = _mapping(row.get("valuation"))
            lines.append(
                "| {rank} | {company} | {symbol} | {price} | {cap} | {basis} | {multiple} | {evfcf} | {fcf} | {roic} | {dilution} | {cycle} | {upside} | {score} | {dq} |".format(
                    rank=row.get("rank"),
                    company=_md_escape(row.get("company_name")),
                    symbol=row.get("symbol"),
                    price=_format_price(
                        identity.get("price"), identity.get("currency", "USD"), missing
                    ),
                    cap=_format_number(identity.get("market_cap"), 1, missing),
                    basis=f"{valuation.get('basis', missing)}/{valuation.get('current_metric_basis', missing)}",
                    multiple=_format_number(valuation.get("current_multiple"), 2, missing),
                    evfcf=_format_number(metrics.get("ev_to_fcf"), 2, missing),
                    fcf=_format_pct(metrics.get("fcf_yield_pct"), 1, missing),
                    roic=_format_pct(metrics.get("roic_pct"), 1, missing),
                    dilution=_format_pct(metrics.get("diluted_share_cagr_pct"), 1, missing),
                    cycle=_mapping(row.get("cyclicality")).get("score", missing),
                    upside=_format_pct(
                        _preferred_three_year_upside(valuation, "constant_multiple"), 1, missing
                    ),
                    score=_format_number(row.get("final_score"), 1, missing),
                    dq=row.get("data_quality_score", missing),
                )
            )
    else:
        pool_status = _text(_mapping(report.get("contract")).get("candidate_pool_status"))
        if report.get("ranking_status") == "final" and pool_status == "no_qualifying_candidates":
            lines.append(
                _label(
                    language,
                    "No qualifying candidates in the audited full universe.",
                    "監査済みの全対象ユニバースでは現時点で該当なし。",
                )
            )
        elif (
            report.get("ranking_status") == "final"
            and pool_status == "no_qualifying_candidates_in_bounded_pool"
        ):
            cov = _mapping(report.get("coverage"))
            lines.append(
                _label(
                    language,
                    (
                        f"No qualifying candidates among the {cov.get('deep_dive_count', '?')} deep-dived names "
                        f"selected from the {cov.get('economic_attempt_count', '?')} economically attempted "
                        f"(of {cov.get('listing_universe_count', '?')} listed); the remaining names were never "
                        "economically compared — this is not a market-wide conclusion."
                    ),
                    (
                        f"経済評価を試行した{cov.get('economic_attempt_count', '?')}銘柄から選定した"
                        f"{cov.get('deep_dive_count', '?')}銘柄の詳細分析では該当なし"
                        f"（上場{cov.get('listing_universe_count', '?')}銘柄の残りは未審査であり、"
                        "市場全体の該当なしを意味しません）。"
                    ),
                )
            )
        else:
            lines.append(
                _label(
                    language,
                    "Ranking withheld: candidate-pool research is incomplete.",
                    "ランキング保留：候補プールの調査が未完了です。",
                )
            )
    lines.append("")

    lines.append(f"## B. {_label(language, 'Scenario Table', 'シナリオ表')}")
    lines.append("")
    lines.append(
        "| Ticker | Current Metric | Current Multiple | 2Y Price | 2Y Upside | 2Y Stress Price | 2Y Stress Upside | 3Y Price | 3Y Upside | 3Y Stress Price | 3Y Stress Upside | Peer 3Y Price |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in ranked:
        valuation = _mapping(row.get("valuation"))
        currency = _mapping(row.get("identity")).get("currency", "USD")
        lines.append(
            f"| {row.get('symbol')} | {_format_number(valuation.get('current_metric'), 2, missing)} | {_format_number(valuation.get('current_multiple'), 2, missing)} | {_format_price(_scenario_value(row, 'constant_multiple', 'year_2', 'implied_price'), currency, missing)} | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_2', 'upside_pct'), 1, missing)} | {_format_price(_scenario_value(row, 'multiple_contraction', 'year_2', 'implied_price'), currency, missing)} | {_format_pct(_scenario_value(row, 'multiple_contraction', 'year_2', 'upside_pct'), 1, missing)} | {_format_price(_scenario_value(row, 'constant_multiple', 'year_3', 'implied_price'), currency, missing)} | {_format_pct(_scenario_value(row, 'constant_multiple', 'year_3', 'upside_pct'), 1, missing)} | {_format_price(_scenario_value(row, 'multiple_contraction', 'year_3', 'implied_price'), currency, missing)} | {_format_pct(_scenario_value(row, 'multiple_contraction', 'year_3', 'upside_pct'), 1, missing)} | {_format_price(_scenario_value(row, 'peer_median', 'year_3', 'implied_price'), currency, missing)} |"
        )
    lines.append("")

    lines.append(f"## C. {_label(language, 'Candidate Details', '各銘柄の詳細')}")
    lines.append("")
    for row in ranked:
        lines.extend(_render_candidate_detail(language, row))

    lines.append(f"## D. {_label(language, 'Conditional Candidates', '条件付き候補')}")
    lines.append("")
    if conditional:
        lines.append("| Ticker | Company | Final Score | Conditions | Low-case Upside |")
        lines.append("|---|---|---:|---|---:|")
        for row in conditional:
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_format_number(row.get('final_score'), 1, missing)} | {_md_escape('; '.join(row.get('conditional_reasons') or []))} | {_format_pct(_best_low_case_upside(_mapping(row.get('valuation'))), 1, missing)} |"
            )
    else:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")

    lines.append(f"## E. {_label(language, 'Review Required', '追加確認が必要な候補')}")
    lines.append("")
    if review:
        lines.append(f"### {_label(language, 'Deep-dive review blockers', '詳細調査の要確認')}")
        lines.append("| Ticker | Company | Final Score | Blockers | Evidence Needed |")
        lines.append("|---|---|---:|---|---|")
        for row in review:
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_format_number(row.get('final_score'), 1, missing)} | {_md_escape('; '.join(row.get('review_reasons') or []))} | {_md_escape('; '.join(row.get('unresolved_fields') or []) or missing)} |"
            )
        lines.append("")
    broad_review = _list(broad.get("review_required"))
    broad_deferred = _list(broad.get("deferred_by_budget"))
    broad_selected = _list(broad.get("selected"))
    broad_unavailable = _list(broad.get("unavailable_after_enrichment"))
    if broad_selected or broad_deferred or broad_review or broad_unavailable:
        lines.append(
            f"### {_label(language, 'Broad-screen dispositions requiring or deferring work', '一次スクリーニングの要確認・繰越')}"
        )
        lines.append(
            "| Ticker | Company | Status | Fwd P/E | Revenue Growth | Per-share Growth | Priority | Reasons / Requirements |"
        )
        lines.append("|---|---|---|---:|---:|---:|---:|---|")
        for row in broad_selected + broad_deferred + broad_review + broad_unavailable:
            metrics = _mapping(row.get("metrics"))
            reasons = list(row.get("review_reasons") or []) + list(
                row.get("deep_dive_requirements") or []
            )
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {row.get('status')} | {_format_number(metrics.get('forward_pe'), 2, missing)} | {_format_pct(metrics.get('revenue_growth_pct'), 1, missing)} | {_format_pct(metrics.get('per_share_growth_pct'), 1, missing)} | {_format_number(row.get('deep_dive_priority_score'), 1, missing)} | {_md_escape('; '.join(dict.fromkeys(reasons)) or missing)} |"
            )
    elif not review:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")

    lines.append(f"## F. {_label(language, 'Screened-Out Log', 'スクリーニング落ちログ')}")
    lines.append("")
    if screened_out:
        lines.append(
            f"### {_label(language, 'Deep-dive screened out', '詳細調査でのスクリーニング落ち')}"
        )
        lines.append("| Ticker | Company | Reason |")
        lines.append("|---|---|---|")
        for row in screened_out:
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_md_escape('; '.join(row.get('screening_reasons') or []))} |"
            )
        lines.append("")
    broad_screened = _list(broad.get("screened_out"))
    if broad_screened:
        lines.append(
            f"### {_label(language, 'Broad-screen screened out', '一次スクリーニング落ち')}"
        )
        lines.append(
            "| Ticker | Company | Fwd P/E | Revenue Growth | Per-share Growth | Guideline Misses | Screen-Fail Reasons |"
        )
        lines.append("|---|---|---:|---:|---:|---|---|")
        for row in broad_screened:
            metrics = _mapping(row.get("metrics"))
            lines.append(
                f"| {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_format_number(metrics.get('forward_pe'), 2, missing)} | {_format_pct(metrics.get('revenue_growth_pct'), 1, missing)} | {_format_pct(metrics.get('per_share_growth_pct'), 1, missing)} | {_md_escape('; '.join(row.get('guideline_misses') or []) or missing)} | {_md_escape('; '.join(row.get('screen_fail_reasons') or []) or missing)} |"
            )
    elif not screened_out:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")

    lines.append(f"## G. {_label(language, 'Hard Exclusion Log', 'ハード除外ログ')}")
    lines.append("")
    broad_excluded = _list(broad.get("excluded"))
    if excluded or broad_excluded:
        lines.append("| Stage | Ticker | Company | Reason |")
        lines.append("|---|---|---|---|")
        for row in excluded:
            lines.append(
                f"| deep_dive | {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_md_escape('; '.join(row.get('hard_exclusion_reasons') or []))} |"
            )
        for row in broad_excluded:
            reasons = list(row.get("review_reasons") or []) + list(
                row.get("screen_fail_reasons") or []
            )
            lines.append(
                f"| broad_screen | {row.get('symbol')} | {_md_escape(row.get('company_name'))} | {_md_escape('; '.join(reasons) or missing)} |"
            )
    else:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")

    lines.append(f"## H. {_label(language, 'Final Three', '最終選定3銘柄')}")
    lines.append("")
    categories = [
        ("highest_conviction", "Highest conviction", "最も確度が高い"),
        ("most_undervalued", "Most undervalued", "最も割安"),
        ("largest_upside", "Largest upside", "最も上昇余地が大きい"),
    ]
    for key, en, ja in categories:
        entry = _mapping(_mapping(report.get("final_three")).get(key))
        lines.append(f"### {_label(language, en, ja)}")
        if not entry:
            lines.append(missing)
            lines.append("")
            continue
        lines.extend(
            [
                f"- **Ticker:** {entry.get('symbol')} — {entry.get('company_name')}",
                f"- **{_label(language, 'Why it qualifies', '最も有望と判断した理由')}:** {entry.get('investment_thesis') or missing}",
                f"- **{_label(language, 'Per-share growth upside', 'EPS/FCF成長だけの上昇余地')}:** {_format_pct(entry.get('constant_multiple_upside_pct'), 1, missing)}",
                f"- **{_label(language, 'What the market may miss', '市場が見落としている可能性')}:** {entry.get('market_may_be_missing') or missing}",
                f"- **{_label(language, 'Best catalyst', '最有力カタリスト')}:** {entry.get('best_catalyst') or missing}",
                f"- **{_label(language, 'Largest risk', '最大のリスク')}:** {entry.get('maximum_risk') or missing}",
                f"- **{_label(language, 'Reason not to buy now', '今買わない理由')}:** {entry.get('do_not_buy_reason') or missing}",
                f"- **{_label(language, 'Bear case', '弱気シナリオ')}:** {entry.get('bear_case') or missing}",
                f"- **{_label(language, 'Invalidation', '無効化条件')}:** {_render_list(entry.get('invalidation_conditions'), missing)}",
                f"- **{_label(language, 'Next earnings KPIs', '次回決算KPI')}:** {_render_list(entry.get('next_earnings_kpis'), missing)}",
            ]
        )
        lines.append("")

    source_rows: dict[str, Mapping[str, Any]] = {}
    for source in _list(report.get("global_sources")):
        item = _mapping(source)
        source_id = _text(item.get("id"))
        if source_id:
            source_rows[source_id] = item
    for row in ranked + review + screened_out + excluded:
        for source in _list(row.get("sources")):
            item = _mapping(source)
            source_id = _text(item.get("id"))
            if source_id:
                source_rows[source_id] = item
    lines.append(f"## I. {_label(language, 'Source Ledger', '情報源台帳')}")
    lines.append("")
    if source_rows:
        lines.append("| Source ID | Tier | Kind | Published | Retrieved | Supports |")
        lines.append("|---|---:|---|---|---|---|")
        for source_id in sorted(source_rows):
            source = source_rows[source_id]
            lines.append(
                f"| {_md_escape(source_id)} | {source.get('tier', missing)} | {_md_escape(source.get('kind', missing))} | {_md_escape(source.get('published_at', missing))} | {_md_escape(source.get('retrieved_at', missing))} | {_md_escape(', '.join(str(value) for value in _list(source.get('supports'))))} |"
            )
    else:
        lines.append(missing)
    lines.append("")

    lines.append(
        f"## J. {_label(language, 'Unresolved Data and Global Warnings', '未解決データと全体警告')}"
    )
    lines.append("")
    warnings = _list(report.get("global_warnings"))
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append(_label(language, "None.", "なし。"))
    lines.append("")
    lines.append(
        _label(
            language,
            "This report is a research screen, not an automatic order or guarantee of return.",
            "本レポートは調査用スクリーニングであり、自動発注や収益保証ではありません。",
        )
    )
    lines.append("")
    return "\n".join(lines)


def _timestamp_for_filename(report: Mapping[str, Any]) -> str:
    generated = _text(report.get("generated_at"))
    if generated:
        try:
            parsed = parse_iso8601(generated, "generated_at")
            if parsed:
                return parsed.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
        except InputError:
            pass
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def write_outputs(
    report: Mapping[str, Any], output_dir: Path, *, language: str
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp_for_filename(report)
    json_path = output_dir / f"us_undervalued_growth_{stamp}.json"
    md_path = output_dir / f"us_undervalued_growth_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report, language=language), encoding="utf-8")
    return json_path, md_path
