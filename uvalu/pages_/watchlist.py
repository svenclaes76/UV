"""Watchlist page — tickers not currently held, tracked separately from the
screener's per-exchange lists. Promoted out of uvalu/pages_/screener.py's
former "Watchlist" tab into its own top-bar nav entry (Phase 1)."""
import pandas as pd
import yfinance as yf
import streamlit as st

from portfolio import (load_watchlist, save_watchlist,
                       load_manual_tickers, save_manual_tickers)
from settings import load_shared_settings, get_veto_thresholds, get_score_weights, ALL_EXCHANGES
from uvalu.data import _load_all_screener_data, _cache_version
from uvalu.components import stock_row, empty_results_html, skeleton_rows
from uvalu.drawer import open_drawer
from uvalu.runtime import current_user
from uvalu.ui import poll_while_fetching

_EXCHANGE_LABELS = {
    "brussels": "Brussels", "amsterdam": "Amsterdam", "paris": "Paris",
    "milan": "Milan", "frankfurt": "Frankfurt", "swiss": "Swiss",
}

# 8 widths matching stock_row's show_action=True layout exactly (star, then
# the 7 shared data columns) — shared by the real column header, the real
# rows (stock_row), and the loading skeleton's column-header/rows so all
# three always stay pixel-aligned.
_HH_WIDTHS = [0.5, 3.0, 1.0, 1.5, 1.0, 0.9, 0.8, 0.9]
_HH_LABELS = ("", "Position", "Signal", "Composite score", "Margin of safety", "Price", "P/E", "Yield")
# Upside/Price/P-E/Yield are right-aligned (matching their own right-aligned
# data cells in stock_row); Position/Signal/Composite score stay left-aligned
# like their left-anchored cells.
_HH_RIGHT = {"Margin of safety", "Price", "P/E", "Yield"}


def _col_header() -> None:
    """The real column-header row — shared by the loaded results table and
    the loading skeleton (labels are static text, no reason to shimmer
    them)."""
    for _hh, _label in zip(st.columns(_HH_WIDTHS, vertical_alignment="center"), _HH_LABELS):
        if _label:
            _align = "right" if _label in _HH_RIGHT else "left"
            with _hh:
                st.markdown(f'<div style="text-align:{_align};font-size:10px;letter-spacing:0.06em;'
                           f'text-transform:uppercase;color:var(--faint);">{_label}</div>',
                           unsafe_allow_html=True)


def render() -> None:
    _is_viewer = current_user().is_viewer
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
        get_veto_thresholds(), get_score_weights())
    *_per_exchange, extra_df = _exch_dfs
    all_df = pd.concat([
        d.assign(Exchange=_EXCHANGE_LABELS.get(k, k))
        for k, d in zip(ALL_EXCHANGES, _per_exchange)
    ] + [extra_df], ignore_index=True)

    # ── Add ticker form — same card treatment as the rest of the app
    # (background/border/radius/shadow, panel-2 inputs, filled teal submit)
    # instead of Streamlit's plain default bordered form. st.form() doesn't
    # turn its own key into a "st-key-*" class the way st.container(key=...)
    # does, so an explicit wrapper container is the hook for that CSS. ─────
    with st.container(key="wl_add_form_wrap"):
        with st.form("wl_add_form", border=True, clear_on_submit=True):
            # Company name gets most of the room, button's own column sized
            # to match its actual (compact, right-aligned) button width. 0.5
            # matched it too tightly (only ~3px slack at 1600px live — the
            # button's own single-line "Add ticker" text wrapped to two
            # lines at a narrower window, confirmed by the report); 0.7
            # gives enough headroom to stay single-line at typical widths,
            # with company name trimmed slightly (4 → 3.8) to compensate.
            _c1, _c2, _c3 = st.columns([1.5, 3.8, 0.7], vertical_alignment="bottom")
            with _c1:
                st.markdown('<div style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                           'color:var(--faint);margin-bottom:7px;">Ticker</div>', unsafe_allow_html=True)
                _new_ticker = st.text_input("Ticker", placeholder="TTE.PA", label_visibility="collapsed")
            with _c2:
                st.markdown('<div style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                           'color:var(--faint);margin-bottom:7px;">Company name (optional)</div>',
                           unsafe_allow_html=True)
                _new_name = st.text_input("Company name (optional)", placeholder="TotalEnergies",
                                          label_visibility="collapsed")
            with _c3:
                _submitted = st.form_submit_button("Add ticker", icon=":material/add:", type="primary",
                                                    disabled=_is_viewer,
                                                    help="Viewer role is read-only" if _is_viewer else None)

    if _submitted and not _is_viewer:
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
    if not watchlist:
        with st.container(border=True):
            st.markdown(empty_results_html(
                "Your watchlist is empty. Star a ticker in the screener or add one above."),
                unsafe_allow_html=True)
        return
    if wl_df.empty:
        # Watchlist has tickers but none are scored yet — cold fundamentals
        # cache. Show a skeleton and (while a fetch is running) let it fill in
        # on its own, instead of the old "your watchlist is empty" message
        # that made a still-loading list look like a mistake.
        _n = len(watchlist)
        _s = "s" if _n != 1 else ""
        _wl_prog = poll_while_fetching("wl_fetch_refresh")
        if _wl_prog["running"] and _wl_prog["total"] > 0:
            _wl_msg = (f"Fetching data for your {_n} watchlisted ticker{_s}… "
                      f"{_wl_prog['done']}/{_wl_prog['total']} companies scored.")
        else:
            _wl_msg = (f"No screener data yet for your watchlisted ticker{_s} — "
                      "they'll appear after the next screener refresh.")
        with st.container(key="wl_table_card", border=True):
            st.caption(_wl_msg)
            with st.container(key="wl_col_header"):
                _col_header()
            skeleton_rows(_HH_WIDTHS, n=min(len(watchlist), 6), name_col=1, key_prefix="wl_skel_row")
        return

    with st.container(key="wl_table_card", border=True):
        with st.container(key="wl_col_header"):
            _col_header()

        _drawer_target = None
        for _ridx, _row in wl_df.iterrows():
            _ticker = _row["Ticker"]
            _result = stock_row(
                key=f"wl_row_{_ridx}_{_ticker}",
                ticker=_ticker, name=_row.get("Name", ""), exchange=_row.get("Exchange"),
                decision=str(_row.get("Decision", "")), veto=_row.get("veto"),
                score=_row.get("Value Score"), mos_pct=_row.get("MoS %"), price=_row.get("Price"),
                pe=_row.get("trailingPE"), div_yield=_row.get("dividendYield"),
                action_active=True, action_help="Remove from watchlist",
                action_disabled=_is_viewer,
            )
            if _result["action"]:
                save_watchlist(watchlist - {_ticker})
                # Manually-added tickers never appear on the Screener page
                # (it excludes extra_df from its own ranked list) -- this is
                # the only place their star can ever be removed, so this has
                # to clean up manual_tickers too or a removed ticker leaks in
                # there permanently, still fetched/scored on every page load.
                _mt = load_manual_tickers()
                if _ticker in _mt:
                    del _mt[_ticker]
                    save_manual_tickers(_mt)
                st.rerun()
            if _result["view"]:
                _drawer_target = _ticker

    if _drawer_target is not None:
        _r = wl_df[wl_df["Ticker"] == _drawer_target]
        if not _r.empty:
            open_drawer(_r.iloc[0])
