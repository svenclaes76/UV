"""Settings page — user admin, screener config, import/export/backup."""
import traceback

import pandas as pd
import streamlit as st

from auth import register, list_users, set_role, delete_user, ROLES
from backup import export_zip, export_excel, import_zip, backup_filename
from portfolio import (parse_excel, user_data_dir, save_portfolio, save_sold,
                       save_div_hist)
from settings import (load_shared_settings, save_shared_settings,
                      ALL_EXCHANGES, EXCHANGE_LABELS)
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user


@st.dialog("Add user", width="large")
def _dlg_add_user():
    _c1, _c2, _c3 = st.columns([3, 3, 2])
    with _c1:
        new_email = st.text_input("Email")
    with _c2:
        new_password = st.text_input("Password", type="password")
    with _c3:
        new_role_sel = st.selectbox("Role", options=list(ROLES))
    _, _save_col = st.columns([3, 1])
    with _save_col:
        if st.button("Save", key="dlg_add_user_save", width="stretch"):
            ok, msg = register(new_email, new_password, role=new_role_sel)
            if ok:
                st.rerun()
            else:
                st.error(msg)


@st.dialog("Edit users", width="large")
def _dlg_edit_user(users: list[dict]):
    current_email = st.session_state.get("user_email", "")
    _tbl = pd.DataFrame([
        {
            "🗑️":      False,
            "Email":   u["email"],
            "Role":    u["role"],
            "Created": u["created_at"][:10],
        }
        for u in users
    ])

    _row_h  = 35
    _header = 35
    _height = _header + min(len(_tbl), 8) * _row_h

    _edited = st.data_editor(
        _tbl,
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        height=_height,
        column_config={
            "🗑️":      st.column_config.CheckboxColumn("🗑️",    width=55),
            "Email":   st.column_config.TextColumn("Email",    disabled=True, pinned=True),
            "Role":    st.column_config.SelectboxColumn("Role", options=list(ROLES)),
            "Created": st.column_config.TextColumn("Created",  disabled=True),
        },
        key="dlg_edit_user_table",
    )

    to_delete  = _edited[_edited["🗑️"]].index.tolist()
    to_keep    = _edited[~_edited["🗑️"]]
    n_selected = len(to_delete)

    _del_note, _save_col = st.columns([3, 1])
    with _del_note:
        if n_selected:
            st.caption(f"{n_selected} selected for deletion")
    with _save_col:
        if st.button("Save", key="dlg_edit_user_save", width="stretch"):
            for _, row in to_keep.iterrows():
                set_role(row["Email"], row["Role"])
            for i in to_delete:
                email = _tbl.iloc[i]["Email"]
                if email != current_email:
                    delete_user(email)
            st.rerun()


def _render_admin_users():
    """User management UI — rendered inside the Settings page."""
    st.subheader("User management")
    st.caption("Add, edit, or remove user accounts. The first account created is automatically assigned the admin role.")
    users = list_users()

    _u1, _u2, _ = st.columns([1, 1, 6], gap="small")
    with _u1:
        if st.button("Add", key="btn_add_user"):
            _dlg_add_user()
    with _u2:
        if st.button("Edit", key="btn_edit_user", disabled=not users):
            _dlg_edit_user(users)

    if not users:
        st.info("No users found.")
        return

    _row_h  = 35
    _header = 38
    _height = min(_header + len(users) * _row_h + 4, 600)

    user_df = pd.DataFrame([
        {
            "Email":      u["email"],
            "Role":       u["role"],
            "Created":    u["created_at"][:10],
        }
        for u in users
    ])
    st.dataframe(
        user_df,
        width="stretch",
        hide_index=True,
        height=_height,
        column_config={
            "Email":   st.column_config.TextColumn("Email",   pinned=True),
            "Role":    st.column_config.TextColumn("Role"),
            "Created": st.column_config.TextColumn("Created"),
        },
    )


def render() -> None:
    _u = current_user()
    _email, _is_admin = _u.email, _u.is_admin
    if _is_admin:
        tab_admin, tab_screener, tab_backup, tab_import, tab_export, tab_appearance = st.tabs(["Users", "Screener", "Backup & Restore", "Import", "Export", "Appearance"])
    else:
        tab_export, tab_appearance = st.tabs(["Export", "Appearance"])

    if _is_admin:
        with tab_admin:
            _render_admin_users()

        with tab_import:
            st.subheader("Import portfolio")
            st.caption("Upload an Excel file to import positions, sold history and dividends. "
                       "This will replace all existing portfolio data for this account.")
            _imp_file = st.file_uploader("Choose your portfolio .xlsx file", type=["xlsx"], key="imp_portfolio")
            if _imp_file:
                with st.spinner("Parsing Excel…"):
                    try:
                        _imp_pf, _imp_sold, _imp_div = parse_excel(_imp_file)
                        if _imp_pf.empty:
                            st.error("No open EBR:/AMS:/EPA:/BIT:/ETR:/SWX: positions found. Check that your file matches the expected format.")
                        else:
                            _udir = user_data_dir(_email)
                            (_udir / "portfolio.json").unlink(missing_ok=True)
                            (_udir / "sold.json").unlink(missing_ok=True)
                            (_udir / "dividends_history.json").unlink(missing_ok=True)
                            save_portfolio(_imp_pf)
                            save_sold(_imp_sold)
                            save_div_hist(_imp_div)
                            st.success(f"Imported {len(_imp_pf)} open, {len(_imp_sold)} sold, {len(_imp_div)} dividend records.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Could not parse file: {e}")
                        st.code(traceback.format_exc())

    with tab_export:
        st.subheader("Excel export")
        st.caption("Human-readable workbook with positions, dividends, "
                   "sold history and watchlist. Useful for inspection or migration.")
        try:
            xls_bytes = export_excel()
            st.download_button(
                "Download backup.xlsx",
                data=xls_bytes,
                file_name=backup_filename("xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except ValueError:
            st.info("Your portfolio is empty. Add positions in the Portfolio section first, then come back to export.")
        except Exception as e:
            st.error(f"Could not create Excel: {e}")

    if _is_admin:
      with tab_screener:
        st.subheader("Screener selection")
        st.caption("Choose which exchanges are included in the screener and portfolio analysis.")
        _cur_settings = load_shared_settings()
        _cur_enabled  = set(_cur_settings.get("enabled_exchanges", ALL_EXCHANGES))
        _new_enabled: list[str] = []
        for _exkey, _exlabel in sorted(EXCHANGE_LABELS.items(), key=lambda x: x[1]):
            if st.checkbox(_exlabel, value=_exkey in _cur_enabled, key=f"scr_exch_{_exkey}"):
                _new_enabled.append(_exkey)
        if st.button("Save", key="btn_save_screener_settings", type="primary"):
            if not _new_enabled:
                st.error("At least one exchange must be enabled.")
            else:
                _cur_settings["enabled_exchanges"] = _new_enabled
                save_shared_settings(_cur_settings)
                _load_all_screener_data.clear()
                st.success("Screener settings saved.")
                st.rerun()

    if _is_admin:
      with tab_backup:
        st.subheader("Encrypted backup (ZIP)")
        st.caption("Bundles all user data and the encryption key. "
                   "Required for a full restore on another machine.")
        try:
            zip_bytes = export_zip(_email)
            st.download_button(
                "Download backup.zip",
                data=zip_bytes,
                file_name=backup_filename("zip"),
                mime="application/zip",
            )
        except Exception as e:
            st.error(f"Could not create ZIP: {e}")

        st.divider()
        st.subheader("Restore from ZIP")
        st.warning("Restoring will **overwrite** your current data. "
                   "Download a backup first if you want to keep it.", icon="⚠️")
        uploaded = st.file_uploader("Upload a backup ZIP", type="zip",
                                    key="backup_restore_upload")
        if uploaded:
            if st.button("Restore", type="primary", key="btn_restore"):
                try:
                    restored = import_zip(uploaded.read(), _email)
                    st.success(f"Restored: {', '.join(restored)}")
                    st.cache_data.clear()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


    with tab_appearance:
        st.subheader("Appearance")
        st.caption("The theme follows your system preference. To override it, open the "
                   "app menu (top-right **⋮ → Settings → Theme**) and pick Light or Dark.")
