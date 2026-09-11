"""Logging setup — console + rotating files.

Files (under ``LOG_DIR``, rotated at ``LOG_FILE_MAX_BYTES`` × ``LOG_FILE_BACKUPS``):

* ``app.log``    — everything at ``LOG_LEVEL`` and above
* ``errors.log`` — the **common exception log**: WARNING and above from anywhere
  in the backend (API + Celery), with full tracebacks (``logger.exception`` /
  ``exc_info=True``). Set ``LOG_DIR=""`` to disable file logging.

Both files get a day-separator banner before the first line of each calendar
day, e.g.::

    --------------------------=11-Sep-25-------------------------------------------------------
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"

_BANNER_LEFT_DASHES = 26
_BANNER_RIGHT_DASHES = 55


def _date_banner(day: date) -> str:
    return f"{'-' * _BANNER_LEFT_DASHES}={day.strftime('%d-%b-%y')}{'-' * _BANNER_RIGHT_DASHES}"


class DatedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that writes a ``_date_banner()`` line before the
    first record of each new calendar day (including the very first record
    ever written), so scanning the file shows where each day starts."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_banner_date: date | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.shouldRollover(record):
                self.doRollover()
                self._last_banner_date = None  # new file -> banner again
            today = datetime.fromtimestamp(record.created).date()
            if today != self._last_banner_date:
                self._last_banner_date = today
                # Also check the file itself: a different process (worker,
                # beat, a previous run today) may have already stamped it.
                if not self._tail_has_banner(_date_banner(today)):
                    if self.stream is None:
                        self.stream = self._open()
                    self.stream.write(_date_banner(today) + self.terminator)
                    self.stream.flush()
        except Exception:
            self.handleError(record)
        logging.FileHandler.emit(self, record)

    def _tail_has_banner(self, banner: str, window: int = 4096) -> bool:
        path = Path(self.baseFilename)
        try:
            size = path.stat().st_size
            if size == 0:
                return False
            with open(path, "rb") as f:
                f.seek(max(0, size - window))
                tail = f.read().decode("utf-8", errors="ignore")
        except OSError:
            return False
        return banner in tail


def _rotating(path: Path, level: int, fmt: logging.Formatter) -> DatedRotatingFileHandler:
    from app.core.config import settings

    h = DatedRotatingFileHandler(
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
