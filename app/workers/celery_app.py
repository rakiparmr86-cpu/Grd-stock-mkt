"""Celery application. Run:

    celery -A app.workers.celery_app worker -l info
    celery -A app.workers.celery_app beat   -l info
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import setup_logging, task_failure

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.workers.beat_schedule import build_beat_schedule

log = get_logger(__name__)

celery_app = Celery(
    "grd_stk_mkt",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.market_data",
        "app.workers.tasks.analysis",
        "app.workers.tasks.rag",
        "app.workers.tasks.inputs",
        "app.workers.tasks.notifications",
    ],
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_max_tasks_per_child=200,
    result_expires=3 * 24 * 3600,
    timezone="Asia/Kolkata",
    enable_utc=True,
    beat_schedule=build_beat_schedule(),
)


@setup_logging.connect
def _use_app_logging(**_kwargs) -> None:
    """Stop Celery hijacking the root logger — keep our console + file handlers
    so worker/beat exceptions land in ``errors.log`` too."""
    configure_logging()


@task_failure.connect
def _log_task_failure(sender=None, task_id=None, exception=None, einfo=None, **_kw) -> None:
    """Guarantee every failed task writes a traceback to the exception log,
    even if the task body didn't call ``log.exception``."""
    logging.getLogger("celery.task").error(
        "task %s[%s] failed: %r",
        getattr(sender, "name", sender), task_id, exception,
        exc_info=einfo.exc_info if einfo is not None else True,
    )
