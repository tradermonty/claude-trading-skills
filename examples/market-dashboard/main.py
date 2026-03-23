"""FastAPI application — market dashboard."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER, CACHE_DIR, DETAIL_ROUTES, ROOT, SKILLS_ROOT, SIGNAL_PANEL_SKILLS, SKILL_REGISTRY
from scheduler import create_scheduler
from settings_manager import SettingsManager
from skills_runner import SkillsRunner
from alpaca_client import AlpacaClient
from ibkr_client import IBKRClient
from universe_builder import UniverseBuilder
from learning.rule_store import RuleStore
from learning.pattern_extractor import PatternExtractor
from learning.multiplier_store import MultiplierStore
from learning.pdt_tracker import PDTTracker
from learning.drawdown_tracker import DrawdownTracker
from learning.earnings_blackout import EarningsBlackout
from pivot_monitor import PivotWatchlistMonitor

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
try:
    ibkr = IBKRClient(paper=ALPACA_PAPER)
except Exception as _ibkr_exc:
    import sys as _sys
    print(f"[main] IBKRClient init failed: {_ibkr_exc}", file=_sys.stderr)

    class _IBKRStub:
        is_configured = False

    ibkr = _IBKRStub()  # type: ignore[assignment]
rule_store = RuleStore()  # defaults to learning/learned_rules.json
multiplier_store = MultiplierStore()  # uses learning/seed_multipliers.json + learning/learned_multipliers.json
from learning.time_of_day_tracker import TimeOfDayTracker
from learning.stop_distance_store import StopDistanceStore
from learning.experiment_tracker import ExperimentTracker

time_of_day_tracker = TimeOfDayTracker()
stop_distance_store = StopDistanceStore()
experiment_tracker = ExperimentTracker(is_paper=ALPACA_PAPER)
pdt_tracker = PDTTracker()
drawdown_tracker = DrawdownTracker()
earnings_blackout = EarningsBlackout(cache_dir=CACHE_DIR)
_us_market_config = {
    "id": "us",
    "label": "US (NYSE/NASDAQ)",
    "broker": "alpaca",
    "exchange": "SMART",
    "currency": "USD",
    "tz": "America/New_York",
    "open": "09:30",
    "close": "16:00",
    "pdt_enabled": True,
    "enabled": True,
}
pivot_monitor = PivotWatchlistMonitor(
    broker_client=alpaca,
    settings_manager=settings_manager,
    cache_dir=CACHE_DIR,
    market_config=_us_market_config,
    pdt_enabled=True,
    rule_store=rule_store,
    multiplier_store=multiplier_store,
    pdt_tracker=pdt_tracker,
    drawdown_tracker=drawdown_tracker,
    earnings_blackout=earnings_blackout,
)
pattern_extractor = PatternExtractor(
    alpaca_client=alpaca,
    rule_store=rule_store,
    cache_dir=CACHE_DIR,
    multiplier_store=multiplier_store,
    time_of_day_tracker=time_of_day_tracker,
    stop_distance_store=stop_distance_store,
    experiment_tracker=experiment_tracker,
)

# Module-level broker map
_broker_map = {"alpaca": alpaca, "ibkr": ibkr}
_monitors: list[PivotWatchlistMonitor] = []


def _build_monitors() -> list[PivotWatchlistMonitor]:
    """Create one PivotWatchlistMonitor per enabled market."""
    import sys
    monitors = []
    for market in settings_manager.get_enabled_markets():
        broker = _broker_map.get(market.get("broker", "alpaca"), alpaca)
        if not broker.is_configured:
            print(
                f"[main] {market['id']}: broker not configured — skipping monitor",
                file=sys.stderr,
            )
            continue
        pdt_enabled = market.get("pdt_enabled", True)
        calendar_file = CACHE_DIR / f"{market['id']}-earnings-calendar.json"
        monitor = PivotWatchlistMonitor(
            broker_client=broker,
            settings_manager=settings_manager,
            cache_dir=CACHE_DIR,
            market_config=market,
            pdt_enabled=pdt_enabled,
            calendar_file=calendar_file if calendar_file.exists() else None,
            rule_store=rule_store,
            multiplier_store=multiplier_store,
            pdt_tracker=pdt_tracker if pdt_enabled else None,
            drawdown_tracker=drawdown_tracker,
        )
        monitors.append(monitor)
    return monitors


def _get_us_monitor() -> "PivotWatchlistMonitor | None":
    """Return the US market monitor (backward-compat for scheduler and status endpoint)."""
    for m in _monitors:
        if m._market_config.get("id") == "us":
            return m
    return _monitors[0] if _monitors else None


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
    global _scheduler, _monitors
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _monitors = _build_monitors()
    us_monitor = _get_us_monitor()
    _scheduler = create_scheduler(
        runner=runner,
        cache_dir=CACHE_DIR,
        pivot_monitor=us_monitor,
        pattern_extractor=pattern_extractor,
        ibkr_client=ibkr,
        settings_manager=settings_manager,
    )
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


def _read_regime(cache_dir: Path) -> str:
    """Extract current_regime string from macro-regime-detector cache."""
    try:
        data = json.loads((cache_dir / "macro-regime-detector.json").read_text())
        regime_data = data.get("regime", {})
        if isinstance(regime_data, dict):
            return regime_data.get("current_regime", "unknown")
        return str(regime_data).lower() if regime_data else "unknown"
    except Exception:
        return "unknown"


def _log_manual_trade(body: "OrderConfirmRequest", order_id: str, regime: str) -> None:
    """Append manual order to auto_trades.json so PatternExtractor can learn from it."""
    trades_file = CACHE_DIR / "auto_trades.json"
    try:
        data = json.loads(trades_file.read_text()) if trades_file.exists() else {"trades": []}
    except (json.JSONDecodeError, OSError):
        data = {"trades": []}
    from datetime import timezone
    data["trades"].append({
        "symbol": body.symbol,
        "order_id": order_id,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "entry_price": body.limit_price,
        "stop_price": body.stop_price,
        "qty": body.qty,
        "confidence_tag": body.confidence_tag,
        "screener": body.skill,
        "regime": regime,
        "outcome": None,
    })
    try:
        trades_file.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


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


@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    ctx = {
        "request": request,
        "settings": settings_manager.load(),
        "multiplier_stats": multiplier_store._load_learned(),
        "time_of_day": time_of_day_tracker.get_stats(),
        "experiments": experiment_tracker.get_stats(),
        "pdt_slots": pdt_tracker.slots_remaining(date.today()),
    }
    return templates.TemplateResponse("stats.html", ctx)


@app.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request):
    trades = []
    # Collect all per-market trade files: cache/*-auto_trades.json
    trade_files = list(CACHE_DIR.glob("*-auto_trades.json"))
    # Backward compat: also check legacy auto_trades.json (no market prefix)
    legacy_file = CACHE_DIR / "auto_trades.json"
    if legacy_file.exists() and legacy_file not in trade_files:
        trade_files.append(legacy_file)

    for trade_file in trade_files:
        try:
            data = json.loads(trade_file.read_text())
            file_trades = data.get("trades", [])
            # Inject market field from filename if missing
            market_id = trade_file.stem.replace("-auto_trades", "")
            for t in file_trades:
                if "market" not in t:
                    t["market"] = market_id if market_id != "auto_trades" else "us"
            trades.extend(file_trades)
        except Exception:
            continue

    # Sort newest first by entry_time
    trades.sort(key=lambda t: t.get("entry_time", ""), reverse=True)

    # Pre-compute R for each trade
    for t in trades:
        try:
            risk = t["entry_price"] - t["stop_price"]
            if risk > 0 and t.get("exit_price"):
                t["r"] = round((t["exit_price"] - t["entry_price"]) / risk, 2)
            else:
                t["r"] = None
        except Exception:
            t["r"] = None

    # Summary stats
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
    open_trades = [t for t in trades if not t.get("outcome")]
    wins = [t for t in closed if t.get("outcome") == "win"]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else None
    r_values = [t["r"] for t in closed if t.get("r") is not None]
    avg_r = round(sum(r_values) / len(r_values), 2) if r_values else None

    ctx = {
        "request": request,
        "market_state": _market_state(),
        "settings": settings_manager.load(),
        "trades": trades,
        "total_trades": len(trades),
        "open_count": len(open_trades),
        "win_rate": win_rate,
        "avg_r": avg_r,
    }
    return templates.TemplateResponse("trades.html", ctx)


@app.get("/api/signals", response_class=HTMLResponse)
async def api_signals(request: Request):
    ctx = {"request": request, **_build_signals_context()}
    return templates.TemplateResponse("fragments/signals.html", ctx)


@app.get("/api/market-state")
async def api_market_state():
    return JSONResponse({"state": _market_state()})


@app.post("/api/order/preview", response_class=HTMLResponse)
async def order_preview(
    request: Request,
    symbol: str = Form(...),
    entry_price: float = Form(...),
    stop_price: float = Form(...),
    skill: str = Form(...),
):
    settings = settings_manager.load()
    if settings.get("mode") == "advisory":
        raise HTTPException(status_code=403, detail="Execute not available in Advisory mode")

    # Fetch live last price; fall back to screener's entry_price if Alpaca unavailable.
    # CANSLIM/PEAD screeners submit entry_price=0 since they have no price data.
    # When Alpaca is configured we always fetch live price (overrides any screener value).
    # When Alpaca is not configured, live_price stays at entry_price (0 for CANSLIM/PEAD).
    live_price = entry_price
    if alpaca.is_configured:
        try:
            live_price = alpaca.get_last_price(symbol)
        except Exception:
            pass

    # Default stop to 3% below entry when screener doesn't provide one (e.g. CANSLIM, PEAD).
    effective_stop = stop_price if stop_price > 0 else round(live_price * 0.97, 2)

    regime = _read_regime(CACHE_DIR)
    bucket_key = f"{skill}+CLEAR+{regime}"
    mult = multiplier_store.get(bucket_key)
    learned_bucket = multiplier_store._load_learned().get(bucket_key, {})
    n_real = len(learned_bucket.get("observed_rr", []))
    from learning.multiplier_store import MIN_SAMPLE_COUNT
    multiplier_source = (
        f"based on {n_real} {bucket_key} trades"
        if n_real >= MIN_SAMPLE_COUNT
        else "from published research"
    )

    account_value = 100_000.0  # fallback for unconfigured Alpaca
    if alpaca.is_configured:
        try:
            account_value = alpaca.get_account()["portfolio_value"]
        except Exception:
            pass

    ctx = {
        "request": request,
        "symbol": symbol,
        "skill": skill,
        "entry_price": round(live_price, 2),
        "stop_price": effective_stop,
        "account_value": account_value,
        "default_risk_pct": settings.get("default_risk_pct", 1.0),
        "multiplier": mult,
        "multiplier_source": multiplier_source,
    }
    return templates.TemplateResponse("fragments/order_preview.html", ctx)


class OrderConfirmRequest(BaseModel):
    symbol: str
    qty: int
    limit_price: float
    stop_price: float
    skill: str = "unknown"
    confidence_tag: str = "CLEAR"


@app.post("/api/order/confirm")
async def order_confirm(body: OrderConfirmRequest):
    settings = settings_manager.load()
    if settings.get("mode") == "advisory":
        raise HTTPException(status_code=403, detail="Execute not available in Advisory mode")
    if not alpaca.is_configured:
        return JSONResponse({"ok": False, "error": "Alpaca not configured — set API keys in .env"})

    regime = _read_regime(CACHE_DIR)
    bucket_key = f"{body.skill}+{body.confidence_tag}+{regime}"
    mult = multiplier_store.get(bucket_key)
    take_profit_price = round(body.limit_price + (body.limit_price - body.stop_price) * mult, 2)

    try:
        result = alpaca.place_bracket_order(
            symbol=body.symbol,
            qty=body.qty,
            limit_price=body.limit_price,
            stop_price=body.stop_price,
            take_profit_price=take_profit_price,
        )
        _log_manual_trade(body, result["id"], regime)
        return JSONResponse({"ok": True, "order_id": result["id"], "status": result["status"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


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


@app.get("/api/monitor/status")
async def monitor_status():
    """Return current PivotWatchlistMonitor state for the Auto mode banner."""
    monitor = _get_us_monitor()
    if monitor is None:
        return JSONResponse({"active": False, "candidate_count": 0, "triggered": []})
    with monitor._lock:
        candidates_snapshot = list(monitor._candidates)
        triggered_snapshot = list(monitor._triggered)
    return JSONResponse({
        "active": len(candidates_snapshot) > 0,
        "candidate_count": len(candidates_snapshot),
        "triggered": triggered_snapshot,
    })


@app.get("/api/broker-status")
async def broker_status():
    """Return connection status for each broker client."""
    return JSONResponse({
        "alpaca": alpaca.is_configured,
        "ibkr": ibkr.is_configured,
    })


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


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    ctx = {
        "request": request,
        "market_state": _market_state(),
        "settings": settings_manager.load(),
    }
    return templates.TemplateResponse("settings.html", ctx)


@app.post("/api/settings")
async def post_settings(
    request: Request,
    mode: str = Form(...),
    default_risk_pct: float = Form(...),
    max_positions: int = Form(...),
    max_position_size_pct: float = Form(...),
    environment: str = Form(...),
    live_confirm: str = Form(""),
    max_weekly_drawdown_pct: float = Form(10.0),
    max_daily_loss_pct: float = Form(5.0),
    earnings_blackout_days: int = Form(5),
    min_volume_ratio: float = Form(1.5),
    avoid_open_close_minutes: int = Form(30),
    breadth_threshold_pct: float = Form(60.0),
    breadth_size_reduction_pct: float = Form(50.0),
    trailing_stop_enabled: str = Form("true"),
    partial_exit_enabled: str = Form("true"),
    partial_exit_at_r: float = Form(1.0),
    partial_exit_pct: int = Form(50),
    time_stop_days: int = Form(5),
    kelly_sizing_enabled: str = Form("false"),
    kelly_max_multiplier: float = Form(2.0),
    vix_sizing_enabled: str = Form("true"),
):
    from fastapi.responses import RedirectResponse
    if environment == "live" and live_confirm != "CONFIRM LIVE TRADING":
        raise HTTPException(
            status_code=400,
            detail="Switching to Live requires typing 'CONFIRM LIVE TRADING'",
        )
    settings_manager.save({
        "mode": mode,
        "default_risk_pct": default_risk_pct,
        "max_positions": max_positions,
        "max_position_size_pct": max_position_size_pct,
        "environment": environment,
        "max_weekly_drawdown_pct": max_weekly_drawdown_pct,
        "max_daily_loss_pct": max_daily_loss_pct,
        "earnings_blackout_days": earnings_blackout_days,
        "min_volume_ratio": min_volume_ratio,
        "avoid_open_close_minutes": avoid_open_close_minutes,
        "breadth_threshold_pct": breadth_threshold_pct,
        "breadth_size_reduction_pct": breadth_size_reduction_pct,
        "trailing_stop_enabled": trailing_stop_enabled == "true",
        "partial_exit_enabled": partial_exit_enabled == "true",
        "partial_exit_at_r": partial_exit_at_r,
        "partial_exit_pct": partial_exit_pct,
        "time_stop_days": time_stop_days,
        "kelly_sizing_enabled": kelly_sizing_enabled == "true",
        "kelly_max_multiplier": kelly_max_multiplier,
        "vix_sizing_enabled": vix_sizing_enabled == "true",
    })
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/api/skill/{skill_name}/refresh")
async def skill_refresh(skill_name: str):
    if skill_name not in SKILL_REGISTRY:
        raise HTTPException(status_code=404, detail="Unknown skill")
    asyncio.get_running_loop().run_in_executor(None, runner.run_skill, skill_name)
    return Response(status_code=202)
