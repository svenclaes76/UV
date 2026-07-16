"""Authentication gate: JWT/localStorage bridges, logout, and the login wall.

These run at module scope in the app's boot sequence. Each step is a function so
``app.py`` can invoke them in order while keeping the logic out of its body.
"""
import streamlit as st

from auth import login, verify_token
from uvalu import shell
from uvalu.runtime import theme_colors


def restore_token_from_query() -> None:
    """Restore a JWT passed via the ``_tok`` query param (legacy / deep-links)."""
    _tok_param = st.query_params.get("_tok", "")
    if not _tok_param:
        return
    if not st.session_state.get("jwt_token"):
        _email_check, _role_check = verify_token(_tok_param)
        if _email_check:
            st.session_state["jwt_token"]  = _tok_param
            st.session_state["user_email"] = _email_check
            st.session_state["user_role"]  = _role_check
        else:
            # Token invalid or expired — purge from localStorage to break any redirect loop
            st.iframe("<script>localStorage.removeItem('uv_jwt');</script>", height=1)
    del st.query_params["_tok"]


def recover_session_from_localstorage() -> None:
    """If there's no active session, redirect with the localStorage JWT as ``_tok``."""
    if st.session_state.get("jwt_token"):
        return
    st.iframe("""
<script>
(function(){
  var tok = localStorage.getItem('uv_jwt');
  if (!tok) return;
  var url = new URL(window.parent.location.href);
  if (url.searchParams.get('_tok')) return;
  url.searchParams.set('_tok', tok);
  window.parent.location.replace(url.toString());
})();
</script>
""", height=1)


def handle_logout() -> None:
    """Clear session + query params when ``?logout=1`` is present."""
    if st.query_params.get("logout") == "1":
        st.query_params.clear()
        for _k in ("jwt_token", "user_email", "user_role"):
            st.session_state.pop(_k, None)
        st.rerun()


def auth_wall() -> None:
    """Show the login form and halt execution if not authenticated."""
    # Fast path: token + email already verified this session — skip re-verification
    # on every rerun (e.g. timed auto-refresh) to prevent ghost login flashes.
    if st.session_state.get("jwt_token") and st.session_state.get("user_email"):
        return

    token = st.session_state.get("jwt_token")
    if token:
        email, role = verify_token(token)
        if email:
            st.session_state["user_email"] = email
            st.session_state["user_role"]  = role
            return  # already logged in

    # Login runs before shell.render_topbar() ever gets a chance to set
    # data-theme on <html>, so without this the page's --panel/--navy tokens
    # would stay pinned to their dark defaults regardless of the user's
    # actual light/dark preference (unlike every authenticated page).
    shell.apply_theme_script(theme_colors().effective_light)

    with st.container(key="uv_login", horizontal=True, gap=None):
        with st.container(key="uv_login_left"):
            st.markdown("""
            <div style="display:flex;align-items:baseline;gap:9px;position:relative;z-index:2;">
              <span style="font-size:24px;font-weight:500;letter-spacing:-0.03em;color:#F5F7FA;">uval<span style="color:var(--mint)">u</span></span>
              <span style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:rgba(245,247,250,0.4);">value engine</span>
            </div>
            <div style="position:relative;z-index:2;">
              <div class="uv-login-headline">Find value before the market does.</div>
              <div class="uv-login-copy">A six-model fair-value engine across 6 European exchanges —
                margin of safety, conviction scoring and hard-veto discipline in one workspace.</div>
              <div class="uv-login-stats">
                <div><div class="uv-login-stat-val">6</div><div class="uv-login-stat-lbl">valuation models</div></div>
                <div><div class="uv-login-stat-val">6</div><div class="uv-login-stat-lbl">EU exchanges</div></div>
                <div><div class="uv-login-stat-val">24/7</div><div class="uv-login-stat-lbl">signal monitoring</div></div>
              </div>
            </div>
            <div class="uv-login-foot">© 2026 Uvalu · Not investment advice.</div>
            <div class="uv-login-ring" style="right:-120px;bottom:-120px;width:420px;height:420px;"></div>
            <div class="uv-login-ring" style="right:-40px;bottom:-40px;width:260px;height:260px;"></div>
            """, unsafe_allow_html=True)

        with st.container(key="uv_login_right"):
            st.markdown(
                '<div class="uv-login-heading">Sign in</div>'
                '<div class="uv-login-subhead">Welcome back. Enter your credentials to continue.</div>',
                unsafe_allow_html=True,
            )
            with st.form("login_form", border=False):
                email    = st.text_input("Email", placeholder="you@company.com", icon=":material/mail:")
                password = st.text_input("Password", type="password", placeholder="••••••••",
                                         icon=":material/lock:")
                _submitted = st.form_submit_button("Sign in", width="stretch", type="primary")
            if _submitted:
                ok, result = login(email, password)
                if ok:
                    _, role = verify_token(result)
                    _login_email = email.strip().lower()
                    st.session_state["jwt_token"]  = result
                    st.session_state["user_email"] = _login_email
                    st.session_state["user_role"]  = role
                    st.iframe(f"<script>localStorage.setItem('uv_jwt',{repr(result)});</script>", height=1)
                    st.rerun()
                else:
                    st.markdown(f'<div class="uv-login-err">{result}</div>', unsafe_allow_html=True)

    st.stop()
