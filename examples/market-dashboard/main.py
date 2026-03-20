"""FastAPI application — market dashboard."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER, CACHE_DIR, DETAIL_ROUTES, ROOT, SKILLS_ROOT, SIGNAL_PANEL_SKILLS, SKILL_REGISTRY
from scheduler import create_scheduler
from settings_manager import SettingsManager
from skills_runner import SkillsRunner
from alpaca_client import AlpacaClient

app = FastAPI(title="Market Dashboard")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

settings_manager = SettingsManager()
runner = SkillsRunner(cache_dir=CACHE_DIR, skills_root=SKILLS_ROOT)
alpaca = AlpacaClient(
    api_key=ALPACA_API_KEY,
    secret_key=ALPACA_SECRET_KEY,
    paper=ALPACA_PAPER,
)
_scheduler = None


async def _refresh_stale_on_startup():
    """On startup, refresh any cache files older than 2× their cadence."""
    loop = asyncio.get_running_loop()
    for skill_name in SKILL_REGISTRY:
        if SKILL_REGISTRY[skill_name].get("script") is None:
            continue
        if runner.is_stale(skill_name):
            loop.run_in_executor(None, runner.run_skill, skill_name)
            await asyncio.sleep(0.2)  # stagger launches to avoid API bursts


@app.on_event("startup")
async def startup():
    global _scheduler
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _scheduler = create_scheduler(runner=runner, cache_dir=CACHE_DIR)
    _scheduler.start()
    asyncio.create_task(_refresh_stale_on_startup())
    if alpaca.is_configured:
        asyncio.create_task(alpaca.start_trading_stream())


@app.on_event("shutdown")
async def shutdown():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()


def _market_state() -> str:
    """Return current market state string based on ET time."""
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
    weekday = now_et.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if weekday >= 5:
        return "market_closed"
    t = now_et.time()
    if t.hour < 7:
        return "market_closed"
    if t.hour < 9 or (t.hour == 9 and t.minute < 30):
        return "pre_market"
    if t.hour < 16:
        return "market_open"
    return "market_closed"


def _build_signals_context() -> dict[str, Any]:
    """Load signal panel data from cache."""
    signals = []
    for skill_name in SIGNAL_PANEL_SKILLS:
        data = runner.load_cache(skill_name)
        stale = runner.is_stale(skill_name)
        signals.append({
            "skill": skill_name,
            "data": data,
            "stale": stale,
        })
    return {"signals": signals}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = {
        "request": request,
        "market_state": _market_state(),
        "settings": settings_manager.load(),
        **_build_signals_context(),
    }
    return templates.TemplateResponse("dashboard.html", ctx)


@app.get("/api/signals", response_class=HTMLResponse)
async def api_signals(request: Request):
    ctx = {"request": request, **_build_signals_context()}
    return templates.TemplateResponse("fragments/signals.html", ctx)


@app.get("/api/market-state")
async def api_market_state():
    return JSONResponse({"state": _market_state()})


@app.get("/api/portfolio", response_class=HTMLResponse)
async def api_portfolio(request: Request):
    portfolio: dict = {"account": None, "positions": [], "error": None}
    if alpaca.is_configured:
        try:
            portfolio["account"] = alpaca.get_account()
            portfolio["positions"] = alpaca.get_positions()
        except Exception as e:
            portfolio["error"] = str(e)
    ctx = {"request": request, "portfolio": portfolio, "settings": settings_manager.load()}
    return templates.TemplateResponse("fragments/portfolio.html", ctx)


@app.get("/detail/{page}", response_class=HTMLResponse)
async def detail(request: Request, page: str):
    skill_name = DETAIL_ROUTES.get(page)
    if skill_name is None:
        raise HTTPException(status_code=404, detail="Unknown detail page")
    data = runner.load_cache(skill_name)
    stale = runner.is_stale(skill_name)
    ctx = {
        "request": request,
        "skill_name": skill_name,
        "page": page,
        "data": data,
        "stale": stale,
        "settings": settings_manager.load(),
    }
    return templates.TemplateResponse(f"detail/{page}.html", ctx)


@app.get("/api/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    ctx = {"request": request, "settings": settings_manager.load()}
    return templates.TemplateResponse("fragments/settings_modal.html", ctx)


@app.post("/api/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    mode: str = Form(...),
    default_risk_pct: float = Form(...),
    max_positions: int = Form(...),
    max_position_size_pct: float = Form(...),
    environment: str = Form(...),
):
    settings_manager.save({
        "mode": mode,
        "default_risk_pct": default_risk_pct,
        "max_positions": max_positions,
        "max_position_size_pct": max_position_size_pct,
        "environment": environment,
    })
    ctx = {"request": request, "settings": settings_manager.load()}
    return templates.TemplateResponse("fragments/settings_modal.html", ctx)


@app.post("/api/skill/{skill_name}/refresh")
async def skill_refresh(skill_name: str):
    if skill_name not in SKILL_REGISTRY:
        raise HTTPException(status_code=404, detail="Unknown skill")
    asyncio.get_running_loop().run_in_executor(None, runner.run_skill, skill_name)
    return Response(status_code=202)
