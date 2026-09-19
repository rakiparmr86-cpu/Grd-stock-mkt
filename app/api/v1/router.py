from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1 import (
    activity,
    analysis,
    auth,
    exceptions,
    health,
    inputs,
    market,
    reports,
    rules,
    runs,
    signals,
    strategies,
    tasks,
    watchlists,
)

# every route in these routers requires a valid bearer token
_auth = [Depends(get_current_user)]

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(watchlists.router, prefix="/watchlists", tags=["watchlists"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(rules.router, prefix="/rules", tags=["rules"])
api_router.include_router(inputs.router, prefix="/inputs", tags=["inputs"], dependencies=_auth)
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(signals.router, prefix="/signals", tags=["signals"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"], dependencies=_auth)
api_router.include_router(
    analysis.router, prefix="/analysis", tags=["analysis"], dependencies=_auth
)
api_router.include_router(
    activity.router, prefix="/activity", tags=["activity"], dependencies=_auth
)
api_router.include_router(
    exceptions.router, prefix="/exceptions", tags=["exceptions"], dependencies=_auth
)
api_router.include_router(market.router, prefix="/market", tags=["market"], dependencies=_auth)
api_router.include_router(market.export_router, prefix="/market", tags=["market"])
