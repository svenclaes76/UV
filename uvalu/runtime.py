"""Per-run shared state accessors.

The app resolves the current user and theme on every script run. These helpers
read that state fresh from ``st.session_state`` / ``st.context`` each call, so
page modules can obtain it without importing mutable module-level globals from
``app.py`` (which would create an import cycle and bind stale values).
"""
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class ThemeColors:
    """Plotly/chart palette tokens for the active light/dark theme variant."""
    effective_light: bool
    axis: str
    grid: str
    invested: str
    text: str
    surface: str
    up_txt: str
    down_txt: str


def theme_colors() -> ThemeColors:
    """Resolve the chart palette from the browser's active theme variant."""
    light = getattr(st.context.theme, "type", None) == "light"
    return ThemeColors(
        effective_light=light,
        axis="#5F5E5A"             if light else "rgba(245,247,250,0.55)",
        grid="rgba(0,0,0,0.07)"    if light else "rgba(255,255,255,0.06)",
        invested="rgba(59,77,99,0.45)" if light else "rgba(245,247,250,0.35)",
        text="#0D1F3C"             if light else "#F5F7FA",
        surface="#F5F7FA"          if light else "#0D1F3C",
        # Matches Uvalu.dc.html's --up-txt/--down-txt tokens (uvalu/styles.py) —
        # literal hex, not var(), since Python-computed colors (Plotly traces,
        # pandas Styler cell colors) can't resolve CSS custom properties.
        up_txt="#0F6E56"           if light else "#1DD6A4",
        down_txt="#A32D2D"         if light else "#F0A6A6",
    )


@dataclass(frozen=True)
class CurrentUser:
    email: str
    role: str
    is_admin: bool
    is_viewer: bool


def current_user() -> CurrentUser:
    """Resolve the logged-in user from session state.

    role is one of auth.ROLES ("Admin"/"Analyst"/"Viewer") — see auth.py's
    _normalize_user for how legacy lowercase admin/user values are mapped.
    """
    email = st.session_state.get("user_email", "")
    role = st.session_state.get("user_role", "Analyst")
    return CurrentUser(email=email, role=role, is_admin=(role == "Admin"), is_viewer=(role == "Viewer"))
