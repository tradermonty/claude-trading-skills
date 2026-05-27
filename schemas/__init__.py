"""
TraderMonty canonical artifact schemas.

Every structured output produced by a skill or workflow step must conform to
one of the models defined in this package.  All models share a common base
(ArtifactBase) that carries identity, provenance, data-gap records, and the
mandatory decision-support disclaimer.

Usage
-----
    from schemas.artifacts import ExposureDecision, DataGap, Severity

    decision = ExposureDecision(
        artifact_id="exp-20260526-001",
        skill_id="exposure-coach",
        ceiling_pct=70,
        recommendation="NEW_ENTRY_ALLOWED",
        confidence="HIGH",
        bias="GROWTH",
        participation="BROAD",
        rationale="Broad breadth, low top-risk.",
        component_scores={},
        inputs_provided=["breadth", "uptrend"],
        inputs_missing=[],
        data_gaps=[],
    )
    print(decision.model_dump_json(indent=2))

JSON Schema export
------------------
    python schemas/export_json_schemas.py
"""
from schemas.artifacts import *  # noqa: F401, F403
