"""Streamlit web app — Euronext Brussels value screener + portfolio tracker."""

import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import streamlit as st

from prices import fetch_prices
from backup import export_zip, export_excel, import_zip, backup_filename

from fetch_tickers import (fetch_brussels_tickers, fetch_amsterdam_tickers,
                            fetch_paris_tickers, fetch_milan_tickers,
                            fetch_frankfurt_tickers, fetch_swiss_tickers,
                            _hardcoded_bel20, _hardcoded_aex25, _hardcoded_cac40,
                            _hardcoded_ftse_mib, _hardcoded_dax40, _hardcoded_smi20)
from screener import (CACHE_FILE, CACHE_TTL_HOURS, _load_cache,
                      run_screener_from_df, fetch_fundamentals_nowait,
                      get_fetch_progress, cancel_background_fetch,
                      clear_live_cache, _file_lock)
import risk as _risk_module
from settings import (load_shared_settings, save_shared_settings,
                      ALL_EXCHANGES, EXCHANGE_LABELS)
from portfolio import (parse_excel, save_portfolio, save_sold, save_div_hist,
                       load_portfolio, load_sold, load_div_hist,
                       add_position, remove_positions, update_positions,
                       sell_position,
                       add_dividend, update_div_hist,
                       save_watchlist, load_watchlist, save_manual_tickers, load_manual_tickers,
                       set_user, user_data_dir, portfolio_exists,
                       load_value_history, record_value_snapshot, backfill_value_history)
from auth import register, login, verify_token, list_users, set_role, delete_user, ROLES

from uvalu import authgate, nav, styles
from uvalu.data import (_bust_cache, _cache_age_str, _cache_version,
                        _load_all_screener_data, _compute_fair_values,
                        _fetch_prices_cached, _fetch_fundamentals, _fetch_live_data)
from uvalu.formatting import (COLUMN_HELP, _HINT_WATCHLIST,
                              fmt_eur as _fmt_eur, fmt_div_flag as _fmt_div_flag,
                              safe_pct as _safe_pct)
from uvalu.runtime import theme_colors, current_user
from uvalu.stock_dialog import _dlg_stock_detail
from uvalu.pages_ import (help as _page_help_mod, settings as _page_settings_mod,
                          dashboard as _page_dashboard_mod, risk as _page_risk_mod)
from uvalu.ui import (_CHART_CONFIG, _DONUT_PALETTE, _row_select_table, _auto_rerun,
                      _static_bar, _donut_chart, _hm_color)

from contextlib import contextmanager

# ── Page config ───────────────────────────────────────────────────────────────

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

# ── Per-run user + theme state (see uvalu.runtime) ────────────────────────────
_u            = current_user()
_email        = _u.email
_current_role = _u.role
_is_admin     = _u.is_admin
set_user(_email)

# Shared chart palette tokens — resolved once, used in every Plotly figure
_C = theme_colors()
_ui_effective_light = _C.effective_light
_c_axis     = _C.axis
_c_grid     = _C.grid
_c_invested = _C.invested
_c_text     = _C.text
_c_surface  = _C.surface

authgate.auth_wall()

# ── Sidebar navigation ────────────────────────────────────────────────────────
# Rendered at the end of the script via st.navigation + st.page_link, once the
# page functions below are defined.

# Keep localStorage token fresh.
st.iframe(f"""
<script>
(function(){{
  var tok = {repr(st.session_state.get('jwt_token', ''))};
  if (tok) localStorage.setItem('uv_jwt', tok);
}})();
</script>
""", height=1)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — VALUE SCREENER
# ══════════════════════════════════════════════════════════════════════════════

# ── Shared cell formatters ──────────────────────────────────────────────────
_f_str  = lambda v: v                if pd.notna(v) else "—"

watchlist = load_watchlist()

def _page_screener() -> None:
    _settings = load_shared_settings()
    _enabled  = tuple(_settings.get("enabled_exchanges", ALL_EXCHANGES))
    _manual_tickers_map  = load_manual_tickers()
    _manual_ticker_keys  = tuple(_manual_tickers_map.keys())
    _manual_ticker_names = tuple(_manual_tickers_map.values())
    df, df_ams, df_par, df_mil, df_etr, df_swx, _scr_extra_df = _load_all_screener_data(
        _cache_version(), _enabled, _manual_ticker_keys, _manual_ticker_names)
    if not df.empty and ("fair_value" not in df.columns or "Decision" not in df.columns):
        _bust_cache()

    _any_data = any(not d.empty for d in [df, df_ams, df_par, df_mil, df_etr, df_swx])

    _prog = get_fetch_progress()
    if _prog["running"] and _prog["total"] > 0:
        _pct = _prog["done"] / _prog["total"]
        st.caption(f"🔄 Updating data… {_prog['done']}/{_prog['total']} tickers ({int(_pct*100)}%)")
        _auto_rerun(5, "screener_fetch_refresh")
    elif not _any_data:
        _auto_rerun(5, "screener_fetch_refresh")

    watchlist = load_watchlist()

    # ── Portfolio fit context (sector/country/beta weights from current portfolio) ──
    _scr_pf_context: dict | None = None
    _scr_pf = load_portfolio()
    if _scr_pf is not None and not _scr_pf.empty:
        # Look up sector/country/price for every portfolio position directly from
        # the app's own fundamentals cache — covers all tickers ever fetched, not
        # just those in the current screener exchange lists.
        _fund_cache = _load_cache()
        _suffix_to_country = {
            ".BR": "Belgium", ".AS": "Netherlands", ".PA": "France",
            ".MI": "Italy",   ".DE": "Germany",     ".SW": "Switzerland",
        }
        _pf_m = _scr_pf.copy()
        for _col in ("sector", "country", "Price"):
            _pf_m[_col] = None
        for _idx, _prow in _pf_m.iterrows():
            _tick = str(_prow.get("ticker", ""))
            _cached = _fund_cache.get(_tick, {})
            _pf_m.at[_idx, "sector"]  = _cached.get("sector") or None
            _pf_m.at[_idx, "country"] = _cached.get("country") or None
            _pf_m.at[_idx, "Price"]   = _cached.get("Price") or None
        # Infer country from exchange suffix as final fallback
        _missing_country = _pf_m["country"].isna()
        if _missing_country.any():
            _pf_m.loc[_missing_country, "country"] = _pf_m.loc[_missing_country, "ticker"].apply(
                lambda t: next((c for s, c in _suffix_to_country.items() if str(t).endswith(s)), None)
            )

        # Market value: shares × current price from cache, fallback to purchase_value / purchase_price
        _pf_m["_val"] = (
            pd.to_numeric(_pf_m["shares"], errors="coerce") *
            pd.to_numeric(_pf_m["Price"], errors="coerce")
        )
        # Fill missing market values with purchase_value or shares × purchase_price
        _missing_val = _pf_m["_val"].isna()
        if _missing_val.any():
            if "purchase_value" in _pf_m.columns:
                _pf_m.loc[_missing_val, "_val"] = pd.to_numeric(
                    _pf_m.loc[_missing_val, "purchase_value"], errors="coerce"
                )
            _still_missing = _pf_m["_val"].isna()
            if _still_missing.any() and "purchase_price" in _pf_m.columns:
                _pf_m.loc[_still_missing, "_val"] = (
                    pd.to_numeric(_pf_m.loc[_still_missing, "shares"], errors="coerce") *
                    pd.to_numeric(_pf_m.loc[_still_missing, "purchase_price"], errors="coerce")
                )
        _pf_total = _pf_m["_val"].sum()
        if _pf_total > 0:
            _scr_pf_context = {
                "total": _pf_total,
                "sector_weights": (
                    _pf_m[_pf_m["sector"].notna()].groupby("sector")["_val"].sum() / _pf_total
                    if "sector" in _pf_m.columns else pd.Series(dtype=float)
                ),
                "country_weights": (
                    _pf_m[_pf_m["country"].notna()].groupby("country")["_val"].sum() / _pf_total
                    if "country" in _pf_m.columns else pd.Series(dtype=float)
                ),
                "portfolio_beta": (
                    (pd.to_numeric(_pf_m["beta"], errors="coerce") * _pf_m["_val"]).sum() / _pf_total
                    if "beta" in _pf_m.columns else float("nan")
                ),
            }

    # ── Column groups ─────────────────────────────────────────────────────────
    # Core columns always shown; extra groups toggled via multiselect
    # fmt=None → keep the raw (numeric) value; formatting is done by the
    # column_config NumberColumn so sorting stays numeric.
    CORE_COLS = {
        "★":              (None,              None),
        "Company":        ("Name",            None),
        "Ticker":         ("Ticker",          None),
        "Price":          ("Price",           None),
        "Analyst Target": ("targetMeanPrice", None),
        "UV":             ("fair_value",      None),
        "MoS %":          ("MoS %",           None),
        "TER %":          ("TER %",           None),
        "Score":          (None,              None),   # built row-by-row below from Decision + Value Score
    }

    EXTRA_GROUPS = {
        "Valuation models": {
            "Graham #":      ("graham_number",  None),
            "PE Fair Val":   ("pe_fair_value",  None),
            "EPV":           ("epv",            None),
            "DDM (1-stage)": ("ddm",            None),
            "DDM (2-stage)": ("ddm_multistage", None),
        },
        "Risk": {
            "Risk Score":  ("Risk Score",        None),
            "Beta":        ("beta",              None),
            "Debt/Equity": ("debtToEquity",      None),
            "Mkt Cap":     ("Market Cap",        None),
        },
        "Multiples": {
            "P/E":       ("trailingPE",         None),
            "P/B":       ("priceToBook",        None),
            "EV/EBITDA": ("enterpriseToEbitda", None),
        },
        "Quality": {
            "ROE %":       ("returnOnEquity",   None),
            "ROA %":       ("returnOnAssets",   None),
            "Op Margin %": ("operatingMargins", None),
            "FCF Yield %": ("fcfYield",         None),
        },
        "Growth": {
            "Rev Growth %": ("revenueGrowth",  None),
            "EPS Growth %": ("earningsGrowth", None),
        },
        "Dividends": {
            "Div Yield":     ("dividendYield",            None),
            "5yr Avg Yield": ("fiveYearAvgDividendYield", None),
            "Payout Ratio":  ("payoutRatio",              None),
            "Cash Payout":   ("cashPayoutRatio",          None),
            "Div Coverage":  ("dividendCoverage",         None),
            "Div Flag":      ("Div Flag",                 _fmt_div_flag),
            "Ex-Div Date":   ("exDividendDate",           _f_str),
            "Div Date":      ("dividendDate",             _f_str),
        },
        "Geography": {
            "Sector":  ("sector",  _f_str),
            "Country": ("country", _f_str),
        },
    }

    # Column config for every possible column — help= adds hover tooltip on header
    _ch = COLUMN_HELP.get  # shorthand
    _col_config_map = {
        **{c: st.column_config.TextColumn(c, width=100, help=_ch(c))
           for g in EXTRA_GROUPS.values() for c in g},
        "★":             st.column_config.CheckboxColumn("★",             width=55,  pinned=True, help=_ch("★")),
        "Company":       st.column_config.TextColumn(    "Company",       width=180, pinned=True, help=_ch("Company")),
        "Ticker":        st.column_config.TextColumn(    "Ticker",        width=90,  help=_ch("Ticker")),
        "Price":         st.column_config.NumberColumn(  "Price",         width=80,  format="euro",    help=_ch("Price")),
        "UV":            st.column_config.NumberColumn(  "Fair Value",    width=90,  format="euro",    help=_ch("UV")),
        "Analyst Target":st.column_config.NumberColumn(  "Analyst Target",width=110, format="euro",    help=_ch("Analyst Target")),
        "MoS %":         st.column_config.NumberColumn(  "MoS %",         width=75,  format="%+.1f%%", help=_ch("MoS %")),
        "TER %":         st.column_config.NumberColumn(  "TER %",         width=75,  format="%+.1f%%", help=_ch("TER %")),
        "Score":         st.column_config.TextColumn(    "Score",         width=110,
                             help="BUY (>70) · MONITOR (40–70) · AVOID (<40)"),
        "Graham #":      st.column_config.NumberColumn("Graham #",      width=100, format="euro", help=_ch("Graham #")),
        "PE Fair Val":   st.column_config.NumberColumn("PE Fair Val",   width=100, format="euro", help=_ch("PE Fair Val")),
        "EPV":           st.column_config.NumberColumn("EPV",           width=100, format="euro", help=_ch("EPV")),
        "DDM (1-stage)": st.column_config.NumberColumn("DDM (1-stage)", width=100, format="euro", help=_ch("DDM (1-stage)")),
        "DDM (2-stage)": st.column_config.NumberColumn("DDM (2-stage)", width=100, format="euro", help=_ch("DDM (2-stage)")),
        "Risk Score":    st.column_config.ProgressColumn("Risk Score",  width=110,
                             min_value=0, max_value=10,  format="%.1f", help=_ch("Risk Score")),
        "Mkt Cap":       st.column_config.NumberColumn(  "Mkt Cap",     width=80,  format="compact", help=_ch("Mkt Cap")),
        "Beta":          st.column_config.NumberColumn(  "Beta",        width=55,  format="%.2f",    help=_ch("Beta")),
        "Debt/Equity":   st.column_config.NumberColumn(  "Debt/Equity", width=95,  format="%.1f",    help=_ch("Debt/Equity")),
        "P/E":           st.column_config.NumberColumn(  "P/E",         width=60,  format="%.1f",    help=_ch("P/E")),
        "P/B":           st.column_config.NumberColumn(  "P/B",         width=60,  format="%.2f",    help=_ch("P/B")),
        "EV/EBITDA":     st.column_config.NumberColumn(  "EV/EBITDA",   width=90,  format="%.1f",    help=_ch("EV/EBITDA")),
        "ROE %":         st.column_config.NumberColumn("ROE %",         width=100, format="percent", help=_ch("ROE %")),
        "ROA %":         st.column_config.NumberColumn("ROA %",         width=100, format="percent", help=_ch("ROA %")),
        "Op Margin %":   st.column_config.NumberColumn("Op Margin %",   width=100, format="percent", help=_ch("Op Margin %")),
        "FCF Yield %":   st.column_config.NumberColumn("FCF Yield %",   width=100, format="percent", help=_ch("FCF Yield %")),
        "Rev Growth %":  st.column_config.NumberColumn("Rev Growth %",  width=100, format="percent", help=_ch("Rev Growth %")),
        "EPS Growth %":  st.column_config.NumberColumn("EPS Growth %",  width=100, format="percent", help=_ch("EPS Growth %")),
        "Div Yield":     st.column_config.NumberColumn("Div Yield",     width=100, format="percent", help=_ch("Div Yield")),
        "5yr Avg Yield": st.column_config.NumberColumn("5yr Avg Yield", width=100, format="percent", help=_ch("5yr Avg Yield")),
        "Payout Ratio":  st.column_config.NumberColumn("Payout Ratio",  width=100, format="percent", help=_ch("Payout Ratio")),
        "Cash Payout":   st.column_config.NumberColumn("Cash Payout",   width=100, format="percent", help=_ch("Cash Payout")),
        "Div Coverage":  st.column_config.NumberColumn("Div Coverage",  width=100, format="%.2f×",   help=_ch("Div Coverage")),
        "Sector":        st.column_config.TextColumn("Sector",      width=150),
        "Country":       st.column_config.TextColumn("Country",     width=120),
        "Ex-Div Date":   st.column_config.TextColumn("Ex-Div Date", width=105),
        "Div Date":      st.column_config.TextColumn("Div Date",    width=95),
    }

    def _render_table(tab_df, key_suffix, score_key=None, score_default=None, extra_toolbar_action=None):
        """Render the screener table with optional column groups, score filter, and sector filter."""
        _grp_key    = f"col_groups_{key_suffix}"
        _sector_key = f"sector_filter_{key_suffix}"
        _tbl_key    = f"table_{key_suffix}"

        @st.dialog("View", width="small")
        def _dlg_view():
            _sel = st.session_state.get(_grp_key, [])
            for _grp in EXTRA_GROUPS.keys():
                _checked = st.checkbox(_grp, value=(_grp in _sel), key=f"scr_colgrp_{key_suffix}_{_grp}")
                if _checked and _grp not in _sel:
                    _sel = _sel + [_grp]
                elif not _checked and _grp in _sel:
                    _sel = [g for g in _sel if g != _grp]
            st.session_state[_grp_key] = _sel
            if st.button("Apply", type="primary", width="stretch", key=f"scr_col_apply_{key_suffix}"):
                st.rerun()

        # ── Collect available sector values ───────────────────────────────────
        _sector_vals = (
            sorted(v for v in tab_df["sector"].dropna().unique() if str(v).strip())
            if "sector" in tab_df.columns else []
        )

        # ── Apply score filter ────────────────────────────────────────────────
        if score_key:
            _sf_sel = st.session_state.get(score_key, score_default or _SCORE_OPTIONS[0])
            tab_df = _apply_score_filter(tab_df, _sf_sel)
        else:
            tab_df = tab_df.reset_index(drop=True)

        # ── Apply sector filter ───────────────────────────────────────────────
        _sec_sel = st.session_state.get(_sector_key, "All sectors")
        if _sec_sel and _sec_sel != "All sectors":
            _sec_col = tab_df["sector"] if "sector" in tab_df.columns else pd.Series("", index=tab_df.index)
            tab_df = tab_df[_sec_col == _sec_sel].reset_index(drop=True)

        n_shown = len(tab_df)
        tab_df.index = range(1, n_shown + 1)

        # ── Toolbar ───────────────────────────────────────────────────────────
        with st.container(horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            with st.container(horizontal=True, gap="small", width="content"):
                _active = st.session_state.get(_grp_key, [])
                _view_label = f"View ({len(_active)})" if _active else "View"
                if st.button(_view_label, key=f"btn_view_{key_suffix}"):
                    _dlg_view()

                if extra_toolbar_action:
                    _btn_label, _btn_cb = extra_toolbar_action
                    if st.button(_btn_label, key=f"btn_{_btn_label.lower()}_{key_suffix}"):
                        _btn_cb()

                if st.button("Buy", key=f"btn_buy_{key_suffix}"):
                    _dlg_buy_screener()

            with st.container(horizontal=True, gap="small", width="content"):
                _sec_cur = st.session_state.get(_sector_key, "All sectors")
                if _sec_cur not in _sector_vals and _sec_cur != "All sectors":
                    _sec_cur = "All sectors"
                with st.popover(_sec_cur, width=220):
                    _sec_opts = ["All sectors"] + _sector_vals
                    st.radio("Sector filter", _sec_opts,
                             index=_sec_opts.index(_sec_cur),
                             key=_sector_key, label_visibility="collapsed")

                if score_key:
                    _sf_cur = st.session_state.get(score_key, score_default or _SCORE_OPTIONS[0])
                    with st.popover(_sf_cur, width=220):
                        st.radio("Score filter", _SCORE_OPTIONS, index=_SCORE_OPTIONS.index(_sf_cur),
                                 key=score_key, label_visibility="collapsed")

        selected_groups = st.session_state.get(_grp_key, [])

        # Column group discoverability hint
        _avail_groups = [g for g in EXTRA_GROUPS if g not in selected_groups]
        if _avail_groups:
            st.caption("Additional columns: " + " · ".join(_avail_groups))

        # Score column: text signal prefix + value (no emoji per brand guidelines)
        _score_prefix = {"Strong Buy": "BUY", "Monitor": "MON", "Avoid": "AVD"}
        def _fmt_score(row):
            s = row.get("Value Score")
            if pd.isna(s):
                return "—"
            p = _score_prefix.get(row.get("Decision", ""), "")
            return f"{p}  {s:.1f}" if p else f"{s:.1f}"

        # Build the display DataFrame from core cols + selected extras.
        # fmt=None keeps raw numeric values (formatted by NumberColumn config).
        def _col_values(field, fmt):
            if field not in tab_df.columns:
                return pd.Series([pd.NA] * len(tab_df)).values
            return (tab_df[field] if fmt is None else tab_df[field].map(fmt)).values

        display_data = {}
        for col, (field, fmt) in list(CORE_COLS.items())[1:]:  # skip ★ (watchlist lives in the dialog)
            if col == "Score":
                display_data[col] = tab_df.apply(_fmt_score, axis=1).values
            else:
                display_data[col] = _col_values(field, fmt)

        active_extra_cols = []
        for group in selected_groups:
            for col, (field, fmt) in EXTRA_GROUPS[group].items():
                display_data[col] = _col_values(field, fmt)
                active_extra_cols.append(col)

        display_df = pd.DataFrame(display_data)
        _n_rows = len(display_df)

        # Highlight extra columns with a subtle tint (same as positions table)
        if active_extra_cols:
            display_df = display_df.style.set_properties(
                subset=active_extra_cols,
                **{"background-color": "rgba(99, 102, 241, 0.07)"},
            )

        col_config = {c: _col_config_map[c] for c in display_data.keys() if c in _col_config_map}

        _row_h  = 35
        _header = 38
        _height = min(_header + _n_rows * _row_h + 4, 800)

        _sel_idx = _row_select_table(
            display_df,
            key=_tbl_key,
            width="stretch",
            hide_index=True,
            column_config=col_config,
            height=_height,
        )
        _sel_ticker = display_data["Ticker"][_sel_idx] if _sel_idx is not None else None
        return _sel_ticker, n_shown, key_suffix

    # ── Buy dialog (shared across all screener tabs) ──────────────────────────
    _scr_all_df = pd.concat([df, df_ams, df_par, df_mil, df_etr, df_swx], ignore_index=True)
    _scr_sorted = _scr_all_df[["Ticker", "Name"]].drop_duplicates("Ticker").sort_values("Name", key=lambda s: s.str.lower())
    _scr_t_opts   = _scr_sorted["Ticker"].tolist()
    _scr_t_labels = {row["Ticker"]: f"{row['Name']}  ({row['Ticker']})" for _, row in _scr_sorted.iterrows()}
    _scr_price_map = _scr_all_df.drop_duplicates("Ticker").set_index("Ticker")["Price"].to_dict()

    @st.dialog("Buy stock", width="large")
    def _dlg_buy_screener():
        _c1, _c2, _c3, _c4 = st.columns([3, 1, 2, 2])
        with _c1:
            ticker = st.selectbox("Company", options=_scr_t_opts, format_func=lambda t: _scr_t_labels.get(t, t))
        with _c2:
            shares = st.number_input("Shares", min_value=1, step=1, value=1)
        with _c3:
            pur_date = st.date_input("Buy Date", format="DD/MM/YYYY")
        with _c4:
            _price    = float(_scr_price_map.get(ticker) or 0.0)
            total_price = st.number_input("Invested (€)", min_value=0.0, step=0.01,
                                          value=round(_price * shares, 2), format="%.2f")
        _, _save_btn = st.columns([3, 1])
        with _save_btn:
            _do_save = st.button("Save", key="dlg_buy_scr_save", width="stretch")
        if _do_save and shares > 0 and total_price > 0:
            name = _scr_t_labels.get(ticker, ticker).split("  (")[0]
            add_position({
                "name":           name,
                "google_ticker":  "",
                "ticker":         ticker,
                "shares":         shares,
                "purchase_price": round(total_price / shares, 4),
                "purchase_value": round(total_price, 2),
                "target_price":   None,
                "dividends":      0.0,
                "date_in":        pd.Timestamp(pur_date).isoformat(),
                "account":        "",
            })
            st.rerun()

    # ── Index constituents — derived from the same hardcoded lists used by the screener ──
    def _index_set(fn) -> frozenset[str]:
        return frozenset(s["ticker"] for s in fn())

    _INDEX_TICKERS: dict[str, tuple[str, frozenset[str]]] = {
        "br":  ("BEL 20",  _index_set(_hardcoded_bel20)),
        "ams": ("AEX",     _index_set(_hardcoded_aex25)),
        "par": ("CAC 40",  _index_set(_hardcoded_cac40)),
        "mil": ("MIB ESG", _index_set(_hardcoded_ftse_mib)),
        "etr": ("DAX",     _index_set(_hardcoded_dax40)),
        "swx": ("SMI",     _index_set(_hardcoded_smi20)),
    }

    # Exchange tab order mirrors ALL_EXCHANGES; map key → (label, render_key, dataframe)
    _EXCHANGE_TAB_META = [
        ("brussels",  "Brussels",  "br",  df),
        ("amsterdam", "Amsterdam", "ams", df_ams),
        ("paris",     "Paris",     "par", df_par),
        ("milan",     "Milan",     "mil", df_mil),
        ("frankfurt", "Frankfurt", "etr", df_etr),
        ("swiss",     "Swiss",     "swx", df_swx),
    ]
    _active_tabs = [(key, label, rkey, data)
                    for key, label, rkey, data in _EXCHANGE_TAB_META
                    if key in set(_enabled)]
    _tab_labels  = ["Watchlist"] + [label for _, label, _, _ in _active_tabs]
    tab_watchlist, *_exchange_tabs = st.tabs(_tab_labels)

    # Collect at most one pending dialog call; dispatched once after all tab code runs
    # to avoid StreamlitDuplicateElementId (all tab code executes every rerun).
    _dlg_pending: list = []

    _SCORE_OPTIONS = [
        "BUY  (> 70)",
        "MONITOR  (40–70)",
        "AVOID  (< 40)",
        "All scores",
    ]

    _DECISION_MAP = {
        "BUY  (> 70)": "Strong Buy",
        "MONITOR  (40–70)":   "Monitor",
        "AVOID  (< 40)":      "Avoid",
    }

    def _apply_score_filter(df_in: pd.DataFrame, sel: str) -> pd.DataFrame:
        decision = _DECISION_MAP.get(sel)
        out = df_in[df_in["Decision"] == decision] if decision else df_in
        return out.reset_index(drop=True)

    # ── Tab: Watchlist ────────────────────────────────────────────────────────
    with tab_watchlist:
        _wl_tickers = watchlist

        @st.dialog("Add stock", width="small")
        def _dlg_add_ticker():
            _t = st.text_input("Ticker symbol", placeholder="e.g. AAPL, 7203.T, BP.L")
            _, _save_col = st.columns([3, 1])
            with _save_col:
                _do_add = st.button("Save", key="dlg_add_confirm_watchlist", width="stretch")
            if _do_add:
                _sym = _t.strip().upper()
                if _sym:
                    _not_found = f"Ticker **{_sym}** not found. Check the symbol and try again."
                    try:
                        _info = yf.Ticker(_sym).info
                        _name = _info.get("shortName") or _info.get("longName") or _sym
                        if not _info.get("regularMarketPrice") and not _info.get("currentPrice"):
                            st.error(_not_found)
                        else:
                            _mt = load_manual_tickers()
                            _mt[_sym] = _name
                            save_manual_tickers(_mt)
                            save_watchlist(watchlist | {_sym})
                            st.rerun()
                    except Exception:
                        st.error(_not_found)

        _wl_col, _wl_refresh = st.columns([9, 1])
        with _wl_refresh:
            if st.button("Refresh", type="tertiary", key="wl_refresh"):
                _bust_cache()
        _wl_all_df = pd.concat([_scr_all_df, _scr_extra_df], ignore_index=True)
        wl_df = _wl_all_df[_wl_all_df["Ticker"].isin(_wl_tickers)].reset_index(drop=True)
        with _wl_col:
            if wl_df.empty:
                st.info("Open any stock's details popup and click ★ to add it to your watchlist, "
                        "or use **Add** to add a stock from any market.")
            else:
                st.markdown(f"**{len(wl_df)}** stocks · click a row to view details")
        _wl_sel_ticker, n_wl, _wl_tbl_key = _render_table(wl_df, "watchlist",
                                         score_key="wl_score_filter",
                                         score_default=_SCORE_OPTIONS[3],
                                         extra_toolbar_action=("Add", _dlg_add_ticker))
        _wl_star = st.session_state.get("_dlg_star_rerun", False)
        _wl_src  = st.session_state.get("_dlg_open_src", "")
        if _wl_sel_ticker is not None:
            _wl_sel_rows = wl_df[wl_df["Ticker"] == _wl_sel_ticker]
            if not _wl_sel_rows.empty:
                st.session_state["_dlg_open_ticker"] = _wl_sel_ticker
                st.session_state["_dlg_open_src"]    = "watchlist"
                _dlg_pending.append((_wl_sel_rows.iloc[0], None))
        elif _wl_star and _wl_src == "watchlist":
            st.session_state.pop("_dlg_star_rerun", None)
            _t = st.session_state.get("_dlg_open_ticker")
            if _t:
                _r = wl_df[wl_df["Ticker"] == _t]
                if not _r.empty:
                    _dlg_pending.append((_r.iloc[0], None))
        elif not _wl_star and _wl_src == "watchlist":
            st.session_state.pop("_dlg_open_ticker", None)
            st.session_state.pop("_dlg_open_src", None)


    def _render_exchange_tab(exchange_df: pd.DataFrame, key: str) -> None:
        """Render a screener exchange tab — toolbar, count, table, watchlist sync."""
        valued      = exchange_df["fair_value"].notna()
        n_unvalued  = (~valued).sum()
        hint        = _HINT_WATCHLIST
        _idx_info   = _INDEX_TICKERS.get(key)
        _idx_name   = _idx_info[0] if _idx_info else None
        _idx_tickers = _idx_info[1] if _idx_info else frozenset()

        cnt_col, _ti1, _ti2, refresh_col = st.columns([5, 2, 2, 1], vertical_alignment="center")
        with _ti1:
            idx_only = st.toggle(_idx_name, value=not _is_admin, key=f"{key}_idx_only") if _idx_name else False
        with _ti2:
            show_all = st.toggle("unvalued", value=False,
                                 key=f"{key}_show_unvalued") if n_unvalued > 0 else False
        with refresh_col:
            if st.button("Refresh", type="tertiary", key=f"{key}_refresh"):
                _bust_cache()

        tab_df = exchange_df if show_all else exchange_df[valued].reset_index(drop=True)
        if idx_only and _idx_tickers:
            tab_df = tab_df[tab_df["Ticker"].isin(_idx_tickers)].reset_index(drop=True)

        _sel_ticker, n_shown, _tbl_key = _render_table(tab_df, key,
                                        score_key=f"{key}_score_filter",
                                        score_default=_SCORE_OPTIONS[0])

        _ex_star = st.session_state.get("_dlg_star_rerun", False)
        _ex_src  = st.session_state.get("_dlg_open_src", "")
        if _sel_ticker is not None:
            _sel_rows = tab_df[tab_df["Ticker"] == _sel_ticker]
            if not _sel_rows.empty:
                st.session_state["_dlg_open_ticker"] = _sel_ticker
                st.session_state["_dlg_open_src"]    = key
                _dlg_pending.append((_sel_rows.iloc[0], _scr_pf_context))
        elif _ex_star and _ex_src == key:
            st.session_state.pop("_dlg_star_rerun", None)
            _t = st.session_state.get("_dlg_open_ticker")
            if _t:
                _r = tab_df[tab_df["Ticker"] == _t]
                if not _r.empty:
                    _dlg_pending.append((_r.iloc[0], _scr_pf_context))
        elif not _ex_star and _ex_src == key:
            st.session_state.pop("_dlg_open_ticker", None)
            st.session_state.pop("_dlg_open_src", None)

        with cnt_col:
            st.markdown(f"**{n_shown}** stocks · click a row to view details")

    for _tab, (_, _, _rkey, _data) in zip(_exchange_tabs, _active_tabs):
        with _tab:
            _render_exchange_tab(_data, _rkey)

    # Dispatch at most one dialog per render cycle to avoid duplicate element IDs
    if _dlg_pending:
        _dlg_stock_detail(*_dlg_pending[0])

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — PORTFOLIO
# ══════════════════════════════════════════════════════════════════════════════

def _page_portfolio() -> None:

    # ── Load saved portfolio ───────────────────────────────────────────────────
    pf = load_portfolio()
    if pf is None:
        pf = pd.DataFrame()

    # ── Migrate: ensure new fields exist ──────────────────────────────────────
    if not pf.empty:
        _dirty = False
        if "account" not in pf.columns:
            pf["account"] = ""
            _dirty = True
        if "purchase_price" not in pf.columns:
            pf["purchase_price"] = (
                pd.to_numeric(pf["purchase_value"], errors="coerce") /
                pd.to_numeric(pf["shares"],         errors="coerce")
            ).round(4)
            _dirty = True
        if _dirty:
            save_portfolio(pf)

        # ── Drop rows with no valid ticker ────────────────────────────────────
        pf = pf[pf["ticker"].notna() & (pf["ticker"].astype(str).str.strip() != "")].reset_index(drop=True)

    # ── Screener data + Add-position dialog (always needed, even for empty portfolio) ──
    _pf_enabled  = tuple(load_shared_settings().get("enabled_exchanges", ALL_EXCHANGES))
    # Combine active + sold tickers so both get fetched at screener cadence
    _sold_early  = load_sold()
    _sold_tickers = tuple(_sold_early["ticker"].dropna().tolist()) if _sold_early is not None and not _sold_early.empty else ()
    _sold_names   = tuple(_sold_early["name"].dropna().tolist())   if _sold_early is not None and not _sold_early.empty else ()
    _pf_tickers  = tuple(pf["ticker"].tolist())
    _pf_names    = tuple(pf["name"].tolist())
    _extra_tickers = tuple(dict.fromkeys(_pf_tickers + _sold_tickers))  # dedup, preserve order
    _extra_names   = tuple(
        {**dict(zip(_sold_tickers, _sold_names)), **dict(zip(_pf_tickers, _pf_names))}[t]
        for t in _extra_tickers
    )
    *_pf_exch_dfs, _pf_extra_df = _load_all_screener_data(_cache_version(), _pf_enabled, _extra_tickers, _extra_names)
    _all_scr_df = pd.concat(_pf_exch_dfs + [_pf_extra_df], ignore_index=True)
    _pf_dlg_pending: list = []  # at most one dialog call per render
    _all_screener = _all_scr_df[["Ticker", "Name"]].sort_values("Name", key=lambda s: s.str.lower())
    _ticker_options = _all_screener["Ticker"].tolist()
    _ticker_labels  = {
        row["Ticker"]: f"{row['Name']}  ({row['Ticker']})"
        for _, row in _all_screener.iterrows()
    }
    _port_price_map = _all_scr_df.drop_duplicates("Ticker").set_index("Ticker")["Price"].to_dict()

    @st.dialog("Add position", width="large")
    def _dlg_add_position():
        _c1, _c2, _c3, _c4 = st.columns([3, 1, 2, 2])
        with _c1:
            ticker = st.selectbox("Company", options=_ticker_options, format_func=lambda t: _ticker_labels.get(t, t))
        with _c2:
            shares = st.number_input("Shares", min_value=1, step=1, value=1)
        with _c3:
            pur_date = st.date_input("Buy Date", format="DD/MM/YYYY")
        with _c4:
            _price      = float(_port_price_map.get(ticker) or 0.0)
            total_price = st.number_input("Invested (€)", min_value=0.0, step=0.01,
                                          value=round(_price * shares, 2), format="%.2f")
        _, _save_btn = st.columns([3, 1])
        with _save_btn:
            _do_save = st.button("Save", key="dlg_add_save", width="stretch")
        if _do_save and shares > 0 and total_price > 0:
            name = _ticker_labels.get(ticker, ticker).split("  (")[0]
            add_position({
                "name":           name,
                "google_ticker":  "",
                "ticker":         ticker,
                "shares":         shares,
                "purchase_price": round(total_price / shares, 4),
                "purchase_value": round(total_price, 2),
                "target_price":   None,
                "dividends":      0.0,
                "date_in":        pd.Timestamp(pur_date).isoformat(),
                "account":        "",
            })
            st.rerun()

    _auto_rerun(60, "portfolio_refresh")

    if pf.empty:
        # ── Empty portfolio — show Add button only ────────────────────────────
        sub_positions, sub_sold, sub_dividends = st.tabs(["Positions", "Realised", "Dividends"])
        with sub_positions:
            if st.button("Buy", key="btn_add_pos_empty"):
                _dlg_add_position()
            st.info("Your portfolio is empty. Click 🛒 Buy to add your first position.")
        with sub_dividends:
            st.info("No positions yet. Add stocks in the Positions tab first.")
        with sub_sold:
            st.info("No sold positions yet.")
        st.stop()

    # ── Fetch live prices ─────────────────────────────────────────────────────
    live_data = _fetch_live_data(tuple(pf["ticker"].tolist()))

    def _lv(field, default=None):
        return pf["ticker"].map(lambda t: live_data[t].get(field, default))

    pf["live_price"]      = _lv("price")
    pf["analyst_target"]  = _lv("analyst_target")
    pf["graham_number"]   = _lv("graham_number")
    pf["pe_fair_value"]   = _lv("pe_fair_value")
    pf["graham_growth"]   = _lv("graham_growth")
    pf["fair_value"]      = _lv("fair_value")
    pf["div_rate"]        = _lv("div_rate", 0).map(lambda v: v or 0)
    pf["day_change_pct"]  = _lv("day_change_pct")
    pf["prev_close"]      = _lv("prev_close")
    pf["sector"]          = _lv("sector")
    pf["country"]         = _lv("country")
    pf["expected_annual"] = (pf["div_rate"] * pf["shares"]).round(2)
    pf["current_value"]   = pf["live_price"] * pf["shares"]
    pf["price_gain"]      = pf["current_value"] - pf["purchase_value"]
    _cost = pf["purchase_value"].replace(0, float("nan"))
    _price = pf["live_price"].replace(0, float("nan"))
    pf["price_gain_pct"]  = (pf["price_gain"] / _cost * 100).round(2)
    pf["total_return"]    = pf["price_gain"] + pf["dividends"].fillna(0)
    pf["total_return_pct"] = (pf["total_return"] / _cost * 100).round(2)
    pf["upside_pct"]      = ((pf["analyst_target"] - pf["live_price"]) / _price * 100).round(1)
    pf["fv_upside_pct"]   = ((pf["fair_value"]     - pf["live_price"]) / _price * 100).round(1)

    _scr = _all_scr_df.set_index("Ticker")
    pf["value_score"] = pf["ticker"].map(_scr["Value Score"].to_dict() if "Value Score" in _scr.columns else {})

    def _scr_col(field: str) -> "pd.Series":
        col = _scr[field] if field in _scr.columns else pd.Series(dtype=object)
        return pf["ticker"].map(col.to_dict())

    # ── Summary cards (shared across both sub-tabs) ───────────────────────────
    total_invested   = pf["purchase_value"].sum()
    total_current    = pf["current_value"].sum()
    total_dividends  = pf["dividends"].fillna(0).sum()
    total_expected   = pf["expected_annual"].sum()
    price_gain       = total_current - total_invested
    total_return     = price_gain + total_dividends
    price_gain_pct   = _safe_pct(price_gain,   total_invested)
    total_return_pct = _safe_pct(total_return, total_invested)

    # Auto-backfill missing trading days — check BEFORE recording today's snapshot
    # so first-ever load (empty history) correctly triggers the full backfill
    _vh_check = load_value_history()
    _yesterday = (pd.Timestamp.today() - pd.Timedelta(days=1)).normalize()
    _last_date = (
        pd.to_datetime(_vh_check["date"]).max()
        if _vh_check is not None and not _vh_check.empty
        else pd.Timestamp("1970-01-01")
    )
    _needs_backfill = (
        total_current > 0
        and (_last_date < _yesterday or (_vh_check is None or len(_vh_check) <= 1))
    )
    if _needs_backfill:
        with st.spinner("Updating value history…"):
            backfill_value_history(pf, load_sold())

    if total_current > 0:
        record_value_snapshot(total_invested, total_current)

    sub_positions, sub_sold, sub_dividends = st.tabs(["Positions", "Realised", "Dividends"])

    # ── Sub-tab: Positions ────────────────────────────────────────────────────
    with sub_positions:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Invested",      f"€{total_invested:,.0f}")
        c2.metric("Current value", f"€{total_current:,.0f}",  delta=f"{price_gain_pct:+.1f}% (€{price_gain:+,.0f})")
        c3.metric("Dividends",     f"€{total_dividends:,.0f}")
        c4.metric("Total return",  f"€{total_return:,.0f}",   delta=f"{total_return_pct:+.1f}%")
        st.divider()

        # ── CRUD actions ─────────────────────────────────────────────────────
        @st.dialog("Edit positions", width="large")
        def _dlg_edit_position():
            _edit_src = pf.sort_values("name", key=lambda s: s.str.lower()).reset_index()  # orig idx in 'index' col
            _tbl = pd.DataFrame({
                "_idx":        _edit_src["index"],
                "🗑️":          False,
                "Company":     _edit_src["name"],
                "Stocks":      pd.to_numeric(_edit_src["shares"], errors="coerce").fillna(0).astype(int),
                "Invested": (
                    pd.to_numeric(_edit_src["purchase_price"], errors="coerce") *
                    pd.to_numeric(_edit_src["shares"],         errors="coerce")
                ).round(2),
                "Date":        pd.to_datetime(
                    _edit_src["date_in"], format="mixed", dayfirst=False, errors="coerce"
                ).dt.date,
            })

            _row_h  = 35
            _header = 35
            _height = _header + min(len(_tbl), 8) * _row_h

            _edited = st.data_editor(
                _tbl.drop(columns="_idx"),
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                height=_height,
                column_config={
                    "🗑️":          st.column_config.CheckboxColumn("🗑️",               width=55),
                    "Company":     st.column_config.TextColumn("Company",              disabled=True, pinned=True),
                    "Stocks":      st.column_config.NumberColumn("Shares",             min_value=1, step=1, format="%d"),
                    "Invested":    st.column_config.NumberColumn("Invested (€)",        min_value=0.01, format="%.2f"),
                    "Date":        st.column_config.DateColumn("Buy Date",             format="DD/MM/YYYY"),
                },
                key="dlg_edit_table",
            )

            to_delete  = _edited[_edited["🗑️"]].index.tolist()
            to_keep    = _edited[~_edited["🗑️"]]
            n_selected = len(to_delete)

            _del_note, _save_col = st.columns([3, 1])
            with _del_note:
                if n_selected:
                    st.caption(f"{n_selected} selected for deletion")
            with _save_col:
                if st.button("Save", key="dlg_edit_save", width="stretch"):
                    for i, row in to_keep.iterrows():
                        orig_idx = int(_tbl.iloc[i]["_idx"])
                        new_shares = max(1, int(row["Stocks"]))
                        new_total  = float(row["Invested"])
                        pf.at[orig_idx, "shares"]         = new_shares
                        pf.at[orig_idx, "purchase_price"] = round(new_total / new_shares, 4)
                        pf.at[orig_idx, "purchase_value"] = round(new_total, 2)
                        if pd.notna(row["Date"]) and row["Date"] is not None:
                            pf.at[orig_idx, "date_in"] = pd.Timestamp(row["Date"]).isoformat()
                    if to_delete:
                        del_orig = [int(_tbl.iloc[i]["_idx"]) for i in to_delete]
                        pf.drop(index=del_orig, inplace=True)
                        pf.reset_index(drop=True, inplace=True)
                    update_positions(pf)
                    st.rerun()

        # ── Column groups (same groups as screener) ───────────────────────────
        # Numeric values stay raw — formatting comes from the NumberColumn
        # config below so column sorting is numeric.
        _POS_EXTRA_GROUPS = {
            "Valuation": {
                "Analyst Target":      pf["analyst_target"],
                "Fair Value":          pf["fair_value"],
                "Fair Value Upside %": pf["fv_upside_pct"],
            },
            "Valuation models": {
                "Graham #":      _scr_col("graham_number"),
                "PE Fair Val":   _scr_col("pe_fair_value"),
                "EPV":           _scr_col("epv"),
                "DDM (1-stage)": _scr_col("ddm"),
                "DDM (2-stage)": _scr_col("ddm_multistage"),
            },
            "Risk": {
                "Risk Score":  _scr_col("Risk Score"),
                "Beta":        _scr_col("beta"),
                "Debt/Equity": _scr_col("debtToEquity"),
                "Mkt Cap":     _scr_col("Market Cap"),
            },
            "Multiples": {
                "P/E":       _scr_col("trailingPE"),
                "P/B":       _scr_col("priceToBook"),
                "EV/EBITDA": _scr_col("enterpriseToEbitda"),
            },
            "Quality": {
                "ROE %":       _scr_col("returnOnEquity"),
                "ROA %":       _scr_col("returnOnAssets"),
                "Op Margin %": _scr_col("operatingMargins"),
                "FCF Yield %": _scr_col("fcfYield"),
            },
            "Growth": {
                "Rev Growth %": _scr_col("revenueGrowth"),
                "EPS Growth %": _scr_col("earningsGrowth"),
            },
            "Dividends": {
                "Div/Share":       pf["div_rate"],
                "Expected Annual": pf["expected_annual"],
                "Div Yield":       _scr_col("dividendYield"),
                "5yr Avg Yield":   _scr_col("fiveYearAvgDividendYield"),
                "Payout Ratio":    _scr_col("payoutRatio"),
                "Cash Payout":     _scr_col("cashPayoutRatio"),
                "Div Coverage":    _scr_col("dividendCoverage"),
                "Div Flag":        _scr_col("Div Flag").map(_fmt_div_flag),
            },
            "Geography": {
                "Sector":  _scr_col("sector").map(_f_str),
                "Country": _scr_col("country").map(_f_str),
            },
            "Score": {
                "Value Score": pf["value_score"],
                "Buy Date":    pd.to_datetime(pf["date_in"], format="mixed", dayfirst=False, errors="coerce").dt.strftime("%d-%m-%Y").fillna("—"),
            },
        }

        @st.dialog("View", width="small")
        def _dlg_columns():
            _sel = st.session_state.get("pos_col_groups", [])
            for _grp in _POS_EXTRA_GROUPS.keys():
                _checked = st.checkbox(_grp, value=(_grp in _sel), key=f"colgrp_{_grp}")
                if _checked and _grp not in _sel:
                    _sel = _sel + [_grp]
                elif not _checked and _grp in _sel:
                    _sel = [g for g in _sel if g != _grp]
            st.session_state["pos_col_groups"] = _sel
            if st.button("Apply", type="primary", width="stretch", key="btn_col_apply"):
                st.rerun()

        @st.dialog("Sell position", width="large")
        def _dlg_sell_position():
            _sell_sorted     = pf.sort_values("name", key=lambda s: s.str.lower())
            _sell_ticker_options = _sell_sorted["ticker"].tolist()
            _sell_ticker_labels  = {
                row["ticker"]: f"{row['name']}  ({row['ticker']})"
                for _, row in _sell_sorted.iterrows()
            }
            _c1, _c2, _c3, _c4 = st.columns([3, 1, 2, 2])
            with _c1:
                ticker = st.selectbox("Company", options=_sell_ticker_options,
                                      format_func=lambda t: _sell_ticker_labels.get(t, t),
                                      key="dlg_sell_ticker")
            _match = pf[pf["ticker"] == ticker]
            with _c2:
                _shares_def = str(int(pd.to_numeric(_match.iloc[0]["shares"], errors="coerce") or 0)) if not _match.empty else "0"
                _shares_raw = st.text_input("Shares", value=_shares_def, key="dlg_sell_shares")
            with _c3:
                sell_date = st.date_input("Sell Date", format="DD/MM/YYYY", key="dlg_sell_date")
            with _c4:
                _current_val = pd.to_numeric(_match.iloc[0].get("current_value"), errors="coerce") if not _match.empty else 0.0
                _proceeds_def = f"{_current_val:.2f}" if pd.notna(_current_val) and _current_val else "0.00"
                _proceeds_raw = st.text_input("Proceeds (€)", value=_proceeds_def, key="dlg_sell_proceeds")
            _, _save_col = st.columns([3, 1])
            with _save_col:
                _do_save = st.button("Save", key="dlg_sell_save", width="stretch")
            try:
                _shares   = max(1, int(_shares_raw.strip()))
                _proceeds = float(_proceeds_raw.strip().replace(",", "."))
            except ValueError:
                _shares, _proceeds = 1, 0.0
            if _do_save and _shares > 0 and _proceeds > 0:
                sell_position(
                    ticker=ticker,
                    shares=_shares,
                    proceeds=_proceeds,
                    sell_date=pd.Timestamp(sell_date).isoformat(),
                )
                st.rerun()

        with st.container(horizontal=True, gap="small"):
            _active_groups = st.session_state.get("pos_col_groups", [])
            _col_label = f"View ({len(_active_groups)})" if _active_groups else "View"
            if st.button(_col_label, key="btn_col_pos"):
                _dlg_columns()
            if st.button("Buy", key="btn_add_pos"):
                _dlg_add_position()
            if st.button("Edit", key="btn_edit_pos"):
                _dlg_edit_position()
            if st.button("Sell", key="btn_sell_pos"):
                _dlg_sell_position()

        _pos_groups = st.session_state.get("pos_col_groups", [])

        # Signal column from screener Decision field
        _decision_map = _scr["Decision"].to_dict() if "Decision" in _scr.columns else {}
        _signal_labels = {"Strong Buy": "BUY", "Monitor": "MONITOR", "Avoid": "AVOID"}

        # Build core positions DataFrame
        pos_data = {
            "Company":        pf["name"],
            "Ticker":         pf["ticker"],
            "Signal":         pf["ticker"].map(lambda t: _signal_labels.get(_decision_map.get(t, ""), "—")),
            "Shares":         pf["shares"],
            "Buy Date":       pd.to_datetime(pf["date_in"], format="mixed", dayfirst=False, errors="coerce").dt.strftime("%d-%m-%Y").fillna("—"),
            "Live Price":     pf["live_price"],
            "Invested":       pf["purchase_value"],
            "Current":        pf["current_value"],
            "Price Gain":     pf["price_gain"],
            "Dividend":       pf["dividends"].fillna(0),
            "Price Gain %":   pf["price_gain_pct"],
            "Total Return %": pf["total_return_pct"],
        }
        for grp in _pos_groups:
            pos_data.update(_POS_EXTRA_GROUPS[grp])

        _core_cols = {"Company", "Ticker", "Signal", "Shares", "Buy Date", "Live Price",
                      "Invested", "Current", "Price Gain", "Dividend", "Price Gain %", "Total Return %"}

        positions = pd.DataFrame(pos_data).sort_values("Company", key=lambda s: s.str.lower())
        _n_rows = len(positions)

        _scr_help = COLUMN_HELP.get
        _pos_col_config = {
            "Company":        st.column_config.TextColumn("Company",         pinned=True,
                                  help="Company name"),
            "Ticker":         st.column_config.TextColumn("Ticker",
                                  help="Exchange ticker symbol"),
            "Signal":         st.column_config.TextColumn("Signal",          width=90,
                                  help="Current fair value signal for this holding: BUY · MONITOR · AVOID"),
            "Shares":         st.column_config.NumberColumn("Shares",        format="%d",
                                  help="Number of shares held"),
            "Buy Date":       st.column_config.TextColumn("Buy Date",
                                  help="Date the position was opened"),
            "Live Price":     st.column_config.NumberColumn("Live Price",    format="euro",
                                  help="Latest market price fetched from yfinance"),
            "Invested":       st.column_config.NumberColumn("Invested",      format="euro",
                                  help="Total amount invested (purchase price × shares)"),
            "Current":        st.column_config.NumberColumn("Current",       format="euro",
                                  help="Current market value (live price × shares)"),
            "Price Gain":     st.column_config.NumberColumn("Price Gain (€)", format="€%.0f",
                                  help="Unrealised gain/loss in euros: current value − invested"),
            "Dividend":       st.column_config.NumberColumn("Dividend",      format="euro",
                                  help="Total dividends received for this position since purchase"),
            "Price Gain %":   st.column_config.NumberColumn("Price Gain %",   format="%.2f%%",
                                  help="Price appreciation since purchase: (current value − invested) / invested"),
            "Total Return %": st.column_config.NumberColumn("Total Return %", format="%.2f%%",
                                  help="Total return including dividends: (price gain + dividends) / invested"),
            "Fair Value Upside %": st.column_config.NumberColumn("Fair Value Upside %", format="%+.1f%%",
                                  help="Upside to the fair value estimate: (fair value − live price) / live price"),
            "Analyst Target": st.column_config.NumberColumn("Analyst Target", format="euro",
                                  help="Mean analyst consensus price target"),
            "Fair Value":     st.column_config.NumberColumn("Fair Value",     format="euro",
                                  help="Weighted composite intrinsic value estimate"),
            "Graham #":       st.column_config.NumberColumn("Graham #",       format="euro", help=_scr_help("Graham #")),
            "PE Fair Val":    st.column_config.NumberColumn("PE Fair Val",    format="euro", help=_scr_help("PE Fair Val")),
            "EPV":            st.column_config.NumberColumn("EPV",            format="euro", help=_scr_help("EPV")),
            "DDM (1-stage)":  st.column_config.NumberColumn("DDM (1-stage)",  format="euro", help=_scr_help("DDM (1-stage)")),
            "DDM (2-stage)":  st.column_config.NumberColumn("DDM (2-stage)",  format="euro", help=_scr_help("DDM (2-stage)")),
            "Beta":           st.column_config.NumberColumn("Beta",           format="%.2f",    help=_scr_help("Beta")),
            "Debt/Equity":    st.column_config.NumberColumn("Debt/Equity",    format="%.1f",    help=_scr_help("Debt/Equity")),
            "Mkt Cap":        st.column_config.NumberColumn("Mkt Cap",        format="compact", help=_scr_help("Mkt Cap")),
            "P/E":            st.column_config.NumberColumn("P/E",            format="%.1f",    help=_scr_help("P/E")),
            "P/B":            st.column_config.NumberColumn("P/B",            format="%.2f",    help=_scr_help("P/B")),
            "EV/EBITDA":      st.column_config.NumberColumn("EV/EBITDA",      format="%.1f",    help=_scr_help("EV/EBITDA")),
            "ROE %":          st.column_config.NumberColumn("ROE %",          format="percent", help=_scr_help("ROE %")),
            "ROA %":          st.column_config.NumberColumn("ROA %",          format="percent", help=_scr_help("ROA %")),
            "Op Margin %":    st.column_config.NumberColumn("Op Margin %",    format="percent", help=_scr_help("Op Margin %")),
            "FCF Yield %":    st.column_config.NumberColumn("FCF Yield %",    format="percent", help=_scr_help("FCF Yield %")),
            "Rev Growth %":   st.column_config.NumberColumn("Rev Growth %",   format="percent", help=_scr_help("Rev Growth %")),
            "EPS Growth %":   st.column_config.NumberColumn("EPS Growth %",   format="percent", help=_scr_help("EPS Growth %")),
            "Div/Share":      st.column_config.NumberColumn("Div/Share",      format="€%.4f",
                                  help="Forward dividend rate per share"),
            "Expected Annual":st.column_config.NumberColumn("Expected Annual", format="euro",
                                  help="Expected annual dividend income (forward rate × shares)"),
            "Div Yield":      st.column_config.NumberColumn("Div Yield",      format="percent", help=_scr_help("Div Yield")),
            "5yr Avg Yield":  st.column_config.NumberColumn("5yr Avg Yield",  format="percent", help=_scr_help("5yr Avg Yield")),
            "Payout Ratio":   st.column_config.NumberColumn("Payout Ratio",   format="percent", help=_scr_help("Payout Ratio")),
            "Cash Payout":    st.column_config.NumberColumn("Cash Payout",    format="percent", help=_scr_help("Cash Payout")),
            "Div Coverage":   st.column_config.NumberColumn("Div Coverage",   format="%.2f×",   help=_scr_help("Div Coverage")),
            "Value Score":    st.column_config.ProgressColumn("Value Score",  min_value=0, max_value=100, format="%.1f",
                                  help="Fair value composite score 0–100. BUY >70 · MONITOR 40–70 · AVOID <40"),
            "Risk Score":     st.column_config.ProgressColumn("Risk Score",   min_value=0, max_value=100, format="%.1f",
                                  help="Fair value risk score 0–10 (displayed as 0–100). Higher = riskier. Aggregates financial health, earnings quality, beta, dividend risk, and liquidity."),
        }

        _row_h  = 35
        _header = 38
        _height = min(_header + _n_rows * _row_h + 4, 800)
        _pf_sel_idx = _row_select_table(
            positions,
            key="pf_positions_table",
            width="stretch",
            hide_index=True,
            column_config=_pos_col_config,
            height=_height,
        )
        if _pf_sel_idx is not None:
            _pf_sel = positions["Ticker"].iloc[_pf_sel_idx]
            _pf_scr_row = _all_scr_df[_all_scr_df["Ticker"] == _pf_sel]
            if not _pf_scr_row.empty:
                st.session_state["_dlg_open_ticker"] = _pf_sel
                st.session_state["_dlg_open_src"]    = "pf_positions"
                _pf_dlg_pending.append((_pf_scr_row.iloc[0], None))
        elif st.session_state.get("_dlg_open_src") == "pf_positions":
            # Keep the dialog open across the rerun caused by the watchlist star
            if st.session_state.pop("_dlg_star_rerun", False):
                _t = st.session_state.get("_dlg_open_ticker")
                _r = _all_scr_df[_all_scr_df["Ticker"] == _t] if _t else pd.DataFrame()
                if not _r.empty:
                    _pf_dlg_pending.append((_r.iloc[0], None))
            else:
                st.session_state.pop("_dlg_open_ticker", None)
                st.session_state.pop("_dlg_open_src", None)

        # ── Charts — tabbed to reduce scroll ─────────────────────────────────
        _ch_perf, _ch_value, _ch_breakdown = st.tabs(["Performance", "Value history", "Breakdown"])

        with _ch_perf:
            _hm_mode_col, _ = st.columns([2, 5])
            _hm_mode = _hm_mode_col.radio(
                "Return",
                options=["Total return", "Daily return"],
                horizontal=True,
                key="hm_mode",
                label_visibility="collapsed",
            )
            st.subheader(f"Gain / loss — {_hm_mode.lower()}")

            _hm_df = pf.dropna(subset=["name", "current_value"]).copy()
            _hm_df["current_value"] = pd.to_numeric(_hm_df["current_value"], errors="coerce")

            if _hm_mode == "Daily return":
                _hm_df["_ret"] = pd.to_numeric(_hm_df["day_change_pct"], errors="coerce")
                _ret_label = "Day %"
            else:
                _hm_df["_ret"] = pd.to_numeric(_hm_df["price_gain_pct"], errors="coerce")
                _ret_label = "Total %"

            _hm_df = _hm_df.dropna(subset=["_ret", "current_value"])

            if not _hm_df.empty:
                _clamp  = 10.0
                _normed = _hm_df["_ret"].clip(-_clamp, _clamp) / _clamp
                _colors = [_hm_color(v) for v in _normed]
                _labels = [f"<b>{row['name']}</b><br>{row['_ret']:+.2f}%" for _, row in _hm_df.iterrows()]
                _hover  = [
                    f"<b>{row['name']}</b><br>{_ret_label}: {row['_ret']:+.2f}%<br>Value: €{row['current_value']:,.0f}"
                    for _, row in _hm_df.iterrows()
                ]
                _hm_fig = go.Figure(go.Treemap(
                    labels=_hm_df["name"].tolist(),
                    parents=[""] * len(_hm_df),
                    values=_hm_df["current_value"].tolist(),
                    text=_labels,
                    customdata=_hover,
                    hovertemplate="%{customdata}<extra></extra>",
                    textinfo="text",
                    textfont=dict(color=_c_text, size=13),
                    marker=dict(colors=_colors, line=dict(width=2, color=_c_surface)),
                ))
                _hm_fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                                      paper_bgcolor="rgba(0,0,0,0)", height=340)
                st.plotly_chart(_hm_fig, width="stretch", config=_CHART_CONFIG)

                st.subheader("P&L per position")
                _static_bar(
                    pf.dropna(subset=["price_gain", "name"])
                      .groupby("name")["price_gain"].sum()
                      .sort_values(ascending=False)
                )
            else:
                st.caption("No return data available.")

        with _ch_value:
            _vh_title_col, _vh_btn_col = st.columns([4, 1])
            with _vh_title_col:
                st.subheader("Portfolio value over time")
            with _vh_btn_col:
                if st.button("Rebuild history", key="rebuild_value_history",
                             help="Fetch full price history from Yahoo Finance"):
                    with st.spinner("Fetching price history…"):
                        _sold_df = load_sold()
                        _n = backfill_value_history(pf, _sold_df)
                    st.success(f"Built {_n} data points.")
                    st.rerun()

            _vh = load_value_history()
            if _vh is not None and not _vh.empty and len(_vh) >= 2:
                _vh["date"]     = pd.to_datetime(_vh["date"])
                _vh["value"]    = pd.to_numeric(_vh["value"],    errors="coerce")
                _vh["invested"] = pd.to_numeric(_vh["invested"], errors="coerce")
                _vh = _vh.dropna(subset=["date", "value"]).sort_values("date")

                _has_spx   = "benchmark_spx"   in _vh.columns and _vh["benchmark_spx"].notna().any()
                _has_stoxx = "benchmark_stoxx" in _vh.columns and _vh["benchmark_stoxx"].notna().any()

                if _has_spx or _has_stoxx:
                    _cb_cols = st.columns([1, 1, 4])
                    _show_spx   = _cb_cols[0].checkbox("S&P 500",      value=False, key="vh_show_spx",   disabled=not _has_spx)
                    _show_stoxx = _cb_cols[1].checkbox("Euro Stoxx 50", value=False, key="vh_show_stoxx", disabled=not _has_stoxx)
                else:
                    _show_spx = _show_stoxx = False

                _vfig = go.Figure()
                _vfig.add_trace(go.Scatter(
                    x=_vh["date"], y=_vh["value"],
                    mode="lines", name="Portfolio value",
                    line=dict(color="#1DD6A4", width=2),
                    fill="tozeroy", fillcolor="rgba(29,214,164,0.07)",
                ))
                _vfig.add_trace(go.Scatter(
                    x=_vh["date"], y=_vh["invested"],
                    mode="lines", name="Amount invested",
                    line=dict(color=_c_invested, width=1.5, dash="dot"),
                ))
                if _has_spx and _show_spx:
                    _vfig.add_trace(go.Scatter(
                        x=_vh["date"], y=pd.to_numeric(_vh["benchmark_spx"], errors="coerce"),
                        mode="lines", name="S&P 500 (same invested)",
                        line=dict(color="#5B8FA8", width=1.5, dash="dash"),
                    ))
                if _has_stoxx and _show_stoxx:
                    _vfig.add_trace(go.Scatter(
                        x=_vh["date"], y=pd.to_numeric(_vh["benchmark_stoxx"], errors="coerce"),
                        mode="lines", name="Euro Stoxx 50 (same invested)",
                        line=dict(color="#8BA888", width=1.5, dash="dash"),
                    ))
                _vfig.update_layout(
                    margin=dict(l=0, r=0, t=32, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                                font=dict(color=_c_axis)),
                    yaxis=dict(tickprefix="€", tickformat=",.0f",
                               tickfont=dict(color=_c_axis), gridcolor=_c_grid),
                    xaxis=dict(showgrid=False, tickfont=dict(color=_c_axis)),
                    hovermode="x unified",
                    font=dict(color=_c_axis),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(_vfig, width="stretch", config=_CHART_CONFIG)
            else:
                st.caption("No history yet — click **Rebuild history** to fetch it from Yahoo Finance.")

        with _ch_breakdown:
            _bd_col1, _bd_col2 = st.columns(2)
            with _bd_col1:
                _bd_options = {"Sector": "sector", "Country": "country", "Position": "name"}
                _bd_by = st.radio(
                    "Breakdown",
                    options=list(_bd_options.keys()),
                    key="pos_breakdown_by",
                    horizontal=True,
                    label_visibility="collapsed",
                )
                st.subheader(f"{_bd_by} breakdown")
                _bd_field = _bd_options[_bd_by]
                _bd_series = (
                    pf.dropna(subset=["current_value"])
                      .assign(**{_bd_field: pf[_bd_field].fillna("Unknown")})
                      .groupby(_bd_field)["current_value"]
                      .sum()
                      .sort_values(ascending=False)
                )
                _donut_chart(_bd_series)

            with _bd_col2:
                st.subheader("Allocation by position")
                _static_bar(
                    pf.dropna(subset=["current_value", "name"])
                      .groupby("name")["current_value"].sum()
                      .sort_values(ascending=False),
                    color="#1DD6A4",
                )

    # ── Sub-tab: Dividends ────────────────────────────────────────────────────
    with sub_dividends:
        div_hist = load_div_hist()
        if div_hist is not None and not div_hist.empty:
            div_hist["amount"] = pd.to_numeric(div_hist["amount"], errors="coerce")
            div_hist["date"]   = pd.to_datetime(div_hist["date"], errors="coerce")
            total_hist = div_hist["amount"].sum()
        else:
            total_hist = total_dividends

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Total received",   f"€{total_hist:,.2f}")
        d2.metric("Current holdings", f"€{total_dividends:,.2f}")
        d3.metric("Expected 12 mths", f"€{total_expected:,.2f}")
        d4.metric("Portfolio yield",  f"{total_expected / total_current * 100:.2f}%" if total_current else "—")
        st.container(height=28, border=False)
        st.divider()

        # ── Dividend CRUD dialogs ─────────────────────────────────────────────
        _div_ticker_options = pf["ticker"].tolist()
        _div_ticker_labels  = {
            row["ticker"]: f"{row['name']}  ({row['ticker']})"
            for _, row in pf.iterrows()
        }

        @st.dialog("Add dividend", width="large")
        def _dlg_add_dividend():
            _c1, _c2, _c3, _c4 = st.columns([3, 1, 1, 2])
            with _c1:
                ticker = st.selectbox("Stock", options=_div_ticker_options,
                                      format_func=lambda t: _div_ticker_labels.get(t, t),
                                      key="dlg_add_div_ticker")
            with _c2:
                _shares_def = ""
                _match = pf[pf["ticker"] == ticker]
                if not _match.empty:
                    _shares_def = str(int(pd.to_numeric(_match.iloc[0]["shares"], errors="coerce") or 0))
                _shares_raw = st.text_input("Shares", value=_shares_def, key="dlg_add_div_shares")
            with _c3:
                _dps_raw = st.text_input("Div/Share (€)", value="0.0000", key="dlg_add_div_dps")
            with _c4:
                div_date = st.date_input("Date", format="DD/MM/YYYY", key="dlg_add_div_date")
            _, _save_col = st.columns([3, 1])
            with _save_col:
                _do_save = st.button("Save", key="dlg_add_div_save", width="stretch")
            try:
                _shares = max(1, int(_shares_raw.strip()))
                _dps    = float(_dps_raw.strip().replace(",", "."))
            except ValueError:
                _shares, _dps = 1, 0.0
            if _do_save and _shares > 0 and _dps > 0:
                _row_match = pf[pf["ticker"] == ticker]
                _name         = _row_match.iloc[0]["name"] if not _row_match.empty else ticker
                _google_ticker = _row_match.iloc[0].get("google_ticker", "") if not _row_match.empty else ""
                add_dividend({
                    "name":          _name,
                    "google_ticker": _google_ticker,
                    "ticker":        ticker,
                    "shares":        _shares,
                    "amount":        round(_dps * _shares, 2),
                    "date":          pd.Timestamp(div_date).isoformat(),
                })
                st.rerun()

        @st.dialog("Edit dividends", width="large")
        def _dlg_edit_dividends():
            _dh = load_div_hist()
            if _dh is None or _dh.empty:
                st.info("No dividend history to edit.")
                return
            _dh = _dh.copy().reset_index(drop=True)
            _dh["amount"] = pd.to_numeric(_dh["amount"], errors="coerce").fillna(0)
            _dh["date"]   = pd.to_datetime(_dh["date"], errors="coerce")
            _dh["shares"] = pd.to_numeric(_dh.get("shares"), errors="coerce").fillna(0).astype(int)

            _tbl = pd.DataFrame({
                "_idx":      range(len(_dh)),
                "🗑️":        False,
                "Company":   _dh["name"],
                "Ticker":    _dh["ticker"],
                "Shares":    _dh["shares"],
                "Div/Share": (_dh["amount"] / _dh["shares"].replace(0, float("nan"))).round(4),
                "Total (€)": _dh["amount"],
                "Date":      _dh["date"].dt.date,
            })

            _row_h  = 35
            _header = 35
            _height = _header + min(len(_tbl), 10) * _row_h

            _edited = st.data_editor(
                _tbl.drop(columns="_idx"),
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                height=_height,
                column_config={
                    "🗑️":        st.column_config.CheckboxColumn("🗑️",           width=55),
                    "Company":   st.column_config.TextColumn("Company",          disabled=True, pinned=True),
                    "Ticker":    st.column_config.TextColumn("Ticker",           disabled=True),
                    "Shares":    st.column_config.NumberColumn("Shares",         min_value=1, step=1, format="%d"),
                    "Div/Share": st.column_config.NumberColumn("Div/Share (€)",  min_value=0.0, format="%.4f"),
                    "Total (€)": st.column_config.NumberColumn("Total (€)",      min_value=0.0, format="%.2f", disabled=True),
                    "Date":      st.column_config.DateColumn("Date",             format="DD/MM/YYYY"),
                },
                key="dlg_edit_div_table",
            )

            to_delete  = _edited[_edited["🗑️"]].index.tolist()
            to_keep    = _edited[~_edited["🗑️"]]
            n_selected = len(to_delete)

            _del_note, _save_col = st.columns([3, 1])
            with _del_note:
                if n_selected:
                    st.caption(f"{n_selected} selected for deletion")
            with _save_col:
                if st.button("Save", key="dlg_edit_div_save", width="stretch"):
                    updated = []
                    for i, row in to_keep.iterrows():
                        orig_idx = int(_tbl.iloc[i]["_idx"])
                        _new_shares = max(1, int(row["Shares"]))
                        _new_dps    = float(row["Div/Share"]) if pd.notna(row["Div/Share"]) else 0.0
                        updated.append({
                            "name":          _dh.iloc[orig_idx]["name"],
                            "google_ticker": _dh.iloc[orig_idx].get("google_ticker", ""),
                            "ticker":        _dh.iloc[orig_idx]["ticker"],
                            "shares":        _new_shares,
                            "amount":        round(_new_dps * _new_shares, 2),
                            "date":          pd.Timestamp(row["Date"]).isoformat() if pd.notna(row["Date"]) else _dh.iloc[orig_idx]["date"].isoformat(),
                        })
                    new_dh = pd.DataFrame(updated)
                    update_div_hist(new_dh)
                    st.rerun()

        # Compute year options here so the selectbox can live in the toolbar row
        _div_years        = sorted(div_hist["date"].dt.year.dropna().unique().astype(int), reverse=True) if div_hist is not None and not div_hist.empty else []
        _div_year_options = ["All"] + _div_years
        _div_year_default = _div_year_options.index(datetime.now().year) if datetime.now().year in _div_year_options else 0

        with st.container(horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            with st.container(horizontal=True, gap="small", width="content"):
                if st.button("Add", key="btn_add_div"):
                    _dlg_add_dividend()
                if st.button("Edit", key="btn_edit_div"):
                    _dlg_edit_dividends()
            selected_year = st.selectbox("Year", _div_year_options, index=_div_year_default,
                                         key="div_year_filter", label_visibility="collapsed",
                                         width=160)

        # Full dividend payment history
        if div_hist is not None and not div_hist.empty:

            hist_table = div_hist.copy()
            if selected_year != "All":
                hist_table = hist_table[hist_table["date"].dt.year == selected_year]
            hist_table = hist_table.sort_values("date", ascending=False).reset_index(drop=True)
            hist_shares = pd.to_numeric(hist_table.get("shares"), errors="coerce") if "shares" in hist_table.columns else None
            div_per_share = (hist_table["amount"] / hist_shares).round(4) if hist_shares is not None else None
            TAX_RATE = 0.30
            gross = hist_table["amount"]
            tax   = (gross * TAX_RATE).round(2)
            net   = (gross - tax).round(2)
            hist_display = pd.DataFrame({
                "Company":   hist_table["name"],
                "Ticker":    hist_table["ticker"],
                "Shares":    hist_shares if hist_shares is not None else None,
                "Div/Share": div_per_share if div_per_share is not None else None,
                "Gross":     gross,
                "Tax (30%)": tax,
                "Net":       net,
                "Date":      hist_table["date"].dt.strftime("%d-%m-%Y"),
            })
            st.dataframe(hist_display, width="stretch", hide_index=True,
                         height=(len(hist_display) + 1) * 35 + 10,
                         column_config={
                             "Company":   st.column_config.TextColumn("Company",   pinned=True,
                                              help="Company name"),
                             "Ticker":    st.column_config.TextColumn("Ticker",
                                              help="Exchange ticker symbol"),
                             "Shares":    st.column_config.NumberColumn("Shares",    format="%d",
                                              help="Number of shares held at the time of the dividend payment"),
                             "Div/Share": st.column_config.NumberColumn("Div/Share", format="€%.4f",
                                              help="Dividend per share = total amount ÷ shares"),
                             "Gross":     st.column_config.NumberColumn("Gross",     format="euro",
                                              help="Total gross dividend received before tax"),
                             "Tax (30%)": st.column_config.NumberColumn("Tax (30%)", format="euro",
                                              help="Belgian withholding tax estimated at 30% of gross dividend"),
                             "Net":       st.column_config.NumberColumn("Net",       format="euro",
                                              help="Net dividend after 30% withholding tax"),
                             "Date":      st.column_config.TextColumn("Date",
                                              help="Date the dividend was received or recorded"),
                         })

            st.divider()
            ch3, ch4 = st.columns(2)
            with ch3:
                st.subheader("Total received per stock")
                _div_clean = div_hist[div_hist["name"].astype(str).str.strip().isin(["", "nan", "None"]) == False]
                _static_bar(
                    _div_clean.groupby("name")["amount"].sum()
                              .sort_values(ascending=False),
                    color="#4caf80",
                )
            with ch4:
                st.subheader("Dividends by year")
                by_year = _div_clean.copy()
                by_year["year"] = by_year["date"].dt.year
                _yr_series = by_year.groupby("year")["amount"].sum().sort_index()
                _static_bar(_yr_series.rename(index=str), color="#4caf80")
        else:
            st.info("Re-upload your Excel file to load full dividend history.")

    # ── Sub-tab: Sold ─────────────────────────────────────────────────────────
    with sub_sold:
        sold = load_sold()
        if sold is None or sold.empty:
            st.info("No sold positions found in your portfolio file.")
        else:
            pv                     = pd.to_numeric(sold["purchase_value"], errors="coerce")
            sv                     = pd.to_numeric(sold["sale_value"], errors="coerce")
            sold["price_gain"]     = sv - pv
            sold["price_gain_pct"] = (sold["price_gain"] / pv * 100).round(2)
            sold["dividends"]      = pd.to_numeric(sold["dividends"], errors="coerce").fillna(0)
            sold["total_return"]   = sold["price_gain"] + sold["dividends"]
            sold["held_days"]      = (pd.to_datetime(sold["date_out"], format="mixed", dayfirst=False, errors="coerce") - pd.to_datetime(sold["date_in"], format="mixed", dayfirst=False, errors="coerce")).dt.days

            def _annual_return(row):
                if pd.isna(row["held_days"]) or row["held_days"] <= 0 or pv[row.name] <= 0:
                    return None
                total_value = sv[row.name] + row["dividends"]
                return ((total_value / pv[row.name]) ** (365 / row["held_days"]) - 1) * 100

            # Use pre-computed annual_return_pct if present, otherwise compute on the fly
            if "annual_return_pct" in sold.columns:
                _computed = sold.apply(_annual_return, axis=1)
                sold["annual_return_pct"] = sold["annual_return_pct"].combine_first(_computed).round(2)
            else:
                sold["annual_return_pct"] = sold.apply(_annual_return, axis=1).round(2)

            # Summary cards
            _pv_sum = pv.sum()
            _tr_sum = sold["total_return"].sum()
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Positions sold",  len(sold))
            s2.metric("Total invested",  f"€{_pv_sum:,.0f}")
            s3.metric("Total proceeds",  f"€{sv.sum():,.0f}")
            s4.metric("Realised return", f"€{_tr_sum:,.0f}",
                      delta=f"{_tr_sum / _pv_sum * 100:+.1f}%" if _pv_sum else "—")
            st.divider()

            # ── Edit sold dialog ──────────────────────────────────────────────
            @st.dialog("Edit realised positions", width="large")
            def _dlg_edit_sold():
                _sold_src = sold.sort_values("name", key=lambda s: s.str.lower()).reset_index()  # orig idx in 'index' col
                _tbl = pd.DataFrame({
                    "_idx":    _sold_src["index"],
                    "🗑️":      False,
                    "Company": _sold_src["name"],
                    "Shares":  pd.to_numeric(_sold_src["shares"], errors="coerce").fillna(0).astype(int),
                    "Proceeds (€)": pd.to_numeric(_sold_src["sale_value"], errors="coerce").fillna(0).round(2),
                    "Sell Date":    pd.to_datetime(_sold_src["date_out"], format="mixed", dayfirst=False, errors="coerce").dt.date,
                })

                _row_h  = 35
                _header = 35
                _height = _header + min(len(_tbl), 8) * _row_h

                _edited = st.data_editor(
                    _tbl.drop(columns="_idx"),
                    width="stretch",
                    hide_index=True,
                    num_rows="fixed",
                    height=_height,
                    column_config={
                        "🗑️":           st.column_config.CheckboxColumn("🗑️",            width=55),
                        "Company":      st.column_config.TextColumn("Company",           disabled=True, pinned=True),
                        "Shares":       st.column_config.NumberColumn("Shares",          min_value=1, step=1, format="%d"),
                        "Proceeds (€)": st.column_config.NumberColumn("Proceeds (€)",   min_value=0.0, format="%.2f"),
                        "Sell Date":    st.column_config.DateColumn("Sell Date",         format="DD/MM/YYYY"),
                    },
                    key="dlg_edit_sold_table",
                )

                to_delete  = _edited[_edited["🗑️"]].index.tolist()
                to_keep    = _edited[~_edited["🗑️"]]
                n_selected = len(to_delete)

                _del_note, _save_col = st.columns([3, 1])
                with _del_note:
                    if n_selected:
                        st.caption(f"{n_selected} selected for deletion")
                with _save_col:
                    if st.button("Save", key="dlg_edit_sold_save", width="stretch"):
                        _sold_updated = sold.copy()
                        for i, row in to_keep.iterrows():
                            orig_idx = int(_tbl.iloc[i]["_idx"])
                            _sold_updated.at[orig_idx, "shares"]     = max(1, int(row["Shares"]))
                            _sold_updated.at[orig_idx, "sale_value"] = round(float(row["Proceeds (€)"]), 2)
                            if pd.notna(row["Sell Date"]) and row["Sell Date"] is not None:
                                _sold_updated.at[orig_idx, "date_out"] = pd.Timestamp(row["Sell Date"]).isoformat()
                        if to_delete:
                            del_orig = [int(_tbl.iloc[i]["_idx"]) for i in to_delete]
                            _sold_updated.drop(index=del_orig, inplace=True)
                            _sold_updated.reset_index(drop=True, inplace=True)
                        save_sold(_sold_updated)
                        st.rerun()

            if st.button("Edit", key="btn_edit_sold"):
                _dlg_edit_sold()

            _sold_date_out = pd.to_datetime(sold["date_out"], format="mixed", dayfirst=False, errors="coerce")
            sold = sold.assign(_sort_date=_sold_date_out).sort_values("_sort_date", ascending=False)

            sold_table = pd.DataFrame({
                "Company":         sold["name"],
                "Ticker":          sold["ticker"],
                "Shares":          pd.to_numeric(sold["shares"], errors="coerce"),
                "Invested":        pd.to_numeric(sold["purchase_value"], errors="coerce"),
                "Proceeds":        pd.to_numeric(sold["sale_value"], errors="coerce"),
                "Price Gain":      sold["price_gain"],
                "Dividends":       sold["dividends"],
                "Price Gain %":    sold["price_gain_pct"],
                "Annual Return %": sold["annual_return_pct"],
                "Buy Date":        pd.to_datetime(sold["date_in"], format="mixed", dayfirst=False, errors="coerce").dt.strftime("%d-%m-%Y").fillna("—"),
                "Sell Date":       sold["_sort_date"].dt.strftime("%d-%m-%Y").fillna("—"),
            })

            _sold_sel_idx = _row_select_table(
                sold_table,
                key="pf_sold_table",
                width="stretch",
                hide_index=True,
                column_config={
                    "Company":         st.column_config.TextColumn("Company",           pinned=True,
                                           help="Company name"),
                    "Ticker":          st.column_config.TextColumn("Ticker",
                                           help="Exchange ticker symbol"),
                    "Shares":          st.column_config.NumberColumn("Shares",     format="%d",
                                           help="Number of shares sold"),
                    "Invested":        st.column_config.NumberColumn("Invested",   format="euro",
                                           help="Total amount originally invested (purchase price × shares)"),
                    "Proceeds":        st.column_config.NumberColumn("Proceeds",   format="euro",
                                           help="Total sale proceeds received"),
                    "Price Gain":      st.column_config.NumberColumn("Price Gain", format="€%+.0f",
                                           help="Absolute price gain/loss: proceeds − invested"),
                    "Dividends":       st.column_config.NumberColumn("Dividends",  format="euro",
                                           help="Total dividends collected while the position was held"),
                    "Price Gain %":    st.column_config.NumberColumn("Price Gain %",    format="%.2f%%",
                                           help="Price gain as a percentage of the original investment"),
                    "Annual Return %": st.column_config.NumberColumn("Annual Return %", format="%.2f%%",
                                           help="Annualised total return (price gain + dividends) using the CAGR formula over the holding period"),
                    "Buy Date":        st.column_config.TextColumn("Buy Date",
                                           help="Date the position was opened"),
                    "Sell Date":       st.column_config.TextColumn("Sell Date",
                                           help="Date the position was closed"),
                },
                height=(len(sold) + 1) * 35 + 10,
            )
            if _sold_sel_idx is not None:
                _sold_sel = sold_table["Ticker"].iloc[_sold_sel_idx]
                _sold_scr_row = _all_scr_df[_all_scr_df["Ticker"] == _sold_sel]
                if not _sold_scr_row.empty:
                    st.session_state["_dlg_open_ticker"] = _sold_sel
                    st.session_state["_dlg_open_src"]    = "pf_sold"
                    _pf_dlg_pending.append((_sold_scr_row.iloc[0], None))
            elif st.session_state.get("_dlg_open_src") == "pf_sold":
                if st.session_state.pop("_dlg_star_rerun", False):
                    _t = st.session_state.get("_dlg_open_ticker")
                    _r = _all_scr_df[_all_scr_df["Ticker"] == _t] if _t else pd.DataFrame()
                    if not _r.empty:
                        _pf_dlg_pending.append((_r.iloc[0], None))
                else:
                    st.session_state.pop("_dlg_open_ticker", None)
                    st.session_state.pop("_dlg_open_src", None)

            st.divider()
            st.subheader("Realised return per position")
            _static_bar(
                sold.dropna(subset=["name"])
                    .groupby("name")["total_return"].sum()
                    .sort_values(ascending=False)
            )

    # Dispatch at most one detail dialog per render
    if _pf_dlg_pending:
        _dlg_stock_detail(*_pf_dlg_pending[0])


# ══════════════════════════════════════════════════════════════════════════════
# PAGE — SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — HELP
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — PORTFOLIO RISK
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# NAVIGATION — st.navigation with st.page_link sidebar
# ══════════════════════════════════════════════════════════════════════════════

_pg_dashboard = st.Page(_page_dashboard_mod.render, title="Dashboard", icon=":material/dashboard:", default=True)
_pg_portfolio = st.Page(_page_portfolio, title="Portfolio", icon=":material/business_center:", url_path="portfolio")
_pg_risk      = st.Page(_page_risk_mod.render, title="Risk",  icon=":material/monitoring:",      url_path="risk")
_pg_screener  = st.Page(_page_screener,  title="Screener",  icon=":material/search:",          url_path="screener")
_pg_settings  = st.Page(_page_settings_mod.render, title="Settings", icon=":material/settings:",  url_path="settings")
_pg_help      = st.Page(_page_help_mod.render, title="Help",  icon=":material/help:",            url_path="help")

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
_legacy_pages = {"dashboard": _pg_dashboard, "portfolio": _pg_portfolio,
                 "risk": _pg_risk, "screener": _pg_screener,
                 "settings": _pg_settings, "help": _pg_help}
_legacy_page = st.query_params.get("page", "")
if _legacy_page:
    del st.query_params["page"]
    if _legacy_page in _legacy_pages:
        st.switch_page(_legacy_pages[_legacy_page])

with st.sidebar:
    st.markdown(f"""
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

