#!/usr/bin/env python3
"""Build a FinViz screener URL from filter codes and open it in Chrome.

Usage:
    python3 open_finviz_screener.py --filters "cap_small,fa_div_o3,fa_pe_u20" --url-only
    python3 open_finviz_screener.py --filters "cap_small,fa_div_o3" --view valuation
    python3 open_finviz_screener.py --filters "cap_small,fa_div_o3" --elite
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import webbrowser

# View type name -> code mapping
VIEW_CODES: dict[str, str] = {
    "overview": "111",
    "valuation": "121",
    "ownership": "131",
    "performance": "141",
    "custom": "152",
    "financial": "161",
    "technical": "171",
}

# Known filter prefixes (warning only if unknown)
KNOWN_PREFIXES: set[str] = {
    "an_",
    "cap_",
    "earningsdate_",
    "etf_",
    "exch_",
    "fa_",
    "geo_",
    "idx_",
    "ind_",
    "ipodate_",
    "news_",
    "sec_",
    "sh_",
    "subtheme_",
    "ta_",
    "targetprice_",
    "theme_",
}

# Strict token pattern: lowercase letters, digits, underscore, dot, hyphen only
_TOKEN_RE = re.compile(r"^[a-z0-9_.\-]+$")

# Order parameter pattern: optional leading dash, then lowercase letters/digits/underscore
_ORDER_RE = re.compile(r"^-?[a-z0-9_]+$")


def validate_filters(raw_filters: str) -> list[str]:
    """Validate and return a list of filter tokens.

    Each token must match ``^[a-z0-9_.\\-]+$`` (lowercase, digits, underscore,
    dot, hyphen).  Tokens containing ``&``, ``=``, spaces, or other characters
    are rejected to prevent URL injection.

    Unknown prefixes generate a warning to stderr but are not rejected.

    Returns:
        Sorted list of valid filter tokens.

    Raises:
        SystemExit: If any token fails the character-class check.
    """
    tokens: list[str] = [t.strip() for t in raw_filters.split(",") if t.strip()]
    if not tokens:
        print("Error: --filters must contain at least one filter code.", file=sys.stderr)
        sys.exit(1)

    validated: list[str] = []
    for token in tokens:
        if not _TOKEN_RE.match(token):
            print(
                f"Error: Invalid filter token '{token}'. "
                "Only lowercase letters, digits, underscores, and dots are allowed.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Warn on unknown prefix (not an error)
        prefix = token.split("_", 1)[0] + "_" if "_" in token else ""
        if prefix and prefix not in KNOWN_PREFIXES:
            print(f"Warning: Unknown filter prefix '{prefix}' in '{token}'.", file=sys.stderr)

        validated.append(token)

    return validated


def validate_order(order: str) -> str:
    """Validate the sort order parameter.

    Must match ``^-?[a-z0-9_]+$`` (optional leading dash, then lowercase
    letters, digits, underscores).  Rejects characters that could inject
    additional URL parameters.

    Returns:
        The validated order string.

    Raises:
        SystemExit: If the order value fails validation.
    """
    if not _ORDER_RE.match(order):
        print(
            f"Error: Invalid order value '{order}'. "
            "Only lowercase letters, digits, underscores, and an optional leading dash are allowed.",
            file=sys.stderr,
        )
        sys.exit(1)
    return order


def detect_elite(args: argparse.Namespace) -> bool:
    """Determine whether to use elite.finviz.com.

    Priority:
    1. ``--elite`` flag → True
    2. ``$FINVIZ_API_KEY`` environment variable present → True
    3. Otherwise → False (public)
    """
    if args.elite:
        return True
    if os.environ.get("FINVIZ_API_KEY"):
        return True
    return False


def build_url(
    filters: list[str],
    *,
    elite: bool = False,
    view: str = "overview",
    order: str | None = None,
) -> str:
    """Build the full FinViz screener URL.

    Args:
        filters: List of validated filter tokens.
        elite: Use elite.finviz.com if True.
        view: View type name (overview, valuation, etc.).
        order: Optional sort order code (e.g., ``-marketcap``).

    Returns:
        Complete URL string.
    """
    host = "elite.finviz.com" if elite else "finviz.com"
    view_code = VIEW_CODES.get(view, VIEW_CODES["overview"])
    filter_str = ",".join(filters)

    url = f"https://{host}/screener.ashx?v={view_code}&f={filter_str}"
    if order:
        url += f"&o={order}"
    return url


def open_browser(url: str) -> None:
    """Open *url* in Google Chrome, with fallbacks.

    macOS: ``open -a "Google Chrome"``  → ``open``
    Linux: ``google-chrome`` → ``chromium-browser`` → ``xdg-open``
    Final fallback: ``webbrowser.open()``.
    """
    if sys.platform == "darwin":
        # Try Chrome first
        try:
            subprocess.run(  # nosec B607 — macOS open is a known local tool
                ["open", "-a", "Google Chrome", url],
                check=True,
                capture_output=True,
            )
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Fallback to default browser on macOS
        try:
            subprocess.run(["open", url], check=True, capture_output=True)  # nosec B607
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    elif sys.platform.startswith("linux"):
        for cmd in ("google-chrome", "chromium-browser", "xdg-open"):
            if shutil.which(cmd):
                try:
                    subprocess.run([cmd, url], check=True, capture_output=True)
                    return
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue

    # Final fallback
    webbrowser.open(url)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a FinViz screener URL and open it in Chrome.",
    )
    parser.add_argument(
        "--filters",
        required=True,
        help="Comma-separated FinViz filter codes (e.g., cap_small,fa_div_o3,fa_pe_u20).",
    )
    parser.add_argument(
        "--elite",
        action="store_true",
        default=False,
        help="Use elite.finviz.com (auto-detected from $FINVIZ_API_KEY if not set).",
    )
    parser.add_argument(
        "--view",
        default="overview",
        choices=sorted(VIEW_CODES.keys()),
        help="Screener view type (default: overview).",
    )
    parser.add_argument(
        "--order",
        default=None,
        help="Sort order code (e.g., -marketcap, dividendyield). Prefix - for descending.",
    )
    parser.add_argument(
        "--url-only",
        action="store_true",
        default=False,
        help="Print the URL without opening a browser.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    filters = validate_filters(args.filters)
    order = validate_order(args.order) if args.order else None
    elite = detect_elite(args)
    url = build_url(filters, elite=elite, view=args.view, order=order)

    mode = "Elite" if elite else "Public"
    print(f"[{mode}] {url}")

    if not args.url_only:
        open_browser(url)


if __name__ == "__main__":
    main()
