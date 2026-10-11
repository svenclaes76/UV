"""uvalu/logo.py — the lockup as inline SVG (logo plan L2, L3)."""
import re
from pathlib import Path

from uvalu.logo import lockup_svg
from uvalu.styles import GLOBAL_CSS

LOGO = Path(__file__).resolve().parent.parent / "assets" / "logo"


def _token(theme_block: str, name: str) -> str:
    return re.search(rf"{name}:(#[0-9A-Fa-f]{{6}})", theme_block).group(1)


def _theme_blocks():
    """(dark, light) token blocks: the :root and [data-theme="light"] rules
    that define the logo tokens."""
    css = re.sub(r"/\*.*?\*/", "", GLOBAL_CSS, flags=re.S)
    blocks = re.findall(r"(:root|\[data-theme=\"light\"\]) \{([^}]*)\}", css)
    dark = next(b for sel, b in blocks if sel == ":root" and "--logo-ring" in b)
    light = next(b for sel, b in blocks if sel != ":root" and "--logo-ring" in b)
    return dark, light


def _fills(svg: str) -> list:
    return re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6}|var\(--[a-z-]+\))"', svg)


def test_markup_is_the_outlined_lockup_at_the_requested_mark_height():
    svg = lockup_svg(26, theme_tokens=True)
    assert "<text" not in svg and 'role="img" aria-label="Uvalu"' in svg
    assert 'height="26"' in svg
    view_w = re.search(r'viewBox="0 0 ([0-9.]+) 64"', (LOGO / "uvalu-lockup-dark.svg").read_text(encoding="utf-8")).group(1)
    assert f'viewBox="0 0 {float(view_w):g} 64"' in svg


def test_top_bar_lockup_is_the_light_lockup_in_light_and_the_dark_lockup_in_dark():
    """Decided 11 Oct 2026: light lockup in the light theme. With each theme's
    token values filled in, the top-bar markup has exactly that file's inks."""
    dark, light = _theme_blocks()
    svg = lockup_svg(26, theme_tokens=True)
    for block, name in ((dark, "uvalu-lockup-dark.svg"), (light, "uvalu-lockup-light.svg")):
        filled = (svg.replace("var(--logo-ring)", _token(block, "--logo-ring"))
                     .replace("var(--logo-accent)", _token(block, "--logo-accent")))
        assert _fills(filled) == _fills((LOGO / name).read_text(encoding="utf-8")), name


def test_dark_only_surfaces_keep_the_dark_lockup_colours():
    svg = lockup_svg(48, theme_tokens=False)
    assert "var(--" not in svg
    assert _fills(svg) == _fills((LOGO / "uvalu-lockup-dark.svg").read_text(encoding="utf-8"))


def test_no_old_wordmark_left_in_the_app():
    """Logo plan L5: no live-text wordmark and no old sidebar-logo styles."""
    root = Path(__file__).resolve().parent.parent
    sources = list((root / "uvalu").rglob("*.py")) + [root / "app.py"]
    assert not [p.name for p in sources if "uval<span" in p.read_text(encoding="utf-8")]
    for cls in (".uv-logo-wordmark", ".uv-logo-accent", ".uv-logo-sub", ".uv-logo "):
        assert cls not in GLOBAL_CSS, cls
