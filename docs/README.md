# GVD Documentation Catalog

> This is the **canonical documentation index** for GVD — GitHub Vulnerability Detector.
> All scattered root-level markdown files have been consolidated here (Phase 9, C-28).

---

## Start Here

| Document | Description |
|----------|-------------|
| [Audit report](audit/AUDIT_REPORT.md) | Prioritized findings (F-01…F-19) with evidence and blockers |
| [Verified baseline](audit/BASELINE.md) | Measured toolchain + test state before modernization |
| [Migration notes & changelog](MIGRATION_NOTES.md) | Chronological, evidence-backed changes log |
| [Release history](audit/release-history.md) | Phase-by-phase milestones, bug fixes, removals |
| [Cleanup report](audit/CLEANUP_REPORT.md) | What was removed and why |

---

## Architecture

| Document | Description |
|----------|-------------|
| [Architecture overview](architecture/overview.md) | Current architecture, components, data model, security boundaries |
| [Target architecture](architecture/TARGET_ARCHITECTURE.md) | Full target-state design, service catalog, migration roadmap |
| [ADR index](adr/README.md) | Significant architectural decisions |

---

## Guides

| Document | Description |
|----------|-------------|
| [Docker guide](guides/docker.md) | Complete Docker / Docker Compose guide (dev + production) |
| [Deployment guide](guides/deployment.md) | Single-server + AWS EC2 production deployment |
| [Bulk scan guide](guides/bulk-scan.md) | Bulk scan architecture, API, configuration, troubleshooting |
| [Quick reference](guides/quick-reference.md) | Commands, env vars, API routes, integration patterns |

---

## Reference Catalogs

| Topic | Location |
|-------|----------|
| Environment variable catalog | [quick-reference.md — Env vars](guides/quick-reference.md#environment-variables--complete-catalog) |
| API routes reference | [quick-reference.md — API routes](guides/quick-reference.md#api-routes-reference) |
| Scanner rule catalog | [quick-reference.md — Scanner rules](guides/quick-reference.md#scanner-rule-catalog) |
| Severity model | [quick-reference.md — Severity](guides/quick-reference.md#severity-model) |
| Data model | [architecture/overview.md — Data model](architecture/overview.md#data-model-abbreviated) |
| OAuth flow | [quick-reference.md — OAuth](guides/quick-reference.md#github-oauth-integration) |
| Bulk scan API | [bulk-scan.md — API](guides/bulk-scan.md#api-endpoints) |
| Known limitations | [quick-reference.md — Limitations](guides/quick-reference.md#known-limitations-and-accepted-risks) |

---

## How to Reproduce the Baseline

```powershell
cd saas ; python -m pytest -p no:flask -q    # 111 tests
cd ..\cli ; python -m pytest -p no:flask -q  # 16 tests
```

---

## Documentation Completeness

| Catalog item | Document | Status |
|--------------|----------|--------|
| Product overview | [README.md](../README.md) | ✅ |
| Architecture overview | [architecture/overview.md](architecture/overview.md) | ✅ |
| Target architecture | [architecture/TARGET_ARCHITECTURE.md](architecture/TARGET_ARCHITECTURE.md) | ✅ |
| Docker Compose guide | [guides/docker.md](guides/docker.md) | ✅ |
| Production deployment | [guides/deployment.md](guides/deployment.md) | ✅ |
| Env-var catalog | [guides/quick-reference.md](guides/quick-reference.md) | ✅ |
| API reference | [guides/quick-reference.md](guides/quick-reference.md) | ✅ |
| Bulk scan guide | [guides/bulk-scan.md](guides/bulk-scan.md) | ✅ |
| Security model | [architecture/TARGET_ARCHITECTURE.md](architecture/TARGET_ARCHITECTURE.md) | ✅ |
| ADR index | [adr/README.md](adr/README.md) | ✅ |
| Known limitations | [guides/quick-reference.md](guides/quick-reference.md) | ✅ |
| Changelog | [MIGRATION_NOTES.md](MIGRATION_NOTES.md) | ✅ |
| Release history | [audit/release-history.md](audit/release-history.md) | ✅ |
| Cleanup report | [audit/CLEANUP_REPORT.md](audit/CLEANUP_REPORT.md) | ✅ |
