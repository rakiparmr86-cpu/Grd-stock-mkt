from __future__ import annotations

import logging

import pytest

import app.core.logging as L
from app.core.config import settings


@pytest.fixture
def fresh_logging(tmp_path, monkeypatch):
    """Point file logging at a tmp dir and force reconfiguration."""
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    monkeypatch.setattr(settings, "log_level", "INFO")
    monkeypatch.setattr(L, "_CONFIGURED", False)
    yield tmp_path
    # restore a clean console-only config for the rest of the suite
    for h in logging.getLogger().handlers[:]:
        try:
            h.close()
        except Exception:
            pass
    monkeypatch.setattr(L, "_CONFIGURED", False)
    L.configure_logging()


def test_exception_written_to_error_log_with_traceback(fresh_logging):
    L.configure_logging()
    logger = logging.getLogger("test.exc")
    try:
        raise ValueError("boom-42")
    except ValueError:
        logger.exception("handler blew up")

    errors = (fresh_logging / settings.error_log_file).read_text(encoding="utf-8")
    assert "handler blew up" in errors
    assert "ValueError: boom-42" in errors
    assert "Traceback (most recent call last)" in errors

    app_log = (fresh_logging / settings.log_file).read_text(encoding="utf-8")
    assert "handler blew up" in app_log


def test_info_not_in_error_log(fresh_logging):
    L.configure_logging()
    logging.getLogger("test.info").info("just fyi")

    assert "just fyi" in (fresh_logging / settings.log_file).read_text(encoding="utf-8")
    err_path = fresh_logging / settings.error_log_file
    err = err_path.read_text(encoding="utf-8") if err_path.exists() else ""
    assert "just fyi" not in err


def test_file_logging_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", "")
    monkeypatch.setattr(L, "_CONFIGURED", False)
    L.configure_logging()  # must not raise
    logging.getLogger("test.nofile").warning("no files here")
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(L, "_CONFIGURED", False)
    L.configure_logging()
