from fastapi import APIRouter

from app.api.v1 import (
    auth,
    health,
    inputs,
    reports,
    rules,
    runs,
    signals,
    strategies,
    watchlists,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(watchlists.router, prefix="/watchlists", tags=["watchlists"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(rules.router, prefix="/rules", tags=["rules"])
api_router.include_router(inputs.router, prefix="/inputs", tags=["inputs"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(signals.router, prefix="/signals", tags=["signals"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
