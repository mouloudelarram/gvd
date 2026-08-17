# GVD — Cleanup Report

Evidence-backed inventory of obsolete, duplicated, generated, unsafe, or unused
artifacts and the decision/recommendation for each. Follows the CLEANUP rules:
every removal is preceded by a reference search, a replacement identification,
and a build/test/deploy impact check; important removals are also logged in
`MIGRATION_NOTES.md`.

Status legend: ✅ removed · 🟡 recommended (needs a gate before removal) ·
🔴 bug (unloaded asset that should probably be wired in, not deleted).

## 1. Templates

| Artifact | Evidence | Decision |
|----------|----------|----------|
| `saas/templates/scan_results.html` | No `render_template`/`url_for` reference (grep, all `*.py`); live replacement is the `#scan-modal` in `dashboard.html`; linked two non-existent assets (`css/scan-results.css`, `js/scan-results.js`). | ✅ **Removed** (C-22). Guard test `test_templates_reference_only_existing_static_assets` prevents recurrence. |

## 1b. Superseded implementation-snippet files (Phase 9, C-27)

| Artifact | Evidence | Decision |
|----------|----------|----------|
| `saas/BACKEND_CHANGES.py`, `saas/FRONTEND_CHANGES.js`, `saas/HTML_CHANGES.html` | Copy-paste "code snippets" from the original bulk-scan rollout. Imported by **no** module (grep); referenced only by two how-to guides. The feature is **already integrated**: `app.py` bulk-scan routes/jobs + `bulk_scan_service.py` (`BulkScanManager`) + loaded/tested `bulk-scan-and-notifications.js` + the dashboard bulk-scan modal. | ✅ **Removed** as dead duplicate implementation. `IMPLEMENTATION_GUIDE.md`/`QUICK_REFERENCE.md` given a "superseded — see integrated files" banner so no doc points at a deleted file. Suite still **111 / 0** (nothing imported them). |

## 2. Stylesheets not loaded by any page — resolved (Phase 9)

`base.html` loads `variables, base, components, layout,
bulk-scan-and-notifications`; per-page `extra_css` adds `dashboard`,
`scan-history`, `auth`, `legal`, `support`, `documentation`. The files below
were loaded by **no** template and not `@import`ed by any loaded stylesheet, so
deleting them is **runtime-neutral** (they never rendered). All were removed in
Phase 9 (C-26).

| File | Evidence | Decision |
|------|----------|----------|
| `static/css/animations.css` | **Zero** usages of its classes (`animate-*`, `loading-skeleton/-dots/-circle`, `hover-lift`, `stagger-*`) across all templates + JS (grep). Reduced-motion support is **also** present in the loaded `base.css` (`@media (prefers-reduced-motion: reduce)` blanket reset), so no runtime a11y loss. | ✅ **Removed.** Guard `test_reduced_motion_support_present` repointed to the loaded `base.css`. |
| `static/css/accessibility.css` | Not loaded. `.sr-only`/`.visually-hidden`/`.skip-to-content` and reduced-motion already live in loaded `base.css`; `prefers-contrast: high` already in loaded `base.css`/`dashboard.css`/`auth.css`; touch-target (`pointer: coarse`) sizing already in loaded `dashboard.css`/`auth.css`. File also had a corrupt line-2 comment (`* … */` with no opening `/*`) → legacy/unmaintained. | ✅ **Removed** as redundant. |
| `static/css/responsive.css` | Not loaded. Targets **live** selectors (`.dashboard-container`, `.repo-grid`, `.modal`, `.header-container`, `.auth-hero`, `.footer-container`, `.toast-container`). **Static proof of redundancy:** loaded `dashboard.css` implements breakpoints at 1400/1200/1024/768/640/480 with responsive `.repo-grid` (`auto-fill/auto-fit minmax`), `auth.css` at 1200/1024/768/480 with `.auth-container` collapse, `scan-history.css` at 768/480 — i.e. the live layout is **already responsive** for the same selectors (and the loaded rules are arguably better). Also had the same corrupt line-2 comment. | ✅ **Removed** as redundant (not a missing-mobile bug — resolved the earlier 🔴 by static evidence, no browser needed since the file never loaded). |
| `static/css/utilities.css` | Not loaded. Tailwind-style utilities (`.p-*`, `.flex`, `.text-center`, `.hidden`, `.w-full`, …). Grep of all templates for a broad set of these class names → **no results**; no JS toggles them. Pure dead code. | ✅ **Removed.** |
| `static/style.css` (static root) | Not loaded by any template (only the modular `static/css/*.css` are linked). Referenced only in `README.md` (documentation drift). | ✅ **Removed** and README corrected. |

**Note (accepted follow-up):** `accessibility.css` also contained never-active
"nice to have" rules (tooltips, `aria-busy` spinner, data-table styling). These
were never rendered (file unloaded); if any are wanted later they should be
authored directly into a *loaded* stylesheet. Tracked as a low-priority
enhancement, not a regression.

## 3. Verified NOT dead (kept)

- `static/css/{variables,base,components,layout,bulk-scan-and-notifications,dashboard,scan-history,auth,legal,support,documentation}.css` — all referenced.
- `static/js/{base,dashboard,bulk-scan-and-notifications}.js` — all referenced.
- `static/images/{favicon,logo}.png` — referenced by templates.

## 4. Follow-up actions

1. ✅ **Done (Phase 9, C-26):** removed the 5 non-loaded stylesheets above; the
   removals are runtime-neutral (files were never linked), so no browser gate
   was required. Reduced-motion guard repointed to the loaded `base.css`.
2. The `frontend-test` (Playwright + axe) CI job remains the gate for the
   *authenticated* journeys and colour-contrast sweep (blocked locally by B5:
   no Node). It is wired and ready to run in CI.
3. Low-priority enhancement: if high-contrast/tooltip/data-table styling from
   the removed `accessibility.css` is desired, author it into a *loaded*
   stylesheet (it was never active before).

