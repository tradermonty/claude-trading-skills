# thesis_store part: Position math, futures path (contracts x multiplier, signed direction).
#
# This file is a source fragment of thesis_store.py, not an importable module.
# thesis_store.py executes it into its own namespace (see _exec_parts there), so
# every name below is a thesis_store attribute and all fragments share one set
# of globals. The TYPE_CHECKING block only declares, for linters and readers,
# which names this fragment uses from the shared namespace; it never runs.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import math
    from pathlib import Path

    import thesis_store

    _ATTACH_FUTURES_ALLOWED = thesis_store._ATTACH_FUTURES_ALLOWED
    _TERMINAL_STATUSES = thesis_store._TERMINAL_STATUSES
    _coerce_dt = thesis_store._coerce_dt
    _load_index = thesis_store._load_index
    _load_thesis = thesis_store._load_thesis
    _load_untrusted_json = thesis_store._load_untrusted_json
    _now_iso = thesis_store._now_iso
    _parse_dt = thesis_store._parse_dt
    _save_index = thesis_store._save_index
    _save_thesis = thesis_store._save_thesis
    _sign = thesis_store._sign
    _sum_realized = thesis_store._sum_realized
    _update_index_entry = thesis_store._update_index_entry
    _valid_finite_positive = thesis_store._valid_finite_positive
    _valid_nonneg_int = thesis_store._valid_nonneg_int
    _valid_positive_int = thesis_store._valid_positive_int
    _validate_expected_price_match = thesis_store._validate_expected_price_match
    logger = thesis_store.logger


def attach_futures_position(
    state_dir: Path,
    thesis_id: str,
    position_report_path: str,
    expected_entry: float | None = None,
    expected_stop: float | None = None,
) -> dict:
    """Attach a futures-position-sizer SIZED report to an existing thesis.

    Futures analog of attach_position() (D6/D2) — deliberately NOT shared
    code: the report shape and validated fields are entirely different
    (no "mode" field; "direction" / "contracts" / "contract_spec.multiplier"
    instead of "final_recommended_shares"). Loads the report through the
    same hardened three-class loader vocabulary as contrarian-setup-gate /
    futures_sizing.py (unreadable / parse_error / non_finite — reused
    verbatim, no new tags).

    Validates:
      1. sizing_status == "SIZED" (rejects NO_TRADE and, incidentally, an
         equity position-sizer report, which has no sizing_status field).
      2. direction in {LONG, SHORT}.
      3. contracts is a positive whole number (P1-4: no fractional
         contracts).
      4. contract_spec.multiplier is a finite, non-bool, strictly-positive
         number.
      5. contract_spec.currency is present, a non-empty string, and equal
         to "USD" — no fallback to any other field (P1-2 / P1-addendum-3:
         this skill has no FX conversion — a non-USD contract's P&L would
         silently be computed in the WRONG currency's magnitude; fail
         closed instead).
      6. If expected_entry/expected_stop given, must match the report's
         top-level entry/stop (same 0.01 tolerance as attach_position()).
      7. _ATTACH_FUTURES_ALLOWED status guard — IDEA/ENTRY_READY ONLY
         (P1-1: stricter than equity's _ATTACH_ALLOWED, which also allows
         ACTIVE). Re-attaching on ACTIVE would silently overwrite the
         entire position dict incl. `direction` of an already-open
         futures position — a sign-flip that corrupts every subsequent
         P&L computation with no error raised. See
         _ATTACH_FUTURES_ALLOWED's module-level docstring.
      8. Cross-attach guard (P1 addendum, user re-review): rejects a
         thesis that already has an EQUITY position attached (same root
         cause and symmetric fix as attach_position()'s cross-attach
         guard above — IDEA/ENTRY_READY are in both status allow-sets, so
         the status guard alone can't stop an equity position from being
         silently overwritten by a futures one, dropping shares/
         shares_remaining/position_value/risk_dollars with no error).

    Raises:
        ValueError: If validation fails.
        FileNotFoundError: If the report path itself does not exist.
    """
    report_path = Path(position_report_path)
    if not report_path.exists():
        raise FileNotFoundError(f"Position report not found: {position_report_path}")

    data, load_error = _load_untrusted_json(str(report_path))
    if load_error is not None:
        raise ValueError(f"Futures position report {load_error}: {position_report_path}")
    if not isinstance(data, dict):
        raise ValueError(f"Futures position report is not a JSON object: {position_report_path}")
    report = data

    sizing_status = report.get("sizing_status")
    if sizing_status != "SIZED":
        raise ValueError(
            f"Futures position report sizing_status is {sizing_status!r}, expected 'SIZED' "
            f"(no_trade_reason={report.get('no_trade_reason')!r})"
        )

    direction = report.get("direction")
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"Futures position report has invalid direction: {direction!r}")

    contracts = _valid_positive_int(report.get("contracts"))
    if contracts is None:
        raise ValueError(
            f"Futures position report has invalid contracts: {report.get('contracts')!r} "
            "(must be a positive whole number of contracts)"
        )

    contract_spec = report.get("contract_spec")
    if not isinstance(contract_spec, dict):
        raise ValueError("Futures position report is missing contract_spec")
    multiplier = _valid_finite_positive(contract_spec.get("multiplier"))
    if multiplier is None:
        raise ValueError(
            f"Futures position report has invalid contract_spec.multiplier: "
            f"{contract_spec.get('multiplier')!r} (must be a finite positive number)"
        )

    # P1-2 / P1-addendum-3 (user independent review, money-critical): this
    # skill has no FX conversion anywhere in the futures P&L path
    # (_finalize_futures_outcome computes (exit-entry)*multiplier*qty*sign
    # with no fx_rate term). A non-USD contract (e.g. FESX/EUR) would
    # silently produce a P&L figure in the wrong currency's magnitude —
    # fail closed instead of computing a plausible-looking but wrong
    # dollar amount. contract_spec.currency is the SOLE source of truth —
    # NO fallback to a top-level report.currency (a prior revision of this
    # check had one; a user re-review correctly flagged it as a second,
    # unnecessary trust boundary that could be used to smuggle a currency
    # claim past the authoritative contract_spec). Missing, empty,
    # non-string, and non-"USD" values are ALL rejected explicitly (not
    # just "!= 'USD'"), so a falsy-but-truthy-looking edge case can't slip
    # through by accident.
    report_currency = contract_spec.get("currency")
    if not isinstance(report_currency, str) or not report_currency:
        raise ValueError(
            "Futures position report is missing contract_spec.currency (must be 'USD')"
        )
    if report_currency != "USD":
        raise ValueError(
            f"non-USD futures not supported (currency={report_currency!r}): P&L "
            "would not be FX-converted; only USD-denominated contracts are accepted"
        )

    # Validate expected entry/stop against the report (P1-C, user
    # re-review: _validate_expected_price_match() closes the fail-open
    # holes the previous inline check had — see its docstring). Runs
    # before _load_thesis(), so a rejection never touches thesis state.
    _validate_expected_price_match("entry", expected_entry, report.get("entry"))
    _validate_expected_price_match("stop", expected_stop, report.get("stop"))

    thesis = _load_thesis(state_dir, thesis_id)

    # Cross-attach guard (P1 addendum, user re-review, money-critical) —
    # symmetric with attach_position()'s guard above. IDEA/ENTRY_READY are
    # in both _ATTACH_ALLOWED and _ATTACH_FUTURES_ALLOWED, so without
    # this, attach_futures_position() could silently overwrite an
    # already-attached EQUITY position (dropping shares/shares_remaining/
    # position_value/risk_dollars with no error, and no way to recover
    # the sizing data). Checked directly on position.shares rather than
    # via _is_futures(), which only recognizes the futures shape — an
    # equity position never sets asset_type/quantity_unit at all, so
    # _is_futures() would return False for it either way.
    existing_position = thesis.get("position") or {}
    if existing_position.get("shares") is not None:
        raise ValueError(
            "attach_futures_position() cannot attach a futures position to a "
            "thesis that already has an equity position — use attach_position() "
            "instead, or register a fresh thesis"
        )

    # _ATTACH_FUTURES_ALLOWED status guard — IDEA/ENTRY_READY ONLY (P1-1,
    # deliberately stricter than equity's _ATTACH_ALLOWED which also
    # permits ACTIVE): see _ATTACH_FUTURES_ALLOWED's module-level
    # docstring for the sign-flip risk this closes.
    if thesis["status"] not in _ATTACH_FUTURES_ALLOWED:
        raise ValueError(
            f"attach_futures_position() not allowed for status {thesis['status']}; "
            f"only {sorted(_ATTACH_FUTURES_ALLOWED)} (ACTIVE would silently overwrite "
            "the position incl. direction — sign-flip risk)"
        )

    thesis["position"] = {
        "asset_type": "futures",
        "quantity": contracts,
        "quantity_remaining": contracts,
        "quantity_unit": "contracts",
        "multiplier": multiplier,
        "contract_symbol": report.get("symbol"),
        "direction": direction,
        "contract_spec": dict(contract_spec),
        "risk_per_contract_usd": report.get("risk_per_contract_usd"),
        "total_risk_usd": report.get("total_risk_usd"),
        "risk_pct_of_account": report.get("risk_pct_of_account"),
        "raw_source": {
            "skill": "futures-position-sizer",
            "file": str(position_report_path),
            "fields": {
                "contracts": contracts,
                "total_risk_usd": report.get("total_risk_usd"),
                "risk_per_contract_usd": report.get("risk_per_contract_usd"),
            },
        },
    }
    thesis["updated_at"] = _now_iso()

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Attached futures position to %s: %s %s contracts (%s, mult=%s)",
        thesis_id,
        contracts,
        thesis["position"]["contract_symbol"],
        direction,
        multiplier,
    )
    return thesis


def _finalize_futures_outcome(
    thesis: dict,
    *,
    exit_price: float,
    exit_date: str,
    history_at: str,
    status: str,
    reason: str,
    append_entry: bool,
) -> None:
    """Futures analog of _finalize_outcome() — deliberately NOT shared code
    (D2/D4 non-negotiable, see _is_futures docstring): the multiplier and
    direction sign must never leak into the equity per-unit path, and the
    equity per-unit path must never be reachable from a futures thesis.

    realized_pnl = round((exit_price - entry_price) * multiplier * qty * sign, 2)
    sign: LONG=+1, SHORT=-1 (see _sign()).

    Precondition: thesis["position"] has quantity/multiplier/direction set
    (attach_futures_position() or a direct open_position(contracts=...)
    always sets all three together).

    Output-side finiteness (P1 addendum, user re-review, teaching 10b —
    guard the OUTPUT, not just the input): every value computed here
    (realized_pnl, proceeds, cumulative pnl_dollars, pnl_pct) is computed
    into a LOCAL variable and validated with math.isfinite() BEFORE any
    mutation of thesis/position/status_history. The checks are two-layered:
    arithmetic and math.isfinite() both live inside try/except OverflowError
    for disk-corrupted huge ints, while the explicit finiteness branch still
    rejects ordinary float inf/nan results.
    """
    entry_price = thesis["entry"].get("actual_price")
    entry_date = thesis["entry"].get("actual_date")
    position = thesis["position"]
    original = position["quantity"]
    remaining = position.get("quantity_remaining", original)
    multiplier = position["multiplier"]
    sign = _sign(position["direction"])

    new_entry = None
    if append_entry:
        try:
            leg_proceeds = round(exit_price * multiplier * remaining, 2)
            leg_realized = round((exit_price - entry_price) * multiplier * remaining * sign, 2)
            leg_finite = math.isfinite(leg_proceeds) and math.isfinite(leg_realized)
        except OverflowError as exc:
            raise ValueError(
                "computed proceeds/realized_pnl overflowed (exit_price="
                f"{exit_price}, multiplier={multiplier}, quantity={remaining}) — "
                "operands too large"
            ) from exc
        if not leg_finite:
            raise ValueError(
                "computed proceeds/realized_pnl is not finite (exit_price="
                f"{exit_price}, multiplier={multiplier}, quantity={remaining}) — "
                "operands are individually finite but their product overflowed"
            )
        new_entry = {
            "status": status,
            "at": history_at,
            "reason": reason,
            "quantity_sold": remaining,
            "price": exit_price,
            "proceeds": leg_proceeds,
            "realized_pnl": leg_realized,
        }

    # Cumulative pnl_dollars/pct computed WITHOUT mutating status_history
    # yet — _sum_realized() runs over the existing ledger plus the
    # not-yet-appended new_entry, so a non-finite cumulative result still
    # rejects cleanly before any state changes.
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
        raise ValueError(
            f"computed cumulative pnl_dollars is not finite ({pnl_dollars}) — "
            "the position's realized P&L ledger overflowed"
        )

    pnl_pct = None
    if entry_price and original:
        # % basis: notional value (entry * multiplier * original contracts),
        # the direct futures analog of equity's entry*shares denominator —
        # a descriptive metric only; pnl_dollars above is the money-critical
        # exact figure and is never derived from this percentage.
        try:
            pnl_pct = round(pnl_dollars / (entry_price * multiplier * original) * 100, 2)
            pnl_pct_finite = math.isfinite(pnl_pct)
        except OverflowError as exc:
            raise ValueError(
                "computed pnl_pct overflowed — the notional denominator "
                "(entry * multiplier * quantity) contains an operand too large"
            ) from exc
        if not pnl_pct_finite:
            raise ValueError(
                f"computed pnl_pct is not finite ({pnl_pct}) — the notional "
                "denominator (entry * multiplier * quantity) overflowed"
            )

    holding_days = None
    if entry_date:
        try:
            holding_days = (_parse_dt(exit_date) - _parse_dt(entry_date)).days
        except (ValueError, TypeError):
            pass

    # All computed values validated finite — now, and only now, mutate.
    if new_entry is not None:
        thesis["status_history"].append(new_entry)
    position["quantity_remaining"] = 0
    thesis["status"] = status
    thesis["outcome"]["pnl_dollars"] = pnl_dollars
    thesis["outcome"]["pnl_pct"] = pnl_pct
    thesis["outcome"]["holding_days"] = holding_days


def _close_futures(
    state_dir: Path,
    thesis: dict,
    exit_reason: str,
    actual_price: float,
    actual_date: str,
    event_date: str | None,
) -> dict:
    """Futures analog of close() — deliberately NOT shared code (D2/D4
    non-negotiable, see _is_futures docstring): a futures thesis must
    never reach close()'s legacy no-position per-unit branch, which
    ignores multiplier/direction and would silently compute a
    plausible-looking but wrong dollar amount.

    Unlike close(), there is no no-position fallback here — a thesis that
    dispatches into this function (_is_futures() is True) always has an
    attached futures position with a quantity.
    """
    if thesis["status"] not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only close ACTIVE or PARTIALLY_CLOSED thesis, current status: {thesis['status']}"
        )

    # P1-3 (user independent review, money-critical): validated before any
    # mutation, before _save_thesis() — a NaN/Infinity exit price would
    # otherwise persist into outcome.pnl_dollars.
    if _valid_finite_positive(actual_price) is None:
        raise ValueError(
            "close() requires a finite positive actual_price for a futures "
            f"thesis, got {actual_price!r}"
        )

    entry_price = thesis["entry"].get("actual_price")
    if entry_price is None:
        raise ValueError("Cannot close thesis: entry.actual_price is not set")

    position = thesis.get("position")
    if not position or position.get("quantity") is None:
        raise ValueError("Cannot close futures thesis: position.quantity is not set")

    thesis["exit"]["actual_price"] = actual_price
    thesis["exit"]["actual_date"] = actual_date
    thesis["exit"]["exit_reason"] = exit_reason

    now = _now_iso()
    history_at = event_date or now

    _finalize_futures_outcome(
        thesis,
        exit_price=actual_price,
        exit_date=actual_date,
        history_at=history_at,
        status="CLOSED",
        reason=f"closed: {exit_reason}",
        append_entry=True,
    )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Closed %s: %s, P&L=%.2f",
        thesis["thesis_id"],
        exit_reason,
        thesis["outcome"].get("pnl_dollars") or 0,
    )
    return thesis


def _trim_futures(
    state_dir: Path,
    thesis: dict,
    contracts_sold: float,
    price: float,
    date: str,
    reason: str,
    exit_reason: str | None,
    event_date: str | None,
) -> dict:
    """Futures analog of trim() — deliberately NOT shared code (D2/D4
    non-negotiable, see _is_futures docstring): realized_pnl here always
    includes multiplier * sign, unlike the equity per-unit formula above.
    """
    status = thesis["status"]
    if status not in ("ACTIVE", "PARTIALLY_CLOSED"):
        raise ValueError(
            f"Can only trim ACTIVE or PARTIALLY_CLOSED thesis, current status: {status}"
        )

    # P1-3 (user independent review, money-critical): validated before any
    # mutation, before _save_thesis().
    if _valid_finite_positive(price) is None:
        raise ValueError(
            f"trim() requires a finite positive price for a futures thesis, got {price!r}"
        )

    entry_price = thesis["entry"].get("actual_price")
    if entry_price is None:
        raise ValueError("Cannot trim thesis: entry.actual_price is not set")

    position = thesis.get("position")
    if not position or position.get("quantity") is None:
        raise ValueError(
            "trim requires a recorded futures position — run "
            "open-position --contracts or attach-futures-position first"
        )

    original = position["quantity"]
    remaining = position.get("quantity_remaining", original)
    # P1-4: contracts_sold must be a whole number (no fractional contracts).
    valid_contracts_sold = _valid_positive_int(contracts_sold)
    if valid_contracts_sold is None:
        raise ValueError(
            f"contracts_sold must be a positive whole number of contracts, got {contracts_sold!r}"
        )
    if not (0 < valid_contracts_sold <= remaining):
        raise ValueError(
            f"contracts_sold ({valid_contracts_sold}) must be > 0 and <= "
            f"quantity_remaining ({remaining})"
        )

    multiplier = position["multiplier"]
    sign = _sign(position["direction"])
    # P1 addendum-1 (user re-review, teaching 10b — guard the OUTPUT, not
    # just the input): individually-finite operands (e.g. multiplier=1e308)
    # can still overflow their PRODUCT to inf, while a disk-corrupted huge
    # int can raise OverflowError before math.isfinite() is reached. Both
    # cases are validated before any mutation below.
    try:
        realized = round((price - entry_price) * multiplier * valid_contracts_sold * sign, 2)
        proceeds = round(price * multiplier * valid_contracts_sold, 2)
        trim_finite = math.isfinite(realized) and math.isfinite(proceeds)
    except OverflowError as exc:
        raise ValueError(
            "computed realized_pnl/proceeds overflowed (price="
            f"{price}, multiplier={multiplier}, contracts_sold={valid_contracts_sold}) — "
            "operands too large"
        ) from exc
    if not trim_finite:
        raise ValueError(
            "computed realized_pnl/proceeds is not finite (price="
            f"{price}, multiplier={multiplier}, contracts_sold={valid_contracts_sold}) — "
            "operands are individually finite but their product overflowed"
        )
    # Round to kill float-subtraction noise, then epsilon-snap a ~0
    # remainder to an exact 0 (→ full close-out) — same as equity trim().
    # (Both operands are exact ints post-P1-4, so this is now a no-op
    # safety net rather than a load-bearing rounding step, but kept for
    # symmetry with equity trim() and defense-in-depth.)
    new_remaining = round(remaining - valid_contracts_sold, 8)
    if abs(new_remaining) < 1e-9:
        new_remaining = 0
    # P1 addendum-4 (canonical int storage): quantity_remaining must never
    # be a float like 2.0 — validated + coerced to int here even though,
    # with whole-number contracts throughout, this should always already
    # be an exact integer.
    valid_new_remaining = _valid_nonneg_int(new_remaining)
    if valid_new_remaining is None:
        raise ValueError(
            f"computed quantity_remaining is not a valid non-negative integer "
            f"({new_remaining!r}) — this should be unreachable with whole-number "
            "contracts"
        )
    new_remaining = valid_new_remaining

    now = _now_iso()
    history_at = _coerce_dt(event_date) or _coerce_dt(date)
    full_close = new_remaining == 0
    new_status = "CLOSED" if full_close else "PARTIALLY_CLOSED"

    # _trim_futures() owns its ledger append (exactly one entry per trim).
    thesis["status_history"].append(
        {
            "status": new_status,
            "at": history_at,
            "reason": reason,
            "quantity_sold": valid_contracts_sold,
            "price": price,
            "proceeds": proceeds,
            "realized_pnl": realized,
        }
    )
    position["quantity_remaining"] = new_remaining

    if full_close:
        exit_date = _coerce_dt(date)
        thesis["exit"]["actual_price"] = price
        thesis["exit"]["actual_date"] = exit_date
        thesis["exit"]["exit_reason"] = exit_reason or "manual"
        thesis["status"] = "CLOSED"
        # Ledger entry already appended above → append_entry=False (sum only).
        _finalize_futures_outcome(
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
        "Trimmed %s: sold %s contracts @ %.4f → %s remaining, status %s",
        thesis["thesis_id"],
        valid_contracts_sold,
        price,
        new_remaining,
        thesis["status"],
    )
    return thesis


def _open_futures_position(
    state_dir: Path,
    thesis: dict,
    actual_price: float,
    actual_date: str,
    *,
    reason: str,
    contracts: float | None,
    multiplier: float | None,
    direction: str | None,
    contract_symbol: str | None,
    contract_currency: str | None,
    event_date: str | None,
) -> dict:
    """Futures analog of open_position()'s equity shares= branch —
    deliberately NOT shared code (D2/D4 non-negotiable, see _is_futures
    docstring). Two entry paths:

      1. attach_futures_position() already populated position (asset_type,
         quantity, multiplier, direction, contract_spec incl. currency,
         ...) — `contracts` here is None and this only transitions status
         + sets entry data. Currency was already validated as "USD" by
         attach_futures_position() itself.
      2. Direct open (no prior attach): `contracts`/`multiplier`/`direction`/
         `contract_currency` are supplied here and this populates position
         from scratch (P2-3c: `open-position --contracts` without
         attach-futures-position first). Unlike path 1, there is no
         contract_spec at all here, so currency must be validated
         explicitly (P1-addendum-2, user re-review) — a direct open with
         no contract_currency, or a non-USD one, is a fail-closed reject,
         not a silent USD assumption.
    """
    if thesis["status"] != "ENTRY_READY":
        raise ValueError(f"open_position() requires ENTRY_READY status, got {thesis['status']}")

    # P1-3 (user independent review, money-critical): validated BEFORE any
    # mutation of `pos`/`thesis` below, so a rejected call leaves the
    # in-memory thesis untouched and _save_thesis() is never reached — a
    # NaN/Infinity actual_price would otherwise persist into entry data and
    # NaN-poison every downstream P&L computation for this thesis.
    if _valid_finite_positive(actual_price) is None:
        raise ValueError(
            "open_position() requires a finite positive actual_price for a "
            f"futures thesis, got {actual_price!r}"
        )

    pos = dict(thesis.get("position") or {})

    if contracts is not None:
        if multiplier is None or direction is None:
            raise ValueError(
                "open_position(contracts=...) requires multiplier and direction "
                "when no futures position is already attached"
            )
        # P1-addendum-2 (user re-review): a direct open has no attached
        # contract_spec, so currency must be supplied and validated here —
        # never silently assumed to be USD. Same rejection rules as
        # attach_futures_position(): missing/empty/non-string/non-USD are
        # ALL rejected explicitly.
        if not isinstance(contract_currency, str) or not contract_currency:
            raise ValueError(
                "open_position(contracts=...) requires contract_currency "
                "when no futures position is already attached (must be 'USD')"
            )
        if contract_currency != "USD":
            raise ValueError(
                f"non-USD futures not supported (currency={contract_currency!r}): "
                "P&L would not be FX-converted; only USD-denominated contracts "
                "are accepted"
            )
        # Symmetric with attach_futures_position()'s handoff validation
        # (P2/P1-4): bool-exclude -> isfinite -> integral -> range, with a
        # futures-specific error message rather than relying on the
        # generic schema failure surfaced later at _save_thesis() time.
        # Contracts must be a whole number (P1-4) — no fractional
        # contracts.
        valid_contracts = _valid_positive_int(contracts)
        if valid_contracts is None:
            raise ValueError(
                "open_position(contracts=...) requires a positive whole "
                f"number of contracts, got {contracts!r}"
            )
        valid_multiplier = _valid_finite_positive(multiplier)
        if valid_multiplier is None:
            raise ValueError(
                "open_position(contracts=...) requires a finite positive "
                f"multiplier, got {multiplier!r}"
            )
        _sign(direction)  # raises ValueError for anything other than LONG/SHORT
        pos["asset_type"] = "futures"
        pos["quantity_unit"] = "contracts"
        pos["quantity"] = valid_contracts
        pos["multiplier"] = valid_multiplier
        pos["direction"] = direction
        # Stored in contract_spec.currency for audit consistency with the
        # attach path (contract_spec.currency is the single field any
        # future code checks for currency — see attach_futures_position()).
        spec = dict(pos.get("contract_spec") or {})
        spec["currency"] = contract_currency
        pos["contract_spec"] = spec
        if contract_symbol is not None:
            pos["contract_symbol"] = contract_symbol

    if pos.get("quantity") is None:
        raise ValueError(
            "open_position() for a futures thesis requires position.quantity — "
            "attach a SIZED report via attach-futures-position, or pass contracts="
        )

    pos["quantity_remaining"] = pos["quantity"]
    thesis["position"] = pos

    now = _now_iso()
    thesis["entry"]["actual_price"] = actual_price
    thesis["entry"]["actual_date"] = actual_date

    history_at = event_date or now
    thesis["status"] = "ACTIVE"
    thesis["status_history"].append({"status": "ACTIVE", "at": history_at, "reason": reason})
    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info(
        "Opened futures position %s at %.2f (%s contracts)",
        thesis["thesis_id"],
        actual_price,
        pos["quantity"],
    )
    return thesis


def _terminate_futures(
    state_dir: Path,
    thesis: dict,
    exit_reason: str,
    actual_price: float | None,
    actual_date: str | None,
    event_date: str | None,
) -> dict:
    """Futures analog of terminate()'s INVALIDATED branch — deliberately
    NOT shared code (D2/D4 non-negotiable, see _is_futures docstring):
    must never reach the legacy per-unit no-position INVALIDATED branch
    above, which ignores multiplier/direction entirely.

    Unlike the equity legacy branch, when a full P&L cannot be computed
    (missing price/quantity) this NEVER falls back to a partial per-unit
    calculation — it simply records the INVALIDATED transition with no
    P&L, avoiding any multiplier-ignorant dollar figure.
    """
    if thesis["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"Cannot terminate: already in terminal status {thesis['status']}")

    # P1-3 (user independent review, money-critical): actual_price is
    # OPTIONAL for INVALIDATED (unlike close()'s required actual_price),
    # so only validate when given — but validated before any mutation,
    # before _save_thesis().
    if actual_price is not None and _valid_finite_positive(actual_price) is None:
        raise ValueError(
            "terminate() requires a finite positive actual_price for a futures "
            f"thesis when provided, got {actual_price!r}"
        )

    now = _now_iso()

    if actual_price is not None:
        thesis["exit"]["actual_price"] = actual_price
    if actual_date is not None:
        thesis["exit"]["actual_date"] = actual_date
    thesis["exit"]["exit_reason"] = "invalidated"

    entry_price = thesis["entry"].get("actual_price")
    history_at = event_date or now
    position = thesis.get("position")

    if (
        position
        and position.get("quantity")
        and actual_price is not None
        and actual_date is not None
        and entry_price
    ):
        _finalize_futures_outcome(
            thesis,
            exit_price=actual_price,
            exit_date=actual_date,
            history_at=history_at,
            status="INVALIDATED",
            reason=f"invalidated: {exit_reason}",
            append_entry=True,
        )
    else:
        # No P&L computed — plain INVALIDATED transition (see docstring:
        # never a multiplier-ignorant partial calculation).
        thesis["status"] = "INVALIDATED"
        thesis["status_history"].append(
            {
                "status": "INVALIDATED",
                "at": history_at,
                "reason": f"invalidated: {exit_reason}",
            }
        )

    thesis["updated_at"] = now

    _save_thesis(state_dir, thesis)

    index = _load_index(state_dir)
    _update_index_entry(index, thesis)
    _save_index(state_dir, index)

    logger.info("Terminated %s → INVALIDATED: %s", thesis["thesis_id"], exit_reason)
    return thesis
