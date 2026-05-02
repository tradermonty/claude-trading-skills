#!/usr/bin/env python3
"""Live API smoke check for parabolic-short-trade-planner.

Five logical checks (4 required gates + 1 optional warning) that prove
both the happy paths and the 404 graceful-handling path that's
otherwise unreachable from Phase 1 output:

    1. FMP historical-price-eod/full?symbol=AAPL&from=&to=  (Issue #64
       flat-list shape; the contract Phase 1 exercises)
    2. FMP profile/AAPL                                     (mktCap)
    3. FMP sp500_constituent                                (optional —
       entitlement varies by tier; print a warning, do not fail)
    4. Alpaca /v2/assets/AAPL                               (shortable +
       easy_to_borrow keys present)
    5. Alpaca /v2/assets/XXXXXFAKE                          (negative
       path: 404 → AlpacaInventoryAdapter must return asset_not_found
       dict without raising)

Note: check #5 issues TWO HTTP requests against the same Alpaca
endpoint (one raw probe to confirm the 404 itself, then a second one
through `AlpacaInventoryAdapter.get_inventory_status` to confirm the
adapter handles that response gracefully). So while there are 5
logical checks, the script makes 6 HTTP calls per run (3 FMP +
3 Alpaca). The cost remains trivial under both API rate limits.

Returns 0 on all four required gates passing. Logs status code +
first 200 chars of the error body on failures.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

# Ensure the skill's adapters/ is importable for the Alpaca 404 check.
SCRIPTS_DIR = Path(__file__).resolve().parent
ADAPTERS_DIR = SCRIPTS_DIR / "adapters"
for _p in (str(ADAPTERS_DIR), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


FMP_STABLE_HIST = "https://financialmodelingprep.com/stable/historical-price-eod/full"
FMP_V3 = "https://financialmodelingprep.com/api/v3"
ALPACA_PAPER = "https://paper-api.alpaca.markets"
ALPACA_LIVE = "https://api.alpaca.markets"

REQUIRED_HISTORICAL_KEYS = {"date", "open", "high", "low", "close", "volume"}


def _truncate(body: str, n: int = 200) -> str:
    body = body.strip()
    return body if len(body) <= n else body[:n] + "..."


def _print_pass(name: str, detail: str) -> None:
    print(f"PASS {name} — {detail}")


def _print_warn(name: str, detail: str) -> None:
    print(f"WARN {name} — {detail}")


def _print_fail(name: str, detail: str) -> None:
    print(f"FAIL {name} — {detail}")


def check_fmp_historical(api_key: str) -> bool:
    """Gate 1 — verify Issue #64 flat-list shape."""
    name = "fmp.historical_price_eod_full"
    today = date.today()
    params = {
        "symbol": "AAPL",
        "from": (today - timedelta(days=10)).isoformat(),
        "to": today.isoformat(),
        "apikey": api_key,
    }
    try:
        r = requests.get(FMP_STABLE_HIST, params=params, timeout=15)
    except requests.RequestException as e:
        _print_fail(name, f"network error: {e}")
        return False

    if r.status_code != 200:
        _print_fail(name, f"HTTP {r.status_code} — {_truncate(r.text)}")
        return False

    try:
        data = r.json()
    except ValueError:
        _print_fail(name, f"non-JSON body: {_truncate(r.text)}")
        return False

    if not isinstance(data, list) or not data:
        _print_fail(name, f"expected non-empty list[dict], got {type(data).__name__}")
        return False

    first = data[0]
    if not isinstance(first, dict):
        _print_fail(name, f"first row is {type(first).__name__}, expected dict")
        return False

    missing = REQUIRED_HISTORICAL_KEYS - set(first.keys())
    if missing:
        _print_fail(name, f"row missing keys: {sorted(missing)} (got {sorted(first.keys())})")
        return False

    _print_pass(name, f"{len(data)} bars; Issue #64 shape verified (date/o/h/l/c/v)")
    return True


def check_fmp_profile(api_key: str) -> bool:
    """Gate 2 — verify profile/AAPL returns a non-empty list with mktCap."""
    name = "fmp.profile"
    url = f"{FMP_V3}/profile/AAPL"
    try:
        r = requests.get(url, params={"apikey": api_key}, timeout=15)
    except requests.RequestException as e:
        _print_fail(name, f"network error: {e}")
        return False

    if r.status_code != 200:
        _print_fail(name, f"HTTP {r.status_code} — {_truncate(r.text)}")
        return False

    try:
        data = r.json()
    except ValueError:
        _print_fail(name, f"non-JSON body: {_truncate(r.text)}")
        return False

    if not isinstance(data, list) or not data or "mktCap" not in data[0]:
        _print_fail(name, f"expected list with mktCap on first item, got {data!r:.200}")
        return False

    _print_pass(name, f"mktCap={data[0].get('mktCap')}")
    return True


def check_fmp_sp500(api_key: str) -> bool:
    """Optional warning — sp500_constituent entitlement varies by FMP tier."""
    name = "fmp.sp500_constituent"
    url = f"{FMP_V3}/sp500_constituent"
    try:
        r = requests.get(url, params={"apikey": api_key}, timeout=15)
    except requests.RequestException as e:
        _print_warn(name, f"network error (optional gate): {e}")
        return True

    if r.status_code != 200:
        _print_warn(
            name,
            f"HTTP {r.status_code} — likely entitlement (skip on Free); body: {_truncate(r.text)}",
        )
        return True

    try:
        data = r.json()
    except ValueError:
        _print_warn(name, f"non-JSON body: {_truncate(r.text)}")
        return True

    if not isinstance(data, list) or not data:
        _print_warn(name, "empty list (skip on Free)")
        return True

    _print_pass(name, f"{len(data)} constituents")
    return True


def check_alpaca_assets_aapl(api_key: str, secret: str, paper: bool) -> bool:
    """Gate 3 — verify shortable + easy_to_borrow keys are present."""
    name = "alpaca.assets_aapl"
    base = ALPACA_PAPER if paper else ALPACA_LIVE
    url = f"{base}/v2/assets/AAPL"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    try:
        r = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException as e:
        _print_fail(name, f"network error: {e}")
        return False

    if r.status_code != 200:
        _print_fail(name, f"HTTP {r.status_code} — {_truncate(r.text)}")
        return False

    try:
        data = r.json()
    except ValueError:
        _print_fail(name, f"non-JSON body: {_truncate(r.text)}")
        return False

    missing = {"shortable", "easy_to_borrow"} - set(data.keys())
    if missing:
        _print_fail(name, f"missing keys {sorted(missing)} (got {sorted(data.keys())})")
        return False

    _print_pass(
        name,
        f"shortable={data['shortable']} easy_to_borrow={data['easy_to_borrow']} (paper={paper})",
    )
    return True


def check_alpaca_404_graceful(api_key: str, secret: str, paper: bool) -> bool:
    """Gate 4 — confirm AlpacaInventoryAdapter returns asset_not_found
    on 404 instead of raising. Phase 1 normally rejects unknown tickers
    before they reach the Adapter, so this is the only end-to-end
    coverage of the 404 fix."""
    name = "alpaca.assets_404_graceful"
    base = ALPACA_PAPER if paper else ALPACA_LIVE
    url = f"{base}/v2/assets/XXXXXFAKE"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}

    try:
        r = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException as e:
        _print_fail(name, f"network error on raw 404 probe: {e}")
        return False

    if r.status_code != 404:
        _print_fail(
            name,
            f"expected HTTP 404 from raw probe, got {r.status_code} — {_truncate(r.text)}",
        )
        return False

    # Now confirm the Adapter handles the same response gracefully.
    try:
        from alpaca_inventory_adapter import AlpacaInventoryAdapter  # noqa: WPS433

        adapter = AlpacaInventoryAdapter(api_key=api_key, secret_key=secret, paper=paper)
        status = adapter.get_inventory_status("XXXXXFAKE")
    except Exception as e:  # noqa: BLE001 — we explicitly want any raise to fail this gate
        _print_fail(name, f"AlpacaInventoryAdapter raised on 404: {type(e).__name__}: {e}")
        return False

    if status.get("error") != "asset_not_found":
        _print_fail(name, f"expected error=asset_not_found, got {status!r:.200}")
        return False
    if status.get("can_open_new_short") is not False:
        _print_fail(
            name, f"can_open_new_short must be False, got {status.get('can_open_new_short')}"
        )
        return False

    _print_pass(name, "raw HTTP 404 mapped to asset_not_found dict (no exception)")
    return True


def main() -> int:
    print("=" * 70)
    print("Parabolic Short — live API smoke check")
    print("=" * 70)

    fmp_key = os.environ.get("FMP_API_KEY")
    alpaca_key = os.environ.get("ALPACA_API_KEY")
    alpaca_secret = os.environ.get("ALPACA_SECRET_KEY")
    alpaca_paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    if not fmp_key:
        print("FAIL setup — FMP_API_KEY env var is missing")
        return 1
    if not alpaca_key or not alpaca_secret:
        print("FAIL setup — ALPACA_API_KEY / ALPACA_SECRET_KEY env vars are missing")
        return 1

    results = {
        "fmp_historical": check_fmp_historical(fmp_key),
        "fmp_profile": check_fmp_profile(fmp_key),
        "fmp_sp500": check_fmp_sp500(fmp_key),  # optional, never gates exit code
        "alpaca_assets_aapl": check_alpaca_assets_aapl(alpaca_key, alpaca_secret, alpaca_paper),
        "alpaca_404_graceful": check_alpaca_404_graceful(alpaca_key, alpaca_secret, alpaca_paper),
    }

    required = ("fmp_historical", "fmp_profile", "alpaca_assets_aapl", "alpaca_404_graceful")
    passed = sum(1 for k in required if results[k])
    print("-" * 70)
    print(f"Required gates: {passed}/{len(required)} passed (sp500 is optional warning)")
    return 0 if passed == len(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
