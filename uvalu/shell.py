"""Top bar shell — logo, horizontal nav, theme toggle, avatar menu.

Replaces the old st.sidebar navigation (see app.py) with the mockup's dark
top bar. Call render_topbar(nav) once per run, after st.navigation(...) is
built but before nav.run() so the bar renders above the page body.
"""
from datetime import datetime

import streamlit as st

from settings import load_settings, save_settings
from uvalu import nav as nav_registry
from uvalu.runtime import current_user

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


def _apply_theme_script(theme: str) -> None:
    """Set data-theme on the parent document's <html> element so the mockup's
    [data-theme="light"] CSS override (uvalu/styles.py) takes effect. This is
    independent of Streamlit's own native browser-level theme (st.context.theme,
    used by uvalu.runtime.theme_colors() for Plotly charts) — the mockup's
    custom-styled surfaces (top bar, cards) and native Streamlit widgets can
    follow different theme sources today; see Phase 1 plan notes."""
    st.iframe(f"""
<script>
(function(){{
  try {{ window.parent.document.documentElement.setAttribute('data-theme', {theme!r}); }} catch(e) {{}}
}})();
</script>
""", height=1)


def _topbar_css(active_path: str) -> str:
    return f"""
.st-key-uv_topbar {{
  position: sticky; top: 0; z-index: 999;
  background: var(--panel); border-bottom: 0.5px solid var(--line);
  padding: 10px 24px; margin: -1rem -1.5rem 0.75rem;
}}
[data-theme="light"] .st-key-uv_topbar {{ background: var(--panel); }}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] {{
  border-radius: 8px !important; padding: 7px 12px !important;
  font-size: 12.5px !important; color: var(--muted) !important;
}}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"]:hover {{
  background: var(--line-2) !important; color: var(--text) !important;
}}
.st-key-uv_topbar_nav a[href="{active_path}"] {{
  background: var(--soft) !important; color: var(--mint) !important; font-weight: 500 !important;
}}
.st-key-uv_avatar_pop button {{
  border-radius: 8px !important; background: var(--navy) !important;
  color: var(--mint) !important; border: 0.5px solid var(--line) !important;
  font-weight: 600 !important; font-size: 12px !important;
}}
.st-key-uv_avatar_menu a[data-testid="stPageLink-NavLink"] {{
  border-radius: 8px !important; padding: 8px 10px !important; font-size: 12.5px !important;
}}
.st-key-uv_avatar_menu a[data-testid="stPageLink-NavLink"]:hover {{ background: var(--line-2) !important; }}
"""


def render_topbar(nav) -> None:
    user = current_user()
    settings = load_settings(user.email)
    theme = settings.get("ui_theme", "dark")
    _apply_theme_script(theme)

    active_path = getattr(nav, "url_path", "") or ""
    st.markdown(f"<style>{_topbar_css(active_path)}</style>", unsafe_allow_html=True)

    with st.container(key="uv_topbar"):
        col_logo, col_nav, col_right = st.columns([0.16, 0.5, 0.34], vertical_alignment="center")

        with col_logo:
            st.markdown(
                '<span style="font-size:20px;font-weight:500;letter-spacing:-0.03em;">'
                'uval<span style="color:var(--teal)">u</span></span>',
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
                st.caption(f"As of {datetime.now().strftime('%H:%M')}")

                if st.button("🌗", key="uv_theme_toggle", help="Toggle theme", type="tertiary"):
                    settings["ui_theme"] = "light" if theme == "dark" else "dark"
                    save_settings(settings, user.email)
                    st.rerun()

                with st.container(key="uv_avatar_pop"):
                    with st.popover(_initials(user.email)):
                        st.markdown(f"**{user.email}**")
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
