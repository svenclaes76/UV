"""Value screener page — one unified ranked list across enabled exchanges,
with a filter bar (search, signal, sector, market, score/MoS sliders, hide-
owned toggle), matching the Uvalu.dc.html mockup. Full replacement of the
former per-exchange-tabs + column-groups layout (Watchlist moved to its own
page in Phase 1; column-group customization is covered by the Analysis page
now, same call the abandoned redesign-v2 branch made for this exact page)."""
import pandas as pd
import streamlit as st

from portfolio import (load_portfolio, load_manual_tickers, load_watchlist,
                       save_watchlist, save_manual_tickers)
from settings import load_shared_settings, get_veto_thresholds, ALL_EXCHANGES
from screener import get_fetch_progress, _load_cache
from uvalu.data import _load_all_screener_data, _cache_version, _bust_cache
from uvalu.drawer import open_drawer
from uvalu.components import signal_badge_for_decision, stock_row, empty_results_html
from uvalu.ui import _auto_rerun

_EXCHANGE_LABELS = {
    "brussels": "Brussels", "amsterdam": "Amsterdam", "paris": "Paris",
    "milan": "Milan", "frankfurt": "Frankfurt", "swiss": "Swiss",
}
_SIGNAL_CHIPS = ["BUY", "MONITOR", "AVOID", "VETO"]

# Sortable columns, matching Uvalu.dc.html's colDefs/keyf exactly — key is
# what's stored in session state, column is the DataFrame column it sorts by.
# "signal" has no direct column (it's derived per-row via
# signal_badge_for_decision), so it's computed into _signal_label just before
# sorting rather than kept on every row all the time.
_SORT_COLUMNS = [
    ("name",   "Position",        "Name"),
    ("signal", "Signal",          "_signal_label"),
    ("score",  "Composite score", "Value Score"),
    ("mos",    "Upside",          "MoS %"),
    ("price",  "Price",           "Price"),
    ("pe",     "P/E",             "trailingPE"),
    ("dy",     "Yield",           "dividendYield"),
]


def _sort_by(key: str) -> None:
    """Click a header: same column toggles asc/desc, a different column
    switches to it defaulting to desc — matches Uvalu.dc.html's sortBy()."""
    _cur_key = st.session_state.get("scr_sort_key", "score")
    _cur_dir = st.session_state.get("scr_sort_dir", "desc")
    if _cur_key == key:
        st.session_state["scr_sort_dir"] = "asc" if _cur_dir == "desc" else "desc"
    else:
        st.session_state["scr_sort_key"] = key
        st.session_state["scr_sort_dir"] = "desc"


def _scr_header_css(active_key: str) -> str:
    return f"""
[class*="st-key-scr_sort_"] button {{
  background: transparent !important; border: none !important; padding: 0 !important;
  min-height: unset !important; font-size: 10px !important; letter-spacing: 0.06em !important;
  text-transform: uppercase !important; color: var(--faint) !important; font-weight: 400 !important;
}}
[class*="st-key-scr_sort_"] button:hover {{ color: var(--text) !important; }}
.st-key-scr_sort_{active_key} button {{ color: var(--text) !important; font-weight: 500 !important; }}
"""


def render() -> None:
    _settings = load_shared_settings()
    _enabled  = tuple(_settings.get("enabled_exchanges", ALL_EXCHANGES))
    _manual_tickers_map  = load_manual_tickers()
    dfs = _load_all_screener_data(
        _cache_version(), _enabled, tuple(_manual_tickers_map.keys()), tuple(_manual_tickers_map.values()),
        get_veto_thresholds())
    *_exch_dfs, _ = dfs  # extra (portfolio-only) tickers aren't shown in the ranked list
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

    # ── Heading — filled in after filters are computed so the "Export list"
    # button (which needs the filtered set) can sit in the header row like
    # the mockup, instead of further down the page. ───────────────────────────
    _valued_df = _all_df[_all_df["fair_value"].notna()].reset_index(drop=True) if not _all_df.empty else _all_df
    _header_slot = st.empty()

    if _valued_df.empty:
        with _header_slot.container():
            st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Value screener</div>',
                       unsafe_allow_html=True)
        st.info("No screener data available yet.")
        return

    # ── Filter bar ───────────────────────────────────────────────────────────
    _f1, _f2 = st.columns([2, 1])
    with _f1:
        _search = st.text_input("Search", placeholder="Ticker or company…",
                                key="scr_search", label_visibility="collapsed")
    with _f2:
        _signal = st.pills("Signal", options=_SIGNAL_CHIPS, selection_mode="multi",
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
        # A single-option st.pills reads as a clickable dot+label pill (same
        # widget already used for the Signal filter chips above), matching
        # Uvalu.dc.html's heldStyle/heldDot instead of a native toggle switch.
        _hide_owned = bool(st.pills("Hide positions I own", options=["Hide positions I own"],
                                    selection_mode="multi", key="scr_hide_owned",
                                    label_visibility="collapsed"))

    # ── Apply filters ──────────────────────────────────────────────────────────
    _filtered = _valued_df.copy()
    if _search:
        _q = _search.strip().lower()
        _filtered = _filtered[
            _filtered["Ticker"].str.lower().str.contains(_q, na=False) |
            _filtered["Name"].str.lower().str.contains(_q, na=False)
        ]
    if _signal:
        _filtered = _filtered[_filtered.apply(
            lambda r: signal_badge_for_decision(r.get("Decision", ""), veto=bool(r.get("veto")))[1] in _signal,
            axis=1)]
    if _sector_sel and _sector_sel != "All sectors":
        _filtered = _filtered[_filtered.get("sector") == _sector_sel]
    if _market_sel and _market_sel != "All markets":
        _filtered = _filtered[_filtered["Exchange"] == _market_sel]
    _filtered = _filtered[pd.to_numeric(_filtered["Value Score"], errors="coerce").fillna(0) >= _min_score]
    _filtered = _filtered[pd.to_numeric(_filtered["MoS %"], errors="coerce").fillna(-999) >= _min_mos]
    if _hide_owned:
        _filtered = _filtered[~_filtered["Ticker"].isin(_held_tickers)]

    _sort_key = st.session_state.get("scr_sort_key", "score")
    _sort_dir = st.session_state.get("scr_sort_dir", "desc")
    if _sort_key == "signal":
        _filtered["_signal_label"] = _filtered.apply(
            lambda r: signal_badge_for_decision(str(r.get("Decision", "")), veto=bool(r.get("veto")))[1], axis=1)
    _sort_col = next(c for k, _, c in _SORT_COLUMNS if k == _sort_key)
    _filtered = _filtered.sort_values(
        _sort_col, ascending=(_sort_dir == "asc"), na_position="last").reset_index(drop=True)

    _csv = _filtered[["Ticker", "Name", "Exchange", "Decision", "Value Score", "Price",
                      "fair_value", "MoS %", "trailingPE", "dividendYield"]].to_csv(index=False)

    with _header_slot.container():
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            with st.container(width="content"):
                st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Value screener</div>',
                           unsafe_allow_html=True)
                st.caption(f"**{len(_filtered)}** of {len(_valued_df)} European stocks pass your filters · "
                          "ranked by composite signal score.")
            with st.container(horizontal=True, gap="small", width="content"):
                if st.button("Reset filters", key="scr_reset"):
                    for _k in ("scr_search", "scr_signal", "scr_sector", "scr_market",
                              "scr_min_score", "scr_min_mos", "scr_hide_owned"):
                        st.session_state.pop(_k, None)
                    st.rerun()
                st.download_button("Export list", data=_csv, file_name="uvalu_screener.csv",
                                   mime="text/csv", key="scr_export")

    if _filtered.empty:
        with st.container(border=True):
            st.markdown(empty_results_html(
                "No stocks match these filters. Try loosening the score or margin-of-safety threshold."),
                unsafe_allow_html=True)
        return

    # ── Column headers — clickable, sortable (matches Uvalu.dc.html's
    # sortBy()/arrow header spec instead of a hardcoded Value-Score-desc sort)
    _watchlist = load_watchlist()
    st.markdown(f"<style>{_scr_header_css(_sort_key)}</style>", unsafe_allow_html=True)
    _sortable = {k: (label, col) for k, label, col in _SORT_COLUMNS}
    _hh_widths = [0.4, 0.4, 2.3, 0.9, 1.3, 0.9, 0.8, 0.7, 0.8, 0.5]
    _hh_cols = st.columns(_hh_widths, vertical_alignment="center")
    _hh_slots = ("", "#", "name", "signal", "score", "mos", "price", "pe", "dy", "")
    for _hh, _slot in zip(_hh_cols, _hh_slots):
        if _slot in _sortable:
            _label, _ = _sortable[_slot]
            _arrow = (" ↓" if _sort_dir == "desc" else " ↑") if _sort_key == _slot else ""
            with _hh:
                st.button(_label + _arrow, key=f"scr_sort_{_slot}", type="tertiary",
                         on_click=_sort_by, args=(_slot,))
        elif _slot == "#":
            with _hh:
                st.markdown('<span style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                           'color:var(--faint);">#</span>', unsafe_allow_html=True)

    _drawer_target = None
    for _ridx, _row in _filtered.iterrows():
        _ticker = _row["Ticker"]
        _in_wl = _ticker in _watchlist
        _result = stock_row(
            key=f"scr_row_{_ridx}_{_ticker}",
            ticker=_ticker, name=_row.get("Name", ""), exchange=_row.get("Exchange"),
            decision=str(_row.get("Decision", "")), veto=bool(_row.get("veto")),
            score=_row.get("Value Score"), mos_pct=_row.get("MoS %"), price=_row.get("Price"),
            pe=_row.get("trailingPE"), div_yield=_row.get("dividendYield"), rank=_ridx + 1,
            action_active=_in_wl,
            action_help="Remove from watchlist" if _in_wl else "Add to watchlist",
        )
        if _result["action"]:
            if _in_wl:
                save_watchlist(_watchlist - {_ticker})
                _mt = load_manual_tickers()
                if _ticker in _mt:
                    del _mt[_ticker]
                    save_manual_tickers(_mt)
            else:
                save_watchlist(_watchlist | {_ticker})
            st.rerun()
        if _result["view"]:
            _drawer_target = _ticker

    if _drawer_target is not None:
        _r = _filtered[_filtered["Ticker"] == _drawer_target]
        if not _r.empty:
            open_drawer(_r.iloc[0], _scr_pf_context)
    else:
        _reopen = st.session_state.get("_drw_reopen_ticker")
        if _reopen:
            _r = _all_df[_all_df["Ticker"] == _reopen]
            if not _r.empty:
                st.session_state.pop("_drw_reopen_ticker", None)
                open_drawer(_r.iloc[0], _scr_pf_context)
