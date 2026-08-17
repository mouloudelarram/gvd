# ADR 0002 â€” Durable state on PostgreSQL + Redis queue

- Status: Proposed
- Date: 2026-07-16
- Related: F-01, F-02, F-11 (audit)

## Context

Jobs, notifications, statistics, and completed reports are stored in **module-level Python dicts**
(`BULK_SCAN_JOBS`, `SESSION_SCAN_RESULTS`, `SESSION_NOTIFICATIONS`, `SCAN_STATISTICS`). They are
lost on restart and are incorrect across multiple Gunicorn workers, and long scans run in daemon
threads inside the web process.

## Decision

- Use **PostgreSQL** as the system of record (SQLite for lightweight local dev), with **Alembic**
  migrations.
- Use **Redis** as (a) the durable **job queue** (RQ) between `gvd-web` and `gvd-worker`, and
  (b) the **server-side session** store (see ADR 0003).
- Generated report artifacts (JSON/PDF) live on a named volume; their metadata + checksum live in
  the DB.

## Rationale

- Meets "durable scan state rather than process-local dictionaries" and "in-memory state that
  cannot survive restarts."
- Redis + RQ gives explicit retry, timeout, and dead-letter semantics with minimal code and is
  easy to run in Compose; Postgres is the stable default for relational data.
- Both are mainstream, actively maintained, and Compose-friendly â€” satisfying "stable, actively
  maintained technologies" and "avoid unnecessary dependencies" (two infra services, both earning
  their place).

## Consequences

- Compose gains `postgres` and `redis` services with health checks and named volumes.
- A migration mechanism runs on startup (`alembic upgrade head`) with a documented rollback.
- Idempotency keys on job creation prevent duplicate scans on retries.

## Alternatives considered

- **Celery + RabbitMQ:** more features than needed now; heavier ops. Revisit if fan-out grows.
- **DB-only "queue" via polling:** simpler but reinvents retry/visibility semantics; rejected.
- **SQLite in prod:** insufficient for concurrent workers; kept only for local dev.
