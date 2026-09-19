#!/usr/bin/env python3
"""Check EN/JA skill-doc command parity (issue #433).

For each skill with pages under ``docs/en/skills/`` and ``docs/ja/skills/``,
every shell command in the EN page must also appear in the JA page
(directional EN-subset-JA; JA extras are allowed). Code fences that carry
data or output samples (``json``, ``text``, directory trees) are out of
scope; only ``bash``-family fences are compared.

JA pages that still carry the generator's untranslated banner are skipped.
Remaining divergences must be listed in ``ALLOWLIST`` with a reason, or
``--check`` exits 1.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN_DIR = ROOT / "docs" / "en" / "skills"
JA_DIR = ROOT / "docs" / "ja" / "skills"

UNTRANSLATED_BANNER = "has not yet been translated into Japanese"

# Tagged fences compared whole (command lines extracted, see _extract_commands).
SHELL_TAGS = {"bash", "sh", "shell", "console", "zsh"}

# Corpus audit (issue #433, 4 flipped pages): commands are `python3 ...` with
# backslash continuations. The prefix list is frozen here; unknown command
# families surface via --verbose "uncompared" output (fail-open, visible).
COMMAND_PREFIXES = ("python3",)


@dataclass
class AllowEntry:
    skill: str
    commands: list[str]
    reason: str
    issue_ref: str
    review_by: str


# Pre-existing divergences out of scope for the flipping PR (#433).
# Each entry: exact normalized EN commands that may be absent from JA.
# New divergences (commands not listed here) fail --check.
_ALLOWLIST: list[AllowEntry] = [
    AllowEntry(
        skill="backtest-expert",
        commands=[
            "python3 skills/backtest-expert/scripts/evaluate_backtest.py --total-trades 150 --win-rate 62 --avg-win-pct 1.8 --avg-loss-pct 1.2 --max-drawdown-pct 15 --years-tested 8 --num-parameters 3 --slippage-tested --output-dir reports/",
            "python3 skills/backtest-expert/scripts/evaluate_backtest.py --total-trades 25 --win-rate 88 --avg-win-pct 4.2 --avg-loss-pct 0.8 --max-drawdown-pct 8 --years-tested 2 --num-parameters 9 --output-dir reports/",
            "python3 skills/backtest-expert/scripts/evaluate_backtest.py --total-trades 85 --win-rate 48 --avg-win-pct 3.5 --avg-loss-pct 1.5 --max-drawdown-pct 22 --years-tested 5 --num-parameters 5 --output-dir reports/",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="breakout-trade-planner",
        commands=[
            "python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py --input reports/vcp_screener_2026-04-12.json --account-size 100000 --risk-pct 0.5 --current-exposure-json exposure.json --output-dir reports/",
            "python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py --input reports/vcp_screener_2026-04-12.json --account-size 50000 --risk-pct 0.25 --max-portfolio-heat-pct 3.0 --max-chase-pct 1.0 --output-dir reports/",
            "python3 skills/breakout-trade-planner/scripts/plan_breakout_trades.py --input reports/vcp_screener_2026-04-12_200418.json --account-size 100000 --risk-pct 0.5 --output-dir reports/",
            "python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir reports/",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="canslim-screener",
        commands=[
            "python3 skills/canslim-screener/scripts/screen_canslim.py --max-candidates 35 --output-dir reports/",
            "python3 skills/canslim-screener/scripts/screen_canslim.py --output-dir reports/",
            "python3 skills/canslim-screener/scripts/screen_canslim.py --universe NVDA AMD QCOM AVGO TXN INTC MU MRVL AMAT LRCX --output-dir reports/",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="dividend-growth-pullback-screener",
        commands=[
            "python3 screen_dividend_growth_rsi.py --min-yield 2.0 --min-div-growth 10.0 --max-candidates 30",
            "python3 screen_dividend_growth_rsi.py --use-finviz --fmp-api-key YOUR_FMP_KEY --finviz-api-key YOUR_FINVIZ_KEY",
            "python3 screen_dividend_growth_rsi.py --use-finviz --min-yield 2.0 --min-div-growth 15.0 --rsi-max 35",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="downtrend-duration-analyzer",
        commands=[
            'python3 skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py --sector "Technology" --lookback-years 5 --output-dir reports/',
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="exposure-coach",
        commands=[
            "python3 skills/exposure-coach/scripts/calculate_exposure.py --breadth reports/breadth_latest.json --uptrend reports/uptrend_latest.json --regime reports/regime_latest.json --top-risk reports/top_risk_latest.json --ftd reports/ftd_latest.json --theme reports/theme_latest.json --sector reports/sector_latest.json --institutional reports/institutional_latest.json --output-dir reports/",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="finviz-screener",
        commands=[
            'python3 skills/finviz-screener/scripts/open_finviz_screener.py --filters "fa_div_o3,fa_pe_u20,cap_large" --view valuation --order dividendyield --url-only',
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="fxmacrodata-calendar",
        commands=[
            "python3 skills/fxmacrodata-calendar/scripts/fetch_calendar.py --currency usd --min-tier 1",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="position-sizer",
        commands=[
            "python3 skills/position-sizer/scripts/position_sizer.py --account-size 100000 --entry 850 --atr 22.50 --atr-multiplier 2.0 --risk-pct 1.0 --output-dir reports/",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="signal-postmortem",
        commands=[
            "python3 skills/signal-postmortem/scripts/postmortem_analyzer.py --postmortems-dir reports/postmortems/ --generate-improvement-backlog --output-dir reports/",
            "python3 skills/signal-postmortem/scripts/postmortem_analyzer.py --postmortems-dir reports/postmortems/ --generate-weight-feedback --output-dir reports/",
            "python3 skills/signal-postmortem/scripts/postmortem_recorder.py --list-ready --signals-dir state/signals/ --min-days 5",
            'python3 skills/signal-postmortem/scripts/postmortem_recorder.py --signal-id sig_aapl_20260310_abc --exit-price 178.50 --exit-date 2026-03-15 --outcome-notes "Closed at target, +3.2% in 5 days" --output-dir reports/',
            "python3 skills/signal-postmortem/scripts/postmortem_analyzer.py --postmortems-dir reports/postmortems/ --summary --group-by skill,month --output-dir reports/",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="stockbee-episodic-pivot-analyzer",
        commands=[
            "python3 skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py --earnings-json reports/earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json --output-dir reports/",
            "python3 skills/stockbee-episodic-pivot-analyzer/scripts/analyze_ep.py --events-json data/catalysts.json --momentum-json reports/stockbee_momentum_burst_YYYY-MM-DD_HHMMSS.json --output-dir reports/",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="trading-skills-navigator",
        commands=[
            'python3 skills/trading-skills-navigator/scripts/recommend.py --query "<the user\'s goal, verbatim>" --format json',
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="us-market-bubble-detector",
        commands=[
            'python3 skills/us-market-bubble-detector/scripts/bubble_scorer.py --scores \'{"mass_penetration":0,"media_saturation":1,"new_accounts":0,"new_issuance":1,"leverage":1,"price_acceleration":1,"valuation_disconnect":0,"breadth_expansion":1}\' --output text',
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
    AllowEntry(
        skill="vcp-screener",
        commands=[
            "python3 skills/vcp-screener/scripts/screen_vcp.py --min-contractions 3 --breakout-volume-ratio 2.0 --trend-min-score 90 --output-dir reports/",
            "python3 skills/vcp-screener/scripts/screen_vcp.py --universe AAPL NVDA MSFT AMZN META AVGO CRM ADBE --output-dir reports/",
        ],
        reason="pre-existing hand-translation divergence; sync in a follow-up",
        issue_ref="#433",
        review_by="2026-12-31",
    ),
]


def is_allowlisted(skill: str, command: str) -> bool:
    """True when this exact missing command is a recorded pre-existing divergence."""
    for entry in _ALLOWLIST:
        if entry.skill == skill and command in entry.commands:
            return True
    return False


def _strip_inline_comment(line: str) -> str:
    """Remove a trailing ``#`` comment, respecting single/double quotes."""
    out: list[str] = []
    quote: str | None = None
    for ch in line:
        if quote is not None:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#" and out and out[-1] in (" ", "\t"):
            break
        else:
            out.append(ch)
    return "".join(out)


def _join_continuations(lines: list[str]) -> list[str]:
    """Join backslash-continued lines into logical lines."""
    logical: list[str] = []
    buf = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
        else:
            buf += line
            logical.append(buf)
            buf = ""
    if buf:
        logical.append(buf)
    return logical


def _normalize_command(line: str) -> str | None:
    """Normalize one command line; return None when not a command."""
    s = line.strip()
    if not s or s.startswith("#!"):
        return None
    if s.startswith("$"):
        rest = s[1:].lstrip()
        if not rest.startswith(COMMAND_PREFIXES):
            return None
        s = rest
    if s.startswith(">"):
        # Prompt marker only when the remainder is a known command; otherwise
        # this may be shell syntax (redirection/continuation) — keep as-is,
        # which then fails the prefix test below and is ignored.
        rest = s[1:].lstrip()
        if rest.startswith(COMMAND_PREFIXES):
            s = rest
        else:
            return None
    if s.startswith("#"):
        return None
    if not s.startswith(COMMAND_PREFIXES):
        return None
    s = _strip_inline_comment(s)
    return re.sub(r"\s+", " ", s).strip() or None


def _extract_commands(page: Path) -> tuple[Counter, list[str]]:
    """Return (command multiset, uncompared-fence notes) for shell fences."""
    text = page.read_text(encoding="utf-8")
    counter: Counter = Counter()
    uncompared: list[str] = []
    for match in re.finditer(r"```(\w*)\n(.*?)```", text, re.S):
        tag, body = match.group(1).lower(), match.group(2)
        if tag not in SHELL_TAGS:
            continue
        found = False
        for line in _join_continuations(body.splitlines()):
            cmd = _normalize_command(line)
            if cmd is not None:
                counter[cmd] += 1
                found = True
        if not found and body.strip():
            uncompared.append(
                f"{page.name}: non-command bash fence ({len(body.splitlines())} lines)"
            )
    return counter, uncompared


def check_skill(skill: str) -> list[str]:
    """Return violation messages for one skill (empty when parity holds)."""
    en = EN_DIR / f"{skill}.md"
    ja = JA_DIR / f"{skill}.md"
    if not en.is_file() or not ja.is_file():
        return []
    if UNTRANSLATED_BANNER in ja.read_text(encoding="utf-8"):
        return []
    en_cmds, _ = _extract_commands(en)
    ja_cmds, _ = _extract_commands(ja)
    violations = []
    for cmd, want in sorted(en_cmds.items()):
        have = ja_cmds.get(cmd, 0)
        if have < want:
            violations.append(f"  [{skill}] missing x{want - have}: {cmd}")
    return violations


def check_all(verbose: bool = False) -> tuple[list[str], list[str]]:
    """Check every skill pair; return (violations, uncompared notes)."""
    skills = sorted(p.stem for p in EN_DIR.glob("*.md") if p.stem != "index")
    violations: list[str] = []
    uncompared: list[str] = []
    for skill in skills:
        ja = JA_DIR / f"{skill}.md"
        if not ja.is_file():
            continue
        if UNTRANSLATED_BANNER in ja.read_text(encoding="utf-8"):
            continue
        violations.extend(check_skill(skill))
        _, notes = _extract_commands(EN_DIR / f"{skill}.md")
        uncompared.extend(notes)
    if verbose:
        for note in uncompared:
            print(f"UNCOMPARED: {note}")
    return violations, uncompared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 on non-allowlisted divergence")
    parser.add_argument("--verbose", action="store_true", help="List uncompared fences")
    parser.add_argument("--skill", default=None, help="Check a single skill only")
    args = parser.parse_args(argv)

    if args.skill:
        violations = check_skill(args.skill)
    else:
        violations, _ = check_all(verbose=args.verbose)

    effective = []
    for line in violations:
        m = re.match(r"\s*\[(.*?)\] missing x\d+: (.*)", line)
        if m and is_allowlisted(m.group(1), m.group(2)):
            continue
        effective.append(line)

    checked = args.skill or "all"
    print(
        f"PARITY: {checked} checked, {len(violations)} violations ({len(violations) - len(effective)} allowlisted)"
    )
    for line in effective:
        print(line)
    if args.check and effective:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
