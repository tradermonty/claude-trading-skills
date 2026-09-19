"""Budget refusal must not invent provider spend or destroy selection history."""

import copy
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_pipeline as PIPELINE


@pytest.mark.parametrize("operation", ["get_key_metrics_ttm", "get_income_statement"])
@pytest.mark.parametrize(
    "consumed,refused", [(0, True), (1, True), (0, False), (1, False), (2, False)]
)
def test_probe_counts_provider_budget_units(operation, consumed, refused):
    class Client:
        api_calls_made = 7  # Prior stages must not leak into this stage's audit.

        def call(self, name):
            self.api_calls_made += consumed if name == operation else 1
            if name == operation and refused:
                raise PIPELINE.ApiCallBudgetExceeded("test budget stop")
            return []

        def get_key_metrics_ttm(self, symbol):
            return self.call("get_key_metrics_ttm")

        def get_income_statement(self, symbol, **kwargs):
            return self.call("get_income_statement")

    client = Client()
    _, audit = PIPELINE.apply_quality_probe(
        client,
        [{"symbol": "AAA"}],
        target_symbols=["AAA"],
        source_id="test",
        analysis_as_of=datetime(2026, 9, 19, tzinfo=timezone.utc),
        return_partial_on_budget=True,
    )
    income_reached = operation == "get_income_statement" or not refused
    assert audit["actual_eps_calls"] == (
        consumed if operation == "get_income_statement" else int(income_reached)
    )
    assert audit["calls_used"] == client.api_calls_made - 7
    assert audit["budget_exhausted"] is refused
    assert audit["attempted_symbols"] == ["AAA"]


def test_real_client_refuses_first_income_call_without_counting_it(tmp_path):
    client = PIPELINE.FMPClient(
        api_key="test",  # pragma: allowlist secret - mocked transport only
        max_api_calls=1,
        cache_path=tmp_path / "cache.sqlite",
        rate_limit_delay=0,
    )
    response = mock.Mock(status_code=200)
    response.json.return_value = []
    try:
        with mock.patch.object(client.session, "get", return_value=response) as get:
            _, audit = PIPELINE.apply_quality_probe(
                client,
                [{"symbol": "AAA"}],
                target_symbols=["AAA"],
                source_id="test",
                analysis_as_of=datetime(2026, 9, 19, tzinfo=timezone.utc),
                return_partial_on_budget=True,
            )
        assert get.call_count == 1
        assert audit["actual_eps_calls"] == 0
        assert audit["calls_used"] == 1
        assert audit["interrupted_at"]["operation"] == "get_income_statement"
    finally:
        client.close()


@pytest.mark.parametrize("status", ["selected", "rejected", "deferred_by_budget"])
def test_invalidation_preserves_original_audit_without_selection_authority(status):
    rows = [
        {
            "symbol": "AAA",
            "selection_eligible": status == "selected",
            "selection_lane": "growth",
            "decision": {
                "status": status,
                "selection_eligible": status == "selected",
                "preselection_status": "eligible",
                "selection_lane": "growth",
                "selection_reason": {"reason": ["original"]},
            },
        }
    ]
    before = copy.deepcopy(rows)
    result = PIPELINE._invalidate_candidate_decisions(rows)
    assert rows == before
    assert result[0]["prior_decision"] == before[0]["decision"]
    assert result[0]["prior_selection"] == {
        "selection_eligible": status == "selected",
        "selection_lane": "growth",
    }
    assert result[0]["decision"] == {"status": "deferred_by_budget", "selection_eligible": False}
    assert result[0]["selection_eligible"] is False
    assert "selection_lane" not in result[0]
    assert PIPELINE._invalidate_candidate_decisions(result) == result
    rows[0]["decision"]["selection_reason"]["reason"].append("changed")
    assert result[0]["prior_decision"] == before[0]["decision"]


@pytest.mark.parametrize("refused", [False, True])
def test_client_without_counter_uses_completed_logical_calls(refused):
    class Client:
        def get_key_metrics_ttm(self, symbol):
            return []

        def get_income_statement(self, symbol, **kwargs):
            if refused:
                raise PIPELINE.ApiCallBudgetExceeded("test budget stop")
            return []

    _, audit = PIPELINE.apply_quality_probe(
        Client(),
        [{"symbol": "AAA"}],
        target_symbols=["AAA"],
        source_id="test",
        analysis_as_of=datetime(2026, 9, 19, tzinfo=timezone.utc),
        return_partial_on_budget=True,
    )
    assert audit["actual_eps_calls"] == int(not refused)
    assert audit["calls_used"] == 1 + int(not refused)
