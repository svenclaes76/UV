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
from uvalu.ui import enter_dialog

SECTOR_OPTIONS = [
    "Technology", "Healthcare", "Financial Services", "Consumer Cyclical",
    "Consumer Defensive", "Energy", "Industrials", "Utilities", "Basic Materials",
]

DIV_TYPE_OPTIONS = ["Cash", "Stock", "Special"]


def _dividend_tax_breakdown(gross: float, foreign_wh_pct: float, div_type: str) -> tuple[float, float, float]:
    """(foreign_wh_amount, be_amount, net) for a gross dividend — mirrors
    portfolio.dividends_in_eur()'s per-row math exactly (foreign % first,
    then Belgium's fixed 30% roerende voorheffing on the remainder), so the
    dialog's live preview always matches what gets stored/read back. Stock
    (scrip) dividends carry no cash withholding."""
    from portfolio import BE_WITHHOLDING_RATE

    fwh = round(gross * (foreign_wh_pct or 0) / 100, 2)
    be = 0.0 if div_type == "Stock" else round(max(0.0, gross - fwh) * BE_WITHHOLDING_RATE, 2)
    return fwh, be, round(gross - fwh - be, 2)


def dividend_tax_preview(gross: float, fwh: float, be: float, net: float) -> None:
    """The Gross -> Foreign WH -> BE 30% -> Net "Calculated" box shared by the
    Add and Edit dividend dialogs (Uvalu Dividend Management.dc.html), so
    both render it identically."""
    st.markdown(
        f'<div style="margin-top:4px;padding:10px 12px;border-radius:8px;background:var(--panel-2);">'
        f'<div style="font-size:10px;letter-spacing:0.05em;text-transform:uppercase;color:var(--faint);'
        f'margin-bottom:6px;">Calculated</div>'
        f'<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:12px;">'
        f'<span style="color:var(--muted);">Gross</span><span style="font-family:var(--uv-mono);">€{gross:,.2f}</span></div>'
        f'<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:12px;color:var(--muted);">'
        f'<span>Foreign withholding</span><span style="font-family:var(--uv-mono);">−€{fwh:,.2f}</span></div>'
        f'<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:12px;color:var(--muted);">'
        f'<span>Belgian RV 30%</span><span style="font-family:var(--uv-mono);">−€{be:,.2f}</span></div>'
        f'<div style="display:flex;justify-content:space-between;padding:6px 0 0;margin-top:4px;'
        f'border-top:0.5px solid var(--line-2);font-size:12.5px;font-weight:500;">'
        f'<span>Net received</span><span style="font-family:var(--uv-mono);color:var(--uv-mint,#1DD6A4);">€{net:,.2f}</span></div>'
        f'</div>', unsafe_allow_html=True)


DIALOG_WIDTH = 420  # Uvalu.dc.html's Add position / closed-trade modal width


def _dialog_width_css(px: int = DIALOG_WIDTH) -> None:
    """Clamp this dialog to Uvalu.dc.html's modal width. Only ever present in
    the DOM while this specific dialog is open (only one dialog can be open
    at a time), so it can't leak into any other dialog's sizing.

    Since Streamlit 1.60 the visible box (background, radius, shadow) is the
    PARENT of `[role="dialog"]`, sized by the `width="small"` preset (500px).
    Clamping only `[role="dialog"]` — what this used to do — left the content
    420px wide against the box's left edge with ~100px of dead space on the
    right (live-measured). So size the box itself and let the inner section
    fill it. Also hides number-input -/+ steppers, which only rendered in
    some dialogs (wide-enough columns), unlike the mockup's plain fields."""
    st.markdown(
        f'<style>[data-testid="stDialog"] div:has(> [role="dialog"]) {{ width: {px}px !important; '
        f'max-width: calc(100vw - 32px) !important; }}'
        f'[data-testid="stDialog"] [role="dialog"] {{ width: 100% !important; max-width: 100% !important; }}'
        f'[data-testid="stDialog"] [data-testid="stNumberInputStepDown"],'
        f'[data-testid="stDialog"] [data-testid="stNumberInputStepUp"] {{ display: none !important; }}'
        f'</style>',
        unsafe_allow_html=True,
    )


# ── Shared Add/Edit dialog layout ─────────────────────────────────────────────
# Every Add/Edit dialog follows Uvalu.dc.html's modal structure: title (the
# st.dialog chrome) → one-line subtitle → Ticker + Company name row → fields →
# one action row. These helpers keep that identical across dialogs.

def dialog_frame(subtitle: str) -> None:
    """Width clamp + the one-line muted subtitle under the dialog title.
    Keep `subtitle` to ~48 characters: at the 420px width a longer one wraps
    to a second line and makes that dialog taller than its Add/Edit sibling
    (the Add dividend subtitle did — 22px taller than Edit, live-measured)."""
    _dialog_width_css()
    st.caption(subtitle)


def identity_row(*, ticker: str = "", name: str = "", key_prefix: str, locked: bool = False,
                 ticker_placeholder: str = "", name_placeholder: str = "") -> tuple[str, str]:
    """Ticker + Company name, always first and at the same 1 : 1.4 split as
    the mockup's dividend modal. `locked` (Edit dialogs) shows the same
    fields read-only — changing an existing record's ticker would make it a
    different holding. Returns (TICKER, name) stripped."""
    _c1, _c2 = st.columns([1, 1.4])
    with _c1:
        t = st.text_input("Ticker", value=ticker, placeholder=ticker_placeholder,
                          key=f"{key_prefix}_ticker", disabled=locked)
    with _c2:
        n = st.text_input("Company name", value=name, placeholder=name_placeholder,
                          key=f"{key_prefix}_name", disabled=locked)
    return (t or "").strip().upper(), (n or "").strip()


def dialog_actions(key_prefix: str, *, save_label: str = "Save", delete: bool = False,
                   danger_save: bool = False) -> tuple[bool, bool]:
    """One action row: [Delete] (Edit dialogs, compact red outline, left) |
    Cancel | Save. Cancel closes the dialog. Returns (save, delete)."""
    _cols = st.columns([0.8, 1, 1] if delete else [1, 1])
    _do_delete = False
    if delete:
        with _cols[0], st.container(key=f"uv_danger_btn_{key_prefix}"):
            _do_delete = st.button("Delete", key=f"{key_prefix}_delete", width="stretch")
    with _cols[-2]:
        if st.button("Cancel", key=f"{key_prefix}_cancel", width="stretch"):
            st.rerun()
    with _cols[-1]:
        if danger_save:
            with st.container(key=f"uv_danger_btn_{key_prefix}_save"):
                _do_save = st.button(save_label, key=f"{key_prefix}_save", width="stretch", type="primary")
        else:
            _do_save = st.button(save_label, key=f"{key_prefix}_save", width="stretch", type="primary")
    return _do_save, _do_delete


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
    enter_dialog()
    dialog_frame("Enter a total cost or a price per share.")
    ticker_raw, name_raw = identity_row(ticker=preset_ticker, name=preset_name, key_prefix="dlg_ap",
                                        ticker_placeholder="TTE.PA", name_placeholder="TotalEnergies")

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

    _do_save, _ = dialog_actions("dlg_ap")

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
    enter_dialog()
    dialog_frame("Sell all or part of this position.")
    if ticker is None:
        _sorted = pf.sort_values("name", key=lambda s: s.str.lower())
        _opts   = _sorted["ticker"].tolist()
        _labels = {r["ticker"]: f"{r['name']}  ({r['ticker']})" for _, r in _sorted.iterrows()}
        ticker = st.selectbox("Company", options=_opts, format_func=lambda t: _labels.get(t, t),
                              key="dlg_sell_ticker")
        _match = pf[pf["ticker"] == ticker]
    else:
        _match = pf[pf["ticker"] == ticker]
        identity_row(ticker=ticker, name=str(_match.iloc[0]["name"]) if not _match.empty else "",
                     key_prefix="dlg_sell_id", locked=True)

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

    _do_save, _ = dialog_actions("dlg_sell", save_label="Confirm close", danger_save=True)

    if _do_save and shares > 0 and price > 0:
        sell_position(ticker=ticker, shares=shares, proceeds=round(shares * price, 2),
                      sell_date=pd.Timestamp(sell_date).isoformat())
        st.rerun()


@st.dialog("Add dividend", width="small")
def add_dividend_dialog(pf: "pd.DataFrame") -> None:
    import datetime as _dt

    from portfolio import currency_for_ticker, exchange_key_for_ticker
    from settings import get_dividend_withholding
    from uvalu.runtime import current_user

    enter_dialog()
    dialog_frame("Record a dividend payment for a holding.")
    # The company name defaults from the held position once the ticker is
    # known, so read the ticker's current value before drawing the row.
    _t0 = str(st.session_state.get("dlg_dv_ticker") or "").strip().upper()
    _match = pf[pf["ticker"] == _t0] if _t0 and "ticker" in pf.columns else pf.iloc[0:0]
    _default_name = _match.iloc[0]["name"] if not _match.empty else ""
    ticker_raw, name_raw = identity_row(name=_default_name, key_prefix="dlg_dv",
                                        ticker_placeholder="ALV.DE", name_placeholder="Allianz")
    _ccy = currency_for_ticker(ticker_raw) if ticker_raw else "EUR"


    # Declaration/record dates and per-holding frequency were dropped from
    # this dialog (and the Edit dialog / CSV export) per user review: only
    # the ex-date and payment date are asked for, in one readable row.
    _c3, _c4 = st.columns(2)
    with _c3:
        ex_date = st.date_input("Ex-dividend date *", value=None, format="DD/MM/YYYY",
                                max_value=_dt.date.today() + _dt.timedelta(days=365), key="dlg_dv_ex")
    with _c4:
        pay_date = st.date_input("Payment date *", format="DD/MM/YYYY", max_value=_dt.date.today(),
                                 key="dlg_dv_pay")

    _c5, _c6, _c7 = st.columns(3)
    with _c5:
        _shares0 = int(_num_or(_match.iloc[0]["shares"], 0)) if not _match.empty else 0
        shares = st.number_input("Shares held", min_value=0, step=1, value=_shares0, key="dlg_dv_shares")
    with _c6:
        dps = st.number_input(f"Per share ({_ccy})", min_value=0.0, step=0.0001, value=0.0,
                              format="%.4f", key="dlg_dv_ps")
    with _c7:
        _default_tax = get_dividend_withholding(exchange_key_for_ticker(ticker_raw), current_user().email)
        tax_rate = st.number_input("Foreign WH (%)", min_value=0.0, max_value=100.0,
                                   step=0.5, value=_default_tax, key="dlg_dv_tax")

    div_type = st.selectbox("Type", options=DIV_TYPE_OPTIONS, key="dlg_dv_type")

    if div_type == "Special":
        st.caption("Flagged as special / one-off. Excluded from growth-streak and yield calculations.")

    gross = round(dps * shares, 2)
    fwh, be, net = _dividend_tax_breakdown(gross, tax_rate, div_type)
    dividend_tax_preview(gross, fwh, be, net)

    _do_save, _ = dialog_actions("dlg_dv")

    if not _do_save:
        return
    if not ticker_raw or gross <= 0:
        st.error("Enter a ticker, shares held and a gross amount per share.")
        return
    if ex_date is None:
        st.error("Ex-dividend date is required.")
        return
    if pay_date is None:
        st.error("Payment date is required.")
        return
    _google_ticker = _match.iloc[0].get("google_ticker", "") if not _match.empty else ""
    add_dividend({
        "name":              name_raw or ticker_raw,
        "google_ticker":     _google_ticker,
        "ticker":            ticker_raw,
        "shares":            int(shares),
        "amount":            gross,
        "amount_per_share":  round(dps, 4),
        "currency":          _ccy,
        "tax_rate":          round(tax_rate, 2),
        "tax_amount":        fwh,
        "div_type":          div_type,
        "source":            "manual",
        "declaration_date":  None,
        "ex_date":           pd.Timestamp(ex_date).isoformat(),
        "record_date":       None,
        "date":              pd.Timestamp(pay_date).isoformat(),
        # The DRIP checkbox was removed from this dialog (user review, Sep
        # 2026): new records are always cash. Existing DRIP records keep
        # their flag.
        "reinvested":        False,
        "reinvested_shares": None,
    })
    st.rerun()


@st.dialog("Add closed trade", width="small")
def add_closed_trade_dialog() -> None:
    enter_dialog()
    dialog_frame("Record a trade opened and closed elsewhere.")
    ticker_raw, name_raw = identity_row(key_prefix="dlg_ct", ticker_placeholder="SAP.DE",
                                        name_placeholder="SAP")
    sector = st.selectbox("Sector", options=SECTOR_OPTIONS, key="dlg_ct_sector")

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

    _do_save, _ = dialog_actions("dlg_ct")

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
