"""Value screener page — per-exchange tabs, watchlist, column groups, filters."""
import pandas as pd
import yfinance as yf
import streamlit as st

from portfolio import (load_portfolio, load_watchlist, save_watchlist,
                       load_manual_tickers, save_manual_tickers, add_position)
from settings import load_shared_settings, ALL_EXCHANGES
from screener import get_fetch_progress, _load_cache
from fetch_tickers import (_hardcoded_bel20, _hardcoded_aex25, _hardcoded_cac40,
                           _hardcoded_ftse_mib, _hardcoded_dax40, _hardcoded_smi20)
from uvalu.data import _load_all_screener_data, _cache_version, _bust_cache
from uvalu.formatting import (COLUMN_HELP, fmt_div_flag as _fmt_div_flag,
                              f_str as _f_str)
from uvalu.runtime import current_user
from uvalu.stock_dialog import _dlg_stock_detail
from uvalu.ui import _row_select_table, _auto_rerun


def render() -> None:
    # Per-run state (module was split out of app.py)
    _is_admin = current_user().is_admin
    watchlist = load_watchlist()
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
        "Sector":        st.column_config.TextColumn("Sector",      width=150, help=_ch("Sector")),
        "Country":       st.column_config.TextColumn("Country",     width=120, help=_ch("Country")),
        "Ex-Div Date":   st.column_config.TextColumn("Ex-Div Date", width=105, help=_ch("Ex-Div Date")),
        "Div Date":      st.column_config.TextColumn("Div Date",    width=95,  help=_ch("Div Date")),
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
