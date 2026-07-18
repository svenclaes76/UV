"""Admin portal — Users, Data feeds, Backups. A standalone page reached only
via the avatar dropdown (uvalu/shell.py) and rendering its own sidebar nav +
header (render()'s _admin_shell_css/_nav_col/_main_col) instead of the main
app's top-bar — app.py skips shell.render_topbar() for this page's url_path
so the two chromes never stack. Matches Uvalu Admin.dc.html's separate
admin-only surface. Admin-role only."""
import streamlit as st

from auth import ROLES, list_users, set_role, set_status, delete_user, invite_user
from backup import list_backups, create_backup, get_backup_bytes, restore_backup
from settings import load_shared_settings, save_shared_settings, ALL_EXCHANGES, EXCHANGE_LABELS
from uvalu import nav as nav_registry
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user
from uvalu.shell import _initials, _display_name

_NAV_ITEMS = (
    ("users",   "Users",       ":material/group:"),
    ("feeds",   "Data feeds",  ":material/dns:"),
    ("backups", "Backups",     ":material/backup:"),
)
_SECTION_TITLES = {"users": "User management", "feeds": "Data feeds", "backups": "Backups & restore"}

_STATUS_STYLE = {
    "Active":    ("var(--up-bg,#E8F5F0)",    "var(--up-txt,#0F6E56)"),
    "Invited":   ("var(--amber-bg,#FDF0E8)", "var(--amber-txt,#854F0B)"),
    "Suspended": ("var(--down-bg,#FCEAEA)",  "var(--down-txt,#A32D2D)"),
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
    return (f'<span style="background:{bg};color:{txt};padding:3px 9px;border-radius:5px;'
           f'font-size:11px;font-weight:500;">{status}</span>')


@st.dialog("Invite user", width="large")
def _dlg_invite():
    st.caption("They'll need this temporary password to sign in — there's no outbound email, "
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
        ok, msg, temp_pw = invite_user(_email, _role)
        if ok:
            st.success(msg)
            st.code(temp_pw, language=None)
            st.caption("Temporary password — shown once. Copy it now.")
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
  <div style="font-size:16px;font-weight:500;">Restore complete</div>
  <div style="font-size:12.5px;color:var(--muted);margin-top:6px;">The workspace has been restored to the
    "{_done['created']}" snapshot.</div>
</div>""", unsafe_allow_html=True)
        if st.button("Done", key="admin_restore_done_btn", type="primary", width="stretch"):
            st.session_state.pop("_admin_restore_done", None)
            st.rerun()
        return

    st.warning("This replaces all current portfolio data and settings with this snapshot. "
              "This cannot be undone.", icon=":material/warning:")
    st.markdown(f"**Manual snapshot**  \n{created}")
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


def _render_users() -> None:
    users = list_users()
    _current_email = current_user().email

    _c1, _c2, _c3, _c4 = st.columns(4)
    _c1.metric("Total users", len(users))
    _c2.metric("Active now", sum(1 for u in users if u["status"] == "Active"))
    _c3.metric("Pending invites", sum(1 for u in users if u["status"] == "Invited"))
    _c4.metric("Suspended", sum(1 for u in users if u["status"] == "Suspended"))

    _t1, _t2 = st.columns([3, 1], vertical_alignment="bottom")
    with _t1:
        _search = st.text_input("Search users…", key="admin_user_search", label_visibility="collapsed",
                                placeholder="Search users…")
    with _t2:
        if st.button("Invite user", key="admin_open_invite", type="primary", width="stretch"):
            _dlg_invite()

    _filtered = [u for u in users if not _search or _search.lower() in u["email"].lower()]
    if not _filtered:
        st.info(f'No users match "{_search}".' if _search else "No users found.")
        return

    for u in _filtered:
        with st.container(border=True):
            _c1, _c2, _c3, _c4, _c5 = st.columns([3, 1.4, 1.2, 1.6, 1.2], vertical_alignment="center")
            with _c1:
                st.markdown(f"**{_display_name(u['email'])}**")
                st.caption(f"{u['email']} · since {u['created_at'][:10]}" if u["created_at"] else u["email"])
            with _c2:
                _new_role = st.selectbox("Role", options=list(ROLES), index=list(ROLES).index(u["role"]),
                                         key=f"admin_role_{u['email']}", label_visibility="collapsed",
                                         disabled=(u["email"] == _current_email))
                if _new_role != u["role"]:
                    set_role(u["email"], _new_role)
                    st.rerun()
            with _c3:
                st.markdown(_status_badge(u["status"]), unsafe_allow_html=True)
            with _c4:
                _last = u["last_active"]
                st.caption(_last[:16].replace("T", " ") if _last else "Never")
            with _c5:
                if u["email"] == _current_email:
                    st.caption("You")
                else:
                    _label = "Reactivate" if u["status"] == "Suspended" else "Suspend"
                    if st.button(_label, key=f"admin_toggle_{u['email']}", width="stretch"):
                        set_status(u["email"], "Active" if u["status"] == "Suspended" else "Suspended")
                        st.rerun()
                    with st.popover("⋯", width=160):
                        st.caption(f"Delete {u['email']}? This cannot be undone.")
                        if st.button("Delete account", key=f"admin_delete_{u['email']}", type="primary"):
                            delete_user(u["email"])
                            st.rerun()


def _render_feeds() -> None:
    st.caption("Enable or disable exchanges included in the Screener and portfolio analysis. "
              "There's no live health/latency monitoring — this only reflects enabled vs disabled.")
    _shared = load_shared_settings()
    _enabled = set(_shared.get("enabled_exchanges", ALL_EXCHANGES))
    _new_enabled: list[str] = []
    for _key, _label in EXCHANGE_LABELS.items():
        with st.container(border=True):
            _c1, _c2, _c3, _c4 = st.columns([0.3, 3.3, 1, 1], vertical_alignment="center")
            _was_on = _key in _enabled
            with _c1:
                _dot_color = "var(--mint)" if _was_on else "var(--faint)"
                st.markdown(f'<span style="display:inline-block;margin-top:6px;width:8px;height:8px;'
                           f'border-radius:50%;background:{_dot_color};"></span>', unsafe_allow_html=True)
            with _c2:
                st.markdown(f"**{_label}**")
                st.caption(f"Equities feed — {_EXCHANGE_SUFFIX.get(_key, '')} tickers")
            with _c3:
                _badge_bg, _badge_txt = ("var(--up-bg,#E8F5F0)", "var(--up-txt,#0F6E56)") if _was_on \
                    else ("var(--line-2)", "var(--muted)")
                st.markdown(f'<span style="background:{_badge_bg};color:{_badge_txt};padding:3px 9px;'
                           f'border-radius:5px;font-size:11px;font-weight:500;">'
                           f'{"Enabled" if _was_on else "Disabled"}</span>', unsafe_allow_html=True)
            with _c4:
                _on = st.toggle(_label, value=_was_on, key=f"admin_feed_{_key}",
                                label_visibility="collapsed")
            if _on:
                _new_enabled.append(_key)
    if st.button("Save", key="admin_feeds_save", type="primary"):
        if not _new_enabled:
            st.error("At least one exchange must be enabled.")
        else:
            _shared["enabled_exchanges"] = _new_enabled
            save_shared_settings(_shared)
            _load_all_screener_data.clear()
            st.success("Saved.")
            st.rerun()


def _render_backups(email: str) -> None:
    st.caption("Every entry here is a real, on-demand snapshot — this app has no scheduler, "
              "so nothing is created automatically. All entries are Manual.")
    if st.button("Create backup now", key="admin_create_backup", type="primary"):
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

    for e in entries:
        with st.container(border=True):
            _c1, _c2, _c3, _c4 = st.columns([3, 1, 1, 1], vertical_alignment="center")
            _created = e["created_at"][:16].replace("T", " ")
            _size_mb = e["size_bytes"] / 1024 / 1024
            with _c1:
                st.markdown("**Manual snapshot**")
                st.caption(f"{_created} · {_size_mb:.1f} MB · {e['email']}")
            with _c2:
                st.markdown(
                    '<span style="background:var(--soft,rgba(29,214,164,0.1));color:var(--up-txt,#0F6E56);'
                    'padding:3px 9px;border-radius:5px;font-size:11px;font-weight:500;">Manual</span>',
                    unsafe_allow_html=True)
            with _c3:
                st.download_button("Download", data=get_backup_bytes(e["id"]), file_name=f"{e['id']}.zip",
                                   mime="application/zip", key=f"admin_dl_{e['id']}", width="stretch")
            with _c4:
                if st.button("Restore", key=f"admin_restore_{e['id']}", width="stretch"):
                    _dlg_restore(e["id"], _created, e["email"])
            if _pending_done and _pending_done.get("id") == e["id"]:
                _dlg_restore(e["id"], _created, e["email"])


def _admin_shell_css(active: str) -> str:
    return f"""
.st-key-admin_sidebar {{
  background: var(--panel); border: 0.5px solid var(--line); border-radius: 12px;
  padding: 16px 12px; box-shadow: var(--shadow);
}}
.st-key-admin_sidebar button {{
  width: 100%; justify-content: flex-start !important; border: none !important;
  background: transparent !important; color: var(--muted) !important;
  font-size: 12.5px !important; border-radius: 8px !important;
}}
.st-key-admin_sidebar button:hover {{ background: var(--line-2) !important; color: var(--text) !important; }}
.st-key-admin_navbtn_{active} button {{
  background: var(--soft) !important; color: var(--mint) !important; font-weight: 500 !important;
}}
.st-key-admin_topbar {{
  background: var(--panel); border: 0.5px solid var(--line); border-radius: 12px;
  padding: 12px 20px; box-shadow: var(--shadow); margin-bottom: 18px;
}}
"""


def render() -> None:
    _u = current_user()
    if not _u.is_admin:
        st.error("Admin access required.")
        st.stop()

    _dash_page = nav_registry.pages.get("dashboard")
    _section = st.session_state.get("admin_section", "users")

    def _goto(section: str) -> None:
        st.session_state["admin_section"] = section
        st.rerun()

    st.markdown(f"<style>{_admin_shell_css(_section)}</style>", unsafe_allow_html=True)

    # ── Standalone shell: its own sidebar nav + header, not the main app's
    # top-bar (skipped for this page in app.py) — matching Uvalu Admin.dc.html's
    # separate admin surface rather than reusing the Dashboard/Screener/etc chrome.
    _nav_col, _main_col = st.columns([0.16, 0.84], gap="medium")

    with _nav_col:
        with st.container(key="admin_sidebar"):
            st.markdown(
                '<div style="display:flex;align-items:baseline;gap:9px;padding:0 8px 18px;">'
                '<span style="font-size:20px;font-weight:500;letter-spacing:-0.03em;">'
                'uval<span style="color:var(--teal)">u</span></span>'
                '<span style="font-size:9.5px;letter-spacing:0.14em;text-transform:uppercase;'
                'color:var(--faint);">admin</span></div>',
                unsafe_allow_html=True,
            )
            for _key, _label, _icon in _NAV_ITEMS:
                if st.button(_label, key=f"admin_navbtn_{_key}", icon=_icon, width="stretch"):
                    _goto(_key)
            st.container(height=20, border=False)
            if _dash_page is not None and st.button("← Back to app", key="admin_back", type="tertiary",
                                                     width="stretch"):
                st.switch_page(_dash_page)

    with _main_col:
        with st.container(key="admin_topbar"):
            _t1, _t2 = st.columns([3, 1], vertical_alignment="center")
            with _t1:
                st.markdown(f'<div style="font-size:15px;font-weight:500;letter-spacing:-0.01em;">'
                           f'{_SECTION_TITLES[_section]}</div>', unsafe_allow_html=True)
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

        if _section == "users":
            _render_users()
        elif _section == "feeds":
            _render_feeds()
        else:
            _render_backups(_u.email)
