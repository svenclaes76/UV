"""Watchlist page — tickers not currently held, tracked separately from the
screener's per-exchange lists. Promoted out of uvalu/pages_/screener.py's
former "Watchlist" tab into its own top-bar nav entry (Phase 1)."""
import html
import re

import pandas as pd
import yfinance as yf
import streamlit as st

from portfolio import (load_watchlist, save_watchlist,
                       load_manual_tickers, save_manual_tickers)
from settings import load_shared_settings, get_veto_thresholds, get_score_weights, ALL_EXCHANGES
from uvalu import a11y
from uvalu.data import _load_all_screener_data, _cache_version
from uvalu.components import list_provenance_html, page_header, fit_widths, header_cell_html, stock_row, empty_results_html, skeleton_rows
from uvalu.drawer import open_drawer
from uvalu.formatting import exchange_code, row_currency
from uvalu.i18n import N_, _, h_, ngettext, tr
from uvalu.runtime import current_user
from uvalu.ui import _auto_rerun, poll_while_fetching

_EXCHANGE_LABELS = {
    "brussels": N_("Brussels"), "amsterdam": N_("Amsterdam"), "paris": N_("Paris"),
    "milan": N_("Milan"), "frankfurt": N_("Frankfurt"), "swiss": N_("Swiss"),
}

# 8 widths matching stock_row's show_remove=True layout exactly (the 7
# shared data columns, then the "×" remove column) — shared by the real
# column header, the real rows (stock_row), and the loading skeleton's
# column-header/rows so all three always stay pixel-aligned.
_HH_WIDTHS = [3.0, 1.8, 1.5, 1.0, 0.9, 0.8, 0.9, 0.32]   # signal column fits the longest badge (BDG-1)
_HH_LABELS = (N_("Company"), N_("Model signal"), N_("Composite score"), N_("Margin of safety"), N_("Price"),
              "P/E", N_("Yield"), "")
# Upside/Price/P-E/Yield are right-aligned (matching their own right-aligned
# data cells in stock_row); Position/Signal/Composite score stay left-aligned
# like their left-anchored cells.
_HH_RIGHT = {"Margin of safety", "Price", "P/E", "Yield"}
_PX_PER_UNIT = 110   # st.columns weights → px at the design width, for fit_widths


def _fitted_widths() -> list:
    """_HH_WIDTHS widened to fit the translated headers (header, rows and
    skeleton share it, so they stay aligned)."""
    return fit_widths(_HH_WIDTHS, [tr(label) if label else "" for label in _HH_LABELS],
                      px_per_unit=_PX_PER_UNIT)


def _col_header() -> None:
    """The real column-header row — shared by the loaded results table and
    the loading skeleton (labels are static text, no reason to shimmer
    them)."""
    for _hh, _label in zip(st.columns(_fitted_widths(), vertical_alignment="center"), _HH_LABELS):
        if _label:
            with _hh:
                st.markdown(header_cell_html(tr(_label), right=_label in _HH_RIGHT), unsafe_allow_html=True)


def _universe_loading() -> bool:
    """True while the screening universe is still being prepared: the peer
    reference is rebuilt after a restart, or the scored universe recomputed."""
    from uvalu.data import peer_reference_pending
    from uvalu.store import universe_recomputing
    try:
        return bool(peer_reference_pending() or universe_recomputing())
    except Exception:
        return False


def _not_found_html(sym: str) -> str:
    msg = h_("Ticker **{ticker}** not found. Check the symbol and try again.", ticker=sym)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", msg)


def render() -> None:
    _is_viewer = current_user().is_viewer
    # REC-4 / REC-5: the provenance (third line of the page header) is filled
    # in once the watchlist's rows are known (below the add form).
    _header_slot = st.empty()

    def _header(provenance: str = "") -> None:
        with _header_slot.container():
            page_header(_("Watchlist"),
                        _("Track tickers you don't hold yet. Add from the screener with the star, or type a symbol directly below."),
                        provenance=provenance)
    _header()

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
            # The button's column then sizes to the button itself (styles.py),
            # so a longer label ("Ticker hinzufügen") or a narrower window
            # never wraps it.
            _add_label = _("Add ticker")
            _c1, _c2, _c3 = st.columns([1.5, 3.8, 0.7], vertical_alignment="bottom")
            with _c1:
                st.markdown('<div style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                           f'color:var(--muted);margin-bottom:7px;">{h_("Ticker")}</div>', unsafe_allow_html=True)
                _new_ticker = st.text_input(_("Ticker"), placeholder="TTE.PA", label_visibility="collapsed")
            with _c2:
                st.markdown('<div style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                           f'color:var(--muted);margin-bottom:7px;">{h_("Company name (optional)")}</div>',
                           unsafe_allow_html=True)
                _new_name = st.text_input(_("Company name (optional)"), placeholder="TotalEnergies",
                                          label_visibility="collapsed")
            with _c3:
                _submitted = st.form_submit_button(_add_label, icon=":material/add:", type="primary",
                                                    disabled=_is_viewer,
                                                    help=_("Viewer role is read-only") if _is_viewer else None)

    if _submitted and not _is_viewer:
        _sym = _new_ticker.strip().upper()
        if not _sym:
            st.markdown(f'<div style="font-size:12px;color:var(--down-txt);">{h_("Enter a ticker symbol.")}</div>',
                       unsafe_allow_html=True)
        elif _sym in watchlist:
            # G28: say so instead of silently doing nothing.
            st.markdown(f'<div style="font-size:12px;color:var(--muted);">{h_("Already on your watchlist.")}</div>',
                        unsafe_allow_html=True)
        else:
            try:
                _info = yf.Ticker(_sym).info
                _name = _new_name.strip() or _info.get("shortName") or _info.get("longName") or _sym
                if not _info.get("regularMarketPrice") and not _info.get("currentPrice"):
                    st.markdown(f'<div style="font-size:12px;color:var(--down-txt);">{_not_found_html(_sym)}</div>',
                               unsafe_allow_html=True)
                else:
                    _mt = load_manual_tickers()
                    _mt[_sym] = _name
                    save_manual_tickers(_mt)
                    save_watchlist(watchlist | {_sym})
                    st.rerun()
            except Exception:
                st.markdown(f'<div style="font-size:12px;color:var(--down-txt);">{_not_found_html(_sym)}</div>',
                           unsafe_allow_html=True)

    # ── Results list ─────────────────────────────────────────────────────────
    # Highest composite score first, like the Screener (rows came out grouped
    # by exchange); unscored rows last.
    wl_df = all_df[all_df["Ticker"].isin(watchlist)]
    if "Value Score" in wl_df.columns:
        wl_df = wl_df.assign(_sort=pd.to_numeric(wl_df["Value Score"], errors="coerce")).sort_values(
            "_sort", ascending=False, na_position="last").drop(columns="_sort")
    wl_df = wl_df.reset_index(drop=True)
    if not watchlist:
        with st.container(border=True):
            st.markdown(empty_results_html(
                h_("Your watchlist is empty. Star a ticker in the screener or add one above.")),
                unsafe_allow_html=True)
        return
    if not wl_df.empty and (_prov := list_provenance_html(wl_df)):
        _header(_prov)
    if wl_df.empty:
        # Watchlist has tickers but none are scored yet — cold fundamentals
        # cache. Show a skeleton and (while a fetch is running) let it fill in
        # on its own, instead of the old "your watchlist is empty" message
        # that made a still-loading list look like a mistake.
        _n = len(watchlist)
        _wl_prog = poll_while_fetching("wl_fetch_refresh")
        if _wl_prog["running"] and _wl_prog["total"] > 0:
            _wl_msg = html.escape(ngettext("Fetching data for your {count} watchlisted ticker… {done}/{total} companies scored.",
                                  "Fetching data for your {count} watchlisted tickers… {done}/{total} companies scored.",
                                  _n, done=_wl_prog['done'], total=_wl_prog['total']))
        elif _universe_loading():
            # P9: right after a restart the fetch hasn't started yet while the
            # peer reference is rebuilt or the universe rescored; "after the
            # next screener refresh" read as if nothing was happening.
            _wl_msg = html.escape(ngettext("Loading screener data for your {count} watchlisted ticker…",
                                  "Loading screener data for your {count} watchlisted tickers…", _n))
            # poll_while_fetching only polls while the fetch runs or the
            # universe is rescored; keep polling through the peer rebuild too,
            # so the rows appear without a click.
            from uvalu.data import screener_refresh_signature
            _auto_rerun(5.0, "wl_fetch_refresh", version_fn=screener_refresh_signature)
        else:
            _wl_msg = html.escape(ngettext("No screener data yet for your watchlisted ticker — it will appear after the next screener refresh.",
                                  "No screener data yet for your watchlisted tickers — they'll appear after the next screener refresh.",
                                  _n))
        with st.container(key="wl_table_card", border=True):
            # wl_table_card is padding:0 by design (uvalu/styles.py) so its
            # own children — the column header, the rows — each own their
            # exact padding; a bare st.caption() here would sit flush against
            # the card's raw edge instead of aligned with those 20px-indented
            # children. Same padding loading_skeleton_html() used to carry.
            st.markdown(f'<div role="status" aria-live="polite" style="padding:22px 20px 8px;font-size:13px;color:var(--muted);">{_wl_msg}</div>',
                       unsafe_allow_html=True)
            with st.container(key="wl_col_header"):
                _col_header()
            skeleton_rows(_fitted_widths(), n=min(len(watchlist), 6), name_col=0, key_prefix="uv_skel_row_wl")
        return

    with st.container(key="wl_table_card", border=True):
        with st.container(key="wl_col_header"):
            _col_header()

        _drawer_target = None
        # AC2: the rows are a table for screen readers (uvalu/a11y.py).
        a11y.table("wl_table_card", _("Watchlist"), header="wl_col_header",
                   rows=[f"wl_row_{_i}_{_t}" for _i, _t in wl_df["Ticker"].items()],
                   header_names={len(_HH_LABELS) - 1: _("Remove from watchlist")})
        for _ridx, _row in wl_df.iterrows():
            _ticker = _row["Ticker"]
            _result = stock_row(
                key=f"wl_row_{_ridx}_{_ticker}",
                ticker=_ticker, name=_row.get("Name", ""), exchange=exchange_code(_ticker),
                signal_code=str(_row.get("signal_code", "")), veto=_row.get("veto"),
                score=_row.get("Value Score"), mos_pct=_row.get("MoS %"), price=_row.get("Price"),
                pe=_row.get("trailingPE"), div_yield=_row.get("dividendYield"),
                show_action=False, show_remove=True, remove_help=_("Remove from watchlist"),
                action_disabled=_is_viewer, widths=_fitted_widths(), currency=row_currency(_row),
            )
            if _result["remove"]:
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
