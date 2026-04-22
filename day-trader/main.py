"""FastAPI backend that serves the dashboard and exposes control endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import RISK_MODES
from db import get_events, get_trades, init_db, trade_stats
from trader import agent

STATIC_DIR = Path(__file__).parent / "static"


app = FastAPI(title="Day Trading Agent", version="1.0.0")


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ---------------------- control ----------------------

class StartReq(BaseModel):
    risk_mode: str = "medium"


@app.post("/api/start")
def start(req: StartReq):
    try:
        result = agent.start(req.risk_mode)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "start failed"))
    return result


class StopReq(BaseModel):
    liquidate: bool = False


@app.post("/api/stop")
def stop(req: StopReq):
    result = agent.stop(liquidate=req.liquidate)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "stop failed"))
    return result


@app.get("/api/status")
def status():
    return agent.status()


# ---------------------- data ----------------------

@app.get("/api/risk-modes")
def risk_modes():
    return {
        name: {
            "description": rm.description,
            "max_position_pct": rm.max_position_pct,
            "max_concurrent_positions": rm.max_concurrent_positions,
            "min_trade_dollars": rm.min_trade_dollars,
            "stop_loss_pct": rm.stop_loss_pct,
            "take_profit_pct": rm.take_profit_pct,
            "max_daily_loss_pct": rm.max_daily_loss_pct,
            "trailing_activation_pct": rm.trailing_activation_pct,
            "trailing_retrace_pct": rm.trailing_retrace_pct,
            "stagnation_minutes": rm.stagnation_minutes,
            "eod_flatten_minutes": rm.eod_flatten_minutes,
            "allow_shorts": rm.allow_shorts,
            "max_leverage": rm.max_leverage,
            "margin_call_threshold": rm.margin_call_threshold,
            "allowed_strategies": rm.allowed_strategies,
            "universe_size": len(rm.universe),
            "scan_interval_sec": rm.scan_interval_sec,
        }
        for name, rm in RISK_MODES.items()
    }


@app.get("/api/trades")
def trades(limit: int = 200):
    return {"trades": get_trades(limit=limit), "stats": trade_stats()}


@app.get("/api/events")
def events(limit: int = 300):
    return {"events": get_events(limit=limit)}


@app.post("/api/liquidate-all")
def liquidate_all():
    """Emergency: close all positions + cancel all orders, do NOT stop the agent."""
    try:
        agent.client.cancel_all_orders()
        agent.client.close_all_positions(cancel_orders=True)
        from db import log_event
        log_event("info", "Manual liquidate-all triggered via dashboard.",
                  risk_mode=agent.risk_mode.name)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------- static site ----------------------

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8787, reload=False)
