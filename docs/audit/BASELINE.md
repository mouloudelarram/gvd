# GVD â€” Verified Baseline (Phase 1)

> Purpose: record the **measured** state of the repository *before* any modernization,
> so regressions can be distinguished from pre-existing failures. All results below were
> produced by running the commands shown. Nothing here is assumed.

Date captured: 2026-07-16
Host: Windows, PowerShell 5.1

## 1. Toolchain discovered

| Tool | Result | Evidence |
|------|--------|----------|
| Python (`python`) | âŒ not on PATH (Windows Store stub) | `python --version` â†’ "Python est introuvable" |
| Python (`py`) | âœ… Python 3.14.0 | `py --version` |
| Docker | âŒ not installed on this host | `docker --version` â†’ not found |
| Docker Compose | âŒ not installed on this host | `docker compose version` â†’ not found |
| Git | âœ… available | `git ls-files` works |

**Blocker B1:** Docker / Docker Compose are not available on this workstation, so the container
release gates (build, healthy containers, compose smoke test) **cannot be executed here**. They
must run in CI or on a Docker-enabled host. See `AUDIT_REPORT.md` â†’ Blockers.

## 2. Test baseline

Global `pytest-flask` plugin is **incompatible** with the installed Flask 3.x
(`ImportError: cannot import name '_request_ctx_stack' from 'flask'`), so it must be disabled
with `-p no:flask` to collect any tests at all.

### SaaS suite (`saas/`)

```
py -m pytest -p no:flask -q
=> 7 failed, 12 passed, 3 errors
```

Failing (pre-existing):
- `test_build_repo_key` â€” AssertionError
- `test_github_auth_url_generation`, `test_oauth_state_validation` â€” "Working outside of request context"
- `test_sanitize_path_component`, `test_build_clone_url` â€” "DID NOT RAISE"
- `test_csrf_token_generation`, `test_require_login_decorator` â€” "Working outside of request context"
- errors: `test_dashboard_with_authentication`, `test_scan_endpoint`, `test_logout`

Root cause bucket: tests patch `flask.session` / call view helpers **outside** an app/request
context and rely on the now-removed `pytest-flask` behavior. Several are test-harness defects,
not application defects; two (`test_sanitize_path_component`, `test_build_clone_url`) assert
security behavior the implementation does **not** provide (see F-07, F-08).

### CLI suite (`cli/`)

```
py -m pytest -p no:flask -q
=> 7 failed, 9 passed
```

Failing (pre-existing):
- `test_aws_key_pattern`, `test_generic_api_key_pattern`, `test_private_key_pattern`,
  `test_database_url_pattern` â€” AssertionError on `severity == Severity.CRITICAL/HIGH`
- `test_scan_history_success`, `test_scan_history_empty`, `test_scan_repo_integration` â€”
  `AttributeError: module 'cli' does not have the attribute 'ReportExporter'` (mock target wrong)

**Verified root cause of the 4 pattern failures (F-09):** the pattern engine detection itself is
correct â€” `PatternEngine().match_pattern("AKIA1234567890123456")` returns exactly one `aws_key`
match. The tests fail only on the **enum identity** comparison because `Severity` is imported
under two different module paths (`cli.core.models` **and** `core.models`) via a
`try/except ImportError` fallback, producing two distinct enum classes whose members are not
`==`. `test_multiple_patterns`, which checks only `type` (strings), **passes** â€” confirming the
diagnosis.

## 3. Secret-exposure check (git-tracked files only)

```
git ls-files | Select-String "\.env"
=> .env.production, .env.production.template, saas/.env.example
```

- **Tracked** env files contain **placeholders only** (e.g. `your_github_client_secret`,
  `dev-secret-key-change-in-production-...`). No live secret is committed.
- A **local, untracked** `saas/.env` exists on this machine and does contain real values; it is
  correctly ignored by `.gitignore` (`/saas/.env`). Its previously-used credentials should still
  be **rotated** as a precaution (they may have been shared out-of-band). Values were **not**
  printed during this audit.
- `repos/` and `scan_reports/` are **not** tracked (correctly ignored).

## 4. How to reproduce this baseline

```powershell
# from repo root
cd saas ; py -m pytest -p no:flask -q
cd ..\cli ; py -m pytest -p no:flask -q
```
</invoke>

