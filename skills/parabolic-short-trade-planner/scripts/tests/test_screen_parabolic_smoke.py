"""Smoke test: drive the Phase 1 pipeline against a fixture, no FMP calls.

Verifies that ``run_dry_run`` + ``build_json_report`` + ``write_outputs``
produce a valid v1.0 JSON, that the parabolic XYZ fixture survives all
filters, and that the flat CALM fixture is rejected (insufficient ROC /
extension). Acts as the executable schema contract for downstream skills.
"""

import json
from pathlib import Path

# screen_parabolic.py is a CLI module; import works because conftest puts
# the scripts dir on sys.path.
import screen_parabolic  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "dry_run_minimal.json"


def _make_args(**overrides):
    parser = screen_parabolic.build_arg_parser()
    args = parser.parse_args(
        [
            "--dry-run",
            "--fixture",
            str(FIXTURE_PATH),
            "--watch-min-grade",
            "D",
            "--min-roc-5d",
            "30",
            "--as-of",
            "2026-04-30",
        ]
    )
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


class TestDryRunPipeline:
    def test_xyz_survives_calm_rejected(self):
        args = _make_args()
        candidates = screen_parabolic.run_dry_run(str(FIXTURE_PATH), args)
        tickers = [c["ticker"] for c in candidates]
        assert "XYZ" in tickers
        assert "CALM" not in tickers

    def test_pipeline_writes_valid_v1_json(self, tmp_path):
        args = _make_args(output_dir=str(tmp_path), output_prefix="ps_smoke")
        candidates = screen_parabolic.run_dry_run(str(FIXTURE_PATH), args)
        report = screen_parabolic.build_json_report(
            candidates=candidates,
            mode=args.mode,
            universe=args.universe,
            as_of=args.as_of,
            data_source="fixture",
        )
        json_path, md_path = screen_parabolic.write_outputs(
            report, args.output_dir, args.output_prefix, args.as_of
        )
        # Verify JSON is well-formed and matches schema essentials
        loaded = json.loads(json_path.read_text())
        assert loaded["schema_version"] == "1.0"
        assert loaded["skill"] == "parabolic-short-trade-planner"
        assert loaded["phase"] == "screen"
        assert loaded["mode"] == "safe_largecap"
        assert loaded["data_source"] == "fixture"
        assert loaded["candidates_total"] == len(candidates)

        # Markdown must have header and the surviving ticker
        md = md_path.read_text()
        assert "Parabolic Short Watchlist" in md
        if candidates:
            assert candidates[0]["ticker"] in md


class TestMainCLI:
    def test_main_dry_run_returns_zero(self, tmp_path):
        rc = screen_parabolic.main(
            [
                "--dry-run",
                "--fixture",
                str(FIXTURE_PATH),
                "--output-dir",
                str(tmp_path),
                "--as-of",
                "2026-04-30",
                "--watch-min-grade",
                "D",
                "--min-roc-5d",
                "30",
            ]
        )
        assert rc == 0
        files = sorted(p.name for p in tmp_path.iterdir())
        assert any(f.endswith(".json") for f in files)
        assert any(f.endswith(".md") for f in files)
