"""Logging setup — console + rotating files.

Files (under ``LOG_DIR``, rotated at ``LOG_FILE_MAX_BYTES`` × ``LOG_FILE_BACKUPS``):

* ``app.log``    — everything at ``LOG_LEVEL`` and above
* ``errors.log`` — the **common exception log**: WARNING and above from anywhere
  in the backend (API + Celery), with full tracebacks (``logger.exception`` /
  ``exc_info=True``). Set ``LOG_DIR=""`` to disable file logging.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def _rotating(path: Path, level: int, fmt: logging.Formatter) -> RotatingFileHandler:
    from app.core.config import settings

    h = RotatingFileHandler(
        path,
        maxBytes=settings.log_file_max_bytes,
        backupCount=settings.log_file_backups,
        encoding="utf-8",
        delay=True,
    )
    h.setLevel(level)
    h.setFormatter(fmt)
    return h


def configure_logging(level: int | str | None = None) -> None:
    """Idempotent. Call once at process start (API lifespan, Celery setup)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    from app.core.config import settings

    lvl = level if level is not None else settings.log_level
    if isinstance(lvl, str):
        lvl = logging.getLevelName(lvl.upper())
    if not isinstance(lvl, int):
        lvl = logging.INFO

    fmt = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    handlers: list[logging.Handler] = []

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    stream.setLevel(lvl)
    handlers.append(stream)

    if settings.log_dir:
        try:
            log_dir = Path(settings.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            handlers.append(_rotating(log_dir / settings.log_file, lvl, fmt))
            handlers.append(
                _rotating(log_dir / settings.error_log_file, logging.WARNING, fmt)
            )
        except OSError as exc:  # read-only fs etc. — keep console logging
            stream.handle(
                logging.LogRecord(
                    "app.core.logging", logging.WARNING, __file__, 0,
                    "file logging disabled: %s", (exc,), None,
                )
            )

    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(min(lvl, logging.WARNING))  # let WARNING+ reach errors.log

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.captureWarnings(True)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
