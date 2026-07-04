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

from uvalu import authgate, nav, styles
from uvalu.runtime import current_user
from uvalu.pages_ import (dashboard as _page_dashboard, portfolio as _page_portfolio,
                          risk as _page_risk, screener as _page_screener,
                          settings as _page_settings, help as _page_help)

# ── Page config + global styles ───────────────────────────────────────────────
st.set_page_config(
    page_title="uvalu",
    page_icon="favicon.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)
styles.inject()

# ── Authentication gate (see uvalu.authgate) ──────────────────────────────────
authgate.restore_token_from_query()
authgate.recover_session_from_localstorage()
authgate.handle_logout()

# Resolve the current user and point the data layer at their storage.
_email = current_user().email
set_user(_email)

authgate.auth_wall()

# Keep the localStorage JWT fresh for the next full page load.
st.iframe(f"""
<script>
(function(){{
  var tok = {repr(st.session_state.get('jwt_token', ''))};
  if (tok) localStorage.setItem('uv_jwt', tok);
}})();
</script>
""", height=1)

# ── Navigation ────────────────────────────────────────────────────────────────
_pg_dashboard = st.Page(_page_dashboard.render, title="Dashboard", icon=":material/dashboard:", default=True)
_pg_portfolio = st.Page(_page_portfolio.render, title="Portfolio", icon=":material/business_center:", url_path="portfolio")
_pg_risk      = st.Page(_page_risk.render,      title="Risk",      icon=":material/monitoring:",      url_path="risk")
_pg_screener  = st.Page(_page_screener.render,  title="Screener",  icon=":material/search:",          url_path="screener")
_pg_settings  = st.Page(_page_settings.render,  title="Settings",  icon=":material/settings:",        url_path="settings")
_pg_help      = st.Page(_page_help.render,      title="Help",      icon=":material/help:",            url_path="help")

# Populate the shared registry so page modules can link to one another.
nav.pages.update({
    "dashboard": _pg_dashboard, "portfolio": _pg_portfolio, "risk": _pg_risk,
    "screener": _pg_screener, "settings": _pg_settings, "help": _pg_help,
})

_nav = st.navigation(
    [_pg_dashboard, _pg_portfolio, _pg_risk, _pg_screener, _pg_settings, _pg_help],
    position="hidden",
)

# Legacy ?page= deep links (pre-st.navigation) → redirect to the new URL paths
_legacy_page = st.query_params.get("page", "")
if _legacy_page:
    del st.query_params["page"]
    if _legacy_page in nav.pages:
        st.switch_page(nav.pages[_legacy_page])

with st.sidebar:
    st.markdown("""
<div class="uv-logo">
  <div>
    <div class="uv-logo-wordmark">uval<span class="uv-logo-accent">u</span></div>
    <div class="uv-logo-sub">Find value before the market does.</div>
  </div>
</div>
""", unsafe_allow_html=True)
    st.page_link(_pg_dashboard)
    st.page_link(_pg_portfolio)
    st.page_link(_pg_risk)
    st.page_link(_pg_screener)
    st.divider()
    st.page_link(_pg_settings)
    st.page_link(_pg_help)
    st.markdown(f"""
<div class="uv-bottom">
  <div class="uv-bottom-email" style="margin-bottom:8px;">{_email}</div>
  <div style="text-align:center;">
    <a href="/?logout=1" target="_self" class="uv-logout" onclick="try{{window.parent.localStorage.removeItem('uv_jwt')}}catch(e){{}}">Log out</a>
  </div>
</div>
""", unsafe_allow_html=True)

_nav.run()
