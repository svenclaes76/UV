"""Value screener page — one unified ranked list across enabled exchanges,
with a filter bar (search, signal, sector, market, score/MoS sliders, hide-
owned toggle), matching the Uvalu.dc.html mockup. Full replacement of the
former per-exchange-tabs + column-groups layout (Watchlist moved to its own
page in Phase 1; column-group customization is covered by the Analysis page
now, same call the abandoned redesign-v2 branch made for this exact page)."""
import pandas as pd
import streamlit as st

from portfolio import load_portfolio, load_manual_tickers, add_position
from settings import load_shared_settings, get_veto_thresholds, ALL_EXCHANGES
from screener import get_fetch_progress, _load_cache
from uvalu.data import _load_all_screener_data, _cache_version, _bust_cache
from uvalu.drawer import open_drawer
from uvalu.components import signal_badge_for_decision
from uvalu.runtime import current_user
from uvalu.ui import _row_select_table, _auto_rerun

_EXCHANGE_LABELS = {
    "brussels": "Brussels", "amsterdam": "Amsterdam", "paris": "Paris",
    "milan": "Milan", "frankfurt": "Frankfurt", "swiss": "Swiss",
}
_SIGNAL_CHIPS = ["All", "Buy", "Monitor", "Avoid"]
_DECISION_MAP = {"Buy": "Strong Buy", "Monitor": "Monitor", "Avoid": "Avoid"}


def render() -> None:
    _settings = load_shared_settings()
    _enabled  = tuple(_settings.get("enabled_exchanges", ALL_EXCHANGES))
    _manual_tickers_map  = load_manual_tickers()
    dfs = _load_all_screener_data(
        _cache_version(), _enabled, tuple(_manual_tickers_map.keys()), tuple(_manual_tickers_map.values()),
        get_veto_thresholds())
    *_exch_dfs, _scr_extra_df = dfs
    _exch_keys = [k for k in ALL_EXCHANGES if k in set(_enabled)]

    if not _exch_dfs[0].empty and ("fair_value" not in _exch_dfs[0].columns or "Decision" not in _exch_dfs[0].columns):
        _bust_cache()

    _any_data = any(not d.empty for d in _exch_dfs)
    _prog = get_fetch_progress()
    if _prog["running"] and _prog["total"] > 0:
        _pct = _prog["done"] / _prog["total"]
        st.caption(f"🔄 Updating data… {_prog['done']}/{_prog['total']} tickers ({int(_pct*100)}%)")
        _auto_rerun(5, "screener_fetch_refresh")
    elif not _any_data:
        _auto_rerun(5, "screener_fetch_refresh")

    _all_df = pd.concat([
        d.assign(Exchange=_EXCHANGE_LABELS.get(k, k))
        for k, d in zip(_exch_keys, _exch_dfs)
    ], ignore_index=True) if _exch_dfs else pd.DataFrame()

    # ── Portfolio fit context (sector/country/beta weights) ──────────────────
    _scr_pf_context: dict | None = None
    _scr_pf = load_portfolio()
    _held_tickers: set[str] = set()
    if _scr_pf is not None and not _scr_pf.empty:
        _held_tickers = set(_scr_pf["ticker"].dropna().astype(str))
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
        _missing_country = _pf_m["country"].isna()
        if _missing_country.any():
            _pf_m.loc[_missing_country, "country"] = _pf_m.loc[_missing_country, "ticker"].apply(
                lambda t: next((c for s, c in _suffix_to_country.items() if str(t).endswith(s)), None)
            )
        _pf_m["_val"] = (
            pd.to_numeric(_pf_m["shares"], errors="coerce") *
            pd.to_numeric(_pf_m["Price"], errors="coerce")
        )
        _missing_val = _pf_m["_val"].isna()
        if _missing_val.any():
            if "purchase_value" in _pf_m.columns:
                _pf_m.loc[_missing_val, "_val"] = pd.to_numeric(
                    _pf_m.loc[_missing_val, "purchase_value"], errors="coerce")
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

    # ── Buy dialog ─────────────────────────────────────────────────────────────
    _scr_sorted = _all_df[["Ticker", "Name"]].drop_duplicates("Ticker").sort_values(
        "Name", key=lambda s: s.str.lower()) if not _all_df.empty else pd.DataFrame(columns=["Ticker", "Name"])
    _scr_t_opts   = _scr_sorted["Ticker"].tolist()
    _scr_t_labels = {r["Ticker"]: f"{r['Name']}  ({r['Ticker']})" for _, r in _scr_sorted.iterrows()}
    _scr_price_map = _all_df.drop_duplicates("Ticker").set_index("Ticker")["Price"].to_dict() if not _all_df.empty else {}

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
            _price = float(_scr_price_map.get(ticker) or 0.0)
            total_price = st.number_input("Invested (€)", min_value=0.0, step=0.01,
                                          value=round(_price * shares, 2), format="%.2f")
        _, _save_btn = st.columns([3, 1])
        with _save_btn:
            _do_save = st.button("Save", key="dlg_buy_scr_save", width="stretch")
        if _do_save and shares > 0 and total_price > 0:
            name = _scr_t_labels.get(ticker, ticker).split("  (")[0]
            add_position({
                "name": name, "google_ticker": "", "ticker": ticker, "shares": shares,
                "purchase_price": round(total_price / shares, 4), "purchase_value": round(total_price, 2),
                "target_price": None, "dividends": 0.0,
                "date_in": pd.Timestamp(pur_date).isoformat(), "account": "",
            })
            st.rerun()

    # ── Heading ───────────────────────────────────────────────────────────────
    _valued_df = _all_df[_all_df["fair_value"].notna()].reset_index(drop=True) if not _all_df.empty else _all_df
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
        with st.container(width="content"):
            st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Value screener</div>',
                       unsafe_allow_html=True)
            st.caption(f"{len(_valued_df)} European stocks with a fair-value estimate · "
                      "ranked by composite signal score.")
        with st.container(horizontal=True, gap="small", width="content"):
            if st.button("Reset filters", key="scr_reset"):
                for _k in ("scr_search", "scr_signal", "scr_sector", "scr_market",
                          "scr_min_score", "scr_min_mos", "scr_hide_owned"):
                    st.session_state.pop(_k, None)
                st.rerun()
            if st.button("Refresh", key="scr_refresh"):
                _bust_cache()
            _is_viewer = current_user().is_viewer
            if _scr_t_opts and st.button("Buy", key="scr_buy", type="primary", disabled=_is_viewer,
                                        help="Viewer role is read-only" if _is_viewer else None):
                _dlg_buy_screener()

    if _valued_df.empty:
        st.info("No screener data available yet.")
        return

    # ── Filter bar ───────────────────────────────────────────────────────────
    _f1, _f2 = st.columns([2, 1])
    with _f1:
        _search = st.text_input("Search", placeholder="Search by ticker or company name…",
                                key="scr_search", label_visibility="collapsed")
    with _f2:
        _signal = st.segmented_control("Signal", options=_SIGNAL_CHIPS, default="All",
                                       key="scr_signal", label_visibility="collapsed")

    _sector_vals = sorted(v for v in _valued_df.get("sector", pd.Series(dtype=object)).dropna().unique() if str(v).strip())
    _market_vals = [_EXCHANGE_LABELS[k] for k in _exch_keys]

    _c1, _c2, _c3, _c4, _c5 = st.columns([1.2, 1.2, 1.4, 1.4, 1.2])
    with _c1:
        _sector_sel = st.selectbox("Sector", options=["All sectors"] + _sector_vals, key="scr_sector")
    with _c2:
        _market_sel = st.selectbox("Market", options=["All markets"] + _market_vals, key="scr_market")
    with _c3:
        _min_score = st.slider("Min score", 0, 90, 0, step=5, key="scr_min_score")
    with _c4:
        _min_mos = st.slider("Min margin of safety", -20, 50, -20, step=5, key="scr_min_mos")
    with _c5:
        st.container(height=28, border=False)
        _hide_owned = st.toggle("Hide positions I own", key="scr_hide_owned")

    # ── Apply filters ──────────────────────────────────────────────────────────
    _filtered = _valued_df.copy()
    if _search:
        _q = _search.strip().lower()
        _filtered = _filtered[
            _filtered["Ticker"].str.lower().str.contains(_q, na=False) |
            _filtered["Name"].str.lower().str.contains(_q, na=False)
        ]
    if _signal and _signal != "All":
        _filtered = _filtered[_filtered["Decision"] == _DECISION_MAP[_signal]]
    if _sector_sel and _sector_sel != "All sectors":
        _filtered = _filtered[_filtered.get("sector") == _sector_sel]
    if _market_sel and _market_sel != "All markets":
        _filtered = _filtered[_filtered["Exchange"] == _market_sel]
    _filtered = _filtered[pd.to_numeric(_filtered["Value Score"], errors="coerce").fillna(0) >= _min_score]
    _filtered = _filtered[pd.to_numeric(_filtered["MoS %"], errors="coerce").fillna(-999) >= _min_mos]
    if _hide_owned:
        _filtered = _filtered[~_filtered["Ticker"].isin(_held_tickers)]

    _filtered = _filtered.sort_values("Value Score", ascending=False).reset_index(drop=True)

    if _filtered.empty:
        st.info("No stocks match your current filters.")
        return

    st.caption(f"**{len(_filtered)}** of {len(_valued_df)} stocks pass your filters · click a row to view details")

    _csv = _filtered[["Ticker", "Name", "Exchange", "Decision", "Value Score", "Price",
                      "fair_value", "MoS %", "trailingPE", "dividendYield"]].to_csv(index=False)
    st.download_button("Export list", data=_csv, file_name="uvalu_screener.csv", mime="text/csv",
                       key="scr_export")

    display_df = pd.DataFrame({
        "Company":   _filtered["Name"],
        "Ticker":    _filtered["Ticker"],
        "Market":    _filtered["Exchange"],
        "Signal":    _filtered.apply(lambda r: signal_badge_for_decision(r.get("Decision", ""))[1], axis=1),
        "Score":     _filtered["Value Score"],
        "MoS %":     _filtered["MoS %"],
        "Price":     _filtered["Price"],
        "P/E":       _filtered.get("trailingPE"),
        "Div Yield": _filtered.get("dividendYield"),
    })

    _row_h, _header = 35, 38
    _height = min(_header + len(display_df) * _row_h + 4, 800)
    _sel_idx = _row_select_table(
        display_df, key="screener_table", width="stretch", hide_index=True,
        column_config={
            "Score":     st.column_config.NumberColumn("Score", format="%.1f"),
            "MoS %":     st.column_config.NumberColumn("MoS %", format="%+.1f%%"),
            "Price":     st.column_config.NumberColumn("Price", format="euro"),
            "P/E":       st.column_config.NumberColumn("P/E", format="%.1f"),
            "Div Yield": st.column_config.NumberColumn("Div Yield", format="percent"),
        },
        height=_height,
    )

    if _sel_idx is not None:
        open_drawer(_filtered.iloc[_sel_idx], _scr_pf_context)
    else:
        _reopen = st.session_state.get("_drw_reopen_ticker")
        if _reopen:
            _r = _all_df[_all_df["Ticker"] == _reopen]
            if not _r.empty:
                st.session_state.pop("_drw_reopen_ticker", None)
                open_drawer(_r.iloc[0], _scr_pf_context)
