"""AC1 / AC4 (docs/accessibility-review.md): headings, landmarks, skip link,
page titles. The script itself runs in the browser; these tests pin what the
Python side emits and stop new section titles from losing their heading role."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
H2 = 'role="heading" aria-level="2"'


def test_page_and_card_titles_are_headings():
    from uvalu.components import card_header_html, page_heading_html
    assert 'role="heading" aria-level="1"' in page_heading_html("Risk assessment")
    assert H2 in card_header_html("Holdings")


def test_every_section_title_is_a_heading():
    """A 15px/500 title in a page module is a section title (brand §7); each
    carries role="heading" aria-level="2". Values in that size (a green
    figure on the Dashboard) are colour-coded and don't count."""
    missing = []
    for path in sorted((ROOT / "uvalu").rglob("*.py")):
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r'<(?:div|span) ([^>]*?)style="font-size:15px;font-weight:500;([^"]*)"', line):
                attrs, rest = m.group(1), m.group(2)
                if "uv-mono" in rest or "up-txt" in rest or "font-family" in rest:
                    continue
                if H2 not in attrs:
                    missing.append(f"{path.relative_to(ROOT)}:{no}")
    assert not missing, "section titles without a heading role: " + ", ".join(missing)


def test_sign_in_headings_are_level_one():
    src = (ROOT / "uvalu" / "authgate.py").read_text(encoding="utf-8")
    assert src.count('class="uv-login-heading"') == src.count(
        'class="uv-login-heading" role="heading" aria-level="1"') > 0


def test_landmark_script_marks_nav_main_footer_and_adds_skip_link(monkeypatch):
    from uvalu import shell
    seen = []
    monkeypatch.setattr(shell.st, "iframe", lambda body, **kw: seen.append(body))
    shell.render_landmarks("risk")
    (body,) = seen
    assert "/* page: risk */" in body   # differs per page, so it runs again on navigation
    for sel, role in ((".st-key-uv_topbar_nav", "navigation"), (".st-key-uv_main", "main"),
                      (".st-key-uv_footer", "contentinfo")):
        assert f"mark('{sel}', '{role}'" in body
    assert '"skip": "Skip to content"' in body and '"nav": "Main"' in body
    assert "d.body.insertBefore(a, d.body.firstChild)" in body


def test_app_wraps_the_page_body_and_titles_each_page():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'with st.container(key="uv_main"):\n        _nav.run()' in src.replace("\r\n", "\n")
    assert 'st.set_page_config(page_title=f"{_nav.title} · Uvalu")' in src
    assert "shell.render_landmarks(" in src
