"""v3.7 PR B: verified full-snapshot screening and market-wide scope."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import estimate_snapshot as SNAP  # noqa: E402
import run_pipeline as PIPELINE  # noqa: E402


def _listing(symbol: str, index: int) -> dict:
    sectors = (
        ("Technology", "Software - Application"),
        ("Industrials", "Industrial Distribution"),
        ("Basic Materials", "Chemicals"),
        ("Consumer Defensive", "Packaged Foods"),
    )
    sector, industry = sectors[index % len(sectors)]
    return {
        "symbol": symbol,
        "company_name": f"{symbol} Corp",
        "exchange": "NASDAQ",
        "sector": sector,
        "industry": industry,
        "price": 20.0,
        "market_cap": 1_000_000_000 + index * 50_000_000,
        "volume": 500_000,
        "is_actively_trading": True,
        "is_common_stock": True,
        "common_stock": True,
        "currency": "USD",
        "country": "US",
        "isin": None,
        "is_adr": False,
        "sector_profile_type": "general",
    }


def _estimate_rows() -> list[dict]:
    return [
        {
            "date": f"{year}-12-31",
            "fiscalYear": str(year),
            "epsAvg": eps,
            "epsHigh": eps * 1.1,
            "epsLow": eps * 0.9,
            "revenueAvg": revenue,
            "numAnalystsEps": 5,
            "numAnalystsRevenue": 5,
        }
        for year, eps, revenue in (
            (2026, 2.0, 1_000_000_000),
            (2027, 2.4, 1_120_000_000),
            (2028, 2.8, 1_250_000_000),
        )
    ]


def _enumeration_audit(universe: list[dict], *, row_count: int | None = None) -> dict:
    bands = [
        {
            "exchange": exchange,
            "min_market_cap": 500_000_000,
            "max_market_cap": 20_000_000_000,
            "row_count": sum(row["exchange"] == exchange for row in universe),
            "rows_fetched": sum(row["exchange"] == exchange for row in universe),
            "provider_exhausted": True,
            "depth": 0,
        }
        for exchange in ("NASDAQ", "NYSE", "AMEX")
    ]
    return {
        "method": "adaptive_market_cap_bands",
        "retrieval_scope_explicit": True,
        "pagination_exhausted": True,
        "requested_exchanges": ["NASDAQ", "NYSE", "AMEX"],
        "retrieved_exchanges": ["AMEX", "NASDAQ", "NYSE"],
        "requested_min_market_cap": 500_000_000,
        "requested_max_market_cap": 20_000_000_000,
        "min_price": 5.0,
        "page_limit": 1000,
        "query_count": 3,
        "row_count": len(universe) if row_count is None else row_count,
        "bands": bands,
        "saturated_leaf_count": 0,
        "enumeration_verified": True,
    }


def _build_snapshot(
    root: Path,
    *,
    now: datetime,
    count: int = 8,
    with_estimates: bool = True,
    enumeration_row_count: int | None = None,
    enumeration_band_range: tuple[float, float] | None = None,
) -> Path:
    snapshot_dir = root / "snapshot"
    universe = [_listing(f"S{i:02d}", i) for i in range(count)]
    enumeration_audit = _enumeration_audit(universe, row_count=enumeration_row_count)
    if enumeration_band_range is not None:
        for band in enumeration_audit["bands"]:
            band["min_market_cap"], band["max_market_cap"] = enumeration_band_range
    manifest = SNAP.create_snapshot(
        snapshot_dir,
        universe,
        shard_count=1,
        as_of=now,
        enumeration_audit=enumeration_audit,
    )
    normalized = PIPELINE.normalize_estimate_frame(
        universe,
        {row["symbol"]: (_estimate_rows() if with_estimates else []) for row in universe},
        analysis_as_of=now,
        source_id="fixture-estimates",
        config=PIPELINE.load_config(None),
    )
    stamp = now.astimezone(timezone.utc).isoformat()
    records = []
    classified: dict[str, int] = {}
    for row in normalized:
        record = dict(row)
        classification = SNAP.classify_symbol(
            row,
            row,
            requires_unit_reconciliation=PIPELINE.requires_unit_reconciliation,
        )
        record.update(
            {
                "snapshot_classification": classification,
                "snapshot_shard": 0,
                "snapshot_retrieved_at": stamp,
                "snapshot_normalization_as_of": stamp,
                "snapshot_served_from_cache": False,
            }
        )
        records.append(record)
        classified[classification] = classified.get(classification, 0) + 1
    SNAP.append_shard_rows(snapshot_dir, 0, records)
    SNAP.update_shard(
        snapshot_dir,
        manifest,
        0,
        status="complete",
        as_of=stamp,
        calls_used=count,
        classified=classified,
        attempted=count,
        expected=count,
        oldest_retrieved_at=stamp,
        newest_retrieved_at=stamp,
        oldest_normalization_as_of=stamp,
        newest_normalization_as_of=stamp,
    )
    return snapshot_dir


class FakeScreenClient:
    def __init__(self) -> None:
        self.api_calls_made = 0
        self.max_api_calls = 999

    def get_historical_prices(self, symbol, *, from_date, to_date):
        self.api_calls_made += 1
        return [{"date": f"2026-08-{day:02d}", "volume": 600_000} for day in range(1, 26)]

    def get_key_metrics_ttm(self, symbol):
        self.api_calls_made += 1
        return [
            {
                "returnOnInvestedCapitalTTM": 0.16,
                "freeCashFlowYieldTTM": 0.07,
                "evToFreeCashFlowTTM": 14.0,
                "netDebtToEBITDATTM": 1.2,
                "stockBasedCompensationToRevenueTTM": 0.02,
            }
        ]

    def diagnostics(self):
        return {
            "api_calls_made": self.api_calls_made,
            "max_api_calls": self.max_api_calls,
            "cache_hits": 0,
            "failure_count": 0,
            "failure_samples": [],
            "disabled_endpoint_count": 0,
            "offline": False,
        }


class BackfillScreenClient(FakeScreenClient):
    def __init__(self, *, failed_history_calls: int) -> None:
        super().__init__()
        self.failed_history_calls = failed_history_calls
        self.history_calls = 0

    def get_historical_prices(self, symbol, *, from_date, to_date):
        self.api_calls_made += 1
        self.history_calls += 1
        if self.history_calls <= self.failed_history_calls:
            return []
        return [{"date": f"2026-08-{day:02d}", "volume": 600_000} for day in range(1, 26)]


class VerifiedSnapshotBundleTests(unittest.TestCase):
    def test_verified_rows_and_digest_come_from_one_verified_read(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = _build_snapshot(Path(tmp), now=now)
            bundle = SNAP.load_verified_snapshot(
                snapshot_dir,
                screening_as_of=now,
                max_staleness_days=7,
            )
            self.assertTrue(bundle["verdict"]["ready_for_screening"])
            self.assertEqual(len(bundle["rows"]), 8)
            self.assertEqual(len(bundle["verification_digest"]), 64)
            self.assertEqual(
                bundle["verification_digest"],
                bundle["verdict"]["snapshot_verification_digest"],
            )

    def test_tampered_shard_returns_no_consumable_rows(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = _build_snapshot(Path(tmp), now=now)
            path = SNAP.shard_path(snapshot_dir, 0)
            path.write_text(path.read_text().replace('"symbol": "S00"', '"symbol": "BAD"'))
            bundle = SNAP.load_verified_snapshot(
                snapshot_dir,
                screening_as_of=now,
                max_staleness_days=7,
            )
            self.assertFalse(bundle["verdict"]["ready_for_screening"])
            self.assertEqual(bundle["rows"], [])

    def test_subset_enumeration_proof_is_rejected(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = _build_snapshot(Path(tmp), now=now, count=8, enumeration_row_count=9)
            bundle = SNAP.load_verified_snapshot(
                snapshot_dir,
                screening_as_of=now,
                max_staleness_days=7,
            )
            self.assertFalse(bundle["verdict"]["listing_enumeration_verified"])
            self.assertFalse(bundle["verdict"]["ready_for_screening"])
            self.assertTrue(
                any("complete requested scope" in p for p in bundle["verdict"]["problems"])
            )

    def test_gapped_enumeration_bands_are_rejected(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = _build_snapshot(
                Path(tmp),
                now=now,
                enumeration_band_range=(1_000_000_000, 2_000_000_000),
            )
            bundle = SNAP.load_verified_snapshot(
                snapshot_dir,
                screening_as_of=now,
                max_staleness_days=7,
            )
            self.assertFalse(bundle["verdict"]["listing_enumeration_verified"])
            self.assertFalse(bundle["verdict"]["ready_for_screening"])

    def test_old_normalization_basis_is_rejected_even_with_fresh_retrieval(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        old = (now - timedelta(days=30)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = _build_snapshot(Path(tmp), now=now)
            path = SNAP.shard_path(snapshot_dir, 0)
            rows = SNAP.load_shard_rows(snapshot_dir, 0)
            for row in rows:
                row["snapshot_normalization_as_of"] = old
            path.write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
            manifest = SNAP.load_manifest(snapshot_dir)
            entry = manifest["shards"]["0"]
            SNAP.update_shard(
                snapshot_dir,
                manifest,
                0,
                status="complete",
                as_of=entry["as_of"],
                calls_used=entry["calls_used"],
                classified=entry["classified"],
                attempted=entry["attempted"],
                expected=entry["expected"],
                oldest_retrieved_at=entry["oldest_retrieved_at"],
                newest_retrieved_at=entry["newest_retrieved_at"],
                oldest_normalization_as_of=old,
                newest_normalization_as_of=old,
            )
            bundle = SNAP.load_verified_snapshot(
                snapshot_dir,
                screening_as_of=now,
                max_staleness_days=7,
            )
            self.assertFalse(bundle["verdict"]["normalization_current"])
            self.assertFalse(bundle["verdict"]["ready_for_screening"])


class FullSnapshotStageTests(unittest.TestCase):
    def _config(self) -> dict:
        config = PIPELINE.load_config(None)
        config.update(
            {
                "full_snapshot_pool_size": 30,
                "full_snapshot_deep_dive_candidates": 5,
                "full_snapshot_max_staleness_days": 7,
                "full_snapshot_screening_clock_skew_seconds": 300,
            }
        )
        return config

    def test_complete_current_snapshot_emits_consistent_marketwide_audit(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_dir = _build_snapshot(root, now=now)
            prepared = PIPELINE.prepare_screen_full_snapshot(
                snapshot_dir,
                analysis_as_of=now,
                config=self._config(),
                screening_started_at=now,
            )
            output = root / "run"
            result = PIPELINE.execute_screen_full_snapshot(
                FakeScreenClient(),
                self._config(),
                analysis_as_of=now,
                output_dir=output,
                prepared_snapshot=prepared,
                include_packets=False,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.summary["ranking_scope"], "final_marketwide")
            self.assertEqual(result.summary["conclusion_scope"], "full_listing_universe")
            self.assertEqual(result.summary["estimate_acquisition_mode"], "sharded_snapshot")
            self.assertEqual(result.summary["economic_attempt_count"], 8)
            self.assertEqual(result.summary["listing_universe_count"], 8)
            self.assertEqual(
                result.summary["snapshot_verification_digest"], prepared["verification_digest"]
            )

            broad = json.loads((output / "audit" / "broad-screen-audit.json").read_text())
            self.assertEqual(broad["conclusion_scope"], "full_listing_universe")
            self.assertEqual(broad["deep_dive_plan"]["max_deep_dive_candidates"], 5)
            universe_audit = [
                json.loads(line)
                for line in (output / "audit" / "universe-audit-results.jsonl")
                .read_text()
                .splitlines()
            ]
            self.assertEqual(
                {row["symbol"] for row in universe_audit}, {f"S{i:02d}" for i in range(8)}
            )
            self.assertEqual(
                {row["estimate_attempt"]["classification"] for row in universe_audit},
                {"evaluable"},
            )
            self.assertTrue(
                all(
                    row["estimate_attempt"]["snapshot_verification_digest"]
                    == prepared["verification_digest"]
                    for row in universe_audit
                )
            )
            selected = set(result.summary["selected_symbols"])
            final_pool = {
                json.loads(line)["symbol"]: json.loads(line)
                for line in (output / "audit" / "provider-prefilter-pool.jsonl")
                .read_text()
                .splitlines()
            }
            self.assertTrue(selected)
            self.assertTrue(
                all(final_pool[symbol]["quality_probe_attempted"] for symbol in selected)
            )

    def test_historical_as_of_is_rejected_before_enrichment(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        historical = now - timedelta(days=30)
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = _build_snapshot(Path(tmp), now=historical)
            with self.assertRaisesRegex(ValueError, "current-only"):
                PIPELINE.prepare_screen_full_snapshot(
                    snapshot_dir,
                    analysis_as_of=historical,
                    config=self._config(),
                    screening_started_at=now,
                )

    def test_snapshot_scope_must_cover_current_screen_request(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        config = self._config()
        config["min_market_cap"] = 100_000_000
        config["max_market_cap"] = 100_000_000_000
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = _build_snapshot(Path(tmp), now=now)
            with self.assertRaisesRegex(ValueError, "does not cover"):
                PIPELINE.prepare_screen_full_snapshot(
                    snapshot_dir,
                    analysis_as_of=now,
                    config=config,
                    screening_started_at=now,
                )

    def test_fifty_name_pool_is_not_silently_limited_to_forty(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        config = self._config()
        config["full_snapshot_pool_size"] = 50
        config["exact_liquidity_limit"] = 40
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_dir = _build_snapshot(root, now=now, count=55)
            prepared = PIPELINE.prepare_screen_full_snapshot(
                snapshot_dir,
                analysis_as_of=now,
                config=config,
                screening_started_at=now,
            )
            result = PIPELINE.execute_screen_full_snapshot(
                FakeScreenClient(),
                config,
                analysis_as_of=now,
                output_dir=root / "run",
                prepared_snapshot=prepared,
                include_packets=False,
            )
            self.assertEqual(result.summary["exact_liquidity_target_count"], 50)
            self.assertEqual(result.summary["provider_prefilter_pool_count"], 50)
            self.assertEqual(len(result.summary["selected_symbols"]), 5)

    def test_liquidity_failures_backfill_until_target_is_reached(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        config = self._config()
        config["full_snapshot_pool_size"] = 50
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_dir = _build_snapshot(root, now=now, count=75)
            prepared = PIPELINE.prepare_screen_full_snapshot(
                snapshot_dir,
                analysis_as_of=now,
                config=config,
                screening_started_at=now,
            )
            client = BackfillScreenClient(failed_history_calls=25)
            result = PIPELINE.execute_screen_full_snapshot(
                client,
                config,
                analysis_as_of=now,
                output_dir=root / "run",
                prepared_snapshot=prepared,
                include_packets=False,
            )
            self.assertEqual(client.history_calls, 75)
            self.assertEqual(result.summary["exact_liquidity_target_count"], 75)
            self.assertEqual(result.summary["provider_prefilter_pool_count"], 50)
            self.assertEqual(result.summary["ranking_scope"], "final_marketwide")

    def test_all_symbols_classified_no_estimates_is_marketwide_no_candidates(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_dir = _build_snapshot(
                root,
                now=now,
                count=3,
                with_estimates=False,
            )
            prepared = PIPELINE.prepare_screen_full_snapshot(
                snapshot_dir,
                analysis_as_of=now,
                config=self._config(),
                screening_started_at=now,
            )
            result = PIPELINE.execute_screen_full_snapshot(
                FakeScreenClient(),
                self._config(),
                analysis_as_of=now,
                output_dir=root / "run",
                prepared_snapshot=prepared,
                include_packets=False,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.summary["status"], "no_candidates_in_marketwide_snapshot")
            self.assertEqual(result.summary["ranking_scope"], "final_marketwide")
            self.assertEqual(result.summary["snapshot_classification_totals"]["no_estimates"], 3)

    def test_cli_invalid_snapshot_creates_no_cache_raw_or_run_tree(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "reports"
            cache = root / "cache" / "fmp.sqlite3"
            raw = root / "raw"
            rc = PIPELINE.main(
                [
                    "--stage",
                    "screen-full-snapshot",
                    "--snapshot-dir",
                    str(root / "missing"),
                    "--analysis-as-of",
                    now.isoformat(),
                    "--output-dir",
                    str(output),
                    "--cache-path",
                    str(cache),
                    "--raw-store-dir",
                    str(raw),
                ]
            )
            self.assertEqual(rc, 1)
            self.assertFalse(output.exists())
            self.assertFalse(cache.exists())
            self.assertFalse(raw.exists())

    def test_cli_historical_collection_basis_is_rejected_before_side_effects(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "reports"
            cache = root / "cache" / "fmp.sqlite3"
            raw = root / "raw"
            snapshot = root / "snapshot"
            rc = PIPELINE.main(
                [
                    "--stage",
                    "collect-estimates",
                    "--shard-index",
                    "0",
                    "--shard-count",
                    "1",
                    "--snapshot-dir",
                    str(snapshot),
                    "--analysis-as-of",
                    (now - timedelta(days=30)).isoformat(),
                    "--output-dir",
                    str(output),
                    "--cache-path",
                    str(cache),
                    "--raw-store-dir",
                    str(raw),
                ]
            )
            self.assertEqual(rc, 1)
            self.assertFalse(output.exists())
            self.assertFalse(cache.exists())
            self.assertFalse(raw.exists())
            self.assertFalse(snapshot.exists())


if __name__ == "__main__":
    unittest.main()
