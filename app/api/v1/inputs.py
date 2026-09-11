from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.deps import DbSession, InputSourceRepo
from app.models.inputs import InputSource
from app.schemas.inputs import (
    CrawlRequest,
    InputRunResponse,
    InputSourceCreate,
    InputSourceOut,
    InputSourceUpdate,
    InputTestRequest,
    UploadItemResult,
    UploadResponse,
)
from app.services.inputs.registry import get_connector, list_connectors
from app.services.inputs.sink import run_connector
from app.services.inputs.ssrf import UnsafeUrlError, assert_public_url
from app.services.inputs.upload import UploadError, connector_for_path, save_upload

router = APIRouter()


@router.get("/connectors")
def connectors() -> list[dict]:
    """Available connector types + the config keys each one reads."""
    return list_connectors()


@router.get("", response_model=list[InputSourceOut])
def list_sources(sources: InputSourceRepo) -> list[InputSource]:
    return sources.list_all()


@router.post("", response_model=InputSourceOut, status_code=201)
def create_source(payload: InputSourceCreate, db: DbSession,
                  sources: InputSourceRepo) -> InputSource:
    if sources.by_name(payload.name):
        raise HTTPException(409, "input source name already exists")
    # fail fast on a bad config
    try:
        get_connector(payload.connector, payload.config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"invalid connector config: {exc}") from exc
    src = sources.add(InputSource(**payload.model_dump()))
    db.commit()
    db.refresh(src)
    return src


@router.get("/{source_id}", response_model=InputSourceOut)
def get_source(source_id: int, sources: InputSourceRepo) -> InputSource:
    src = sources.get(source_id)
    if not src:
        raise HTTPException(404, "input source not found")
    return src


@router.patch("/{source_id}", response_model=InputSourceOut)
def update_source(source_id: int, payload: InputSourceUpdate, db: DbSession,
                  sources: InputSourceRepo) -> InputSource:
    src = sources.get(source_id)
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
def delete_source(source_id: int, db: DbSession, sources: InputSourceRepo) -> None:
    src = sources.get(source_id)
    if src:
        sources.delete(src)
        db.commit()


@router.post("/{source_id}/run", response_model=InputRunResponse)
def run_source(source_id: int, db: DbSession, sources: InputSourceRepo,
               async_: bool = True) -> InputRunResponse:
    src = sources.get(source_id)
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


# ── frontend-driven inputs ─────────────────────────────────────────
@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    db: DbSession,
    sources: InputSourceRepo,
    files: Annotated[list[UploadFile], File(description="one or more data/document files")],
    mode: Annotated[str, Form()] = "ingest_once",       # ingest_once | save_source
    excel_mode: Annotated[str, Form()] = "docs",         # docs | rows
    row_kind: Annotated[str, Form()] = "ohlcv",          # ohlcv | fundamental
    doc_type: Annotated[str | None, Form()] = None,
    ticker: Annotated[str | None, Form()] = None,
    name_prefix: Annotated[str | None, Form()] = None,   # for save_source
    schedule_cron: Annotated[str | None, Form()] = None,
    run_now: Annotated[bool, Form()] = True,
) -> UploadResponse:
    """Accept browser uploads (CSV / Excel / PDF / images).

    ``mode=ingest_once`` (default) queues a one-off ingest per file.
    ``mode=save_source`` also creates a reusable ``InputSource`` row (optionally
    scheduled) pointed at the stored file.
    """
    if mode not in ("ingest_once", "save_source"):
        raise HTTPException(422, "mode must be 'ingest_once' or 'save_source'")

    from app.workers.tasks.inputs import run_adhoc_connector, run_input_source

    items: list[UploadItemResult] = []
    for uf in files:
        try:
            data = await uf.read()
            path = save_upload(uf.filename or "upload.bin", data)
            connector, kind, cfg = connector_for_path(
                path, excel_mode=excel_mode, row_kind=row_kind,
                doc_type=doc_type, ticker=ticker,
            )
        except UploadError as exc:
            items.append(UploadItemResult(
                filename=uf.filename or "?", stored_path="", connector="", kind="docs",
                mode=mode, error=str(exc),
            ))
            continue

        res = UploadItemResult(filename=uf.filename or path.name, stored_path=str(path),
                               connector=connector, kind=kind, mode=mode)
        if mode == "save_source":
            base = (name_prefix or "Upload").strip()
            src = sources.add(InputSource(
                name=f"{base}: {path.name}", connector=connector,
                kind=kind, config=cfg, is_active=True, schedule_cron=schedule_cron,
            ))
            db.commit()
            db.refresh(src)
            res.source_id = src.id
            if run_now:
                res.task_id = run_input_source.delay(src.id).id
        elif run_now:
            res.task_id = run_adhoc_connector.delay(
                connector, cfg, f"upload:{path.name}"
            ).id
        items.append(res)

    return UploadResponse(items=items)


@router.post("/crawl", response_model=InputRunResponse)
def crawl_url(payload: CrawlRequest, db: DbSession, sources: InputSourceRepo) -> InputRunResponse:
    """Kick off a web crawl from URL(s) supplied by the frontend.

    Secrets never travel in this body — ``auth`` names environment variables
    (see DATA_FORMATS.md). Private / loopback hosts are refused unless
    ``CRAWLER_ALLOW_PRIVATE=true``.
    """
    for url in payload.urls:
        try:
            assert_public_url(url)
        except UnsafeUrlError as exc:
            raise HTTPException(422, f"unsafe URL {url!r}: {exc}") from exc

    cfg: dict = {
        "start_urls": payload.urls,
        "max_depth": payload.max_depth,
        "max_pages": payload.max_pages,
        "same_domain_only": payload.same_domain_only,
        "include_patterns": payload.include_patterns,
        "exclude_patterns": payload.exclude_patterns,
        "doc_type": payload.doc_type,
    }
    if payload.allowed_domains:
        cfg["allowed_domains"] = payload.allowed_domains
    if payload.delay_seconds is not None:
        cfg["delay_seconds"] = payload.delay_seconds
    if payload.auth:
        cfg["auth"] = payload.auth

    # validate the config now (raises on bad shape)
    try:
        get_connector("web_crawler", cfg)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"invalid crawl config: {exc}") from exc

    from app.workers.tasks.inputs import run_adhoc_connector, run_input_source

    if payload.save_as:
        src = sources.add(InputSource(
            name=payload.save_as, connector="web_crawler", kind="docs",
            config=cfg, is_active=payload.is_active, schedule_cron=payload.schedule_cron,
        ))
        db.commit()
        db.refresh(src)
        task = run_input_source.delay(src.id)
        return InputRunResponse(mode="async", task_id=task.id, source_id=src.id)

    task = run_adhoc_connector.delay("web_crawler", cfg, f"crawl:{payload.urls[0]}")
    return InputRunResponse(mode="async", task_id=task.id)


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
