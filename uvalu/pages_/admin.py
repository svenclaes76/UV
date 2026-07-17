"""Admin portal — Users, Data feeds, Backups. A standalone page reached only
via the avatar dropdown (uvalu/shell.py), not the regular top-bar nav —
matching the mockup's separate admin-only surface. Admin-role only."""
import streamlit as st

from auth import ROLES, list_users, set_role, set_status, delete_user, invite_user
from backup import list_backups, create_backup, get_backup_bytes, restore_backup
from settings import load_shared_settings, save_shared_settings, ALL_EXCHANGES, EXCHANGE_LABELS
from uvalu import nav as nav_registry
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user

_STATUS_STYLE = {
    "Active":    ("var(--up-bg,#E8F5F0)",    "var(--up-txt,#0F6E56)"),
    "Invited":   ("var(--amber-bg,#FDF0E8)", "var(--amber-txt,#854F0B)"),
    "Suspended": ("var(--down-bg,#FCEAEA)",  "var(--down-txt,#A32D2D)"),
}


def _status_badge(status: str) -> str:
    bg, txt = _STATUS_STYLE.get(status, ("var(--line-2)", "var(--muted)"))
    return (f'<span style="background:{bg};color:{txt};padding:3px 9px;border-radius:5px;'
           f'font-size:11px;font-weight:500;">{status}</span>')


def _display_name(email: str) -> str:
    """Title-cased name derived from the email local-part (e.g. "marek.k@uvalu.eu"
    -> "Marek K") — there's no real display-name field in the user record, so
    this is a readable stand-in rather than a fabricated one, same approach as
    shell.py's _initials() avatar helper."""
    local = (email or "").split("@")[0]
    parts = [p for p in local.replace(".", " ").replace("_", " ").replace("-", " ").split(" ") if p]
    return " ".join(p.capitalize() for p in parts) if parts else email


@st.dialog("Invite user", width="large")
def _dlg_invite():
    st.caption("They'll need this temporary password to sign in — there's no outbound email, "
              "so share it with them yourself.")
    _email = st.text_input("Email", key="admin_invite_email", placeholder="name@company.com")
    _role = st.selectbox("Role", options=list(ROLES), index=list(ROLES).index("Analyst"),
                         key="admin_invite_role")
    if st.button("Send invite", key="admin_invite_submit", type="primary"):
        ok, msg, temp_pw = invite_user(_email, _role)
        if ok:
            st.success(msg)
            st.code(temp_pw, language=None)
            st.caption("Temporary password — shown once. Copy it now.")
        else:
            st.error(msg)


@st.dialog("Restore workspace?", width="large")
def _dlg_restore(backup_id: str, created: str, email: str):
    st.warning("This replaces all current portfolio data and settings with this snapshot. "
              "This cannot be undone.", icon=":material/warning:")
    st.markdown(f"**Manual snapshot**  \n{created}")
    if st.button("Restore workspace", type="primary", key="admin_restore_confirm"):
        with st.spinner("Restoring…"):
            restored = restore_backup(backup_id, email)
        st.success(f"Restored: {', '.join(restored)}")
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
            _c1, _c2 = st.columns([5, 1], vertical_alignment="center")
            _c1.markdown(f"**{_label}**")
            _on = _c2.toggle(_label, value=_key in _enabled, key=f"admin_feed_{_key}",
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


def render() -> None:
    _u = current_user()
    if not _u.is_admin:
        st.error("Admin access required.")
        st.stop()

    _dash_page = nav_registry.pages.get("dashboard")
    if _dash_page is not None and st.button("← Back to app", key="admin_back", type="tertiary"):
        st.switch_page(_dash_page)

    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Admin portal</div>',
               unsafe_allow_html=True)

    _tab_users, _tab_feeds, _tab_backups = st.tabs(["Users", "Data feeds", "Backups"])
    with _tab_users:
        _render_users()
    with _tab_feeds:
        _render_feeds()
    with _tab_backups:
        _render_backups(_u.email)
