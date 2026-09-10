from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.inputs import InputSource
from app.schemas.inputs import (
    InputRunResponse,
    InputSourceCreate,
    InputSourceOut,
    InputSourceUpdate,
    InputTestRequest,
)
from app.services.inputs.registry import get_connector, list_connectors
from app.services.inputs.sink import run_connector

router = APIRouter()


@router.get("/connectors")
def connectors() -> list[dict]:
    """Available connector types + the config keys each one reads."""
    return list_connectors()


@router.get("", response_model=list[InputSourceOut])
def list_sources(db: DbSession) -> list[InputSource]:
    return list(db.execute(select(InputSource).order_by(InputSource.id)).scalars())


@router.post("", response_model=InputSourceOut, status_code=201)
def create_source(payload: InputSourceCreate, db: DbSession) -> InputSource:
    if db.execute(
        select(InputSource).where(InputSource.name == payload.name)
    ).scalar_one_or_none():
        raise HTTPException(409, "input source name already exists")
    # fail fast on a bad config
    try:
        get_connector(payload.connector, payload.config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"invalid connector config: {exc}") from exc
    src = InputSource(**payload.model_dump())
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


@router.get("/{source_id}", response_model=InputSourceOut)
def get_source(source_id: int, db: DbSession) -> InputSource:
    src = db.get(InputSource, source_id)
    if not src:
        raise HTTPException(404, "input source not found")
    return src


@router.patch("/{source_id}", response_model=InputSourceOut)
def update_source(source_id: int, payload: InputSourceUpdate, db: DbSession) -> InputSource:
    src = db.get(InputSource, source_id)
    if not src:
        raise HTTPException(404, "input source not found")
    data = payload.model_dump(exclude_unset=True)
    merged_connector = data.get("connector", src.connector)
    merged_config = data.get("config", src.config)
    if "connector" in data or "config" in data:
        try:
            get_connector(merged_connector, merged_config)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, f"invalid connector config: {exc}") from exc
    for k, v in data.items():
        setattr(src, k, v)
    db.commit()
    db.refresh(src)
    return src


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, db: DbSession) -> None:
    src = db.get(InputSource, source_id)
    if src:
        db.delete(src)
        db.commit()


@router.post("/{source_id}/run", response_model=InputRunResponse)
def run_source(source_id: int, db: DbSession, async_: bool = True) -> InputRunResponse:
    src = db.get(InputSource, source_id)
    if not src:
        raise HTTPException(404, "input source not found")
    if async_:
        from app.workers.tasks.inputs import run_input_source

        task = run_input_source.delay(source_id)
        return InputRunResponse(mode="async", task_id=task.id, source_id=source_id)

    conn = get_connector(src.connector, dict(src.config or {}))
    stats = run_connector(conn, source_name=src.name)
    src.last_stats = stats
    src.last_status = "error" if stats.get("errors") else "ok"
    db.commit()
    return InputRunResponse(mode="sync", source_id=source_id, stats=stats)


@router.post("/test", response_model=InputRunResponse)
def test_connector(payload: InputTestRequest) -> InputRunResponse:
    """Dry-run a connector config (no writes) and return capped stats.

    A crawler / API connector still performs real fetches — just nothing is
    persisted. Use a small ``max_results``.
    """
    try:
        conn = get_connector(payload.connector, payload.config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"invalid connector config: {exc}") from exc
    stats = run_connector(conn, source_name=f"test:{payload.connector}",
                          dry_run=True, max_results=payload.max_results)
    return InputRunResponse(mode="dry_run", stats=stats)
