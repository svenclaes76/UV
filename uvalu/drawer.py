"""Slide-in quick-preview panel for a single stock — the universal row-click
target across Screener/Watchlist/Portfolio/Risk tables. Replaces the old
centered uvalu/stock_dialog.py modal (retired).

Implemented as a restyled @st.dialog: Streamlit has no native right-edge
slide-in panel, so CSS pins the dialog to the right edge and narrows it,
while every existing row-click-to-dialog call site keeps working unchanged
(same (row, pf_context) call signature as the old _dlg_stock_detail).
"""
import pandas as pd
import streamlit as st

from portfolio import (save_watchlist, load_watchlist, load_manual_tickers,
                       save_manual_tickers, load_portfolio, add_position,
                       sell_position)
from uvalu import nav as nav_registry
from uvalu.components import signal_badge_for_decision, signal_badge_html, fair_value_ladder
from uvalu.formatting import fmt_eur as _fmt_eur
from uvalu.runtime import current_user

_DRAWER_CSS = """
[data-testid="stDialog"] div[role="dialog"] {
  position: fixed !important; top: 0 !important; right: 0 !important; left: auto !important;
  height: 100vh !important; max-height: 100vh !important;
  width: 420px !important; max-width: 92vw !important;
  border-radius: 0 !important; margin: 0 !important;
  animation: uvDrawerIn 0.18s ease;
}
@keyframes uvDrawerIn { from { transform: translateX(24px); opacity: 0; } to { transform: none; opacity: 1; } }
[data-testid="stDialog"] div[role="dialog"] > div:first-child { display: none !important; }
"""


def _fv(row, field, fmt=None):
    v = row.get(field)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return fmt(v) if fmt else str(v)


def _safe_float(v, default: float = 0.0) -> float:
    """0.0 for None/NaN — plain `v or default` is wrong here since a NaN
    float is truthy in Python and would pass straight through unchanged."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    return float(v)


def _go_analysis(ticker: str) -> None:
    st.session_state["_analysis_ticker"] = ticker
    _page = nav_registry.pages.get("analysis")
    if _page is not None:
        st.switch_page(_page)


@st.dialog("Stock preview", width="small")
def open_drawer(row: "pd.Series", pf_context: dict | None = None) -> None:
    st.markdown(f"<style>{_DRAWER_CSS}</style>", unsafe_allow_html=True)

    ticker = str(row.get("Ticker", ""))
    watchlist = load_watchlist()
    in_wl = ticker in watchlist
    kind, label = signal_badge_for_decision(str(row.get("Decision", "")), veto=bool(row.get("veto")))

    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f"#### {row.get('Name', '—')}")
        if st.button("★" if in_wl else "☆", key="drw_star", type="tertiary",
                    help="Remove from watchlist" if in_wl else "Add to watchlist"):
            save_watchlist((watchlist - {ticker}) if in_wl else (watchlist | {ticker}))
            if in_wl:
                _mt = load_manual_tickers()
                if ticker in _mt:
                    del _mt[ticker]
                    save_manual_tickers(_mt)
            # Reruns close @st.dialog by default — flag this ticker so the
            # calling page's row-click dispatch reopens the drawer on it.
            st.session_state["_drw_reopen_ticker"] = ticker
            st.rerun()
    st.caption(f"`{ticker}`  ·  {_fv(row, 'sector')}")
    st.markdown(signal_badge_html(kind, label), unsafe_allow_html=True)

    # ── Hero: price / fair value / MoS ───────────────────────────────────────
    _c1, _c2, _c3 = st.columns(3)
    with _c1:
        st.caption("Price")
        st.markdown(f"**{_fv(row, 'Price', _fmt_eur)}**")
    with _c2:
        st.caption("Fair value")
        st.markdown(f"**{_fv(row, 'fair_value', _fmt_eur)}**")
    with _c3:
        st.caption("Margin of safety")
        st.markdown(f"**{_fv(row, 'MoS %', lambda v: f'{v:+.1f}%')}**")

    if row.get("veto"):
        st.error("Hard veto triggered — excluded from scoring. See Analysis for the reason.")

    st.divider()
    st.caption("Six-model fair value")
    _price = row.get("Price")
    if _price is not None and pd.notna(_price):
        fair_value_ladder(
            price=float(_price),
            models=[
                ("Graham #",    row.get("graham_number")),
                ("PE fair val", row.get("pe_fair_value")),
                ("EPV",         row.get("epv")),
                ("DDM 1-stage", row.get("ddm")),
                ("DDM 2-stage", row.get("ddm_multistage")),
                ("Analyst",     row.get("targetMeanPrice")),
            ],
            composite=row.get("fair_value"),
        )

    st.divider()
    st.caption("Position & metrics")
    st.markdown("\n".join([
        "| | |", "|:--|--:|",
        f"| Beta | {_fv(row, 'beta', lambda v: f'{v:.2f}')} |",
        f"| Debt / equity | {_fv(row, 'debtToEquity', lambda v: f'{v:.1f}')} |",
        f"| Risk score | {_fv(row, 'Risk Score', lambda v: f'{v:.1f} / 10')} |",
        f"| P/E | {_fv(row, 'trailingPE', lambda v: f'{v:.1f}×')} |",
    ]), unsafe_allow_html=True)

    st.divider()
    _pf = load_portfolio()
    _held_row = None
    if _pf is not None and not _pf.empty and "ticker" in _pf.columns:
        _match = _pf[_pf["ticker"] == ticker]
        if not _match.empty:
            _held_row = _match.iloc[0]

    _is_viewer = current_user().is_viewer
    _act1, _act2 = st.columns(2)
    with _act1:
        if st.button("View full analysis", key="drw_analysis", width="stretch"):
            _go_analysis(ticker)

    if _held_row is not None:
        with _act2:
            if st.button("Sell", key="drw_sell", width="stretch", disabled=_is_viewer,
                        help="Viewer role is read-only" if _is_viewer else None):
                st.session_state["_drw_sell_open"] = True
        if not _is_viewer and st.session_state.get("_drw_sell_open"):
            with st.form("drw_sell_form", border=True):
                st.caption(f"Currently holding {_held_row.get('shares', 0):.0f} shares")
                _sh = st.number_input("Shares to sell", min_value=1,
                                      max_value=int(_held_row.get("shares", 1) or 1),
                                      value=int(_held_row.get("shares", 1) or 1))
                _px = st.number_input("Sell price", min_value=0.0, step=0.01,
                                      value=_safe_float(row.get("Price")), format="%.2f")
                _dt = st.date_input("Sell date", format="DD/MM/YYYY")
                if st.form_submit_button("Confirm sale", width="stretch"):
                    sell_position(ticker, int(_sh), round(_sh * _px, 2), pd.Timestamp(_dt).isoformat())
                    st.session_state["_drw_sell_open"] = False
                    st.rerun()
    else:
        with _act2:
            if st.button("Buy", key="drw_buy", width="stretch", disabled=_is_viewer,
                        help="Viewer role is read-only" if _is_viewer else None):
                st.session_state["_drw_buy_open"] = True
        if not _is_viewer and st.session_state.get("_drw_buy_open"):
            with st.form("drw_buy_form", border=True):
                _sh = st.number_input("Shares", min_value=1, step=1, value=1)
                _price = _safe_float(row.get("Price"))
                _cost = st.number_input("Total cost", min_value=0.0, step=0.01,
                                        value=round(_price * _sh, 2), format="%.2f")
                _dt = st.date_input("Buy date", format="DD/MM/YYYY")
                if st.form_submit_button("Confirm buy", width="stretch"):
                    add_position({
                        "name": row.get("Name", ticker), "google_ticker": "", "ticker": ticker,
                        "shares": _sh, "purchase_price": round(_cost / _sh, 4) if _sh else 0.0,
                        "purchase_value": round(_cost, 2), "target_price": None,
                        "dividends": 0.0, "date_in": pd.Timestamp(_dt).isoformat(), "account": "",
                    })
                    st.session_state["_drw_buy_open"] = False
                    st.rerun()
