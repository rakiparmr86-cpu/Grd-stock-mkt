"""FastAPI application entrypoint."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("starting %s (env=%s)", settings.app_name, settings.env)
    yield
    log.info("shutting down")


app = FastAPI(
    title="grd-stk-mkt",
    version="0.1.0",
    description="Multi-agent stock-market analysis platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # in dev, accept any localhost / 127.0.0.1 port (Vite may pick 5174, 5175, …)
    allow_origin_regex=(
        r"http://(localhost|127\.0\.0\.1)(:\d+)?" if settings.env == "dev" else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_unhandled_exceptions(request: Request, call_next):
    """Write any unhandled error (with traceback) to the exception log, then
    let Starlette produce its normal 500 / debug response."""
    try:
        return await call_next(request)
    except Exception:
        log.exception(
            "unhandled exception: %s %s", request.method, request.url.path
        )
        raise


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "docs": "/docs", "api": settings.api_v1_prefix}


@app.websocket("/ws/signals")
async def ws_signals(ws: WebSocket) -> None:
    """Push channel for live signals.

    A production build would subscribe to a Redis pub/sub channel that the
    analysis tasks publish to; here we accept the socket and echo pings so the
    frontend contract is stable.
    """
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                msg = {"type": "raw", "data": raw}
            await ws.send_json({"type": "ack", "echo": msg})
    except WebSocketDisconnect:
        log.info("ws client disconnected")
    except Exception:
        log.exception("ws/signals handler error")
