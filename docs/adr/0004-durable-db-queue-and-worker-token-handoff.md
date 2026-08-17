# ADR 0004 â€” Durable DB-backed job queue and worker token handoff

- Status: Accepted (queue mechanics) / Proposed (separate-process deployment)
- Date: 2026-07-16
- Related: F-01, F-02, F-03, F-19

## Context

Scans must survive restarts, support retries/timeouts/cancellation, and run in
isolation. ADR 0002 proposed Redis + RQ. However:

1. A separate worker process needs a GitHub token to clone private repos, but the
   token lives in the user's **server-side session** and is intentionally **not**
   persisted (ADR 0003 / F-03).
2. The local/CI environment cannot always run a Redis server, yet the queue
   semantics must be testable.

## Decision

- Implement the durable queue on the **existing relational DB** (SQLite/Postgres)
  via a `scan_jobs` table and guarded-UPDATE claiming (`jobs_repo.claim_next_job`),
  which is correct on both engines and needs no extra infrastructure to test.
- Implement the worker (`worker.py`) with idempotent claiming, bounded retries
  (`requeue_or_fail`), per-job timeout, cooperative cancellation
  (`cancel_requested` flag checked at safe checkpoints), and guaranteed temp
  workspace cleanup.
- The worker receives a **`cloner` callable** rather than reaching into sessions,
  so the token-handoff strategy is an explicit, separately-decided concern.

### Token handoff for a separate worker process (Proposed)

When the worker is deployed as its own process, the enqueuing request (which holds
the token) must hand it off securely. Options, in order of preference:

1. **Short-lived encrypted token in the job payload** â€” encrypt with an app-managed
   key, set a short TTL, delete on completion. Simple; token briefly at rest.
2. **GitHub App installation tokens** â€” mint a short-lived installation token per
   job instead of using the user OAuth token. Best security; requires a GitHub App.
3. **Broker-side secret store** (e.g. Vault) â€” worker fetches a lease. Most infra.

Until one is chosen, bulk scans continue to run **in-process** (thread) where the
token is already available; the durable queue/worker is used for its state,
retries, and recovery semantics and is ready for extraction.

## Consequences

- No Redis dependency for the queue (Redis remains for server-side sessions, ADR 0003).
- Fully testable without external services (SQLite queue + local git repos).
- A follow-up is required before running the worker as a separate deployable
  process: pick a token-handoff option above and add encryption + TTL + tests.

## Alternatives considered

- **Redis + RQ now:** blocked by the token-handoff question and local testability;
  revisit once the token strategy is chosen and fan-out demands it.
- **Persist the raw OAuth token on the job:** rejected â€” violates F-03 (token at
  rest, long-lived). Only short-lived/encrypted or minted tokens are acceptable.

