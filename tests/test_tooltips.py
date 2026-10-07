"""Brand tooltips: the title= takeover script (uvalu/tooltips.py), the
Streamlit help= tooltip CSS and the Plotly hover label (runtime)."""
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from uvalu import runtime, styles, tooltips


def test_script_takes_over_title_tooltips_in_app_markup_only():
    js = tooltips.script()
    assert "__uvTip" in js                                  # installs once across reruns
    assert 'removeAttribute("title")' in js                  # no native (OS-styled) tooltip
    assert "stMarkdownContainer" in js and "stCaptionContainer" in js
    assert "aria-describedby" in js                          # still announced
    assert "%(scope)s" not in js


def test_script_is_injected_with_javascript_enabled():
    def _script():
        from uvalu import tooltips
        tooltips.inject()

    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = at.get("html")[0].proto
    assert "__uvTip" in html.body and html.unsafe_allow_javascript


def test_tooltip_css_is_light_on_light_and_covers_streamlit_help():
    css = styles.GLOBAL_CSS
    assert ".uv-tip {" in css and '[data-testid="stTooltipContent"]' in css
    light = css[css.index('[data-theme="light"] { --tip-bg'):]
    assert light.startswith('[data-theme="light"] { --tip-bg:#FFFFFF;')


def _tc(light: bool):
    return SimpleNamespace(effective_light=light, text="#0D1F3C" if light else "#F5F7FA")


def test_plotly_hoverlabel_follows_the_theme_not_the_trace():
    light = runtime.brand_hoverlabel(_tc(True))
    dark = runtime.brand_hoverlabel(_tc(False))
    assert light["bgcolor"] == "#FFFFFF" and light["font"]["color"] == "#0D1F3C"
    assert dark["bgcolor"] == "#15305A" and dark["font"]["color"] == "#F5F7FA"
    assert light["font"]["size"] == 12
