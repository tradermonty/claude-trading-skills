# Short Invalidation Rules

Hard-rejects in `invalidation_rules.py`. These run before any scoring,
so they're cheap and binary. Soft signals (state caps / warnings) live
in `state_caps.py` instead.

## Rules (mode-aware)

| Rule | safe_largecap | classic_qm | Source |
|---|---|---|---|
| Earnings within N trading days | ≤ 2 days → reject | ≤ 2 days → reject | FMP earnings calendar |
| Market cap floor | < $2B → reject | < $300M → reject | FMP profile `mktCap` |
| 20-day average dollar volume | < $20M → reject | < $5M → reject | Computed from EOD bars |
| Latest close | < $5.00 → reject | < $5.00 → reject | EOD close |
| Days since IPO | < 60 trading days → reject | < 60 trading days → reject | FMP profile `days_listed_actual` |
| User CSV catalyst flag | flagged → reject | flagged → reject | Optional input |

## Why earnings within 2 days is hard-rejected

Earnings risk is binary and asymmetric. Even a deeply parabolic chart
can gap +30% on a beat-and-raise overnight, blowing through any stop.
The screener does not enable a "trade through earnings" override —
post-earnings setups belong to a different skill (earnings-trade-analyzer
or pead-screener).

## Why classic_qm tolerates smaller caps

Qullamaggie's archetypal Parabolic Short targets — small-cap meme
runners up 300-1000% in a few weeks — wouldn't pass `safe_largecap`.
Switching to `classic_qm` lowers the cap floor to $300M and the ADV
floor to $5M so those names enter the universe. The trade-off:
classic_qm names are far more likely to be `borrow_inventory_unavailable`
on Alpaca and end up `plan_status: watch_only`.

## What's NOT a hard reject

- Recent 52-week high — that's a state cap, not a kill.
- Strong closing print near session high — also a state cap.
- Premarket gap — turns into the "wait for first crack" advisory warning.

The reasoning: this is a Parabolic SHORT planner. Bullish-looking daily
patterns are the *target*. Filtering them out leaves no candidates.
