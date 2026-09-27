"""Shared CRUD modals for the Portfolio screens — Add / Edit position, Close
position, Add / Edit dividend, Add / Edit closed trade, Add / Edit cash
transaction and the read-only linked cash entry. Consolidates what used to be
near-duplicate @st.dialog functions scattered across uvalu/pages_/portfolio.py
(the Edit dialogs were closures there), dashboard.py, screener.py and the
inline forms in uvalu/drawer.py, and aligns their fields/copy with
Uvalu.dc.html's modal specs.

Every dialog follows the same conventions (Sep 2026 alignment pass):
- 420px wide (`dialog_frame`), one-line subtitle (≤ ~48 chars);
- required fields end in " *", optional ones in " (opt.)";
- validation errors via `st.error`;
- one action row — [Delete] | Cancel | Save — with a confirmation step
  before any delete (`dialog_actions(..., confirm_text=...)`);
- Edit dialogs address their record by its stable id (trade_id / div_id /
  cash entry id) and reload it, never a row index into a render-time frame;
- the Viewer role gets a read-only notice inside every dialog, on top of the
  disabled buttons that open them (`viewer_blocked`).

Tickers are free-text and validated against yfinance on submit — the same
pattern uvalu/pages_/watchlist.py already uses for its "add a symbol
directly" flow.
"""
import datetime as _dt
import functools
import html as _html

import pandas as pd
import streamlit as st
import yfinance as yf

from portfolio import add_dividend, add_closed_trade, record_buy, record_sell
from uvalu.i18n import N_, _, date_input_format, fmt_int, fmt_money, fmt_num, fmt_pct, ngettext, tr
from uvalu.locale_ui import number_field
from uvalu.ui import enter_dialog

# Stored values stay English (they are data); every widget shows them via tr().
SECTOR_OPTIONS = [
    N_("Technology"), N_("Healthcare"), N_("Financial Services"), N_("Consumer Cyclical"),
    N_("Consumer Defensive"), N_("Energy"), N_("Industrials"), N_("Utilities"), N_("Basic Materials"),
]

DIV_TYPE_OPTIONS = [N_("Cash"), N_("Stock"), N_("Special")]


def _dialog(title: str):
    """st.dialog with its title translated when the dialog opens (the
    decorator argument is otherwise fixed at import time, in English)."""
    def deco(fn):
        @functools.wraps(fn)
        def call(*args, **kwargs):
            return st.dialog(_(title), width="small")(fn)(*args, **kwargs)
        return call
    return deco


def _nz(v, default=0):
    """number_field() returns None for empty/invalid input in comma-decimal
    regions; computations treat that as `default` and validation catches it."""
    return default if v is None else v


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


# ── Calculated box ───────────────────────────────────────────────────────────
# One look for every dialog's live preview: the dividend Gross → Net box, the
# cash dialog's balance preview and the Buy/Sell "cash after trade" box.

def calc_preview_html(title: str, rows: list[tuple[str, str]], total_label: str, total_value: str,
                      total_color: str = "var(--text)") -> str:
    row = ('<div style="display:flex;justify-content:space-between;gap:12px;padding:2px 0;font-size:12px;">'
           '<span style="color:var(--muted);">{l}</span>'
           '<span style="font-family:var(--uv-mono);white-space:nowrap;">{v}</span></div>')
    return (f'<div style="margin-top:4px;padding:10px 12px;border-radius:8px;background:var(--panel-2);">'
            f'<div style="font-size:10px;letter-spacing:0.05em;text-transform:uppercase;color:var(--faint);'
            f'margin-bottom:6px;">{title}</div>'
            + "".join(row.format(l=_html.escape(l), v=v) for l, v in rows)
            + f'<div style="display:flex;justify-content:space-between;gap:12px;padding:6px 0 0;margin-top:4px;'
              f'border-top:0.5px solid var(--line-2);font-size:12.5px;font-weight:500;">'
              f'<span>{_html.escape(total_label)}</span><span style="font-family:var(--uv-mono);white-space:nowrap;'
              f'color:{total_color};">{total_value}</span></div></div>')


def calc_preview(title: str, rows: list[tuple[str, str]], total_label: str, total_value: str,
                 total_color: str = "var(--text)") -> None:
    st.markdown(calc_preview_html(title, rows, total_label, total_value, total_color), unsafe_allow_html=True)


def dividend_tax_preview(gross: float, fwh: float, be: float, net: float) -> None:
    """The Gross -> Foreign WH -> BE 30% -> Net box shared by the Add and
    Edit dividend dialogs (Uvalu Dividend Management.dc.html)."""
    calc_preview(_("Calculated"), [(_("Gross"), fmt_money(gross, "EUR")),
                                   (_("Foreign withholding"), "−" + fmt_money(fwh, "EUR")),
                                   (_("Belgian RV 30%"), "−" + fmt_money(be, "EUR"))],
                 _("Net received"), fmt_money(net, "EUR"), "var(--uv-mint,#1DD6A4)")


DIALOG_WIDTH = 420  # Uvalu.dc.html's modal width — every dialog uses it


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
    some dialogs (wide-enough columns), unlike the mockup's plain fields.

    Header gap: Streamlit pads the title 12px below and the body 12px above,
    and every <style>-only markdown block still took a 16px row gap —
    ~40px between title and subtitle (live-measured). The style blocks now
    sit in zero-size uv_hidden_util containers and the paddings are trimmed.
    The action row gets a little extra room so the Calculated box above it
    doesn't sit on the buttons."""
    with st.container(key="uv_hidden_util_dlg_css"):
        st.markdown(
            f'<style>[data-testid="stDialog"] div:has(> [role="dialog"]) {{ width: {px}px !important; '
            f'max-width: calc(100vw - 32px) !important; }}'
            f'[data-testid="stDialog"] [role="dialog"] {{ width: 100% !important; max-width: 100% !important; }}'
            f'[data-testid="stDialog"] [role="dialog"] > h2 {{ padding-bottom: 0 !important; }}'
            f'[data-testid="stDialog"] [role="dialog"] > h2 + div {{ padding-top: 6px !important; }}'
            f'[data-testid="stDialog"] [class*="st-key-uv_dlg_actions_"] {{ margin-top: 6px !important; }}'
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


def cash_link_line(text: str) -> None:
    """The Edit dialogs' cash-link slot, always just above the action row:
    what happens to this record's cash (a checkbox, when the user can choose,
    is drawn in the same slot instead)."""
    st.caption(text)


def viewer_blocked() -> bool:
    """True (after a read-only notice) for the Viewer role. Every dialog
    checks this itself — the buttons that open dialogs are disabled for
    viewers, but a dialog can also be reached through a hand-off (the
    drawer's Edit button, a pending edit ticker)."""
    from uvalu.runtime import current_user

    if current_user().is_viewer:
        st.caption(_("Viewer role is read-only."))
        return True
    return False


def identity_row(*, ticker: str = "", name: str = "", key_prefix: str, locked: bool = False,
                 ticker_placeholder: str = "", name_placeholder: str = "",
                 ticker_options: list[str] | None = None) -> tuple[str, str]:
    """Ticker + Company name, always first and at the same 1 : 1.4 split as
    the mockup's dividend modal. `locked` (Edit dialogs) shows the same
    fields read-only — changing an existing record's ticker would make it a
    different holding. `ticker_options` turns Ticker into a selectbox that
    suggests those tickers but still accepts any other (Add dividend
    suggests the held ones). Returns (TICKER, name) stripped."""
    _c1, _c2 = st.columns([1, 1.4])
    _t_label = _("Ticker") if locked else _("Ticker *")
    with _c1:
        if ticker_options is not None and not locked:
            t = st.selectbox(_t_label, options=ticker_options, index=None, placeholder=ticker_placeholder,
                             accept_new_options=True, key=f"{key_prefix}_ticker")
        else:
            t = st.text_input(_t_label, value=ticker, placeholder=ticker_placeholder,
                              key=f"{key_prefix}_ticker", disabled=locked)
    with _c2:
        n = st.text_input(_("Company name") if locked else _("Company name (opt.)"), value=name,
                          placeholder=name_placeholder, key=f"{key_prefix}_name", disabled=locked)
    return (t or "").strip().upper(), (n or "").strip()


def _confirm_key(key_prefix: str) -> str:
    return f"_uvdlg_confirm_{key_prefix}"


def _rerun_dialog() -> None:
    """Redraw just this dialog (a fragment rerun) so a state change made by a
    button — entering / leaving the delete confirmation — shows at once,
    extra choices included. Only possible inside a fragment rerun, i.e. an
    interaction within an open dialog; otherwise the change simply shows on
    the next run."""
    from uvalu.ui import dialog_just_opened

    if not dialog_just_opened():
        st.rerun(scope="fragment")


def delete_pending(key_prefix: str) -> bool:
    """True while this dialog shows its delete confirmation — lets a dialog
    draw extra choices (e.g. "Also remove its cash entries") above it."""
    return bool(st.session_state.get(_confirm_key(key_prefix)))


def dialog_actions(key_prefix: str, *, save_label: str | None = None, delete: bool = False,
                   danger_save: bool = False, confirm_text: str = "") -> tuple[bool, bool]:
    """One action row: [Delete] (Edit dialogs, compact red outline, left) |
    Cancel | Save. Cancel closes the dialog. Delete first swaps the row for a
    confirmation (`confirm_text` + Keep | Delete permanently); only that
    second click returns delete=True. Returns (save, delete)."""
    save_label = save_label or _("Save")
    _ck = _confirm_key(key_prefix)
    if delete and st.session_state.get(_ck):
        _q = _("{question} This can't be undone.", question=confirm_text or _("Delete this record?"))
        st.markdown(
            f'<div style="padding:10px 12px;border-radius:8px;background:var(--down-bg);color:var(--down-txt);'
            f'font-size:12.5px;line-height:1.5;">{_html.escape(_q)}</div>', unsafe_allow_html=True)
        with st.container(key=f"uv_dlg_actions_{key_prefix}_confirm"):
            _k1, _k2 = st.columns(2)
            with _k1:
                if st.button(_("Keep"), key=f"{key_prefix}_keep", width="stretch"):
                    st.session_state.pop(_ck, None)
                    _rerun_dialog()
            with _k2, st.container(key=f"uv_danger_btn_{key_prefix}_confirm"):
                _confirmed = st.button(_("Delete permanently"), key=f"{key_prefix}_delete_confirm",
                                       width="stretch", type="primary")
        return False, _confirmed

    with st.container(key=f"uv_dlg_actions_{key_prefix}"):
        _cols = st.columns([0.8, 1, 1] if delete else [1, 1])
        if delete:
            with _cols[0], st.container(key=f"uv_danger_btn_{key_prefix}"):
                if st.button(_("Delete"), key=f"{key_prefix}_delete", width="stretch"):
                    st.session_state[_ck] = True
                    _rerun_dialog()
        with _cols[-2]:
            if st.button(_("Cancel"), key=f"{key_prefix}_cancel", width="stretch"):
                st.rerun()
        with _cols[-1]:
            if danger_save:
                with st.container(key=f"uv_danger_btn_{key_prefix}_save"):
                    _do_save = st.button(save_label, key=f"{key_prefix}_save", width="stretch", type="primary")
            else:
                _do_save = st.button(save_label, key=f"{key_prefix}_save", width="stretch", type="primary")
    return _do_save, False


def _num_or(value, default):
    """pd.to_numeric-coerced value, or `default` if missing/unparseable/NaN.
    `pd.to_numeric(value, errors="coerce") or default` doesn't work here --
    NaN is truthy in Python, so a NaN field (e.g. an Excel-imported position
    with a blank shares cell) passes straight through instead of falling
    back, and `int(nan)` raises ValueError rather than silently corrupting."""
    v = pd.to_numeric(value, errors="coerce")
    return v if pd.notna(v) else default


def _to_date(v) -> "_dt.date | None":
    d = pd.to_datetime(v, format="mixed", dayfirst=False, errors="coerce")
    return d.date() if pd.notna(d) else None


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


def _mutation_errors() -> tuple:
    """Exceptions a save can raise with a user-facing message: a cash rule
    (CashError), a missing FX rate, a record deleted in the meantime."""
    import cash
    import fx
    return cash.CashError, fx.FxUnavailable, ValueError


# ── Cash after trade (Cash Management v1) ────────────────────────────────────
# Buy/Sell show the balance a trade leaves behind (Uvalu Cash
# Management.dc.html's ap/sell modals), in the shared Calculated box. Trades
# are never blocked by the balance (user decision D3): a shortfall shows as an
# automatic top-up line instead of the mockup's red "blocked" state.

def cash_after_html(kind: str, gross: float, fee: float, on=None) -> str:
    import cash
    try:
        p = cash.preview_trade(kind, max(float(gross or 0.0), 0.0), max(float(fee or 0.0), 0.0), on=on)
        cur = cash.balance()
    except Exception:
        return ""
    base = "EUR"
    rows = [(_("Current balance"), cash.money(cur, base)),
            (_("This buy") if kind == "Buy" else _("This sale"), cash.signed_money(p["amount"], base))]
    if p["topup"] > 0:
        rows.append((_("Auto top-up from outside cash"), "+" + cash.money(p["topup"], base)))
    return calc_preview_html(_("Cash · {currency} base", currency=base), rows, _("Cash after trade"),
                             cash.money(p["after"], base))


# ── Positions ────────────────────────────────────────────────────────────────
# Standard layout (Add / Edit / Close alike): identity → dates row (date |
# fees) → amounts row → Cash box → [Edit: cash-link slot, Sell link] →
# actions.

@_dialog(N_("Add position"))
def add_position_dialog(preset_ticker: str = "", preset_name: str = "", preset_price: float = 0.0) -> None:
    enter_dialog()
    dialog_frame(_("Enter a total cost or a price per share."))
    if viewer_blocked():
        return
    ticker_raw, name_raw = identity_row(ticker=preset_ticker, name=preset_name, key_prefix="dlg_ap",
                                        ticker_placeholder="TTE.PA", name_placeholder="TotalEnergies")

    # Buy date defaults to today; a backdated buy posts its cash on that
    # date, so the ledger's running balance stays in date order.
    _today = _dt.date.today()
    _c1, _c2 = st.columns(2)
    with _c1:
        pur_date = st.date_input(_("Buy date *"), value=_today, max_value=_today, format=date_input_format(),
                                 key="dlg_ap_date") or _today
    with _c2:
        fee = _nz(number_field(_("Fees (opt.)"), min_value=0.0, step=0.01, value=0.0,
                               format="%.2f", key="dlg_ap_fee"), 0.0)
    _c3, _c4, _c5 = st.columns(3)
    with _c3:
        shares = _nz(number_field(_("Shares *"), min_value=1, step=1, value=1, key="dlg_ap_shares"))
    with _c4:
        total_cost = _nz(number_field(_("Total cost (€) *"), min_value=0.0, step=0.01, value=0.0,
                                      format="%.2f", key="dlg_ap_cost"), 0.0)
    with _c5:
        price = _nz(number_field(_("Price / share (opt.)"), min_value=0.0, step=0.01,
                                 value=round(preset_price, 2), format="%.2f", key="dlg_ap_price"), 0.0)
    _gross_preview = total_cost if total_cost > 0 else round(price * shares, 2)
    st.markdown(cash_after_html("Buy", _gross_preview, fee, on=pur_date), unsafe_allow_html=True)

    _do_save = dialog_actions("dlg_ap")[0]

    if not _do_save:
        return
    if not ticker_raw:
        st.error(_("Enter a ticker symbol."))
        return
    _looked_up = _lookup_ticker(ticker_raw)
    if _looked_up is None:
        st.error(_("Ticker **{ticker}** not found. Check the symbol and try again.", ticker=ticker_raw))
        return
    _yf_name = _looked_up[0]
    _total = total_cost if total_cost > 0 else round(price * shares, 2)
    if _total <= 0 or shares <= 0:
        st.error(_("Enter shares and either a total cost or a price per share."))
        return
    record_buy({
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
    }, fee=fee)
    st.rerun()


def _edit_cash_box(kind: str, trade_id: str, *, sync: bool, gross: float, fee: float, on) -> None:
    """Cash box for Edit position / Edit trade: what saving does to the
    balance — the re-posted trade when the linked entry is updated, else no
    change."""
    import cash
    base = "EUR"
    cur = cash.balance()
    if not sync:
        calc_preview(_("Cash · {currency} base", currency=base), [(_("Current balance"), cash.money(cur, base)),
                                                                   (_("Change"), _("no cash change"))],
                     _("Balance after"), cash.money(cur, base))
        return
    p = cash.preview_repost(kind, trade_id, gross=max(gross, 0.0), fee=max(fee, 0.0), on=on)
    rows = [(_("Current balance"), cash.money(cur, base)), (_("Change"), cash.signed_money(p["change"], base))]
    if p["topup"] > 0:
        rows.append((_("Auto top-up from outside cash"), "+" + cash.money(p["topup"], base)))
    calc_preview(_("Cash · {currency} base", currency=base), rows, _("Balance after"), cash.money(p["after"], base))


@_dialog(N_("Edit position"))
def edit_position_dialog(trade_id: str, live_price: float | None = None) -> None:
    import cash
    from portfolio import get_position, update_position, delete_position

    enter_dialog()
    dialog_frame(_("Update shares, total cost or buy date."))
    if viewer_blocked():
        return
    row = get_position(trade_id)
    if row is None:
        st.error(_("This position no longer exists."))
        return
    identity_row(ticker=str(row["ticker"]), name=str(row["name"]), key_prefix="dlg_eop_id", locked=True)
    _pv0 = round(float(_num_or(row.get("purchase_value"), 0.0)), 2)
    _fee0 = round(float(_num_or(row.get("fee"), 0.0)), 2)
    _sh0 = max(1, int(_num_or(row.get("shares"), 1)))
    _linked = cash.trade_in_sync("Buy", trade_id, _pv0, _fee0)

    _c1, _c2 = st.columns(2)
    with _c1:
        _d0 = _to_date(row.get("date_in"))
        _date = st.date_input(_("Buy date *"), value=_d0, max_value=max(_dt.date.today(), _d0 or _dt.date.today()),
                              format=date_input_format(), key="dlg_eop_date")
    with _c2:
        _fee = _nz(number_field(_("Fees (opt.)"), min_value=0.0, step=0.01, value=_fee0, format="%.2f",
                                key="dlg_eop_fee", disabled=not _linked,
                                help=None if _linked else _("Fees only affect the linked cash entry.")), 0.0)
    _c3, _c4, _c5 = st.columns(3)
    with _c3:
        _shares = _nz(number_field(_("Shares *"), min_value=1, step=1, value=_sh0, key="dlg_eop_shares"), _sh0)
    with _c4:
        _invested = _nz(number_field(_("Total cost (€) *"), min_value=0.01, step=0.01, value=max(_pv0, 0.01),
                                     format="%.2f", key="dlg_eop_invested"), 0.0)
    with _c5:
        _price0 = round(_pv0 / _sh0, 2)
        _price = _nz(number_field(_("Price / share (opt.)"), min_value=0.0, step=0.01, value=_price0,
                                  format="%.2f", key="dlg_eop_price"), _price0)
    # Same two ways in as Add position: a changed price per share sets the
    # total cost (price × shares); otherwise Total cost is used as entered.
    _total = round(_price * _shares, 2) if abs(_price - _price0) > 0.004 and _price > 0 else float(_invested)

    _pending = delete_pending("dlg_eop")
    _sync = bool(st.session_state.get("dlg_eop_sync", True)) and _linked and not _pending
    _edit_cash_box("Buy", trade_id, sync=_sync, gross=_total, fee=_fee, on=_date or _d0)

    # Cash-link slot, then the secondary Sell link.
    _remove_cash = False
    if _pending:
        if _linked:
            _remove_cash = st.checkbox(_("Also remove its cash entries"), value=True, key="dlg_eop_rm_cash")
    else:
        if _linked:
            _sync = st.checkbox(_("Also update the linked cash entry"), value=True, key="dlg_eop_sync",
                                help=_("Re-posts the buy ({trade_id}) at the new cost, fees and date.", trade_id=trade_id))
        else:
            cash_link_line(_("No cash change — the ledger keeps this buy as recorded."))
        # Selling opens the Close position dialog (dialogs can't nest): hand
        # the request to app.py's dispatch_pending_drawer_action.
        if st.button(_("Sell shares…"), key="dlg_eop_sell", type="tertiary", icon=":material/sell:"):
            st.session_state["_drw_action"] = {"kind": "sell", "ticker": str(row["ticker"]),
                                               "price": live_price}
            st.rerun()

    _do_save, _do_delete = dialog_actions("dlg_eop", delete=True,
                                          confirm_text=_("Delete {ticker} ({shares} shares)?",
                                                         ticker=row['ticker'], shares=fmt_int(int(_shares))))
    try:
        if _do_save:
            if _date is None:
                st.error(_("Buy date is required."))
                return
            update_position(trade_id, shares=int(_shares), invested=_total, date_in=_date,
                            fee=float(_fee), sync_cash=_sync)
            st.rerun()
        if _do_delete:
            delete_position(trade_id, remove_cash=_remove_cash)
            st.rerun()
    except _mutation_errors() as exc:
        st.error(str(exc))


@_dialog(N_("Close position"))
def sell_position_dialog(pf: "pd.DataFrame", ticker: str | None = None,
                         preset_price: float | None = None) -> None:
    from uvalu.i18n import sort_df
    enter_dialog()
    dialog_frame(_("Sell all or part of this position."))
    if viewer_blocked():
        return
    if ticker is None:
        _sorted = sort_df(pf, "name")
        _opts   = _sorted["ticker"].tolist()
        _labels = {r["ticker"]: f"{r['name']}  ({r['ticker']})" for _i, r in _sorted.iterrows()}
        ticker = st.selectbox(_("Company *"), options=_opts, format_func=lambda t: _labels.get(t, t),
                              key="dlg_sell_ticker")
        _match = pf[pf["ticker"] == ticker]
    else:
        _match = pf[pf["ticker"] == ticker]
        identity_row(ticker=ticker, name=str(_match.iloc[0]["name"]) if not _match.empty else "",
                     key_prefix="dlg_sell_id", locked=True)

    _held_shares = int(_num_or(_match["shares"].sum() if not _match.empty else 0, 0))
    if preset_price is not None:
        _live_price = float(preset_price)
    else:
        _live_price = float(_num_or(_match.iloc[0].get("live_price"), 0.0)) \
            if not _match.empty else 0.0

    _today = _dt.date.today()
    _c1, _c2 = st.columns(2)
    with _c1:
        sell_date = st.date_input(_("Sell date *"), value=_today, max_value=_today, format=date_input_format(),
                                  key="dlg_sell_date") or _today
    with _c2:
        fee = _nz(number_field(_("Fees (opt.)"), min_value=0.0, step=0.01, value=0.0,
                               format="%.2f", key="dlg_sell_fee"), 0.0)
    _c3, _c4 = st.columns(2)
    with _c3:
        shares = _nz(number_field(_("Shares to sell *"), min_value=1, max_value=max(_held_shares, 1),
                                  value=max(_held_shares, 1), step=1, key="dlg_sell_shares"))
    with _c4:
        price = _nz(number_field(_("Sell price *"), min_value=0.0, step=0.01, value=round(_live_price, 2),
                                 format="%.2f", key="dlg_sell_price"), 0.0)
    st.markdown(cash_after_html("Sell", round(shares * price, 2), fee, on=sell_date), unsafe_allow_html=True)

    _do_save = dialog_actions("dlg_sell", save_label=_("Confirm sale"), danger_save=True)[0]

    if not _do_save:
        return
    if shares <= 0 or price <= 0:
        st.error(_("Enter the shares to sell and a sell price."))
        return
    record_sell(ticker, shares, price, fee, pd.Timestamp(sell_date).isoformat())
    st.rerun()


# ── Dividends ────────────────────────────────────────────────────────────────

def _dividend_dates_error(ex_date, pay_date) -> str | None:
    if ex_date is None:
        return _("Ex-dividend date is required.")
    if pay_date is None:
        return _("Payment date is required.")
    if ex_date > pay_date:
        return _("The ex-dividend date must be on or before the payment date.")
    return None


@_dialog(N_("Add dividend"))
def add_dividend_dialog(pf: "pd.DataFrame") -> None:
    from portfolio import currency_for_ticker, exchange_key_for_ticker
    from settings import get_dividend_withholding
    from uvalu.runtime import current_user

    enter_dialog()
    dialog_frame(_("Record a dividend payment for a holding."))
    if viewer_blocked():
        return
    _held = sorted(pf["ticker"].dropna().astype(str).unique().tolist()) if "ticker" in pf.columns else []
    # The company name defaults from the held position once the ticker is
    # known, so read the ticker's current value before drawing the row.
    _t0 = str(st.session_state.get("dlg_dv_ticker") or "").strip().upper()
    _match = pf[pf["ticker"] == _t0] if _t0 and "ticker" in pf.columns else pf.iloc[0:0]
    _default_name = _match.iloc[0]["name"] if not _match.empty else ""
    ticker_raw, name_raw = identity_row(name=_default_name, key_prefix="dlg_dv", ticker_options=_held,
                                        ticker_placeholder="ALV.DE", name_placeholder="Allianz")
    _ccy = currency_for_ticker(ticker_raw) if ticker_raw else "EUR"

    # Declaration/record dates and per-holding frequency were dropped from
    # this dialog (and the Edit dialog / CSV export) per user review: only
    # the ex-date and payment date are asked for, in one readable row.
    _c3, _c4 = st.columns(2)
    with _c3:
        ex_date = st.date_input(_("Ex-dividend date *"), value=None, format=date_input_format(),
                                max_value=_dt.date.today() + _dt.timedelta(days=365), key="dlg_dv_ex")
    with _c4:
        pay_date = st.date_input(_("Payment date *"), format=date_input_format(), max_value=_dt.date.today(),
                                 key="dlg_dv_pay")

    _c5, _c6, _c7 = st.columns(3)
    with _c5:
        _shares0 = int(_num_or(_match["shares"].sum(), 0)) if not _match.empty else 0
        shares = _nz(number_field(_("Shares held *"), min_value=0, step=1, value=_shares0, key="dlg_dv_shares"))
    with _c6:
        dps = _nz(number_field(_("Per share ({currency}) *", currency=_ccy), min_value=0.0, step=0.0001, value=0.0,
                               format="%.4f", key="dlg_dv_ps"), 0.0)
    with _c7:
        _default_tax = get_dividend_withholding(exchange_key_for_ticker(ticker_raw), current_user().email)
        tax_rate = _nz(number_field(_("Foreign WH (%)"), min_value=0.0, max_value=100.0,
                                    step=0.5, value=_default_tax, key="dlg_dv_tax"), 0.0)

    div_type = st.selectbox(_("Type"), options=DIV_TYPE_OPTIONS, format_func=tr, key="dlg_dv_type")

    if div_type == "Special":
        st.caption(_("Flagged as special / one-off. Excluded from growth-streak and yield calculations."))

    gross = round(dps * shares, 2)
    fwh, be, net = _dividend_tax_breakdown(gross, tax_rate, div_type)
    dividend_tax_preview(gross, fwh, be, net)

    _do_save = dialog_actions("dlg_dv")[0]

    if not _do_save:
        return
    if not ticker_raw or gross <= 0:
        st.error(_("Enter a ticker, shares held and a gross amount per share."))
        return
    _err = _dividend_dates_error(ex_date, pay_date)
    if _err:
        st.error(_err)
        return
    _google_ticker = _match.iloc[0].get("google_ticker", "") if not _match.empty else ""
    add_dividend({
        "name":              name_raw or (_default_name or ticker_raw),
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


@_dialog(N_("Edit dividend"))
def edit_dividend_dialog(div_id: str) -> None:
    from portfolio import currency_for_ticker, get_dividend, update_dividend, delete_dividend

    enter_dialog()
    dialog_frame(_("Update this dividend's dates, amounts or type."))
    if viewer_blocked():
        return
    row = get_dividend(div_id)
    if row is None:
        st.error(_("This dividend no longer exists."))
        return
    identity_row(ticker=str(row["ticker"]), name=str(row.get("name") or ""), key_prefix="dlg_ed_id", locked=True)
    # A missing currency comes back as NaN (truthy), which used to render the
    # label as "Gross / share (nan)".
    _ccy = row.get("currency")
    if not isinstance(_ccy, str) or not _ccy.strip():
        _ccy = currency_for_ticker(str(row["ticker"])) or "EUR"

    _row_pay = _to_date(row.get("date"))
    _max_date = max(_dt.date.today(), _row_pay) if _row_pay else _dt.date.today()

    # Same fields/order as add_dividend_dialog. Saving leaves any
    # declaration/record date a record already carries untouched.
    _c1, _c2 = st.columns(2)
    with _c1:
        _ex = st.date_input(_("Ex-dividend date *"), value=_to_date(row.get("ex_date")), format=date_input_format(),
                            max_value=_max_date, key="dlg_ed_ex")
    with _c2:
        _date = st.date_input(_("Payment date *"), value=_row_pay, format=date_input_format(),
                              max_value=_max_date, key="dlg_ed_date")

    _c5, _c6, _c7 = st.columns(3)
    _sh0 = float(_num_or(row.get("shares"), 0))
    with _c5:
        _shares = _nz(number_field(_("Shares held *"), min_value=0, step=1, value=max(0, int(_sh0)),
                                   key="dlg_ed_shares"))
    with _c6:
        _dps0 = float(_num_or(row.get("amount_per_share"), 0.0)) or (
            float(_num_or(row.get("amount"), 0.0)) / _sh0 if _sh0 else 0.0)
        _dps = _nz(number_field(_("Per share ({currency}) *", currency=_ccy), min_value=0.0, step=0.0001,
                                value=round(float(_dps0), 4), format="%.4f", key="dlg_ed_dps"), 0.0)
    with _c7:
        _tax_rate = _nz(number_field(_("Foreign WH (%)"), min_value=0.0, max_value=100.0, step=0.5,
                                     value=float(_num_or(row.get("tax_rate"), 0.0)), key="dlg_ed_tax"), 0.0)

    _type0 = row.get("div_type") if isinstance(row.get("div_type"), str) else "Cash"
    _type = st.selectbox(_("Type"), options=DIV_TYPE_OPTIONS, format_func=tr,
                         index=DIV_TYPE_OPTIONS.index(_type0) if _type0 in DIV_TYPE_OPTIONS else 0,
                         key="dlg_ed_type")

    _gross = round(_dps * _shares, 2)
    _fwh, _be, _net = _dividend_tax_breakdown(_gross, _tax_rate, _type)
    dividend_tax_preview(_gross, _fwh, _be, _net)

    # Cash-link slot: the ledger mirrors dividends by itself
    # (cash.reconcile_dividend_postings), so there is no choice to make here.
    if bool(_num_or(row.get("reinvested"), False)):
        cash_link_line(_("Reinvested (DRIP): no cash entry. The purchased shares were already added to the position and aren't re-applied by editing this record."))
    elif _type == "Stock":
        cash_link_line(_("Stock dividend: no cash entry."))
    elif _date is not None and _date > _dt.date.today():
        cash_link_line(_("The cash entry posts automatically on the payment date."))
    else:
        cash_link_line(_("Cash entry follows automatically (net {currency} {amount}).",
                         currency=_ccy, amount=fmt_num(_net, 2)))

    _auto = row.get("source") == "auto"
    _do_save, _do_delete = dialog_actions(
        "dlg_ed", delete=True,
        confirm_text=(_("Delete this {ticker} dividend? It came from market data and won't be imported again.",
                        ticker=row['ticker']) if _auto else _("Delete this {ticker} dividend?", ticker=row['ticker'])))
    try:
        if _do_save:
            _err = _dividend_dates_error(_ex, _date)
            if _err:
                st.error(_err)
                return
            if _gross <= 0:
                st.error(_("Enter shares held and a gross amount per share."))
                return
            update_dividend(div_id, {
                "shares": int(_shares), "amount": _gross, "amount_per_share": round(_dps, 4),
                "tax_rate": round(_tax_rate, 2), "tax_amount": _fwh, "div_type": _type,
                "ex_date": pd.Timestamp(_ex).isoformat(), "date": pd.Timestamp(_date).isoformat(),
            })
            st.rerun()
        if _do_delete:
            delete_dividend(div_id)
            st.rerun()
    except _mutation_errors() as exc:
        st.error(str(exc))


# ── Closed trades ────────────────────────────────────────────────────────────
# Add trade / Edit trade share one layout: identity → Sell date | Sector →
# Shares | Buy price | Sell price → Result box → [Edit: cash-link slot] →
# actions.

def trade_result_preview(shares: float, buy: float, sell: float) -> None:
    """Cost basis → Proceeds → Realised P&L, in the shared Calculated box."""
    cost, proceeds = round(buy * shares, 2), round(sell * shares, 2)
    pl = round(proceeds - cost, 2)
    pct = f" · {fmt_pct(pl / cost * 100, signed=True)}" if cost else ""
    calc_preview(_("Result"), [(_("Cost basis"), fmt_money(cost, "EUR")), (_("Proceeds"), fmt_money(proceeds, "EUR"))],
                 _("Realised P&L"), f"{'+' if pl >= 0 else '−'}{fmt_money(abs(pl), 'EUR')}{pct}",
                 "var(--up-txt)" if pl >= 0 else "var(--down-txt)")


def _trade_fields(key: str, *, date0, sector0: str | None, shares0: int, buy0: float, sell0: float,
                  max_date) -> tuple:
    _c1, _c2 = st.columns(2)
    with _c1:
        d = st.date_input(_("Sell date *"), value=date0, max_value=max_date, format=date_input_format(), key=f"{key}_date")
    with _c2:
        sector = st.selectbox(_("Sector"), options=SECTOR_OPTIONS, placeholder="—", format_func=tr,
                              index=SECTOR_OPTIONS.index(sector0) if sector0 in SECTOR_OPTIONS else None,
                              key=f"{key}_sector")
    _c3, _c4, _c5 = st.columns(3)
    with _c3:
        shares = _nz(number_field(_("Shares *"), min_value=1, step=1, value=shares0, key=f"{key}_shares"))
    with _c4:
        buy = _nz(number_field(_("Buy price *"), min_value=0.0, step=0.01, value=buy0, format="%.2f",
                               key=f"{key}_buy"), 0.0)
    with _c5:
        sell = _nz(number_field(_("Sell price *"), min_value=0.0, step=0.01, value=sell0, format="%.2f",
                                key=f"{key}_sell"), 0.0)
    trade_result_preview(shares, buy, sell)
    return d, sector, shares, buy, sell


@_dialog(N_("Add trade"))
def add_closed_trade_dialog() -> None:
    enter_dialog()
    dialog_frame(_("Record a trade opened and closed elsewhere."))
    if viewer_blocked():
        return
    ticker_raw, name_raw = identity_row(key_prefix="dlg_ct", ticker_placeholder="SAP.DE",
                                        name_placeholder="SAP")
    _today = _dt.date.today()
    closed_date, sector, shares, buy_price, sell_price = _trade_fields(
        "dlg_ct", date0=_today, sector0=None, shares0=1, buy0=0.0, sell0=0.0, max_date=_today)
    closed_date = closed_date or _today

    _do_save = dialog_actions("dlg_ct")[0]

    if not _do_save:
        return
    if not ticker_raw or shares <= 0 or buy_price <= 0 or sell_price <= 0:
        st.error(_("Enter a ticker, shares, and both a buy and sell price."))
        return
    _looked_up = _lookup_ticker(ticker_raw)
    if _looked_up is None:
        st.error(_("Ticker **{ticker}** not found. Check the symbol and try again.", ticker=ticker_raw))
        return
    _closed_iso = pd.Timestamp(closed_date).isoformat()
    add_closed_trade({
        "name":              name_raw or _looked_up[0],
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


@_dialog(N_("Edit trade"))
def edit_closed_trade_dialog(trade_id: str) -> None:
    """Same fields as Add trade. Buy and sell are per-share prices, so
    changing the share count rescales both the cost basis and the proceeds."""
    import cash
    from portfolio import get_closed_trade, update_closed_trade, delete_closed_trade

    enter_dialog()
    dialog_frame(_("Update shares, prices, sector or sell date."))
    if viewer_blocked():
        return
    row = get_closed_trade(trade_id)
    if row is None:
        st.error(_("This trade no longer exists."))
        return
    identity_row(ticker=str(row["ticker"]), name=str(row.get("name") or ""), key_prefix="dlg_ecp_id",
                 locked=True)
    _sh0 = max(1, int(_num_or(row.get("shares"), 1)))
    _pv0 = float(_num_or(row.get("purchase_value"), 0.0))
    _sv0 = float(_num_or(row.get("sale_value"), 0.0))
    _fee0 = float(_num_or(row.get("fee"), 0.0))
    _linked = cash.trade_in_sync("Sell", trade_id, _sv0, _fee0)

    _d0 = _to_date(row.get("date_out"))
    _date, _sector, _shares, _buy, _sell = _trade_fields(
        "dlg_ecp", date0=_d0, sector0=row.get("sector"), shares0=_sh0, buy0=round(_pv0 / _sh0, 2),
        sell0=round(_sv0 / _sh0, 2), max_date=max(_dt.date.today(), _d0 or _dt.date.today()))

    # Cash-link slot.
    _sync = _remove_cash = False
    if delete_pending("dlg_ecp"):
        if _linked:
            _remove_cash = st.checkbox(_("Also remove its cash entries"), value=True, key="dlg_ecp_rm_cash")
    elif _linked:
        _sync = st.checkbox(_("Also update the linked cash entry"), value=True, key="dlg_ecp_sync",
                            help=_("Re-posts the sale ({trade_id}) at the new proceeds and date.", trade_id=trade_id))
    else:
        cash_link_line(_("No cash change — the ledger keeps this trade as recorded."))

    _do_save, _do_delete = dialog_actions("dlg_ecp", delete=True,
                                          confirm_text=_("Delete this {ticker} trade?", ticker=row['ticker']))
    try:
        if _do_save:
            if _date is None:
                st.error(_("Sell date is required."))
                return
            if _buy <= 0 or _sell <= 0:
                st.error(_("Enter both a buy and a sell price."))
                return
            # Round-trip the prices only when they changed, so an untouched
            # dialog saves back the exact stored totals (a price shown at 2dp
            # times the shares can be a cent off the original total).
            _buy_ps = _pv0 / _sh0 if int(_shares) == _sh0 and abs(_buy - round(_pv0 / _sh0, 2)) < 1e-9 else _buy
            _sell_ps = _sv0 / _sh0 if int(_shares) == _sh0 and abs(_sell - round(_sv0 / _sh0, 2)) < 1e-9 else _sell
            update_closed_trade(trade_id, shares=int(_shares), buy_price=_buy_ps, sell_price=_sell_ps,
                                date_out=_date, sector=_sector, sync_cash=_sync)
            st.rerun()
        if _do_delete:
            delete_closed_trade(trade_id, remove_cash=_remove_cash)
            st.rerun()
    except _mutation_errors() as exc:
        st.error(str(exc))


# ── Cash transactions (Cash Management v1) ───────────────────────────────────
# Uvalu Cash Management.dc.html's "Add cash transaction" modal — Type,
# Date / Amount / Currency with an ECB-rate panel (auto → "Enter manually";
# manual or frankfurter outage → amber panel with a flagged rate), the
# Adjustment variant (corrected balance), an optional note and the
# Calculated preview. The Edit dialog is the same form, pre-filled with its
# type and currency locked. Trades and dividends never come through here —
# they post automatically, and their rows open the same Edit form read-only.

CASH_TX_TYPES = [N_("Deposit"), N_("Withdrawal"), N_("Fee"), N_("Interest"), N_("Adjustment")]
CASH_OUTAGE_TEXT = N_("frankfurter.dev is unreachable or has no rate for this date. Enter the rate manually; the entry will be flagged.")
# "This deposit", … — the Calculated box's row for the entry being added.
_THIS_TYPE = {"Deposit": N_("This deposit"), "Withdrawal": N_("This withdrawal"), "Fee": N_("This fee"),
              "Interest": N_("This interest"), "Adjustment": N_("This adjustment"),
              "Buy": N_("This buy"), "Sell": N_("This sale"), "Dividend": N_("This dividend")}
_CASH_BASIS = "_uvdlg_cash_basis"
_CASH_MODE = "_uvdlg_cash_mode"   # "keep" (stored rate, Edit) | "ecb" | "manual"


def _cash_dialog_css() -> None:
    with st.container(key="uv_hidden_util_dlg_cash_css"):
        _cash_dialog_css_block()


def _cash_dialog_css_block() -> None:
    st.markdown(
        '<style>'
        '.st-key-uv_cash_fx_manual { border:0.5px solid #C98A3A !important; background:rgba(201,138,58,0.08) !important;'
        ' border-radius:8px !important; padding:10px 12px !important; }'
        '.st-key-uv_cash_fx_auto { border:0.5px solid var(--line) !important; border-radius:8px !important;'
        ' padding:6px 12px !important; }'
        '.st-key-uv_cash_fx_auto button p, .st-key-uv_cash_fx_manual button p { color:var(--teal) !important;'
        ' font-size:11.5px !important; white-space:nowrap !important; }'
        '</style>', unsafe_allow_html=True)


def _set_cash_mode(mode: str) -> None:
    st.session_state[_CASH_MODE] = mode


def _cash_rate_panel(ccy: str, base: str, d: "_dt.date", entry: dict | None) -> tuple[float, bool, float | None]:
    """The FX panel for a non-base currency. Returns (rate, manual,
    manual_rate); rate 0.0 when a manual rate is still missing."""
    import cash
    import fx

    mode = st.session_state.get(_CASH_MODE, "ecb")
    quote = None
    outage = False
    if mode == "ecb":
        try:
            quote = fx.get_rate(ccy, base, d)
        except fx.FxUnavailable:
            outage = True
            mode = "manual"
    if mode in ("keep", "ecb"):
        if mode == "keep":
            _rate = float(entry["fx_rate"])
            _sub = _("Rate stored with this entry · ECB {date}",
                     date=cash.fmt_date(entry.get('fx_date') or entry['date']))
        else:
            _rate = quote.rate
            _sub = _("ECB reference rate for {date} · frankfurter.dev", date=cash.fmt_date(quote.rate_date.isoformat()))
        with st.container(key="uv_cash_fx_auto", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;min-width:0;">'
                f'<span style="width:6px;height:6px;border-radius:50%;background:var(--mint);flex:none;"></span>'
                f'<div style="min-width:0;"><div style="font-family:var(--uv-mono);font-size:12.5px;">'
                f'1 {ccy} = {cash.money(_rate, base, 4)}</div>'
                f'<div style="font-size:10.5px;color:var(--faint);margin-top:2px;">{_sub}</div></div></div>',
                unsafe_allow_html=True, width="content")
            st.button(_("Enter manually"), key="dlg_cash_use_manual", type="tertiary",
                      on_click=_set_cash_mode, args=("manual",))
        return _rate, False, None

    _default = None
    if entry is not None and entry.get("currency") == ccy and entry.get("fx_rate"):
        _default = round(float(entry["fx_rate"]), 4)
    with st.container(key="uv_cash_fx_manual"):
        if outage:
            st.markdown(f'<div style="font-size:11.5px;color:#C98A3A;line-height:1.5;">{_html.escape(_(CASH_OUTAGE_TEXT))}</div>',
                        unsafe_allow_html=True)
        _m1, _m2 = st.columns([0.9, 1.1], vertical_alignment="center")
        with _m1:
            st.markdown(f'<span style="font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);'
                        f'white-space:nowrap;">1 {ccy} = {"€" if base == "EUR" else base}</span>',
                        unsafe_allow_html=True)
        with _m2:
            manual_rate = number_field(_("Rate"), min_value=0.0, step=0.0001, format="%.4f",
                                       label_visibility="collapsed", value=_default, placeholder=_("Rate"),
                                       key="dlg_cash_rate")
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            st.markdown('<span style="font-size:9.5px;font-family:var(--uv-mono);padding:2px 7px;'
                        'border-radius:5px;background:var(--amber-bg);color:var(--amber-txt);'
                        f'white-space:nowrap;">{_html.escape(_("Manual rate · flagged"))}</span>', unsafe_allow_html=True, width="content")
            if not outage:
                st.button(_("Use ECB rate"), key="dlg_cash_use_auto", type="tertiary",
                          on_click=_set_cash_mode, args=("ecb",))
    return (manual_rate or 0.0), True, manual_rate


def _cash_form(entry: dict | None, preset_type: str = "Deposit", *, readonly: bool = False) -> None:
    """Add / Edit cash transaction, one layout: Type | Currency (identity,
    locked in Edit) → Date | Amount → FX panel → Note → Calculated →
    [Edit: cash-link slot] → actions. `readonly` draws an automatic entry
    (trade, top-up, dividend) in the same form, every field locked, with a
    button to the record it mirrors instead of Delete / Save."""
    import cash
    import fx
    from portfolio import base_currency

    _cash_dialog_css()
    base = base_currency()
    entries = cash.load_ledger()
    today = _dt.date.today()
    is_edit = entry is not None
    locked = is_edit  # identity (type, currency) never changes on an existing entry

    _type = entry["type"] if is_edit else (preset_type if preset_type in CASH_TX_TYPES else "Deposit")
    is_adj = _type == "Adjustment"
    d0 = _dt.date.fromisoformat(str(entry["date"])[:10]) if is_edit else today
    _max_d = max(today, d0)
    others = [e for e in entries if not is_edit or e.get("id") != entry["id"]]
    _ccy0 = (entry.get("currency") or base) if is_edit else base

    # ── Identity row: Type | Currency ────────────────────────────────────────
    _i1, _i2 = st.columns([1, 1.4])
    with _i1:
        if locked:
            _label = tr(_type) + (" · " + _("top-up") if entry.get("topup") else "")
            st.selectbox(_("Type"), options=[_label], key="dlg_cash_type", disabled=True)
        else:
            _type = st.selectbox(_("Type *"), options=CASH_TX_TYPES, index=CASH_TX_TYPES.index(_type),
                                 format_func=tr, key="dlg_cash_type")
            is_adj = _type == "Adjustment"
    with _i2:
        _opts = fx.supported_currencies()
        if base not in _opts:
            _opts = [base] + _opts
        if _ccy0 not in _opts:
            _opts = _opts + [_ccy0]
        if is_adj:
            # A corrected balance is always in the base currency.
            ccy = st.selectbox(_("Currency"), options=[base], key="dlg_cash_ccy_adj", disabled=True)
        else:
            ccy = st.selectbox(_("Currency"), options=_opts, index=_opts.index(_ccy0), key="dlg_cash_ccy",
                               disabled=locked)

    # ── Date | Amount ────────────────────────────────────────────────────────
    rate, manual, manual_rate = 1.0, False, None
    amount, target = 0.0, None
    _c1, _c2 = st.columns(2)
    with _c1:
        d = st.date_input(_("Date") if readonly else _("Date *"), value=d0, max_value=_max_d, format=date_input_format(),
                          key="dlg_cash_date", disabled=readonly) or d0
    with _c2:
        if is_adj:
            target = number_field(_("Corrected balance ({currency}) *", currency=base), min_value=0.0, step=0.01,
                                  value=(round(float(entry.get("target_balance") or 0.0), 2) if is_edit else None),
                                  format="%.2f", placeholder=_("Balance per broker"), key="dlg_cash_target")
        else:
            _amt0 = round(abs(float(entry.get("amount") or 0.0)), 2) if is_edit else 0.0
            amount = _nz(number_field(_("Amount") if readonly else _("Amount *"), min_value=0.0, step=0.01,
                                      value=_amt0, format="%.2f", key="dlg_cash_amt", disabled=readonly), 0.0)

    if is_adj:
        _before = cash.balance_before(others, d)
        st.caption(_("Current balance {amount}. Saved as a separate correction entry; earlier entries stay unchanged.",
                     amount=cash.money(_before, base)) if d >= today else
                   _("Balance on that date {amount}. Saved as a separate correction entry; earlier entries stay unchanged.",
                     amount=cash.money(_before, base)))
    elif readonly:
        if ccy != base:
            rate = float(entry.get("fx_rate") or 1.0)
            _stored_on = cash.fmt_date(entry.get("fx_date") or entry["date"])
            _src = (_("Manual rate stored with this entry · {date}", date=_stored_on)
                    if entry.get("fx_source") == "manual" else
                    _("ECB reference rate stored with this entry · {date}", date=_stored_on))
            with st.container(key="uv_cash_fx_auto"):
                st.markdown(
                    f'<div style="font-family:var(--uv-mono);font-size:12.5px;">1 {ccy} = {cash.money(rate, base, 4)}'
                    f'</div><div style="font-size:10.5px;color:var(--faint);margin-top:2px;">{_html.escape(_src)}</div>',
                    unsafe_allow_html=True)
    else:
        # Changing the date (or, when adding, the currency) drops back to the
        # automatic ECB rate; an Edit that leaves the date alone keeps the
        # rate stored with the entry.
        _basis = f"{ccy}|{d.isoformat()}"
        if _CASH_BASIS not in st.session_state:
            st.session_state[_CASH_BASIS] = _basis
            _orig = is_edit and _basis == f"{_ccy0}|{d0.isoformat()}" and entry.get("fx_rate")
            st.session_state[_CASH_MODE] = (("manual" if entry.get("fx_source") == "manual" else "keep")
                                            if _orig else "ecb")
        elif st.session_state[_CASH_BASIS] != _basis:
            st.session_state[_CASH_BASIS] = _basis
            st.session_state[_CASH_MODE] = "ecb"
            st.session_state.pop("dlg_cash_rate", None)
        if ccy != base:
            rate, manual, manual_rate = _cash_rate_panel(ccy, base, d, entry)

    note = st.text_input(_("Note") if readonly else _("Note (opt.)"),
                         value=((cash.note_text(entry) if readonly else str(entry.get("note") or ""))
                                if is_edit else ""), key="dlg_cash_note",
                         disabled=readonly,
                         placeholder=_("Reconciled to broker statement") if is_adj else _("e.g. Transfer from savings"))

    # ── Calculated ───────────────────────────────────────────────────────────
    _this = _(_THIS_TYPE.get(_type, _type))
    if ccy != base:
        _this_in = _("{label} in {currency}", label=_this, currency=base)
    else:
        _this_in = _this
    if readonly:
        _row = next((r for r in cash.replay(entries) if r.get("id") == entry["id"]), None)
        _eff = float(_row["base"]) if _row else 0.0
        _bal = float(_row["bal"]) if _row else 0.0
        calc_preview(_("Calculated · {currency} base", currency=base),
                     [(_("Balance before"), cash.money(round(_bal - _eff, 2), base)),
                      (_this_in, cash.signed_money(_eff, base))],
                     _("Balance after"), cash.money(_bal, base))
        _section, _label = linked_entry_target(entry)
        _ref = entry.get("ref_label") or entry.get("ref_id") or "—"
        cash_link_line(_("Posted automatically from {ref}.", ref=_ref))
        _go = dialog_actions("dlg_cash", save_label=_label)[0]
        if _go:
            st.session_state["port_section"] = _section
            st.rerun()
        return

    cur = cash.balance(entries)
    sign = -1 if _type in ("Withdrawal", "Fee") else 1
    blocked = False
    if is_adj:
        calc = None if target is None else round(target - cash.balance_before(others, d), 2)
        new = None if target is None else {**(entry or {}), "id": (entry or {}).get("id", "probe"),
                                            "seq": (entry or {}).get("seq") or 10 ** 12, "date": d.isoformat(),
                                            "type": "Adjustment", "target_balance": round(target, 2)}
    else:
        calc = round(sign * amount * rate, 2) if amount and rate and rate > 0 else None
        new = None if calc is None else {**(entry or {}), "id": (entry or {}).get("id", "probe"),
                                          "seq": (entry or {}).get("seq") or 10 ** 12, "date": d.isoformat(),
                                          "type": _type, "amount": round(sign * amount, 2),
                                          "currency": ccy, "fx_rate": rate, "amount_base": calc}
    if new is None:
        after = None
    elif is_edit:
        _pv = cash.preview_change(entry["id"], new, entries)
        after, blocked = _pv["after"], _pv["blocked"]
    else:
        after = round(cur + calc, 2)
        if sign < 0 and not is_adj:
            blocked = cash.min_balance_after(entries, new) < -0.004
    if is_edit:
        _rows = [(_("Current balance"), cash.money(cur, base)),
                 (_("Change"), "—" if after is None else cash.signed_money(round(after - cur, 2), base))]
    else:
        _calc_label = _("Correction") if is_adj else _this_in
        _rows = [(_("Current balance"), cash.money(cur, base)),
                 (_calc_label, "—" if calc is None else cash.signed_money(calc, base))]
    if after is None:
        _after_txt, _after_color = "—", "var(--text)"
    elif blocked:
        _after_txt, _after_color = _("{amount} · blocked", amount=cash.money(after, base)), "var(--down-txt)"
    else:
        _after_txt, _after_color = cash.money(after, base), "var(--text)"
    calc_preview(_("Calculated · {currency} base", currency=base), _rows, _("Balance after"), _after_txt, _after_color)

    if is_edit:
        _del = cash.preview_change(entry["id"], None, entries)
        _effect = next((r["base"] for r in cash.replay(entries) if r["id"] == entry["id"]), 0.0)
        _confirm = _("Delete this {type} of {amount}? Balance after: {balance}.",
                     type=tr(_type).lower(),
                     amount=cash.signed_money(float(_effect), base), balance=cash.money(_del['after'], base))
        if entry.get("opening"):
            _confirm += " " + _("It is the opening balance; the ledger will start from the next entry.")
        if _del["blocked"]:
            _confirm += " " + _("This would take the balance below zero, so it will be refused.")
        _do_save, _do_delete = dialog_actions("dlg_cash", delete=True, confirm_text=_confirm)
    else:
        _do_save, _do_delete = dialog_actions("dlg_cash")
    if not (_do_save or _do_delete):
        return
    try:
        if _do_delete:
            cash.delete_entry(entry["id"])
        elif is_adj:
            if target is None:
                raise cash.CashError(_("Enter the corrected balance."))
            if is_edit:
                cash.update_manual(entry["id"], d, note=note or "", target_balance=target)
            else:
                cash.post_adjustment(d, target, note or "")
        else:
            if ccy != base and manual and not (manual_rate and manual_rate > 0):
                raise cash.CashError(_("Enter the FX rate to convert {currency} to {base}.", currency=ccy, base=base))
            if is_edit:
                cash.update_manual(entry["id"], d, amount or 0.0, ccy, note=note or "",
                                   manual_rate=manual_rate if manual else None,
                                   refresh_rate=st.session_state.get(_CASH_MODE) == "ecb")
            else:
                cash.post_manual(_type, d, amount or 0.0, ccy, note=note or "",
                                 manual_rate=manual_rate if manual else None)
    except cash.CashError as exc:
        st.error(str(exc))
        return
    except fx.FxUnavailable:
        st.session_state[_CASH_MODE] = "manual"
        st.error(_(CASH_OUTAGE_TEXT))
        return
    st.rerun()


@_dialog(N_("Add cash transaction"))
def cash_transaction_dialog(preset_type: str = "Deposit") -> None:
    enter_dialog()
    dialog_frame(_("Trades and dividends post automatically."))
    if viewer_blocked():
        return
    _cash_form(None, preset_type)


def linked_entry_target(entry: dict) -> tuple[str, str]:
    """(Portfolio section, button label) where an automatic entry's source
    record is edited."""
    if entry.get("ref_kind") == "dividend":
        return "dividends", _("Open dividend log")
    from portfolio import get_position
    if entry.get("type") == "Sell" or not get_position(str(entry.get("ref_id") or "")):
        return "closed", _("Open closed positions")
    return "open", _("Open positions")


@_dialog(N_("Edit cash transaction"))
def edit_cash_dialog(entry_id: str) -> None:
    """Every ledger row's pencil opens this. Manual entries are edited here;
    automatic ones (trades, top-ups, dividends) show the same form read-only
    with a button to the record they mirror, where they are changed."""
    import cash

    enter_dialog()
    entry = cash.get_entry(entry_id)
    _auto = entry is not None and not cash.is_editable(entry)
    dialog_frame(_("Posted automatically; edit it at its source.") if _auto
                 else _("Update this entry; its type stays the same."))
    if entry is None:
        st.error(_("This entry no longer exists."))
        return
    if _auto:
        _cash_form(entry, readonly=True)
        return
    if viewer_blocked():
        return
    _cash_form(entry)
