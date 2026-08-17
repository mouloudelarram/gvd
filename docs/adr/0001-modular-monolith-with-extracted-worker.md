# ADR 0001 â€” Modular monolith with an extracted scanner worker

- Status: Proposed
- Date: 2026-07-16
- Related: F-02, F-10, F-19 (audit)

## Context

GVD is currently a single Flask process that also performs cloning and scanning in daemon
threads. The mission demands a "service-oriented" architecture but explicitly warns against
introducing microservices for appearance and against a distributed monolith. A small team must be
able to run and operate it.

## Decision

Adopt a **modular monolith** (`gvd-web`) with explicit internal boundaries
(delivery / application / domain / infrastructure) **plus one separately deployed process**
(`gvd-worker`) that performs cloning and scanning.

## Rationale

- The **only** capability with a compelling isolation/scaling justification today is the scanner:
  it runs `git clone` and analyzes **untrusted repository content**. Running it in its own
  container (no inbound network, dropped capabilities, read-only FS except a temp workspace,
  CPU/mem/pid limits) contains the blast radius of a malicious repository.
- All other capabilities (web, API, identity, orchestration, reporting) share the same data and
  release cadence; splitting them now would add network hops and operational cost without benefit.
- Internal module boundaries keep future extraction cheap if a real need appears.

## Consequences

- Two deployables: `gvd-web` and `gvd-worker`, plus `postgres` and `redis`.
- A durable queue is required to hand work to the worker (see ADR 0002).
- Clear module packages must be maintained; a linter/import-boundary check should enforce them.

## Alternatives considered

- **Keep single process + threads:** rejected â€” not restart-safe, no isolation, blocks graceful
  shutdown (F-02).
- **Full microservices (web/api/identity/orchestrator/worker/reporting):** rejected â€” distributed
  monolith risk, disproportionate ops burden for a small team.
