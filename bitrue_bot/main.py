from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .config import load_runtime_config
from .engine import TradingEngine


CONFIG_PATH = os.getenv("BITRUE_BOT_CONFIG", "config/bitrue_bot.example.json")

app = FastAPI(title="Bitrue Spot Bot", version="0.1.0")
engine = TradingEngine(load_runtime_config(CONFIG_PATH))


class RuntimeControlPayload(BaseModel):
    kill_switch: bool | None = None
    disabled_symbols: list[str] | None = None
    notes: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": engine.config.settings.mode.value}


@app.get("/positions")
def positions() -> dict:
    return engine.get_positions()


@app.get("/control")
def control() -> dict:
    return engine.get_runtime_control()


@app.post("/control")
def update_control(payload: RuntimeControlPayload) -> JSONResponse:
    try:
        result = engine.update_runtime_control(
            kill_switch=payload.kill_switch,
            disabled_symbols=payload.disabled_symbols,
            notes=payload.notes,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse({"status": "ok", "control": result})


@app.post("/reconcile")
def reconcile() -> JSONResponse:
    try:
        result = engine.reconcile_positions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse({"status": "ok", "positions": result})


@app.post("/webhook/tradingview")
def tradingview_webhook(payload: dict, request: Request) -> JSONResponse:
    try:
        supplied_secret = payload.get("secret") or payload.get("webhook_secret")
        auth_result = engine.security.authorize_webhook(
            request.client.host if request.client else None,
            str(supplied_secret) if supplied_secret is not None else None,
        )
        if not auth_result.allowed:
            raise HTTPException(status_code=403, detail=auth_result.reason)

        sanitized_payload = dict(payload)
        sanitized_payload.pop("secret", None)
        sanitized_payload.pop("webhook_secret", None)
        result = engine.handle_webhook_payload(sanitized_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(result)
