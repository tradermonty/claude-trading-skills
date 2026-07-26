# Prompt: required-only swing opportunity review

Run only the required steps of `swing-opportunity-daily` for `2026-06-29`.

1. Confirm `00_exposure_decision.json` is `NEW_ENTRY_ALLOWED`; otherwise stop.
2. Confirm the account circuit breaker allows new risk.
3. Use only the fictional VCP candidate and require a clean weekly-chart
   validation.
4. Calculate size from the fixed entry, stop, account, and risk inputs.
5. Register an `ENTRY_READY` thesis and run the manual execution discipline
   gate.
6. Skip optional steps 3, 4, 5, 6, and 9. Do not invent their artifacts.

Stop at the `GO`/`NO_GO` decision. A `GO` means the written fictional checklist
is internally consistent; it is not an instruction or authorization to place
an order. `EXMPL` and all values are fictional. This is not investment advice.
