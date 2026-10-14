"""AC1–AC4 (docs/accessibility-review.md): headings, landmarks, skip link,
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


def test_page_script_marks_landmarks_icons_and_names(monkeypatch):
    from uvalu import a11y
    seen = []
    monkeypatch.setattr(a11y.st, "iframe", lambda body, **kw: seen.append(body))
    a11y.begin_run()
    a11y.label("scr_row_ASML.AS_action", "On the watchlist: ASML (ASML.AS)", pressed=True)
    a11y.render("risk")
    (body,) = seen
    assert "/* page: risk */" in body   # differs per page, so it runs again on navigation
    for sel, role in ((".st-key-uv_topbar_nav", "navigation"), (".st-key-uv_main", "main"),
                      (".st-key-uv_footer", "contentinfo")):
        assert f"mark('{sel}', '{role}'" in body
    assert '"skip": "Skip to content"' in body and '"nav": "Main"' in body
    assert "d.body.insertBefore(a, d.body.firstChild)" in body
    assert "stIconMaterial" in body and "MutationObserver" in body
    # Streamlit's class for a key with "." uses "-" instead.
    assert '"scr_row_ASML-AS_action": ["On the watchlist: ASML (ASML.AS)", true]' in body


def test_early_render_keeps_the_previous_names(monkeypatch):
    from uvalu import a11y
    seen = []
    monkeypatch.setattr(a11y.st, "iframe", lambda body, **kw: seen.append(body))
    a11y.render("risk", names=False)
    assert "var aria = null;" in seen[0]


def test_names_cannot_close_the_script():
    from uvalu import a11y
    assert "</script>" not in a11y._js({"x": "</script><b>"})


def test_stock_name():
    from uvalu import a11y
    assert a11y.stock_name("INVE-B.ST", "Investor AB") == "Investor AB (INVE-B.ST)"
    assert a11y.stock_name("ASML.AS", "") == "ASML.AS"
    assert a11y.stock_name("ASML.AS", "ASML.AS") == "ASML.AS"


_BARE = re.compile(r'st\.(?:button|popover)\((?:"(?:★|×|✎|)"|_\("View(?: details)?"\))')


def test_every_unnamed_row_or_icon_button_registers_a_name():
    """AC2/AC3: a button whose visible text is "★", "×", "✎", "View" or only
    an icon calls a11y.label() for its key within a few lines."""
    missing = []
    for path in sorted((ROOT / "uvalu").rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not _BARE.search(line):
                continue
            window = "\n".join(lines[max(0, i - 4):i + 4])
            if "a11y.label(" not in window:
                missing.append(f"{path.relative_to(ROOT)}:{i + 1}")
    assert not missing, "buttons without a screen-reader name: " + ", ".join(missing)


def test_app_wraps_the_page_body_and_titles_each_page():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'with st.container(key="uv_main"):\n        _nav.run()' in src.replace("\r\n", "\n")
    assert 'st.set_page_config(page_title=f"{_nav.title} · Uvalu")' in src
    assert "a11y.render(" in src and "a11y.begin_run()" in src


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def test_primary_button_fill_has_4_5_to_1_with_white():
    """AC5: white 12.5px text on the primary fill (and its hover) is at
    least 4.5:1, and primary buttons use that fill."""
    from uvalu import styles
    css = styles.__dict__.get("_CSS") or (ROOT / "uvalu" / "styles.py").read_text(encoding="utf-8")
    for token in ("--primary-fill", "--primary-fill-hover"):
        m = re.search(token + r":(#[0-9A-Fa-f]{6});", css)
        assert m, token
        assert 1.05 / (_luminance(m.group(1)) + 0.05) >= 4.5, (token, m.group(1))
    assert re.search(r'button\[data-testid="stBaseButton-primary"\],\s*button\[data-testid='
                     r'"stBaseButton-primaryFormSubmit"\] \{\s*background-color: var\(--primary-fill\)', css)
