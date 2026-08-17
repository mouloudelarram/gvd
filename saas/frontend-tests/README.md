# GVD Frontend Tests (Playwright + axe-core)

Browser-based accessibility and journey tests for the GVD web UI. These run in
CI (`frontend-test` job) on a Node-enabled runner; they are **not** run by the
Python `pytest` suite. The static-source guards in
`saas/test_frontend_a11y.py` and `saas/test_frontend_security.py` provide fast,
Node-free regression coverage in every `pytest` run.

## What is covered

Against the **real running Flask app** (real templates, CSS and JS):

- **Login page** (`/`): axe WCAG 2.2 A/AA scan (no serious/critical
  violations), skip-link + single-H1, keyboard focus reaches the sign-in
  control.
- **OAuth error journey**: declined consent
  (`/callback?error=access_denied`) renders "Authorization Cancelled" with no
  a11y violations; the 404 page renders its status code.
- **Reduced motion**: the login page passes axe under
  `prefers-reduced-motion: reduce`.

Only **unauthenticated** pages are exercised, so no GitHub credentials or live
OAuth are required.

## Running locally

Requires Node.js 20+.

```bash
cd saas/frontend-tests
npm ci
npx playwright install --with-deps chromium
npm test
```

The Playwright config boots the app with `python app.py` from the parent
`saas/` directory (see `webServer` in `playwright.config.js`), so a working
Python environment with the SaaS dependencies installed is also needed.

## Follow-up (tracked)

Authenticated journeys (dashboard, single/bulk scan modal, live progress,
report preview) require an OAuth mock or a test-only login shim. Add a mocked
GitHub token exchange and cover:

- repository grid empty/populated states,
- single scan modal loading → results,
- bulk scan progress + cancellation,
- report preview and cross-user report access rejection.

