"""
Export Pydantic models from schemas/artifacts.py to JSON Schema files.

Usage
-----
    python schemas/export_json_schemas.py

Writes one .json file per artifact model to schemas/json/.
Also writes schemas/json/index.json listing all available schemas.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.artifacts import (  # noqa: E402
    ArtifactBase,
    BacktestReport,
    BacktestSpec,
    BreadthAssessment,
    DataQualityReport,
    DividendReview,
    ExposureDecision,
    JournalEntry,
    MacroRegimeReport,
    MarketTopRiskReport,
    PortfolioReview,
    PositionSizingPlan,
    PostmortemReport,
    ScenarioAnalysis,
    ScreenCandidate,
    StrategyReview,
    TechnicalValidation,
    TradePlan,
    TradeThesis,
    UptrendAssessment,
    WorkflowRun,
)

ARTIFACT_MODELS = [
    DataQualityReport,
    BreadthAssessment,
    UptrendAssessment,
    MarketTopRiskReport,
    MacroRegimeReport,
    ExposureDecision,
    ScreenCandidate,
    TechnicalValidation,
    PositionSizingPlan,
    TradePlan,
    TradeThesis,
    JournalEntry,
    PostmortemReport,
    BacktestSpec,
    BacktestReport,
    StrategyReview,
    PortfolioReview,
    DividendReview,
    ScenarioAnalysis,
    WorkflowRun,
]


def export_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    index: list[dict] = []

    for model in ARTIFACT_MODELS:
        artifact_type = getattr(model, "ARTIFACT_TYPE", model.__name__.lower())
        schema = model.model_json_schema()
        filename = f"{artifact_type}.json"
        path = output_dir / filename
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        index.append(
            {
                "artifact_type": artifact_type,
                "model": model.__name__,
                "schema_file": filename,
            }
        )
        print(f"  wrote {filename}")

    # Write index
    index_path = output_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote index.json ({len(index)} schemas)")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[1]
    out = repo_root / "schemas" / "json"
    print(f"Exporting JSON schemas to {out}/")
    export_schemas(out)
    print("Done.")
