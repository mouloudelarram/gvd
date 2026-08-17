"""ORM models for the GVD SaaS service."""

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScanEvent(Base):
    """One completed scan, attributed to the user who initiated it.

    Daily, per-user statistics are aggregated from these rows, replacing the
    previous global in-memory dictionary (durable + no cross-user leakage; F-11).
    """

    __tablename__ = "scan_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_login: Mapped[str] = mapped_column(String(255), index=True, default="")
    scan_date: Mapped[date] = mapped_column(Date, index=True)
    total_findings: Mapped[int] = mapped_column(Integer, default=0)
    critical: Mapped[int] = mapped_column(Integer, default=0)
    high: Mapped[int] = mapped_column(Integer, default=0)
    medium: Mapped[int] = mapped_column(Integer, default=0)
    low: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


# Scan job lifecycle states (durable; survive restarts — F-01).
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_STOPPED = "stopped"
JOB_STATUS_INTERRUPTED = "interrupted"  # process died while running (startup recovery)

ACTIVE_JOB_STATUSES = (JOB_STATUS_QUEUED, JOB_STATUS_RUNNING)


class ScanJob(Base):
    """Durable record of a scan job.

    The live process/thread handles remain in memory (they cannot be persisted),
    but the job's identity, ownership, status and counters live here so history
    survives restarts and access can be authorized per user (F-01, F-06).
    """

    __tablename__ = "scan_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID4 hex
    owner_login: Mapped[str] = mapped_column(String(255), index=True, default="")
    job_type: Mapped[str] = mapped_column(String(20), default="bulk")
    status: Mapped[str] = mapped_column(String(20), index=True, default=JOB_STATUS_QUEUED)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=True)
    total_repositories: Mapped[int] = mapped_column(Integer, default=0)
    scanned_repositories: Mapped[int] = mapped_column(Integer, default=0)
    failed_repositories: Mapped[int] = mapped_column(Integer, default=0)
    report_id: Mapped[str] = mapped_column(String(64), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

