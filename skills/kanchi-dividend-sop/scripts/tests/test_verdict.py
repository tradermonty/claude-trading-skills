"""WS-5 verdict-synthesis tests (offline, deterministic)."""

from verdict import build_run_context, evidence_ref, synthesize_verdict, worst


def test_clean_pass_when_all_green():
    v = synthesize_verdict(
        step1_verdict="STEP1-PASS",
        safety_verdict="PASS",
        event_verdict_cap=None,
        pre_order_blockers=[],
    )
    assert v.verdict == "CLEAN-PASS" and v.t1_blocked is False


def test_pass_caution_when_blockers_present():
    v = synthesize_verdict(
        step1_verdict="STEP1-PASS",
        safety_verdict="PASS",
        event_verdict_cap=None,
        pre_order_blockers=["bank_npl_nco_deteriorating"],
    )
    assert v.verdict == "PASS-CAUTION"


def test_step1_fail_is_fail():
    v = synthesize_verdict(step1_verdict="FAIL", safety_verdict="PASS", event_verdict_cap=None)
    assert v.verdict == "FAIL" and v.t1_blocked is True


def test_step1_recheck_dominates_d5():
    v = synthesize_verdict(
        step1_verdict="STEP1-RECHECK", safety_verdict="PASS", event_verdict_cap=None
    )
    assert v.verdict == "STEP1-RECHECK" and v.t1_blocked is True


def test_event_major_caps_hold_review():
    v = synthesize_verdict(
        step1_verdict="STEP1-PASS",
        safety_verdict="PASS",
        event_verdict_cap="HOLD-REVIEW",
        event_t1_blocked=True,
    )
    assert v.verdict == "HOLD-REVIEW" and v.t1_blocked is True


def test_freeze_with_clean_safety_is_conditional_pass():
    # CMCSA-style: frozen dividend but income/FCF safety strong.
    v = synthesize_verdict(
        step1_verdict="HOLD-REVIEW",
        safety_verdict="PASS",
        event_verdict_cap=None,
        pre_order_blockers=[],
    )
    assert v.verdict == "CONDITIONAL-PASS"


def test_freeze_with_blockers_is_hold_review():
    v = synthesize_verdict(
        step1_verdict="HOLD-REVIEW",
        safety_verdict="CAUTION",
        event_verdict_cap=None,
        pre_order_blockers=["adjusted_eps_unavailable"],
    )
    assert v.verdict == "HOLD-REVIEW"


def test_worst_picks_lowest_tier():
    assert worst(["CLEAN-PASS", "HOLD-REVIEW", "PASS-CAUTION"]) == "HOLD-REVIEW"
    assert worst(["CLEAN-PASS", "PASS-CAUTION"]) == "PASS-CAUTION"


def test_run_context_carries_profile_guard():
    ctx = build_run_context(
        profile="balanced",
        yield_floor_pct=3.0,
        safety_bias="medium",
        universe_source="finviz",
        excluded_asset_types=["reit", "bdc"],
    )
    assert ctx["yield_floor_pct"] == 3.0 and "bdc" in ctx["excluded_asset_types"]


def test_evidence_ref_shape():
    e = evidence_ref(
        "CMCSA dividend maintained at $1.32",
        source_type="issuer_ir",
        source_url="https://example",
        confidence="high",
    )
    assert e["claim"].startswith("CMCSA") and e["confidence"] == "high"
