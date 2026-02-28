"""Data quality checker for market analysis documents.

Validates price scales, instrument notation, date/weekday accuracy,
allocation totals, and unit consistency. Advisory mode -- flags issues
as warnings for human review.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime

SEVERITY_ORDER: dict[str, int] = {"ERROR": 0, "WARNING": 1, "INFO": 2}


@dataclass
class Finding:
    """A single data quality finding."""

    severity: str  # ERROR, WARNING, INFO
    category: str  # price_scale, notation, dates, allocations, units
    message: str
    line_number: int | None = None
    context: str | None = None

    def sort_key(self) -> tuple[int, int]:
        return (SEVERITY_ORDER.get(self.severity, 99), self.line_number or 0)


# ---------------------------------------------------------------------------
# Price Scale Check
# ---------------------------------------------------------------------------

INSTRUMENT_DIGIT_HINTS: dict[str, tuple[int, int]] = {
    "GLD": (2, 3),
    "GC": (3, 4),
    "SPY": (2, 3),
    "SPX": (4, 5),
    "VIX": (1, 2),
    "TLT": (2, 3),
    "SLV": (2, 2),
    "SI": (2, 2),
    "USO": (2, 2),
    "CL": (2, 3),
}


# Ratio-based cross-reference pairs: (ETF, futures) -> expected_ratio (futures / ETF)
SCALE_RATIOS: dict[tuple[str, str], float] = {
    ("GLD", "GC"): 15,
    ("SLV", "SI"): 2.3,
    ("USO", "CL"): 0.85,
    ("SPY", "SPX"): 10,
}


def _extract_instrument_prices(content: str) -> dict[str, list[tuple[float, int]]]:
    """Extract all (price, line_number) mentions for each known instrument."""
    mentions: dict[str, list[tuple[float, int]]] = {}

    tickers = sorted(INSTRUMENT_DIGIT_HINTS.keys(), key=len, reverse=True)
    ticker_alt = "|".join(re.escape(t) for t in tickers)
    ticker_pat = re.compile(
        r"(?:^|[\s(])"
        r"(" + ticker_alt + r")"
        r"(?:[)\s:,])",
    )

    for tmatch in ticker_pat.finditer(content):
        instrument = tmatch.group(1)
        rest = content[tmatch.end() - 1 : tmatch.end() + 80]
        price_m = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", rest)
        if not price_m:
            continue
        price_str = price_m.group(1).replace(",", "")
        try:
            price = float(price_str)
        except ValueError:
            continue
        if price <= 0:
            continue
        line_num = content[: tmatch.start()].count("\n") + 1
        mentions.setdefault(instrument, []).append((price, line_num))

    return mentions


def check_price_scale(content: str) -> list[Finding]:
    """Check for price scale inconsistencies using digit heuristics and ratio analysis."""
    findings: list[Finding] = []
    mentions = _extract_instrument_prices(content)

    # --- Digit count heuristics ---
    for instrument, price_list in mentions.items():
        min_digits, max_digits = INSTRUMENT_DIGIT_HINTS[instrument]
        for price, line_num in price_list:
            digit_count = len(str(int(price)))
            if digit_count < min_digits or digit_count > max_digits:
                findings.append(
                    Finding(
                        severity="WARNING",
                        category="price_scale",
                        message=(
                            f"{instrument}: ${price:,.2f} has {digit_count} digits "
                            f"(expected {min_digits}-{max_digits} digits)"
                        ),
                        line_number=line_num,
                    )
                )

    # --- Ratio-based cross-reference ---
    # Check every pair of (etf_mention, futures_mention) to catch later mismatches.
    for (etf, futures), expected_ratio in SCALE_RATIOS.items():
        if etf not in mentions or futures not in mentions:
            continue
        for etf_price, etf_line in mentions[etf]:
            if etf_price <= 0:
                continue
            for futures_price, futures_line in mentions[futures]:
                actual_ratio = futures_price / etf_price
                if abs(actual_ratio - expected_ratio) / expected_ratio > 0.5:
                    findings.append(
                        Finding(
                            severity="WARNING",
                            category="price_scale",
                            message=(
                                f"Price scale ratio mismatch: {futures}/${etf} = "
                                f"{actual_ratio:.1f}x (expected ~{expected_ratio}x). "
                                f"Possible ETF/futures price mix-up."
                            ),
                            line_number=min(etf_line, futures_line),
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# Notation Check
# ---------------------------------------------------------------------------

NOTATION_GROUPS: dict[str, list[str]] = {
    "gold": ["Gold", "GLD", "GC", "金", "金先物", "ゴールド"],
    "sp500": ["S&P 500", "S&P500", "SPX", "SPY", "SP500"],
    "oil": ["WTI", "Crude", "CL", "USO", "原油"],
    "silver": ["Silver", "SLV", "SI", "銀"],
    "bonds": ["TLT", "10Y", "10年債", "米国債"],
    "vix": ["VIX", "恐怖指数"],
}


def check_notation(content: str) -> list[Finding]:
    """Check for inconsistent instrument notation within the same document."""
    findings: list[Finding] = []

    for group_name, variants in NOTATION_GROUPS.items():
        found: list[str] = []
        for v in variants:
            # Use case-insensitive only for longer terms to avoid false positives
            flags = re.IGNORECASE if len(v) > 3 else 0
            pattern = re.compile(r"(?<!\w)" + re.escape(v) + r"(?!\w)", flags)
            if pattern.search(content):
                found.append(v)
        if len(found) > 1:
            findings.append(
                Finding(
                    severity="WARNING",
                    category="notation",
                    message=(
                        f"Mixed notation for {group_name}: {', '.join(found)}. "
                        f"Consider using a consistent term."
                    ),
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Date Check
# ---------------------------------------------------------------------------

WEEKDAY_MAP_EN: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

WEEKDAY_MAP_JA: dict[str, int] = {
    "月": 0,
    "火": 1,
    "水": 2,
    "木": 3,
    "金": 4,
    "土": 5,
    "日": 6,
}

MONTH_MAP: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _resolve_en_weekday(weekday_str: str) -> int | None:
    """Resolve an English weekday string to a weekday number (Monday=0)."""
    lower = weekday_str.lower()
    # Try exact match first
    if lower in WEEKDAY_MAP_EN:
        return WEEKDAY_MAP_EN[lower]
    # Try 3-char prefix match
    prefix = lower[:3]
    for name, val in WEEKDAY_MAP_EN.items():
        if name == prefix:
            return val
    return None


def infer_year(
    month: int,
    day: int,
    as_of: date | None,
    content: str,
    filepath: str | None = None,
) -> int:
    """Infer year for dates without explicit year.

    Priority:
    1. --as-of option
    2. Year from document content
    3. Year from filename (YYYY-MM-DD pattern)
    4. Fallback: current year
    """
    if as_of is not None:
        candidate = as_of.year
        # Calculate month difference
        diff_months = month - as_of.month
        if diff_months < -6:
            return candidate + 1
        if diff_months > 6:
            return candidate - 1
        return candidate

    # Search document for a 4-digit year (2020-2039)
    year_match = re.search(r"(?:^|\D)(20[2-3]\d)(?:\D|$)", content)
    if year_match:
        return int(year_match.group(1))

    # Search filename for YYYY-MM-DD pattern
    if filepath:
        fname_match = re.search(r"(20[2-3]\d)-\d{2}-\d{2}", filepath)
        if fname_match:
            return int(fname_match.group(1))

    # Fallback to current year
    return date.today().year


def check_dates(
    content: str, as_of: date | None = None, filepath: str | None = None
) -> list[Finding]:
    """Check date-weekday mismatches in English and Japanese content."""
    findings: list[Finding] = []

    # ---- English with year: "February 28, 2026 (Friday)" ----
    en_year_pat = re.compile(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})\s*\((\w+)\)", re.IGNORECASE)
    en_year_spans: list[tuple[int, int]] = []

    for m in en_year_pat.finditer(content):
        month_str = m.group(1)
        day_str = m.group(2)
        year_str = m.group(3)
        weekday_str = m.group(4)

        month = MONTH_MAP.get(month_str.lower())
        if not month:
            continue

        try:
            d = date(int(year_str), month, int(day_str))
        except ValueError:
            continue

        en_year_spans.append((m.start(), m.end()))

        actual_weekday = d.weekday()
        stated_weekday = _resolve_en_weekday(weekday_str)

        if stated_weekday is not None and stated_weekday != actual_weekday:
            line_num = content[: m.start()].count("\n") + 1
            actual_name = calendar.day_name[actual_weekday]
            findings.append(
                Finding(
                    severity="ERROR",
                    category="dates",
                    message=(
                        f"Date-weekday mismatch: {m.group(0).strip()} "
                        f"-- actual weekday is {actual_name}"
                    ),
                    line_number=line_num,
                )
            )

    # ---- English without year: "Feb 28 (Fri)" or "January 15 (Wed)" ----
    en_no_year_pat = re.compile(r"(\w+)\s+(\d{1,2})\s*\((\w+)\)", re.IGNORECASE)

    for m in en_no_year_pat.finditer(content):
        # Skip if overlapping with a year-pattern match
        overlaps = False
        for ys, ye in en_year_spans:
            if not (m.end() <= ys or m.start() >= ye):
                overlaps = True
                break
        if overlaps:
            continue

        month_str = m.group(1)
        day_str = m.group(2)
        weekday_str = m.group(3)

        month = MONTH_MAP.get(month_str.lower())
        if not month:
            continue

        # Check for year immediately before this match
        before = content[max(0, m.start() - 10) : m.start()]
        if re.search(r"\d{4}\s*$", before):
            continue

        year = infer_year(month, int(day_str), as_of, content, filepath)
        try:
            d = date(year, month, int(day_str))
        except ValueError:
            continue

        actual_weekday = d.weekday()
        stated_weekday = _resolve_en_weekday(weekday_str)

        if stated_weekday is not None and stated_weekday != actual_weekday:
            line_num = content[: m.start()].count("\n") + 1
            actual_name = calendar.day_name[actual_weekday]
            findings.append(
                Finding(
                    severity="ERROR",
                    category="dates",
                    message=(
                        f"Date-weekday mismatch: {m.group(0).strip()} "
                        f"-- actual weekday is {actual_name} "
                        f"(inferred year: {year})"
                    ),
                    line_number=line_num,
                )
            )

    # ---- Japanese: "1月1日（木）" or "1月1日（木曜日）" ----
    ja_pat = re.compile(r"(\d{1,2})月(\d{1,2})日[（(]([月火水木金土日])(?:曜日)?[）)]")
    for m in ja_pat.finditer(content):
        month_val = int(m.group(1))
        day_val = int(m.group(2))
        weekday_char = m.group(3)

        year = infer_year(month_val, day_val, as_of, content, filepath)
        try:
            d = date(year, month_val, day_val)
        except ValueError:
            continue

        actual_weekday = d.weekday()
        stated_weekday = WEEKDAY_MAP_JA.get(weekday_char)

        if stated_weekday is not None and stated_weekday != actual_weekday:
            ja_names = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
            line_num = content[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    severity="WARNING",
                    category="dates",
                    message=(
                        f"Date-weekday mismatch: {m.group(0)} "
                        f"-- actual weekday is {ja_names[actual_weekday]} "
                        f"(inferred year: {year})"
                    ),
                    line_number=line_num,
                )
            )

    # ---- Japanese slash format: "1/1(木)" ----
    ja_slash_pat = re.compile(r"(\d{1,2})/(\d{1,2})[（(]([月火水木金土日])[）)]")
    for m in ja_slash_pat.finditer(content):
        month_val = int(m.group(1))
        day_val = int(m.group(2))
        weekday_char = m.group(3)

        year = infer_year(month_val, day_val, as_of, content, filepath)
        try:
            d = date(year, month_val, day_val)
        except ValueError:
            continue

        actual_weekday = d.weekday()
        stated_weekday = WEEKDAY_MAP_JA.get(weekday_char)

        if stated_weekday is not None and stated_weekday != actual_weekday:
            ja_names = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
            line_num = content[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    severity="WARNING",
                    category="dates",
                    message=(
                        f"Date-weekday mismatch: {m.group(0)} "
                        f"-- actual weekday is {ja_names[actual_weekday]} "
                        f"(inferred year: {year})"
                    ),
                    line_number=line_num,
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Allocation Check
# ---------------------------------------------------------------------------

ALLOCATION_HEADING_KEYWORDS: list[str] = [
    "配分",
    "アロケーション",
    "allocation",
    "セクター配分",
    "asset allocation",
]

ALLOCATION_TABLE_KEYWORDS: list[str] = [
    "配分",
    "allocation",
    "ウェイト",
    "weight",
    "比率",
    "ratio",
    "目安比率",
]


def find_allocation_sections(content: str) -> list[str]:
    """Find sections that are allocation-related."""
    sections: list[str] = []
    lines = content.split("\n")

    # ---- Heading-based sections ----
    for i, line in enumerate(lines):
        if not re.match(r"^#{1,6}\s", line):
            continue
        heading_text = re.sub(r"^#{1,6}\s+", "", line).strip().lower()
        # Skip ポジション alone (without 配分)
        if "ポジション" in heading_text and "配分" not in heading_text:
            continue
        if any(kw.lower() in heading_text for kw in ALLOCATION_HEADING_KEYWORDS):
            section_lines: list[str] = []
            for j in range(i + 1, len(lines)):
                if re.match(r"^#{1,6}\s", lines[j]):
                    break
                section_lines.append(lines[j])
            sections.append("\n".join(section_lines))

    # ---- Table-based allocations ----
    in_table = False
    table_lines: list[str] = []
    header_line = ""

    for line in lines:
        stripped = line.strip()
        if "|" in stripped and not in_table:
            # Potential table header
            header_line = stripped
            in_table = True
            table_lines = [stripped]
        elif in_table and "|" in stripped:
            table_lines.append(stripped)
        else:
            if in_table and table_lines:
                if any(kw.lower() in header_line.lower() for kw in ALLOCATION_TABLE_KEYWORDS):
                    sections.append("\n".join(table_lines))
                in_table = False
                table_lines = []
                header_line = ""

    # Handle table at end of content
    if in_table and table_lines:
        if any(kw.lower() in header_line.lower() for kw in ALLOCATION_TABLE_KEYWORDS):
            sections.append("\n".join(table_lines))

    return sections


def extract_percentage_values(
    section: str,
) -> list[tuple[float, float]]:
    """Extract percentage values from a section.

    Returns list of (min, max) tuples.
    Fixed value "20%" -> (20, 20). Range "20-25%" or "20~25%" -> (20, 25).
    """
    values: list[tuple[float, float]] = []

    # Normalize full-width characters
    normalized = section
    normalized = normalized.replace("\uff05", "%")  # ％ -> %
    normalized = normalized.replace("\u301c", "~")  # 〜 -> ~
    normalized = normalized.replace("\u2013", "-")  # en-dash -> -
    normalized = normalized.replace("\u2014", "-")  # em-dash -> -

    # Range pattern: "50-55%" or "50~55%"
    range_pat = re.compile(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)\s*%")
    # Single value: "50%"
    single_pat = re.compile(r"(\d+(?:\.\d+)?)\s*%")

    # Find ranges first and record their spans
    range_spans: list[tuple[int, int]] = []
    for m in range_pat.finditer(normalized):
        low, high = float(m.group(1)), float(m.group(2))
        values.append((low, high))
        range_spans.append((m.start(), m.end()))

    # Find single values not overlapping with ranges
    for m in single_pat.finditer(normalized):
        overlaps = False
        for rs, re_ in range_spans:
            if rs <= m.start() < re_ or rs < m.end() <= re_:
                overlaps = True
                break
        if not overlaps:
            val = float(m.group(1))
            values.append((val, val))

    return values


def check_allocations(content: str) -> list[Finding]:
    """Check allocation totals in allocation sections only."""
    findings: list[Finding] = []
    sections = find_allocation_sections(content)

    for section in sections:
        values = extract_percentage_values(section)
        if not values or len(values) < 2:
            continue

        sum_mins = sum(v[0] for v in values)
        sum_maxs = sum(v[1] for v in values)

        if abs(sum_mins - sum_maxs) < 0.01:
            # Fixed values only
            if abs(sum_mins - 100) > 0.5:
                findings.append(
                    Finding(
                        severity="WARNING",
                        category="allocations",
                        message=f"Allocation total: {sum_mins}% (expected ~100%)",
                    )
                )
        else:
            # Range notation: check if 100% is contained in [sum_mins, sum_maxs]
            if sum_mins > 100.5 or sum_maxs < 99.5:
                findings.append(
                    Finding(
                        severity="WARNING",
                        category="allocations",
                        message=(
                            f"Allocation range [{sum_mins}%-{sum_maxs}%] does not contain 100%"
                        ),
                    )
                )

    return findings


# ---------------------------------------------------------------------------
# Unit Check
# ---------------------------------------------------------------------------

# Pattern for standalone numeric values near financial instrument names
# that lack a unit ($ or % or bp)
_INSTRUMENT_WORDS = re.compile(
    r"\b(Gold|Silver|Oil|Crude|WTI|SPY|SPX|VIX|GLD|GC|TLT|SLV|USO|CL|SI)\b",
    re.IGNORECASE,
)
_MOVEMENT_WORDS = re.compile(
    r"\b(moved|rose|fell|dropped|gained|lost|up|down|changed|increased|decreased)\b",
    re.IGNORECASE,
)
_BARE_NUMBER = re.compile(r"\b(\d+(?:\.\d+)?)\b")
_HAS_UNIT = re.compile(r"(\$\d|\d\s*%|\d\s*bp|\d\s*bps)", re.IGNORECASE)


def check_units(content: str) -> list[Finding]:
    """Check for missing or mixed units."""
    findings: list[Finding] = []

    # Check for mixed bp and % for rates/yields
    has_bp = bool(re.search(r"\d+\s*bp", content, re.IGNORECASE))
    has_pct_rate = bool(
        re.search(
            r"(?:yield|rate|利回り|金利).*?\d+(?:\.\d+)?%",
            content,
            re.IGNORECASE,
        )
    )
    if has_bp and has_pct_rate:
        findings.append(
            Finding(
                severity="INFO",
                category="units",
                message=("Mixed use of basis points (bp) and percentage (%) for rates/yields"),
            )
        )

    # Check for bare numbers near instrument + movement words without units
    for line_idx, line in enumerate(content.split("\n"), 1):
        if _INSTRUMENT_WORDS.search(line) and _MOVEMENT_WORDS.search(line):
            if _BARE_NUMBER.search(line) and not _HAS_UNIT.search(line):
                findings.append(
                    Finding(
                        severity="WARNING",
                        category="units",
                        message=(f"Possible missing unit in: {line.strip()!r}"),
                        line_number=line_idx,
                    )
                )

    return findings


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

ALL_CHECKS = {
    "price_scale": check_price_scale,
    "notation": check_notation,
    "dates": check_dates,
    "allocations": check_allocations,
    "units": check_units,
}


def run_checks(
    content: str,
    checks: list[str] | None = None,
    as_of: date | None = None,
    filepath: str | None = None,
) -> list[Finding]:
    """Run specified checks (or all) on content."""
    if checks is None:
        checks = list(ALL_CHECKS.keys())

    all_findings: list[Finding] = []
    for check_name in checks:
        func = ALL_CHECKS.get(check_name)
        if not func:
            continue
        if check_name == "dates":
            all_findings.extend(func(content, as_of, filepath))
        else:
            all_findings.extend(func(content))

    all_findings.sort(key=lambda f: f.sort_key())
    return all_findings


def generate_report(findings: list[Finding], source_file: str) -> str:
    """Generate a markdown report of findings."""
    lines = [
        "# Data Quality Report",
        f"**Source:** {source_file}",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total findings:** {len(findings)}",
        "",
    ]

    if not findings:
        lines.append("No issues found.")
        return "\n".join(lines) + "\n"

    # Group by severity
    for severity in ["ERROR", "WARNING", "INFO"]:
        sevs = [f for f in findings if f.severity == severity]
        if sevs:
            lines.append(f"## {severity} ({len(sevs)})")
            for f in sevs:
                loc = f" (line {f.line_number})" if f.line_number else ""
                lines.append(f"- **[{f.category}]**{loc}: {f.message}")
                if f.context:
                    lines.append(f"  > `{f.context}`")
            lines.append("")

    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate data quality in market analysis documents"
    )
    parser.add_argument("--file", required=True, help="Path to markdown file to check")
    parser.add_argument(
        "--checks",
        help="Comma-separated list of checks to run (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/",
        help="Output directory for reports",
    )
    parser.add_argument(
        "--as-of",
        help="Reference date for year inference (YYYY-MM-DD)",
    )
    return parser


def main() -> None:
    """Entry point for CLI usage."""
    parser = build_parser()
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    with open(args.file, encoding="utf-8") as f:
        content = f.read()

    checks = [c.strip() for c in args.checks.split(",")] if args.checks else None
    as_of_date: date | None = None
    if args.as_of:
        try:
            as_of_date = date.fromisoformat(args.as_of)
        except ValueError:
            print(f"Error: Invalid date format: {args.as_of}", file=sys.stderr)
            sys.exit(1)

    findings = run_checks(content, checks, as_of_date, filepath=args.file)

    # Always exit 0 (advisory mode) unless script error
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # JSON output
    json_path = os.path.join(args.output_dir, f"data_quality_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(
            [asdict(f) for f in findings],
            jf,
            indent=2,
            ensure_ascii=False,
        )
    print(f"JSON report: {json_path}")

    # Markdown output
    report = generate_report(findings, args.file)
    md_path = os.path.join(args.output_dir, f"data_quality_{timestamp}.md")
    with open(md_path, "w", encoding="utf-8") as mf:
        mf.write(report)
    print(f"Markdown report: {md_path}")

    # Summary
    if findings:
        errors = sum(1 for f in findings if f.severity == "ERROR")
        warnings = sum(1 for f in findings if f.severity == "WARNING")
        infos = sum(1 for f in findings if f.severity == "INFO")
        print(f"\nFindings: {errors} errors, {warnings} warnings, {infos} info")
    else:
        print("\nNo issues found.")


if __name__ == "__main__":
    main()
