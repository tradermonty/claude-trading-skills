#!/usr/bin/env python3
"""Orchestrate the 3-round MT5 bot-selection pipeline from the command line.

For every ``.ex5`` in the *candidates* folder:

  Round 1  one ``Optimization=0`` backtest per configured symbol. Gate: >=5
           symbols profitable AND best symbol profit >= 3x deposit.
  Round 2  single backtest on the best symbol; analyze the quality profile
           (net profit %, worst drawdown %, % positive months, all years
           positive, LR Correlation, months-to-new-high).
  Round 3  sequential per-parameter optimization of the 5-6 inputs after
           ``MagicNumber`` (range +/-50%, step 5%), one at a time; then a final
           backtest with the optimized set.
  Finalist optimized result improves on Round 2 AND profit >= 4x deposit AND
           worst drawdown <= 12%.

Tested bots move to *in-testing*; finalists are also copied to *finalists* with
their optimized ``.set``. Progress is checkpointed to ``state.json`` (``--resume``
continues where it stopped) and a cross-run learning store reorders Round-3
parameters by historical impact.

Pure helpers (INI builders, range/param/finalist logic) are unit-tested without
MT5. Launching MT5 requires Windows + the terminal at run time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PureWindowsPath

_HERE = Path(__file__).resolve().parent
try:
    from mt5_common import to_float
    from mt5_learnings import Learnings
    from parse_mt5_optimization import best_param_value, gate_round1, parse_passes
    from parse_mt5_report import parse_report_file
except ImportError:  # pragma: no cover - import shim
    sys.path.insert(0, str(_HERE))
    from mt5_common import to_float
    from mt5_learnings import Learnings
    from parse_mt5_optimization import best_param_value, gate_round1, parse_passes
    from parse_mt5_report import parse_report_file

DEFAULTS = {
    "common": {
        "period": "H1",
        "from": "2020.01.01",
        "to": "2026.06.30",
        "model": 4,  # every tick based on real ticks
        "deposit": 10000,
        "currency": "USD",
        "leverage": 100,
        "delay_ms": 32,
        "optimization_criterion": 0,  # Maximum profitability (maximum balance)
    },
    "gates": {
        "round1_min_positive": 5,
        "round1_min_profit_multiple": 3.0,
        "finalist_min_profit_multiple": 4.0,
        "finalist_max_drawdown_pct": 12.0,
        "finalist_require_improvement": True,
    },
    "round2_reference": {
        "min_profit_pct": 300.0,
        "max_drawdown_pct": 15.0,
        "min_pct_positive_months": 70.0,
        "require_all_years_positive": True,
        "min_lr_correlation": 0.80,
        "max_months_to_new_high": 3,
    },
    "round3": {
        "range_pct": 0.5,
        "step_pct": 0.05,
        "params_after_magic": 6,
        "magic_param_name": "MagicNumber",
        "use_learned_order": True,
    },
    "timeout_seconds": 3600,
}


class TerminalTerminationError(RuntimeError):
    """Fatal: the exact MT5 child may still own the shared terminal data folder."""

    def __init__(self, pid: int, context: str):
        self.pid = pid
        self.context = context
        super().__init__(f"could not confirm termination of MT5 PID {pid} ({context})")


# ----------------------------------------------------------------------------
# Pure, unit-tested helpers
# ----------------------------------------------------------------------------


def normalize_date(value: str) -> str:
    return str(value).strip().replace("-", ".").replace("/", ".")


def experts_relpath(candidates_dir: str | Path) -> str:
    """Path of the candidates folder relative to ``MQL5\\Experts`` (for Expert=)."""
    raw = str(candidates_dir)
    windows_path = "\\" in raw
    path = PureWindowsPath(raw) if windows_path else Path(raw)
    parts = list(path.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == "experts":
            return "\\".join(parts[i + 1 :])
    # Fall back to just the folder name.
    return path.name


def mt5_data_dir(candidates_dir: str | Path) -> Path | None:
    """The MT5 data directory (the folder that contains ``MQL5``)."""
    raw = str(candidates_dir)
    windows_path = "\\" in raw
    path = PureWindowsPath(raw) if windows_path else Path(raw)
    parts = list(path.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == "mql5":
            parent = type(path)(*parts[:i])
            return Path(str(parent))
    return None


def shared_lock_path(candidates_dir: str | Path, terminal: str | Path) -> Path:
    """Return one lock path for every run sharing an MT5 data identity."""
    data_dir = mt5_data_dir(candidates_dir)
    if data_dir is not None:
        return data_dir / ".mt5-robot-tester.lock"
    return Path(terminal).resolve().parent / ".mt5-robot-tester.lock"


def fmt_num(value) -> str:
    """Format a number for an INI without scientific notation or noisy decimals."""
    f = float(value)
    if f == int(f):
        return str(int(f))
    return f"{f:.10g}"


def compute_range(value: float, range_pct: float, step_pct: float):
    """Return (start, step, stop) for +/-range_pct around ``value``, step_pct step.

    Returns ``None`` for a zero value (cannot scale). Integer-valued inputs get
    integer bounds and a step of at least 1.
    """
    if value == 0:
        return None
    lo = value * (1 - range_pct)
    hi = value * (1 + range_pct)
    start, stop = (lo, hi) if lo <= hi else (hi, lo)
    step = abs(value) * step_pct
    if float(value) == int(value):
        start, stop = int(round(start)), int(round(stop))
        step = max(1, int(round(step)))
    return (start, step, stop)


def select_strategy_params(ordered_names: list[str], magic_name: str, count: int) -> list[str]:
    """The ``count`` input names immediately after ``magic_name`` (5-6 params).

    If MagicNumber is absent, fall back to the first ``count`` names.
    """
    lowered = [n.lower() for n in ordered_names]
    try:
        idx = lowered.index(magic_name.lower())
        after = ordered_names[idx + 1 :]
    except ValueError:
        after = ordered_names[:]
    return after[:count]


def evaluate_finalist(
    final_metrics: dict, r2_profit: float | None, deposit: float, gates: dict
) -> tuple[bool, str]:
    """Finalist iff improved AND profit >= Nx deposit AND worst DD <= limit."""
    profit = final_metrics.get("net_profit")
    dd = final_metrics.get("drawdown_max_pct")
    profit_threshold = gates["finalist_min_profit_multiple"] * deposit
    dd_limit = gates["finalist_max_drawdown_pct"]

    reasons = []
    improved = True
    if gates.get("finalist_require_improvement", True):
        improved = profit is not None and r2_profit is not None and profit > r2_profit
        if not improved:
            reasons.append(f"does not improve on R2 ({profit} <= {r2_profit})")
    if profit is None or profit < profit_threshold:
        reasons.append(
            f"profit {profit} < {profit_threshold:.0f} (≥{gates['finalist_min_profit_multiple']}x)"
        )
    if dd is None or dd > dd_limit:
        reasons.append(f"DD {dd}% > {dd_limit}%")

    passed = not reasons and improved
    return passed, ("ok" if passed else "; ".join(reasons))


def evaluate_round2_profile(metrics: dict, deposit: float, ref: dict) -> dict:
    """Score the Round-2 quality profile against the reference thresholds."""
    profit_pct = metrics.get("profit_pct")
    dd = metrics.get("drawdown_max_pct")
    pos_months = metrics.get("pct_positive_months")
    all_years = metrics.get("all_years_positive")
    lr = metrics.get("lr_correlation")
    mtnh = metrics.get("max_months_to_new_high")
    checks = {
        "profit_pct": profit_pct is not None and profit_pct >= ref["min_profit_pct"],
        "drawdown": dd is not None and dd < ref["max_drawdown_pct"],
        "positive_months": (pos_months is not None and pos_months > ref["min_pct_positive_months"]),
        "all_years_positive": (all_years is True if ref["require_all_years_positive"] else True),
        "lr_correlation": lr is not None and lr >= ref["min_lr_correlation"],
        "months_to_new_high": (mtnh is not None and mtnh <= ref["max_months_to_new_high"]),
    }
    checks["all_passed"] = all(checks.values())
    return checks


def parse_set_file(path: str | Path) -> list[tuple[str, object]]:
    """Parse an MT5 ``.set`` into an ordered [(name, value)] list.

    Ignores the ``name,F`` / ``name,1..3`` optimization-range companion lines.
    """
    inputs: list[tuple[str, object]] = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if "," in key:  # companion optimization line
            continue
        num = to_float(value)
        inputs.append((key.strip(), num if num is not None else value.strip()))
    return inputs


def inputs_from_passes(passes: list[dict]) -> list[tuple[str, object]]:
    """Ordered [(name, value)] of EA inputs taken from an optimization report."""
    for p in passes:
        inputs = p.get("inputs")
        if inputs:
            return list(inputs.items())
    return []


# ----------------------------------------------------------------------------
# INI builders
# ----------------------------------------------------------------------------


def _base_tester_lines(expert: str, symbol: str, common: dict, report_no_ext: Path) -> list[str]:
    return [
        "[Tester]",
        f"Expert={expert}",
        f"Symbol={symbol}",
        f"Period={common['period']}",
        f"Model={common['model']}",
        f"FromDate={normalize_date(common['from'])}",
        f"ToDate={normalize_date(common['to'])}",
        "ForwardMode=0",
        f"Deposit={common['deposit']}",
        f"Currency={common['currency']}",
        f"Leverage={common['leverage']}",
        f"Report={report_no_ext}",
        "ReplaceReport=1",
        "ShutdownTerminal=1",
        "Visual=0",
    ]


def build_backtest_ini(
    expert: str,
    symbol: str,
    common: dict,
    report_no_ext: Path,
    inputs: list[tuple[str, object]] | None = None,
) -> str:
    """Optimization=0: single backtest, optionally with fixed [TesterInputs]."""
    lines = _base_tester_lines(expert, symbol, common, report_no_ext)
    lines.insert(-4, "Optimization=0")
    text = "\n".join(lines) + "\n"
    if inputs:
        text += "\n[TesterInputs]\n"
        for name, value in inputs:
            text += f"{name}={_fmt_input(value)}\n"
    return text


def build_optimize_param_ini(
    expert: str,
    symbol: str,
    common: dict,
    report_no_ext: Path,
    strategy_inputs: list[tuple[str, object]],
    target: str,
    rng: tuple,
) -> str:
    """Optimization=1 over a single ``target`` parameter; others fixed."""
    lines = _base_tester_lines(expert, symbol, common, report_no_ext)
    lines.insert(-4, "Optimization=1")
    lines.insert(-4, f"OptimizationCriterion={common['optimization_criterion']}")
    text = "\n".join(lines) + "\n\n[TesterInputs]\n"
    start, step, stop = rng
    for name, value in strategy_inputs:
        if name == target:
            text += (
                f"{name}={_fmt_input(start)}||{_fmt_input(start)}||"
                f"{_fmt_input(step)}||{_fmt_input(stop)}||Y\n"
            )
        else:
            text += f"{name}={_fmt_input(value)}\n"
    return text


def _fmt_input(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return fmt_num(value)
    return str(value)


# ----------------------------------------------------------------------------
# Terminal / report I/O
# ----------------------------------------------------------------------------


def find_terminal(explicit: str | None = None, configured: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("MT5_TERMINAL_PATH"):
        candidates.append(Path(os.environ["MT5_TERMINAL_PATH"]))
    if configured:
        candidates.append(Path(configured))
    for base in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        if not base:
            continue
        candidates.append(Path(base) / "MetaTrader 5" / "terminal64.exe")
        candidates.extend(Path(base).glob("*/terminal64.exe"))
    for path in candidates:
        if path and path.exists():
            return path
    return None


def _find_report_in(data_dir: Path, report_name: str, exts) -> Path | None:
    """MT5 writes ``Report=<name>`` to ``<data_dir>\\<name>.<ext>`` (build 6061)."""
    for ext in exts:
        candidate = data_dir / f"{report_name}{ext}"
        if candidate.exists():
            return candidate
    return None


def terminate_child_process(proc: subprocess.Popen, timeout: float = 15) -> bool:
    """Terminate one exact child process and confirm that it exited."""
    if proc.poll() is not None:
        return True
    try:
        proc.terminate()
    except OSError:
        return proc.poll() is not None
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            return proc.poll() is not None
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            return False
    return proc.poll() is not None


def _quarantine_reports(data_dir: Path, report_name: str, exts) -> None:
    """Keep failed-run artifacts for diagnosis without leaving a reusable report."""
    token = f"failed-{time.time_ns()}"
    for ext in list(exts) + [".png"]:
        source = data_dir / f"{report_name}{ext}"
        if not source.exists():
            continue
        destination = data_dir / f"{report_name}.{token}{ext}"
        try:
            source.replace(destination)
        except OSError:
            try:
                source.unlink()
            except OSError:
                pass


def run_tester(
    terminal: Path,
    ini_path: Path,
    data_dir: Path,
    report_name: str,
    timeout: int,
    portable: bool,
    exts,
    poll_interval: float = 3.0,
) -> tuple[Path | None, str]:
    """Launch MT5 for one config and wait for the report by **polling**.

    Build 6061 ignores an absolute ``Report=`` path and instead writes the report
    (``.htm`` for a backtest, ``.xml`` for optimization, plus a ``.png`` graph) to
    the terminal **data folder** using the relative ``Report=`` name. So we poll
    ``data_dir`` for ``<report_name>.<ext>`` only after the terminal exits, because
    reports are written incrementally. If the terminal does not exit before the
    timeout, terminate that exact child and perform one final report check.
    """
    for ext in list(exts) + [".png"]:
        stale = data_dir / f"{report_name}{ext}"
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                return None, "stale_report_cleanup_failed"
    cmd = [str(terminal), f"/config:{ini_path}"]
    if portable:
        cmd.append("/portable")
    try:
        proc = subprocess.Popen(cmd)
    except FileNotFoundError:
        return None, "terminal_not_found"

    # Wait for the terminal to close itself (ShutdownTerminal=1 closes it only
    # when the test/optimization has finished). Do NOT proceed on mere file
    # appearance — an optimization report is written incrementally (header first,
    # then one row per symbol), so closing early truncates it to zero results.
    deadline = time.time() + timeout
    try:
        while proc.poll() is None and time.time() < deadline:
            time.sleep(poll_interval)
    except BaseException:
        if not terminate_child_process(proc):
            _quarantine_reports(data_dir, report_name, exts)
            raise TerminalTerminationError(proc.pid, "interrupted")
        raise
    timed_out = proc.poll() is None
    if timed_out:
        stopped = terminate_child_process(proc)
        _quarantine_reports(data_dir, report_name, exts)
        if not stopped:
            raise TerminalTerminationError(proc.pid, "timeout")
        return None, "timeout"

    returncode = proc.poll()
    if returncode != 0:
        _quarantine_reports(data_dir, report_name, exts)
        return None, f"terminal_exit_{returncode}"

    report = _find_report_in(data_dir, report_name, exts)
    try:
        if report and report.is_file() and report.stat().st_size > 0:
            return report, "ok"
    except OSError:
        pass
    return None, "no_report"


# ----------------------------------------------------------------------------
# State / log
# ----------------------------------------------------------------------------


class Pipeline:
    def __init__(
        self,
        config: dict,
        output_dir: Path,
        terminal: Path | None,
        timeout: int,
        portable: bool,
        resume: bool,
    ):
        self.config = config
        self.common = {**DEFAULTS["common"], **config.get("common", {})}
        self.gates = {**DEFAULTS["gates"], **config.get("gates", {})}
        self.ref = {**DEFAULTS["round2_reference"], **config.get("round2_reference", {})}
        self.r3 = {**DEFAULTS["round3"], **config.get("round3", {})}
        self.output_dir = output_dir
        self.terminal = terminal
        self.timeout = timeout
        self.portable = portable
        self.resume = resume

        self.reports_dir = output_dir / "mt5_reports"
        self.ini_dir = output_dir / "mt5_ini"
        self.sets_dir = output_dir / "sets"
        for d in (self.reports_dir, self.ini_dir, self.sets_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.state_path = output_dir / "state.json"
        self.log_path = output_dir / "run.log"
        self.state = self._load_state()

        self.learn = Learnings(output_dir / "learnings.json")
        self._learn_md = output_dir / "learnings.md"

        folders = config.get("folders", {})
        self.candidates = Path(folders["candidates"]) if folders.get("candidates") else None
        self.in_testing = Path(folders["in_testing"]) if folders.get("in_testing") else None
        self.finalists = Path(folders["finalists"]) if folders.get("finalists") else None
        self.expert_prefix = config.get("experts_relpath") or (
            experts_relpath(self.candidates) if self.candidates else ""
        )
        self.mt5_data_dir = mt5_data_dir(self.candidates) if self.candidates else None

    def tester_log_tail(self, n: int = 15) -> str:
        """Last non-empty lines of the newest MT5 Tester log (decoded UTF-16)."""
        if not self.mt5_data_dir:
            return ""
        logs_dir = self.mt5_data_dir / "Tester" / "logs"
        try:
            logs = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
        except OSError:
            return ""
        if not logs:
            return ""
        try:
            raw = logs[-1].read_bytes().decode("utf-16", errors="replace")
        except OSError:
            return ""
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        return " | ".join(lines[-n:])

    def _load_state(self) -> dict:
        if self.resume and self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "schema_version": "2.0",
            "started": dt.datetime.now().isoformat(timespec="seconds"),
            "bots": {},
        }

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=str(self.state_path.parent), suffix=".state.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(self.state, indent=2, ensure_ascii=False))
            os.replace(temp_name, self.state_path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def log(self, msg: str) -> None:
        line = f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}"
        print(line, flush=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    # --- per-bot pipeline --------------------------------------------------

    def expert_path(self, ex5: Path) -> str:
        return f"{self.expert_prefix}\\{ex5.name}" if self.expert_prefix else ex5.name

    def _round1_symbols(self) -> list[str] | None:
        """The Market-Watch symbol list for Round-1 screening (from config)."""
        syms = self.common.get("symbols") or self.config.get("symbols")
        if not syms:
            return None
        return list(dict.fromkeys(str(symbol).strip() for symbol in syms if str(symbol).strip()))

    def _input_path(self, name: str, ex5: Path) -> Path | None:
        candidates = []
        sets_dir = self.config.get("sets_dir")
        if sets_dir:
            candidates.append(Path(sets_dir) / f"{name}.set")
        candidates.append(ex5.with_suffix(".set"))
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
        return None

    def _discover_inputs(self, name: str, ex5: Path) -> list:
        """EA inputs for Round-3, from a ``.set`` file (config sets_dir or beside
        the bot). Returns [] if none — Round 3 is then skipped."""
        path = self._input_path(name, ex5)
        return parse_set_file(path) if path is not None else []

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _execution_fingerprint(self, name: str, ex5: Path) -> str:
        """Identity of every input that can change a resumed bot's outcome."""
        set_path = self._input_path(name, ex5)
        payload = {
            "schema_version": "2.0",
            "ea_sha256": self._sha256(ex5),
            "set_sha256": self._sha256(set_path) if set_path is not None else None,
            "execution": {
                "common": self.common,
                "gates": self.gates,
                "round2_reference": self.ref,
                "round3": self.r3,
                "expert_prefix": self.expert_prefix,
                "terminal": str(self.terminal) if self.terminal is not None else None,
                "portable": self.portable,
            },
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def report_name(self, name: str, stub: str) -> str:
        """Safe, relative Report= name (MT5 writes it into the data folder)."""
        safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{name}_{stub}").strip("_")
        return f"mt5rt_{safe}"[:120]

    def _collect_report(self, src: Path, name: str, stub: str) -> Path:
        """Move the report (and its .png graph) from the data folder to output."""
        dest = self.reports_dir / f"{name}__{stub}{src.suffix}"
        if dest.exists():
            self.log(f"[{name}] warning: destination report already exists: {dest}")
            return src
        try:
            self._move_exclusive(src, dest)
        except OSError:
            return src
        png = src.with_suffix(".png")
        if png.exists():
            png_dest = self.reports_dir / f"{name}__{stub}.png"
            if png_dest.exists():
                self.log(f"[{name}] warning: destination chart already exists: {png_dest}")
                return dest
            try:
                self._move_exclusive(png, png_dest)
            except OSError:
                pass
        return dest

    def _run(self, ini_text: str, name: str, stub: str, report_name: str, exts) -> tuple:
        ini_path = self.ini_dir / f"{name}__{stub}.ini"
        ini_path.write_text(ini_text, encoding="utf-8")
        data_dir = self.mt5_data_dir or self.reports_dir
        src, status = run_tester(
            self.terminal, ini_path, data_dir, report_name, self.timeout, self.portable, exts
        )
        report = None
        if status == "ok" and src:
            report = self._collect_report(src, name, stub)
        else:
            tail = self.tester_log_tail()
            if tail:
                self.log(f"[{name}] tester log: {tail}")
        return report, status, ini_path

    def process_bot(self, ex5: Path) -> dict:
        name = ex5.stem
        fingerprint = self._execution_fingerprint(name, ex5)
        existing = self.state["bots"].get(name)
        if existing is not None and existing.get("fingerprint") != fingerprint:
            self.log(f"[{name}] inputs or config changed; resetting this bot's state")
            existing = None
        if existing is None:
            existing = {"status": "pending", "fingerprint": fingerprint}
            self.state["bots"][name] = existing
            self._save_state()
        st = existing
        if self.resume and st.get("status") == "done":
            self.log(f"[{name}] already completed ({st.get('verdict')}); skipping")
            return st

        expert = self.expert_path(ex5)

        # --- Round 1: screen across all pairs via per-symbol backtests -----
        # Build 6061 leaves the Optimization=3 XML empty (results go to the
        # binary .opt cache), so we backtest each Market-Watch symbol instead.
        if "round1" not in st:
            symbols = self._round1_symbols()
            if not symbols:
                return self._finish(
                    name, "error", "R1: missing symbol list (config common.symbols)", st
                )
            # Resume mid-Round-1: reuse symbols already backtested.
            passes = [
                p
                for p in (st.get("round1_passes") or [])
                if p.get("status", "ok") == "ok" and isinstance(p.get("profit"), (int, float))
            ]
            done = {p["symbol"] for p in passes}
            if not passes:
                self.log(f"[{name}] Round 1: backtests across {len(symbols)} symbols")
            for i, sym in enumerate(symbols, 1):
                if sym in done:
                    continue
                self.log(f"[{name}] R1 {i}/{len(symbols)}: {sym}")
                rname = self.report_name(name, f"R1_{sym}")
                ini = build_backtest_ini(expert, sym, self.common, rname)
                report, status, _ = self._run(
                    ini, name, f"R1_{sym}", rname, (".htm", ".html", ".xml")
                )
                if status == "ok" and report:
                    m = parse_report_file(report, self.common["from"], self.common["to"])
                    if not isinstance(m.get("net_profit"), (int, float)):
                        st["status"] = "error"
                        st["reason"] = f"R1 {sym}: invalid_report"
                        self._save_state()
                        return st
                    passes.append(
                        {
                            "symbol": sym,
                            "profit": m.get("net_profit"),
                            "drawdown_pct": m.get("drawdown_max_pct"),
                            "trades": m.get("total_trades"),
                            "status": "ok",
                        }
                    )
                else:
                    st["status"] = "error"
                    st["reason"] = f"R1 {sym}: {status}"
                    st["round1_passes"] = passes
                    self._save_state()
                    return st
                # Checkpoint after every symbol so progress survives interruption.
                st["status"] = "round1"
                st["round1_passes"] = passes
                self._save_state()
            gate = gate_round1(
                passes,
                self.common["deposit"],
                self.gates["round1_min_positive"],
                self.gates["round1_min_profit_multiple"],
            )
            st["round1"] = gate
            st["round1_passes"] = passes
            st["inputs"] = self._discover_inputs(name, ex5)
            self._save_state()
        gate = st["round1"]
        if not gate["passed"]:
            return self._finish(
                name,
                "rejected",
                f"R1: {gate['reason']}",
                st,
                ex5=ex5,
            )

        best_symbol = gate["best_symbol"]
        self.learn.record_best_pair(best_symbol, gate.get("best_profit"))

        # --- Round 2 -------------------------------------------------------
        if "round2" not in st:
            self.log(f"[{name}] Round 2: backtest on {best_symbol}")
            rname = self.report_name(name, "R2")
            ini = build_backtest_ini(
                expert,
                best_symbol,
                self.common,
                rname,
                inputs=st.get("inputs") or None,
            )
            report, status, _ = self._run(ini, name, "R2", rname, (".htm", ".html", ".xml"))
            if status != "ok":
                return self._finish(name, "error", f"R2 {status}", st)
            metrics = parse_report_file(report, self.common["from"], self.common["to"])
            required = (
                "net_profit",
                "profit_pct",
                "drawdown_max_pct",
                "pct_positive_months",
                "all_years_positive",
                "lr_correlation",
                "max_months_to_new_high",
            )
            if any(metrics.get(key) is None for key in required):
                return self._finish(name, "error", "R2 invalid_report", st)
            st["round2"] = metrics
            st["round2_profile"] = evaluate_round2_profile(
                metrics, self.common["deposit"], self.ref
            )
            self._save_state()
        r2 = st["round2"]
        r2_profit = r2.get("net_profit")

        # --- Round 3: sequential parameter optimization (needs input .set) -
        if "round3" not in st:
            if st.get("inputs"):
                round3 = self._round3(name, expert, best_symbol, st)
                if round3.get("status") != "ok":
                    st["round3_error"] = round3
                    self._save_state()
                    return self._finish(
                        name,
                        "error",
                        f"R3 {round3.get('status', 'error')}",
                        st,
                    )
                st["round3"] = round3
                st.pop("round3_error", None)
            else:
                self.log(f"[{name}] R3 skipped (no input .set); verdict based on R2")
                st["round3"] = {
                    "status": "ok",
                    "per_param": [],
                    "final_metrics": st["round2"],
                    "best_set": None,
                }
            self._save_state()
        r3 = st["round3"]

        final = r3.get("final_metrics") or {}
        optimized = bool(r3.get("per_param"))
        gates = self.gates if optimized else {**self.gates, "finalist_require_improvement": False}
        passed, reason = evaluate_finalist(final, r2_profit, self.common["deposit"], gates)
        verdict = "finalist" if passed else "rejected"
        st["final_reason"] = reason
        return self._finish(name, verdict, reason, st, ex5=ex5, optimized_set=r3.get("best_set"))

    def _round3(self, name: str, expert: str, symbol: str, st: dict) -> dict:
        ordered = [(n, v) for n, v in st.get("inputs", [])]
        ordered_names = [n for n, _ in ordered]
        strategy_names = select_strategy_params(
            ordered_names, self.r3["magic_param_name"], self.r3["params_after_magic"]
        )
        if self.r3.get("use_learned_order", True):
            strategy_names = self.learn.param_priority_order(strategy_names)

        # Working values: start from discovered defaults.
        values = dict(ordered)
        best_profit = st["round2"].get("net_profit")
        per_param = []

        for target in strategy_names:
            v = values.get(target)
            if not isinstance(v, (int, float)):
                continue
            rng = compute_range(v, self.r3["range_pct"], self.r3["step_pct"])
            if rng is None:
                continue
            self.log(f"[{name}] R3 optimizes {target} over {rng}")
            cur_inputs = [(n, values[n]) for n in ordered_names]
            rname = self.report_name(name, f"R3_{target}")
            ini = build_optimize_param_ini(
                expert, symbol, self.common, rname, cur_inputs, target, rng
            )
            report, status, _ = self._run(
                ini, name, f"R3_{target}", rname, (".xml", ".symbols.xml", ".htm", ".html")
            )
            if status != "ok":
                return {"status": status, "failed_param": target, "per_param": per_param}
            passes = parse_passes(report)
            best_val = best_param_value(passes, target, by="profit")
            top = max(
                (p for p in passes if isinstance(p.get("profit"), (int, float))),
                key=lambda p: p["profit"],
                default=None,
            )
            new_profit = top.get("profit") if top else None
            if best_val is None or new_profit is None:
                return {
                    "status": "invalid_report",
                    "failed_param": target,
                    "per_param": per_param,
                }
            improvement = ((new_profit or 0) - (best_profit or 0)) if new_profit is not None else 0
            if (
                best_val is not None
                and new_profit is not None
                and new_profit >= (best_profit or float("-inf"))
            ):
                values[target] = best_val
                best_profit = new_profit
            self.learn.record_param_optimization(target, improvement)
            per_param.append(
                {
                    "param": target,
                    "best_value": best_val,
                    "profit": new_profit,
                    "improvement": improvement,
                }
            )

        best_set = [(n, values.get(n)) for n in ordered_names]

        # Final backtest with exactly the same complete input set we will save.
        final_metrics = {}
        self.log(f"[{name}] R3 final optimized backtest on {symbol}")
        rname = self.report_name(name, "final")
        ini = build_backtest_ini(expert, symbol, self.common, rname, inputs=best_set)
        report, status, _ = self._run(ini, name, "final", rname, (".htm", ".html", ".xml"))
        if status == "ok":
            final_metrics = parse_report_file(report, self.common["from"], self.common["to"])
            if any(final_metrics.get(key) is None for key in ("net_profit", "drawdown_max_pct")):
                return {"status": "invalid_report", "per_param": per_param}
        else:
            return {"status": status, "per_param": per_param}

        return {
            "status": "ok",
            "per_param": per_param,
            "best_set": best_set,
            "strategy_set": best_set,
            "final_metrics": final_metrics,
        }

    def _finish(
        self,
        name: str,
        verdict: str,
        reason: str,
        st: dict,
        ex5: Path | None = None,
        optimized_set: list | None = None,
    ) -> dict:
        st["verdict"] = verdict
        st["reason"] = reason
        self.learn.record_bot(name, verdict, reason)
        self.log(f"[{name}] => {verdict.upper()} ({reason})")
        if verdict == "error":
            st["status"] = "error"
            self._save_state()
            return st
        if ex5 is not None and verdict != "error":
            moved, move_error = self._move_bot(ex5, verdict, optimized_set)
            st["moved"] = moved
            if not moved:
                st["status"] = "move_error"
                st["move_error"] = move_error
                self.log(f"[{name}] MOVE ERROR: {move_error}")
                self._save_state()
                return st
        st["status"] = "done"
        self._save_state()
        return st

    @staticmethod
    def _copy_exclusive(source: Path, destination: Path) -> None:
        """Copy without ever replacing an existing destination."""
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with source.open("rb") as src, os.fdopen(fd, "wb") as dest:
                fd = -1
                shutil.copyfileobj(src, dest)
            shutil.copystat(source, destination)
        except BaseException:
            if fd >= 0:
                os.close(fd)
            try:
                destination.unlink()
            except OSError:
                pass
            raise

    @staticmethod
    def _cleanup_created(paths: list[Path]) -> None:
        for path in reversed(paths):
            try:
                path.unlink()
            except OSError:
                pass

    @classmethod
    def _move_exclusive(cls, source: Path, destination: Path) -> None:
        """Copy then remove a source only after an exclusive destination succeeds."""
        cls._copy_exclusive(source, destination)
        try:
            source.unlink()
        except BaseException:
            try:
                destination.unlink()
            except OSError:
                pass
            raise

    def _move_bot(self, ex5: Path, verdict: str, optimized_set: list | None) -> tuple[bool, str]:
        """Copy/move one bot fail-closed, without overwriting user files."""
        if self.in_testing is None:
            return False, "missing folders.in_testing"
        in_testing_dest = self.in_testing / ex5.name
        if in_testing_dest.exists():
            return False, f"destination already exists: {in_testing_dest}"

        finalist_dest = None
        finalist_set = None
        if verdict == "finalist":
            if self.finalists is None:
                return False, "missing folders.finalists"
            finalist_dest = self.finalists / ex5.name
            finalist_set = self.finalists / f"{ex5.stem}.set" if optimized_set else None
            for destination in (finalist_dest, finalist_set):
                if destination is not None and destination.exists():
                    return False, f"destination already exists: {destination}"

        created: list[Path] = []
        try:
            self.in_testing.mkdir(parents=True, exist_ok=True)
            if finalist_dest is not None:
                self.finalists.mkdir(parents=True, exist_ok=True)
                self._copy_exclusive(ex5, finalist_dest)
                created.append(finalist_dest)
                if finalist_set is not None:
                    self._write_set(finalist_set, optimized_set, exclusive=True)
                    created.append(finalist_set)
            self._move_exclusive(ex5, in_testing_dest)
        except OSError as exc:
            if ex5.exists():
                self._cleanup_created(created)
            return False, str(exc)
        return True, ""

    @staticmethod
    def _write_set(path: Path, inputs: list, *, exclusive: bool = False) -> None:
        lines = [f"{n}={_fmt_input(v)}" for n, v in inputs if v is not None]
        content = "\n".join(lines) + "\n"
        if not exclusive:
            path.write_text(content, encoding="utf-8")
            return
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = -1
                handle.write(content)
        except BaseException:
            if fd >= 0:
                os.close(fd)
            try:
                path.unlink()
            except OSError:
                pass
            raise

    # --- leaderboard -------------------------------------------------------

    def write_leaderboard(self) -> tuple[Path, Path]:
        bots = self.state["bots"]
        rows = []
        for name, st in bots.items():
            final = (st.get("round3") or {}).get("final_metrics") or {}
            r2 = st.get("round2") or {}
            rows.append(
                {
                    "name": name,
                    "verdict": st.get("verdict"),
                    "reason": st.get("reason"),
                    "best_symbol": (st.get("round1") or {}).get("best_symbol"),
                    "r2_profit": r2.get("net_profit"),
                    "final_profit": final.get("net_profit"),
                    "final_dd_pct": final.get("drawdown_max_pct"),
                    "lr": r2.get("lr_correlation"),
                }
            )

        def rank_key(r):
            return (
                r["verdict"] == "finalist",
                r["final_profit"]
                if isinstance(r["final_profit"], (int, float))
                else (
                    r["r2_profit"] if isinstance(r["r2_profit"], (int, float)) else float("-inf")
                ),
            )

        rows.sort(key=rank_key, reverse=True)

        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        json_out = self.output_dir / f"leaderboard_{stamp}.json"
        md_out = self.output_dir / f"leaderboard_{stamp}.md"
        json_out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        md_out.write_text(self._render_leaderboard_md(rows), encoding="utf-8")
        return md_out, json_out

    @staticmethod
    def _render_leaderboard_md(rows: list[dict]) -> str:
        def f(v):
            if v is None:
                return "—"
            return f"{v:,.2f}" if isinstance(v, float) else str(v)

        lines = [
            "# MT5 Robot Tester — Leaderboard",
            "",
            f"Generated: {dt.datetime.now():%Y-%m-%d %H:%M:%S}",
            "",
            "| # | Bot | Verdict | Best symbol | R2 profit | Final profit | Final DD % | LR | Reason |",
            "|---|-----|---------|-------------|----------:|-------------:|-----------:|---:|--------|",
        ]
        for i, r in enumerate(rows, 1):
            lines.append(
                f"| {i} | {r['name']} | {r.get('verdict', '')} | "
                f"{r.get('best_symbol') or '—'} | {f(r.get('r2_profit'))} | "
                f"{f(r.get('final_profit'))} | {f(r.get('final_dd_pct'))} | "
                f"{f(r.get('lr'))} | {r.get('reason', '')} |"
            )
        lines.append("")
        return "\n".join(lines)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def discover_bots(candidates_dir: Path) -> list[Path]:
    bots = sorted([*candidates_dir.glob("*.ex5"), *candidates_dir.glob("*.mq5")])
    # Prefer compiled .ex5 when both exist for the same stem.
    seen = {}
    for b in bots:
        seen.setdefault(b.stem, b)
        if b.suffix == ".ex5":
            seen[b.stem] = b
    return sorted(seen.values())


def load_config(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def acquire_lock(lock_path: Path):
    """Acquire an OS lock held by the returned open file for this process lifetime."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode())
        handle.flush()
        if lock_blocker_path(lock_path).exists():
            release_lock(handle)
            return None
        return handle
    except (OSError, BlockingIOError):
        try:
            handle.close()
        except (NameError, OSError):
            pass
        return None


def release_lock(handle) -> None:
    try:
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        handle.close()


def lock_blocker_path(lock_path: Path) -> Path:
    return lock_path.with_name(f"{lock_path.name}.blocked")


def block_lock(lock_path: Path, error: TerminalTerminationError) -> Path:
    """Require manual MT5 process verification before this data folder is reused."""
    blocker = lock_blocker_path(lock_path)
    blocker.write_text(
        json.dumps(
            {
                "reason": "unconfirmed_mt5_termination",
                "pid": error.pid,
                "context": error.context,
                "recorded_at": dt.datetime.now().isoformat(timespec="seconds"),
                "recovery": (
                    "Verify this MT5 PID/process tree has exited, then remove this "
                    "blocker file manually."
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return blocker


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; make our output UTF-8 safe.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", help="Pipeline configuration JSON.")
    parser.add_argument("--candidates-dir", help="Override the candidate-bot folder.")
    parser.add_argument("--output-dir", default="reports/mt5_pipeline")
    parser.add_argument("--terminal-path", default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--portable", action="store_true")
    parser.add_argument(
        "--resume", action="store_true", help="Resume from state.json without repeating work."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Generate Round 1 INIs without launching MT5."
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.candidates_dir:
        config.setdefault("folders", {})["candidates"] = args.candidates_dir

    candidates = config.get("folders", {}).get("candidates")
    if not candidates:
        print(
            "error: candidate folder is required (config folders.candidates or --candidates-dir)",
            file=sys.stderr,
        )
        return 1
    candidates_dir = Path(candidates)
    if not candidates_dir.exists():
        print(f"error: candidate folder does not exist: {candidates_dir}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timeout = args.timeout or config.get("timeout_seconds", DEFAULTS["timeout_seconds"])

    bots = discover_bots(candidates_dir)
    if not bots:
        print(f"error: no .ex5/.mq5 files found in {candidates_dir}", file=sys.stderr)
        return 1

    common = {**DEFAULTS["common"], **config.get("common", {})}
    expert_prefix = config.get("experts_relpath") or experts_relpath(candidates_dir)

    if args.dry_run:
        symbols = common.get("symbols")
        if not symbols:
            print(
                "error: common.symbols is required to generate Round 1 backtests",
                file=sys.stderr,
            )
            return 1
        ini_dir = output_dir / "mt5_ini"
        ini_dir.mkdir(parents=True, exist_ok=True)
        for ex5 in bots:
            expert = f"{expert_prefix}\\{ex5.name}" if expert_prefix else ex5.name
            for symbol in symbols:
                token = re.sub(r"[^A-Za-z0-9]+", "_", str(symbol)).strip("_")
                report_name = re.sub(r"[^A-Za-z0-9]+", "_", f"mt5rt_{ex5.stem}_R1_{symbol}").strip(
                    "_"
                )[:120]
                ini = build_backtest_ini(expert, str(symbol), common, report_name)
                (ini_dir / f"{ex5.stem}__R1_{token}.ini").write_text(ini, encoding="utf-8")
        count = len(bots) * len(symbols)
        print(f"[dry-run] {count} Round 1 INIs in {ini_dir}")
        print("Rounds 2 and 3 require real results; rerun without --dry-run.")
        return 0

    terminal = find_terminal(args.terminal_path, config.get("terminal_path"))
    if terminal is None:
        print(
            "error: terminal64.exe was not found. Use --terminal-path, "
            "$MT5_TERMINAL_PATH, or config.terminal_path.",
            file=sys.stderr,
        )
        return 1

    # Prevent concurrent runs: two pipelines share one MT5 data folder and would
    # collide (only one terminal instance per data folder is allowed).
    lock = shared_lock_path(candidates_dir, terminal)
    lock_handle = acquire_lock(lock)
    if lock_handle is None:
        blocker = lock_blocker_path(lock)
        detail = f" Verify MT5 and remove {blocker} manually." if blocker.exists() else ""
        print(
            f"error: MT5 data folder is locked ({lock}).{detail}",
            file=sys.stderr,
        )
        return 1

    try:
        pipe = Pipeline(config, output_dir, terminal, timeout, args.portable, args.resume)
        pipe.learn.bump_run()
        pipe.log(f"Terminal: {terminal}")
        pipe.log(f"Candidates: {candidates_dir} ({len(bots)} bots)")

        for ex5 in bots:
            try:
                pipe.process_bot(ex5)
            except TerminalTerminationError as error:
                # Block reuse first while this process still holds the OS lock.
                # Output logging/checkpointing can fail independently (for
                # example, a full output disk) and must never mask this guard.
                block_lock(lock, error)
                try:
                    pipe.log(f"[{ex5.stem}] ERROR FATAL: {error}")
                except OSError:
                    pass
                try:
                    st = pipe.state["bots"].setdefault(ex5.stem, {})
                    st.update({"status": "error", "verdict": "error", "reason": str(error)})
                    pipe._save_state()
                except OSError:
                    pass
                raise
            except Exception as e:  # keep the loop resilient; record and continue
                pipe.log(f"[{ex5.stem}] UNEXPECTED ERROR: {e}")
                st = pipe.state["bots"].setdefault(ex5.stem, {})
                st.update({"status": "error", "verdict": "error", "reason": str(e)})
                pipe._save_state()

        pipe.learn.save(markdown_path=pipe._learn_md)
        md, js = pipe.write_leaderboard()
        pipe.log(f"Leaderboard: {md}")
        pipe.log(f"Learnings:   {pipe.learn.path}")
    except TerminalTerminationError as error:
        blocker = lock_blocker_path(lock)
        if not blocker.exists():
            blocker = block_lock(lock, error)
        print(
            f"fatal error: {error}. Rerun blocked until MT5 is verified; {blocker}",
            file=sys.stderr,
        )
        return 2
    finally:
        release_lock(lock_handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
