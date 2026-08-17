"""Durable scan worker (F-02).

Consumes jobs from the durable DB-backed queue (see ``jobs_repo``), runs the
in-process scanner in an isolated temporary workspace, and updates durable job
state. Provides idempotent claiming, bounded retries, per-job timeout,
cooperative cancellation, and guaranteed workspace cleanup.

Design note: cloning needs a GitHub token, which lives in the user's server-side
session and is intentionally NOT persisted (F-03). The worker therefore receives
a ``cloner`` callable so the token-handoff strategy is a separate, explicit
decision (see the pending ADR). This keeps the queue/worker mechanics fully
testable without external services (SQLite-backed queue, local git repos).
"""

import shutil
import tempfile
import time
from pathlib import Path

import jobs_repo
import scanner_lib


def process_job(
    job,
    cloner,
    output_root,
    scanner=None,
    max_retries=3,
    timeout=300,
    session_factory=None,
):
    """Process one claimed job end-to-end.

    ``cloner(job, workspace) -> repo_path`` performs the isolated clone.
    Returns a dict with the resulting ``status``.
    """
    scanner = scanner or scanner_lib.scan_to_dir
    job_id = job["id"]
    workspace = Path(tempfile.mkdtemp(prefix="gvd-scan-"))

    def cancelled():
        return jobs_repo.is_cancel_requested(job_id, session_factory=session_factory)

    try:
        if cancelled():
            jobs_repo.update_job(job_id, status="stopped", session_factory=session_factory)
            return {"status": "stopped"}

        repo_path = cloner(job, workspace)

        if cancelled():
            jobs_repo.update_job(job_id, status="stopped", session_factory=session_factory)
            return {"status": "stopped"}

        output_dir = Path(output_root) / job_id
        report = scanner(repo_path, output_dir, job.get("owner_login") or "repo", timeout=timeout)

        jobs_repo.update_job(
            job_id,
            status="completed",
            scanned_repositories=1,
            report_id=job_id,
            session_factory=session_factory,
        )
        return {"status": "completed", "report": report}
    except Exception as exc:  # noqa: BLE001 - convert any failure into retry/fail
        status = jobs_repo.requeue_or_fail(
            job_id, max_retries=max_retries, error=str(exc), session_factory=session_factory
        )
        return {"status": status, "error": str(exc)}
    finally:
        # Always clean up the temporary workspace (no leaked repos/artifacts).
        shutil.rmtree(workspace, ignore_errors=True)


class Worker:
    """Polls the durable queue and processes jobs one at a time."""

    def __init__(self, cloner, output_root, session_factory=None, max_retries=3, timeout=300):
        self.cloner = cloner
        self.output_root = output_root
        self.session_factory = session_factory
        self.max_retries = max_retries
        self.timeout = timeout

    def run_once(self):
        """Claim and process a single job; returns its result dict or None."""
        job = jobs_repo.claim_next_job(session_factory=self.session_factory)
        if job is None:
            return None
        return process_job(
            job,
            self.cloner,
            self.output_root,
            max_retries=self.max_retries,
            timeout=self.timeout,
            session_factory=self.session_factory,
        )

    def run_forever(self, poll_interval=2.0, stop_event=None):  # pragma: no cover - loop
        """Continuously process jobs until ``stop_event`` is set."""
        while stop_event is None or not stop_event.is_set():
            if self.run_once() is None:
                time.sleep(poll_interval)


def main():  # pragma: no cover - process entrypoint
    """Standalone worker entrypoint (future separate-process deployment)."""
    import logging
    import os

    logging.basicConfig(level=logging.INFO)
    output_root = os.environ.get("SCAN_OUTPUT_ROOT", "scan_reports/worker")

    def _not_configured(job, workspace):
        raise RuntimeError(
            "No cloner configured. Wire a secure token-handoff strategy before "
            "running the worker as a separate process (see ADR)."
        )

    Worker(_not_configured, output_root).run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
