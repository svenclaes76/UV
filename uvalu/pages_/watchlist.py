"""Watchlist page — tickers not currently held, tracked separately from the
screener's per-exchange lists. Promoted out of uvalu/pages_/screener.py's
former "Watchlist" tab into its own top-bar nav entry (Phase 1)."""
import pandas as pd
import yfinance as yf
import streamlit as st

from portfolio import (load_watchlist, save_watchlist,
                       load_manual_tickers, save_manual_tickers)
from settings import load_shared_settings, get_veto_thresholds, ALL_EXCHANGES
from uvalu.data import _load_all_screener_data, _cache_version
from uvalu.components import stock_row, empty_results_html
from uvalu.drawer import open_drawer

_EXCHANGE_LABELS = {
    "brussels": "Brussels", "amsterdam": "Amsterdam", "paris": "Paris",
    "milan": "Milan", "frankfurt": "Frankfurt", "swiss": "Swiss",
}


def render() -> None:
    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Watchlist</div>',
               unsafe_allow_html=True)
    st.caption("Track tickers you don't hold yet. Add from the screener with the star, "
              "or type a symbol directly below.")

    watchlist = load_watchlist()
    _settings = load_shared_settings()
    _enabled  = tuple(_settings.get("enabled_exchanges", ALL_EXCHANGES))
    _manual_tickers_map  = load_manual_tickers()
    _exch_dfs = _load_all_screener_data(
        _cache_version(), _enabled, tuple(_manual_tickers_map.keys()), tuple(_manual_tickers_map.values()),
        get_veto_thresholds())
    *_per_exchange, extra_df = _exch_dfs
    all_df = pd.concat([
        d.assign(Exchange=_EXCHANGE_LABELS.get(k, k))
        for k, d in zip(ALL_EXCHANGES, _per_exchange)
    ] + [extra_df], ignore_index=True)

    # ── Add ticker form ─────────────────────────────────────────────────────
    with st.form("wl_add_form", border=True, clear_on_submit=True):
        _c1, _c2, _c3 = st.columns([2, 3, 1], vertical_alignment="bottom")
        with _c1:
            _new_ticker = st.text_input("Ticker", placeholder="TTE.PA")
        with _c2:
            _new_name = st.text_input("Company name (optional)", placeholder="TotalEnergies")
        with _c3:
            _submitted = st.form_submit_button("Add ticker", width="stretch")

    if _submitted:
        _sym = _new_ticker.strip().upper()
        if not _sym:
            st.markdown('<div style="font-size:12px;color:var(--down-txt);">Enter a ticker symbol.</div>',
                       unsafe_allow_html=True)
        else:
            try:
                _info = yf.Ticker(_sym).info
                _name = _new_name.strip() or _info.get("shortName") or _info.get("longName") or _sym
                if not _info.get("regularMarketPrice") and not _info.get("currentPrice"):
                    st.markdown(f'<div style="font-size:12px;color:var(--down-txt);">Ticker <b>{_sym}</b> not '
                               f'found. Check the symbol and try again.</div>', unsafe_allow_html=True)
                else:
                    _mt = load_manual_tickers()
                    _mt[_sym] = _name
                    save_manual_tickers(_mt)
                    save_watchlist(watchlist | {_sym})
                    st.rerun()
            except Exception:
                st.markdown(f'<div style="font-size:12px;color:var(--down-txt);">Ticker <b>{_sym}</b> not '
                           f'found. Check the symbol and try again.</div>', unsafe_allow_html=True)

    # ── Results list ─────────────────────────────────────────────────────────
    wl_df = all_df[all_df["Ticker"].isin(watchlist)].reset_index(drop=True)
    if wl_df.empty:
        with st.container(border=True):
            st.markdown(empty_results_html(
                "Your watchlist is empty. Star a ticker in the screener or add one above."),
                unsafe_allow_html=True)
        return

    # 8 widths matching stock_row's show_action=False/show_remove=True layout
    # exactly (7 data cols + trailing remove, no leading icon at all —
    # Uvalu.dc.html's watchlist rows start directly with Company — and no
    # trailing view-arrow column, since the whole ticker/name cell is the
    # click target now) — a mismatched count here silently shifts every
    # header label one column off from the row data beneath it.
    _hh_widths = [3.0, 1.0, 1.5, 1.0, 0.9, 0.8, 0.9, 0.4]
    # Upside/Price/P-E/Yield are right-aligned (matching their own
    # right-aligned data cells in stock_row); Position/Signal/Composite
    # score stay left-aligned like their left-anchored cells.
    _hh_right = {"Upside", "Price", "P/E", "Yield"}

    with st.container(key="wl_table_card", border=True):
        with st.container(key="wl_col_header"):
            _hh_cols = st.columns(_hh_widths, vertical_alignment="center")
            for _hh, _label in zip(_hh_cols, ("Position", "Signal", "Composite score",
                                             "Upside", "Price", "P/E", "Yield", "")):
                if _label:
                    _align = "right" if _label in _hh_right else "left"
                    with _hh:
                        st.markdown(f'<div style="text-align:{_align};font-size:10px;letter-spacing:0.06em;'
                                   f'text-transform:uppercase;color:var(--faint);">{_label}</div>',
                                   unsafe_allow_html=True)

        _drawer_target = None
        for _ridx, _row in wl_df.iterrows():
            _ticker = _row["Ticker"]
            _result = stock_row(
                key=f"wl_row_{_ridx}_{_ticker}",
                ticker=_ticker, name=_row.get("Name", ""), exchange=_row.get("Exchange"),
                decision=str(_row.get("Decision", "")), veto=bool(_row.get("veto")),
                score=_row.get("Value Score"), mos_pct=_row.get("MoS %"), price=_row.get("Price"),
                pe=_row.get("trailingPE"), div_yield=_row.get("dividendYield"),
                show_action=False, show_remove=True, remove_help="Remove from watchlist",
            )
            if _result["remove"]:
                save_watchlist(watchlist - {_ticker})
                st.rerun()
            if _result["view"]:
                _drawer_target = _ticker

    if _drawer_target is not None:
        _r = wl_df[wl_df["Ticker"] == _drawer_target]
        if not _r.empty:
            open_drawer(_r.iloc[0], None)
