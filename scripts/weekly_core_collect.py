#!/usr/bin/env python3
"""Collect weekly core portfolio data for local review workflows."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

ALPACA_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE_URL = "https://api.alpaca.markets"
FMP_V3_BASE_URL = "https://financialmodelingprep.com/api/v3"
FMP_STABLE_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_SYMBOL_QUERY_ENDPOINTS = {
    "balance-sheet-statement",
    "cash-flow-statement",
    "income-statement",
    "profile",
    "quote",
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Collect Alpaca holdings plus FMP enrichment for weekly core reviews."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "reports",
        help="Directory for generated JSON artifacts. Defaults to reports/ in this repo.",
    )
    parser.add_argument(
        "--as-of",
        default=dt.datetime.now().astimezone().date().isoformat(),
        help="Date string for output filenames. Defaults to today's local date.",
    )
    parser.add_argument(
        "--alpaca-paper",
        default=os.environ.get("ALPACA_PAPER", "true").lower(),
        help=(
            "Use Alpaca paper endpoint. Accepts true/false, yes/no, or 1/0. "
            "Defaults to ALPACA_PAPER or true."
        ),
    )
    parser.add_argument(
        "--fmp-sleep-seconds",
        type=float,
        default=0.08,
        help="Pause between per-symbol FMP request groups.",
    )
    args = parser.parse_args()
    args.alpaca_paper = parse_bool(args.alpaca_paper, "ALPACA_PAPER/--alpaca-paper")
    return args


def parse_bool(value: str, name: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise SystemExit(
        f"Invalid {name}: {value!r}. Expected true/false, yes/no, or 1/0; refusing "
        "to choose a live Alpaca endpoint implicitly."
    )


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def alpaca_headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": require_env("ALPACA_API_KEY"),
        "APCA-API-SECRET-KEY": require_env("ALPACA_SECRET_KEY"),
    }


def get_json(url: str, **kwargs: Any) -> Any:
    response = requests.get(url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def alpaca_base_url(use_paper: bool) -> str:
    return ALPACA_PAPER_BASE_URL if use_paper else ALPACA_LIVE_BASE_URL


class FmpClient:
    """Small stable-first FMP client for the weekly collector.

    Callers pass the legacy v3 path-style endpoints used elsewhere in the repo.
    The client tries the known /stable query-style equivalent first, falls back
    to v3 for legacy keys, and records diagnostics instead of silently dropping
    enrichment failures.
    """

    def __init__(self, api_key: str | None):
        self.api_key = api_key
        self.attempts = 0
        self.successes = 0
        self.failures: list[dict[str, Any]] = []

    def get(self, path: str, **params: Any) -> Any:
        if not self.api_key:
            return None

        attempts: list[tuple[str, str, dict[str, Any]]] = []
        stable_spec = self._stable_spec(path, params)
        if stable_spec:
            attempts.append(("stable", stable_spec[0], stable_spec[1]))
        attempts.append(("v3", f"{FMP_V3_BASE_URL}/{path}", dict(params)))

        for source, url, req_params in attempts:
            data = self._request(source, path, url, req_params)
            if data is not None:
                return self._normalize(path, data)
        return None

    def diagnostics(self) -> dict[str, Any]:
        if not self.api_key:
            status = "disabled"
        elif self.attempts == 0:
            status = "skipped"
        elif self.successes == 0:
            status = "failed"
        elif self.failures:
            status = "degraded"
        else:
            status = "ok"

        return {
            "status": status,
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": len(self.failures),
            "failure_samples": self.failures[:20],
        }

    @staticmethod
    def _stable_spec(path: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        stable_params = dict(params)
        if path.startswith("historical-price-full/stock_dividend/"):
            stable_params["symbol"] = path.rsplit("/", 1)[-1]
            return f"{FMP_STABLE_BASE_URL}/dividends", stable_params

        endpoint, _, symbol = path.partition("/")
        if symbol and endpoint in FMP_SYMBOL_QUERY_ENDPOINTS:
            stable_params["symbol"] = symbol
            return f"{FMP_STABLE_BASE_URL}/{endpoint}", stable_params

        return None

    @staticmethod
    def _normalize(path: str, data: Any) -> Any:
        if path.startswith("historical-price-full/stock_dividend/"):
            return {"historical": data} if isinstance(data, list) else data

        if path.startswith(("profile/", "quote/")) and isinstance(data, dict):
            return [data]

        if path.startswith("cash-flow-statement/") and isinstance(data, list):
            for row in data:
                if (
                    isinstance(row, dict)
                    and "dividendsPaid" not in row
                    and "netDividendsPaid" in row
                ):
                    row["dividendsPaid"] = row["netDividendsPaid"]

        return data

    def _request(self, source: str, path: str, url: str, params: dict[str, Any]) -> Any:
        self.attempts += 1
        req_params = dict(params)
        req_params["apikey"] = self.api_key
        try:
            response = requests.get(url, params=req_params, timeout=30)
        except requests.RequestException as exc:
            self.failures.append({"source": source, "path": path, "error": str(exc)})
            return None

        if response.status_code != 200:
            self.failures.append(
                {
                    "source": source,
                    "path": path,
                    "status_code": response.status_code,
                    "body_preview": response.text[:200],
                }
            )
            return None

        try:
            data = response.json()
        except ValueError as exc:
            self.failures.append({"source": source, "path": path, "error": str(exc)})
            return None

        self.successes += 1
        return data


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def fetch_profiles_and_quotes(symbols: list[str], fmp_client: FmpClient) -> tuple[dict, dict]:
    profiles: dict[str, dict] = {}
    quotes: dict[str, dict] = {}
    if not symbols or not fmp_client.api_key:
        return profiles, quotes

    for chunk in chunks(symbols, 50):
        symbol_csv = ",".join(chunk)
        profile_data = fmp_client.get(f"profile/{symbol_csv}")
        if isinstance(profile_data, list):
            profiles.update(
                {item.get("symbol"): item for item in profile_data if item.get("symbol")}
            )

        quote_data = fmp_client.get(f"quote/{symbol_csv}")
        if isinstance(quote_data, list):
            quotes.update({item.get("symbol"): item for item in quote_data if item.get("symbol")})

    return profiles, quotes


def build_holding_rows(
    account: dict,
    positions: list[dict],
    profiles: dict[str, dict],
    quotes: dict[str, dict],
    fmp_client: FmpClient,
    fmp_sleep_seconds: float,
) -> tuple[list[dict], list[dict]]:
    monitor_holdings = []
    full_rows = []
    equity = to_float(account.get("equity"))
    long_market_value = to_float(account.get("long_market_value"))

    for position in positions:
        symbol = position["symbol"]
        profile = profiles.get(symbol, {}) or {}
        quote = quotes.get(symbol, {}) or {}

        dividends = []
        cashflow = []
        income = []
        balance_sheet = []
        if fmp_client.api_key:
            dividend_data = fmp_client.get(f"historical-price-full/stock_dividend/{symbol}")
            if isinstance(dividend_data, dict):
                dividends = dividend_data.get("historical") or []

            cashflow = fmp_client.get(f"cash-flow-statement/{symbol}", limit=4)
            income = fmp_client.get(f"income-statement/{symbol}", limit=4)
            balance_sheet = fmp_client.get(f"balance-sheet-statement/{symbol}", limit=4)
            time.sleep(fmp_sleep_seconds)

        positive_dividends = [
            to_float(item.get("adjDividend") or item.get("dividend"))
            for item in dividends
            if to_float(item.get("adjDividend") or item.get("dividend")) > 0
        ]
        latest_dividend = positive_dividends[0] if positive_dividends else None
        prior_dividend = positive_dividends[1] if len(positive_dividends) > 1 else None

        coverage_ratios = []
        if isinstance(cashflow, list):
            for statement in cashflow[:4]:
                free_cash_flow = to_float(statement.get("operatingCashFlow")) + to_float(
                    statement.get("capitalExpenditure")
                )
                dividends_paid = abs(to_float(statement.get("dividendsPaid")))
                if dividends_paid:
                    coverage_ratios.append(
                        dividends_paid / free_cash_flow if free_cash_flow else 999
                    )

        net_debt_history = []
        if isinstance(balance_sheet, list):
            for statement in balance_sheet[:4]:
                net_debt_history.append(
                    to_float(statement.get("totalDebt"))
                    - to_float(statement.get("cashAndCashEquivalents"))
                )

        interest_coverage_history = []
        revenues = []
        if isinstance(income, list):
            for statement in income[:4]:
                interest_expense = abs(to_float(statement.get("interestExpense")))
                ebit = to_float(statement.get("ebitda") or statement.get("operatingIncome"))
                interest_coverage_history.append(
                    ebit / interest_expense if interest_expense else None
                )
                if statement.get("revenue"):
                    revenues.append(to_float(statement.get("revenue")))

        revenue_cagr_3y = None
        if len(revenues) >= 4 and revenues[-1] > 0:
            revenue_cagr_3y = (revenues[0] / revenues[-1]) ** (1 / 3) - 1

        instrument_type = "etf" if profile.get("isEtf") else "stock"
        sector = profile.get("sector") or quote.get("sector") or "Unknown"
        market_value = to_float(position.get("market_value"))

        row = {
            "symbol": symbol,
            "qty": to_float(position.get("qty")),
            "market_value": market_value,
            "cost_basis": to_float(position.get("cost_basis")),
            "unrealized_pl": to_float(position.get("unrealized_pl")),
            "unrealized_plpc": to_float(position.get("unrealized_plpc")),
            "current_price": to_float(position.get("current_price")),
            "weight_gross_long": market_value / long_market_value if long_market_value else None,
            "weight_equity": market_value / equity if equity else None,
            "sector": sector,
            "industry": profile.get("industry"),
            "company": profile.get("companyName") or symbol,
            "instrument_type": instrument_type,
            "is_etf": bool(profile.get("isEtf")),
            "beta": profile.get("beta") or quote.get("beta"),
            "dividend_yield_profile": profile.get("lastDiv"),
            "latest_regular_dividend": latest_dividend,
            "prior_regular_dividend": prior_dividend,
            "dividend_events_count": len(positive_dividends),
            "coverage_ratio_history": coverage_ratios[:4],
            "net_debt_history": net_debt_history[:4],
            "interest_coverage_history": interest_coverage_history[:4],
            "revenue_cagr_3y": revenue_cagr_3y,
        }
        full_rows.append(row)

        if latest_dividend is not None or instrument_type == "etf":
            dividend_growth_stalled = (
                latest_dividend is not None
                and prior_dividend is not None
                and abs(latest_dividend - prior_dividend) < 1e-9
            )
            monitor_holdings.append(
                {
                    "ticker": symbol,
                    "instrument_type": instrument_type,
                    "dividend": {
                        "latest_regular": latest_dividend,
                        "prior_regular": prior_dividend,
                        "is_missing": latest_dividend is None or prior_dividend is None,
                        "flags": {
                            "cut_flag": bool(
                                latest_dividend is not None
                                and prior_dividend is not None
                                and latest_dividend < prior_dividend * 0.99
                            ),
                            "freeze_flag": dividend_growth_stalled,
                            "special_dividend_flag": False,
                            "variable_policy_flag": False,
                        },
                    },
                    "cashflow": {
                        "fcf": None,
                        "ffo": None,
                        "nii": None,
                        "dividends_paid": None,
                        "coverage_ratio_history": coverage_ratios[:4],
                    },
                    "balance_sheet": {
                        "net_debt_history": net_debt_history[:4],
                        "interest_coverage_history": interest_coverage_history[:4],
                    },
                    "capital_returns": {"buybacks": None, "dividends_paid": None, "fcf": None},
                    "filings": {"recent_text": "", "latest_8k_text": "", "headlines": []},
                    "operations": {
                        "revenue_cagr_5y": revenue_cagr_3y * 100
                        if revenue_cagr_3y is not None
                        else None,
                        "margin_trend": None,
                        "guidance_trend": None,
                        "dividend_growth_stalled": dividend_growth_stalled,
                    },
                }
            )

    return full_rows, monitor_holdings


def build_summary(account: dict, holdings: list[dict], as_of: str, fmp_status: dict) -> dict:
    sector_weights: dict[str, float] = defaultdict(float)
    for row in holdings:
        sector_weights[row["sector"]] += row["market_value"]

    equity = to_float(account.get("equity"))
    long_market_value = to_float(account.get("long_market_value"))
    return {
        "as_of": as_of,
        "account": {
            key: account.get(key)
            for key in [
                "status",
                "currency",
                "equity",
                "cash",
                "buying_power",
                "long_market_value",
                "short_market_value",
                "portfolio_value",
                "balance_asof",
                "multiplier",
                "pattern_day_trader",
            ]
        },
        "positions_count": len(holdings),
        "symbols": [row["symbol"] for row in holdings],
        "fmp_enrichment": fmp_status,
        "gross_long_exposure_pct_equity": long_market_value / equity * 100 if equity else None,
        "cash_pct_equity": to_float(account.get("cash")) / equity * 100 if equity else None,
        "sector_weights_gross_long": {
            sector: value / long_market_value * 100 if long_market_value else None
            for sector, value in sorted(sector_weights.items(), key=lambda item: -item[1])
        },
        "top_positions": sorted(holdings, key=lambda row: row["market_value"], reverse=True)[:10],
        "holdings": holdings,
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    base_url = alpaca_base_url(args.alpaca_paper)
    headers = alpaca_headers()
    account = get_json(f"{base_url}/v2/account", headers=headers)
    positions = get_json(f"{base_url}/v2/positions", headers=headers)
    if not isinstance(account, dict):
        raise SystemExit("Unexpected Alpaca account response")
    if not isinstance(positions, list):
        raise SystemExit("Unexpected Alpaca positions response")

    symbols = [position["symbol"] for position in positions]
    fmp_client = FmpClient(os.environ.get("FMP_API_KEY"))
    profiles, quotes = fetch_profiles_and_quotes(symbols, fmp_client)
    holdings, monitor_holdings = build_holding_rows(
        account, positions, profiles, quotes, fmp_client, args.fmp_sleep_seconds
    )
    fmp_status = fmp_client.diagnostics()
    summary = build_summary(account, holdings, args.as_of, fmp_status)

    holdings_path = args.output_dir / f"core_portfolio_holdings_{args.as_of}.json"
    monitor_path = args.output_dir / f"kanchi_monitor_input_{args.as_of}.json"
    write_json(holdings_path, summary)
    write_json(
        monitor_path,
        {"schema_version": 1, "as_of": args.as_of, "holdings": monitor_holdings},
    )

    print(
        json.dumps(
            {
                "holdings_path": str(holdings_path),
                "monitor_path": str(monitor_path),
                "positions": len(holdings),
                "symbols": symbols,
                "equity": account.get("equity"),
                "long_mv": account.get("long_market_value"),
                "cash": account.get("cash"),
                "sector_weights": summary["sector_weights_gross_long"],
                "fmp_enrichment": fmp_status,
            },
            indent=2,
        )
    )
    if fmp_status["status"] == "failed":
        raise SystemExit("FMP enrichment failed; artifacts were written with fmp_enrichment=failed")


if __name__ == "__main__":
    main()
