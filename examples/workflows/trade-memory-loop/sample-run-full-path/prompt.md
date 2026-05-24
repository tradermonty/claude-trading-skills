# Prompt — `trade-memory-loop` (full-path)

Paste the following to Claude (with the `trader-memory-core`,
`signal-postmortem`, and `backtest-expert` skills available). Replace
`<repo>` with your checkout path and `$PROJECT_DIR` with your thesis state
directory.

---

> I just closed a position. Run the **trade-memory-loop** workflow end-to-end
> (include the optional backtest-expert re-validation step).
>
> 1. Use **trader-memory-core** to record the closed trade outcome: update the
>    thesis to `CLOSED` with the exit price/date, realized P&L, MAE/MFE, and
>    final status history. State dir: `$PROJECT_DIR/state/theses/`.
> 2. Use **signal-postmortem** to consume the closed thesis and classify the
>    outcome (TRUE_POSITIVE / FALSE_POSITIVE / REGIME_MISMATCH / NEUTRAL),
>    with the root-cause read: was it thesis quality, execution, market
>    environment, or randomness?
> 3. Use **backtest-expert** to re-validate the lesson candidate
>    (e.g. "trail under rising 10-EMA after 2R for VCP / RISK_ON setups")
>    against a historical sample. Report verdict and any refinement.
> 4. Use **trader-memory-core** again to append the lessons — including the
>    backtest result — to my journal.
>
> Be honest about whether the win was thesis-driven or luck. Don't rationalize
> randomness as skill.

Trade details for this sample run: ticker **EXMPL**, LONG, entered
2026-01-08 @ 142.10 (70 sh, 1% risk, stop 134.50), exited 2026-02-27 @
168.40 (`target_hit`), origin `vcp-screener` grade A.

---

## What to expect

This is the **full-path** sample. Steps 1, 2, and 4 are identical to the
required-only sample (the same closed thesis and postmortem classification);
the new content is **step 3 backtest-expert** re-validation of the
"trail-under-10-EMA-after-2R" rule on an 87-setup illustrative sample. The
backtest verdict (**VALIDATED_WITH_CAVEAT**: +4.4 pp avg return vs the
fixed-2R baseline, at the cost of ~16 extra holding days and 18% premature
trail exits) feeds the step-4 journal entry as a statistical cross-check
alongside the qualitative postmortem.

> ⚠️ Illustrative sample — fictional ticker `EXMPL` and fictional historical
> backtest universe, **not investment advice**.
