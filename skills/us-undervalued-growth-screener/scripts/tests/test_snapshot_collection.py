"""v3.7 PR A: sharded estimate snapshot + shared coverage semantics."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_semantics as COV  # noqa: E402
import estimate_snapshot as SNAP  # noqa: E402
import run_pipeline as PIPELINE  # noqa: E402
from fmp_client import ApiCallBudgetExceeded  # noqa: E402
from screen_universe import requires_unit_reconciliation  # noqa: E402

AS_OF = datetime.now(timezone.utc).replace(microsecond=0)


def _listing(symbol: str, **overrides) -> dict:
    row = {
        "symbol": symbol,
        "company_name": f"{symbol} Corp",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "industry": "Software - Application",
        "price": 20.0,
        "market_cap": 2_000_000_000,
        "volume": 1_000_000,
        "is_actively_trading": True,
        "is_common_stock": True,
        "common_stock": True,
        "currency": "USD",
        "country": "US",
        "isin": None,
        "is_adr": False,
        "sector_profile_type": "general",
    }
    row.update(overrides)
    return row


def _estimate_rows(fy1: float = 2.0) -> list[dict]:
    rows = []
    for offset, eps in ((0, fy1), (1, fy1 * 1.15), (2, fy1 * 1.3)):
        year = 2026 + offset
        rows.append(
            {
                "date": f"{year}-12-31",
                "fiscalYear": str(year),
                "epsAvg": eps,
                "epsHigh": eps * 1.1,
                "epsLow": eps * 0.9,
                "revenueAvg": 1_000_000_000 * (1 + 0.1 * offset),
                "numAnalystsEps": 4,
                "numAnalystsRevenue": 4,
            }
        )
    return rows


class FakeClient:
    def __init__(self, estimates: dict[str, list[dict]], budget: int | None = None):
        self._estimates = estimates
        self._budget = budget
        self.calls = 0

    def get_analyst_estimates(self, symbol: str, *, period: str = "annual", limit: int = 6):
        if self._budget is not None and self.calls >= self._budget:
            raise ApiCallBudgetExceeded("budget exhausted")
        self.calls += 1
        return self._estimates.get(symbol, [])

    def get_analyst_estimates_detailed(
        self, symbol: str, *, period: str = "annual", limit: int = 6
    ) -> dict:
        rows = self.get_analyst_estimates(symbol, period=period, limit=limit)
        return {
            "rows": rows,
            "status": "ok" if rows else "empty",
            "served_from_cache": False,
            "retrieved_at": time.time(),
        }

    def diagnostics(self) -> dict:
        return {"api_calls_made": self.calls, "cache_hits": 0, "failure_count": 0}


def _config() -> dict:
    return dict(PIPELINE.DEFAULT_CONFIG)


def _enumeration_audit(universe: list[dict]) -> dict:
    return {
        "method": "adaptive_market_cap_bands",
        "retrieval_scope_explicit": True,
        "pagination_exhausted": True,
        "requested_exchanges": ["NASDAQ", "NYSE", "AMEX"],
        "retrieved_exchanges": ["NASDAQ", "NYSE", "AMEX"],
        "requested_min_market_cap": 500_000_000,
        "requested_max_market_cap": 20_000_000_000,
        "min_price": 5.0,
        "page_limit": 1000,
        "query_count": 3,
        "row_count": len(universe),
        "bands": [
            {
                "exchange": exchange,
                "min_market_cap": 500_000_000,
                "max_market_cap": 20_000_000_000,
                "row_count": 0,
                "rows_fetched": 0,
                "provider_exhausted": True,
                "depth": 0,
            }
            for exchange in ("NASDAQ", "NYSE", "AMEX")
        ],
        "saturated_leaf_count": 0,
        "enumeration_verified": True,
    }


class StableShardTests(unittest.TestCase):
    def test_shard_assignment_is_deterministic_and_case_insensitive(self) -> None:
        self.assertEqual(SNAP.stable_shard("AAPL", 8), SNAP.stable_shard(" aapl ", 8))
        first = [SNAP.stable_shard(f"SYM{i}", 8) for i in range(200)]
        second = [SNAP.stable_shard(f"SYM{i}", 8) for i in range(200)]
        self.assertEqual(first, second)
        self.assertTrue(all(0 <= shard < 8 for shard in first))
        # every shard gets some members over a reasonable universe
        self.assertEqual(len(set(first)), 8)


class ClassifySymbolTests(unittest.TestCase):
    def _classify(self, listing: dict, normalized: dict) -> str:
        return SNAP.classify_symbol(
            listing, normalized, requires_unit_reconciliation=requires_unit_reconciliation
        )

    def test_precedence(self) -> None:
        base = _listing("T")
        self.assertEqual(
            self._classify(_listing("T", is_common_stock=False), {"estimate_periods": []}),
            "excluded",
        )
        self.assertEqual(
            self._classify(_listing("T", country="CN"), {"estimate_periods": []}),
            "unit_mismatch",
        )
        self.assertEqual(self._classify(base, {"estimate_periods": []}), "no_estimates")
        self.assertEqual(
            self._classify(base, {"estimate_periods": [{}], "fy1_eps": -0.5}), "negative_eps"
        )
        self.assertEqual(
            self._classify(base, {"estimate_periods": [{}], "fy1_eps": 2.0}), "evaluable"
        )

    def test_implausible_forward_pe_is_unit_mismatch(self) -> None:
        verdict = self._classify(
            _listing("T"), {"estimate_periods": [{}], "fy1_eps": 20.0, "forward_pe": 0.45}
        )
        self.assertEqual(verdict, "unit_mismatch")


class CollectEstimatesStageTests(unittest.TestCase):
    def _universe(self) -> list[dict]:
        rows = [_listing(f"SYM{i}") for i in range(20)]
        rows.append(_listing("FRGN", country="CN", currency="CNY"))
        rows.append(_listing("NOEST"))
        return rows

    def _snapshot(self, tmp: str) -> tuple[Path, list[dict]]:
        snapshot_dir = Path(tmp) / "snap"
        universe = self._universe()
        SNAP.create_snapshot(snapshot_dir, universe, shard_count=2, as_of=AS_OF)
        return snapshot_dir, universe

    def _estimates_for(self, universe: list[dict]) -> dict[str, list[dict]]:
        estimates = {row["symbol"]: _estimate_rows() for row in universe}
        estimates["NOEST"] = []
        return estimates

    def test_full_shard_collection_classifies_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir, universe = self._snapshot(tmp)
            estimates = self._estimates_for(universe)
            for shard in (0, 1):
                result = PIPELINE.execute_collect_estimates(
                    FakeClient(estimates),
                    _config(),
                    analysis_as_of=AS_OF,
                    snapshot_dir=snapshot_dir,
                    shard_index=shard,
                    shard_count=2,
                    resume=False,
                )
                self.assertEqual(result.exit_code, 0)
                self.assertEqual(result.summary["status"], "shard_complete")
            status = SNAP.snapshot_status(SNAP.load_manifest(snapshot_dir))
            self.assertTrue(status["all_shards_complete"])
            self.assertTrue(status["classification_matches_universe"])
            self.assertEqual(status["universe_count"], len(universe))
            totals = status["classified_totals"]
            self.assertEqual(totals["unit_mismatch"], 1)  # FRGN
            self.assertEqual(totals["no_estimates"], 1)  # NOEST
            self.assertEqual(totals["evaluable"], len(universe) - 2)

    def test_budget_exhaustion_is_partial_and_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir, universe = self._snapshot(tmp)
            estimates = self._estimates_for(universe)
            shard0 = [row for row in universe if SNAP.stable_shard(row["symbol"], 2) == 0]
            partial = PIPELINE.execute_collect_estimates(
                FakeClient(estimates, budget=3),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=2,
                resume=False,
            )
            self.assertEqual(partial.exit_code, 3)
            self.assertEqual(partial.summary["status"], "shard_partial_budget")
            self.assertTrue(partial.summary["budget_exhausted"])
            manifest = SNAP.load_manifest(snapshot_dir)
            self.assertEqual(manifest["shards"]["0"]["status"], "partial")
            self.assertEqual(manifest["shards"]["0"]["attempted"], 3)

            # a second run without --resume must refuse
            with self.assertRaises(ValueError):
                PIPELINE.execute_collect_estimates(
                    FakeClient(estimates),
                    _config(),
                    analysis_as_of=AS_OF,
                    snapshot_dir=snapshot_dir,
                    shard_index=0,
                    shard_count=2,
                    resume=False,
                )

            resumed = PIPELINE.execute_collect_estimates(
                FakeClient(estimates),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=2,
                resume=True,
            )
            self.assertEqual(resumed.exit_code, 0)
            manifest = SNAP.load_manifest(snapshot_dir)
            entry = manifest["shards"]["0"]
            self.assertEqual(entry["status"], "complete")
            self.assertEqual(entry["attempted"], len(shard0))
            rows = SNAP.load_shard_rows(snapshot_dir, 0)
            self.assertEqual(len({row["symbol"] for row in rows}), len(shard0))

    def test_shard_count_mismatch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir, _ = self._snapshot(tmp)
            with self.assertRaises(ValueError):
                PIPELINE.execute_collect_estimates(
                    FakeClient({}),
                    _config(),
                    analysis_as_of=AS_OF,
                    snapshot_dir=snapshot_dir,
                    shard_index=0,
                    shard_count=4,
                    resume=False,
                )


class CoverageSemanticsSharedTests(unittest.TestCase):
    def test_pipeline_and_evaluator_share_one_implementation(self) -> None:
        import evaluate_candidates as EVAL

        self.assertIs(PIPELINE.classify_ranking_scope, COV.classify_ranking_scope)
        # the evaluator delegates to the shared derive function
        self.assertIn(
            "derive_ranking_scope_from_audit", EVAL._derive_ranking_scope.__code__.co_names
        )

    def test_validate_coverage_block(self) -> None:
        block = COV.build_coverage_block(
            ranking_scope="final_scoped",
            listing_universe_count=2371,
            economic_attempt_count=180,
            economically_evaluable_count=98,
            quality_probe_count=35,
            deep_dive_count=3,
        )
        self.assertEqual(COV.validate_coverage_block(block), [])
        broken = dict(block)
        broken["economic_attempt_count"] = 5000
        problems = COV.validate_coverage_block(broken)
        self.assertTrue(any("exceeds listing_universe_count" in p for p in problems))
        broken2 = dict(block)
        broken2["ranking_scope"] = "complete"
        self.assertTrue(COV.validate_coverage_block(broken2))
        broken3 = dict(block)
        del broken3["economically_evaluable_count"]
        self.assertTrue(COV.validate_coverage_block(broken3))


class OfflineMissClient:
    """Simulates offline mode with an empty cache: an explicit failed status."""

    def get_analyst_estimates_detailed(
        self, symbol: str, *, period: str = "annual", limit: int = 6
    ) -> dict:
        return {"rows": [], "status": "failed", "served_from_cache": False, "retrieved_at": None}

    def diagnostics(self) -> dict:
        return {"api_calls_made": 0, "cache_hits": 0, "failure_count": 0}


class HttpFailClient:
    """Simulates HTTP failures: calls made, failures recorded, failed status."""

    def __init__(self) -> None:
        self.calls = 0

    def get_analyst_estimates_detailed(
        self, symbol: str, *, period: str = "annual", limit: int = 6
    ) -> dict:
        self.calls += 1
        return {"rows": [], "status": "failed", "served_from_cache": False, "retrieved_at": None}

    def diagnostics(self) -> dict:
        return {"api_calls_made": self.calls, "cache_hits": 0, "failure_count": self.calls}


class ProviderFailureTests(unittest.TestCase):
    """Round-2 review P0: provider failures must never classify as no_estimates."""

    def _run(self, client, snapshot_dir, resume=False):
        return PIPELINE.execute_collect_estimates(
            client,
            _config(),
            analysis_as_of=AS_OF,
            snapshot_dir=snapshot_dir,
            shard_index=0,
            shard_count=1,
            resume=resume,
        )

    def test_offline_empty_cache_is_fetch_failure_not_no_estimates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(
                snapshot_dir, [_listing("AAA"), _listing("BBB")], shard_count=1, as_of=AS_OF
            )
            result = self._run(OfflineMissClient(), snapshot_dir)
            self.assertEqual(result.exit_code, 3)
            self.assertEqual(result.summary["status"], "shard_partial_fetch_failures")
            self.assertEqual(result.summary["fetch_failed_count"], 2)
            self.assertEqual(result.summary["shard_classified"], {})
            status = SNAP.snapshot_status(SNAP.load_manifest(snapshot_dir))
            self.assertFalse(status["all_shards_complete"])
            self.assertFalse(status["classification_matches_universe"])

    def test_http_failures_are_fetch_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            result = self._run(HttpFailClient(), snapshot_dir)
            self.assertEqual(result.exit_code, 3)
            self.assertEqual(result.summary["fetch_failed_symbols"], ["AAA"])
            manifest = SNAP.load_manifest(snapshot_dir)
            self.assertEqual(manifest["shards"]["0"]["fetch_failed"], 1)
            self.assertEqual(manifest["shards"]["0"]["status"], "partial")

    def test_successful_empty_response_is_still_no_estimates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            result = self._run(FakeClient({"AAA": []}), snapshot_dir)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.summary["shard_classified"], {"no_estimates": 1})


class FrozenUniverseIntegrityTests(unittest.TestCase):
    """Round-2 review P0: a swapped universe.jsonl must be refused."""

    def test_tampered_universe_is_refused_before_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            tampered = _listing("ZZZ")
            import json as _json

            (snapshot_dir / SNAP.UNIVERSE_NAME).write_text(
                _json.dumps(tampered, sort_keys=True) + "\n", encoding="utf-8"
            )
            client = FakeClient({"ZZZ": _estimate_rows()})
            with self.assertRaises(ValueError):
                PIPELINE.execute_collect_estimates(
                    client,
                    _config(),
                    analysis_as_of=AS_OF,
                    snapshot_dir=snapshot_dir,
                    shard_index=0,
                    shard_count=1,
                    resume=False,
                )
            self.assertEqual(client.calls, 0)  # refused before any API access

    def test_count_mismatch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(
                snapshot_dir, [_listing("AAA"), _listing("BBB")], shard_count=1, as_of=AS_OF
            )
            content = (snapshot_dir / SNAP.UNIVERSE_NAME).read_text().splitlines()
            (snapshot_dir / SNAP.UNIVERSE_NAME).write_text(content[0] + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                SNAP.load_verified_universe(snapshot_dir, SNAP.load_manifest(snapshot_dir))


class FreshnessStampTests(unittest.TestCase):
    """Round-2 review P0: zero-collection runs must not refresh shard freshness."""

    def test_zero_collect_resume_preserves_as_of(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            estimates = {"AAA": _estimate_rows()}
            first = PIPELINE.execute_collect_estimates(
                FakeClient(estimates),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            self.assertEqual(first.exit_code, 0)
            original_as_of = SNAP.load_manifest(snapshot_dir)["shards"]["0"]["as_of"]
            later = AS_OF + timedelta(minutes=1)
            second = PIPELINE.execute_collect_estimates(
                FakeClient(estimates),
                _config(),
                analysis_as_of=later,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=True,
            )
            self.assertEqual(second.summary["collected_this_run"], 0)
            entry = SNAP.load_manifest(snapshot_dir)["shards"]["0"]
            self.assertEqual(entry["as_of"], original_as_of)
            self.assertIsNotNone(entry["oldest_retrieved_at"])
            self.assertIsNotNone(entry["newest_retrieved_at"])

    def test_rows_carry_actual_retrieval_stamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            PIPELINE.execute_collect_estimates(
                FakeClient({"AAA": _estimate_rows()}),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            [row] = SNAP.load_shard_rows(snapshot_dir, 0)
            self.assertIn("snapshot_retrieved_at", row)
            self.assertFalse(row["snapshot_served_from_cache"])


class NegativeEpsIntegrationTests(unittest.TestCase):
    """Round-2 review P1: negative_eps must be reachable through the real normalizer."""

    def test_negative_consensus_classifies_negative_eps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("NEG")], shard_count=1, as_of=AS_OF)
            result = PIPELINE.execute_collect_estimates(
                FakeClient({"NEG": _estimate_rows(fy1=-1.0)}),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            self.assertEqual(result.summary["shard_classified"], {"negative_eps": 1})


class _StubResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class Http200ErrorPayloadTests(unittest.TestCase):
    """Round-3 review P0: HTTP-200 error objects are failures, never data."""

    def _client(self, tmp: str, *, offline: bool = False, session_get=None):
        from fmp_client import FMPClient

        client = FMPClient(
            api_key="test-key",  # pragma: allowlist secret
            max_api_calls=10,
            cache_path=Path(tmp) / "cache.sqlite",
            raw_store_dir=Path(tmp) / "raw",
            offline=offline,
        )
        if session_get is not None:
            import types

            client.session = types.SimpleNamespace(get=session_get)
        return client

    def _stable_key(self, client, symbol: str) -> str:
        from fmp_client import SQLiteJsonCache

        return SQLiteJsonCache.make_key(
            f"{client.STABLE_URL}/analyst-estimates",
            {"symbol": symbol, "period": "annual", "limit": 6},
        )

    def test_http200_error_object_is_failure_and_never_cached(self) -> None:
        payload = {"Error Message": "plan limit reached"}
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(
                tmp, session_get=lambda url, params=None, timeout=None: _StubResponse(200, payload)
            )
            self.assertEqual(client.get_analyst_estimates("AAA"), [])
            diag = client.diagnostics()
            self.assertGreaterEqual(diag["failure_count"], 1)
            self.assertEqual(diag["cache_hits"], 0)
            self.assertIsNone(client.cache.get(self._stable_key(client, "AAA"), 10**9))

    def test_previously_cached_error_object_is_purged_and_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp, offline=True)
            key = self._stable_key(client, "AAA")
            client.cache.put(key, {"Error Message": "poisoned"})
            result = client.get_analyst_estimates_detailed("AAA")
            self.assertEqual(result["status"], "failed")
            self.assertGreaterEqual(client.diagnostics()["failure_count"], 1)
            # the poisoned entry is purged so an online retry reaches HTTP
            self.assertIsNone(client.cache.get(key, 10**9))

    def test_error_object_inside_list_is_failure_and_never_cached(self) -> None:
        # Round-4 review P0: [{"Error Message": ...}] hid the outage one
        # level down and was accepted (and cached) as data.
        payload = [{"Error Message": "plan limit reached"}]
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(
                tmp, session_get=lambda url, params=None, timeout=None: _StubResponse(200, payload)
            )
            result = client.get_analyst_estimates_detailed("AAA")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["rows"], [])
            self.assertGreaterEqual(client.diagnostics()["failure_count"], 1)
            self.assertIsNone(client.cache.get(self._stable_key(client, "AAA"), 10**9))

    def test_poisoned_cache_is_purged_and_refetched_online(self) -> None:
        good = _estimate_rows()
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(
                tmp, session_get=lambda url, params=None, timeout=None: _StubResponse(200, good)
            )
            key = self._stable_key(client, "AAA")
            client.cache.put(key, [{"Error Message": "poisoned"}])
            result = client.get_analyst_estimates_detailed("AAA")
            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["served_from_cache"])
            self.assertEqual(len(result["rows"]), len(good))
            self.assertGreaterEqual(client.diagnostics()["failure_count"], 1)
            self.assertIsNotNone(client.cache.get(key, 10**9))  # replaced with valid data

    def test_nonempty_unusable_payload_is_failure_not_no_estimates(self) -> None:
        # Round-5 review P0: a non-empty payload that cannot yield a single
        # valid estimate period is unusable noise, not "no estimates".
        for payload in (
            [{"date": "not-a-date", "epsAvg": None}],
            [{"date": "2026-12-31", "epsAvg": None, "revenueAvg": None}],
            # round-6: truncation let a garbage suffix through
            [{"date": "2026-12-31garbage", "epsAvg": 2.0}],
            # round-6: an analyst COUNT is not an estimate value
            [{"date": "2026-12-31", "epsAvg": None, "revenueAvg": None, "numAnalystsEps": 4}],
        ):
            with tempfile.TemporaryDirectory() as tmp:
                client = self._client(
                    tmp,
                    session_get=lambda url, params=None, timeout=None, p=payload: _StubResponse(
                        200, p
                    ),
                )
                result = client.get_analyst_estimates_detailed("AAA")
                self.assertEqual(result["status"], "failed", payload)
                self.assertIsNone(client.cache.get(self._stable_key(client, "AAA"), 10**9))

    def test_stable_failure_with_v3_empty_success_is_no_estimates(self) -> None:
        # Round-4 review P1: stable HTTP 500 followed by a SUCCESSFUL empty
        # v3 response is a genuine empty consensus, not a fetch failure.
        def _get(url, params=None, timeout=None):
            if "/stable/" in url:
                return _StubResponse(500, None)
            return _StubResponse(200, [])

        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            client = self._client(tmp, session_get=_get)
            result = PIPELINE.execute_collect_estimates(
                client,
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.summary["status"], "shard_complete")
            self.assertEqual(result.summary["shard_classified"], {"no_estimates": 1})

    def test_cached_error_object_becomes_fetch_failure_in_collect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            client = self._client(tmp, offline=True)
            client.cache.put(self._stable_key(client, "AAA"), {"Error Message": "poisoned"})
            result = PIPELINE.execute_collect_estimates(
                client,
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            self.assertEqual(result.summary["status"], "shard_partial_fetch_failures")
            self.assertEqual(result.summary["shard_classified"], {})


class CacheProvenanceTests(unittest.TestCase):
    """Round-3 review P1: cache-served data keeps its original fetch time."""

    def test_stable_http_failure_with_v3_cache_hit_keeps_cache_time(self) -> None:
        import sqlite3 as _sqlite3
        import time as _time

        from fmp_client import FMPClient, SQLiteJsonCache

        # One hour ago: old enough to differ from "now", young enough to
        # survive the estimates cache TTL.
        fixed_created_at = float(int(_time.time() - 3600.0))
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("CPV")], shard_count=1, as_of=AS_OF)
            client = FMPClient(
                api_key="test-key",  # pragma: allowlist secret
                max_api_calls=10,
                cache_path=Path(tmp) / "cache.sqlite",
                raw_store_dir=Path(tmp) / "raw",
            )
            import types

            client.session = types.SimpleNamespace(
                get=lambda url, params=None, timeout=None: _StubResponse(500, None)
            )
            v3_key = SQLiteJsonCache.make_key(
                f"{client.V3_URL}/analyst-estimates/CPV", {"period": "annual", "limit": 6}
            )
            client.cache.put(v3_key, _estimate_rows())
            with _sqlite3.connect(str(client.cache.path)) as connection:
                connection.execute(
                    "UPDATE responses SET created_at = ? WHERE cache_key = ?",
                    (fixed_created_at, v3_key),
                )
                connection.commit()
            result = PIPELINE.execute_collect_estimates(
                client,
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            self.assertEqual(result.summary["shard_classified"], {"evaluable": 1})
            [row] = SNAP.load_shard_rows(snapshot_dir, 0)
            self.assertTrue(row["snapshot_served_from_cache"])
            expected = datetime.fromtimestamp(fixed_created_at, tz=timezone.utc).isoformat()
            self.assertEqual(row["snapshot_retrieved_at"], expected)

    def test_unknown_cache_provenance_stays_null(self) -> None:
        class UnknownCacheClient:
            def __init__(self, estimates):
                self._estimates = estimates
                self.hits = 0

            def get_analyst_estimates_detailed(
                self, symbol: str, *, period: str = "annual", limit: int = 6
            ) -> dict:
                self.hits += 1
                return {
                    "rows": self._estimates.get(symbol, []),
                    "status": "ok",
                    "served_from_cache": True,
                    "retrieved_at": None,
                }

            def diagnostics(self) -> dict:
                return {"api_calls_made": 0, "cache_hits": self.hits, "failure_count": 0}

        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            result = PIPELINE.execute_collect_estimates(
                UnknownCacheClient({"AAA": _estimate_rows()}),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            [row] = SNAP.load_shard_rows(snapshot_dir, 0)
            self.assertIsNone(row["snapshot_retrieved_at"])
            self.assertTrue(row["snapshot_served_from_cache"])
            self.assertEqual(result.summary["retrieval_time_unknown"], 1)
            entry = SNAP.load_manifest(snapshot_dir)["shards"]["0"]
            self.assertEqual(entry["retrieval_time_unknown"], 1)
            self.assertIsNone(entry["oldest_retrieved_at"])
            # Round-4 review: unknown provenance blocks screening readiness
            # even when collection itself is complete.
            status = SNAP.snapshot_status(SNAP.load_manifest(snapshot_dir))
            self.assertTrue(status["all_shards_complete"])
            self.assertFalse(status["freshness_provenance_complete"])
            self.assertFalse(status["collection_ready"])


class SnapshotReadinessTests(unittest.TestCase):
    """Round-4 review P1: readiness = collection + classification + provenance."""

    def test_clean_complete_snapshot_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            PIPELINE.execute_collect_estimates(
                FakeClient({"AAA": _estimate_rows()}),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            status = SNAP.snapshot_status(SNAP.load_manifest(snapshot_dir))
            self.assertTrue(status["all_shards_complete"])
            self.assertTrue(status["classification_matches_universe"])
            self.assertEqual(status["retrieval_time_unknown_total"], 0)
            self.assertEqual(status["fetch_failed_total"], 0)
            self.assertTrue(status["freshness_provenance_complete"])
            self.assertTrue(status["collection_ready"])
            self.assertNotIn("ready_for_screening", status)  # verify_snapshot only
            self.assertIsNotNone(status["oldest_retrieved_at"])
            self.assertIsNotNone(status["newest_retrieved_at"])

    def test_fetch_failures_block_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snap"
            SNAP.create_snapshot(snapshot_dir, [_listing("AAA")], shard_count=1, as_of=AS_OF)
            PIPELINE.execute_collect_estimates(
                OfflineMissClient(),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=False,
            )
            status = SNAP.snapshot_status(SNAP.load_manifest(snapshot_dir))
            self.assertGreaterEqual(status["fetch_failed_total"], 1)
            self.assertFalse(status["collection_ready"])


class SnapshotVerificationTests(unittest.TestCase):
    """Round-5 review P0: readiness must be proven against the ACTUAL files."""

    def _build_clean(self, tmp: str) -> Path:
        snapshot_dir = Path(tmp) / "snap"
        universe = [_listing("AAA"), _listing("BBB")]
        SNAP.create_snapshot(
            snapshot_dir,
            universe,
            shard_count=1,
            as_of=AS_OF,
            enumeration_audit=_enumeration_audit(universe),
        )
        result = PIPELINE.execute_collect_estimates(
            FakeClient({row["symbol"]: _estimate_rows() for row in universe}),
            _config(),
            analysis_as_of=AS_OF,
            snapshot_dir=snapshot_dir,
            shard_index=0,
            shard_count=1,
            resume=False,
        )
        assert result.exit_code == 0
        return snapshot_dir

    def _verify(self, snapshot_dir: Path, **overrides) -> dict:
        kwargs = {
            "screening_as_of": datetime.now(timezone.utc),
            "max_staleness_days": 7.0,
        }
        kwargs.update(overrides)
        return SNAP.verify_snapshot(snapshot_dir, **kwargs)

    def test_clean_snapshot_verifies_and_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            verdict = self._verify(self._build_clean(tmp))
            self.assertTrue(verdict["contents_verified"], verdict["problems"])
            self.assertTrue(verdict["staleness_ok"])
            self.assertTrue(verdict["ready_for_screening"])

    def test_swapped_shard_symbol_is_detected(self) -> None:
        # The reviewer's reproduction: freeze AAA+BBB, then swap AAA -> ZZZ
        # inside the shard file. Manifest counters still balance.
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = self._build_clean(tmp)
            path = SNAP.shard_path(snapshot_dir, 0)
            path.write_text(path.read_text().replace('"symbol": "AAA"', '"symbol": "ZZZ"'))
            self.assertTrue(
                SNAP.snapshot_status(SNAP.load_manifest(snapshot_dir))["collection_ready"]
            )
            verdict = self._verify(snapshot_dir)
            self.assertFalse(verdict["contents_verified"])
            self.assertFalse(verdict["ready_for_screening"])
            text = " ".join(verdict["problems"])
            self.assertIn("ZZZ", text)
            self.assertIn("AAA", text)  # AAA reported as never collected

    def test_missing_shard_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = self._build_clean(tmp)
            SNAP.shard_path(snapshot_dir, 0).unlink()
            verdict = self._verify(snapshot_dir)
            self.assertFalse(verdict["ready_for_screening"])
            self.assertTrue(any("file missing" in p for p in verdict["problems"]))

    def test_duplicate_symbol_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = self._build_clean(tmp)
            [row, *_] = SNAP.load_shard_rows(snapshot_dir, 0)
            SNAP.append_shard_rows(snapshot_dir, 0, [row])
            verdict = self._verify(snapshot_dir)
            self.assertFalse(verdict["ready_for_screening"])
            self.assertTrue(any("duplicate symbol" in p for p in verdict["problems"]))

    def test_future_data_blocks_historical_screening(self) -> None:
        # Round-6 review P0: a 2026-collected snapshot must never be "ready"
        # for a 2020 screening_as_of — that is look-ahead.
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = self._build_clean(tmp)
            verdict = self._verify(
                snapshot_dir,
                screening_as_of=datetime(2020, 1, 1, tzinfo=timezone.utc),
                max_staleness_days=36500.0,
            )
            self.assertTrue(verdict["contents_verified"])
            self.assertFalse(verdict["no_future_retrievals"])
            self.assertFalse(verdict["ready_for_screening"])

    def test_missing_shard_sha_is_detected(self) -> None:
        # Round-6 review P1: an unpinned shard (pre-SHA collection) must not
        # verify; a zero-collect --resume backfills the SHA.
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = self._build_clean(tmp)
            manifest = SNAP.load_manifest(snapshot_dir)
            del manifest["shards"]["0"]["shard_sha256"]
            SNAP.write_manifest(snapshot_dir, manifest)
            verdict = self._verify(snapshot_dir)
            self.assertFalse(verdict["ready_for_screening"])
            self.assertTrue(any("shard_sha256" in p for p in verdict["problems"]))
            resumed = PIPELINE.execute_collect_estimates(
                FakeClient({}),
                _config(),
                analysis_as_of=AS_OF,
                snapshot_dir=snapshot_dir,
                shard_index=0,
                shard_count=1,
                resume=True,
            )
            self.assertEqual(resumed.summary["collected_this_run"], 0)
            verdict = self._verify(snapshot_dir)
            self.assertTrue(verdict["ready_for_screening"], verdict["problems"])

    def test_stale_snapshot_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = self._build_clean(tmp)
            future = datetime.now(timezone.utc) + timedelta(days=30)
            verdict = self._verify(snapshot_dir, screening_as_of=future, max_staleness_days=1.0)
            self.assertTrue(verdict["contents_verified"])
            self.assertFalse(verdict["staleness_ok"])
            self.assertFalse(verdict["ready_for_screening"])


if __name__ == "__main__":
    unittest.main()
