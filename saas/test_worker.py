"""Durable queue + worker tests (F-02)."""

import pathlib
import subprocess
import tempfile
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def factory():
    tmpdir = tempfile.mkdtemp()
    url = f"sqlite:///{pathlib.Path(tmpdir, 'q.db').as_posix()}"
    import db

    db.run_migrations(url)
    engine = create_engine(url, future=True)
    yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    engine.dispose()


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def secret_repo(tmp_path):
    repo = tmp_path / "srepo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.email", "t@e.com"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "s.txt").write_text("AWS=AKIA1234567890ABCDEF\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "x"], repo)
    return repo


def _enqueue(jobs_repo, sf, owner="alice"):
    jid = uuid.uuid4().hex
    jobs_repo.create_job(jid, owner, status="queued", session_factory=sf)
    return jid


def test_claim_is_atomic(factory):
    import jobs_repo

    jid = _enqueue(jobs_repo, factory)
    first = jobs_repo.claim_next_job(session_factory=factory)
    assert first["id"] == jid
    assert first["status"] == "running"
    # No more queued jobs to claim.
    assert jobs_repo.claim_next_job(session_factory=factory) is None


def test_claim_fifo_order(factory):
    import jobs_repo

    a = _enqueue(jobs_repo, factory)
    b = _enqueue(jobs_repo, factory)
    assert jobs_repo.claim_next_job(session_factory=factory)["id"] == a
    assert jobs_repo.claim_next_job(session_factory=factory)["id"] == b


def test_requeue_then_fail_after_max(factory):
    import jobs_repo

    jid = _enqueue(jobs_repo, factory)
    assert jobs_repo.requeue_or_fail(jid, max_retries=2, session_factory=factory) == "queued"
    assert jobs_repo.requeue_or_fail(jid, max_retries=2, session_factory=factory) == "queued"
    assert jobs_repo.requeue_or_fail(jid, max_retries=2, error="boom", session_factory=factory) == "failed"
    job = jobs_repo.get_job(jid, session_factory=factory)
    assert job["retry_count"] == 3
    assert job["error"] == "boom"


def test_cancel_flag(factory):
    import jobs_repo

    jid = _enqueue(jobs_repo, factory)
    # Ownership enforced.
    assert jobs_repo.request_cancel(jid, owner_login="mallory", session_factory=factory) is False
    assert jobs_repo.request_cancel(jid, owner_login="alice", session_factory=factory) is True
    assert jobs_repo.is_cancel_requested(jid, session_factory=factory) is True


def test_worker_processes_job_and_cleans_up(factory, secret_repo, tmp_path):
    import jobs_repo
    import worker

    jid = _enqueue(jobs_repo, factory)
    captured = {}

    def cloner(job, workspace):
        captured["workspace"] = workspace
        return secret_repo  # pretend we cloned into the workspace

    w = worker.Worker(cloner, tmp_path / "out", session_factory=factory)
    result = w.run_once()
    assert result["status"] == "completed"
    assert result["report"]["total_findings"] >= 1
    # Job marked completed durably.
    assert jobs_repo.get_job(jid, session_factory=factory)["status"] == "completed"
    # Temp workspace was cleaned up.
    assert not captured["workspace"].exists()


def test_worker_respects_cancellation(factory, tmp_path):
    import jobs_repo
    import worker

    jid = _enqueue(jobs_repo, factory)
    jobs_repo.request_cancel(jid, owner_login="alice", session_factory=factory)

    def cloner(job, workspace):
        raise AssertionError("cloner must not run when already cancelled")

    # Manually claim then process to simulate the worker seeing a cancelled job.
    claimed = jobs_repo.claim_next_job(session_factory=factory)
    result = worker.process_job(claimed, cloner, tmp_path / "out", session_factory=factory)
    assert result["status"] == "stopped"
    assert jobs_repo.get_job(jid, session_factory=factory)["status"] == "stopped"


def test_worker_retries_on_clone_failure(factory, tmp_path):
    import jobs_repo
    import worker

    jid = _enqueue(jobs_repo, factory)
    claimed = jobs_repo.claim_next_job(session_factory=factory)

    def failing_cloner(job, workspace):
        raise RuntimeError("clone failed")

    result = worker.process_job(
        claimed, failing_cloner, tmp_path / "out", max_retries=1, session_factory=factory
    )
    # First failure requeues.
    assert result["status"] == "queued"
    assert jobs_repo.get_job(jid, session_factory=factory)["retry_count"] == 1


def test_worker_run_once_none_when_empty(factory, tmp_path):
    import worker

    w = worker.Worker(lambda j, w: None, tmp_path / "out", session_factory=factory)
    assert w.run_once() is None
