"""Shared CRUD modals — Add position, Sell position, Add dividend, Add
closed trade. Consolidates what used to be near-duplicate @st.dialog
functions scattered across uvalu/pages_/portfolio.py, dashboard.py,
screener.py and the inline forms in uvalu/drawer.py, and aligns their
fields/copy with Uvalu.dc.html's four modal specs.

Tickers are free-text and validated against yfinance on submit — the same
pattern uvalu/pages_/watchlist.py already uses for its "add a symbol
directly" flow — rather than restricted to a pre-loaded screener universe,
matching the mockup's plain text Ticker input.
"""
import pandas as pd
import streamlit as st
import yfinance as yf

from portfolio import add_position, sell_position, add_dividend, add_closed_trade

SECTOR_OPTIONS = [
    "Technology", "Healthcare", "Financial Services", "Consumer Cyclical",
    "Consumer Defensive", "Energy", "Industrials", "Utilities", "Basic Materials",
]


def _dialog_width_css(px: int) -> None:
    """Clamp this dialog to Uvalu.dc.html's exact modal width — Streamlit's
    `width="small"` preset (550px) is the closest built-in option but still
    wider than the mockup's compact 420px/380px cards. Only ever present in
    the DOM while this specific dialog is open (only one dialog can be open
    at a time), so it can't leak into any other dialog's sizing.

    Reuses the exact `[data-testid="stDialog"] [role="dialog"]` selector
    uvalu/styles.py's global CSS already clamps every dialog to 550px with —
    same specificity, but injected later (inside this dialog's own render,
    after that app-level stylesheet), so it wins the tie on source order
    without needing `!important`-vs-`!important` selector one-upmanship."""
    st.markdown(
        f'<style>[data-testid="stDialog"] [role="dialog"] {{ max-width: {px}px !important; '
        f'width: {px}px !important; }}</style>',
        unsafe_allow_html=True,
    )


def _num_or(value, default):
    """pd.to_numeric-coerced value, or `default` if missing/unparseable/NaN.
    `pd.to_numeric(value, errors="coerce") or default` doesn't work here --
    NaN is truthy in Python, so a NaN field (e.g. an Excel-imported position
    with a blank shares cell) passes straight through instead of falling
    back, and `int(nan)` raises ValueError rather than silently corrupting."""
    v = pd.to_numeric(value, errors="coerce")
    return v if pd.notna(v) else default


def _lookup_ticker(sym: str) -> tuple[str, float] | None:
    """Validate a free-text ticker via yfinance. Returns (name, price) or None
    if the symbol doesn't resolve to a live quote."""
    try:
        info = yf.Ticker(sym).info
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not price:
            return None
        name = info.get("shortName") or info.get("longName") or sym
        return name, float(price)
    except Exception:
        return None


@st.dialog("Add position", width="small")
def add_position_dialog(preset_ticker: str = "", preset_name: str = "", preset_price: float = 0.0) -> None:
    _dialog_width_css(420)
    st.caption("Enter the ticker and either a total cost or a price per share — whichever you have on hand.")
    _c1, _c2 = st.columns(2)
    with _c1:
        ticker_raw = st.text_input("Ticker", value=preset_ticker, placeholder="TTE.PA",
                                   key="dlg_ap_ticker").strip().upper()
    with _c2:
        name_raw = st.text_input("Company name", value=preset_name, placeholder="TotalEnergies",
                                 key="dlg_ap_name").strip()

    # No date field — Uvalu.dc.html's ap state has no date input at all, so the
    # purchase is recorded as of today rather than asking for a backdated one.
    _c3, _c4, _c5 = st.columns(3)
    with _c3:
        shares = st.number_input("Shares", min_value=1, step=1, value=1, key="dlg_ap_shares")
    with _c4:
        total_cost = st.number_input("Total cost (€)", min_value=0.0, step=0.01, value=0.0,
                                     format="%.2f", key="dlg_ap_cost")
    with _c5:
        price = st.number_input("Price / share (opt.)", min_value=0.0, step=0.01,
                                value=round(preset_price, 2), format="%.2f", key="dlg_ap_price")
    pur_date = pd.Timestamp.now()

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="dlg_ap_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_save = st.button("Save", key="dlg_ap_save", width="stretch", type="primary")

    if not _do_save:
        return
    if not ticker_raw:
        st.error("Enter a ticker symbol.")
        return
    _looked_up = _lookup_ticker(ticker_raw)
    if _looked_up is None:
        st.error(f"Ticker **{ticker_raw}** not found. Check the symbol and try again.")
        return
    _yf_name, _ = _looked_up
    _total = total_cost if total_cost > 0 else round(price * shares, 2)
    if _total <= 0 or shares <= 0:
        st.error("Enter shares and either a total cost or a price per share.")
        return
    add_position({
        "name":           name_raw or _yf_name,
        "google_ticker":  "",
        "ticker":         ticker_raw,
        "shares":         shares,
        "purchase_price": round(_total / shares, 4),
        "purchase_value": round(_total, 2),
        "target_price":   None,
        "dividends":      0.0,
        "date_in":        pd.Timestamp(pur_date).isoformat(),
        "account":        "",
    })
    st.rerun()


@st.dialog("Close position", width="small")
def sell_position_dialog(pf: "pd.DataFrame", ticker: str | None = None,
                         preset_price: float | None = None) -> None:
    _dialog_width_css(380)
    if ticker is None:
        _sorted = pf.sort_values("name", key=lambda s: s.str.lower())
        _opts   = _sorted["ticker"].tolist()
        _labels = {r["ticker"]: f"{r['name']}  ({r['ticker']})" for _, r in _sorted.iterrows()}
        ticker = st.selectbox("Company", options=_opts, format_func=lambda t: _labels.get(t, t),
                              key="dlg_sell_ticker")
    else:
        st.markdown(f'<div style="font-size:17px;font-weight:500;letter-spacing:-0.02em;">'
                    f'Close {ticker}</div>', unsafe_allow_html=True)
        st.caption("Close all or part of this position. Realised P&L is recorded on the Portfolio page.")

    _match = pf[pf["ticker"] == ticker]
    _held_shares = int(_num_or(_match.iloc[0]["shares"], 0)) if not _match.empty else 0
    if preset_price is not None:
        _live_price = float(preset_price)
    else:
        _live_price = float(_num_or(_match.iloc[0].get("live_price"), 0.0)) \
            if not _match.empty else 0.0

    # No date field — Uvalu.dc.html's sell state is just shares + price, so the
    # sale is recorded as of today rather than asking for a backdated one.
    _c1, _c2 = st.columns(2)
    with _c1:
        shares = st.number_input("Shares to sell", min_value=1, max_value=max(_held_shares, 1),
                                 value=max(_held_shares, 1), step=1, key="dlg_sell_shares")
    with _c2:
        price = st.number_input("Sell price", min_value=0.0, step=0.01, value=round(_live_price, 2),
                                format="%.2f", key="dlg_sell_price")
    sell_date = pd.Timestamp.now()

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="dlg_sell_cancel", width="stretch"):
            st.rerun()
    with _b2:
        with st.container(key="uv_danger_btn"):
            _do_save = st.button("Confirm close", key="dlg_sell_save", width="stretch", type="primary")

    if _do_save and shares > 0 and price > 0:
        sell_position(ticker=ticker, shares=shares, proceeds=round(shares * price, 2),
                      sell_date=pd.Timestamp(sell_date).isoformat())
        st.rerun()


@st.dialog("Add dividend", width="small")
def add_dividend_dialog(pf: "pd.DataFrame") -> None:
    _dialog_width_css(380)
    _c1, _c2 = st.columns(2)
    with _c1:
        ticker_raw = st.text_input("Ticker", placeholder="ALV.DE", key="dlg_dv_ticker").strip().upper()
    with _c2:
        amount = st.number_input("Amount (€)", min_value=0.0, step=0.01, value=0.0,
                                 format="%.2f", key="dlg_dv_amount")

    _match = pf[pf["ticker"] == ticker_raw] if ticker_raw and "ticker" in pf.columns else pf.iloc[0:0]
    _default_name = _match.iloc[0]["name"] if not _match.empty else ""
    name_raw = st.text_input("Company name", value=_default_name, placeholder="Allianz",
                             key="dlg_dv_name").strip()
    div_date = st.date_input("Date", format="DD/MM/YYYY", key="dlg_dv_date")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="dlg_dv_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_save = st.button("Save", key="dlg_dv_save", width="stretch", type="primary")

    if not _do_save:
        return
    if not ticker_raw or amount <= 0:
        st.error("Enter a ticker and an amount.")
        return
    _google_ticker = _match.iloc[0].get("google_ticker", "") if not _match.empty else ""
    _shares = int(_num_or(_match.iloc[0]["shares"], 0)) if not _match.empty else 0
    add_dividend({
        "name":          name_raw or ticker_raw,
        "google_ticker": _google_ticker,
        "ticker":        ticker_raw,
        "shares":        _shares,
        "amount":        round(amount, 2),
        "date":          pd.Timestamp(div_date).isoformat(),
    })
    st.rerun()


@st.dialog("Add closed trade", width="small")
def add_closed_trade_dialog() -> None:
    _dialog_width_css(420)
    st.caption("Record a trade that was opened and closed outside this app's normal Add/Close flow.")
    _c1, _c2 = st.columns(2)
    with _c1:
        ticker_raw = st.text_input("Ticker", placeholder="SAP.DE", key="dlg_ct_ticker").strip().upper()
    with _c2:
        sector = st.selectbox("Sector", options=SECTOR_OPTIONS, key="dlg_ct_sector")
    name_raw = st.text_input("Company name", placeholder="SAP", key="dlg_ct_name").strip()

    _c3, _c4, _c5 = st.columns(3)
    with _c3:
        shares = st.number_input("Shares", min_value=1, step=1, value=1, key="dlg_ct_shares")
    with _c4:
        buy_price = st.number_input("Buy price", min_value=0.0, step=0.01, value=0.0,
                                    format="%.2f", key="dlg_ct_buy")
    with _c5:
        sell_price = st.number_input("Sell price", min_value=0.0, step=0.01, value=0.0,
                                     format="%.2f", key="dlg_ct_sell")
    closed_date = st.date_input("Closed date", format="DD/MM/YYYY", key="dlg_ct_closed")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="dlg_ct_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_save = st.button("Save", key="dlg_ct_save", width="stretch", type="primary")

    if not _do_save:
        return
    if not ticker_raw or shares <= 0 or buy_price <= 0 or sell_price <= 0:
        st.error("Enter a ticker, shares, and both a buy and sell price.")
        return
    _closed_iso = pd.Timestamp(closed_date).isoformat()
    add_closed_trade({
        "name":              name_raw or ticker_raw,
        "google_ticker":     "",
        "ticker":            ticker_raw,
        "shares":            shares,
        "purchase_value":    round(buy_price * shares, 2),
        "sale_value":        round(sell_price * shares, 2),
        "dividends":         0.0,
        "sector":            sector,
        # The open date is never asked (matching the mockup) — this modal is
        # for trades whose open date is unknown/irrelevant, so held-days-based
        # figures (e.g. annual_return_pct) can't be computed for these rows.
        "date_in":           _closed_iso,
        "date_out":          _closed_iso,
        "annual_return_pct": float("nan"),
    })
    st.rerun()
