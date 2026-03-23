# Market Dashboard — CLAUDE.md

## What this is

Always-on FastAPI + HTMX market monitoring dashboard. Runs trading analysis skills on a background schedule, displays live TradingView charts, and shows skill signals with drill-down pages. This is Plan 1 (Level 1 Advisory). Plans 2 and 3 add Alpaca integration and Auto trading.

## How to start

```bash
cd examples/market-dashboard
cp .env.example .env    # fill in API keys
uv run uvicorn main:app --port 8000 --host 0.0.0.0
```

Use `--reload` during development only. In production, `--reload` watches the filesystem and will restart the server on every cache file write (because `cache/` is in the project directory). Do not use `--reload` in production.

To restart (kills any running instance first):
```bash
pkill -f "uvicorn main:app"; cd ~/claude-trading-skills/examples/market-dashboard && uv run uvicorn main:app --port 8000 --host 0.0.0.0
```

## Environment setup

1. Copy `.env.example` to `.env`
2. Set `FMP_API_KEY` — required for VCP, FTD, CANSLIM, Macro Regime, calendars
3. Set `FINVIZ_API_KEY` — optional, speeds up Theme Detector
4. Set `ANTHROPIC_API_KEY` — required only if a skill internally uses Claude
5. Alpaca keys — not needed for Plan 1; required for Plan 2

## How skills are invoked

Skills run as subprocesses via `skills_runner.py`. The runner:
- Injects API keys from `.env` into the subprocess environment
- Passes `--output-dir cache/` to each skill script
- After a successful run, renames the newest timestamped JSON to `cache/<skill-name>.json`
- Captures stderr to `cache/<skill-name>.stderr.log`
- Skill scripts are resolved relative to `SKILLS_ROOT` (two directories up from `market-dashboard/`)

To manually trigger a skill: `POST /api/skill/<skill-name>/refresh`

## Cache directory

`cache/` is auto-created on startup. The files are:
- `cache/<skill-name>.json` — latest successful output
- `cache/<skill-name>.stderr.log` — last run's stderr (for debugging failures)

Delete a `.json` file to force a refresh on the next scheduler tick. Delete `.stderr.log` files to clean up logs.

## Settings

Runtime mode and risk settings are stored in `settings.json` (auto-created on first save). To reset to `.env` defaults, delete `settings.json`. Do not edit `.env` for runtime settings — it is only read at startup.

## Testing

```bash
cd examples/market-dashboard
uv run pytest tests/ -v
```

## TDD requirement

Follow the repo-wide TDD-first workflow: write the failing test first, then implement the minimal code to pass it.
