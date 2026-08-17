"""Frontend accessibility regression tests (Phase 6, WCAG 2.2 AA).

Static-source guards that run in the normal pytest suite (no browser/Node
needed). They assert the accessibility affordances added to templates and the
shared JS remain in place. A full axe/browser audit runs in CI.
"""

from pathlib import Path

BASE = Path(__file__).parent
TEMPLATES = BASE / "templates"
JS = BASE / "static" / "js"


def _read(path):
    return path.read_text(encoding="utf-8")
def test_toast_container_is_live_region():
    html = _read(TEMPLATES / "base.html")
    assert 'id="toast-container"' in html
    assert 'aria-live="polite"' in html
    assert 'role="status"' in html


def test_header_menu_buttons_have_aria_state():
    html = _read(TEMPLATES / "base.html")
    # Notifications + user menu toggles must advertise popup state.
    assert 'id="notifications-btn"' in html
    assert 'id="user-dropdown-toggle"' in html
    for marker in ('aria-haspopup', 'aria-expanded="false"', 'aria-controls'):
        assert html.count(marker) >= 2, f"expected {marker} on both menu toggles"
    assert 'id="user-dropdown" role="menu"' in html


def test_skip_link_and_landmarks_present():
    html = _read(TEMPLATES / "base.html")
    assert 'class="skip-to-content"' in html
    assert 'href="#main-content"' in html
    for role in ('role="banner"', 'role="main"', 'role="contentinfo"'):
        assert role in html


def test_dashboard_form_controls_have_accessible_names():
    html = _read(TEMPLATES / "dashboard.html")
    assert 'id="repo-search"' in html and 'aria-label="Search repositories"' in html
    assert 'aria-label="Filter repositories by visibility"' in html


def test_modal_js_supports_escape_focus_trap_and_restore():
    js = _read(JS / "base.js")
    # Escape-to-close.
    assert 'e.key === "Escape"' in js
    # Focus trap on Tab.
    assert 'e.key === "Tab"' in js
    # Restore focus to the triggering element on close.
    assert "_lastTrigger" in js
    # Mark the dialog for assistive tech.
    assert 'aria-modal' in js


def test_dropdown_js_syncs_aria_expanded():
    js = _read(JS / "base.js")
    assert "_syncAria" in js
    assert 'setAttribute("aria-expanded"' in js


def test_toast_uses_alert_role_for_errors():
    js = _read(JS / "base.js")
    assert '"alert"' in js and '"status"' in js


def test_reduced_motion_support_present():
    """Motion-sensitive users must get a reduced-motion path (WCAG 2.3.3).

    Asserted against the *loaded* base.css (linked by base.html) rather than an
    unloaded stylesheet, so the guard reflects behaviour users actually receive.
    """
    css = _read(BASE / "static" / "css" / "base.css")
    assert "@media (prefers-reduced-motion: reduce)" in css
    # The blanket reset must neutralise animations/transitions for all elements.
    assert "animation-duration: 0.01ms" in css
    assert "transition-duration: 0.01ms" in css


def test_dashboard_has_empty_and_loading_states():
    """The repository journey must cover empty, loading and error states."""
    html = _read(TEMPLATES / "dashboard.html")
    # Empty state when no repositories are returned.
    assert 'class="empty-state"' in html
    assert "No repositories found" in html
    # Loading placeholders inside the detail/scan modals.
    assert "Loading repository details" in html
    assert "Loading report" in html
    # Success/error alert region for flashed messages.
    assert 'class="alert alert-success"' in html


def test_scan_history_has_empty_state():
    """The scan-history journey must show a friendly empty state."""
    html = _read(TEMPLATES / "scan_history.html")
    assert 'class="empty-state"' in html


def test_dashboard_html_has_no_leaked_script_after_endblock():
    """Guard against the corruption where raw JS leaked past {% endblock %}."""
    html = _read(TEMPLATES / "dashboard.html")
    # A child template that extends base.html must not emit its own </html>.
    assert "</html>" not in html
    assert "pollBulkScanJob" not in html
    assert "bulk-report-item__header" not in html


def test_templates_reference_only_existing_static_assets():
    """Every static filename referenced by a template must exist on disk.

    Catches the class of bug where a template linked css/scan-results.css or
    js/scan-results.js that were never shipped (dead template scan_results.html).
    """
    import re

    static_dir = BASE / "static"
    pattern = re.compile(r"filename=['\"]([^'\"{}]+)['\"]")
    missing = []
    for html in TEMPLATES.glob("*.html"):
        for asset in pattern.findall(_read(html)):
            if not (static_dir / asset).is_file():
                missing.append(f"{html.name} -> {asset}")
    assert not missing, (
        "Templates reference missing static assets:\n" + "\n".join(missing)
    )



