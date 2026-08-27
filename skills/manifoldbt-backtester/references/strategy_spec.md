# Strategy Spec Reference

A spec is a JSON object. `scripts/spec.py` validates it before any data loads,
so a mistake costs a second instead of a long read.

## Fields

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `name` | string | required | Strategy label, carried into the result |
| `indicators` | object | required | Named indicators, at least one |
| `entry` | object | required | One condition; the position is held while it holds |
| `size` | number | `1.0` | Fraction of equity when in position, in `(0, 1]` |
| `stop_loss_pct` | number | none | Stop distance in percent from entry |
| `take_profit_pct` | number | none | Target distance in percent from entry |
| `fees_bps` | number | `0.0` | Fee in basis points, charged both sides |
| `slippage_bps` | number | `0.0` | Fixed slippage in basis points |
| `signal_delay` | integer | `1` | Bars between signal and fill |

## Indicators

```json
"indicators": {
  "fast": { "type": "sma", "period": 20 },
  "rsi14": { "type": "rsi", "period": 14, "source": "close" }
}
```

`type` is `sma`, `ema` or `rsi`. `period` is a positive integer. `source` is
`open`, `high`, `low` or `close`, defaulting to `close`.

Each name becomes a signal you can reference in `entry`.

## Entry condition

```json
"entry": { "left": "fast", "op": ">", "right": "slow" }
```

`op` is `>`, `<`, `>=` or `<=`. Each side is an indicator name, a price column,
or a number:

```json
"entry": { "left": "rsi14", "op": "<", "right": 30 }
"entry": { "left": "close", "op": ">", "right": "slow" }
```

The strategy holds `size` while the condition is true and goes flat when it
turns false. A crossing is the condition becoming true, so a moving-average
crossover is written as the comparison, not as a separate crossing operator.

## Why `signal_delay` defaults to 1

At 0 the strategy fills on the bar that produced the signal. Unless the fill
price is knowable at signal time, that is look-ahead, and it inflates results in
a way no later stress test recovers. `backtest-expert` lists it among its red
flags. Setting it to 0 is allowed and reported as a warning.

## Parameter count

`count_parameters` counts what the robustness dimension penalises:

- one per indicator `period`
- one per numeric threshold used in `entry`
- one when `size` is explicitly supplied
- one per bracket distance set

Fees, slippage and `signal_delay` are excluded. They are costs and conventions,
not knobs you tune until the equity curve improves.

A spec with more than four parameters triggers a warning before it runs.

## What validation refuses

| Refused | Reason |
|---------|--------|
| Unknown `type` | The three supported kinds are named in the error |
| `period` of 0, negative, or `True` | `True` is an `int` in Python and would build a period of one |
| `entry` naming an undeclared indicator | The error lists what is declared |
| `size` outside `(0, 1]` | Sizing above equity needs leverage the spec does not model |
| Negative `fees_bps` or `slippage_bps` | A negative cost is a rebate the engine does not model |
| Empty `indicators` | A condition needs something to compare |

## Full example

```json
{
  "name": "rsi_oversold_costed",
  "indicators": {
    "rsi14": { "type": "rsi", "period": 14 }
  },
  "entry": { "left": "rsi14", "op": "<", "right": 30 },
  "size": 0.5,
  "stop_loss_pct": 2.0,
  "take_profit_pct": 4.0,
  "fees_bps": 5.0,
  "slippage_bps": 2.0,
  "signal_delay": 1
}
```

Five parameters: the RSI period, the threshold of 30, the explicit position
size, the stop and the target.
