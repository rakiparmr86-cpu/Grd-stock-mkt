"""Persist an unexpected failure to the ``exception_logs`` table.

Complements ``log.exception(...)`` (text log, ephemeral, not queryable) —
call this alongside it at every genuine "this should not have happened"
catch site (an unhandled API exception, a websocket handler error, a Celery
task failure) so the Exceptions page has something to show and the user can
hard-delete an entry once it's understood/resolved.

Deliberately not used for expected/handled errors (a 404, a validation
error, an input source's own recorded ``last_error``) — those already have
a home and logging them here too would just be noise.
"""

from __future__ import annotations

import traceback as _traceback
from typing import Any

from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.history import ExceptionLog

log = get_logger(__name__)


def log_exception(
    source: str, exc: BaseException, *, context: dict[str, Any] | None = None,
) -> None:
    """``source`` is a short tag for where this came from (e.g. "api",
    "websocket", "run", "input_source") — shown as-is on the Exceptions page.
    Swallows its own failure (a broken exception logger must never mask the
    original exception or crash the caller)."""
    try:
        with session_scope() as db:
            db.add(ExceptionLog(
                source=source, message=str(exc)[:4000],
                traceback="".join(_traceback.format_exception(exc))[:20000],
                context=context or {},
            ))
    except Exception:  # noqa: BLE001
        log.exception("failed to persist exception log entry (source=%s)", source)
