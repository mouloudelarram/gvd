"""Statistics repository: durable, per-user daily scan statistics (F-11)."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from db import ensure_schema, session_scope
from models_db import ScanEvent


def _today():
    return datetime.now(timezone.utc).date()


def _utc_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def record_scan_event(user_login, severity_counts, total_findings, session_factory=None):
    """Persist one completed scan for later per-user aggregation.

    Best-effort: callers should not let a stats write failure break a scan.
    """
    if session_factory is None:
        ensure_schema()
    counts = severity_counts or {}
    with session_scope(session_factory) as session:
        session.add(
            ScanEvent(
                user_login=(user_login or "").strip(),
                scan_date=_today(),
                total_findings=int(total_findings or 0),
                critical=int(counts.get("CRITICAL", 0)),
                high=int(counts.get("HIGH", 0)),
                medium=int(counts.get("MEDIUM", 0)),
                low=int(counts.get("LOW", 0)),
            )
        )


def get_today_stats(user_login, session_factory=None):
    """Return today's aggregated statistics for a single user."""
    if session_factory is None:
        ensure_schema()
    login = (user_login or "").strip()
    today = _today()
    with session_scope(session_factory) as session:
        scans, total, crit, high, med, low = session.execute(
            select(
                func.count(ScanEvent.id),
                func.coalesce(func.sum(ScanEvent.total_findings), 0),
                func.coalesce(func.sum(ScanEvent.critical), 0),
                func.coalesce(func.sum(ScanEvent.high), 0),
                func.coalesce(func.sum(ScanEvent.medium), 0),
                func.coalesce(func.sum(ScanEvent.low), 0),
            ).where(
                ScanEvent.user_login == login,
                ScanEvent.scan_date == today,
            )
        ).one()

    return {
        "scanned_today": int(scans),
        "high_risk_findings": int(crit) + int(high),
        "total_findings_today": int(total),
        "breakdown": {
            "CRITICAL": int(crit),
            "HIGH": int(high),
            "MEDIUM": int(med),
            "LOW": int(low),
        },
        "timestamp": _utc_iso(),
    }
