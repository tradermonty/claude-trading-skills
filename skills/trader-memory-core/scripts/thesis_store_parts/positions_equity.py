# thesis_store part: Position math, equity path: attach, open, trim, close, terminate, and
# outcome finalization. Each public entry point dispatches futures theses
# to positions_futures.py before any equity math runs.
#
# This file is a source fragment of thesis_store.py, not an importable module.
# thesis_store.py executes it into its own namespace (see _exec_parts there), so
# every name below is a thesis_store attribute and all fragments share one set
# of globals. The TYPE_CHECKING block only declares, for linters and readers,
# which names this fragment uses from the shared namespace; it never runs.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import json
    import math
    from pathlib import Path

    import thesis_store

    _ATTACH_ALLOWED = thesis_store._ATTACH_ALLOWED
    _TERMINAL_STATUSES = thesis_store._TERMINAL_STATUSES
    _close_futures = thesis_store._close_futures
    _coerce_dt = thesis_store._coerce_dt
    _has_unsupported_equity_short = thesis_store._has_unsupported_equity_short
    _is_futures = thesis_store._is_futures
    _load_index = thesis_store._load_index
    _load_thesis = thesis_store._load_thesis
    _now_iso = thesis_store._now_iso
    _open_futures_position = thesis_store._open_futures_position
    _parse_dt = thesis_store._parse_dt
    _require_long_equity_direction = thesis_store._require_long_equity_direction
    _save_index = thesis_store._save_index
    _save_thesis = thesis_store._save_thesis
    _terminate_futures = thesis_store._terminate_futures
    _trim_futures = thesis_store._trim_futures
    _update_index_entry = thesis_store._update_index_entry
    _valid_finite_number = thesis_store._valid_finite_number
    _valid_finite_positive = thesis_store._valid_finite_positive
    _validate_equity_actual_prices = thesis_store._validate_equity_actual_prices
    _validate_equity_initial_stop = thesis_store._validate_equity_initial_stop
    _validate_equity_long_only = thesis_store._validate_equity_long_only
    logger = thesis_store.logger


def attach_position(
    state_dir: Path,
    thesis_id: str,
    position_report_path: str,
    expected_entry: float | None = None,
    expected_stop: float | None = None,
) -> dict:
    """Attach position-sizer output to an existing thesis.

    Validates:
      1. Report mode must be "shares" (budget mode has no shares/value/risk).
      2. If expected_entry is provided, must match report's entry_price.
      3. If expected_stop is provided, must match report's stop_price.

    Raises:
        ValueError: If validation fails.
        FileNotFoundError: If report or thesis doesn't exist.
    """
    report_path = Path(position_report_path)
    if not report_path.exists():
        raise FileNotFoundError(f"Position report not found: {position_report_path}")

    with open(report_path) as f:
        report = json.load(f)

    # Validate mode
    mode = report.get("mode")
    if mode != "shares":
        raise ValueError(
            f"Position report mode is '{mode}', expected 'shares'. "
            "Budget mode does not produce shares/value/risk fields."
        )

    # A shares report must not silently discard a short direction or use
    # short-style initial geometry. Inspect report prices, not the original
    # cost of an ACTIVE long whose protective stop may have moved higher.
    _require_long_equity_direction(report.get("direction"), normalize=True)
    params = report.get("parameters")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError("Equity long-only position report parameters must be a mapping")
    _require_long_equity_direction(params.get("direction"), normalize=True)
    _validate_equity_initial_stop(params.get("entry_price"), params.get("stop_price"))

    # Validate expected entry/stop
    if expected_entry is not None:
        actual_entry = params.get("entry_price")
        if actual_entry is not None and abs(actual_entry - expected_entry) > 0.01:
            raise ValueError(
                f"Entry price mismatch: thesis expects {expected_entry}, report has {actual_entry}"
            )
    if expected_stop is not None:
        actual_stop = params.get("stop_price")
        if actual_stop is not None and abs(actual_stop - expected_stop) > 0.01:
            raise ValueError(
                f"Stop price mismatch: thesis expects {expected_stop}, report has {actual_stop}"
            )

    thesis = _load_thesis(state_dir, thesis_id)

    # Cross-attach guard (P1 addendum, user re-review, money-critical, same
    # root cause as the update() P1 fix): the status guard below only
    # blocks re-attaching on the WRONG STATUS — it says nothing about
    # whether a position of the OPPOSITE asset type is already attached.
    # IDEA/ENTRY_READY are in BOTH _ATTACH_ALLOWED and
    # _ATTACH_FUTURES_ALLOWED, so without this check, calling
    # attach_position() on a thesis that already has a futures position
    # (attach_futures_position() doesn't advance status) silently replaces
    # the ENTIRE position dict with an equity shares dict — direction/
    # multiplier/quantity/contract_spec vanish, _is_futures(thesis)
    # flips to False, and open_position()/close()/trim() then dispatch
    # into the legacy EQUITY per-unit path for what was a futures trade
    # (wrong sign, wrong magnitude, no error anywhere — confirmed
    # reproducible before this fix). Symmetric guard in
    # attach_futures_position() below.
    if _is_futures(thesis):
        raise ValueError(
            "attach_position() cannot attach an equity position to a thesis "
            "that already has a futures position — use attach_futures_position() "
            "instead, or register a fresh thesis"
        )

    # Validate loaded intent before replacing position: a save-time check on
    # the new shares dict alone would lose a legacy SHORT marker.
    _validate_equity_long_only(thesis)

    # attach_position() (re)writes position incl. shares_remaining == shares
    # — see the module-level _ATTACH_ALLOWED docstring for why this status
    # guard exists.
    if thesis["status"] not in _ATTACH_ALLOWED:
        raise ValueError(
            f"attach_position() not allowed for status {thesis['status']}; "
            f"only {sorted(_ATTACH_ALLOWED)} (would corrupt shares_remaining)"
        )

    # Determine sizing method from whichever calculation was actually used
    sizing_method = None
    calcs = report.get("calculations", {})
    for method_key in ("fixed_fractional", "atr_based", "kelly"):
        if calcs.get(method_key) is not None:
            sizing_method = calcs[method_key].get("method", method_key)
            break

    thesis["position"] = {
        "shares": report.get("final_recommended_shares"),
        "shares_remaining": report.get("final_recommended_shares"),
        "position_value": report.get("final_position_value"),
        "risk_dollars": report.get("final_risk_dollars"),
        "risk_pct_of_account": report.get("final_risk_pct"),
        "account_type": None,
        "sizing_method": sizing_method,
        "raw_source": {
            "skill": "position-sizer",
            "file": str(position_report_path),
            "fields": {
                "final_recommended_shares": report.get("final_recommended_shares"),
                "final_position_value": report.get("final_position_value"),
                "final_risk_dollars": report.get("final_risk_dollars"),
            },
        },
    }
    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Attached position to %s: %s shares", thesis_id, thesis["position"]["shares"])
    return thesis


def _sum_realized(history: list[dict]) -> float:
    """Σ realized_pnl over status_history ledger entries (trims + final leg)."""
    return sum(e["realized_pnl"] for e in history if "realized_pnl" in e)


def _finalize_outcome(
    thesis: dict,
    *,
    exit_price: float,
    exit_date: str,
    history_at: str,
    status: str,
    reason: str,
    append_entry: bool,
) -> None:
    """Roll up the cumulative realized outcome for a position-backed thesis.

    Single owner of the final-leg status_history ledger append. Callers:
      - close() / terminate(): append_entry=True (this appends the one final
        ledger entry for the still-open remainder).
      - trim() full close-out: append_entry=False (trim already appended the
        final ledger entry; here we only sum + finalize).

    Precondition: thesis has a position with shares (legacy / no-position
    theses keep their pre-PR-80B code path in the caller and never reach here).

    Output-side finiteness (Issue #254, pre-existing money-critical gap —
    same "guard the OUTPUT, not just the input" principle and the same
    two-layer arithmetic/finiteness pattern as `_finalize_futures_outcome()`):
    every value computed here (proceeds, realized_pnl,
    cumulative pnl_dollars via `_sum_realized()`, pnl_pct) is computed
    into a LOCAL variable and validated finite BEFORE any mutation of
    `thesis`/`position`/`status_history`. Validation is TWO layers, both
    required:

      1. `try/except OverflowError` around the arithmetic itself. A huge
         Python int operand (e.g. a disk-corrupted `shares: 10**400` that
         bypassed `_validate_thesis()` at write time — see D1's
         `_validate_equity_position_fields()`, which only runs on
         `_save_thesis()`, not on read) makes `round(10**400 * 1.5, 2)`
         raise `OverflowError` from *inside* the multiplication —
         `math.isfinite()` is never reached. Verified empirically.
      2. `math.isfinite()` on the result, for the case where the
         arithmetic itself succeeds but produces `inf`/`nan` (e.g.
         `shares = float("inf")`, which multiplies cleanly to `inf`
         without raising).

    Both layers apply to `math.isfinite()` itself too, not just the
    preceding arithmetic — `_sum_realized()` over an all-Python-int
    ledger can return a huge *int* result (no float ever entered the
    computation, so `round()` doesn't raise), and `math.isfinite()` on
    THAT huge int raises OverflowError in turn. Each finiteness check
    below therefore lives inside the same `try` as the value it checks.
    """
    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")
    position = thesis["position"]
    original = position["shares"]
    remaining = position.get("shares_remaining", original)

    new_entry = None
    if append_entry:
        try:
            leg_proceeds = round(exit_price * remaining, 2)
            leg_realized = round((exit_price - entry_price) * remaining, 2)
            leg_finite = math.isfinite(leg_proceeds) and math.isfinite(leg_realized)
        except OverflowError as exc:
            raise ValueError(
                "computed proceeds/realized_pnl overflowed (exit_price="
                f"{exit_price}, shares={remaining}) — operands too large"
            ) from exc
        if not leg_finite:
            raise ValueError(
                f"computed proceeds/realized_pnl is not finite ({leg_proceeds}, {leg_realized})"
            )
        new_entry = {
            "status": status,
            "at": history_at,
            "reason": reason,
            "shares_sold": remaining,
            "price": exit_price,
            "proceeds": leg_proceeds,
            "realized_pnl": leg_realized,
        }

    # Cumulative pnl_dollars computed WITHOUT mutating status_history yet
    # — _sum_realized() runs over the existing ledger plus the
    # not-yet-appended new_entry, so a non-finite/overflowing cumulative
    # result still rejects cleanly before any state changes.
    history_for_sum = thesis["status_history"] + ([new_entry] if new_entry else [])
    try:
        pnl_dollars = round(_sum_realized(history_for_sum), 2)
        pnl_dollars_finite = math.isfinite(pnl_dollars)
    except OverflowError as exc:
        raise ValueError(
            "computed cumulative pnl_dollars overflowed — the position's "
            "realized P&L ledger contains an operand too large"
        ) from exc
    if not pnl_dollars_finite:
        raise ValueError(f"computed cumulative pnl_dollars is not finite ({pnl_dollars})")

    pnl_pct = None
    if entry_price and original:
        try:
            pnl_pct = round(pnl_dollars / (entry_price * original) * 100, 2)
            pnl_pct_finite = math.isfinite(pnl_pct)
        except OverflowError as exc:
            raise ValueError(
                "computed pnl_pct overflowed — the notional denominator (entry * shares) overflowed"
            ) from exc
        if not pnl_pct_finite:
            raise ValueError(f"computed pnl_pct is not finite ({pnl_pct})")

    holding_days = None
    if entry_date:
        try:
            holding_days = (_parse_dt(exit_date) - _parse_dt(entry_date)).days
        except (ValueError, TypeError):
            pass

    # All computed values validated finite — now, and only now, mutate.
    if new_entry is not None:
        thesis["status_history"].append(new_entry)
    position["shares_remaining"] = 0
    thesis["status"] = status
    thesis["outcome"]["pnl_dollars"] = pnl_dollars
    thesis["outcome"]["pnl_pct"] = pnl_pct
    thesis["outcome"]["holding_days"] = holding_days


def close(
    state_dir: Path,
    thesis_id: str,
    exit_reason: str,
    actual_price: float,
    actual_date: str,
    event_date: str | None = None,
) -> dict:
    """Close an ACTIVE or PARTIALLY_CLOSED thesis and compute outcome.

    With a position: outcome is the cumulative realized P&L (Σ trim
    realized_pnl + this final leg). With no position: the pre-PR-80B
    single-leg behaviour is kept verbatim.

    Args:
        state_dir: Path to state/theses/.
        thesis_id: Thesis to close.
        exit_reason: One of stop_hit, target_hit, time_stop, invalidated, manual.
        actual_price: Exit price.
        actual_date: Exit date (ISO format).
        event_date: Optional ISO timestamp for status_history.at (for backfilling).

    Returns:
        Updated thesis dict.

    Raises:
        ValueError: If thesis is not ACTIVE/PARTIALLY_CLOSED or entry missing.
    """
    thesis = _load_thesis(state_dir, thesis_id)

    # Dispatch at function entry (D2/D4 non-negotiable, see _is_futures
    # docstring): a futures thesis must NEVER reach the legacy no-position
    # branch below, which ignores multiplier/direction entirely.
    if _is_futures(thesis):
        return _close_futures(state_dir, thesis, exit_reason, actual_price, actual_date, event_date)

    if thesis["status"] not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only close ACTIVE or PARTIALLY_CLOSED thesis, current status: {thesis['status']}"
        )

    # Issue #257: this runs after futures dispatch but before any equity
    # arithmetic or mutation. The stored-price check also covers hand-edited
    # or legacy YAML that bypassed the save-time validation above.
    _validate_equity_actual_prices(thesis)
    if _valid_finite_number(actual_price) is None:
        raise ValueError(
            f"close() requires a finite actual_price for an equity thesis, got {actual_price!r}"
        )

    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")

    if entry_price is None:
        raise ValueError("Cannot close thesis: entry.actual_price is not set")

    # Set exit data
    thesis["exit"]["actual_price"] = actual_price
    thesis["exit"]["actual_date"] = actual_date
    thesis["exit"]["exit_reason"] = exit_reason

    now = _now_iso()
    history_at = event_date or now
    position = thesis.get("position")

    if position and position.get("shares"):
        # Cumulative path (single-owner ledger append in _finalize_outcome).
        _finalize_outcome(
            thesis,
            exit_price=actual_price,
            exit_date=actual_date,
            history_at=history_at,
            status="CLOSED",
            reason=f"closed: {exit_reason}",
            append_entry=True,
        )
    else:
        # Legacy no-position path — pre-PR-80B behaviour, byte-identical.
        pnl_dollars = actual_price - entry_price
        pnl_pct = ((actual_price - entry_price) / entry_price) * 100 if entry_price else None
        holding_days = None
        if entry_date:
            try:
                holding_days = (_parse_dt(actual_date) - _parse_dt(entry_date)).days
            except (ValueError, TypeError):
                pass
        thesis["outcome"]["pnl_dollars"] = (
            round(pnl_dollars, 2) if pnl_dollars is not None else None
        )
        thesis["outcome"]["pnl_pct"] = round(pnl_pct, 2) if pnl_pct is not None else None
        thesis["outcome"]["holding_days"] = holding_days
        thesis["status"] = "CLOSED"
        thesis["status_history"].append(
            {"status": "CLOSED", "at": history_at, "reason": f"closed: {exit_reason}"}
        )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Closed %s: %s, P&L=%.2f%%",
        thesis_id,
        exit_reason,
        thesis["outcome"].get("pnl_pct") or 0,
    )
    return thesis


def trim(
    state_dir: Path,
    thesis_id: str,
    shares_sold: float,
    price: float,
    date: str,
    reason: str = "position trimmed",
    exit_reason: str | None = None,
    event_date: str | None = None,
) -> dict:
    """Partially close (trim) an ACTIVE / PARTIALLY_CLOSED position.

    Records a status_history ledger entry (shares_sold / price / proceeds /
    realized_pnl) and decrements position.shares_remaining. If the trim sells
    the entire remaining quantity it becomes a full close-out (status CLOSED,
    exit fields set, cumulative outcome).

    Args:
        shares_sold: Quantity sold in this trim (0 < shares_sold <= remaining).
        price: Trim execution price.
        date: Trim execution date (YYYY-MM-DD or ISO).
        exit_reason: Only used when this trim fully closes the position
            (default "manual"); ∈ stop_hit/target_hit/time_stop/invalidated/manual.
        event_date: Overrides the ledger timestamp (else --date is used).

    Raises:
        ValueError: On bad status / missing entry / no position / bad qty.
    """
    thesis = _load_thesis(state_dir, thesis_id)

    # Dispatch at function entry (D2/D4 non-negotiable, see _is_futures
    # docstring): a futures thesis must never reach the equity per-unit
    # math below.
    if _is_futures(thesis):
        return _trim_futures(
            state_dir, thesis, shares_sold, price, date, reason, exit_reason, event_date
        )

    status = thesis["status"]
    if status not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only trim ACTIVE or PARTIALLY_CLOSED thesis, current status: {status}"
        )

    # Issue #257: keep the finite-only equity contract separate from the
    # finite-positive futures branch dispatched above.
    _validate_equity_actual_prices(thesis)
    if _valid_finite_number(price) is None:
        raise ValueError(f"trim() requires a finite price for an equity thesis, got {price!r}")

    entry_price = thesis["entry"].get("actual_price")
    if entry_price is None:
        raise ValueError("Cannot trim thesis: entry.actual_price is not set")

    position = thesis.get("position")
    if not position or position.get("shares") is None:
        raise ValueError("trim requires a recorded position — run open-position --shares first")

    original = position["shares"]
    remaining = position.get("shares_remaining", original)  # legacy default
    if not (0 < shares_sold <= remaining):
        raise ValueError(
            f"shares_sold ({shares_sold}) must be > 0 and <= shares_remaining ({remaining})"
        )
    # Note: this range check is comparison-based, not arithmetic — a
    # huge/nan/inf shares_sold is already rejected here (comparisons
    # never raise OverflowError in Python, unlike the multiplication/
    # subtraction below), so no separate input-side guard is needed.

    # Output-side finiteness (Issue #254, pre-existing money-critical gap
    # — see _finalize_outcome()'s docstring for the two-layer rationale:
    # try/except OverflowError for arithmetic that can raise mid-
    # computation on a disk-corrupted huge `shares_remaining` — e.g. a
    # thesis that bypassed _validate_thesis()'s write-time D1 chokepoint
    # — PLUS math.isfinite() for a clean-but-inf/nan result). Both layers
    # apply before any state mutation below.
    try:
        realized = round((price - entry_price) * shares_sold, 2)
        proceeds = round(price * shares_sold, 2)
        # Round to kill float-subtraction noise (7.86 - 4.00 == 3.86000…3),
        # then epsilon-snap a ~0 remainder to an exact 0.0 (→ full close-out).
        new_remaining = round(remaining - shares_sold, 8)
        trim_finite = (
            math.isfinite(realized) and math.isfinite(proceeds) and math.isfinite(new_remaining)
        )
    except OverflowError as exc:
        raise ValueError(
            f"computed realized_pnl/proceeds/shares_remaining overflowed (price={price}, "
            f"shares_sold={shares_sold}) — operands too large"
        ) from exc
    if not trim_finite:
        raise ValueError(
            "computed realized_pnl/proceeds/shares_remaining is not finite "
            f"({realized}, {proceeds}, {new_remaining})"
        )
    if abs(new_remaining) < 1e-9:
        new_remaining = 0.0

    now = _now_iso()
    history_at = _coerce_dt(event_date) or _coerce_dt(date)
    full_close = new_remaining == 0
    new_status = "CLOSED" if full_close else "PARTIALLY_CLOSED"

    # trim() owns its ledger append (exactly one entry per trim).
    thesis["status_history"].append(
        {
            "status": new_status,
            "at": history_at,
            "reason": reason,
            "shares_sold": shares_sold,
            "price": price,
            "proceeds": proceeds,
            "realized_pnl": realized,
        }
    )
    position["shares_remaining"] = new_remaining

    if full_close:
        exit_date = _coerce_dt(date)
        thesis["exit"]["actual_price"] = price
        thesis["exit"]["actual_date"] = exit_date
        thesis["exit"]["exit_reason"] = exit_reason or "manual"
        thesis["status"] = "CLOSED"
        # Ledger entry already appended above → append_entry=False (sum only).
        _finalize_outcome(
            thesis,
            exit_price=price,
            exit_date=exit_date,
            history_at=history_at,
            status="CLOSED",
            reason=reason,
            append_entry=False,
        )
    else:
        thesis["status"] = "PARTIALLY_CLOSED"

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Trimmed %s: sold %s @ %.4f → %s remaining, status %s",
        thesis_id,
        shares_sold,
        price,
        new_remaining,
        thesis["status"],
    )
    return thesis


def open_position(
    state_dir: Path,
    thesis_id: str,
    actual_price: float,
    actual_date: str,
    reason: str = "position opened",
    shares: float | None = None,
    event_date: str | None = None,
    contracts: float | None = None,
    multiplier: float | None = None,
    direction: str | None = None,
    contract_symbol: str | None = None,
    contract_currency: str | None = None,
    allow_gap_fill: bool = False,
) -> dict:
    """Transition thesis from ENTRY_READY to ACTIVE with entry data.

    This is the only way to reach ACTIVE status. transition() blocks ACTIVE.

    Args:
        state_dir: Path to state/theses/.
        thesis_id: Thesis to activate.
        actual_price: Entry price.
        actual_date: Entry date (ISO format).
        reason: Transition reason.
        shares: Optional share count to record (equity).
        event_date: Optional ISO timestamp for status_history.at (for backfilling).
        contracts: Optional contract count to record (futures; P2-1). If a
            futures position was already attached via
            attach_futures_position(), leave this None — the attached
            quantity is used. If given, this is a "direct open" that
            populates position from scratch and REQUIRES multiplier,
            direction, AND contract_currency too.
        multiplier: Futures contract multiplier — required with `contracts`
            on a direct open (no attached position).
        direction: "LONG" | "SHORT" — required with `contracts` on a direct
            open (no attached position).
        contract_symbol: Optional futures contract symbol (e.g. "ES").
        contract_currency: Required with `contracts` on a direct open
            (P1-addendum-2, user re-review): a direct open with no
            attach_futures_position() handoff has no contract_spec at all,
            so — unlike the attach path — there is no currency to
            validate unless the caller supplies one explicitly. Must be
            exactly "USD" (this skill has no FX conversion); a direct
            open with no currency, or a non-USD currency, is rejected
            rather than silently treated as USD.

        allow_gap_fill: Explicit equity-only acknowledgement of a positive
            actual fill below the existing positive planned stop. Leaves the
            plan intact and records the stop/fill in protected status history.
            Does not permit explicit equity SHORT intent or alter sizing.

    Returns:
        Updated thesis dict.

    Raises:
        ValueError: If thesis is not ENTRY_READY.
    """
    if not isinstance(allow_gap_fill, bool):
        raise ValueError("allow_gap_fill must be a bool")

    # P3-2: providing both is never meaningful (one silently overrides or
    # gets ignored depending on dispatch order) — fail loud instead of
    # silently picking one.
    if shares is not None and contracts is not None:
        raise ValueError(
            "open_position() got both shares and contracts; provide either "
            "--shares (equity) or --contracts (futures), not both"
        )

    thesis = _load_thesis(state_dir, thesis_id)
    if allow_gap_fill and (contracts is not None or _is_futures(thesis)):
        raise ValueError("--allow-gap-fill is equity-only; futures keep their existing contract")

    # Dispatch at function entry (D2/D4 non-negotiable, see _is_futures
    # docstring). `contracts is not None` covers a direct futures open with
    # no prior attach; `_is_futures(thesis)` covers open_position() called
    # after attach_futures_position() already populated position. The
    # existing equity `shares=` branch below is untouched.
    if contracts is not None or _is_futures(thesis):
        return _open_futures_position(
            state_dir,
            thesis,
            actual_price,
            actual_date,
            reason=reason,
            contracts=contracts,
            multiplier=multiplier,
            direction=direction,
            contract_symbol=contract_symbol,
            contract_currency=contract_currency,
            event_date=event_date,
        )

    _require_long_equity_direction(direction, normalize=True)

    if thesis["status"] != "ENTRY_READY":
        raise ValueError(f"open_position() requires ENTRY_READY status, got {thesis['status']}")

    # Issue #257: reject malformed equity entry prices before the thesis
    # can reach ACTIVE. Futures dispatch above retains its stricter
    # finite-positive contract and error messages.
    _validate_equity_actual_prices(thesis)
    if _valid_finite_number(actual_price) is None:
        raise ValueError(
            "open_position() requires a finite actual_price for an equity thesis, "
            f"got {actual_price!r}"
        )

    stop_loss = thesis.get("exit", {}).get("stop_loss")
    gap_fill = (
        _valid_finite_positive(actual_price) is not None
        and _valid_finite_positive(stop_loss) is not None
        and actual_price < stop_loss
    )
    if gap_fill:
        if not allow_gap_fill:
            raise ValueError(
                "Equity accounting is long-only; fill is below the planned stop. "
                "Use --allow-gap-fill only to record an acknowledged long fill "
                "without rewriting its plan."
            )
        if not isinstance(reason, str):
            raise ValueError("gap-fill acknowledgement requires a string reason")
        # Status history is immutable through generic update(). Preserve exact
        # stop/fill values here even if a later lifecycle update changes stop_loss.
        reason += (
            f"; gap fill acknowledged: actual_price={actual_price!r}, "
            f"planned_stop_loss={stop_loss!r}"
        )
    else:
        _validate_equity_initial_stop(actual_price, stop_loss)

    now = _now_iso()
    thesis["entry"]["actual_price"] = actual_price
    thesis["entry"]["actual_date"] = actual_date
    if shares is not None:
        if thesis["position"] is None:
            thesis["position"] = {}
        thesis["position"]["shares"] = shares
    # A PR-80B-era ACTIVE thesis carries shares_remaining explicitly (== the
    # full opened quantity). Covers both --shares here and an earlier
    # attach_position()-populated position; legacy (no shares) stays absent.
    pos = thesis.get("position")
    if pos and pos.get("shares") is not None and pos.get("shares_remaining") is None:
        pos["shares_remaining"] = pos["shares"]

    history_at = event_date or now
    thesis["status"] = "ACTIVE"
    thesis["status_history"].append({"status": "ACTIVE", "at": history_at, "reason": reason})
    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Opened position %s at %.2f", thesis_id, actual_price)
    return thesis


def terminate(
    state_dir: Path,
    thesis_id: str,
    terminal_status: str,
    exit_reason: str,
    actual_price: float | None = None,
    actual_date: str | None = None,
    event_date: str | None = None,
) -> dict:
    """Move thesis to a terminal state (CLOSED or INVALIDATED).

    For CLOSED: delegates to close() which requires actual_price/date.
    For INVALIDATED: actual_price/date are optional. If ACTIVE with price,
    computes P&L. Partial outcome (no P&L) is allowed.

    Args:
        event_date: Optional ISO timestamp for status_history.at (for backfilling).

    Raises:
        ValueError: If terminal_status is invalid or thesis is already terminal.
    """
    if terminal_status == "CLOSED":
        if actual_price is None or actual_date is None:
            raise ValueError("CLOSED requires actual_price and actual_date")
        return close(
            state_dir, thesis_id, exit_reason, actual_price, actual_date, event_date=event_date
        )

    if terminal_status != "INVALIDATED":
        raise ValueError(f"terminal_status must be CLOSED or INVALIDATED, got {terminal_status}")

    thesis = _load_thesis(state_dir, thesis_id)

    # Dispatch at function entry (D2/D4 non-negotiable, see _is_futures
    # docstring): a futures thesis must never reach the legacy per-unit
    # partial-outcome branch below, which ignores multiplier/direction.
    if _is_futures(thesis):
        return _terminate_futures(
            state_dir, thesis, exit_reason, actual_price, actual_date, event_date
        )

    if thesis["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot terminate: already in terminal status {thesis['status']}")

    # INVALIDATED permits an omitted price, but a provided equity price
    # and any stored prices must be finite before outcome calculation or
    # exit/status mutation. Futures were dispatched above.
    legacy_short = _has_unsupported_equity_short(thesis)
    if legacy_short and actual_price is not None:
        raise ValueError(
            "Equity accounting is long-only; invalidate legacy shorts without an exit price"
        )
    # A no-price invalidation only retires the record, preserving all money
    # fields and provenance. It must not manufacture a long-side outcome.
    _validate_equity_actual_prices(thesis, allow_legacy_short=legacy_short)
    if actual_price is not None and _valid_finite_number(actual_price) is None:
        raise ValueError(
            "terminate() requires a finite actual_price for an equity thesis "
            f"when provided, got {actual_price!r}"
        )

    now = _now_iso()

    # Set exit data if provided
    if actual_price is not None:
        thesis["exit"]["actual_price"] = actual_price
    if actual_date is not None:
        thesis["exit"]["actual_date"] = actual_date
    # exit_reason enum: use "invalidated"; user's reason goes in status_history
    thesis["exit"]["exit_reason"] = "invalidated"

    entry_price = thesis["entry"].get("actual_price")
    history_at = event_date or now
    position = thesis.get("position")

    if (
        position
        and position.get("shares")
        and actual_price is not None
        and actual_date is not None
        and entry_price
    ):
        # Cumulative path: single-owner ledger append + roll-up. For a no-trim
        # ACTIVE thesis (shares_remaining == shares) this yields the same
        # pnl_dollars/pct as the legacy block below; for a PARTIALLY_CLOSED
        # thesis it correctly sums prior trims (no double-count).
        _finalize_outcome(
            thesis,
            exit_price=actual_price,
            exit_date=actual_date,
            history_at=history_at,
            status="INVALIDATED",
            reason=f"invalidated: {exit_reason}",
            append_entry=True,
        )
    else:
        # Pre-PR-80B partial-outcome path — verbatim (covers no-price
        # terminate INVALIDATED, incl. position-attached but no exit price).
        #
        # Output-side finiteness (Issue #254, pre-existing money-critical
        # gap — same two-layer rationale as _finalize_outcome()'s
        # docstring): pnl_dollars/pnl_pct are computed into LOCAL
        # variables and validated (try/except OverflowError for
        # mid-arithmetic overflow on a disk-corrupted huge `shares`, then
        # math.isfinite() for a clean-but-inf/nan result) BEFORE any
        # mutation of thesis["outcome"]. compute_outcome mirrors the
        # original `if entry_price and actual_price:` gate exactly, so a
        # thesis with no price data is untouched exactly as before.
        pnl_pct = None
        pnl_dollars = None
        holding_days = None
        compute_outcome = bool(entry_price and actual_price)
        if compute_outcome:
            try:
                pnl_pct_raw = ((actual_price - entry_price) / entry_price) * 100
                pnl_dollars_raw = actual_price - entry_price
                if thesis.get("position") and thesis["position"].get("shares"):
                    pnl_dollars_raw *= thesis["position"]["shares"]
                pnl_pct = round(pnl_pct_raw, 2)
                pnl_dollars = round(pnl_dollars_raw, 2)
                outcome_finite = math.isfinite(pnl_pct) and math.isfinite(pnl_dollars)
            except OverflowError as exc:
                raise ValueError(
                    "computed pnl_dollars/pnl_pct overflowed (actual_price="
                    f"{actual_price}, entry_price={entry_price}) — operands too large"
                ) from exc
            if not outcome_finite:
                raise ValueError(
                    f"computed pnl_dollars/pnl_pct is not finite ({pnl_dollars}, {pnl_pct})"
                )

            entry_date = thesis["entry"].get("actual_date")
            if entry_date and actual_date:
                try:
                    holding_days = (_parse_dt(actual_date) - _parse_dt(entry_date)).days
                except (ValueError, TypeError):
                    pass

        # All computed values validated finite — now, and only now, mutate.
        if compute_outcome:
            thesis["outcome"]["pnl_pct"] = pnl_pct
            thesis["outcome"]["pnl_dollars"] = pnl_dollars
            if holding_days is not None:
                thesis["outcome"]["holding_days"] = holding_days

        thesis["status"] = "INVALIDATED"
        thesis["status_history"].append(
            {
                "status": "INVALIDATED",
                "at": history_at,
                "reason": f"invalidated: {exit_reason}",
            }
        )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis, allow_legacy_short=legacy_short)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Terminated %s → INVALIDATED: %s", thesis_id, exit_reason)
    return thesis
