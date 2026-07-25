"""Streamlit web app — uvalu value screener + portfolio tracker (entry point).

This module is the thin app shell: page config, global styles, the auth gate,
navigation registration and the sidebar. All page bodies and shared helpers live
in the ``uvalu`` package (see uvalu/pages_/ and the shared modules).
"""
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import streamlit as st

from portfolio import set_user

from uvalu import authgate, nav, shell, styles
from uvalu.drawer import dispatch_pending_drawer_action
from uvalu.runtime import current_user
from uvalu.pages_ import (dashboard as _page_dashboard, portfolio as _page_portfolio,
                          risk as _page_risk, screener as _page_screener,
                          watchlist as _page_watchlist, analysis as _page_analysis,
                          settings as _page_settings, help as _page_help,
                          admin as _page_admin)

# ── Page config + global styles ───────────────────────────────────────────────
st.set_page_config(
    page_title="uvalu",
    page_icon="favicon.svg",
    layout="wide",
    initial_sidebar_state="collapsed",
)
styles.inject()

# ── Authentication gate (see uvalu.authgate) ──────────────────────────────────
authgate.recover_session_from_cookie()
authgate.handle_logout()

# Resolve the current user and point the data layer at their storage.
_email = current_user().email
set_user(_email)

authgate.auth_wall()

# Keep the localStorage/cookie JWT fresh for the next full page load — the
# cookie is what recover_session_from_cookie() (uvalu/authgate.py) actually
# reads server-side to survive a reload (e.g. the top bar's theme toggle).
with st.container(key="uv_hidden_util_jwt"):
    st.iframe(f"""
<script>
(function(){{
  var tok = {repr(st.session_state.get('jwt_token', ''))};
  if (tok) {{
    localStorage.setItem('uv_jwt', tok);
    document.cookie = 'uv_jwt=' + encodeURIComponent(tok) + '; path=/; max-age=86400';
  }}
}})();
</script>
""", height=1)

# ── Navigation ────────────────────────────────────────────────────────────────
_pg_dashboard = st.Page(_page_dashboard.render, title="Dashboard", icon=":material/dashboard:", default=True)
_pg_portfolio = st.Page(_page_portfolio.render, title="Portfolio", icon=":material/business_center:", url_path="portfolio")
_pg_risk      = st.Page(_page_risk.render,      title="Risk",      icon=":material/monitoring:",      url_path="risk")
_pg_screener  = st.Page(_page_screener.render,  title="Screener",  icon=":material/search:",          url_path="screener")
_pg_watchlist = st.Page(_page_watchlist.render, title="Watchlist", icon=":material/star:",             url_path="watchlist")
_pg_analysis  = st.Page(_page_analysis.render,  title="Analysis",  icon=":material/query_stats:",     url_path="analysis")
_pg_settings  = st.Page(_page_settings.render,  title="Settings",  icon=":material/settings:",        url_path="settings")
_pg_help      = st.Page(_page_help.render,      title="Help",      icon=":material/help:",            url_path="help")
_pg_admin     = st.Page(_page_admin.render,     title="Admin",     icon=":material/shield_person:",   url_path="admin")

# Populate the shared registry so page modules can link to one another.
# _pg_analysis and _pg_admin are deliberately not in the top-bar nav
# (uvalu/shell.py) — Analysis is only reached via the drawer's "View full
# analysis" link, Admin only via the avatar dropdown (admin role only).
nav.pages.update({
    "dashboard": _pg_dashboard, "portfolio": _pg_portfolio, "risk": _pg_risk,
    "screener": _pg_screener, "watchlist": _pg_watchlist, "analysis": _pg_analysis,
    "settings": _pg_settings, "help": _pg_help, "admin": _pg_admin,
})

_nav = st.navigation(
    [_pg_dashboard, _pg_portfolio, _pg_risk, _pg_screener, _pg_watchlist,
     _pg_analysis, _pg_settings, _pg_help, _pg_admin],
    position="hidden",
)

# Legacy ?page= deep links (pre-st.navigation) → redirect to the new URL paths
_legacy_page = st.query_params.get("page", "")
if _legacy_page:
    del st.query_params["page"]
    if _legacy_page in nav.pages:
        st.switch_page(nav.pages[_legacy_page])

# Admin renders its own standalone sidebar/topbar (uvalu/pages_/admin.py),
# matching Uvalu Admin.dc.html's separate shell — skip the main app's
# horizontal top-bar nav for it instead of stacking both.
if _nav.url_path != "admin":
    shell.render_topbar(_nav)
# Outside any dialog context, before the page body runs — opens the Buy/Sell
# dialog the drawer's own buttons requested (Streamlit forbids nesting one
# @st.dialog inside another, so open_drawer() can't call them directly).
dispatch_pending_drawer_action()
_nav.run()
