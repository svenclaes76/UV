"""Authentication gate: JWT/cookie bridges, logout, and the login wall.

These run at module scope in the app's boot sequence. Each step is a function so
``app.py`` can invoke them in order while keeping the logic out of its body.
"""
import html
from datetime import datetime, timedelta, timezone

import streamlit as st

from auth import (TOTP_REQUIRED, accept_invite_with_oauth, accept_invite_with_password,
                  backup_codes_remaining, complete_backup_code_login, complete_password_reset,
                  complete_totp_login, find_pending_invite_by_email, get_lockout,
                  get_pending_invite, get_pending_reset, get_user_status,
                  is_session_active, login, no_users_exist, oauth_login, register,
                  trust_this_device, verify_token)
from settings import load_shared_settings
from uvalu import locale_ui, logkit, oauth, shell
from uvalu.i18n import N_, _, h_, tr
from uvalu.runtime import theme_colors
from uvalu.shell import _display_name, _password_strength

# A TOTP/backup-code challenge is a short-lived marker in st.session_state
# only (never written to the uv_jwt cookie) — a reload drops back to the
# password step instead of leaving a half-authenticated session hanging
# around, per the impact doc's own recommendation.
_TOTP_PENDING_TTL_MIN = 5

# Marked with N_() and translated at the use site with h_(): their
# apostrophes don't fit inside the single-quoted f-strings that show them.
_FIRST_ADMIN_TEXT = N_("No accounts exist yet. This account gets full Admin access — you can invite everyone else once you're signed in.")
_PW_MISMATCH_TEXT = N_("New password and confirmation don't match.")


def recover_session_from_cookie() -> None:
    """If there's no active session, restore one from the ``uv_jwt`` cookie
    (set by app.py's JWT-sync script on every authenticated render) — read
    directly server-side via st.context.cookies, so it survives a full page
    reload (e.g. the top bar's theme toggle, uvalu/shell.py) without any
    client-side redirect. An earlier version of this used a JS-only
    localStorage-plus-``?_tok=``-redirect dance instead; that redirect is
    real cross-frame top-level navigation, which Streamlit's st.iframe()
    sandboxes without the `allow-top-navigation` flag — it silently never
    fired, so every hard reload dropped the session back to the login
    screen. Cookies are just sent with the next request/reconnect, no
    navigation required, so this sidesteps that sandbox restriction
    entirely instead of working around it."""
    if st.session_state.get("jwt_token"):
        return
    tok = st.context.cookies.get("uv_jwt")
    if not tok:
        return
    email, role, sid = verify_token(tok)
    if email and is_session_active(email, sid):
        st.session_state["jwt_token"]  = tok
        st.session_state["user_email"] = email
        st.session_state["user_role"]  = role
        st.session_state["jwt_sid"]    = sid
        logkit.auth_event("session.restored", outcome="ok", user_id=logkit.user_hash(email))


def handle_logout() -> None:
    """Clear session + query params when ``?logout=1`` is present."""
    if st.query_params.get("logout") == "1":
        st.query_params.clear()
        _who = logkit.user_hash(st.session_state.get("user_email"))
        for _k in ("jwt_token", "user_email", "user_role", "jwt_sid",
                  "uv_oauth_handled", "uv_oauth_refused"):
            st.session_state.pop(_k, None)
        logkit.auth_event("logout", outcome="ok", user_id=_who)
        # Expire the uv_jwt cookie/localStorage entry, THEN reload, both
        # inside the same script so the clearing genuinely finishes first.
        # An earlier version called st.rerun() right after queuing this
        # iframe — st.rerun() halts the script and starts a new run
        # immediately, and that new run doesn't re-emit this iframe (query
        # params are already cleared), so the browser could tear the
        # iframe down before its clearing script ever got to execute.
        # Cookie/localStorage silently survived, and recover_session_from_
        # cookie() logged the user straight back in on their next reload.
        st.iframe("""
<script>
(function(){
  try {
    document.cookie = 'uv_jwt=; path=/; max-age=0';
    localStorage.removeItem('uv_jwt');
  } catch(e) {}
  window.parent.location.reload();
})();
</script>
""", height=1)
        st.stop()


def _user_agent() -> str:
    return st.context.headers.get("User-Agent", "") if st.context.headers else ""


def _sync_cookie_script(token: str) -> None:
    """Same localStorage+cookie sync every successful sign-in path needs
    (password, invite acceptance, OAuth) — see app.py's own copy of this for
    every already-authenticated render."""
    st.iframe(
        f"<script>localStorage.setItem('uv_jwt',{repr(token)});"
        f"document.cookie='uv_jwt='+encodeURIComponent({repr(token)})+"
        f"'; path=/; max-age=86400';</script>",
        height=1,
    )


def _device_id_from_cookie() -> str | None:
    return st.context.cookies.get("uv_td") if st.context.cookies else None


def _sync_trusted_device_cookie(device_id: str) -> None:
    """Persist a "remember this device" grant client-side — a separate,
    longer-lived cookie from the session cookie (uv_jwt) so it survives a
    sign-out and is available the next time this browser hits the TOTP
    challenge."""
    st.iframe(
        f"<script>document.cookie='uv_td='+encodeURIComponent({repr(device_id)})+"
        f"'; path=/; max-age={30 * 86400}';</script>",
        height=1,
    )


def _render_totp_challenge(pending: dict) -> None:
    st.markdown(
        f'<div class="uv-login-heading">{h_("Enter your authenticator code")}</div>'
        f'<div class="uv-login-subhead">{h_("Open your authenticator app and enter the 6-digit code for Uvalu.")}</div>',
        unsafe_allow_html=True,
    )
    with st.form("totp_challenge_form", border=False):
        code = st.text_input(_("Code"), placeholder="000000", icon=":material/pin:")
        remember = st.toggle(_("Remember this device for 30 days"), key="totp_remember_device")
        submitted = st.form_submit_button(_("Verify"), width="stretch", type="primary")
    if submitted:
        ok, result = complete_totp_login(pending["email"], code, user_agent=_user_agent())
        if ok:
            st.session_state.pop("uv_totp_pending", None)
            _start_session(result)
            if remember:
                device_id = trust_this_device(pending["email"])
                _sync_trusted_device_cookie(device_id)
            st.rerun()
        else:
            st.markdown(f'<div class="uv-login-err">{result}</div>', unsafe_allow_html=True)

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button(_("Use a backup code"), key="totp_use_backup", width="stretch"):
            st.session_state["uv_totp_pending"]["mode"] = "backup"
            st.rerun()
    with _b2:
        if st.button(_("Cancel"), key="totp_cancel", width="stretch"):
            st.session_state.pop("uv_totp_pending", None)
            st.rerun()


def _render_backup_code_challenge(pending: dict) -> None:
    st.markdown(
        f'<div class="uv-login-heading">{h_("Enter a backup code")}</div>'
        f'<div class="uv-login-subhead">{h_("Use one of the one-time backup codes you saved when you set up two-factor authentication.")}</div>',
        unsafe_allow_html=True,
    )
    if backup_codes_remaining(pending["email"]) == 0:
        st.markdown(
            '<div style="background:var(--panel-2);border:0.5px solid var(--line);border-radius:10px;'
            'padding:14px 16px;margin-top:12px;font-size:12.5px;color:var(--muted);line-height:1.6;">'
            f'{h_("No backup codes left on this account. Ask an admin to reset your two-factor authentication so you can re-enroll.")}</div>',
            unsafe_allow_html=True,
        )
        if st.button(_("Cancel"), key="backup_dead_end_cancel", width="stretch"):
            st.session_state.pop("uv_totp_pending", None)
            st.rerun()
        return

    with st.form("backup_code_challenge_form", border=False):
        code = st.text_input(_("Backup code"), placeholder="xxxx-xxxx", icon=":material/key:")
        submitted = st.form_submit_button(_("Verify"), width="stretch", type="primary")
    if submitted:
        ok, result = complete_backup_code_login(pending["email"], code, user_agent=_user_agent())
        if ok:
            st.session_state.pop("uv_totp_pending", None)
            _start_session(result)
            st.rerun()
        else:
            st.markdown(f'<div class="uv-login-err">{result}</div>', unsafe_allow_html=True)

    if st.button(_("Back to the authenticator code"), key="backup_back_to_totp", width="stretch"):
        st.session_state["uv_totp_pending"]["mode"] = "totp"
        st.rerun()


def _render_strength_caption(password: str) -> None:
    """Advisory-only, shown after a failed submit on invite-accept/password-
    reset — the same tiny indicator uvalu/pages_/settings.py's Change/Set-
    password dialogs show live while typing (uvalu.shell._password_strength);
    not duplicated here as a live check because both screens wrap their
    password field in st.form, which only reruns on submit, so "live" isn't
    available without restructuring either screen for a one-time, low-
    frequency flow — see the Sep 13 password-strength-indicator commit. This
    still closes most of the gap against Uvalu Auth.dc.html frames 05/07
    (both themselves static screenshots, not live either): the strength read-
    out is visible after the one submit a real user actually makes here,
    instead of never appearing on these two screens at all."""
    label, tone = _password_strength(password)
    if not label:
        return
    st.markdown(f'<div style="font-size:12px;margin-top:8px;color:var(--{tone}-txt);">'
               f'{h_("Password strength: {strength}", strength=label)}</div>', unsafe_allow_html=True)


def _start_session(token: str) -> None:
    email, role, sid = verify_token(token)
    st.session_state["jwt_token"]  = token
    st.session_state["user_email"] = email
    st.session_state["user_role"]  = role
    st.session_state["jwt_sid"]    = sid
    _sync_cookie_script(token)


def _render_brand_panel() -> None:
    st.markdown(f"""
    <div style="display:flex;align-items:baseline;gap:9px;position:relative;z-index:2;">
      <span style="font-size:24px;font-weight:500;letter-spacing:-0.03em;color:#F5F7FA;">uval<span style="color:var(--mint)">u</span></span>
      <span style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:rgba(245,247,250,0.4);">{h_("value engine")}</span>
    </div>
    <div style="position:relative;z-index:2;">
      <div class="uv-login-headline">{h_("Find value before the market does.")}</div>
      <div class="uv-login-copy">{h_("A six-model fair-value engine across 6 European exchanges — margin of safety, conviction scoring and hard-veto discipline in one workspace.")}</div>
      <div class="uv-login-stats">
        <div><div class="uv-login-stat-val">6</div><div class="uv-login-stat-lbl">{h_("valuation models")}</div></div>
        <div><div class="uv-login-stat-val">6</div><div class="uv-login-stat-lbl">{h_("EU exchanges")}</div></div>
        <div><div class="uv-login-stat-val">24/7</div><div class="uv-login-stat-lbl">{h_("signal monitoring")}</div></div>
      </div>
    </div>
    <div class="uv-login-foot">{h_("© 2026 Uvalu · Not investment advice.")}</div>
    <div class="uv-login-ring" style="right:-120px;bottom:-120px;width:420px;height:420px;"></div>
    <div class="uv-login-ring" style="right:-40px;bottom:-40px;width:260px;height:260px;"></div>
    """, unsafe_allow_html=True)


def _render_provider_buttons(key_prefix: str) -> None:
    """One button per entry in oauth.configured_providers() — Google ships in
    phase 1, Microsoft is drawn as the unconfigured second entry so a later
    addition changes data (secrets.toml + uvalu/oauth.py's PROVIDERS tuple),
    not this layout (Uvalu Auth.dc.html frame 01's whole point).

    An unconfigured provider is inert markdown, not a disabled st.button —
    matches frame 01's own dashed-border + "NOT CONFIGURED" badge treatment
    (the same convention Settings' Passkeys row already uses for its own
    "not built yet" state), and sidesteps a real bug a plain disabled button
    had: Streamlit's disabled-button border follows the REAL native theme
    (confirmed live: `rgb(34,51,78)`, `[theme.dark].borderColor`) rather than
    this app's `var(--line)`, the same "native chrome leaks through" class of
    bug already fixed twice elsewhere (Admin's search/select boxes).

    Wrapped in its own keyed container so styles.py can pin the gap between
    entries to the design's 10px (Uvalu Auth.dc.html frame 01's `gap:10px`
    flex column) instead of Streamlit's larger default inter-element
    spacing, which read as no deliberate separation between the two
    buttons."""
    with st.container(key=f"{key_prefix}_list"):
        for _p in oauth.configured_providers():
            if _p["configured"]:
                if st.button(_("Continue with {provider}", provider=_p["label"]), key=f"{key_prefix}_{_p['id']}", width="stretch"):
                    oauth.start_login(_p["id"])
            else:
                st.markdown(
                    f'<div style="display:flex;align-items:center;justify-content:center;gap:8px;'
                    f'width:100%;box-sizing:border-box;padding:11px;border-radius:9px;font-size:13px;'
                    f'border:0.5px dashed var(--line);color:var(--faint);">{h_("Continue with {provider}", provider=_p["label"])}'
                    f'<span style="font-size:9.5px;letter-spacing:0.04em;padding:2px 6px;border-radius:4px;'
                    f'background:var(--line-2);color:var(--faint);">{h_("NOT CONFIGURED")}</span></div>',
                    unsafe_allow_html=True,
                )


def _render_oauth_refused(info: dict) -> None:
    if info.get("reason") == "suspended":
        _heading = h_("This account has been suspended")
        _body = h_("Sign-in via {provider} succeeded, but the Uvalu account for it is suspended.",
                   provider=info["label"])
    else:
        _heading = h_("No Uvalu account for this {provider} identity", provider=info["label"])
        _body = h_("Uvalu is invite-only. {email} is not a member of this workspace, so no account was created.",
                   email=f"<span style=\"font-family:var(--uv-mono);font-size:12.5px;"
                         f"color:var(--text);\">{info['email']}</span>")
    st.markdown(
        f'<div class="uv-login-heading">{_heading}</div>'
        f'<div class="uv-login-subhead">{_body}</div>'
        '<div style="background:var(--panel-2);border:0.5px solid var(--line);border-radius:10px;'
        'padding:14px 16px;margin-top:18px;font-size:12.5px;color:var(--muted);line-height:1.6;">'
        f'{h_("If you were invited on a different address, sign in with that one — or ask an admin to invite this address.")}</div>',
        unsafe_allow_html=True,
    )
    if st.button(_("Back to sign in"), key="oauth_refused_back", width="stretch"):
        oauth.sign_out()
        st.session_state.pop("uv_oauth_refused", None)
        st.session_state.pop("uv_oauth_handled", None)
        st.rerun()


def _render_invite_acceptance(token: str) -> None:
    invite = get_pending_invite(token)
    shell.apply_theme_script(theme_colors().effective_light)
    with st.container(key="uv_login", horizontal=True, gap=None):
        with st.container(key="uv_login_left"):
            _render_brand_panel()
        with st.container(key="uv_login_right"):
            locale_ui.render_login_switcher()
            if not invite:
                st.markdown(
                    f'<div class="uv-login-heading">{h_("Invite link invalid")}</div>'
                    f'<div class="uv-login-subhead">{h_("This invite link is invalid or has expired. Ask your admin to send a new one.")}</div>',
                    unsafe_allow_html=True,
                )
                return

            _inviter = _display_name(invite["invited_by"]) if invite["invited_by"] else _("an admin")
            _invited = h_("Invited by {inviter} as {role}. Pick a password, or use a connected provider — you can add another method later.",
                          inviter=_inviter, role=f'<span style="color:var(--text);">{tr(invite["role"])}</span>')
            st.markdown(
                f'<div class="uv-login-heading">{h_("Create your account")}</div>'
                f'<div class="uv-login-subhead">{_invited}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div style="margin-top:22px;">'
                '<div style="font-size:11px;letter-spacing:0.05em;text-transform:uppercase;'
                f'color:var(--faint);margin-bottom:8px;">{h_("Email")}</div>'
                '<div style="background:var(--panel-2);border:0.5px solid var(--line-2);border-radius:9px;'
                'padding:11px 13px;font-size:14px;color:var(--muted);display:flex;align-items:center;'
                'justify-content:space-between;">'
                f'<span style="font-family:var(--uv-mono);font-size:13px;">{invite["email"]}</span>'
                '<span style="font-size:10px;letter-spacing:0.04em;padding:2px 7px;border-radius:4px;'
                f'background:var(--line-2);color:var(--faint);">{h_("FIXED BY INVITE")}</span></div></div>',
                unsafe_allow_html=True,
            )
            _min_len = int(load_shared_settings().get("min_password_length", 12))
            with st.form("invite_accept_form", border=False):
                password = st.text_input(_("Password"), type="password", placeholder="••••••••",
                                         icon=":material/lock:",
                                         help=_("At least {min_len} characters.", min_len=_min_len))
                submitted = st.form_submit_button(_("Create account"), width="stretch", type="primary")
            if submitted:
                ok, result = accept_invite_with_password(token, password, user_agent=_user_agent())
                if ok:
                    st.query_params.clear()
                    _start_session(result)
                    st.rerun()
                else:
                    st.markdown(f'<div class="uv-login-err">{result}</div>', unsafe_allow_html=True)
                    _render_strength_caption(password)

            st.markdown(
                '<div style="display:flex;align-items:center;gap:12px;margin:22px 0;">'
                '<div style="flex:1;height:0.5px;background:var(--line);"></div>'
                f'<span style="font-size:11px;color:var(--faint);">{h_("or")}</span>'
                '<div style="flex:1;height:0.5px;background:var(--line);"></div></div>',
                unsafe_allow_html=True,
            )
            # Deliberately just starts st.login() — doesn't try to complete
            # accept_invite_with_oauth() here even if oauth.current_identity()
            # already has one, because st.login()'s redirect lands back on the
            # app's home page, not this one, dropping ?invite=<token> from the
            # URL. auth_wall()'s own post-redirect handling (find_pending_
            # invite_by_email) finishes the acceptance once the user is back
            # there instead — see that function's docstring.
            _render_provider_buttons("invite_accept_provider")


def _render_first_admin_setup() -> None:
    """Shown instead of the normal sign-in form when the user store is
    completely empty (auth.no_users_exist()) — otherwise a fresh install
    with no ADMIN_EMAIL/ADMIN_PASSWORD env vars (auth.bootstrap_admin_from_
    env(), run once at app boot) has no way to create an account at all,
    since the sign-in wall is invite-only and there's no admin yet to send
    an invite. register() already promotes the first-ever account to Admin
    (auth.py) — this only collects email + password and calls it directly.
    Password-only: oauth_login() requires an existing invited account, so
    provider-based first-admin creation isn't offered here."""
    shell.apply_theme_script(theme_colors().effective_light)
    with st.container(key="uv_login", horizontal=True, gap=None):
        with st.container(key="uv_login_left"):
            _render_brand_panel()
        with st.container(key="uv_login_right"):
            locale_ui.render_login_switcher()
            st.markdown(
                f'<div class="uv-login-heading">{h_("Create the first admin account")}</div>'
                f'<div class="uv-login-subhead">{h_(_FIRST_ADMIN_TEXT)}</div>',
                unsafe_allow_html=True,
            )
            _min_len = int(load_shared_settings().get("min_password_length", 12))
            with st.form("first_admin_setup_form", border=False):
                email = st.text_input(_("Email"), placeholder=_("you@company.com"), icon=":material/mail:")
                password = st.text_input(_("Password"), type="password", placeholder="••••••••",
                                         icon=":material/lock:",
                                         help=_("At least {min_len} characters.", min_len=_min_len))
                submitted = st.form_submit_button(_("Create admin account"), width="stretch", type="primary")
            if submitted:
                ok, result = register(email, password)
                if not ok:
                    st.markdown(f'<div class="uv-login-err">{result}</div>', unsafe_allow_html=True)
                    _render_strength_caption(password)
                else:
                    # The store is no longer empty either way once register()
                    # succeeds, so on the unlikely chance login() itself fails
                    # right after, falling through to a rerun just lands on the
                    # normal sign-in form instead of getting stuck here.
                    _ok2, _result2 = login(email, password, user_agent=_user_agent())
                    if _ok2:
                        _start_session(_result2)
                    st.rerun()


def _render_forgot_password() -> None:
    """There's no self-service password reset — no outbound email exists, so
    the plan's own resolution for this open question is "ask an admin", who
    generates a one-time link via the Admin portal's "Send password reset"
    action (uvalu/pages_/admin.py) and relays it manually, same as an
    invite link."""
    shell.apply_theme_script(theme_colors().effective_light)
    with st.container(key="uv_login", horizontal=True, gap=None):
        with st.container(key="uv_login_left"):
            _render_brand_panel()
        with st.container(key="uv_login_right"):
            locale_ui.render_login_switcher()
            st.markdown(
                f'<div class="uv-login-heading">{h_("Forgot your password?")}</div>'
                f'<div class="uv-login-subhead">{h_("Uvalu has no automated password reset — ask an admin to send you a one-time reset link from the Admin portal.")}</div>',
                unsafe_allow_html=True,
            )
            if st.button(_("Back to sign in"), key="forgot_back", width="stretch"):
                st.query_params.clear()
                st.rerun()


def _render_password_reset(token: str) -> None:
    pending = get_pending_reset(token)
    shell.apply_theme_script(theme_colors().effective_light)
    with st.container(key="uv_login", horizontal=True, gap=None):
        with st.container(key="uv_login_left"):
            _render_brand_panel()
        with st.container(key="uv_login_right"):
            locale_ui.render_login_switcher()
            if not pending:
                st.markdown(
                    f'<div class="uv-login-heading">{h_("Reset link invalid")}</div>'
                    f'<div class="uv-login-subhead">{h_("This reset link is invalid or has expired. Ask your admin to send a new one.")}</div>',
                    unsafe_allow_html=True,
                )
                return

            _resetting = h_("Resetting the password for {email}",
                            email=f'<span style="color:var(--text);">{pending["email"]}</span>')
            st.markdown(
                f'<div class="uv-login-heading">{h_("Choose a new password")}</div>'
                f'<div class="uv-login-subhead">{_resetting}.</div>',
                unsafe_allow_html=True,
            )
            _min_len = int(load_shared_settings().get("min_password_length", 12))
            with st.form("password_reset_form", border=False):
                password = st.text_input(_("New password"), type="password", placeholder="••••••••",
                                         icon=":material/lock:",
                                         help=_("At least {min_len} characters.", min_len=_min_len))
                confirm = st.text_input(_("Confirm new password"), type="password", placeholder="••••••••",
                                        icon=":material/lock:")
                submitted = st.form_submit_button(_("Reset password"), width="stretch", type="primary")
            if submitted:
                if password != confirm:
                    st.markdown(f'<div class="uv-login-err">{h_(_PW_MISMATCH_TEXT)}</div>',
                               unsafe_allow_html=True)
                    _render_strength_caption(password)
                else:
                    ok, result = complete_password_reset(token, password, user_agent=_user_agent())
                    if ok:
                        st.query_params.clear()
                        _start_session(result)
                        st.rerun()
                    else:
                        st.markdown(f'<div class="uv-login-err">{result}</div>', unsafe_allow_html=True)
                        _render_strength_caption(password)


def auth_wall() -> None:
    """Show the login form and halt execution if not authenticated."""
    # Invite links (?invite=<token>) render their own screen regardless of any
    # existing session — an explicit click on a specific link is unambiguous
    # intent, checked before anything else the same way handle_logout()'s own
    # query param is (both in app.py's boot sequence, this one called first).
    if st.query_params.get("invite"):
        _render_invite_acceptance(st.query_params["invite"])
        st.stop()
    if st.query_params.get("reset"):
        _render_password_reset(st.query_params["reset"])
        st.stop()
    if st.query_params.get("forgot"):
        _render_forgot_password()
        st.stop()

    # A genuinely empty user store has no session, invite or reset token that
    # could ever be valid anyway — checked once per rerun (cheap: the same
    # small local file read every other check here already does), so this
    # naturally stops showing itself the moment bootstrap_admin_from_env() or
    # this very screen creates the first account.
    if no_users_exist():
        _render_first_admin_setup()
        st.stop()

    # Re-verified on every rerun, not cached — a session_state-only "already
    # verified this session" fast path used to skip this entirely once set,
    # which meant an Admin suspending/deleting a user, or changing their
    # role, had NO effect on that user's already-open tab until their JWT
    # happened to expire (up to 24h) — session_state persists for the life
    # of the browser connection, so in practice this could be indefinite.
    # verify_token() is a pure in-memory JWT decode (no I/O); is_session_active()
    # and get_user_status() each read the same small local user-store file —
    # none of the three is expensive enough to justify caching a
    # security-relevant check across reruns.
    token = st.session_state.get("jwt_token")
    _revoked_msg = None
    if token:
        email, _role, sid = verify_token(token)
        if email and not is_session_active(email, sid):
            _revoked_msg = _("You were signed out of this session.")
            logkit.auth_event("session.revoked", outcome="revoked", reason="session_signed_out",
                              user_id=logkit.user_hash(email))
        elif email:
            _status = get_user_status(email)
            if _status is None:
                _revoked_msg = _("Your account no longer exists. Please contact your admin.")
                logkit.auth_event("session.revoked", outcome="revoked", reason="account_deleted",
                                  user_id=logkit.user_hash(email))
            elif _status[1] == "Suspended":
                _revoked_msg = _("This account has been suspended.")
                logkit.auth_event("session.revoked", outcome="revoked", reason="suspended",
                                  user_id=logkit.user_hash(email))
            else:
                st.session_state["user_email"] = email
                st.session_state["user_role"]  = _status[0]
                st.session_state["jwt_sid"]    = sid
                return  # still a valid, active session
        else:
            logkit.auth_event("session.revoked", outcome="revoked", reason="invalid_token")
        for _k in ("jwt_token", "user_email", "user_role", "jwt_sid"):
            st.session_state.pop(_k, None)

    # Resolve a completed native Streamlit OIDC login (st.login()/st.user,
    # uvalu/oauth.py) into a uvalu session — guarded by uv_oauth_handled so
    # this runs once per browser OIDC session rather than on every rerun
    # after (st.user stays populated for the life of that identity cookie).
    if not st.session_state.get("uv_oauth_handled"):
        _identity = oauth.current_identity()
        if _identity:
            st.session_state["uv_oauth_handled"] = True
            _ok, _result = oauth_login(_identity["issuer"], _identity["subject"], _identity["email"],
                                       user_agent=_user_agent())
            if not _ok and _result == "not_invited":
                # A pending invite's token doesn't survive st.login()'s
                # redirect (it always lands back on the app's home page, not
                # wherever ?invite=<token> was) — fall back to looking one up
                # by the identity's own email instead.
                _pending = find_pending_invite_by_email(_identity["email"])
                if _pending:
                    _ok, _result = accept_invite_with_oauth(
                        _pending["token"], _identity["issuer"], _identity["subject"],
                        _identity["email"], user_agent=_user_agent())
            if _ok:
                _start_session(_result)
                st.rerun()
            else:
                st.session_state["uv_oauth_refused"] = {
                    "email": _identity["email"], "label": _identity["label"], "reason": _result}

    # Login runs before shell.render_topbar() ever gets a chance to set
    # data-theme on <html>, so without this the page's --panel/--navy tokens
    # would stay pinned to their dark defaults regardless of the user's
    # actual light/dark preference (unlike every authenticated page).
    shell.apply_theme_script(theme_colors().effective_light)

    with st.container(key="uv_login", horizontal=True, gap=None):
        with st.container(key="uv_login_left"):
            _render_brand_panel()

        with st.container(key="uv_login_right"):
            locale_ui.render_login_switcher()
            if st.session_state.get("uv_oauth_refused"):
                _render_oauth_refused(st.session_state["uv_oauth_refused"])
                st.stop()

            _pending_totp = st.session_state.get("uv_totp_pending")
            if _pending_totp:
                if datetime.now(timezone.utc) > datetime.fromisoformat(_pending_totp["expires"]):
                    st.session_state.pop("uv_totp_pending", None)
                elif _pending_totp.get("mode") == "backup":
                    _render_backup_code_challenge(_pending_totp)
                    st.stop()
                else:
                    _render_totp_challenge(_pending_totp)
                    st.stop()

            _attempted_email = st.session_state.get("uv_login_attempted_email")
            _lock_expiry = get_lockout(_attempted_email) if _attempted_email else None

            if _lock_expiry:
                _mins_left = max(1, -(-int((_lock_expiry - datetime.now(timezone.utc)).total_seconds()) // 60))
                st.markdown(
                    f'<div class="uv-login-heading">{h_("Sign in temporarily locked")}</div>'
                    f'<div class="uv-login-subhead">{h_("Too many failed attempts on this account. Uvalu will accept a new attempt when the timer expires.")}</div>'
                    '<div class="uv-lock-card">'
                      '<div class="uv-lock-icon">'
                        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
                        '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 3"></path></svg></div>'
                     f'<div><div class="uv-lock-timer">{h_("{minutes} min", minutes=_mins_left)}</div>'
                     f'<div class="uv-lock-caption">{h_("until the next attempt")}</div></div>'
                    '</div>'
                    f'<div class="uv-login-btn-disabled">{h_("Sign in")}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div style="display:flex;align-items:center;gap:12px;margin:18px 0;">'
                    '<div style="flex:1;height:0.5px;background:var(--line);"></div>'
                    f'<span style="font-size:11px;color:var(--faint);">{h_("or")}</span>'
                    '<div style="flex:1;height:0.5px;background:var(--line);"></div></div>',
                    unsafe_allow_html=True,
                )
                _render_provider_buttons("login_locked_provider")
                st.markdown(
                    '<div style="font-size:11.5px;color:var(--faint);margin-top:12px;text-align:center;'
                    f'line-height:1.5;">{h_("The lock applies to password sign-in only. Providers are unaffected.")}</div>',
                    unsafe_allow_html=True,
                )
                if st.button(_("Not you? Use a different account"), key="login_switch_account",
                             width="stretch"):
                    st.session_state.pop("uv_login_attempted_email", None)
                    st.rerun()
                st.stop()

            st.markdown(
                f'<div class="uv-login-heading">{h_("Sign in")}</div>'
                f'<div class="uv-login-subhead">{h_("Welcome back. Enter your credentials to continue.")}</div>',
                unsafe_allow_html=True,
            )
            if _revoked_msg:
                st.markdown(f'<div class="uv-login-err">{_revoked_msg}</div>', unsafe_allow_html=True)
            with st.form("login_form", border=False):
                email = st.text_input(_("Email"), placeholder=_("you@company.com"), icon=":material/mail:")
                # Custom label row (native label hidden below) so "Forgot?" can sit
                # inline with "Password" — matches Uvalu.dc.html's layout. It's
                # plain styled text, not a link: this app has no password-reset
                # flow to send it to, and a dead click would be worse than an
                # honestly-inert label.
                st.markdown(
                    '<div style="display:flex;align-items:baseline;justify-content:space-between;'
                    'margin-top:4px;">'
                    '<span style="font-size:11px;letter-spacing:0.05em;text-transform:uppercase;'
                    f'color:var(--faint);">{h_("Password")}</span>'
                    '<a href="?forgot=1" target="_self" style="font-size:11.5px;color:var(--teal);'
                    f'text-decoration:none;">{h_("Forgot?")}</a></div>',
                    unsafe_allow_html=True,
                )
                password = st.text_input(_("Password"), type="password", placeholder="••••••••",
                                         icon=":material/lock:", label_visibility="collapsed")
                _submitted = st.form_submit_button(_("Sign in"), width="stretch", type="primary")
            if _submitted:
                if not email.strip() or not password.strip():
                    st.markdown(f'<div class="uv-login-err">{h_("Enter your email and password to continue.")}</div>',
                               unsafe_allow_html=True)
                else:
                    ok, result = login(email, password, user_agent=_user_agent(),
                                       device_id=_device_id_from_cookie())
                    if ok and result == TOTP_REQUIRED:
                        st.session_state.pop("uv_login_attempted_email", None)
                        st.session_state["uv_totp_pending"] = {
                            "email": email.strip().lower(), "mode": "totp",
                            "expires": (datetime.now(timezone.utc)
                                       + timedelta(minutes=_TOTP_PENDING_TTL_MIN)).isoformat(),
                        }
                        st.rerun()
                    elif ok:
                        st.session_state.pop("uv_login_attempted_email", None)
                        _start_session(result)
                        st.rerun()
                    else:
                        st.session_state["uv_login_attempted_email"] = email.strip().lower()
                        if get_lockout(email):
                            # This attempt is the one that tripped the lock (or the
                            # account was already locked) — rerun so the top of this
                            # function renders the dedicated locked-out card above
                            # instead of the plain inline error.
                            st.rerun()
                        st.markdown(f'<div class="uv-login-err">{result}</div>', unsafe_allow_html=True)
                        # Highlights the password field itself alongside the error above,
                        # per Uvalu Auth.dc.html frame 02 — CSS application doesn't depend
                        # on DOM order, so this still reaches the password input even
                        # though that input was already emitted earlier in this same run
                        # (its value came back wrong, but Streamlit had already drawn it
                        # by the time login() returns). Scoped to this screen's own
                        # `uv_login_right` container — the only other place a "Password"-
                        # labeled field renders is invite-accept/reset, on a completely
                        # different, mutually-exclusive branch of auth_wall().
                        st.markdown(
                            '<style>.st-key-uv_login_right div[data-testid="stTextInput"]'
                            f':has(input[aria-label="{html.escape(_("Password"))}"]) > div '
                            '{ border-color: var(--down-txt) !important; }</style>',
                            unsafe_allow_html=True,
                        )

            st.markdown(
                '<div style="display:flex;align-items:center;gap:12px;margin:22px 0;">'
                '<div style="flex:1;height:0.5px;background:var(--line);"></div>'
                f'<span style="font-size:11px;color:var(--faint);">{h_("or")}</span>'
                '<div style="flex:1;height:0.5px;background:var(--line);"></div></div>',
                unsafe_allow_html=True,
            )
            _render_provider_buttons("login_provider")
            # No self-service request-access flow exists (accounts are created
            # via the Admin portal's Invite flow), so this is styled text, not
            # a dead link.
            st.markdown(
                '<div style="font-size:12.5px;color:var(--muted);margin-top:26px;text-align:center;">'
                f'{h_("New to Uvalu?")} <span style="color:var(--teal);">{h_("Ask your admin for an invite")}</span></div>',
                unsafe_allow_html=True,
            )

    st.stop()
