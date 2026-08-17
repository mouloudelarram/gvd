"""Durable scan-job repository (F-01).

Persists job identity, ownership, status and counters so history survives
restarts and access can be authorized per user. Live process/thread handles stay
in memory (they cannot be serialized); this module is the durable source of truth
for job *state*. All functions return plain dicts to keep callers decoupled from
ORM sessions.
"""

from datetime import datetime, timezone

from sqlalchemy import select, update

from db import ensure_schema, session_scope
from models_db import (
    ACTIVE_JOB_STATUSES,
    JOB_STATUS_FAILED,
    JOB_STATUS_INTERRUPTED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    ScanJob,
)


def _to_dict(job: ScanJob) -> dict:
    return {
        "id": job.id,
        "owner_login": job.owner_login,
        "job_type": job.job_type,
        "status": job.status,
        "idempotency_key": job.idempotency_key,
        "visibility": job.visibility,
        "total_repositories": job.total_repositories,
        "scanned_repositories": job.scanned_repositories,
        "failed_repositories": job.failed_repositories,
        "report_id": job.report_id,
        "error": job.error,
        "retry_count": job.retry_count,
        "cancel_requested": bool(job.cancel_requested),
        "created_at": job.created_at.isoformat().replace("+00:00", "Z") if job.created_at else None,
        "updated_at": job.updated_at.isoformat().replace("+00:00", "Z") if job.updated_at else None,
    }


def create_job(
    job_id,
    owner_login,
    job_type="bulk",
    total_repositories=0,
    visibility=None,
    idempotency_key=None,
    status=JOB_STATUS_QUEUED,
    session_factory=None,
):
    """Create a job, or return the existing one for the same (owner, idempotency_key).

    Idempotency prevents duplicate scans on retried requests (F-13).
    """
    if session_factory is None:
        ensure_schema()
    owner = (owner_login or "").strip()
    key = (idempotency_key or "").strip() or None

    with session_scope(session_factory) as session:
        if key:
            existing = session.execute(
                select(ScanJob).where(
                    ScanJob.owner_login == owner,
                    ScanJob.idempotency_key == key,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _to_dict(existing), False

        job = ScanJob(
            id=job_id,
            owner_login=owner,
            job_type=job_type,
            status=status,
            idempotency_key=key,
            visibility=visibility,
            total_repositories=int(total_repositories or 0),
        )
        session.add(job)
        session.flush()
        return _to_dict(job), True


def get_job(job_id, session_factory=None):
    if session_factory is None:
        ensure_schema()
    with session_scope(session_factory) as session:
        job = session.get(ScanJob, job_id)
        return _to_dict(job) if job else None


def update_job(job_id, session_factory=None, **fields):
    """Update mutable fields on a job; returns the updated dict or None."""
    if session_factory is None:
        ensure_schema()
    allowed = {
        "status",
        "visibility",
        "total_repositories",
        "scanned_repositories",
        "failed_repositories",
        "report_id",
        "error",
    }
    changes = {k: v for k, v in fields.items() if k in allowed}
    with session_scope(session_factory) as session:
        job = session.get(ScanJob, job_id)
        if job is None:
            return None
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(timezone.utc)
        session.flush()
        return _to_dict(job)


def list_jobs_for_user(owner_login, limit=50, session_factory=None):
    if session_factory is None:
        ensure_schema()
    owner = (owner_login or "").strip()
    with session_scope(session_factory) as session:
        rows = session.execute(
            select(ScanJob)
            .where(ScanJob.owner_login == owner)
            .order_by(ScanJob.created_at.desc())
            .limit(int(limit))
        ).scalars().all()
        return [_to_dict(job) for job in rows]


def count_queued_jobs(session_factory=None) -> int:
    """Return the number of jobs currently waiting in the queue (metrics gauge)."""
    if session_factory is None:
        ensure_schema()
    with session_scope(session_factory) as session:
        rows = session.execute(
            select(ScanJob.id).where(ScanJob.status == JOB_STATUS_QUEUED)
        ).all()
        return len(rows)


def mark_stale_running_as_interrupted(session_factory=None) -> int:
    """Startup recovery: any job still 'queued'/'running' is orphaned by a restart.

    Returns the number of jobs transitioned to 'interrupted'.
    """
    if session_factory is None:
        ensure_schema()
    with session_scope(session_factory) as session:
        result = session.execute(
            update(ScanJob)
            .where(ScanJob.status.in_(ACTIVE_JOB_STATUSES))
            .values(status=JOB_STATUS_INTERRUPTED, updated_at=datetime.now(timezone.utc))
        )
        return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Durable queue operations (F-02)
# ---------------------------------------------------------------------------

def claim_next_job(session_factory=None):
    """Atomically claim the oldest queued job (status queued -> running).

    Uses a guarded UPDATE so that, under concurrency, only one claimer wins.
    Works on SQLite and PostgreSQL. Returns the claimed job dict or None.
    """
    if session_factory is None:
        ensure_schema()
    with session_scope(session_factory) as session:
        candidate = session.execute(
            select(ScanJob.id)
            .where(ScanJob.status == JOB_STATUS_QUEUED)
            .order_by(ScanJob.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        if candidate is None:
            return None
        result = session.execute(
            update(ScanJob)
            .where(ScanJob.id == candidate, ScanJob.status == JOB_STATUS_QUEUED)
            .values(status=JOB_STATUS_RUNNING, updated_at=datetime.now(timezone.utc))
        )
        if result.rowcount != 1:
            return None  # lost the race to another claimer
        return _to_dict(session.get(ScanJob, candidate))


def request_cancel(job_id, owner_login=None, session_factory=None):
    """Request cancellation of a job. If owner_login is given, enforce ownership.

    Returns True if the flag was set, False if not found / not owned.
    """
    if session_factory is None:
        ensure_schema()
    with session_scope(session_factory) as session:
        job = session.get(ScanJob, job_id)
        if job is None:
            return False
        if owner_login is not None and job.owner_login != (owner_login or "").strip():
            return False
        job.cancel_requested = True
        job.updated_at = datetime.now(timezone.utc)
        return True


def is_cancel_requested(job_id, session_factory=None):
    """Return True if cancellation has been requested for the job."""
    if session_factory is None:
        ensure_schema()
    with session_scope(session_factory) as session:
        job = session.get(ScanJob, job_id)
        return bool(job and job.cancel_requested)


def requeue_or_fail(job_id, max_retries=3, error=None, session_factory=None):
    """Increment retry_count; requeue if under the limit, else mark failed.

    Returns the resulting status ('queued' or 'failed'), or None if not found.
    """
    if session_factory is None:
        ensure_schema()
    with session_scope(session_factory) as session:
        job = session.get(ScanJob, job_id)
        if job is None:
            return None
        job.retry_count = int(job.retry_count or 0) + 1
        job.updated_at = datetime.now(timezone.utc)
        if job.retry_count <= int(max_retries):
            job.status = JOB_STATUS_QUEUED
        else:
            job.status = JOB_STATUS_FAILED
            if error:
                job.error = str(error)[:1000]
        return job.status
