"""Celery application. Run:

    celery -A app.workers.celery_app worker -l info
    celery -A app.workers.celery_app beat   -l info
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings
from app.workers.beat_schedule import build_beat_schedule

celery_app = Celery(
    "grd_stk_mkt",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.market_data",
        "app.workers.tasks.analysis",
        "app.workers.tasks.rag",
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
