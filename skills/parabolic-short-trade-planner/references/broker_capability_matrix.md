# Broker Capability Matrix

What each broker exposes through its API for short inventory, and how
it maps onto this skill's `BrokerShortInventoryAdapter` contract.

| Field | Alpaca (paper + live) | Interactive Brokers | Manual |
|---|---|---|---|
| `shortable` | ✅ (`/v2/assets/{symbol}.shortable`) | ✅ via TWS API | n/a |
| `easy_to_borrow` | ✅ (`easy_to_borrow`) | ⚠️ inferred from rate sheet | n/a |
| `can_open_new_short` | shortable AND ETB | locate-dependent | always False (default-deny) |
| `borrow_fee_apr` | 0.0 for ETB; None for HTB | quoted per-symbol | None |
| `borrow_fee_manual_check_required` | True only for HTB | False (rate is quoted) | always True |
| `manual_locate_required` | always True (broker confirms) | False after locate succeeds | always True |
| New short on HTB? | ❌ rejected at submit | ✅ after locate | n/a |

## Why the contract sets `manual_locate_required` to True even for ETB

ETB names can lose ETB status mid-day if borrow demand spikes. Marking
the field always True keeps the human in the loop: the trader sees
`advisory_manual_reasons: [manual_locate_required]` on every plan and
re-checks at the broker before submitting. The flag is *advisory*, so
it does not gate `trade_allowed_without_manual` on its own.

## How to add another broker

1. Subclass `BrokerShortInventoryAdapter` in
   `scripts/adapters/<broker>_inventory_adapter.py`.
2. Implement `get_inventory_status(symbol) -> dict` returning the
   contract dict.
3. Raise `BrokerNotConfiguredError` if the broker's credentials are
   missing — `generate_pre_market_plan.py` falls back to
   `ManualBrokerAdapter` when this fires.
4. Add the broker name to the `--broker` CLI choices in
   `generate_pre_market_plan.py::build_arg_parser`.
5. Add an adapter test that mocks the broker's HTTP layer with
   `unittest.mock.patch`.

## Why no SDK dependency

Alpaca publishes `alpaca-py` but each broker SDK pulls in additional
transitive dependencies and increases the skill bundle size. This skill
talks HTTP via `requests` directly, the same pattern the existing
`portfolio-manager` skill uses for its account checks. Keeps the
.skill bundle deployable as-is.
