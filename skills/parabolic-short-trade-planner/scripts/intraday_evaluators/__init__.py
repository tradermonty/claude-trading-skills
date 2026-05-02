"""Phase 3 trigger evaluators (pure functions).

Each module exports an ``evaluate(plan, bars, *, atr_14,
vwap_series=None) -> dict`` function. Importing as
``from intraday_evaluators import orl_evaluator`` keeps the dispatch
table in ``intraday_state_machine`` readable.
"""
