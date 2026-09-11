"""Check the status of an async Celery task by the id every ``mode: "async"``
response hands back (``POST /inputs/*``, ``POST /runs`` with ``async_: true``).

There's no way to tell a genuinely-still-queued task apart from a typo'd /
unknown task_id here — Celery's result backend only ever says "no result yet"
for both, which shows as PENDING. If a task stays PENDING for a long time,
the near-certain cause is **no Celery worker running** to consume the queue.
"""

from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter

from app.workers.celery_app import celery_app

router = APIRouter()

# Celery's own states, for reference: PENDING, STARTED, RETRY, SUCCESS, FAILURE.


@router.get("/{task_id}")
def get_task_status(task_id: str) -> dict:
    result = AsyncResult(task_id, app=celery_app)
    ready = result.ready()
    return {
        "task_id": task_id,
        "status": result.status,
        "ready": ready,
        "successful": result.successful() if ready else None,
        "result": result.result if ready and result.successful() else None,
        "error": str(result.result) if ready and result.failed() else None,
    }
