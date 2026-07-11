"""Watchlist page — tickers not currently held, tracked separately from the
screener's per-exchange lists. Promoted out of uvalu/pages_/screener.py's
former "Watchlist" tab into its own top-bar nav entry (Phase 1)."""
import pandas as pd
import yfinance as yf
import streamlit as st

from portfolio import (load_watchlist, save_watchlist,
                       load_manual_tickers, save_manual_tickers)
from settings import load_shared_settings, ALL_EXCHANGES
from uvalu.data import _load_all_screener_data, _cache_version
from uvalu.components import signal_badge_for_decision, signal_badge_html, fair_value_bar_compact
from uvalu.stock_dialog import _dlg_stock_detail
from uvalu.ui import _row_select_table


def render() -> None:
    st.subheader("Watchlist")
    st.caption("Track tickers you don't hold yet. Add from a stock's details "
               "with the ★ toggle, or type a symbol directly below.")

    watchlist = load_watchlist()
    _settings = load_shared_settings()
    _enabled  = tuple(_settings.get("enabled_exchanges", ALL_EXCHANGES))
    _manual_tickers_map  = load_manual_tickers()
    df, df_ams, df_par, df_mil, df_etr, df_swx, extra_df = _load_all_screener_data(
        _cache_version(), _enabled, tuple(_manual_tickers_map.keys()), tuple(_manual_tickers_map.values()))
    all_df = pd.concat([df, df_ams, df_par, df_mil, df_etr, df_swx, extra_df], ignore_index=True)

    # ── Add ticker form ─────────────────────────────────────────────────────
    with st.form("wl_add_form", border=True, clear_on_submit=True):
        _c1, _c2, _c3 = st.columns([2, 3, 1], vertical_alignment="bottom")
        with _c1:
            _new_ticker = st.text_input("Ticker", placeholder="e.g. AAPL, 7203.T, BP.L")
        with _c2:
            _new_name = st.text_input("Company name (optional)", placeholder="Apple Inc.")
        with _c3:
            _submitted = st.form_submit_button("Add ticker", width="stretch")

    if _submitted:
        _sym = _new_ticker.strip().upper()
        if not _sym:
            st.error("Enter a ticker symbol.")
        else:
            try:
                _info = yf.Ticker(_sym).info
                _name = _new_name.strip() or _info.get("shortName") or _info.get("longName") or _sym
                if not _info.get("regularMarketPrice") and not _info.get("currentPrice"):
                    st.error(f"Ticker **{_sym}** not found. Check the symbol and try again.")
                else:
                    _mt = load_manual_tickers()
                    _mt[_sym] = _name
                    save_manual_tickers(_mt)
                    save_watchlist(watchlist | {_sym})
                    st.rerun()
            except Exception:
                st.error(f"Ticker **{_sym}** not found. Check the symbol and try again.")

    # ── Results table ────────────────────────────────────────────────────────
    wl_df = all_df[all_df["Ticker"].isin(watchlist)].reset_index(drop=True)
    if wl_df.empty:
        st.info("Your watchlist is empty. Add a ticker above to start tracking it.")
        return

    display_df = pd.DataFrame({
        "Company":  wl_df["Name"],
        "Ticker":   wl_df["Ticker"],
        "Signal":   wl_df.apply(lambda r: signal_badge_for_decision(r.get("Decision", ""))[1], axis=1),
        "Score":    wl_df.get("Value Score"),
        "MoS %":    wl_df.get("MoS %"),
        "Price":    wl_df.get("Price"),
        "P/E":      wl_df.get("trailingPE"),
        "Div Yield": wl_df.get("dividendYield"),
    })

    _row_h, _header = 35, 38
    _height = min(_header + len(display_df) * _row_h + 4, 600)
    _sel_idx = _row_select_table(
        display_df, key="watchlist_table", width="stretch", hide_index=True,
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
        _sel_ticker = wl_df.iloc[_sel_idx]
        _dlg_stock_detail(_sel_ticker, None)

    with st.expander("Remove tickers"):
        _to_remove = st.multiselect("Select tickers to remove", options=sorted(watchlist), key="wl_remove_sel")
        if _to_remove and st.button("Remove selected", key="wl_remove_btn"):
            save_watchlist(watchlist - set(_to_remove))
            st.rerun()
