# Prompt — `market-regime-daily` (full-path)

Paste the following to Claude (Claude Code or the web app, with the
`market-breadth-analyzer`, `uptrend-analyzer`, `market-top-detector`, and
`exposure-coach` skills available). Replace `<repo>` with your checkout
path.

---

> Run the **market-regime-daily** workflow end-to-end (include the optional
> market-top-detector step today).
>
> 1. Use **market-breadth-analyzer** to score current market breadth from the
>    public TraderMonty CSV. Save the JSON + Markdown to
>    `<repo>/reports/`.
> 2. Use **uptrend-analyzer** to score uptrend participation from Monty's
>    public Uptrend Ratio Dashboard CSV. Save to `<repo>/reports/`.
> 3. Use **market-top-detector** to score top-formation risk. Save to
>    `<repo>/reports/`.
> 4. Hand the breadth, uptrend, and top-risk reports to **exposure-coach**
>    and produce a one-page market posture (exposure ceiling, bias,
>    participation, new-entry-allowed vs cash-priority).
>
> Then tell me: is new swing-trade risk **allowed**, **restricted**, or
> **cash-priority** today, and why. Treat the output as a posture, not a
> buy/sell signal.

---

## What to expect

This is the **full-path** sample. All three upstream skills are run and the
raw fixtures here mirror the **nested** JSON shape those skills actually
emit (`composite.composite_score`) — there is **no** top-level
`breadth_score` / `uptrend_score` / `top_risk_score` workflow hand-off
field. This deliberately exercises the nested-shape parser path in
`exposure-coach` that was fixed in
[PR #137](https://github.com/tradermonty/claude-trading-skills/pull/137)
(merged 2026-05-24).

With `top_risk` now contributing, the posture moves from the required-only
**REDUCE_ONLY / LOW** outcome to **NEW_ENTRY_ALLOWED / MEDIUM** at a 58%
exposure ceiling. See [`../README.md`](../README.md) for the comparison
table and the verification command.

> ⚠️ Illustrative sample — fictional market snapshot, **not investment
> advice**.
