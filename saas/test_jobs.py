"""Tests for the durable scan-job repository (F-01)."""

import pathlib
import tempfile
import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def factory():
    tmpdir = tempfile.mkdtemp()
    url = f"sqlite:///{pathlib.Path(tmpdir, 'jobs.db').as_posix()}"
    import db

    db.run_migrations(url)
    engine = create_engine(url, future=True)
    yield sessionmaker(bind=engine, expire_on_commit=False, future=True), engine
    engine.dispose()


def test_migration_creates_scan_jobs(factory):
    _sf, engine = factory
    assert "scan_jobs" in inspect(engine).get_table_names()


def test_create_and_get(factory):
    sf, _ = factory
    import jobs_repo

    jid = uuid.uuid4().hex
    created, is_new = jobs_repo.create_job(
        jid, "alice", total_repositories=5, visibility="both", session_factory=sf
    )
    assert is_new is True
    assert created["id"] == jid
    assert created["owner_login"] == "alice"
    assert created["status"] == "queued"

    fetched = jobs_repo.get_job(jid, session_factory=sf)
    assert fetched["total_repositories"] == 5


def test_idempotency_returns_same_job(factory):
    sf, _ = factory
    import jobs_repo

    first, new1 = jobs_repo.create_job(
        uuid.uuid4().hex, "alice", idempotency_key="abc", session_factory=sf
    )
    second, new2 = jobs_repo.create_job(
        uuid.uuid4().hex, "alice", idempotency_key="abc", session_factory=sf
    )
    assert new1 is True and new2 is False
    assert first["id"] == second["id"]  # same job returned, no duplicate


def test_update_status_and_counts(factory):
    sf, _ = factory
    import jobs_repo

    jid = uuid.uuid4().hex
    jobs_repo.create_job(jid, "alice", session_factory=sf)
    updated = jobs_repo.update_job(
        jid, session_factory=sf, status="completed", scanned_repositories=3, report_id="r1"
    )
    assert updated["status"] == "completed"
    assert updated["scanned_repositories"] == 3
    assert updated["report_id"] == "r1"


def test_list_is_owner_scoped(factory):
    sf, _ = factory
    import jobs_repo

    jobs_repo.create_job(uuid.uuid4().hex, "alice", session_factory=sf)
    jobs_repo.create_job(uuid.uuid4().hex, "alice", session_factory=sf)
    jobs_repo.create_job(uuid.uuid4().hex, "mallory", session_factory=sf)

    assert len(jobs_repo.list_jobs_for_user("alice", session_factory=sf)) == 2
    assert len(jobs_repo.list_jobs_for_user("mallory", session_factory=sf)) == 1


def test_startup_recovery_marks_interrupted(factory):
    sf, _ = factory
    import jobs_repo

    running = uuid.uuid4().hex
    done = uuid.uuid4().hex
    jobs_repo.create_job(running, "alice", status="running", session_factory=sf)
    jobs_repo.create_job(done, "alice", session_factory=sf)
    jobs_repo.update_job(done, session_factory=sf, status="completed")

    count = jobs_repo.mark_stale_running_as_interrupted(session_factory=sf)
    assert count == 1
    assert jobs_repo.get_job(running, session_factory=sf)["status"] == "interrupted"
    assert jobs_repo.get_job(done, session_factory=sf)["status"] == "completed"
