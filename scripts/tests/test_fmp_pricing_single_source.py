"""Guard: FMP prices and paid-plan limits live only in the dated getting-started note.

Issue #666. The single note is the ``fmp-plans`` section of
``docs/en/getting-started.md`` and its Japanese translation
``docs/ja/getting-started.md`` (the EN/JA pair counts as one note). Everywhere
else, docs, SKILL.md files, references and CLAUDE.md must not copy FMP prices or
paid-plan rate limits, because they go stale when FMP changes its plans.

Correct free-plan statements ("250 calls/day") and per-run call budgets are fine.

Known limits of the matcher (accepted, not bugs):
- Rarer unit spellings are not recognised, e.g. "req/min", "calls/sec", "per hour",
  "each month", "29 dollars", "月$29".
- The vendor/plan attribution window (``SUBJECT_WINDOW``, 40 characters) is a
  heuristic, so lines whose price sits near the window boundary may be misjudged.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

NOTE_PAGES = ("docs/en/getting-started.md", "docs/ja/getting-started.md")
NOTE_ANCHOR = "{: #fmp-plans }"
PLANS = ("Basic", "Starter", "Premium", "Ultimate")

# Generic words such as "Build" and "Basic" are not plan subjects for prices; "Basic"
# only counts in limit claims that carry an explicit call/request unit.
TIER = r"(?:Starter|Premium\+?|Ultimate|Professional|Enterprise|(?i:paid (?:tier|plan)))"
# Letter lookarounds instead of \b so "Starterは" (no space before Japanese) matches.
TIER_RE = re.compile(rf"(?<![A-Za-z]){TIER}(?![A-Za-z])")
# "FMP free" names the free plan and "250 FMP requests" is a quantity; neither is a
# priced subject.
FMP = re.compile(r"(?i:(?<!\d )\bFMP\b(?!\s+free)|financial ?modeling ?prep)")
OTHER_VENDOR = re.compile(r"(?i)finviz|elite|alpaca|polygon|intrinio|alpha vantage")
DOLLAR = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|ドル)"
    r"|\bUSD\s?\d[\d,]*(?:\.\d+)?"
)
PERIOD = re.compile(
    r"(?i)/\s?(?:mo|month|yr|year)\b|/月|/年|月額|年額"
    r"|\b(?:a|per) month\b|\bmonthly\b"
)
# A price is attributed to the vendor/plan word nearest to it, within this window.
SUBJECT_WINDOW = 40

LIMIT_PERIOD = r"(?:/|\s+per\s+|\s*a\s+)\s*(?:day|日|min(?:ute)?s?|分)"
# Paid-tier limit claims such as "Premium = 750-2500 calls/day" or "Starter 300 calls/minute".
TIER_LIMIT = re.compile(
    # With an explicit call/request unit (also for "Basic").
    rf"(?<![A-Za-z])(?:{TIER}|Basic)(?![A-Za-z])[^\n]{{0,60}}?\d[\d,]*(?:-\d[\d,]*)?[ -]*"
    rf"(?:API )?(?:calls?|requests?|回)\s*{LIMIT_PERIOD}"
    rf"|(?<![A-Za-z]){TIER}(?![A-Za-z])[^\n]{{0,20}}?(?:1日|毎日)\s*\d[\d,]*\s*回"
    r"|daily plan limit"
)
# Unit-less "750/min" only counts for a plan word on a line that also names FMP.
TIER_LIMIT_UNITLESS = re.compile(
    rf"(?<![A-Za-z]){TIER}(?![A-Za-z])[^\n]{{0,60}}?\d[\d,]*\s*/\s*(?:day|日|min(?:ute)?s?|分)"
)

# Plan-name table rows that carry numeric limits, e.g. "| Starter | 500 | 10 |".
TIER_TABLE_ROW = re.compile(
    r"^\|\s*(?:Starter|Premium\+?|Ultimate|Professional|Enterprise)\s*\|[^|]*\d"
)

# (path, substring, reason). Only lines containing the substring are tolerated.
ALLOWLIST = (
    (
        "skills/us-undervalued-growth-screener/references/full-universe-snapshot.md",
        "daily plan limit",
        "Shard schedule is sized to a 750-call daily limit; changing it is a design"
        " decision tracked in follow-up issue #750, not a pricing-copy fix.",
    ),
)


def _price_attributed_to_fmp(line: str) -> bool:
    subjects = [(m.start(), m.end(), "fmp") for m in TIER_RE.finditer(line)]
    subjects += [(m.start(), m.end(), "fmp") for m in FMP.finditer(line)]
    subjects += [(m.start(), m.end(), "other") for m in OTHER_VENDOR.finditer(line)]
    for price in DOLLAR.finditer(line):
        near = [
            (min(abs(price.start() - e), abs(s - price.end())), kind)
            for s, e, kind in subjects
            if min(abs(price.start() - e), abs(s - price.end())) <= SUBJECT_WINDOW
        ]
        if not near:
            continue
        if min(near)[1] != "fmp":
            continue
        lo, hi = max(0, price.start() - SUBJECT_WINDOW), price.end() + SUBJECT_WINDOW
        if PERIOD.search(line, lo, hi):
            return True
    return False


def line_violation(line: str) -> str | None:
    """Return 'price' or 'limit' if the line copies an FMP price or paid limit."""
    if _price_attributed_to_fmp(line):
        return "price"
    if (
        TIER_LIMIT.search(line)
        or TIER_TABLE_ROW.search(line)
        or (FMP.search(line) and TIER_LIMIT_UNITLESS.search(line))
    ):
        return "limit"
    return None


def note_section_range(lines: list[str]) -> tuple[int, int] | None:
    """Return the 0-based [start, end) line range of the fmp-plans section."""
    for i, line in enumerate(lines):
        if line.strip() == NOTE_ANCHOR and i > 0:
            heading = re.match(r"(#+)\s", lines[i - 1])
            if not heading:
                continue
            level = len(heading.group(1))
            end = len(lines)
            for j in range(i + 1, len(lines)):
                m = re.match(r"(#+)\s", lines[j])
                if m and len(m.group(1)) <= level:
                    end = j
                    break
            return i - 1, end
    return None


def find_violations(path: str, text: str) -> list[str]:
    lines = text.splitlines()
    exempt = note_section_range(lines) if path in NOTE_PAGES else None
    out = []
    for idx, line in enumerate(lines):
        if exempt and exempt[0] <= idx < exempt[1]:
            continue
        kind = line_violation(line)
        if not kind:
            continue
        if any(path == p and sub in line for p, sub, _ in ALLOWLIST):
            continue
        out.append(f"{kind} {path}:{idx + 1}: {line.strip()[:120]}")
    return out


def in_scan_scope(path: str) -> bool:
    """Whether a repo-relative path is scanned for copied FMP prices."""
    if path.startswith("examples/") or path == "CHANGELOG.md":
        return False
    in_scope = path.startswith(("skills/", "docs/")) or path in {
        "CLAUDE.md",
        "README.md",
        "README.ja.md",
        "skills-index.yaml",
    }
    return in_scope and path.endswith((".md", ".yaml"))


def tracked_scan_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in result.stdout.splitlines() if in_scan_scope(p) and (REPO_ROOT / p).is_file()]


# --------------------------------------------------------------------------
# Matcher unit tests
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "- Starter tier ($29.99/mo): 750 calls/day",
        "- **Starter ($14/month)**: 500 requests/day",
        "- **Enterprise ($99/month)**: 10,000 requests/day",
        "Upgrade to paid tier ($14/month for 500 requests/day)",
        "| Starter | $29/月 | 300回/分 |",
        "- **Rate Limiting**: Free tier = 250 calls/day, Premium = 750-2500 calls/day",
        "Operating on the FMP Starter plan, the 750-call daily plan limit applies",
        "FMP costs $99/month for the top plan",
        "| Professional | 1,000+ | 20+ |",
        # Per-minute limits for paid tiers (the note's own correct values).
        "Premium: 750 calls/min",
        "Starter tier gives 300 requests/minute",
        "Ultimate tier: 3,000 calls per min",
        "Upgrade to FMP Premium (750/min)",
        "Use the Starter plan's 300 calls/minute",
        "FMP's paid plan is 300 requests per minute",
        "Premium は 750 回/分 まで使えます",
        # Other price phrasings.
        "Starter plan costs $29 a month",
        "FMP Starter: $29.99 monthly",
        "FMP Starter at $29.99, billed monthly",
        "FMP Starter plan is 29.99 USD/month",
        "FMP Starter は月額 $29 です",
        "FMP Starter $29/月",
        "FMP Starter $29.99/mo",
        "Starterは1日750回",
        # Mixed-vendor lines: the other vendor must not hide the FMP price.
        "FINVIZ Elite $39.50/mo; FMP Starter $29/mo",
        "FMP Starter $29/mo (vs Alpaca free)",
    ],
)
def test_matcher_flags_copied_prices_and_paid_limits(line):
    assert line_violation(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "Free tier: 250 calls/day is enough for 35 stocks",
        "FINVIZ Elite ($39.50/mo) speeds up screening",
        "FINVIZ Elite $40/month + FMP free tier is cheaper",
        "- **FINVIZ Elite + FMP Free** ($40/month, 250 FMP requests): ~30 stocks/day",
        "Filter by market cap > $2B using FMP data",
        "Sell a call and collect a $3.50 premium per share",
        "Position size $25,000 per the trading plan",
        "Budget about 283 calls per run",
        "Open the FMP pricing page in a browser for current plans",
        "Alpaca paper trading is free; FMP free tier gives 250 calls/day",
        # Generic words that are also plan names must not trigger on ordinary prose.
        "Basic position size 5 per day",
        "Build 3 calls per day max",
        "Build a $25,000 position per month",
        "Premium decay of 5 per day on the short call",
        "Collect the premium of $3.50 per month on the covered call",
    ],
)
def test_matcher_ignores_free_tier_budgets_and_other_vendors(line):
    assert line_violation(line) is None


NOTE_FIXTURE = """# Page

## FMP plans (as of 2026-11)
{: #fmp-plans }

| Starter | $29/month | 300 |

### Sub heading

| Premium | $69/month | 750 |

## Next section

Upgrade to FMP Starter ($29/month).
"""


def test_price_inside_note_section_is_exempt_only_for_note_pages():
    note = find_violations("docs/en/getting-started.md", NOTE_FIXTURE)
    assert len(note) == 1
    assert note[0].startswith("price docs/en/getting-started.md:14:")
    other = find_violations("docs/en/skills/x.md", NOTE_FIXTURE)
    assert len(other) == 3


def test_note_section_range_ends_at_same_level_heading():
    lines = NOTE_FIXTURE.splitlines()
    start, end = note_section_range(lines)
    assert lines[start].startswith("## FMP plans")
    assert lines[end] == "## Next section"


def test_allowlist_tolerates_only_the_listed_substring():
    path = ALLOWLIST[0][0]
    assert find_violations(path, "the 750-call daily plan limit") == []
    assert find_violations(path, "FMP Starter ($29/month)") != []
    assert "#750" in ALLOWLIST[0][2]


# --------------------------------------------------------------------------
# Repo scan scope and result
# --------------------------------------------------------------------------


def test_scan_scope_covers_all_documented_locations():
    files = set(tracked_scan_files())
    for required in ("CLAUDE.md", "README.md", "README.ja.md", "skills-index.yaml"):
        assert required in files, f"{required} must be scanned"
    assert any(f.startswith("skills/") and f.endswith(".md") for f in files)
    assert any(f.startswith("docs/") and f.endswith(".md") for f in files)
    assert "docs/en/getting-started.md" in files and "docs/ja/getting-started.md" in files
    assert not any(f.startswith("examples/") or f == "CHANGELOG.md" for f in files)


def test_scan_scope_excludes_examples_and_includes_docs():
    line = "Starter tier ($29.99/mo): 750 calls/day"
    assert line_violation(line) is not None
    assert not in_scan_scope("examples/weekly-trade-strategy/blog.md")
    assert not in_scan_scope("CHANGELOG.md")
    assert in_scan_scope("docs/en/skills/canslim-screener.md")
    assert in_scan_scope("skills/canslim-screener/SKILL.md")


def test_no_fmp_prices_or_paid_limits_outside_the_dated_note():
    hits: list[str] = []
    for path in tracked_scan_files():
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        hits.extend(find_violations(path, text))
    assert not hits, (
        "FMP prices / paid-plan limits must live only in the fmp-plans section of "
        "docs/{en,ja}/getting-started.md. Link to it instead:\n" + "\n".join(hits)
    )


# --------------------------------------------------------------------------
# The note itself: EN/JA must carry the same values per plan
# --------------------------------------------------------------------------


def _note_section(path: str) -> list[str]:
    lines = (REPO_ROOT / path).read_text(encoding="utf-8").splitlines()
    rng = note_section_range(lines)
    assert rng is not None, f"{path} is missing a heading followed by {NOTE_ANCHOR}"
    return lines[rng[0] : rng[1]]


def plan_numbers(section: list[str]) -> dict[str, list[str]]:
    """Map plan name -> numbers in its table row, in column order."""
    out: dict[str, list[str]] = {}
    for line in section:
        if not line.startswith("|"):
            continue
        first_cell = line.split("|")[1]
        for plan in PLANS:
            if plan in first_cell:
                out[plan] = re.findall(r"\d[\d,]*(?:\.\d+)?", "|".join(line.split("|")[2:]))
    return out


def date_stamp_numbers(section: list[str]) -> list[str]:
    return [
        n
        for line in section
        if "as of" in line.lower() or "時点" in line
        for n in re.findall(r"\d[\d,]*", line)
    ]


def note_differences(en: list[str], ja: list[str]) -> list[str]:
    """Return human-readable EN/JA differences: per-plan numbers, plans, date stamp."""
    en_plans, ja_plans = plan_numbers(en), plan_numbers(ja)
    diffs = []
    for plan in PLANS:
        if (plan in en_plans) != (plan in ja_plans):
            where = "JA" if plan in en_plans else "EN"
            diffs.append(f"{plan}: row missing in {where}")
        elif plan in en_plans and en_plans[plan] != ja_plans[plan]:
            diffs.append(f"{plan}: EN {en_plans[plan]} != JA {ja_plans[plan]}")
    if date_stamp_numbers(en) != date_stamp_numbers(ja):
        diffs.append(f"date stamp: EN {date_stamp_numbers(en)} != JA {date_stamp_numbers(ja)}")
    return diffs


def test_note_exists_with_the_four_plans_and_stamp_in_both_languages():
    for path in NOTE_PAGES:
        section = _note_section(path)
        assert set(plan_numbers(section)) == set(PLANS), f"{path} note must have a row per plan"
        assert "2026-11" in "\n".join(section)
        assert date_stamp_numbers(section), f"{path} note needs an as-of stamp"


def test_en_and_ja_note_carry_the_same_numbers_per_plan():
    en, ja = (_note_section(p) for p in NOTE_PAGES)
    assert note_differences(en, ja) == []


EN_FIXTURE = [
    "#### FMP plans (as of 2026-11)",
    "| Starter | $29/month | 300 |",
    "| Premium | $69/month | 750 |",
]
JA_FIXTURE = [
    "#### FMP プラン（2026-11 時点）",
    "| Starter | $29/月 | 300 |",
    "| Premium | $69/月 | 750 |",
]


def test_note_differences_is_empty_for_a_matching_pair():
    assert note_differences(EN_FIXTURE, JA_FIXTURE) == []


def test_note_differences_reports_swapped_prices():
    ja = [JA_FIXTURE[0], "| Starter | $69/月 | 750 |", "| Premium | $29/月 | 300 |"]
    diffs = note_differences(EN_FIXTURE, ja)
    assert any(d.startswith("Starter:") for d in diffs)
    assert any(d.startswith("Premium:") for d in diffs)


def test_note_differences_reports_a_missing_plan():
    ja = JA_FIXTURE[:2]
    assert note_differences(EN_FIXTURE, ja) == ["Premium: row missing in JA"]
    assert note_differences(ja, EN_FIXTURE) == ["Premium: row missing in EN"]


def test_note_differences_reports_a_different_date_stamp():
    ja = ["#### FMP プラン（2026-12 時点）", *JA_FIXTURE[1:]]
    diffs = note_differences(EN_FIXTURE, ja)
    assert len(diffs) == 1 and diffs[0].startswith("date stamp:")
