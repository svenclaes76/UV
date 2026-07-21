"""Settings page — Display, Screening & veto rules, Alerts & data, matching
the Uvalu.dc.html mockup's Settings screen (bordered/shadowed panel per
section, uppercase header row, hairline-divided setting rows). User
management and Backups moved to the Admin portal (Phase 4); the per-exchange
picker moves there too as "Data feeds". Import/Export are per-user portfolio
ops (not admin-scoped, not shown in the mockup) and stay here.

Every control saves immediately on change (matching the mockup, which has no
Save button anywhere) — an earlier version of this page kept explicit Save
buttons on Screening/Alerts since those values are shared across every user
or need a screener-cache clear, but Sven asked for instant-apply everywhere
instead; each control below compares its new value against the persisted one
and only writes + reruns when it actually changed, so dragging a slider
without releasing on a new value doesn't spam disk writes."""
import traceback

import pandas as pd
import streamlit as st

from backup import export_zip, export_excel, import_zip, backup_filename
from portfolio import parse_excel, user_data_dir, save_portfolio, save_sold, save_div_hist
from settings import load_shared_settings, save_shared_settings, load_settings, save_settings
from uvalu import nav as nav_registry
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user, theme_colors
from uvalu.shell import _display_name, _initials, set_theme_script


def _row_header(label: str) -> None:
    st.markdown(f'<div style="padding:15px 20px;border-bottom:0.5px solid var(--line-2);font-size:13px;'
               f'font-weight:600;letter-spacing:0.03em;text-transform:uppercase;color:var(--faint);">'
               f'{label}</div>', unsafe_allow_html=True)


def _row_desc(text: str) -> None:
    st.markdown(f'<div style="padding:10px 20px 2px;font-size:12px;color:var(--muted);">{text}</div>',
               unsafe_allow_html=True)


def _row_title(title: str, desc: str) -> None:
    st.markdown(f'<div><div style="font-size:13.5px;font-weight:500;">{title}</div>'
               f'<div style="font-size:12px;color:var(--muted);margin-top:2px;">{desc}</div></div>',
               unsafe_allow_html=True)


def _slider_label(label: str, value_str: str) -> None:
    st.markdown(f'<div style="display:flex;align-items:baseline;justify-content:space-between;'
               f'margin-bottom:9px;"><span style="font-size:13px;font-weight:500;">{label}</span>'
               f'<span style="font-family:var(--uv-mono);font-size:13px;color:var(--mint);">{value_str}</span>'
               f'</div>', unsafe_allow_html=True)


def render() -> None:
    _u = current_user()
    _email = _u.email
    _s = load_settings(_email)
    _shared = load_shared_settings()

    _dash_page = nav_registry.pages.get("dashboard")
    if _dash_page is not None and st.button("← Back", key="set_back", type="tertiary"):
        st.switch_page(_dash_page)

    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Settings</div>',
               unsafe_allow_html=True)
    st.caption("Display preferences, screening thresholds and alerts. Changes apply immediately.")

    # ── Display ────────────────────────────────────────────────────────────────
    with st.container(key="set_card_display", border=True):
        _row_header("Display")

        with st.container(key="set_row_theme"):
            _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
            with _c1:
                _row_title("Theme", "Deep-navy dark or surface-white light.")
            with _c2:
                _light = theme_colors().effective_light
                _cur_theme = "Light" if _light else "Dark"
                _theme_sel = st.segmented_control(
                    "Theme", options=["Dark", "Light"], default=_cur_theme,
                    label_visibility="collapsed", key="set_theme_seg")
                if _theme_sel and _theme_sel != _cur_theme:
                    set_theme_script(_theme_sel)

        with st.container(key="set_row_currency"):
            _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
            with _c1:
                _row_title("Display currency", "Reporting currency for values and P&amp;L.")
            with _c2:
                st.segmented_control("Currency", options=["EUR"], default="EUR", disabled=True,
                                     label_visibility="collapsed", key="set_currency_seg")

        with st.container(key="set_row_numfmt"):
            _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
            with _c1:
                _row_title("Number format", "Decimal and thousands separators.")
            with _c2:
                st.segmented_control("Format", options=["1,234.56"], default="1,234.56", disabled=True,
                                     label_visibility="collapsed", key="set_numfmt_seg")

    # ── Screening & veto rules ───────────────────────────────────────────────────
    with st.container(key="set_card_screening", border=True):
        _row_header("Screening &amp; veto rules")
        _row_desc("These drive every BUY/MONITOR/AVOID decision across the app — Screener, "
                 "Watchlist, Dashboard, Portfolio and Analysis all read the same values.")

        with st.container(key="set_slider_grid"):
            _v1, _v2 = st.columns(2, gap="large")
            with _v1:
                _de_default = int(_shared.get("max_debt_equity", 500))
                _slider_label("Max debt / equity",
                              f'{st.session_state.get("scr_max_de", _de_default)}%')
                _max_de = st.slider("Max debt / equity (%)", 50, 1000, _de_default, step=50,
                                    key="scr_max_de", label_visibility="collapsed")
                st.caption("Hard veto above this leverage.")
            with _v2:
                _payout_default = int(_shared.get("max_payout", 90))
                _slider_label("Max dividend payout",
                              f'{st.session_state.get("scr_max_payout", _payout_default)}%')
                _max_payout = st.slider("Max dividend payout (%)", 50, 100, _payout_default, step=5,
                                        key="scr_max_payout", label_visibility="collapsed")
                st.caption("Flag dividends above this payout.")

            _v3, _v4 = st.columns(2, gap="large")
            with _v3:
                _mos_default = int(_shared.get("min_mos", 0))
                _mos_cur = st.session_state.get("scr_min_mos", _mos_default)
                _slider_label("Target margin of safety", f'{"+" if _mos_cur >= 0 else ""}{_mos_cur}%')
                _min_mos = st.slider("Target margin of safety (%)", -20, 50, _mos_default, step=5,
                                     key="scr_min_mos", label_visibility="collapsed")
                st.caption("Discount to fair value required for a BUY.")
            with _v4:
                _buy_default = int(_shared.get("buy_threshold", 70))
                _slider_label("BUY score threshold",
                              str(st.session_state.get("scr_buy_thr", _buy_default)))
                _buy_thr = st.slider("BUY score threshold", 50, 90, _buy_default, step=5,
                                     key="scr_buy_thr", label_visibility="collapsed")
                st.caption("Composite score required for a BUY signal.")

        with st.container(key="set_row_stoxx"):
            _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
            with _c1:
                _row_title("Benchmark — Euro Stoxx 50", "Overlay on the portfolio value chart.")
            with _c2:
                _stoxx = st.toggle("Benchmark — Euro Stoxx 50",
                                   value=bool(_shared.get("benchmark_stoxx", False)), key="scr_stoxx",
                                   label_visibility="collapsed")

        with st.container(key="set_row_us"):
            _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
            with _c1:
                _row_title("Include US-listed names", "Extend the screener beyond European exchanges.")
            with _c2:
                st.toggle("Include US-listed names", value=False, disabled=True, key="scr_us",
                         label_visibility="collapsed")

        # Save immediately, one field at a time — only the field the user
        # actually just touched differs from the persisted value, so at most
        # one of these five fires on a given rerun.
        _veto_changed = (
            _max_de     != _shared.get("max_debt_equity", 500) or
            _max_payout != _shared.get("max_payout", 90) or
            _min_mos    != _shared.get("min_mos", 0) or
            _buy_thr    != _shared.get("buy_threshold", 70)
        )
        if _veto_changed:
            _shared["max_debt_equity"] = float(_max_de)
            _shared["max_payout"]      = float(_max_payout)
            _shared["min_mos"]         = float(_min_mos)
            _shared["buy_threshold"]   = float(_buy_thr)
            save_shared_settings(_shared)
            _load_all_screener_data.clear()
            st.rerun()
        elif _stoxx != bool(_shared.get("benchmark_stoxx", False)):
            _shared["benchmark_stoxx"] = bool(_stoxx)
            save_shared_settings(_shared)
            st.rerun()

    # ── Alerts & data ────────────────────────────────────────────────────────────
    with st.container(key="set_card_alerts", border=True):
        _row_header("Alerts &amp; data")
        _row_desc("Stored as preferences — no email/push delivery exists yet, so these don't send anything.")

        _notif_rows = [
            ("alert_buy_signal",       "New BUY signal",       "A held or watchlisted stock crosses into BUY."),
            ("alert_avoid_signal",     "New AVOID signal",     "A held stock crosses into AVOID."),
            ("alert_dividend_ex_date", "Upcoming ex-dividend", "A held stock's ex-dividend date is within 7 days."),
            ("alert_price_target",     "Analyst target reached", "Price crosses the analyst mean target."),
        ]
        _new_alert_vals = {}
        for _key, _title, _desc in _notif_rows:
            with st.container(key=f"set_row_{_key}"):
                _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
                with _c1:
                    _row_title(_title, _desc)
                with _c2:
                    _new_alert_vals[_key] = st.toggle(_title, value=bool(_s.get(_key, False)),
                                                      key=f"disp_{_key}", label_visibility="collapsed")

        with st.container(key="set_row_refresh"):
            _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
            with _c1:
                _row_title("Price refresh interval", "How often quotes update during market hours.")
            with _c2:
                _refresh_opts = [30, 60, 300, 900]
                _refresh_fmt = lambda s: f"{s}s" if s < 60 else f"{s // 60} min"
                _cur_refresh = _s.get("refresh_interval_s", 60)
                _refresh_idx = _refresh_opts.index(_cur_refresh) if _cur_refresh in _refresh_opts else 1
                st.markdown(f'<div style="text-align:right;font-family:var(--uv-mono);font-size:13px;'
                           f'color:var(--mint);margin-bottom:6px;">'
                           f'{_refresh_fmt(st.session_state.get("disp_refresh_interval", _refresh_opts[_refresh_idx]))}'
                           f'</div>', unsafe_allow_html=True)
                _new_refresh = st.select_slider(
                    "Price refresh interval", options=_refresh_opts,
                    value=_refresh_opts[_refresh_idx],
                    format_func=_refresh_fmt,
                    key="disp_refresh_interval", label_visibility="collapsed")

        _alerts_changed = any(_new_alert_vals[k] != bool(_s.get(k, False)) for k in _new_alert_vals)
        if _alerts_changed:
            _s.update(_new_alert_vals)
            save_settings(_s, _email)
            st.rerun()
        elif int(_new_refresh) != _cur_refresh:
            _s["refresh_interval_s"] = int(_new_refresh)
            save_settings(_s, _email)
            st.rerun()

    # ── Import / Export (per-user, not admin-scoped) ─────────────────────────────
    with st.container(key="set_card_import", border=True):
        _row_header("Import &amp; export")

        _imp_col, _exp_col = st.columns(2, gap="large")
        with _imp_col:
            with st.container(key="set_import_body"):
                st.markdown('<div style="font-size:13.5px;font-weight:500;">Import portfolio</div>'
                           '<div style="font-size:12px;color:var(--muted);margin-top:2px;">Upload an Excel '
                           'file to import positions, sold history and dividends. This replaces all existing '
                           'portfolio data for this account.</div>', unsafe_allow_html=True)
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
            with st.container(key="set_export_body"):
                st.markdown('<div style="font-size:13.5px;font-weight:500;">Excel export</div>'
                           '<div style="font-size:12px;color:var(--muted);margin-top:2px;">Human-readable '
                           'workbook with positions, dividends, sold history and watchlist. Useful for '
                           'inspection or migration.</div>', unsafe_allow_html=True)
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

    # ── Account footer ─────────────────────────────────────────────────────────
    # One raw-HTML flex row (not st.columns) — there are no interactive
    # widgets here, and Streamlit's per-column wrapper/vertical_alignment
    # centering proved unreliable for mismatched-height siblings (confirmed
    # live: an 8px offset between the avatar square and the Sign out pill
    # persisted even after forcing align-items:center and matching explicit
    # heights). A single native CSS flex row centers all three exactly.
    with st.container(key="set_account_footer"):
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<div style="width:38px;height:38px;border-radius:9px;background:var(--navy);'
            f'border:0.5px solid var(--line);display:flex;align-items:center;justify-content:center;'
            f'font-size:13px;font-weight:600;color:var(--mint);flex:none;">{_initials(_email)}</div>'
            f'<div style="flex:1;"><div style="font-size:13.5px;font-weight:500;">{_display_name(_email)}</div>'
            f'<div style="font-size:12px;color:var(--faint);font-family:var(--uv-mono);">'
            f'{_email} · {_u.role.capitalize()}</div></div>'
            f'<a href="/?logout=1" target="_self" class="uv-set-signout">Sign out</a>'
            f'</div>', unsafe_allow_html=True)
