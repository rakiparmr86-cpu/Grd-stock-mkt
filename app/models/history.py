"""Analysis history: runs, signals, reports, alerts, agent decisions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AnalysisRun(Base, TimestampMixin):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(32), default="schedule")  # schedule|manual|signal
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL")
    )
    watchlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("watchlists.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|error
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)

    signals: Mapped[list["Signal"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["AgentDecision"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id", ondelete="SET NULL"))
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    signal_type: Mapped[str] = mapped_column(String(16))  # buy|sell|alert
    strength: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    price: Mapped[float | None] = mapped_column(Float)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)  # matched sub-expressions

    run: Mapped[AnalysisRun | None] = relationship(back_populates="signals")


class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str | None] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str | None] = mapped_column(Text)
    html_path: Mapped[str | None] = mapped_column(String(512))
    pdf_path: Mapped[str | None] = mapped_column(String(512))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)  # structured agent output

    run: Mapped[AnalysisRun | None] = relationship(back_populates="reports")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(24), default="email")
    recipient: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|sent|failed
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AgentDecision(Base):
    """One node's contribution inside a LangGraph run — the audit trail."""

    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    agent: Mapped[str] = mapped_column(String(48), index=True)  # supervisor, technical_analyst...
    step: Mapped[int] = mapped_column(default=0)
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    rationale: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[int | None] = mapped_column()
    latency_ms: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    run: Mapped[AnalysisRun] = relationship(back_populates="decisions")


class IngestionRun(Base):
    """One connector execution — whether ad-hoc (an upload with
    mode=ingest_once, or a "crawl now") or from a saved ``InputSource`` —
    tracked from the moment it's queued.

    This is what makes an in-progress or one-off ingest show up in the
    Activity feed at all: ``InputSource`` only ever remembers its *latest*
    run (``last_run_at``/``last_status``), and an ad-hoc run has no
    ``InputSource`` row to begin with. A row here starts at ``status =
    "running"`` the moment the Celery task begins and gets a ``finished_at``
    + final status once it completes, so the feed can show real progress
    instead of only ever seeing a run after the fact.
    """

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str | None] = mapped_column(String(64), index=True)
    input_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("input_sources.id", ondelete="SET NULL")
    )
    source_name: Mapped[str] = mapped_column(String(255))
    connector: Mapped[str] = mapped_column(String(32))
    ticker: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|ok|error
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExceptionLog(Base):
    """A persisted record of an unexpected failure, from any part of the
    system (API request, Celery task, websocket handler) — the actual store
    behind the "unhandled exception" log line ``app.main``'s middleware has
    always written to the text log but never persisted anywhere queryable.
    Deliberately has no ``TimestampMixin``/``updated_at``: a log row is
    write-once, and hard-deleting one (see ``ExceptionLogRepository``) is the
    only mutation it ever gets."""

    __tablename__ = "exception_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)  # api|websocket|run|input_source
    message: Mapped[str] = mapped_column(Text)
    traceback: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)  # e.g. ticker/run_id/path
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
