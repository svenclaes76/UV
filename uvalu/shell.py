"""Top bar shell — logo, horizontal nav, theme toggle, avatar menu.

Replaces the old st.sidebar navigation (see app.py) with the mockup's dark
top bar. Call render_topbar(nav) once per run, after st.navigation(...) is
built but before nav.run() so the bar renders above the page body.
"""
from datetime import datetime

import streamlit as st

from settings import load_settings
from uvalu import nav as nav_registry
from uvalu.runtime import current_user, theme_colors

_NAV_ITEMS = (
    ("dashboard", "Dashboard"),
    ("screener",  "Screener"),
    ("watchlist", "Watchlist"),
    ("portfolio", "Portfolio"),
    ("risk",      "Risk"),
)


def _initials(email: str) -> str:
    local = (email or "").split("@")[0]
    parts = [p for p in local.replace(".", " ").replace("_", " ").replace("-", " ").split(" ") if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _display_name(email: str) -> str:
    """Title-cased name derived from the email local-part (e.g. "marek.k@uvalu.eu"
    -> "Marek K") — there's no real display-name field on the user record, so
    this is a readable stand-in rather than a fabricated one, same source data
    as _initials() above. Shared with uvalu/pages_/admin.py's Users table so
    both surfaces render a name the same way."""
    local = (email or "").split("@")[0]
    parts = [p for p in local.replace(".", " ").replace("_", " ").replace("-", " ").split(" ") if p]
    return " ".join(p.capitalize() for p in parts) if parts else email


def apply_theme_script(light: bool) -> None:
    """Set data-theme on the parent document's <html> element from Streamlit's
    OWN active theme (st.context.theme, resolved via theme_colors()) so the
    mockup's [data-theme="light"] CSS override (uvalu/styles.py) always
    matches whatever native widgets (buttons, dataframes, Plotly charts) are
    already rendering in — a single source of truth. Streamlit's own theme
    preference (light/dark/system) is switched via the top bar's sun/moon
    toggle (see set_theme_script below), which writes the same localStorage
    key Streamlit's native app-menu theme picker used before that menu was
    hidden — st.context.theme itself is still the single point of truth this
    function reads from, only the UI for changing it moved. An earlier
    version of this function drove data-theme from an independent per-user
    setting instead; that let native widgets and the new raw-HTML cards
    disagree on light/dark, so it was dropped before the Dashboard rebuild
    (Phase 3.1) started leaning on these tokens too."""
    theme = "light" if light else "dark"
    st.iframe(f"""
<script>
(function(){{
  try {{ window.parent.document.documentElement.setAttribute('data-theme', {theme!r}); }} catch(e) {{}}
}})();
</script>
""", height=1)


def set_theme_script(target: str) -> None:
    """Persist `target` ("Light"/"Dark") to the same localStorage key
    Streamlit's own (now-hidden) app-menu theme picker writes to
    (`stActiveTheme-<base_path>-v2`), then reload. st.context.theme is only
    resolved from that value on a fresh server round-trip — a same-render
    st.rerun() would still see the OLD theme, so a full reload (not a
    lighter rerun) is what actually makes native widgets, Plotly charts and
    this custom toggle agree on the next paint.

    The key is namespaced per page path (`window.parent.location.pathname`,
    e.g. "/" or "/risk"), not hardcoded to root — each Streamlit page has its
    OWN `stActiveTheme-<path>-v2` entry, confirmed live (setting only the
    root key while on /risk did not flip that page's theme). Public (not
    module-private) since both the top bar's own toggle button below and
    uvalu/pages_/settings.py's Theme control call it.

    The reload itself is instant/abrupt (old page vanishes, blank tab, new
    page pops in) — measured with the browser's own Layout Instability API
    during development, which found zero real post-paint position shifts,
    so nothing is actually moving incorrectly; the cut just reads as a
    "flip" because there's no visual continuity across it. Fading the OLD
    page out first (instead of reloading instantly) turns that hard cut
    into a cross-fade with the NEW page's existing entry animation
    (.block-container's uvFadeIn, uvalu/styles.py) — same fix either way,
    but doing it here needs no theory about the reload's internals to work."""
    st.iframe(f"""
<script>
(function(){{
  try {{
    var path = window.parent.location.pathname;
    window.parent.localStorage.setItem('stActiveTheme-' + path + '-v2', JSON.stringify({target!r}));
    var docEl = window.parent.document.documentElement;
    docEl.style.transition = 'opacity 0.12s ease';
    docEl.style.opacity = '0';
    setTimeout(function(){{ window.parent.location.reload(); }}, 120);
  }} catch(e) {{ window.parent.location.reload(); }}
}})();
</script>
""", height=1)


def _apply_density_script(density: str) -> None:
    """Set data-density on the parent document's <html> element from the
    per-user "density" setting (Settings → Display → Table density) — the
    CSS in uvalu/styles.py reads this to tighten dataframe row padding."""
    st.iframe(f"""
<script>
(function(){{
  try {{ window.parent.document.documentElement.setAttribute('data-density', {density!r}); }} catch(e) {{}}
}})();
</script>
""", height=1)


def _topbar_css(active_path: str) -> str:
    return f"""
.st-key-uv_topbar {{
  position: sticky; top: 0; z-index: 999;
  background: var(--panel); border-bottom: 0.5px solid var(--line);
  padding: 10px 24px; margin: 0 -1.5rem 0.75rem;
  width: calc(100% + 3rem) !important; max-width: calc(100% + 3rem) !important;
  flex: none !important; min-height: 61px !important; box-sizing: border-box !important;
}}
[data-theme="light"] .st-key-uv_topbar {{ background: var(--panel); }}
/* Streamlit's stMarkdownContainer carries a built-in -16px bottom margin
   (compensating for default <p> spacing in rendered markdown) that doesn't
   apply to our raw <div> HTML — left alone, it shrinks the box the outer
   row's vertical_alignment="center" centers against, visually pushing the
   logo/tagline and Live indicator ~8px below true center. */
.st-key-uv_topbar [data-testid="stMarkdownContainer"] {{ margin: 0 !important; }}
.st-key-uv_topbar_nav {{ flex-wrap: nowrap !important; }}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] {{
  border-radius: 8px !important; padding: 7px 12px !important;
  font-size: 12.5px !important; color: var(--muted) !important;
  white-space: nowrap !important;
}}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] {{
  font-size: 16px !important;
}}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"]:hover {{
  background: var(--line-2) !important; color: var(--text) !important;
}}
.st-key-uv_topbar_nav a[href="{active_path}"] {{
  background: var(--soft) !important; color: var(--mint) !important; font-weight: 500 !important;
}}
div:has(> .st-key-uv_theme_toggle) {{ flex: none !important; width: auto !important; }}
.st-key-uv_theme_toggle button {{
  border-radius: 8px !important; background: var(--navy) !important;
  color: var(--mint) !important; border: 0.5px solid var(--line) !important;
  padding: 6px !important; min-height: 32px !important; min-width: 32px !important;
}}
/* Unlike the avatar chip (always navy+mint — a fixed brand badge), the
   theme toggle is a plain UI control and should read as "off"/neutral in
   light mode instead of standing out as a dark tile among light ones. */
[data-theme="light"] .st-key-uv_theme_toggle button {{
  background: var(--panel-2) !important; color: var(--text) !important;
  border: 0.5px solid var(--line) !important;
}}
div:has(> .st-key-uv_avatar_pop) {{ flex: none !important; width: auto !important; }}
/* The avatar control is two visually distinct zones — a navy initials pill
   plus a separate chevron — not one solid-color button. Streamlit renders
   label and chevron as sibling divs inside the button (chevron marked
   aria-hidden="true"), so style the outer button as the neutral "chip"
   shell and give just the label div its own pill treatment. */
.st-key-uv_avatar_pop button {{
  border-radius: 8px !important; background: transparent !important;
  border: 0.5px solid transparent !important;
  padding: 4px 6px !important; height: 40px !important; min-height: 40px !important;
}}
.st-key-uv_avatar_pop button:hover {{
  background: var(--panel-2) !important; border: 0.5px solid var(--line) !important;
}}
.st-key-uv_avatar_pop button > div {{ gap: 6px !important; height: 100% !important; }}
.st-key-uv_avatar_pop button > div > div:not([aria-hidden]) {{
  background: var(--navy) !important; color: var(--mint) !important;
  border-radius: 6px !important; padding: 0 8px !important;
  font-weight: 600 !important; font-size: 12px !important;
  height: 100% !important; display: flex !important; align-items: center !important;
}}
.st-key-uv_avatar_pop button [aria-hidden="true"] {{ color: var(--muted) !important; }}
.st-key-uv_avatar_menu a[data-testid="stPageLink-NavLink"] {{
  border-radius: 8px !important; padding: 8px 10px !important; font-size: 12.5px !important;
}}
.st-key-uv_avatar_menu a[data-testid="stPageLink-NavLink"]:hover {{ background: var(--line-2) !important; }}
"""


def render_topbar(nav) -> None:
    user = current_user()
    active_path = getattr(nav, "url_path", "") or ""

    # Theme/density sync scripts and the CSS injection below produce no
    # visible content, but each is still a Streamlit element and would
    # otherwise consume a full row-gap in the vertical block, pushing the
    # visible bar down the page. Collapsing them into one zero-size,
    # out-of-flow container keeps the bar flush with the top of the page.
    with st.container(key="uv_hidden_util_topbar"):
        _light = theme_colors().effective_light
        apply_theme_script(_light)
        _density = load_settings(user.email).get("density", "comfortable")
        _apply_density_script(_density)
        st.markdown(f"<style>{_topbar_css(active_path)}</style>", unsafe_allow_html=True)

    with st.container(key="uv_topbar"):
        col_logo, col_nav, col_right = st.columns([0.16, 0.5, 0.34], vertical_alignment="center")

        with col_logo:
            st.markdown(
                '<div style="display:flex;align-items:baseline;gap:9px;">'
                '<span style="font-size:20px;font-weight:500;letter-spacing:-0.03em;">'
                'uval<span style="color:var(--teal)">u</span></span>'
                '<span style="font-size:9px;letter-spacing:0.14em;text-transform:uppercase;'
                'color:var(--faint);">value engine</span></div>',
                unsafe_allow_html=True,
            )

        with col_nav:
            with st.container(key="uv_topbar_nav", horizontal=True, gap="small"):
                for key, label in _NAV_ITEMS:
                    page = nav_registry.pages.get(key)
                    if page is not None:
                        st.page_link(page, label=label)

        with col_right:
            with st.container(horizontal=True, gap="small", horizontal_alignment="right",
                              vertical_alignment="center"):
                # "Live ·" + a pulsing dot, matching Uvalu.dc.html's asOf indicator —
                # no "CET" suffix though, since the app has no real timezone
                # awareness anywhere else (every other timestamp in the app is
                # naive local time) and asserting one here would be its own
                # small fabrication.
                st.markdown(
                    '<div style="display:flex;align-items:center;gap:7px;font-size:11px;'
                    'color:var(--faint);font-family:var(--uv-mono);">'
                    '<span style="width:6px;height:6px;border-radius:50%;background:var(--mint);'
                    'box-shadow:0 0 0 3px rgba(29,214,164,0.18);"></span>'
                    f'Live · {datetime.now().strftime("%H:%M")}</div>',
                    unsafe_allow_html=True,
                )

                with st.container(key="uv_theme_toggle"):
                    _toggle_icon = ":material/dark_mode:" if _light else ":material/light_mode:"
                    if st.button("", icon=_toggle_icon, key="uv_theme_toggle_btn",
                                 help="Switch to dark theme" if _light else "Switch to light theme"):
                        set_theme_script("Dark" if _light else "Light")

                with st.container(key="uv_avatar_pop"):
                    with st.popover(_initials(user.email)):
                        st.markdown(f"**{_display_name(user.email)}**")
                        st.caption(user.email)
                        st.caption(user.role.capitalize())
                        st.divider()
                        with st.container(key="uv_avatar_menu"):
                            _settings_page = nav_registry.pages.get("settings")
                            _help_page = nav_registry.pages.get("help")
                            _admin_page = nav_registry.pages.get("admin")
                            if _settings_page is not None:
                                st.page_link(_settings_page, label="Settings")
                            if _help_page is not None:
                                st.page_link(_help_page, label="Help & docs")
                            if user.is_admin and _admin_page is not None:
                                st.page_link(_admin_page, label="Admin portal")
                        st.divider()
                        st.markdown(
                            '<a href="/?logout=1" target="_self" '
                            'style="color:var(--down-txt);font-size:12.5px;">Sign out</a>',
                            unsafe_allow_html=True,
                        )
