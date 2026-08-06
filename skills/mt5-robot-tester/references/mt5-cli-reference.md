# MetaTrader 5 Command-Line Strategy Tester Reference

Use this reference to automate the MT5 Strategy Tester without its GUI and to
understand the keys and enums used by this skill. Verify details marked
**(verify)** against the installed MT5 build because exact report formats can
vary.

## Launch

```bat
terminal64.exe /config:C:\path\to\tester.ini
```

- `ShutdownTerminal=1` runs the test and closes the terminal automatically, so
  the process ends when the backtest finishes. The orchestrator waits with a
  timeout.
- `/portable` uses the data folder next to the executable instead of the folder
  under `%APPDATA%`.
- The terminal needs broker tick data downloaded for `Model=4` (real ticks), or
  the test will fail or use incomplete data.

## `[Tester]` Section

| Key | Value | Notes |
|-----|-------|-------|
| `Expert` | `candidate bots\MyBot.ex5` | Path **relative to `MQL5\Experts`**. |
| `ExpertParameters` | `MyBot.set` | Optional `.set` under `MQL5\Profiles\Tester\`. |
| `Symbol` | `US100.cash` | Symbol; `Optimization=3` iterates Market Watch. |
| `Period` | `H1` | Time frame. |
| `Model` | `4` | Modeling mode; see below. |
| `FromDate`/`ToDate` | `2020.01.01` | `YYYY.MM.DD` format. |
| `ForwardMode` | `0` | `0` disables forward testing. |
| `Deposit` | `10000` | Initial deposit. |
| `Currency` | `USD` | Deposit currency. |
| `Leverage` | `100` | Leverage ratio `1:N`. |
| `Optimization` | `0/1/2/3` | Optimization mode; see below. |
| `OptimizationCriterion` | `0..7` | Optimization criterion; see below. |
| `Report` | Relative name **without an extension** | Build 6061 writes the report into the data folder; the orchestrator collects it after the run. |
| `ReplaceReport` | `1` | Overwrite rerun reports. |
| `ShutdownTerminal` | `1` | Close the terminal after completion; required for batch runs. |
| `Visual` | `0` | Disable visual mode. |

### `Model`

| Value | Meaning |
|-------|---------|
| `0` | Every tick. |
| `1` | One-minute OHLC. |
| `2` | Open prices only. |
| `3` | Mathematical calculation. |
| **`4`** | **Every tick based on real ticks**; the default. |

### `Optimization`

| Value | Meaning |
|-------|---------|
| `0` | Disabled; single backtest. |
| `1` | Slow complete algorithm. |
| `2` | Fast genetic algorithm. |
| **`3`** | All Market Watch symbols. Round 1 does not use it because build 6061 leaves the XML empty. |

### `OptimizationCriterion`

| Value | Criterion |
|-------|-----------|
| **`0`** | **Maximum balance / maximum profitability**; used by this skill. |
| `1` | Balance multiplied by Profit Factor. |
| `2` | Balance multiplied by Expected Payoff. |
| `3` | Balance multiplied by minimum Drawdown. |
| `4` | Balance multiplied by Recovery Factor. |
| `5` | Balance multiplied by Sharpe Ratio. |
| `6` | Custom `OnTester` result. |
| `7` | Maximum complex criterion. |

## `[TesterInputs]` Section

Specify a fixed EA parameter as follows:

```ini
StopLossCoef1=1.0
```

Specify an optimization range with `value||start||step||stop||Y` syntax:

```ini
GannHiLoPeriod1=43||43||4||129||Y
```

- The final `Y` or `N` field enables or disables optimization for that
  parameter.
- In Round 3, this skill ranges **one parameter at a time** and fixes every
  other parameter at its current best value before continuing to the next one.

## Verified Report Behavior in Build 6061

The following behavior was reproduced with MetaTrader 5 build 6061 on an
FTMO-Demo account:

- **`Report=` must be a relative name** without a path or extension. MT5 ignores
  an absolute path and writes `<name>.htm` plus the `<name>.png` chart at the
  terminal data-folder root. The orchestrator supplies a relative name and
  collects the file from that folder.
- **Encodings differ by report type.** Backtest `.htm` reports are UTF-16;
  optimization XML is UTF-8. The reader detects the BOM and NUL-byte density.
- **Deals table columns are localized.** A Spanish report uses `Fecha/Hora`
  rather than `Hora` for the time column and includes a `Balance` column. The
  parser accepts these labels to reconstruct monthly and yearly balance history
  and months-to-new-high.
- **`Optimization=3` does not populate the XML.** The generated
  `<name>.symbols.xml` contains a header and zero rows; the 73 per-symbol results
  exist only in the binary `Tester\cache\*.opt` cache. Round 1 therefore runs
  one `Optimization=0` backtest per symbol from `common.symbols` instead of
  relying on the XML.
- **Single-parameter optimization works.** `Optimization=1` emits SpreadsheetML
  with one row per combination and is used by Round 3.
- **`ShutdownTerminal=1` closes the terminal after completion.** The runner waits
  for that exit rather than treating the first report-file appearance as
  completion because optimization reports are written incrementally.

## Caveats

- **32 ms delay:** no documented INI key controls the random ping-based delay.
  The terminal usually inherits the last GUI setting. Configure it once in the
  Strategy Tester delay controls **(verify)**.
- **Encoding:** INI files are written as UTF-8. Some builds may require UTF-16
  when names or comments contain non-ASCII text.
- **Market Watch:** `Optimization=3` tests exactly the visible Market Watch
  symbols. Add or remove symbols there to control that universe.
- **Terminal discovery:** `--terminal-path` takes precedence, followed by
  `$MT5_TERMINAL_PATH`, `config.terminal_path`, and common `Program Files`
  installations.
