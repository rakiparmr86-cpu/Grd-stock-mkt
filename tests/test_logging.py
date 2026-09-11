from __future__ import annotations

import logging
from datetime import date

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


def test_date_banner_format():
    banner = L._date_banner(date(2025, 9, 11))
    assert banner == (
        "--------------------------=11-Sep-25"
        "-------------------------------------------------------"
    )
    assert len(banner) == 91


def test_date_banner_written_once_per_day(fresh_logging):
    L.configure_logging()
    log = logging.getLogger("test.banner")
    log.info("first")
    log.info("second")

    lines = (fresh_logging / settings.log_file).read_text(encoding="utf-8").splitlines()
    banner_lines = [ln for ln in lines if ln.startswith("-" * 26 + "=")]
    assert len(banner_lines) == 1  # not repeated for the 2nd record, same day
    assert banner_lines[0] == L._date_banner(date.today())
    assert lines.index(banner_lines[0]) < next(i for i, ln in enumerate(lines) if "first" in ln)


def test_date_banner_not_duplicated_across_handler_instances(fresh_logging):
    """Simulates two processes (e.g. api + worker) writing to the same file on
    the same day — the second handler must see the first one's banner and
    skip re-writing it."""
    path = fresh_logging / settings.log_file
    fmt = logging.Formatter(L._FORMAT, datefmt=L._DATEFMT)

    h1 = L._rotating(path, logging.INFO, fmt)
    logging.getLogger("test.proc1").handlers = []
    log1 = logging.getLogger("test.proc1")
    log1.addHandler(h1)
    log1.setLevel(logging.INFO)
    log1.propagate = False
    log1.info("from process 1")
    h1.close()

    h2 = L._rotating(path, logging.INFO, fmt)  # fresh instance, _last_banner_date=None
    log2 = logging.getLogger("test.proc2")
    log2.addHandler(h2)
    log2.setLevel(logging.INFO)
    log2.propagate = False
    log2.info("from process 2")
    h2.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    banner_lines = [ln for ln in lines if ln.startswith("-" * 26 + "=")]
    assert len(banner_lines) == 1
    assert any("from process 1" in ln for ln in lines)
    assert any("from process 2" in ln for ln in lines)


def test_file_logging_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", "")
    monkeypatch.setattr(L, "_CONFIGURED", False)
    L.configure_logging()  # must not raise
    logging.getLogger("test.nofile").warning("no files here")
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(L, "_CONFIGURED", False)
    L.configure_logging()
