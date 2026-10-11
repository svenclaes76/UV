"""Brand v1.3 tokens in the global stylesheet (docs/uvalu-brand-guidelines.md §4).

The token blocks are parsed straight out of ``uvalu.styles.GLOBAL_CSS`` so the
tests read what the browser gets, not a copy of it."""
import re

import pytest

from uvalu.styles import GLOBAL_CSS

V13_TOKENS = ("--bg", "--panel", "--panel-2", "--text", "--muted", "--faint", "--line", "--line-2",
              "--teal", "--mint", "--link", "--logo-accent", "--logo-ring", "--soft", "--up-txt", "--up-bg",
              "--down-txt", "--down-bg", "--amber-txt", "--amber-bg", "--amber-fill", "--grid",
              "--axis", "--tile", "--shadow", "--veto-bg", "--veto-line", "--nosig-bg")
# Tokens that only exist once because they're the same in both themes.
SHARED = {"--teal", "--mint", "--amber-fill"}


def _block(selector: str) -> dict[str, str]:
    """Every ``--name: value`` pair of the token blocks that start with ``selector``."""
    out: dict[str, str] = {}
    for m in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", GLOBAL_CSS):
        for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m.group(1)):
            out[name] = value.strip()
    return out


DARK = _block(":root")
LIGHT = _block('[data-theme="light"]')


@pytest.mark.parametrize("token", V13_TOKENS)
def test_every_v13_token_is_defined_for_dark(token):
    assert token in DARK, token


@pytest.mark.parametrize("token", [t for t in V13_TOKENS if t not in SHARED])
def test_every_themed_token_is_redefined_for_light(token):
    assert token in LIGHT, token


def _rgb(value: str, background: tuple[float, float, float]) -> tuple[float, float, float]:
    """A hex or rgba() colour as RGB, alpha-composited over ``background``."""
    value = value.strip()
    if value.startswith("#"):
        h = value[1:]
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    nums = [float(x) for x in re.findall(r"[\d.]+", value)]
    r, g, b, a = (nums + [1.0])[:4]
    return tuple(c * a + bg * (1 - a) for c, bg in zip((r, g, b), background))


def _luminance(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    bg_rgb = _rgb(bg, (255, 255, 255))
    l1, l2 = _luminance(_rgb(fg, bg_rgb)), _luminance(bg_rgb)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


@pytest.mark.parametrize("token", ["--text", "--muted", "--link", "--up-txt", "--down-txt", "--amber-txt"])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_readable_text_tokens_meet_4_5_to_1_on_a_card(token, theme):
    tokens = {**DARK, **LIGHT} if theme == "light" else DARK
    assert _contrast(tokens[token], tokens["--panel"]) >= 4.5, (theme, token)


def test_link_is_darker_than_signal_teal_on_white():
    """The reason --link exists: Signal Teal is 4.2:1 on white."""
    assert _contrast(DARK["--teal"], "#FFFFFF") < 4.5 <= _contrast(LIGHT["--link"], "#FFFFFF")


def test_focus_ring_is_keyboard_only():
    assert ":focus-visible" in GLOBAL_CSS and "outline: 2px solid" in GLOBAL_CSS


def _ui_sources():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "uvalu"
    return [p for p in [*root.glob("*.py"), *root.glob("pages_/*.py")]]


# Decoration that may stay --faint: provenance and footer separators, placeholders.
_FAINT_ALLOWED = (".uv-prov-sep", 'content: "·"', "::placeholder")


def test_no_readable_text_in_faint():
    """Brand v1.3 §4: --faint is decoration only; readable text is --muted."""
    hits = []
    for path in _ui_sources():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<![-\w])color:\s*var\(--faint\)", line) and not any(a in line for a in _FAINT_ALLOWED):
                hits.append(f"{path.name}:{n}")
    assert not hits, hits


def test_only_brand_radii():
    """Brand v1.3 §7: radii are 4, 6, 8 or 12px (50% for dots and rings)."""
    hits = []
    for path in _ui_sources():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"border-radius:\s*([0-9.]+)px", line):
                if m.group(1) not in {"0", "4", "6", "8", "12"}:
                    hits.append(f"{path.name}:{n} {m.group(0)}")
    assert not hits, hits


def test_no_selectors_for_retired_streamlit_test_ids():
    """Streamlit 1.60 renders pills and segmented controls as
    button[data-variant=…] with aria-pressed/aria-checked; rules on the old
    stBaseButton-pills / -segmented_control test ids silently match nothing."""
    css = re.sub(r"/\*.*?\*/", "", GLOBAL_CSS, flags=re.S)
    assert "stBaseButton-pills" not in css
    assert "stBaseButton-segmented_control" not in css
    assert 'button[data-variant="segmented_control"][aria-checked="true"]' in css


def test_button_labels_inherit_from_their_button():
    """Streamlit 1.60 renders a button label in its own <p> at 14px; the
    shared rule makes it inherit size, weight, colour and font from the
    button (S01), at :where() specificity so keyed overrides still win."""
    css = re.sub(r"/\*.*?\*/", "", GLOBAL_CSS, flags=re.S)
    assert ':where(button[data-testid^="stBaseButton-"], button[data-testid="stPopoverButton"]) { font-size: 12.5px !important; }' in css
    assert '[data-testid="stMarkdownContainer"] p) {' in css
    assert "font-size: inherit !important; font-weight: inherit !important; color: inherit !important;" in css


def test_top_nav_icons():
    """Top navigation uses the reference's Material Symbols (GL-04)."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    for page, icon in [("Dashboard", "home"), ("Screener", "monitoring"), ("Watchlist", "star"),
                       ("Portfolio", "work"), ("Risk", "shield")]:
        assert re.search(rf'title=_\("{page}"\),\s*icon=":material/{icon}:"', src), page


def test_long_form_tables_and_lead_ins():
    """LG-01/LG-02: document tables use the reference's header and cell
    styles; bold lead-ins read --text."""
    css = re.sub(r"/\*.*?\*/", "", GLOBAL_CSS, flags=re.S)
    assert '.st-key-uv_support_content [data-testid="stMarkdownContainer"] th {' in css
    assert "text-transform: uppercase; color: var(--muted) !important;" in css
    assert '[data-testid="stMarkdownContainer"] strong { color: var(--text); font-weight: 600; }' in css


def test_legal_meta_chips_have_no_colon():
    """LG-03: "Version beta 1.0", not "Version: beta 1.0"."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "uvalu/pages_/legal.py").read_text(encoding="utf-8")
    assert 'f"{html.escape(label)} <b' in src and 'f"{html.escape(label)}: <b' not in src
