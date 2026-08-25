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

from auth import ROLES, list_users, set_role, set_status, delete_user, invite_user
from backup import list_backups, create_backup, get_backup_bytes, restore_backup
from settings import load_shared_settings, save_shared_settings, ALL_EXCHANGES, EXCHANGE_LABELS
from uvalu import nav as nav_registry
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user
from uvalu.shell import _initials, _display_name, apply_theme_script, _close_stray_popover_script

_NAV_ITEMS = (
    ("users",   "Users",       ":material/group:"),
    ("feeds",   "Data feeds",  ":material/dns:"),
    ("backups", "Backups",     ":material/backup:"),
)
_SECTION_TITLES = {"users": "User management", "feeds": "Data feeds", "backups": "Backups & restore"}

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


def _stat_tile(label: str, value) -> str:
    return (f'<div style="background:var(--panel);border:0.5px solid var(--line);border-radius:12px;'
           f'padding:16px 18px;">'
           f'<div style="font-size:11px;color:var(--faint);letter-spacing:0.04em;text-transform:uppercase;'
           f'line-height:1.3;">{label}</div>'
           f'<div style="font-size:22px;font-weight:500;margin-top:6px;font-family:var(--uv-mono);'
           f'color:var(--text);line-height:1.2;">{value}</div></div>')


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
            _h1, _h2, _h3, _h4, _h5 = st.columns([3, 1.4, 1.2, 1.6, 1.2])
            for _col, _label in zip((_h1, _h2, _h3, _h4, _h5),
                                    ("User", "Role", "Status", "Last active", "")):
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
                _c1, _c2, _c3, _c4, _c5 = st.columns([3, 1.4, 1.2, 1.6, 1.2], vertical_alignment="center")
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
                    _last = u["last_active"]
                    st.markdown(f'<div style="font-size:11.5px;color:var(--faint);font-family:var(--uv-mono);">'
                               f'{_last[:16].replace("T", " ") if _last else "Never"}</div>',
                               unsafe_allow_html=True)
                with _c5:
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
                            with st.popover("", icon=":material/more_vert:", width=160):
                                st.caption(f"Delete {u['email']}? This cannot be undone.")
                                if st.button("Delete account", key=f"admin_delete_{u['email']}", type="primary"):
                                    _ok, _msg = delete_user(u["email"])
                                    if not _ok:
                                        st.toast(_msg, icon=":material/warning:")
                                    st.rerun()


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
    _t1, _t2 = st.columns([3, 1], vertical_alignment="center")
    with _t1:
        st.markdown('<div style="font-size:12.5px;color:var(--muted);line-height:1.5;">Every entry here is a '
                   'real, on-demand snapshot — this app has no scheduler, so nothing is created '
                   'automatically. All entries are Manual.</div>', unsafe_allow_html=True)
    with _t2:
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
                    st.download_button("Download", data=lambda _bid=e["id"]: get_backup_bytes(_bid),
                                       file_name=f"{e['id']}.zip",
                                       mime="application/zip", key=f"admin_dl_{e['id']}", width="stretch")
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
  /* Full-height nav rail reaching the true viewport edges now that the
     block-container padding above is zeroed for this page — 100vh is exact
     here (no more approximating against the main column's height with a
     fudged constant, since there's no longer any outer padding/offset to
     account for). */
  min-height: 100vh;
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
  padding: 0 20px; margin-bottom: 18px;
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
   `padding:28px 32px 60px` on its main content wrapper (top handled by
   admin_topbar's existing margin-bottom instead, so only left/right/bottom
   are needed here). ── */
.st-key-admin_content {{ padding: 0 32px 60px; }}

/* ── Users/Feeds/Backups table panels — one seamless bordered card
   (header + hairline-divided rows) instead of a stack of individually
   bordered/gapped st.container(border=True) cards, matching the design's
   <table>/row-list markup. Same overflow:hidden/padding:0/margin-top:-16px
   row-divider convention used by Screener's scr_table_card. ── */
.st-key-admin_users_card, .st-key-admin_feeds_card, .st-key-admin_backups_card {{
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
/* Same bug, fourth column (Last active) — measured 2.4px reported against
   18.4px real content (a single-line mono-font date string), pushing its
   visual center ~7.7px below the row's true center despite the row itself
   correctly centering every OTHER column. */
[class*="st-key-admin_user_row_"] [data-testid="stColumn"]:nth-child(4) {{
  min-height: 18px !important;
}}
/* Same bug again, fifth column's "You" case specifically (the current
   user's row has no buttons, just a plain right-aligned "You" label) —
   measured ~7.7px below the row's true center, identical symptom/cause as
   Last Active. Harmless to the OTHER case this same column holds (the
   Suspend+⋯ buttons, already correctly 40px tall) since this is only a
   floor, not a fixed height. */
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

/* ── Feed toggle — recolor Streamlit's default switch to the design's
   teal-when-on pill instead of the generic red/gray default. DOM order is
   track-div, then <input>, then the label-text div (confirmed live via
   outerHTML) — the checked input has no LATER sibling that's the track, so
   `input:checked + div` (which was tried first) silently matched nothing;
   `:has()` targeting the track from its checked-input DESCENDANT sibling is
   what actually works. */
[class*="st-key-admin_feed_row_"] [data-testid="stCheckbox"] label > div:first-child {{
  background-color: var(--panel-2) !important; border-color: var(--line) !important;
}}
[class*="st-key-admin_feed_row_"] [data-testid="stCheckbox"] label:has(input:checked) > div:first-child {{
  background-color: var(--teal) !important; border-color: var(--teal) !important;
}}

/* ── Role select / search input — dark panel-2 fields matching every other
   page's input treatment instead of Streamlit's default light chrome. ── */
[class*="st-key-admin_user_row_"] [data-testid="stSelectbox"] > div,
.st-key-admin_topbar ~ * [data-testid="stTextInput"] > div,
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) > div {{
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
   browser/environment. */
[class*="st-key-admin_user_row_"] [data-testid="stSelectbox"] > div > div,
.st-key-admin_topbar ~ * [data-testid="stTextInput"] > div > div,
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) > div > div {{
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
[class*="st-key-admin_user_row_"] [data-testid="stSelectbox"] > div > div {{
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
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) input {{
  color: var(--text) !important;
}}
div[data-testid="stTextInput"]:has(input[aria-label="Search users…"]) input::placeholder {{
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
                elif _section == "feeds":
                    _render_feeds()
                else:
                    _render_backups(_u.email)
