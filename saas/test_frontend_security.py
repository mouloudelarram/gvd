"""Frontend XSS-hardening regression tests (Phase 6).

These are static-source guards that run in the normal pytest suite (no browser
or Node required). They fail if a previously-fixed unescaped interpolation is
reintroduced into the dashboard JavaScript. A full browser/e2e suite runs
separately in CI where Node is available.
"""

from pathlib import Path

import pytest

JS_DIR = Path(__file__).parent / "static" / "js"


@pytest.fixture(scope="module")
def dashboard_js():
    return (JS_DIR / "dashboard.js").read_text(encoding="utf-8")


# Patterns that inject GitHub/user-controlled values into HTML *without*
# escaping. Each was fixed; this guards against regressions (defense in depth).
FORBIDDEN_UNESCAPED = [
    'data-owner="${owner}"',
    'data-repo="${repo.name}"',
    'data-repo-url="${repoUrl}"',
    'data-visibility="${visibility}"',
    '${visibility.toUpperCase()}',
    '<strong>Error:</strong> ${verifyError.message}',
    'href="${url}"',
]


@pytest.mark.parametrize("needle", FORBIDDEN_UNESCAPED)
def test_no_unescaped_interpolation(dashboard_js, needle):
    assert needle not in dashboard_js, (
        f"Unescaped interpolation reintroduced: {needle!r}. "
        "Wrap user/GitHub-controlled values in window.GVD.utils.escapeHtml()."
    )


def test_search_result_uses_escaper(dashboard_js):
    # The search-result builder must route attributes through the escaper.
    assert 'const esc = window.GVD.utils.escapeHtml;' in dashboard_js
    assert 'data-repo-url="${esc(repoUrl)}"' in dashboard_js


def test_external_links_have_noopener(dashboard_js):
    # Any target="_blank" anchor must carry rel="noopener" to avoid reverse
    # tabnabbing.
    idx = 0
    while True:
        idx = dashboard_js.find('target="_blank"', idx)
        if idx == -1:
            break
        window = dashboard_js[max(0, idx - 200): idx + 200]
        assert "noopener" in window, (
            "target=\"_blank\" link without rel=\"noopener\" near: "
            f"...{dashboard_js[idx - 40:idx + 40]}..."
        )
        idx += 1


def test_escape_html_escapes_quotes():
    # base.js escapeHtml must handle both quote styles so it is attribute-safe.
    base_js = (JS_DIR / "base.js").read_text(encoding="utf-8")
    assert '.replaceAll(\'"\', "&quot;")' in base_js
    assert '.replaceAll("\'", "&#39;")' in base_js


TEMPLATES_DIR = Path(__file__).parent / "templates"


def test_templates_blank_links_have_noopener():
    """Every target="_blank" anchor in a template must carry rel="noopener"."""
    offenders = []
    for html in TEMPLATES_DIR.glob("*.html"):
        text = html.read_text(encoding="utf-8")
        idx = 0
        while True:
            idx = text.find('target="_blank"', idx)
            if idx == -1:
                break
            window = text[max(0, idx - 300): idx + 300]
            if "noopener" not in window:
                offenders.append(f"{html.name}: ...{text[idx - 40:idx + 40]}...")
            idx += 1
    assert not offenders, "target=_blank without rel=noopener:\n" + "\n".join(offenders)



