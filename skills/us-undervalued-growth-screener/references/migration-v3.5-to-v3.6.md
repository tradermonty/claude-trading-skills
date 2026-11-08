# Migration v3.5 → v3.6

v3.6 changes the preferred execution architecture while retaining schema 3 and the contract-3.5 underwriting/evaluation semantics.

## Runtime identity

```text
skill_version       = 3.6.0
schema_version      = 3
contract_revision   = 3.5
runtime_fingerprint = ug-v3.6-claude-code-direct-fmp-20260829
```

Do not reuse v3.5 audits or checkpoints. The evidence schema is compatible, but runtime identity is intentionally different so a cached package cannot be mistaken for the direct-FMP release.

## New preferred path

```bash
export FMP_API_KEY="..."
python3 skills/us-undervalued-growth-screener/scripts/run_pipeline.py \
  --config skills/us-undervalued-growth-screener/assets/claude-code-config.example.json \
  --output-dir reports/us-undervalued-growth-screener
```

The runner keeps bulk FMP responses on disk, uses a persistent SQLite cache, normalizes FY1 estimates, validates 20-day ADDV, builds the four discovery lanes, and prints only a compact run summary. Claude Code then reads selected candidate packets and performs the existing SEC/IR underwriting and strict final sequence.

## Reused central infrastructure

The skill's `fmp_client.py` is generated from the repository-level `scripts/fmp_client/` source of truth. Run the following repository-maintenance commands from the repository root:

<!-- exec: offline -->
```bash
python3 scripts/generate_fmp_client.py
python3 scripts/generate_fmp_client.py --check
```

## New files

- `scripts/fmp_client/specials/garp.py.tmpl`
- generated `skills/us-undervalued-growth-screener/scripts/fmp_client.py`
- `skills/us-undervalued-growth-screener/scripts/run_pipeline.py`
- `skills/us-undervalued-growth-screener/assets/claude-code-config.example.json`
- `skills/us-undervalued-growth-screener/references/claude-code-execution.md`
- `commands/us-undervalued-growth-screen.md`

## Operational changes

- Direct FMP HTTP calls replace bulk FMP MCP calls in Claude Code.
- Adaptive market-cap-band splitting prevents silent company-screener truncation.
- Bulk analyst-estimate and EOD endpoints are attempted first; bounded per-symbol fallbacks remain available.
- Exact liquidity work is allocated by GARP opportunity lane.
- Raw provider payloads are never printed to stdout and should not be loaded into model context.
- The Claude Code default deep-dive commitment is three names.
- `evaluate_candidates.py`, `prepublish_audit.py`, and `bundle_run_artifacts.py` remain the publication gates.
