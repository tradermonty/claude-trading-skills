"""Executor registry mapping replay step ids to step adapters."""

from __future__ import annotations

from .common import ExecutorRegistration
from .steps_core_portfolio import (
    _core_portfolio_allocation,
    _core_portfolio_dividend,
    _core_portfolio_journal,
    _core_portfolio_rebalance,
    _core_portfolio_snapshot,
)
from .steps_earnings import (
    _earnings_analyze,
    _earnings_discipline,
    _earnings_journal,
    _earnings_pead,
    _earnings_size,
    _earnings_validate,
)
from .steps_ep import (
    _ep_analyze,
    _ep_circuit,
    _ep_discipline,
    _ep_journal,
    _ep_plan,
    _ep_screen,
    _ep_size,
    _ep_validate,
)
from .steps_kanchi import (
    _kanchi_high_yield_screen,
    _kanchi_pullback_screen,
    _kanchi_register_thesis,
    _kanchi_review_queue,
    _kanchi_tax_advice,
    _kanchi_underwrite,
)
from .steps_market_regime import (
    _market_regime_breadth,
    _market_regime_exposure,
    _market_regime_top_risk,
    _market_regime_uptrend,
)
from .steps_monthly import (
    _monthly_aggregate,
    _monthly_backtest,
    _monthly_coach,
    _monthly_decision_log,
    _monthly_postmortem,
    _monthly_skill_review,
)
from .steps_multi_asset import (
    _multi_hypotheses,
    _multi_macro_regime,
    _multi_news_brief,
    _multi_position_size,
    _multi_register,
    _multi_theme,
)
from .steps_portfolio_holdings import _portfolio_holdings_review
from .steps_shapiro import _shapiro_gate, _shapiro_journal, _shapiro_manual, _shapiro_size
from .steps_stockbee_fluency import (
    _manual_lessons,
    _stockbee_ingest,
    _stockbee_summarize,
    _stockbee_update,
)
from .steps_strategy_research import (
    _strategy_research_detect_final,
    _strategy_research_detect_initial,
    _strategy_research_hints,
    _strategy_research_hold,
)
from .steps_swing import (
    _swing_build_plan,
    _swing_canslim,
    _swing_circuit_breaker,
    _swing_discipline,
    _swing_exhaustion_hammer,
    _swing_journal,
    _swing_momentum_burst,
    _swing_position_size,
    _swing_theme,
    _swing_validate_setups,
    _swing_vcp_screen,
)
from .steps_trade_memory import (
    _trade_memory_backtest,
    _trade_memory_close,
    _trade_memory_coach,
    _trade_memory_lessons,
    _trade_memory_postmortem,
)
from .steps_twenty_pct import (
    _manual_twenty_pct_lessons,
    _twenty_pct_enrich,
    _twenty_pct_scan,
    _twenty_pct_summarize,
    _twenty_pct_update_outcomes,
)

EXECUTORS: dict[str, ExecutorRegistration] = {
    "portfolio_holdings_review": ExecutorRegistration("native_cli", _portfolio_holdings_review),
    "strategy_research_detect_initial": ExecutorRegistration(
        "native_cli", _strategy_research_detect_initial
    ),
    "strategy_research_hints": ExecutorRegistration("native_cli", _strategy_research_hints),
    "strategy_research_detect_final": ExecutorRegistration(
        "native_cli", _strategy_research_detect_final
    ),
    "strategy_research_hold": ExecutorRegistration("manual_contract", _strategy_research_hold),
    "earnings_circuit": ExecutorRegistration("native_cli", _swing_circuit_breaker),
    "earnings_analyze": ExecutorRegistration("native_cli", _earnings_analyze),
    "earnings_pead": ExecutorRegistration("native_cli", _earnings_pead),
    "earnings_validate": ExecutorRegistration("manual_contract", _earnings_validate),
    "earnings_size": ExecutorRegistration("native_cli", _earnings_size),
    "earnings_journal": ExecutorRegistration(
        "composite", _earnings_journal, ("manual_contract", "native_api")
    ),
    "earnings_discipline": ExecutorRegistration("native_cli", _earnings_discipline),
    "ep_circuit": ExecutorRegistration("native_cli", _ep_circuit),
    "ep_screen": ExecutorRegistration("manual_contract", _ep_screen),
    "ep_analyze": ExecutorRegistration("native_cli", _ep_analyze),
    "ep_validate": ExecutorRegistration("manual_contract", _ep_validate),
    "ep_size": ExecutorRegistration("native_cli", _ep_size),
    "ep_plan": ExecutorRegistration("manual_contract", _ep_plan),
    "ep_journal": ExecutorRegistration("composite", _ep_journal, ("manual_contract", "native_api")),
    "ep_discipline": ExecutorRegistration(
        "composite", _ep_discipline, ("manual_contract", "native_cli")
    ),
    "shapiro_manual": ExecutorRegistration("manual_contract", _shapiro_manual),
    "shapiro_gate": ExecutorRegistration("native_cli", _shapiro_gate),
    "shapiro_size": ExecutorRegistration("native_cli", _shapiro_size),
    "shapiro_journal": ExecutorRegistration(
        "composite", _shapiro_journal, ("manual_contract", "native_api")
    ),
    "stockbee_fluency_ingest": ExecutorRegistration("native_cli", _stockbee_ingest),
    "stockbee_fluency_update": ExecutorRegistration("native_cli", _stockbee_update),
    "stockbee_fluency_summarize": ExecutorRegistration("native_cli", _stockbee_summarize),
    "manual_lessons_log": ExecutorRegistration("manual_contract", _manual_lessons),
    "twenty_pct_scan": ExecutorRegistration("native_cli", _twenty_pct_scan),
    "twenty_pct_enrich": ExecutorRegistration("native_cli", _twenty_pct_enrich),
    "twenty_pct_update_outcomes": ExecutorRegistration("native_cli", _twenty_pct_update_outcomes),
    "twenty_pct_summarize": ExecutorRegistration("native_cli", _twenty_pct_summarize),
    "manual_twenty_pct_lessons": ExecutorRegistration(
        "manual_contract", _manual_twenty_pct_lessons
    ),
    "trade_memory_close": ExecutorRegistration("native_cli", _trade_memory_close),
    "trade_memory_postmortem": ExecutorRegistration(
        "composite",
        _trade_memory_postmortem,
        ("native_api", "manual_contract"),
    ),
    "trade_memory_coach": ExecutorRegistration(
        "composite",
        _trade_memory_coach,
        ("native_cli", "manual_contract"),
    ),
    "trade_memory_backtest": ExecutorRegistration("native_cli", _trade_memory_backtest),
    "trade_memory_lessons": ExecutorRegistration(
        "composite",
        _trade_memory_lessons,
        ("native_api", "manual_contract"),
    ),
    "market_regime_breadth": ExecutorRegistration("native_api", _market_regime_breadth),
    "market_regime_uptrend": ExecutorRegistration("native_api", _market_regime_uptrend),
    "market_regime_top_risk": ExecutorRegistration("native_api", _market_regime_top_risk),
    "market_regime_exposure": ExecutorRegistration("native_cli", _market_regime_exposure),
    "core_portfolio_snapshot": ExecutorRegistration("manual_contract", _core_portfolio_snapshot),
    "core_portfolio_allocation": ExecutorRegistration(
        "manual_contract", _core_portfolio_allocation
    ),
    "core_portfolio_dividend": ExecutorRegistration("native_api", _core_portfolio_dividend),
    "core_portfolio_rebalance": ExecutorRegistration("manual_contract", _core_portfolio_rebalance),
    "core_portfolio_journal": ExecutorRegistration("manual_contract", _core_portfolio_journal),
    "monthly_aggregate": ExecutorRegistration("manual_contract", _monthly_aggregate),
    "monthly_postmortem": ExecutorRegistration(
        "composite",
        _monthly_postmortem,
        ("native_api", "manual_contract"),
    ),
    "monthly_coach": ExecutorRegistration(
        "composite",
        _monthly_coach,
        ("native_cli", "manual_contract"),
    ),
    "monthly_backtest": ExecutorRegistration("native_cli", _monthly_backtest),
    "monthly_skill_review": ExecutorRegistration("native_cli", _monthly_skill_review),
    "monthly_decision_log": ExecutorRegistration("manual_contract", _monthly_decision_log),
    "swing_theme": ExecutorRegistration("manual_contract", _swing_theme),
    "swing_validate_setups": ExecutorRegistration("manual_contract", _swing_validate_setups),
    "swing_position_size": ExecutorRegistration("native_cli", _swing_position_size),
    "swing_build_plan": ExecutorRegistration("manual_contract", _swing_build_plan),
    "swing_journal": ExecutorRegistration("manual_contract", _swing_journal),
    "swing_discipline": ExecutorRegistration("native_cli", _swing_discipline),
    "swing_circuit_breaker": ExecutorRegistration("native_cli", _swing_circuit_breaker),
    "swing_vcp_screen": ExecutorRegistration("manual_contract", _swing_vcp_screen),
    "swing_momentum_burst": ExecutorRegistration("manual_contract", _swing_momentum_burst),
    "swing_exhaustion_hammer": ExecutorRegistration("manual_contract", _swing_exhaustion_hammer),
    "swing_canslim": ExecutorRegistration("manual_contract", _swing_canslim),
    "kanchi_high_yield_screen": ExecutorRegistration("manual_contract", _kanchi_high_yield_screen),
    "kanchi_pullback_screen": ExecutorRegistration("manual_contract", _kanchi_pullback_screen),
    "kanchi_underwrite": ExecutorRegistration(
        "composite",
        _kanchi_underwrite,
        ("native_cli", "native_api", "manual_contract"),
    ),
    "kanchi_tax_advice": ExecutorRegistration("native_cli", _kanchi_tax_advice),
    "kanchi_review_queue": ExecutorRegistration("native_cli", _kanchi_review_queue),
    "kanchi_register_thesis": ExecutorRegistration(
        "composite",
        _kanchi_register_thesis,
        ("manual_contract", "native_api"),
    ),
    "multi_macro_regime": ExecutorRegistration("native_api", _multi_macro_regime),
    "multi_theme": ExecutorRegistration("manual_contract", _multi_theme),
    "multi_news_brief": ExecutorRegistration("manual_contract", _multi_news_brief),
    "multi_hypotheses": ExecutorRegistration(
        "composite",
        _multi_hypotheses,
        ("native_cli", "manual_contract"),
    ),
    "multi_position_size": ExecutorRegistration("native_cli", _multi_position_size),
    "multi_register": ExecutorRegistration(
        "composite",
        _multi_register,
        ("manual_contract", "native_api"),
    ),
}
