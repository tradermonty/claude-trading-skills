# Intraday Trigger Playbook

> **Status**: this reference describes the trigger semantics that
> Phase 3 (`monitor_intraday_trigger.py`, deferred to v0.5) will
> evaluate. The Phase 2 plans (`generate_pre_market_plan.py`) emit
> `entry_hint` / `stop_hint` strings that map to these triggers.

## 5-min Opening Range Low (ORL) break

```
plan_id template:   <TICKER>-<YYYYMMDD>-ORL5
trigger_type:       orl_5min_break
condition (ja):     5min ORL を出来高 1.2x 以上で下抜け
entry_hint:         5min_orl_low - 0.05
stop_hint:          session_HOD + 0.25 * ATR
structural_targets: dma_10, dma_20
```

**Phase 3 evaluator**:

1. Wait for the first 5-minute bar to close. Mark its high (ORH) and
   low (ORL).
2. After 9:35 ET, watch every 5-minute close. If a bar closes below
   ORL AND its volume ≥ 1.2× the ORL bar's volume, fire the trigger.
3. Stop is `session_HOD + stop_buffer_atr * ATR(14)`.
4. Invalidates if a subsequent 5-minute close prints back above ORL
   AND VWAP (sign of failed breakdown).

## First Red 5-minute candle

```
plan_id template:   <TICKER>-<YYYYMMDD>-FR5
trigger_type:       first_red_5min
condition (ja):     寄付後最初の赤 5min の安値割れ
entry_hint:         first_red_5min_low - 0.05
stop_hint:          first_red_5min_high
```

**Phase 3 evaluator**:

1. Track every 5-minute bar from 9:30 ET. Mark the first bar where
   `close < open` (a red candle).
2. After that bar closes, fire the trigger when a later 5-minute bar
   prints below the red candle's low.
3. Stop is the red candle's high.
4. Invalidates if any subsequent 5-minute bar takes out the red
   candle's high before the trigger fires.

## VWAP fail

```
plan_id template:   <TICKER>-<YYYYMMDD>-VWF
trigger_type:       vwap_fail
condition (ja):     First crack 後 VWAP retest で 5min 終値拒否 + lower-high 下抜け
entry_hint:         lower_high_low - 0.05
stop_hint:          vwap_reclaim_5min_close
```

**Phase 3 evaluator** (FSM):

State machine has six states:
`armed → first_crack_seen → vwap_retest_seen → rejection_confirmed → triggered → invalidated`

1. `armed`: market open, watching for first VWAP loss.
2. `first_crack_seen`: 5-minute close prints below VWAP for the first
   time, AND price comes from session HOD (filters open-print VWAP
   noise).
3. `vwap_retest_seen`: subsequent bar closes back at or above VWAP
   (the "retest").
4. `rejection_confirmed`: next 5-minute bar prints a lower high than
   the retest bar AND closes back below VWAP.
5. `triggered`: fire on the break of the rejection bar's low.
6. `invalidated`: any 5-minute close back above VWAP after `triggered`
   OR a clean uptrend line break before `triggered`.

## Common evaluator concerns

- **Time zone**: all timestamps `America/New_York`.
- **Halt handling**: bars during halt are skipped; the FSM resumes
  from its last state when trading resumes.
- **Bar close vs touch**: triggers fire on bar close, not intra-bar.
  Reduces wick noise.
- **No re-entry**: once a plan is `triggered` or `invalidated`, the
  FSM does not re-arm for the day.
