"""Admin portal — Users, Data feeds, Backups. A standalone page reached only
via the avatar dropdown (uvalu/shell.py) and rendering its own sidebar nav +
header (render()'s _admin_shell_css/_nav_col/_main_col) instead of the main
app's top-bar — app.py skips shell.render_topbar() for this page's url_path
so the two chromes never stack. Matches "Uvalu Admin.dc.html" (the claude.ai/
design project, fetched via the DesignSync MCP tool), reset 2026-07-23 to a
table-style layout (one bordered panel per section, hairline-divided rows)
instead of the previous per-row bordered cards.

The design's own palette (--bg:#0A1730 etc.) is byte-identical to this app's
existing dark-theme tokens (uvalu/styles.py's :root block) — Uvalu Admin.dc.html
has no [data-theme="light"] variant at all, so this page forces data-theme to
"dark" on load regardless of the user's own light/dark preference (same
"admin console ignores the toggle" call already made for the main nav rail in
[[uvalu-redesign-v2]]'s Phase 1). Without this, the page would inherit
whatever theme the user last had active elsewhere in the app, since it skips
shell.apply_theme_script() the way every other page calls it.

Design-vs-real-data conflicts resolved the same way as every other page reset
this branch (reuse real data, adopt only the visual chrome): kept the real
"Suspended" stat tile instead of the mockup's fictional seat-limit ("Seats
used 6/25" — this app has no subscription/plan concept); dropped the
mockup's "Plan" column for the same reason; kept the real "no live
health/latency monitoring" / "no scheduler, every backup is Manual" / "no
outbound email, share the temporary password yourself" captions instead of
the mockup's fabricated per-feed ms latency, "Scheduled" backup type, and
"they'll receive an email invite" copy. Admin-role only."""
import streamlit as st

from auth import (ROLES, admin_request_password_reset, admin_reset_totp, delete_user,
                  has_password, invite_user, list_linked_identities, list_users,
                  revoke_other_sessions, set_role, set_status, two_factor_status)
from backup import list_backups, create_backup, get_backup_bytes, restore_backup, export_env_key
from settings import load_shared_settings, save_shared_settings, ALL_EXCHANGES, EXCHANGE_LABELS
from uvalu import logkit, nav as nav_registry, oauth
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user
from uvalu.shell import _initials, _display_name, apply_theme_script, _close_stray_popover_script

_NAV_ITEMS = (
    ("users",    "Users",       ":material/group:"),
    ("security", "Security",    ":material/shield:"),
    ("feeds",    "Data feeds",  ":material/dns:"),
    ("backups",  "Backups",     ":material/backup:"),
)
_SECTION_TITLES = {"users": "User management", "security": "Security", "feeds": "Data feeds",
                   "backups": "Backups & restore"}

_2FA_STYLE = {
    "ON":       ("var(--up-bg)",    "var(--up-txt)"),
    "REQUIRED": ("var(--down-bg)",  "var(--down-txt)"),
    "OFF":      ("var(--line-2)",   "var(--faint)"),
    "PROVIDER": ("var(--line-2)",   "var(--faint)"),
    "—":        ("var(--line-2)",   "var(--faint)"),
}

_STATUS_STYLE = {
    "Active":    ("var(--up-bg)",    "var(--up-txt)"),
    "Invited":   ("var(--amber-bg)", "var(--amber-txt)"),
    "Suspended": ("var(--down-bg)",  "var(--down-txt)"),
}

# Real ticker suffix per exchange (matches uvalu/data.py's _fetch_map) — used
# only for an honest "what does this feed cover" description, never for a
# fabricated latency/health number (there's no real per-feed telemetry).
_EXCHANGE_SUFFIX = {
    "brussels": ".BR", "amsterdam": ".AS", "paris": ".PA",
    "milan": ".MI", "frankfurt": ".DE", "swiss": ".SW",
}


def _status_badge(status: str) -> str:
    bg, txt = _STATUS_STYLE.get(status, ("var(--line-2)", "var(--muted)"))
    return (f'<span style="display:inline-block;background:{bg};color:{txt};padding:3px 9px;'
           f'border-radius:5px;font-size:11px;font-weight:500;">{status}</span>')


_2FA_LABELS = {"ON": "ON", "OFF": "OFF", "PROVIDER": "Provider", "REQUIRED": "Required", "—": "—"}


def _2fa_badge(status: str) -> str:
    bg, txt = _2FA_STYLE.get(status, ("var(--line-2)", "var(--faint)"))
    return (f'<span style="display:inline-block;background:{bg};color:{txt};padding:3px 9px;'
           f'border-radius:5px;font-size:11px;font-weight:500;">{_2FA_LABELS.get(status, status)}</span>')


def _signin_methods_label(email: str) -> str:
    methods = ["Password"] if has_password(email) else []
    methods += [oauth.label_for_issuer(i["issuer"]) for i in list_linked_identities(email)]
    return " + ".join(methods) if methods else "—"


def _stat_tile(label: str, value) -> str:
    return (f'<div style="background:var(--panel);border:0.5px solid var(--line);border-radius:12px;'
           f'padding:16px 18px;">'
           f'<div style="font-size:11px;color:var(--faint);letter-spacing:0.04em;text-transform:uppercase;'
           f'line-height:1.3;">{label}</div>'
           f'<div style="font-size:22px;font-weight:500;margin-top:6px;font-family:var(--uv-mono);'
           f'color:var(--text);line-height:1.2;">{value}</div></div>')


@st.dialog("Invite user", width="large")
def _dlg_invite():
    st.caption("They'll need this link to set up their account — there's no outbound email, "
              "so share it with them yourself.")
    _email = st.text_input("Email", key="admin_invite_email", placeholder="name@company.com")
    _role = st.selectbox("Role", options=list(ROLES), index=list(ROLES).index("Analyst"),
                         key="admin_invite_role")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="admin_invite_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_invite = st.button("Send invite", key="admin_invite_submit", type="primary", width="stretch")

    if _do_invite:
        ok, msg, token = invite_user(_email, _role, invited_by=current_user().email)
        if ok:
            st.success(msg)
            st.code(f"{st.context.url}?invite={token}", language=None)
            st.caption("Invite link — shown once. Copy it now. Valid for 7 days.")
        else:
            st.error(msg)


@st.dialog("Restore workspace?", width="large")
def _dlg_restore(backup_id: str, created: str, email: str):
    _done = st.session_state.get("_admin_restore_done")
    if _done and _done.get("id") == backup_id:
        # A real "Restore complete" screen, not just a toast the rerun below
        # it used to fire immediately would blow past before anyone saw it —
        # matches Uvalu Admin.dc.html's dedicated done state (checkmark +
        # target snapshot + a single "Done" button, confirm form gone).
        st.markdown(f"""
<div style="text-align:center;padding:20px 0 8px;">
  <div style="width:44px;height:44px;border-radius:12px;background:var(--soft);color:var(--mint);
             display:flex;align-items:center;justify-content:center;margin:0 auto 14px;">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5l10 -10"/></svg>
  </div>
  <div style="font-size:16px;font-weight:500;color:var(--text);">Restore complete</div>
  <div style="font-size:12.5px;color:var(--muted);margin-top:6px;">The workspace has been restored to the
    "{_done['created']}" snapshot.</div>
</div>""", unsafe_allow_html=True)
        if st.button("Done", key="admin_restore_done_btn", type="primary", width="stretch"):
            st.session_state.pop("_admin_restore_done", None)
            st.rerun()
        return

    st.warning("This replaces all current portfolio data and settings with this snapshot. "
              "This cannot be undone.", icon=":material/warning:")
    st.markdown(f'<div style="background:var(--panel-2);border:0.5px solid var(--line);border-radius:8px;'
               f'padding:12px 14px;margin-top:10px;">'
               f'<div style="font-size:13px;font-weight:500;color:var(--text);">Manual snapshot</div>'
               f'<div style="font-size:11.5px;color:var(--faint);font-family:var(--uv-mono);margin-top:2px;">'
               f'{created}</div></div>', unsafe_allow_html=True)
    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="admin_restore_cancel", width="stretch"):
            st.rerun()
    with _b2:
        with st.container(key="uv_danger_btn"):
            _do_restore = st.button("Restore workspace", type="primary", key="admin_restore_confirm",
                                    width="stretch")
    if _do_restore:
        with st.spinner("Restoring…"):
            restore_backup(backup_id, email)
        st.session_state["_admin_restore_done"] = {"id": backup_id, "created": created}
        st.rerun()


@st.dialog("Export encryption key", width="large")
def _dlg_export_env():
    # Deliberately separate from "Create backup now" — routine backups no
    # longer bundle .env (see backup.py's export_zip docstring), so this is
    # the one place that still hands out the deployment's master secrets.
    # Not persisted anywhere; computed and offered fresh on each open.
    st.warning(
        "This file contains this deployment's master encryption and session-signing "
        "keys (AUTH_SECRET, ENCRYPTION_KEY). Anyone who has it can decrypt every "
        "user's data and sign in as anyone, on any account. Store it somewhere "
        "separate from your data backups — only export it when setting up a new "
        "deployment that needs to read this one's encrypted data.",
        icon=":material/warning:",
    )
    _env_bytes = export_env_key()
    if _env_bytes is None:
        st.info("No .env file found on this server.")
    else:
        st.download_button("Download .env", data=_env_bytes, file_name=".env",
                           mime="text/plain", type="primary", width="stretch",
                           key="admin_export_env_dl")


@st.dialog("Send password reset", width="large")
def _dlg_reset_password(email: str):
    st.caption("They'll need this link to set a new password — there's no outbound email, "
              "so share it with them yourself. Existing sessions stay signed in until they use it.")
    if st.button("Generate reset link", key="admin_reset_pw_submit", type="primary", width="stretch"):
        ok, msg, token = admin_request_password_reset(email, requested_by=current_user().email)
        if ok:
            st.success(msg)
            st.code(f"{st.context.url}?reset={token}", language=None)
            st.caption("Reset link — shown once. Copy it now. Valid for 24 hours.")
        else:
            st.error(msg)


def _render_users() -> None:
    users = list_users()
    _current_email = current_user().email

    # Real stat tiles only — the mockup's 4th tile is a fictional "Seats used
    # 6/25" (no subscription/seat-limit concept in this app), so this keeps
    # the previous "Suspended" count instead.
    _c1, _c2, _c3, _c4 = st.columns(4, gap="small")
    _stats = [
        ("Total users",      len(users)),
        ("Active now",       sum(1 for u in users if u["status"] == "Active")),
        ("Pending invites",  sum(1 for u in users if u["status"] == "Invited")),
        ("Suspended",        sum(1 for u in users if u["status"] == "Suspended")),
    ]
    for _col, (_label, _value) in zip((_c1, _c2, _c3, _c4), _stats):
        with _col:
            st.markdown(_stat_tile(_label, _value), unsafe_allow_html=True)

    st.container(height=6, border=False)

    _t1, _t2 = st.columns([3, 1], vertical_alignment="bottom")
    with _t1:
        _search = st.text_input("Search users…", key="admin_user_search", label_visibility="collapsed",
                                placeholder="Search users…")
    with _t2:
        if st.button("Invite user", key="admin_open_invite", icon=":material/add:", type="primary",
                     width="stretch"):
            _dlg_invite()

    _filtered = [u for u in users if not _search or _search.lower() in u["email"].lower()
                or _search.lower() in _display_name(u["email"]).lower()]

    with st.container(key="admin_users_card", border=True):
        with st.container(key="admin_users_colheader"):
            _h1, _h2, _h3, _h4, _h5, _h6, _h7 = st.columns([2.4, 1, 1, 1.3, 0.9, 1.5, 1.2])
            for _col, _label in zip((_h1, _h2, _h3, _h4, _h5, _h6, _h7),
                                    ("User", "Role", "Status", "Sign-in", "2FA", "Last active", "")):
                with _col:
                    st.markdown(f'<div style="font-size:10.5px;color:var(--faint);font-weight:500;'
                               f'letter-spacing:0.05em;text-transform:uppercase;line-height:1.3;">'
                               f'{_label}</div>', unsafe_allow_html=True)

        if not _filtered:
            _msg = f'No users match "{_search}".' if _search else "No users found."
            st.markdown(f'<div style="text-align:center;padding:30px 0;color:var(--faint);font-size:13px;">'
                       f'{_msg}</div>', unsafe_allow_html=True)

        for u in _filtered:
            with st.container(key=f"admin_user_row_{u['email']}"):
                _c1, _c2, _c3, _c4, _c5, _c6, _c7 = st.columns(
                    [2.4, 1, 1, 1.3, 0.9, 1.5, 1.2], vertical_alignment="center")
                with _c1:
                    st.markdown(f'<div style="font-size:13px;font-weight:500;color:var(--text);line-height:1.3;">'
                               f'{_display_name(u["email"])}</div>'
                               f'<div style="font-size:11px;color:var(--faint);font-family:var(--uv-mono);'
                               f'margin-top:2px;line-height:1.3;">{u["email"]}</div>', unsafe_allow_html=True)
                with _c2:
                    _new_role = st.selectbox("Role", options=list(ROLES), index=list(ROLES).index(u["role"]),
                                             key=f"admin_role_{u['email']}", label_visibility="collapsed",
                                             disabled=(u["email"] == _current_email))
                    if _new_role != u["role"]:
                        _ok, _msg = set_role(u["email"], _new_role)
                        if not _ok:
                            # st.toast, not st.error — survives the rerun
                            # below (same reasoning as the feed-toggle revert
                            # further down this file); a same-run st.error()
                            # would be replaced before ever painting.
                            st.toast(_msg, icon=":material/warning:")
                        st.rerun()
                with _c3:
                    st.markdown(_status_badge(u["status"]), unsafe_allow_html=True)
                with _c4:
                    st.markdown(f'<div style="font-size:11.5px;color:var(--muted);">'
                               f'{_signin_methods_label(u["email"])}</div>', unsafe_allow_html=True)
                with _c5:
                    st.markdown(_2fa_badge(two_factor_status(u["email"])), unsafe_allow_html=True)
                with _c6:
                    _last = u["last_active"]
                    st.markdown(f'<div style="font-size:11.5px;color:var(--faint);font-family:var(--uv-mono);">'
                               f'{_last[:16].replace("T", " ") if _last else "Never"}</div>',
                               unsafe_allow_html=True)
                with _c7:
                    if u["email"] == _current_email:
                        st.markdown('<div style="font-size:12px;color:var(--faint);text-align:right;">You</div>',
                                   unsafe_allow_html=True)
                    else:
                        # Suspend + delete side by side (not stacked) so this
                        # column's height matches the design's single-pill
                        # row instead of doubling it — the mockup itself has
                        # no delete affordance at all; kept as a real feature
                        # via a compact overflow popover next to it.
                        _ac1, _ac2 = st.columns([3, 1])
                        with _ac1:
                            _label = "Reactivate" if u["status"] == "Suspended" else "Suspend"
                            if st.button(_label, key=f"admin_toggle_{u['email']}", width="stretch"):
                                _ok, _msg = set_status(
                                    u["email"], "Active" if u["status"] == "Suspended" else "Suspended")
                                if not _ok:
                                    st.toast(_msg, icon=":material/warning:")
                                st.rerun()
                        with _ac2:
                            with st.popover("", icon=":material/more_vert:", width=200):
                                if st.button("Send password reset", key=f"admin_reset_pw_{u['email']}",
                                            width="stretch"):
                                    _dlg_reset_password(u["email"])
                                if two_factor_status(u["email"]) == "ON":
                                    if st.button("Reset two-factor", key=f"admin_reset_totp_{u['email']}",
                                                width="stretch"):
                                        _ok, _msg = admin_reset_totp(u["email"])
                                        st.toast(_msg, icon=None if _ok else ":material/warning:")
                                        st.rerun()
                                if st.button("Sign out all sessions", key=f"admin_signout_all_{u['email']}",
                                            width="stretch"):
                                    _ok, _msg = revoke_other_sessions(u["email"], keep_sid=None)
                                    st.toast(_msg, icon=None if _ok else ":material/warning:")
                                    st.rerun()
                                st.caption(f"Delete {u['email']}? This cannot be undone.")
                                if st.button("Delete account", key=f"admin_delete_{u['email']}", type="primary"):
                                    _ok, _msg = delete_user(u["email"])
                                    if not _ok:
                                        st.toast(_msg, icon=":material/warning:")
                                    st.rerun()


def _sec_row_header(label: str) -> None:
    # padding/min-height match .st-key-admin_users_colheader's own values
    # exactly (uvalu/pages_/admin.py's _admin_shell_css) — previously 15px
    # 20px with no height floor, 4px more generous per side than the Users
    # table's own header with nothing keeping it consistent, which read as
    # "the header looks too tall" once the two pages were compared side by
    # side.
    st.markdown(f'<div style="padding:11px 20px;min-height:34px;box-sizing:border-box;'
               f'border-bottom:0.5px solid var(--line-2);font-size:13px;'
               f'font-weight:600;letter-spacing:0.03em;text-transform:uppercase;color:var(--faint);'
               f'line-height:1.3;display:flex;align-items:center;">{label}</div>', unsafe_allow_html=True)


def _sec_row_title(title: str, desc: str) -> None:
    st.markdown(f'<div><div style="font-size:13.5px;font-weight:500;line-height:1.3;">{title}</div>'
               f'<div style="font-size:12px;color:var(--muted);margin-top:2px;line-height:1.5;">{desc}</div></div>',
               unsafe_allow_html=True)


_MFA_GRACE_OPTS = ["3 d", "7 d", "14 d", "30 d"]
_SESSION_TTL_OPTS = ["8 h", "24 h", "7 d"]


def _render_security() -> None:
    st.caption("Workspace-wide authentication policy — applies to every account, not just this one.")
    _shared = load_shared_settings()

    # ── Password policy ────────────────────────────────────────────────────
    with st.container(key="admin_sec_card_password", border=True):
        _sec_row_header("Password policy")
        with st.container(key="admin_sec_row_minlen"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title("Minimum password length", "Applies to every new password — invite "
                              "acceptance, admin resets, and self-service changes.")
            with _c2:
                _min_len = st.slider("Minimum password length", 8, 20,
                                     int(_shared.get("min_password_length", 12)),
                                     key="admin_sec_min_len", label_visibility="collapsed")
        with st.container(key="admin_sec_row_breach"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title("Block breached passwords", "Checked against Have I Been Pwned by hash "
                              "prefix — the password never leaves this server.")
            with _c2:
                _block_breach = st.toggle("Block breached passwords",
                                          value=bool(_shared.get("block_breached_passwords", True)),
                                          key="admin_sec_block_breach", label_visibility="collapsed")

        if (int(_min_len) != int(_shared.get("min_password_length", 12))
                or bool(_block_breach) != bool(_shared.get("block_breached_passwords", True))):
            _shared["min_password_length"] = int(_min_len)
            _shared["block_breached_passwords"] = bool(_block_breach)
            save_shared_settings(_shared)
            st.rerun()

    # ── Two-factor authentication ──────────────────────────────────────────
    with st.container(key="admin_sec_card_mfa", border=True):
        _sec_row_header("Two-factor authentication")
        with st.container(key="admin_sec_row_require_mfa"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title("Require 2FA", "Who must enroll in an authenticator app before they can "
                              "sign in with a password.")
            with _c2:
                _require_mfa = st.segmented_control(
                    "Require 2FA", options=["Off", "Admins", "Everyone"],
                    default=str(_shared.get("require_mfa", "Admins")), label_visibility="collapsed",
                    key="admin_sec_require_mfa", width="stretch")
        with st.container(key="admin_sec_row_grace"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title("Grace period", "How long a newly-required account can still sign in "
                              "before enrolling. Not yet enforced — display only.")
            with _c2:
                _cur_grace = str(_shared.get("mfa_grace_days", "7 d"))
                _grace = st.segmented_control(
                    "Grace period", options=_MFA_GRACE_OPTS,
                    default=_cur_grace if _cur_grace in _MFA_GRACE_OPTS else "7 d",
                    label_visibility="collapsed", key="admin_sec_grace", width="stretch")

        if ((_require_mfa and _require_mfa != _shared.get("require_mfa", "Admins"))
                or (_grace and _grace != _shared.get("mfa_grace_days", "7 d"))):
            _shared["require_mfa"] = _require_mfa or _shared.get("require_mfa", "Admins")
            _shared["mfa_grace_days"] = _grace or _shared.get("mfa_grace_days", "7 d")
            save_shared_settings(_shared)
            st.rerun()

    # ── Rate limiting & sessions ────────────────────────────────────────────
    with st.container(key="admin_sec_card_ratelimit", border=True):
        _sec_row_header("Rate limiting &amp; sessions")
        with st.container(key="admin_sec_row_attempts"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title("Attempts before lock", "Failed password attempts on one account before "
                              "it locks.")
            with _c2:
                _attempts = st.slider("Attempts before lock", 3, 10,
                                      int(_shared.get("login_attempts_before_lock", 5)),
                                      key="admin_sec_attempts", label_visibility="collapsed")
        with st.container(key="admin_sec_row_lockmin"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title("Lock duration", "How long an account stays locked once triggered.")
            with _c2:
                _lock_min = st.slider("Lock duration (minutes)", 5, 60,
                                      int(_shared.get("lock_minutes", 15)), step=5,
                                      key="admin_sec_lock_min", label_visibility="collapsed")
        with st.container(key="admin_sec_row_session_ttl"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title("Session lifetime", "How long a signed-in session stays valid before "
                              "requiring another sign-in.")
            with _c2:
                _cur_ttl = str(_shared.get("session_ttl", "24 h"))
                _ttl = st.segmented_control(
                    "Session lifetime", options=_SESSION_TTL_OPTS,
                    default=_cur_ttl if _cur_ttl in _SESSION_TTL_OPTS else "24 h",
                    label_visibility="collapsed", key="admin_sec_session_ttl", width="stretch")

        if (int(_attempts) != int(_shared.get("login_attempts_before_lock", 5))
                or int(_lock_min) != int(_shared.get("lock_minutes", 15))
                or (_ttl and _ttl != _shared.get("session_ttl", "24 h"))):
            _shared["login_attempts_before_lock"] = int(_attempts)
            _shared["lock_minutes"] = int(_lock_min)
            _shared["session_ttl"] = _ttl or _shared.get("session_ttl", "24 h")
            save_shared_settings(_shared)
            st.rerun()

    # ── Identity providers ──────────────────────────────────────────────────
    with st.container(key="admin_sec_card_providers", border=True):
        _sec_row_header("Identity providers")
        for _p in oauth.configured_providers():
            with st.container(key=f"admin_sec_row_provider_{_p['id']}"):
                _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
                with _c1:
                    _sec_row_title(_p["label"], "Available for this workspace." if _p["configured"]
                                  else "Not configured — add credentials to secrets.toml.")
                with _c2:
                    _bg, _txt = ("var(--up-bg)", "var(--up-txt)") if _p["configured"] \
                        else ("var(--line-2)", "var(--faint)")
                    st.markdown(f'<span style="display:inline-block;background:{_bg};color:{_txt};'
                               f'padding:3px 9px;border-radius:5px;font-size:11px;font-weight:500;">'
                               f'{"Configured" if _p["configured"] else "Not configured"}</span>',
                               unsafe_allow_html=True)

        with st.container(key="admin_sec_row_autoprov"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title("Auto-provision new accounts", "Create an account automatically for any "
                              "sign-in from an allowed domain below, instead of requiring an invite first.")
            with _c2:
                _auto_prov = st.toggle("Auto-provision new accounts",
                                       value=bool(_shared.get("auto_provision_oauth", False)),
                                       key="admin_sec_auto_prov", label_visibility="collapsed")

        with st.container(key="admin_sec_row_domains"):
            _sec_row_title("Allowed email domains", "Comma-separated. Only used when auto-provision is on.")
            _domains_txt = st.text_input(
                "Allowed email domains", key="admin_sec_domains", label_visibility="collapsed",
                value=", ".join(_shared.get("allowed_email_domains", [])), placeholder="company.com, other.org")

        _new_domains = [d.strip().lower() for d in _domains_txt.split(",") if d.strip()]
        if (bool(_auto_prov) != bool(_shared.get("auto_provision_oauth", False))
                or _new_domains != _shared.get("allowed_email_domains", [])):
            _shared["auto_provision_oauth"] = bool(_auto_prov)
            _shared["allowed_email_domains"] = _new_domains
            save_shared_settings(_shared)
            st.rerun()

        # Passkeys — Phase 3, UI stub only (mockup frame 14): no WebAuthn/
        # py_webauthn registration or login exists yet, so there's no real
        # setting behind this toggle to persist — it's permanently off until
        # that's built.
        with st.container(key="admin_sec_row_passkeys"):
            _c1, _c2 = st.columns([2.3, 1.3], vertical_alignment="center")
            with _c1:
                _sec_row_title(
                    'Passkeys<span style="font-size:9.5px;letter-spacing:0.04em;padding:2px 6px;'
                    'border-radius:4px;background:var(--amber-bg);color:var(--amber-txt);margin-left:8px;">'
                    'PHASE 3</span>',
                    "Feature flag. Off until the custom component is verified on real devices.")
            with _c2:
                st.toggle("Passkeys", value=False, disabled=True, key="admin_sec_passkeys",
                         label_visibility="collapsed")


def _render_feeds() -> None:
    st.caption("Enable or disable exchanges included in the Screener and portfolio analysis. "
              "There's no live health/latency monitoring — this only reflects enabled vs disabled.")
    _shared = load_shared_settings()
    _enabled = set(_shared.get("enabled_exchanges", ALL_EXCHANGES))

    with st.container(key="admin_feeds_card", border=True):
        for _key, _label in EXCHANGE_LABELS.items():
            _was_on = _key in _enabled
            # A blocked toggle (would disable the last exchange) is reverted via
            # this separate flag key, applied *before* the st.toggle below
            # instantiates for the run. Writing straight to the toggle's own
            # session_state key here would hit Streamlit's "cannot modify a
            # widget's state after it's instantiated" guard, since the toggle
            # was already instantiated on the run where the block happened.
            if st.session_state.pop(f"_admin_feed_revert_{_key}", False):
                st.session_state[f"admin_feed_{_key}"] = True
                _was_on = True
            with st.container(key=f"admin_feed_row_{_key}"):
                _c1, _c2, _c3, _c4 = st.columns([0.3, 3.3, 1, 1], vertical_alignment="center")
                with _c1:
                    _dot_color = "var(--mint)" if _was_on else "var(--faint)"
                    _dot_ring = "box-shadow:0 0 0 3px rgba(29,214,164,0.18);" if _was_on else ""
                    st.markdown(f'<span style="display:inline-block;width:8px;height:8px;'
                               f'border-radius:50%;background:{_dot_color};{_dot_ring}"></span>',
                               unsafe_allow_html=True)
                with _c2:
                    st.markdown(f'<div style="font-size:13px;font-weight:500;color:var(--text);line-height:1.3;">'
                               f'{_label}</div>'
                               f'<div style="font-size:11.5px;color:var(--faint);margin-top:2px;line-height:1.3;">'
                               f'Equities feed — {_EXCHANGE_SUFFIX.get(_key, "")} tickers</div>',
                               unsafe_allow_html=True)
                with _c3:
                    _badge_bg, _badge_txt = ("var(--up-bg)", "var(--up-txt)") if _was_on \
                        else ("var(--panel-2)", "var(--faint)")
                    st.markdown(f'<span style="display:inline-block;background:{_badge_bg};color:{_badge_txt};'
                               f'padding:3px 9px;border-radius:5px;font-size:11px;font-weight:500;">'
                               f'{"Enabled" if _was_on else "Disabled"}</span>', unsafe_allow_html=True)
                with _c4:
                    _on = st.toggle(_label, value=_was_on, key=f"admin_feed_{_key}",
                                    label_visibility="collapsed")

            # Save immediately on change instead of a separate Save button
            # (same "no Save buttons, persist on change" rule already applied
            # to Settings). A blocked toggle (would disable the last exchange)
            # is reverted on the *next* rerun via the `_admin_feed_revert_*`
            # flag set above, rather than by overwriting the widget's own
            # session_state here — that would hit Streamlit's guard against
            # modifying a widget's state after it's instantiated this run.
            # st.toast (not st.error) survives the immediate st.rerun() this
            # revert needs; a same-run st.error() here would be replaced
            # before ever painting, per the restore-dialog's identical lesson
            # elsewhere in this file.
            if _on != _was_on:
                if not _on and len(_enabled) <= 1:
                    st.session_state[f"_admin_feed_revert_{_key}"] = True
                    st.toast("At least one exchange must be enabled.", icon=":material/warning:")
                    st.rerun()
                else:
                    if _on:
                        _enabled.add(_key)
                    else:
                        _enabled.discard(_key)
                    _shared["enabled_exchanges"] = [k for k in EXCHANGE_LABELS if k in _enabled]
                    save_shared_settings(_shared)
                    _load_all_screener_data.clear()
                    st.rerun()


def _render_backups(email: str) -> None:
    _t1, _t2 = st.columns([3, 1.7], vertical_alignment="center")
    with _t1:
        st.markdown('<div style="font-size:12.5px;color:var(--muted);line-height:1.5;">Every entry here is a '
                   'real, on-demand snapshot — this app has no scheduler, so nothing is created '
                   'automatically. All entries are Manual. Backups don\'t include this deployment\'s '
                   'encryption keys — export those separately if migrating to a new machine.</div>',
                   unsafe_allow_html=True)
    with _t2, st.container(horizontal=True, gap="small"):
        if st.button("Export key", key="admin_export_env", icon=":material/key:", type="tertiary",
                     width="stretch", help="This deployment's encryption/signing keys — only needed "
                     "when migrating to a new machine, not part of routine backups"):
            _dlg_export_env()
        if st.button("Create backup now", key="admin_create_backup", icon=":material/backup:", type="primary",
                     width="stretch"):
            with st.spinner("Creating backup…"):
                create_backup(email)
            st.success("Backup created.")
            st.rerun()

    entries = list_backups()
    if not entries:
        st.info("No backups yet.")
        return

    # A restore that just completed needs its dialog reopened in the "done"
    # state on this fresh rerun (the button click that triggered it doesn't
    # persist across st.rerun()) — same reopen-after-rerun pattern used for
    # the stock-detail drawer (uvalu/pages_/screener.py's _drw_reopen_ticker).
    _pending_done = st.session_state.get("_admin_restore_done")

    with st.container(key="admin_backups_card", border=True):
        for e in entries:
            _created = e["created_at"][:16].replace("T", " ")
            _size_mb = e["size_bytes"] / 1024 / 1024
            with st.container(key=f"admin_backup_row_{e['id']}"):
                _c1, _c2, _c3, _c4 = st.columns([3, 1, 1, 1], vertical_alignment="center")
                with _c1:
                    st.markdown('<div style="font-size:13px;font-weight:500;color:var(--text);line-height:1.3;">'
                               'Manual snapshot</div>'
                               f'<div style="font-size:11.5px;color:var(--faint);margin-top:2px;'
                               f'font-family:var(--uv-mono);line-height:1.3;">{_created} · {_size_mb:.1f} MB · '
                               f'{e["email"]}</div>', unsafe_allow_html=True)
                with _c2:
                    st.markdown('<span style="display:inline-block;background:var(--soft);color:var(--up-txt);'
                               'padding:3px 9px;border-radius:5px;font-size:11px;font-weight:500;">Manual</span>',
                               unsafe_allow_html=True)
                with _c3:
                    # A callable, not the bytes directly — get_backup_bytes()
                    # reads the whole ZIP off disk; passing it eagerly meant
                    # EVERY backup's full file got read into memory on EVERY
                    # rerun of this section (any click anywhere on the page),
                    # not just when its own Download was clicked. Streamlit
                    # only calls a callable `data` on the actual click.
                    #
                    # Downloads are scoped to your own backups — a backup can
                    # contain another admin's real portfolio holdings, so
                    # `disabled=` here (UI) and get_backup_bytes()'s own
                    # requester_email check (server-side, in case this
                    # callable is ever reached another way) both enforce it.
                    # Restore below deliberately isn't scoped the same way —
                    # restoring someone's own snapshot back into their own
                    # account is a legitimate cross-admin recovery action.
                    _is_own_backup = e["email"] == email
                    st.download_button(
                        "Download", data=lambda _bid=e["id"]: get_backup_bytes(_bid, email),
                        file_name=f"{e['id']}.zip", mime="application/zip",
                        key=f"admin_dl_{e['id']}", width="stretch", disabled=not _is_own_backup,
                        help=None if _is_own_backup else "You can only download your own backups.",
                    )
                with _c4:
                    if st.button("Restore", key=f"admin_restore_{e['id']}", width="stretch"):
                        _dlg_restore(e["id"], _created, e["email"])
            if _pending_done and _pending_done.get("id") == e["id"]:
                _dlg_restore(e["id"], _created, e["email"])


def _admin_shell_css(active: str) -> str:
    return f"""
/* ── Safety net: default every text-bearing tag inside the admin page to
   var(--text). Uvalu Admin.dc.html relies on its own `body{{color:var(
   --text)}}` cascade for this; this app has no equivalent (native Streamlit
   text color follows the REAL st.context.theme, not the `data-theme`
   attribute this page force-overrides to dark above), so any raw-HTML
   element here that forgets an explicit `color:` silently inherits
   whatever native theme the user's browser last had — invisible dark-on-
   dark text if that happened to be light. This rule is the fallback; inline
   `color:` on specific spans/badges (var(--faint)/var(--up-txt)/etc.) still
   wins via inline-style specificity. ── */
.st-key-admin_root, .st-key-admin_root p, .st-key-admin_root span, .st-key-admin_root div,
.st-key-admin_root li, .st-key-admin_root label {{
  color: var(--text);
}}
/* Cancels a real 16px flex gap between the injected `<style>` tag (a plain
   st.markdown() call, not wrapped in the uv_hidden_util hiding convention
   like the theme/popover scripts above it) and this container — confirmed
   live via the vertical block's own child list: the three script iframes
   correctly contribute 0 (already position:absolute per the existing
   uv_hidden_util CSS), but the un-hidden style tag's own zero-height
   element-container still counts as a normal flex sibling and eats one
   real `gap:16px`, pushing admin_root down to y=16 instead of y=0 — which,
   combined with `min-height:100vh` below, made the sidebar overflow 16px
   past the true viewport bottom and visibly shrank the topbar's right edge
   via an induced scrollbar. */
.st-key-admin_root {{ margin-top: -16px !important; }}

/* ── True edge-to-edge full-bleed, scoped to ONLY this page via :has() ──
   Every other page in this app keeps the global 1.5rem .block-container
   margin (uvalu/styles.py); Admin needs to break out of it entirely so its
   sidebar/topbar reach the real browser edges, matching Uvalu Admin.dc.html
   (a genuinely standalone full-viewport shell, not embedded in another
   app's chrome). `:has(.st-key-admin_root)` scopes the override to exactly
   the page that renders that wrapper — no per-page conditional needed, and
   every other page's own margin is untouched. Simpler and more robust than
   the main topbar's `margin:0 -1.5rem;width:calc(100% + 3rem)` breakout
   trick (uvalu/shell.py's uv_topbar), which only works because that bar is
   100% width; Admin's sidebar is a percentage-ratio st.column, so there's
   no single pixel constant to calc against — zeroing the padding at the
   source avoids needing one. */
.block-container:has(.st-key-admin_root) {{
  padding: 0 !important; max-width: 100% !important;
}}

.st-key-admin_sidebar {{
  /* A tiny hairline border, per feedback (reversing the previous round's
     "no borders" — matches Uvalu Admin.dc.html's own spec, which always
     had `border-right:0.5px solid var(--line)` here). */
  background: var(--panel); border-right: 0.5px solid var(--line);
  /* No top padding — the logo wrapper below owns its own exact-58px band
     instead, so its vertical center lines up with the topbar's title
     (which centers in its own separate 58px bar via completely different
     CSS). Left/right/bottom padding stays for the nav buttons below. */
  padding: 0 14px 20px;
  /* Pin the nav rail in place while a tall section (e.g. Security, whose
     stacked cards run well past one viewport) scrolls underneath it.
     `position:sticky` was tried first (tracking the nearest scrolling
     ancestor, Streamlit's own `[data-testid="stMain"]`, confirmed live via
     scrollHeight/clientHeight) but doesn't actually work here: Streamlit
     gives every `stVerticalBlock` — this column's own nav rail included —
     `flex:1 0 0%` by default, so as soon as its immediate wrapper chain is
     given enough height for sticky to have "room" to work in, that same
     `flex-grow` re-stretches the nav rail to fill it, cancelling the fixed
     100vh box sticky needs (confirmed live: forcing the two ancestor
     wrappers to `height:100%` made the rail's own rendered height balloon
     from 900px to the full 1192px scrollable content height, and it still
     didn't stick, until `flex:none` was *also* forced on the rail itself —
     three separate overrides fighting Streamlit's own flex defaults, and
     fragile to any future DOM change in how Streamlit nests these wrapper
     divs). `position:fixed` sidesteps all of it: fixed's containing block
     is the viewport itself (no ancestor here has a transform/filter/
     perspective/contain that would redefine that, confirmed live), so it
     doesn't care about any ancestor's flex/height behavior at all. The nav
     COLUMN itself (`st.columns([0.16, 0.84])`, the flex item one level up)
     is untouched and still reserves 16% of the row's width as an empty
     box — this fixed rail just visually overlays that same reserved
     stripe instead of rendering inside it, so the main column needs no
     compensating margin. */
  position: fixed !important; top: 0 !important; left: 0 !important;
  width: 16% !important; height: 100vh !important; z-index: 20 !important;
  display: flex !important; flex-direction: column !important;
}}
/* Matches the topbar's own height:58px + flex-centering technique exactly
   (same two fixes needed there also apply here: !important, since a plain
   height loses to Streamlit's own rule, and flex-direction:row, since the
   container defaults to column) — the logo sits in the identical 0-58px
   vertical band the topbar occupies, so both texts' vertical centers land
   on the same 29px line despite being two completely separate elements. */
.st-key-admin_sidebar_logo {{
  height: 58px !important; min-height: 58px !important;
  display: flex !important; flex-direction: row !important; align-items: center !important;
}}
/* The REAL bug behind every previous round's failed attempt to align this
   text: `align-items:center` doesn't center the visible glyphs, it centers
   whatever height Streamlit thinks the flex item is — and confirmed live
   via a full ancestor-chain walk, `stElementContainer` here reports only
   4px against the real 20px content (the "uvalu ADMIN" markdown). Centering
   a 4px box in a 58px row puts its TOP near the row's true center (27px),
   and the real 20px-tall text then grows DOWNWARD from there instead of
   being symmetric around it — landing the text's own visual center at 37px,
   a consistent 8px below the row's true 29px center. (Every earlier "this
   measures as centered" check in this file was unknowingly measuring the
   WRONG element — a `querySelector('div')`/`querySelector('span')` call
   that grabbed an outer generated wrapper instead of the actual styled
   text node, several DOM levels apart once Streamlit's own nesting is
   accounted for; re-measuring via the exact `[data-testid=
   "stMarkdownContainer"] > div` element is what finally exposed this.)
   Fix: floor the reporting element at its real height so centering computes
   against 20px, not 4px. */
.st-key-admin_sidebar_logo [data-testid="stElementContainer"] {{
  min-height: 20px !important;
}}
.st-key-admin_sidebar button {{
  width: 100%; justify-content: flex-start !important; border: none !important;
  background: transparent !important; color: var(--muted) !important;
  font-size: 12.5px !important; border-radius: 8px !important;
}}
/* The button's own justify-content is irrelevant here — its single child (an
   unkeyed inner div, confirmed live via computed style) independently sets
   `display:flex;justify-content:center`, which is what was actually
   centering the icon+label despite the outer rule above. */
.st-key-admin_sidebar button > div {{ justify-content: flex-start !important; }}
.st-key-admin_sidebar button:hover {{ background: var(--line-2) !important; color: var(--text) !important; }}
.st-key-admin_navbtn_{active} button {{
  background: var(--soft) !important; color: var(--mint) !important; font-weight: 500 !important;
}}
/* Pins "← Back to app" to the bottom of the now-full-height sidebar (design:
   `margin-top:auto` on its own sidebar footer). Unlike the Dashboard
   conviction card's db_conv_metrics footer (which needed a `:has()` parent
   hop to reach an extra generated wrapper level), this button's own
   `st-key-admin_back` class sits as a DIRECT child of `.st-key-admin_sidebar`
   itself (confirmed live via the DOM ancestor chain) — no wrapper indirection
   needed here. */
.st-key-admin_sidebar > .st-key-admin_back {{ margin-top: auto !important; }}
.st-key-admin_topbar {{
  /* Same tiny-hairline-border reversal as the sidebar above. */
  background: var(--panel); border-bottom: 0.5px solid var(--line);
  padding: 0 20px;
  /* Fixed, not sticky — same reasoning as the sidebar's own fix above:
     Streamlit's default `flex:1 0 0%` on every stVerticalBlock (this bar's
     own wrapper included) fights any attempt to give its ancestor chain
     "room" for sticky to work in, so `position:fixed` (relative to the
     viewport, not any ancestor's flex box) is used instead. `left:16%`
     starts it exactly where the sidebar's own `width:16%` ends, matching
     Uvalu Admin.dc.html's own header spec (`position:sticky;top:0;
     z-index:10` — sticky works there because that's a static HTML mockup
     with none of Streamlit's generated wrapper divs in between). Otherwise
     the title/status/avatar row scrolls out of view with the rest of a
     tall section (Security) while the now-fixed sidebar stays put, which
     would look like only half the chrome is fixed. Taking this out of
     normal flow drops its old `margin-bottom:18px` reserved space — that
     gap is added back as `admin_content`'s own `padding-top` below instead,
     since a fixed element no longer pushes its flow-siblings down on its
     own. */
  /* `width:auto !important` is required alongside `left`/`right` — Streamlit
     gives every `stVerticalBlock` (this bar's own wrapper included) an
     explicit `width:100%` from its own base CSS, and per the CSS
     positioning spec, an explicit `width` on a `left`+`right`-anchored
     positioned box makes `right` get silently RECOMPUTED (i.e. ignored)
     instead of the reverse — confirmed live: without this, the bar's own
     `right:0` had no effect and it rendered 1440px wide starting at
     `left:16%`, overflowing ~230px off the right edge of the (1440px)
     viewport used in that test. Forcing `width:auto` restores the normal
     "compute width from left+right" behavior this rule actually wants. */
  position: fixed !important; top: 0 !important; left: 16% !important; right: 0 !important;
  width: auto !important; z-index: 20 !important;
  /* Both !important AND flex-direction needed, confirmed live after a first
     attempt silently failed: (1) `height` alone (no !important) lost to
     Streamlit's own un-important-but-higher-specificity rule, computed
     height stayed 14.67px; (2) Streamlit's container defaults to
     `flex-direction:column`, so `align-items:center` was centering the
     single child along the CROSS axis (horizontally) — the wrong axis for
     "vertically center the title/avatar row" — until flex-direction:row is
     forced too. */
  height: 58px !important; min-height: 58px !important;
  display: flex !important; flex-direction: row !important; align-items: center !important;
}}
/* The title/avatar row's own reported height (43.33px, back when the bar's
   height came from padding+content instead of a fixed height) undershot its
   real content (the 30px avatar square), letting the avatar overflow past
   the bar's own bottom edge by ~1.33px — confirmed live. Pinning the bar to
   a fixed 58px height (matching the spec exactly) and centering the whole
   row inside it via `align-items:center` on the topbar container itself
   fixes both the overflow and the "title/avatar not vertically centered"
   feedback in one rule, without needing the row's own height to be exactly
   right — flex centering handles that regardless. */
.st-key-admin_topbar [data-testid="stHorizontalBlock"] {{ width: 100% !important; }}
/* The t2 column (status dot + avatar) reported only 14px tall against its
   real 30px content (the avatar square) — confirmed live via
   getBoundingClientRect. Since that column has no explicit
   vertical_alignment of its own reaching the avatar correctly, the avatar's
   content just started at the column's (too-short) top edge and overflowed
   downward, so its own visual center (measured 52.67) sat well below the
   topbar's true center (45). Same "wrapper under-reports its raw-HTML
   content" bug as everywhere else in this file; flooring the column at the
   avatar's real height fixes it the same way. */
.st-key-admin_topbar [data-testid="stColumn"]:last-child {{ min-height: 30px !important; }}
/* CORRECTION to this file's own earlier claim that "the outer flex-centering
   fix above" already handled the TITLE (t1) column correctly — it hadn't.
   Every prior measurement of this claimed to confirm it via `topbar.
   querySelector('div')`, which (once this page's DOM grew several more
   nesting levels across later rounds) silently grabbed an outer generated
   WRAPPER div instead of the actual styled title text, several levels
   removed — so those checks were unknowingly re-confirming the wrapper's
   own (correct) centering, never the real text's. Measuring the exact
   `[data-testid="stMarkdownContainer"] > div` element instead exposed the
   real bug: t1's own stColumn reports 0px against the title's real 15px,
   so the title text's own visual center sat ~8px below the bar's true
   center — the identical root cause as t2's avatar column above, just
   never actually fixed for t1 until now. */
.st-key-admin_topbar [data-testid="stColumn"]:first-child {{ min-height: 15px !important; }}

/* ── Content inset — the topbar itself stays genuinely flush (no padding,
   full-bleed per feedback), but the section content BELOW it (stat tiles,
   table, search bar) needs its own left/right breathing room now that the
   block-container's own global padding was zeroed for this whole page above
   (that zeroing was needed for the sidebar/topbar to reach the true browser
   edges, but it also stripped the main content's only source of horizontal
   inset — confirmed live via a screenshot showing stat cards touching the
   topbar's own left edge with zero margin). Matches the design's own
   `padding:28px 32px 60px` on its main content wrapper. Top padding is
   `76px` (58px topbar height + its old 18px margin-bottom), not the
   design's `28px`: the topbar is `position:fixed` now (see its own rule
   above) and no longer reserves its own space in normal flow, so
   admin_content would otherwise render its first 76px of content hidden
   behind the fixed bar. ── */
.st-key-admin_content {{ padding: 76px 32px 60px; }}

/* ── Users/Feeds/Backups table panels — one seamless bordered card
   (header + hairline-divided rows) instead of a stack of individually
   bordered/gapped st.container(border=True) cards, matching the design's
   <table>/row-list markup. Same overflow:hidden/padding:0/margin-top:-16px
   row-divider convention used by Screener's scr_table_card.
   Security's four cards (admin_sec_card_*) join the same rule — there's no
   "Security" section in Uvalu Admin.dc.html to match, so these previously
   kept Streamlit's bare st.container(border=True) look: native
   theme-driven border color/radius (8px, not this app's 12px), transparent
   background, and no box-shadow — visibly different chrome from every
   other admin card once compared side by side, confirmed live via
   getComputedStyle (border `0.666667px solid rgb(34,51,78)` vs. this rule's
   `var(--line)`, radius 8px vs. 12px, no shadow). ── */
.st-key-admin_users_card, .st-key-admin_feeds_card, .st-key-admin_backups_card,
.st-key-admin_sec_card_password, .st-key-admin_sec_card_mfa,
.st-key-admin_sec_card_ratelimit, .st-key-admin_sec_card_providers {{
  background: var(--panel) !important; border-color: var(--line) !important;
  border-radius: 12px !important; box-shadow: var(--shadow) !important;
  overflow: hidden !important; padding: 0 !important;
}}
.st-key-admin_users_colheader {{
  padding: 11px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
  min-height: 34px !important;
}}
[class*="st-key-admin_user_row_"], [class*="st-key-admin_feed_row_"], [class*="st-key-admin_backup_row_"] {{
  padding: 12px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
  margin-top: -16px !important; min-height: 60px !important;
}}
[class*="st-key-admin_feed_row_"] {{ min-height: 64px !important; }}
[class*="st-key-admin_backup_row_"] {{ min-height: 58px !important; }}
/* Feeds/Backups have no header row before their first data row (unlike
   Users, where -16px correctly cancels the gap to admin_users_colheader) —
   so their first row has no preceding 16px sibling gap to cancel in the
   first place. Applying -16px there anyway pulled it up past the card's own
   top edge and let `overflow:hidden` silently clip ~15px off its top,
   confirmed live (row measured from y=136.4 while the card's own boundary
   started at y=151.7 — only the row's bottom ~48.67px of 64px was actually
   visible). Same lesson as this file's set_slider_grid entry: a "same-shaped"
   gap-cancel fix from one context (a row after a header) doesn't
   automatically apply to a different context (a row with no header) just
   because both measured -16px — reset it to 0 for the true first row only.
   A first attempt used a bare `[class*=...]:first-child` selector — it
   matched EVERY row, not just the first, because each row's own st-key div
   is nested one level inside an unnamed per-row wrapper (confirmed live via
   each card child's outerHTML) and is therefore an ONLY child of that
   wrapper, trivially satisfying `:first-child` regardless of its position
   among the 6 visible rows. Anchoring on the CARD's own direct children
   (the true positional siblings) and descending from there is what actually
   isolates row 1. */
.st-key-admin_feeds_card > div:first-child [class*="st-key-admin_feed_row_"],
.st-key-admin_backups_card > div:first-child [class*="st-key-admin_backup_row_"] {{
  margin-top: 0 !important;
}}

/* ── Security cards' own setting rows (admin_sec_row_*) — same hairline
   row-divider convention as the Users/Feeds/Backups rows above, cancelling
   the same default ~16px inter-sibling gap against the `_sec_row_header`
   markdown title directly above each card's first row (every security card
   has one, unlike Feeds/Backups' headerless first row above — so no
   first-row exception is needed here: -16px is correct for every row in
   every security card). One shared prefix selector reaches all eleven keys
   this file uses (`admin_sec_row_minlen`, `_breach`, `_require_mfa`,
   `_grace`, `_attempts`, `_lockmin`, `_session_ttl`, the per-provider loop's
   `_provider_{id}`, `_autoprov`, `_domains`, `_passkeys`) without listing
   each one. ── */
/* `_sec_row_header()`'s own wrapper has the same under-reported-height bug
   as everywhere else in this file: the styled div inside it correctly
   grows to its real ~40px (11px padding top/bottom + line height, now that
   it also carries an explicit min-height and flex centering — see
   _sec_row_header itself), but the surrounding stElementContainer Streamlit
   generates still reports only 24px, letting the header's own bottom edge
   visually run into the first row below it. Floored at that same 40px,
   matching the pattern already used for every other raw-HTML block on this
   page. Always the card's own first direct child, so no need to reach for
   the wider admin_sec_row_ prefix or a card-by-card list. */
[class*="st-key-admin_sec_card_"] > [data-testid="stElementContainer"]:first-child {{
  min-height: 40px !important;
}}
[class*="st-key-admin_sec_row_"] {{
  /* padding/min-height match the Users table's own row values exactly
     (`[class*="st-key-admin_user_row_"]` below) — previously 15px 20px /
     64px, both a few px more generous than Users' 12px 20px / 60px, which
     read as an inconsistency once the two pages were compared side by
     side. */
  padding: 12px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
  margin-top: -16px !important;
  /* Floors every row at the sliders' own natural height (title + floating
     value label) — previously unset, so row height tracked whatever that
     row's own control needed (55px for a bare toggle up to 99px for a
     segmented control that wrapped to two lines), reported as visibly
     inconsistent row heights. `admin_sec_row_domains` (title + description
     + input, stacked) is naturally taller than this floor already, so it's
     unaffected without needing its own exception. */
  min-height: 60px !important;
}}
/* The title+description block `_sec_row_title()` renders is raw HTML in a
   markdown container that under-reports its own height to Streamlit's
   layout engine — confirmed live: a two-line block measured 38px tall but
   its wrapping stColumn reported only 22px. Every row already sets
   `vertical_alignment="center"` on its st.columns(...) correctly; the
   centering math was just running against that wrong, shorter number,
   which visibly offset the text from the control next to it. Same bug
   class as the Users table's name+email column elsewhere in this file;
   Security's own rows just never got the equivalent fix. */
[class*="st-key-admin_sec_row_"] [data-testid="stColumn"]:first-child {{
  min-height: 38px !important;
}}
/* Same under-reported-height bug, different symptom: the "Allowed email
   domains" row isn't a two-column layout, so the title+description block
   and the text input just stack with a normal 16px flex gap between them.
   Because the block's wrapper reports 22px against its real 38px, the
   visible text overflows 16px below where the layout thinks it ends,
   swallowing the entire gap meant to separate it from the input (confirmed
   live: 0px between the two). The ACTUAL flex item participating in that
   16px gap is the `stElementContainer` wrapper one level further out than
   `stMarkdownContainer` — flooring the inner container alone (tried first)
   didn't move the outer one, which still reported 22px and still ate the
   gap. `:first-child` reaches only the row's own first direct child (the
   title+description container specifically) — not the general
   admin_sec_row_ prefix, since other rows' markdown also includes small
   badge/status spans that shouldn't be forced to the same height. */
[class*="st-key-admin_sec_row_domains"] > [data-testid="stElementContainer"]:first-child {{
  min-height: 38px !important;
}}
/* Deliberately not special-casing each card's own last row to drop its
   border-bottom — the Users table's last row keeps its own border-bottom
   too, matching the design's identical per-row `<tr>` styling in Uvalu
   Admin.dc.html, so this stays consistent with every other row list here. */
/* The name+email 2-line raw-HTML block under-reports its own wrapper height
   (17px reported vs. ~33px real, live-measured) — with vertical_alignment=
   "center" on the row's columns, that mismatch centers the text on the
   wrong (shorter) box, rendering it visibly off-center against the other
   cells. Same bug class documented for Settings' row list; fix is the same
   min-height-on-the-column floor. */
[class*="st-key-admin_user_row_"] [data-testid="stColumn"]:first-child,
[class*="st-key-admin_backup_row_"] [data-testid="stColumn"]:first-child {{
  min-height: 34px !important;
}}
[class*="st-key-admin_feed_row_"] [data-testid="stColumn"]:nth-child(2) {{
  min-height: 34px !important;
}}
/* Same bug, fourth column — this comment and the two rules below it
   originally targeted "Last active" and "You" by nth-child position, but
   the table has since gained Sign-in and 2FA columns in between Status and
   Last active, shifting every column after Status two positions to the
   right without these selectors being updated to match. Re-measured live
   against the current 7-column layout (User, Role, Status, Sign-in, 2FA,
   Last active, actions): Last active and You now center correctly on
   their own (0px offset from the Role select's own center, a reliably-
   centered reference); nth-child(4) is actually Sign-in ("Password"),
   which measured 8px too high. Kept the existing min-height on the COLUMN
   itself (harmless, and Sign-in's own natural content really is ~18px) but
   that alone wasn't the real fix here — confirmed live the column's own
   floor doesn't help because its DIRECT CHILD (an auto-generated
   stVerticalBlock wrapping the st.markdown call) is itself under-reporting
   (2px reported vs. the column's real 18px), the same bug one level
   deeper. Flooring that inner block too is what actually centers it. */
[class*="st-key-admin_user_row_"] [data-testid="stColumn"]:nth-child(4) {{
  min-height: 18px !important;
}}
[class*="st-key-admin_user_row_"] [data-testid="stColumn"]:nth-child(4) [data-testid="stVerticalBlock"] {{
  min-height: 18px !important;
}}
/* 2FA (nth-child(5), badge) already centers correctly on its own (+1px,
   within measurement noise) — this floor predates the column reshuffle
   above and is a harmless no-op today (19px is below its natural ~27px),
   left in place rather than removed since it costs nothing and a future
   layout change could plausibly need it again. */
[class*="st-key-admin_user_row_"] [data-testid="stColumn"]:nth-child(5) {{
  min-height: 19px !important;
}}

/* ── st.popover panels ("⋯" delete-account confirm) — Streamlit renders
   these in a portal with native theme-driven chrome (background AND text
   color both independently follow the REAL st.context.theme, same bug
   class as the search box/select above, confirmed live: this page's own
   custom --panel/--navy vars only happened to already look dark in one
   test session because that session's real theme was ALSO dark — not
   because anything here was actually forcing it). Portals render outside
   admin_root's own DOM subtree, so this can't be scoped via a descendant
   selector; relies instead on this rule only existing in the DOM while
   this page's own <style> tag is present (same as every other admin.py
   rule). Matches the navy chrome st.dialog already uses elsewhere in the
   app for visual consistency between the two kinds of overlay. ── */
[data-testid="stPopoverBody"] {{
  background: var(--navy) !important; border: 0.5px solid var(--line) !important;
  box-shadow: 0 20px 60px rgba(0,0,0,0.35) !important;
}}
[data-testid="stPopoverBody"] * {{
  color: var(--text) !important; background-color: transparent !important;
}}
/* The primary "Delete account" button needs its own teal background back —
   the broad transparent-background rule above would otherwise flatten it
   too. Safe: an attribute selector on `button[kind]` has far higher
   specificity than the bare `*` above, so this wins regardless of rule
   order even with matching !important on both sides. */
[data-testid="stPopoverBody"] button[kind="primary"] {{
  background-color: var(--teal) !important;
}}

/* ── st.selectbox dropdown list (Role select's options panel) — a SEPARATE
   native-themed portal from st.popover above (BaseWeb's own `[data-baseweb=
   "popover"]`/`data-testid="stSelectboxVirtualDropdown"`, not Streamlit's
   `stPopoverBody`), so the popover fix above never reached it. Confirmed
   live this was rendering correctly dark ONLY because that test session's
   real theme had ALREADY been flipped by `_force_native_dark_once()`'s own
   reload earlier in the same session — not because of any explicit CSS —
   so on a session where that reload hasn't fired yet (or fails silently in
   some environment) this would still show native-light white, same root
   cause as every other fix in this section. Guaranteed CSS backstop, same
   pattern as the search box/select/popover above. ── */
[data-testid="stSelectboxVirtualDropdown"] {{
  background: var(--navy) !important;
}}
[data-testid="stSelectboxVirtualDropdown"] li {{
  color: var(--text) !important; background-color: transparent !important;
}}
[data-testid="stSelectboxVirtualDropdown"] li:hover {{
  background-color: var(--line-2) !important;
}}
[data-testid="stSelectboxVirtualDropdown"] li[aria-selected="true"] {{
  background-color: var(--soft) !important; color: var(--mint) !important;
}}
/* Same border-follows-native-theme bug as the closed select box (fixed a
   round ago), on the OPEN dropdown panel this time — confirmed live via an
   ancestor-chain walk from the popover root down to the `<ul>`: a wrapper
   two levels in paints `border: 0.666667px solid rgb(34, 51, 78)` (`
   [theme.dark] borderColor`, "#22334E") in a real-theme-dark session, which
   becomes `[theme.light]`'s "#E5E7EB" (light gray, high-contrast against
   the forced-dark page) otherwise — the exact bright outline reported.
   That wrapper has no stable testid/class of its own, so it's targeted via
   `:has()` from its known child instead of guessing a hashed class name. */
[data-baseweb="popover"] div:has(> [data-testid="stSelectboxVirtualDropdown"]) {{
  border: 0.5px solid var(--line) !important;
}}

/* ── Segmented controls (Require 2FA, Grace period, Session lifetime) — the
   unselected pills had NO app CSS at all before this (Streamlit's own
   default styling only). The selected pill already renders correctly (a
   mint-tinted background/border Streamlit applies natively) and isn't
   touched here — only the unselected state needs a rule, keyed on the
   `aria-checked` attribute rather than any Emotion-generated class name so
   it survives a selection change. NOTE: this rule is confirmed CORRECT via
   getComputedStyle() (resolves to exactly `var(--panel-2)`/`var(--line)`),
   but repeated live screenshots in this session's own testing tool kept
   showing the pill painting white regardless — including with the value
   forced as an inline style, with `appearance:none`, and combinations of
   both, while an unrelated medium-brightness test color (`rgb(80,80,80)`)
   painted correctly in the same spot every time. That pattern (only very
   low-luminance colors on this one native `<button>` element failing to
   paint, independent of how the color is set) points at a rendering quirk
   in that specific testing tool rather than a real browser bug — plain
   `<div>`-based dark surfaces elsewhere on this exact page paint fine at
   similar luminance. Left as this straightforward, spec-correct rule
   rather than adding an unproven workaround; verify in a real browser
   after this ships, since the automated check here could not confirm it
   visually one way or the other. */
.st-key-admin_root [data-testid="stButtonGroup"] button[aria-checked="false"] {{
  background-color: var(--panel-2) !important; border-color: var(--line) !important;
  color: var(--muted) !important;
}}

/* ── Center narrow controls (toggles, status badges) in their own column —
   sliders and segmented controls already fill the full column width so
   centering is a no-op for them, but a small toggle or a "Configured"/
   "Not configured" badge just started at the column's left edge by default,
   confirmed live sitting flush against the left with 0px gap on one side
   and well over half the column empty on the other. Listed by each row's
   own key rather than a generic "column holds a small widget" selector, so
   this can't accidentally catch a future wide control added to one of
   these same rows.
   Two false starts before this, both confirmed live: `display:flex;
   justify-content:center` on the COLUMN itself had no effect (its one
   direct child, a Streamlit-generated `stVerticalBlock`, already spans the
   column's full width on its own, so centering *that* is a no-op — the
   actual narrow element, a 32px stElementContainer, is nested another
   level inside it); the same rule on that inner stVerticalBlock ALSO had
   no effect, because it's a column-direction flex container by default —
   `justify-content` there centers the (single, vertical) main axis, not
   the horizontal one. `align-items` is the property that controls the
   CROSS axis, which is horizontal for a column-direction flex — that's
   the one that actually moves the toggle. */
[class*="st-key-admin_sec_row_breach"] [data-testid="stColumn"]:nth-child(2) [data-testid="stVerticalBlock"],
[class*="st-key-admin_sec_row_autoprov"] [data-testid="stColumn"]:nth-child(2) [data-testid="stVerticalBlock"],
[class*="st-key-admin_sec_row_passkeys"] [data-testid="stColumn"]:nth-child(2) [data-testid="stVerticalBlock"],
[class*="st-key-admin_sec_row_provider_"] [data-testid="stColumn"]:nth-child(2) [data-testid="stVerticalBlock"] {{
  align-items: center !important;
}}

/* ── Feed toggle — recolor Streamlit's default switch to the design's
   teal-when-on pill instead of the generic red/gray default. DOM order is
   track-div, then <input>, then the label-text div (confirmed live via
   outerHTML) — the checked input has no LATER sibling that's the track, so
   `input:checked + div` (which was tried first) silently matched nothing;
   `:has()` targeting the track from its checked-input DESCENDANT sibling is
   what actually works. `:first-child` (not `:first-of-type`) happened to
   still be correct here only because Data feeds' own toggle label has no
   leading non-div sibling — confirmed live it breaks for Security's toggles
   specifically, whose label's actual first CHILD is a `<span>` (screen-
   reader text?), making the real track div only `:first-of-type`, never
   `:first-child`; the old selector silently matched nothing there, and the
   "Block breached passwords" toggle only ever looked teal-when-on by
   coincidence (Streamlit's own native checked-toggle color), not from this
   rule. `:first-of-type` works for both rows' actual DOM shape. */
[class*="st-key-admin_feed_row_"] [data-testid="stCheckbox"] label > div:first-of-type,
[class*="st-key-admin_sec_row_"] [data-testid="stCheckbox"] label > div:first-of-type {{
  background-color: var(--panel-2) !important; border-color: var(--line) !important;
}}
[class*="st-key-admin_feed_row_"] [data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type,
[class*="st-key-admin_sec_row_"] [data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type {{
  background-color: var(--teal) !important; border-color: var(--teal) !important;
}}

/* ── Role select / search input — dark panel-2 fields matching every other
   page's input treatment instead of Streamlit's default light chrome.
   `.st-key-admin_topbar ~ * [data-testid="stTextInput"]` was meant as a
   catch-all for "any text input after the topbar" (including the domains
   input below) but confirmed live via `el.matches(...)` to match NOTHING —
   the `~` general-sibling combinator needs admin_topbar and the input's
   ancestor to share the same direct parent, and Streamlit's own layout-
   wrapper divs put them one level deeper than that, so they're never
   actually siblings. Left in place rather than removed (harmless no-op,
   and auditing every other place that might coincidentally depend on it
   is its own separate pass) but no longer trusted alone — every text input
   on this page now also gets its own dedicated `:has()` rule below, which
   doesn't have this problem. ── */
[class*="st-key-admin_user_row_"] [data-testid="stSelectbox"] > div,
.st-key-admin_topbar ~ * [data-testid="stTextInput"] > div,
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) > div,
div[data-testid="stTextInput"]:has(input[aria-label="Allowed email domains"]) > div {{
  background-color: var(--panel-2) !important; border-color: var(--line) !important;
}}
/* Direct, unconditional override on the specific NATIVE-themed div underneath
   the one above — confirmed live via document.elementFromPoint() at the
   search box/select's own screen coordinates that Streamlit nests a SECOND
   div here (exactly 2 levels below stTextInput/stSelectbox) which paints
   from `[theme.light]`/`[theme.dark]` `secondaryBackgroundColor`
   independent of any custom CSS var — the reason this kept reverting to
   white despite the div one level up already being correctly dark.
   `_force_native_dark_once()` (this page's render()) fixes the ROOT cause
   by flipping the real theme so that native color resolves dark on its
   own, but that depends on a client-side localStorage-write-then-reload
   completing correctly; this rule fixes the same symptom unconditionally
   via plain CSS, with no dependency on reload timing, as a guaranteed
   backstop regardless of whether the reload path succeeds in a given
   browser/environment. The domains input was missing from here specifically
   (only its border/text/placeholder got a dedicated rule in an earlier
   round, background was wrongly assumed to already be covered by the
   general topbar-sibling selector above) — confirmed live as the actual
   cause of it still rendering with a white background. */
[class*="st-key-admin_user_row_"] [data-testid="stSelectbox"] > div > div,
.st-key-admin_topbar ~ * [data-testid="stTextInput"] > div > div,
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) > div > div,
div[data-testid="stTextInput"]:has(input[aria-label="Allowed email domains"]) > div > div {{
  background-color: var(--panel-2) !important;
}}
/* This same deep div also paints its BORDER from the native theme's
   `borderColor` config (`.streamlit/config.toml`'s `[theme.light]` "#E5E7EB"
   vs. `[theme.dark]` "#22334E") — only the background was ever fixed above;
   the border was never touched, so on a real-light-theme session it renders
   a light gray/near-white border against the forced-dark background,
   reading as a jarring bright outline that doesn't match the Suspend
   button's own subtle `var(--line)` hairline right next to it. Same
   guaranteed-CSS-backstop pattern as the background fix, matching the
   Suspend button's exact border spec. */
/* The search box's own deep div was missing from this same border-fix —
   only its BACKGROUND got the guaranteed-backstop treatment above; its
   border was left to inherit the native theme's borderColor exactly like
   the select box's deep div did before the rule below existed for it.
   Confirmed as the actual cause of the reported white search-bar outline
   (a real-light-theme session's `[theme.light]` "#E5E7EB" against this
   page's forced-dark background) — not the same class of bug as the
   segmented-control/toggle "stale paint" issue fixed elsewhere in this
   file, just this one selector never having been extended when the
   pattern was first established for the Role select. */
[class*="st-key-admin_user_row_"] [data-testid="stSelectbox"] > div > div,
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) > div > div,
div[data-testid="stTextInput"]:has(input[aria-label="Allowed email domains"]) > div > div {{
  border: 0.5px solid var(--line) !important;
}}
/* The search box's actual TEXT never had an explicit color at all (only its
   ancestor divs' background was ever fixed) — as long as the box itself
   was still white this was invisible (dark-on-white read fine by accident),
   but now that the background is guaranteed dark, that same never-fixed
   native text color (still following the real theme, same root cause as
   every fix above) went dark-on-dark. `::placeholder` needs its own rule
   separately from `color` — browsers don't inherit placeholder color from
   the input's own text color. */
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) input,
div[data-testid="stTextInput"]:has(input[aria-label="Allowed email domains"]) input {{
  color: var(--text) !important;
}}
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) input::placeholder,
div[data-testid="stTextInput"]:has(input[aria-label="Allowed email domains"]) input::placeholder {{
  color: var(--faint) !important; opacity: 1 !important;
}}

/* ── Suspend/Reactivate outline pill + Restore/Download buttons — match the
   design's `border:0.5px solid var(--line);color:var(--muted)` pill instead
   of Streamlit's default secondary-button look. ── */
[class*="st-key-admin_user_row_"] button[kind="secondary"],
[class*="st-key-admin_backup_row_"] button[kind="secondary"] {{
  background: transparent !important; border: 0.5px solid var(--line) !important;
  color: var(--muted) !important; font-size: 12px !important;
}}
[class*="st-key-admin_user_row_"] button[kind="secondary"]:hover,
[class*="st-key-admin_backup_row_"] button[kind="secondary"]:hover {{
  border-color: var(--teal) !important; color: var(--text) !important;
}}

/* ── User row overflow ("⋯") popover trigger — was a bare text "⋯" button
   that Streamlit ALWAYS appends its own "expand_more" chevron to (confirmed
   live via outerHTML: the button's one direct child wraps TWO sibling
   divs — the label/icon, then a second `aria-hidden="true"` div holding the
   chevron — unconditionally, on every st.popover trigger) — two separate
   "there's more here" indicators (an ellipsis character AND a chevron)
   stacked inside a 25px-wide button read as cluttered, not "nicer" as
   requested. Switched the Python call to a proper `icon=":material/
   more_vert:"` kebab icon with an empty label, and hide the redundant
   chevron entirely here. A first attempt used `> div[aria-hidden="true"]`
   (direct child of the button) and silently matched nothing — confirmed
   live the chevron div is a GRANDCHILD, nested one level inside that
   wrapper, not a direct child; a plain descendant selector (no `>`) is
   what actually reaches it. */
[class*="st-key-admin_user_row_"] [data-testid="stPopoverButton"] div[aria-hidden="true"] {{
  display: none !important;
}}
[class*="st-key-admin_user_row_"] [data-testid="stPopoverButton"] {{
  width: 36px !important; min-width: 36px !important; padding: 0 !important;
  display: flex !important; align-items: center !important; justify-content: center !important;
}}
/* The icon sat 2.5px right of the button's true center (12.5px left margin
   vs. 7.5px right, confirmed live) despite correct `justify-content:center`
   on the button itself. Cause: Streamlit puts a native `margin: 0 -5px 0 0`
   on the button's own label-wrapper div — a compensation that normally
   tucks the label closer to the trailing chevron this button ships with by
   default. Since that chevron is hidden above, the -5px is now an orphaned
   offset with nothing left to compensate for, silently skewing the
   otherwise-correct flex centering. Zeroing it directly is what actually
   fixes the icon's horizontal position — `justify-content` alone can't
   override a margin on the item being centered. */
[class*="st-key-admin_user_row_"] [data-testid="stPopoverButton"] > div {{
  margin: 0 !important;
}}
"""


def _force_native_dark_once() -> None:
    """Flip Streamlit's REAL native theme (st.context.theme) to dark for this
    page, not just the custom `data-theme` CSS attribute apply_theme_script()
    sets below. The two are independent systems: native BaseWeb widgets (the
    Role select, the search input) get their background from Streamlit's own
    `[theme.light]`/`[theme.dark]` `secondaryBackgroundColor` — confirmed live
    via `document.elementFromPoint()` at the search box's own coordinates,
    which found a SECOND div nested inside the one this file's CSS already
    darkens, painted directly from that native theme value, independent of
    any custom CSS var. If the user's real theme happens to be light, that
    inner div renders `[theme.light]`'s white `secondaryBackgroundColor`
    regardless of the custom attribute forced below — the same class of bug
    already fixed once for raw-HTML text color, just recurring on a native
    widget this time. Reuses the same localStorage key Settings' Theme
    control and the topbar's sun/moon toggle write
    (`stActiveTheme-<path>-v2`, shell.set_theme_script), but with an
    idempotency guard set_theme_script itself doesn't have — calling it
    unconditionally on every render would reload in an infinite loop, since
    the reload re-enters this same render() which would fire it again."""
    st.iframe("""
<script>
(function(){
  try {
    var path = window.parent.location.pathname;
    var key = 'stActiveTheme-' + path + '-v2';
    if (window.parent.localStorage.getItem(key) !== JSON.stringify('Dark')) {
      window.parent.localStorage.setItem(key, JSON.stringify('Dark'));
      window.parent.location.reload();
    }
  } catch(e) {}
})();
</script>
""", height=1)


def render() -> None:
    _u = current_user()
    if not _u.is_admin:
        logkit.authz_denied(action="admin.view", actor=logkit.user_id(),
                            required_role="Admin", got_role=_u.role)
        st.error("Admin access required.")
        st.stop()

    # This portal has no light-theme variant in the design — force dark
    # regardless of the user's own toggle, same as the main nav rail. Without
    # this, the page inherits whatever theme was last active elsewhere, since
    # it (deliberately) skips shell.render_topbar()'s own apply_theme_script().
    # Also force-close a leftover avatar popover: clicking "Admin portal"
    # inside that popover navigates here without ever firing its own
    # outside-click-to-close listener (same bug already fixed for Settings/
    # Help in shell.render_topbar(), flagged there as applying here too once
    # this page got touched — but this page skips render_topbar() entirely,
    # so that existing gate never reaches this destination; call the same
    # helper directly instead).
    with st.container(key="uv_hidden_util_admin_theme"):
        apply_theme_script(light=False)
        _force_native_dark_once()
        _close_stray_popover_script()

    _dash_page = nav_registry.pages.get("dashboard")
    _section = st.session_state.get("admin_section", "users")

    def _goto(section: str) -> None:
        st.session_state["admin_section"] = section
        st.rerun()

    st.markdown(f"<style>{_admin_shell_css(_section)}</style>", unsafe_allow_html=True)

    # ── Standalone shell: its own sidebar nav + header, not the main app's
    # top-bar (skipped for this page in app.py) — matching Uvalu Admin.dc.html's
    # separate admin surface rather than reusing the Dashboard/Screener/etc chrome.
    # Wrapped in one keyed container so `.st-key-admin_root`'s CSS default text
    # color (below) can act as a safety net for any raw-HTML text that forgets
    # an explicit `color:` — mirrors the design file's own `body{color:var(
    # --text)}` cascade, which this app has no equivalent of (native Streamlit
    # text color instead follows the REAL st.context.theme, not the custom
    # `data-theme` attribute this page force-overrides above).
    with st.container(key="admin_root"):
        # No gap — the sidebar/topbar are now flush structural panels with
        # no border at all (per feedback), so the topbar should sit flush
        # against the sidebar's own right edge with zero space between them.
        _nav_col, _main_col = st.columns([0.16, 0.84], gap=None)

        with _nav_col:
            with st.container(key="admin_sidebar"):
                with st.container(key="admin_sidebar_logo"):
                    # align-items:center (not the design's own "baseline") —
                    # mixing a 20px and a 9.5px span with baseline alignment
                    # visually reads as off-center even when the outer band's
                    # own box-center is mathematically correct (confirmed via
                    # precise measurement to match the topbar title's center
                    # every round so far): the smaller "admin" text's
                    # baseline sits level with the larger "uvalu" text's
                    # baseline, but that's not the same as either span
                    # looking vertically centered against the topbar's own
                    # single-size title. explicit line-height:1 on both spans
                    # removes font-metric ascender/descender slack that would
                    # otherwise still skew the optical center even under
                    # align-items:center.
                    st.markdown(
                        '<div style="display:flex;align-items:center;gap:9px;padding-left:8px;">'
                        '<span style="font-size:20px;font-weight:500;letter-spacing:-0.03em;'
                        'line-height:1;color:var(--text);">'
                        'uval<span style="color:var(--teal)">u</span></span>'
                        '<span style="font-size:9.5px;letter-spacing:0.14em;text-transform:uppercase;'
                        'line-height:1;color:var(--faint);">admin</span></div>',
                        unsafe_allow_html=True,
                    )
                for _key, _label, _icon in _NAV_ITEMS:
                    if st.button(_label, key=f"admin_navbtn_{_key}", icon=_icon, width="stretch"):
                        _goto(_key)
                if _dash_page is not None and st.button("← Back to app", key="admin_back", type="tertiary",
                                                         width="stretch"):
                    st.switch_page(_dash_page)

        with _main_col:
            with st.container(key="admin_topbar"):
                _t1, _t2 = st.columns([3, 1], vertical_alignment="center")
                with _t1:
                    st.markdown(f'<div style="font-size:15px;font-weight:500;color:var(--text);'
                               f'line-height:1;letter-spacing:-0.01em;">{_SECTION_TITLES[_section]}</div>',
                               unsafe_allow_html=True)
                with _t2:
                    st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:flex-end;gap:16px;">
  <div style="display:flex;align-items:center;gap:7px;font-size:11px;color:var(--faint);font-family:var(--uv-mono);">
    <span style="width:6px;height:6px;border-radius:50%;background:var(--mint);box-shadow:0 0 0 3px rgba(29,214,164,0.18);"></span>
    All systems operational</div>
  <div style="width:30px;height:30px;border-radius:8px;background:var(--navy);border:0.5px solid var(--line);
             display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;color:var(--mint);">
    {_initials(_u.email)}</div>
</div>""", unsafe_allow_html=True)

            with st.container(key="admin_content"):
                if _section == "users":
                    _render_users()
                elif _section == "security":
                    _render_security()
                elif _section == "feeds":
                    _render_feeds()
                else:
                    _render_backups(_u.email)
