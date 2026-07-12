"""Settings page — Display, Screening & veto rules, Alerts & data, matching
the Uvalu.dc.html mockup. User management and Backups moved to the Admin
portal (Phase 4); the per-exchange picker moves there too as "Data feeds".
Import/Export are per-user portfolio ops (not admin-scoped, not shown in the
mockup) and stay here."""
import traceback

import pandas as pd
import streamlit as st

from backup import export_zip, export_excel, import_zip, backup_filename
from portfolio import parse_excel, user_data_dir, save_portfolio, save_sold, save_div_hist
from settings import load_shared_settings, save_shared_settings, load_settings, save_settings
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user, theme_colors


def render() -> None:
    _u = current_user()
    _email = _u.email
    _s = load_settings(_email)
    _shared = load_shared_settings()

    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Settings</div>',
               unsafe_allow_html=True)
    st.caption("Display preferences, screening thresholds and alerts. Changes apply immediately.")

    # ── Display ────────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### Display")

        _d1, _d2 = st.columns(2)
        with _d1:
            st.markdown("**Theme**")
            st.caption("Deep-navy dark or surface-white light.")
            _light = theme_colors().effective_light
            st.segmented_control("Theme", options=["Light", "Dark"],
                                 default="Light" if _light else "Dark",
                                 disabled=True, label_visibility="collapsed", key="disp_theme_ro")
            st.caption("Follows Streamlit's own theme — change it via the app menu "
                      "(top-right **⋮ → Settings → Theme**).")
        with _d2:
            st.markdown("**Table density**")
            st.caption("Row height for card-based lists (e.g. Dashboard holdings).")
            _density_sel = st.segmented_control(
                "Density", options=["Comfortable", "Compact"],
                default=_s.get("density", "comfortable").capitalize(),
                label_visibility="collapsed", key="disp_density")
            if _density_sel and _density_sel.lower() != _s.get("density", "comfortable"):
                _s["density"] = _density_sel.lower()
                save_settings(_s, _email)
                st.rerun()
            st.caption("Native data tables use a fixed row height and aren't affected.")

        _d3, _d4 = st.columns(2)
        with _d3:
            st.markdown("**Display currency**")
            st.caption("Reporting currency for values and P&L.")
            st.segmented_control("Currency", options=["EUR"], default="EUR", disabled=True,
                                 label_visibility="collapsed", key="disp_currency_ro")
            st.caption("EUR only for now.")
        with _d4:
            st.markdown("**Number format**")
            st.caption("Decimal and thousands separators.")
            st.segmented_control("Format", options=["1,234.56"], default="1,234.56", disabled=True,
                                 label_visibility="collapsed", key="disp_numfmt_ro")
            st.caption("Not yet configurable.")

    # ── Screening & veto rules ───────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### Screening & veto rules")
        st.caption("These drive every BUY/MONITOR/AVOID decision across the app — "
                  "Screener, Watchlist, Dashboard, Portfolio and Analysis all read the same values.")

        _v1, _v2 = st.columns(2)
        with _v1:
            _max_de = st.slider("Max debt / equity (%)", 50, 1000,
                                int(_shared.get("max_debt_equity", 500)), step=50, key="scr_max_de")
            st.caption("Hard veto above this leverage.")
        with _v2:
            _max_payout = st.slider("Max dividend payout (%)", 50, 100,
                                    int(_shared.get("max_payout", 90)), step=5, key="scr_max_payout")
            st.caption("Flag dividends above this payout.")

        _v3, _v4 = st.columns(2)
        with _v3:
            _min_mos = st.slider("Target margin of safety (%)", -20, 50,
                                 int(_shared.get("min_mos", 0)), step=5, key="scr_min_mos")
            st.caption("Discount to fair value required for a BUY.")
        with _v4:
            _buy_thr = st.slider("BUY score threshold", 50, 90,
                                 int(_shared.get("buy_threshold", 70)), step=5, key="scr_buy_thr")
            st.caption("Composite score required for a BUY signal.")

        st.divider()
        _stoxx = st.toggle("Benchmark — Euro Stoxx 50",
                           value=bool(_shared.get("benchmark_stoxx", False)), key="scr_stoxx",
                           help="Default state of the overlay checkbox on the Dashboard's value chart.")
        st.toggle("Include US-listed names", value=False, disabled=True, key="scr_us",
                 help="Coming soon — no US ticker universe exists yet.")

        if st.button("Save", type="primary", key="btn_save_veto"):
            _shared["max_debt_equity"] = float(_max_de)
            _shared["max_payout"]      = float(_max_payout)
            _shared["min_mos"]         = float(_min_mos)
            _shared["buy_threshold"]   = float(_buy_thr)
            _shared["benchmark_stoxx"] = bool(_stoxx)
            save_shared_settings(_shared)
            _load_all_screener_data.clear()
            st.success("Saved — screener results updated.")
            st.rerun()

    # ── Alerts & data ────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### Alerts & data")
        st.caption("Stored as preferences — no email/push delivery exists yet, so these don't send anything.")

        _notif_rows = [
            ("alert_buy_signal",       "New BUY signal",     "A held or watchlisted stock crosses into BUY."),
            ("alert_avoid_signal",     "New AVOID signal",   "A held stock crosses into AVOID."),
            ("alert_dividend_ex_date", "Upcoming ex-dividend", "A held stock's ex-dividend date is within 7 days."),
            ("alert_price_target",     "Analyst target reached", "Price crosses the analyst mean target."),
        ]
        _new_alert_vals = {}
        for _key, _title, _desc in _notif_rows:
            _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
            with _c1:
                st.markdown(f"**{_title}**")
                st.caption(_desc)
            with _c2:
                _new_alert_vals[_key] = st.toggle(_title, value=bool(_s.get(_key, False)),
                                                  key=f"disp_{_key}", label_visibility="collapsed")

        st.divider()
        _refresh_opts = [30, 60, 300, 900]
        _cur_refresh = _s.get("refresh_interval_s", 60)
        _refresh_idx = _refresh_opts.index(_cur_refresh) if _cur_refresh in _refresh_opts else 1
        _new_refresh = st.select_slider(
            "Price refresh interval", options=_refresh_opts,
            value=_refresh_opts[_refresh_idx],
            format_func=lambda s: f"{s}s" if s < 60 else f"{s // 60} min",
            key="disp_refresh_interval",
            help="How often the Portfolio page checks for new prices while open.")

        if st.button("Save", type="primary", key="btn_save_alerts"):
            _s.update(_new_alert_vals)
            _s["refresh_interval_s"] = int(_new_refresh)
            save_settings(_s, _email)
            st.success("Saved.")
            st.rerun()

    st.divider()

    # ── Import / Export (per-user, not admin-scoped) ─────────────────────────────
    with st.container(border=True):
        st.markdown("##### Import & export")

        _imp_col, _exp_col = st.columns(2, gap="large")
        with _imp_col:
            st.markdown("**Import portfolio**")
            st.caption("Upload an Excel file to import positions, sold history and dividends. "
                      "This replaces all existing portfolio data for this account.")
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

        with _exp_col:
            st.markdown("**Excel export**")
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
