"""Tests for the durable persistence layer (Phase 4.1): migrations + stats repo."""

import pathlib
import tempfile

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def migrated_session_factory():
    """A session factory bound to a freshly-migrated temporary SQLite database."""
    tmpdir = tempfile.mkdtemp()
    url = f"sqlite:///{pathlib.Path(tmpdir, 'test.db').as_posix()}"

    import db

    # Prove migrations succeed from a clean database (release gate).
    db.run_migrations(url)

    engine = create_engine(url, future=True)
    yield sessionmaker(bind=engine, expire_on_commit=False, future=True), engine
    engine.dispose()


def test_migration_creates_schema(migrated_session_factory):
    _factory, engine = migrated_session_factory
    tables = inspect(engine).get_table_names()
    assert "scan_events" in tables
    assert "alembic_version" in tables  # migration bookkeeping table


def test_stats_aggregate_per_user(migrated_session_factory):
    factory, _engine = migrated_session_factory
    import stats_repo

    stats_repo.record_scan_event(
        "alice", {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 0, "LOW": 0}, 3,
        session_factory=factory,
    )
    stats_repo.record_scan_event(
        "alice", {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 1, "LOW": 4}, 6,
        session_factory=factory,
    )
    stats_repo.record_scan_event(
        "mallory", {"CRITICAL": 9, "HIGH": 9, "MEDIUM": 9, "LOW": 9}, 36,
        session_factory=factory,
    )

    alice = stats_repo.get_today_stats("alice", session_factory=factory)
    assert alice["scanned_today"] == 2
    assert alice["total_findings_today"] == 9
    assert alice["high_risk_findings"] == 4  # 1 critical + 3 high
    assert alice["breakdown"] == {"CRITICAL": 1, "HIGH": 3, "MEDIUM": 1, "LOW": 4}


def test_stats_isolated_between_users(migrated_session_factory):
    factory, _engine = migrated_session_factory
    import stats_repo

    stats_repo.record_scan_event(
        "alice", {"CRITICAL": 1, "HIGH": 0, "MEDIUM": 0, "LOW": 0}, 1,
        session_factory=factory,
    )
    # A different user sees only their own (empty) statistics.
    mallory = stats_repo.get_today_stats("mallory", session_factory=factory)
    assert mallory["scanned_today"] == 0
    assert mallory["high_risk_findings"] == 0
    assert mallory["total_findings_today"] == 0

