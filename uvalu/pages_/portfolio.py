"""Portfolio page — open positions, closed positions, dividends, with CRUD.

Full replacement of the previous st.dataframe/column-groups/chart-tabs
implementation, matching Uvalu.dc.html's Portfolio screen (raw-HTML card
rows via uvalu/components.py's portfolio_open_row/portfolio_closed_row/
portfolio_dividend_row, same pattern already used to reset analysis.py and
screener.py on this branch). Per-row edit (pencil icon) replaces the old
bulk st.data_editor dialogs; the column-groups "View" dialog and the
Performance/Value history/Breakdown chart tabs are dropped entirely — this
page is now a close 1:1 visual match of the mockup, nothing extra.
"""
import time

import pandas as pd
import streamlit as st

from portfolio import (load_portfolio, load_sold, load_div_hist, save_portfolio,
                       save_sold, record_value_snapshot, ensure_value_history_fresh,
                       dividends_in_eur, dividend_income_summary,
                       import_dividends_from_market_data, exchange_key_for_ticker,
                       ensure_trade_ids, ensure_div_ids, save_div_hist,
                       strip_derived_columns, DERIVED_POSITION_COLS)
from screener import get_fetch_progress, PORTFOLIO_FETCH
from uvalu.data import _fetch_prices_cached, _load_portfolio_scored, apply_live_mos
from uvalu.dialogs import (add_position_dialog, add_dividend_dialog, add_closed_trade_dialog,
                           edit_position_dialog, edit_closed_trade_dialog, edit_dividend_dialog)
from uvalu.components import (fit_widths, header_cell_html, kpi_card as _kpi_card, portfolio_open_row,
                              portfolio_closed_row, portfolio_dividend_row, dividend_log_row,
                              dividend_log_header_html, DIVIDEND_LOG_COL_SPLIT,
                              refresh_top_bar_html, skeleton_kpi_card_html, skeleton_rows)
from uvalu.formatting import safe_pct as _safe_pct
from uvalu.i18n import N_, _, fmt_money, fmt_pct, fmt_total, h_, ngettext, sort_df, tr
from uvalu.locale_ui import export_menu
from uvalu.runtime import current_user
from uvalu.drawer import open_drawer
from uvalu.ui import price_autorefresh, consumed_tick, poll_while_fetching
from uvalu.pages_ import cash as _cash_ui

# Full-page sections reachable by deep link (?section=cash), e.g. the Risk
# page's "View cash activity" and the Dashboard Cash tile.
_SECTIONS = ("overview", "open", "closed", "dividends", "cash")
_VIEWER_HELP = N_("Viewer role is read-only")


# Same suffix->exchange mapping already used in uvalu/pages_/risk.py — the
# row components render a compact mono exchange chip next to the ticker.
_TICKER_SUFFIX_EXCHANGE = {
    ".BR": N_("Brussels"), ".AS": N_("Amsterdam"), ".PA": N_("Paris"),
    ".MI": N_("Milan"), ".DE": N_("Frankfurt"), ".SW": N_("Swiss"),
}


def _exchange_label(ticker: str) -> str:
    for suffix, label in _TICKER_SUFFIX_EXCHANGE.items():
        if str(ticker).endswith(suffix):
            return tr(label)
    return "—"


# Table columns: (label, design width in px, right-aligned). The design widths
# fit the English labels; _layout() widens a column when its translated label
# is longer (e.g. "GEM. AANKOOPPRIJS"), and the header, the rows and the
# loading skeleton all use that one list, so they stay aligned.
_OPEN_COLUMNS = [
    (N_("Position"), 200, False), (N_("Shares"), 68, True), (N_("Avg cost"), 88, True),
    (N_("Price"), 88, True), (N_("Cost basis"), 108, True), (N_("Market value"), 118, True),
    (N_("Unrealised P&L"), 132, True), (N_("Income 12m"), 96, True), (N_("Yield"), 60, True),
    (N_("YoC net"), 70, True), (N_("Weight"), 96, False),
]
_CLOSED_COLUMNS = [
    (N_("Position"), 300, False), (N_("Shares"), 56, True), (N_("Buy"), 74, True),
    (N_("Sell"), 74, True), (N_("Realised P&L"), 110, True),
]


def _layout(columns: list, *, name_w: int | None = None, edit: bool = False) -> tuple[list, list, list]:
    """(widths, translated labels, rights) for a table; ``edit`` adds the
    trailing 32px pencil column."""
    labels = [_(label) for label, _w, _r in columns]
    widths = [w for _l, w, _r in columns]
    rights = [r for _l, _w, r in columns]
    if name_w:
        widths[0] = name_w
    if edit:
        labels, widths, rights = labels + [""], widths + [32], rights + [False]
    return fit_widths(widths, labels), labels, rights


def _col_header(widths: list, labels: list[str], rights: list[bool]) -> None:
    """One row of 10px uppercase faint column labels, matching Uvalu.dc.html's
    column-header spec — right-aligned for numeric columns, left for text.
    Labels are already translated; single-line with an ellipsis if the
    window is narrower than the fitted widths."""
    for _c, _lbl, _right in zip(st.columns(widths, vertical_alignment="center"), labels, rights):
        with _c:
            st.markdown(header_cell_html(_lbl, right=_right), unsafe_allow_html=True)


def render() -> None:
    # ── Load saved portfolio ───────────────────────────────────────────────────
    pf = load_portfolio()
    if pf is None:
        pf = pd.DataFrame()

    # ── Migrate: ensure new fields exist ──────────────────────────────────────
    if not pf.empty:
        _dirty = False
        if "account" not in pf.columns:
            pf["account"] = ""
            _dirty = True
        if "purchase_price" not in pf.columns:
            pf["purchase_price"] = (
                pd.to_numeric(pf["purchase_value"], errors="coerce") /
                pd.to_numeric(pf["shares"],         errors="coerce")
            ).round(4)
            _dirty = True
        # Derived live-price columns that the old Edit position dialog saved
        # into the file along with the edit.
        if any(c in pf.columns for c in DERIVED_POSITION_COLS):
            pf = strip_derived_columns(pf)
            _dirty = True
        # Stable ids, so the Edit dialogs address a record by id, not by row.
        pf, _ids_added = ensure_trade_ids(pf)
        if _dirty or _ids_added:
            save_portfolio(pf)

        # ── Drop rows with no valid ticker ────────────────────────────────────
        pf = pf[pf["ticker"].notna() & (pf["ticker"].astype(str).str.strip() != "")].reset_index(drop=True)
    _sold_ids, _sold_changed = ensure_trade_ids(load_sold())
    if _sold_changed:
        save_sold(_sold_ids)

    # ── Screener data + Add-position dialog (always needed, even for empty portfolio) ──
    # Scored rows for held + sold tickers via the portfolio's own fetch lane
    # (uvalu/data.py's PORTFOLIO_FETCH) — no full-universe scoring on the
    # render path (WP-3), and independent of which exchanges are enabled or of
    # the screener's refresh/bust cycle. Used to look up the full screener row
    # (fair value, models, etc.) for whichever position ticker the user clicks
    # — the drawer needs more than the portfolio row alone provides.
    _all_scr_df = _load_portfolio_scored(pf, load_sold())
    _pf_dlg_pending: list = []  # at most one dialog call per render
    # True only on a genuinely cold PORTFOLIO_FETCH lane (a fresh session /
    # newly-added position) — used to skeleton the Overview KPI strip and
    # preview lists below instead of a blank page while the lane warms up.
    _pf_fetch_running = _all_scr_df.empty and bool(get_fetch_progress(PORTFOLIO_FETCH).get("running"))

    _user = current_user()
    _is_viewer = _user.is_viewer

    # Arriving from another page lands on the Overview, so the user starts
    # from the whole picture instead of whichever sub-page they left from —
    # unless something sent them to a specific one: another page that sets
    # port_section together with "_pf_section_handoff" (Risk's "View cash
    # activity", the drawer's Edit), or a ?section= deep link.
    _handoff = st.session_state.pop("_pf_section_handoff", False)
    if (st.session_state.get("_uv_render_page") != "portfolio" and not _handoff
            and "_pf_edit_ticker" not in st.session_state):
        st.session_state["port_section"] = "overview"
    _qs_section = st.query_params.get("section")
    if _qs_section in _SECTIONS:
        st.session_state["port_section"] = _qs_section
        del st.query_params["section"]
    _section = st.session_state.get("port_section", "overview")

    def _goto(section: str) -> None:
        st.session_state["port_section"] = section
        st.rerun()

    # Cash Management v1: post any dividends that came due (or whose FX rate
    # was unavailable earlier) into the cash ledger — once per session.
    _cash_ui.reconcile_once(_user.email, _is_viewer)
    price_autorefresh("portfolio_refresh")
    # A timed price refresh (see uvalu/ui.py) is not a real (re)visit — it
    # shouldn't drag the value-history backfill + daily-snapshot write along
    # with it every minute. Those only need to run when the user actually
    # lands on the page.
    _timer_refresh = consumed_tick("portfolio_refresh")
    if _timer_refresh:
        # Slim top-of-page sweep instead of a silent repaint — same
        # non-disruptive "Data refresh" cue as the Dashboard (uvalu/
        # components.py's refresh_top_bar_html), only for this one script run.
        # uv_hidden_util: it's position:fixed (zero layout height), but its
        # own element-container would still eat a full row-gap and push the
        # heading down (same trick as uvalu/shell.py's topbar CSS injection).
        with st.container(key="uv_hidden_util_refresh_sweep"):
            st.markdown(refresh_top_bar_html(), unsafe_allow_html=True)

    if pf.empty:
        # ── Empty portfolio — Add button + the cash strip (cash can be
        # deposited before the first buy) ──────────────────────────────────────
        if _section == "cash":
            _cash_ui.render_page(invested_value=0.0, is_viewer=_is_viewer, on_back=lambda: _goto("overview"))
            st.stop()
        if st.button(_("Add position"), key="btn_add_pos_empty", icon=":material/add:", disabled=_is_viewer,
                    help=_(_VIEWER_HELP) if _is_viewer else None):
            add_position_dialog()
        st.info(_("Your portfolio is empty. Click Add position to record your first position."))
        _cash_ui.render_strip(invested_value=0.0, is_viewer=_is_viewer, on_open=lambda: _goto("cash"))
        st.stop()

    # ── Fetch live prices ─────────────────────────────────────────────────────
    live_data = _fetch_prices_cached(tuple(pf["ticker"].tolist()))
    # Refresh Price / MoS on the scored lookup frame so a drawer opened from a
    # position shows a margin of safety consistent with its live price (WP-DQ1).
    _all_scr_df = apply_live_mos(_all_scr_df, live_data)
    pf["live_price"]     = pf["ticker"].map(lambda t: live_data[t].get("price"))
    pf["current_value"]  = pf["live_price"] * pf["shares"]
    pf["price_gain"]     = pf["current_value"] - pf["purchase_value"]
    _cost = pf["purchase_value"].replace(0, float("nan"))
    pf["price_gain_pct"] = (pf["price_gain"] / _cost * 100).round(2)

    # ── Dividend income (WP-DIV4): trailing-12m net/gross/regular-gross per
    # ticker, net of foreign withholding AND the Belgian 30% layer — feeds
    # the Income 12m / Yield / YoC net columns below and every dividends-
    # page figure. Computed once here (not per-section) since both the
    # Overview preview and the full Open-positions page need it.
    _div_hist_all = load_div_hist()
    _div_summary = dividend_income_summary(_div_hist_all, months=12)

    def _div_row_for(ticker: str) -> dict:
        if ticker in _div_summary.index:
            return _div_summary.loc[ticker].to_dict()
        return {"gross_eur": 0.0, "net_eur": 0.0, "regular_gross_eur": 0.0}

    # ── Summary cards (Overview only) ──────────────────────────────────────────
    total_invested  = pf["purchase_value"].sum()
    total_current   = pf["current_value"].sum()
    total_dividends = pf["dividends"].fillna(0).sum()
    price_gain      = total_current - total_invested
    price_gain_pct  = _safe_pct(price_gain, total_invested)

    # Auto-backfill missing trading days in the background — non-blocking, so
    # a stale/empty value_history.json never delays this page's own paint.
    # This page doesn't display value-history data itself (see module
    # docstring), so there's nothing to show progress on here; Dashboard's
    # value chart is the one that polls ensure_value_history_fresh() for its
    # own skeleton/fill-in.
    if not _timer_refresh and total_current > 0:
        ensure_value_history_fresh(pf, load_sold(), _user.email)

    # record_value_snapshot upserts one row per calendar day, so skipping it on
    # timed refreshes and throttling it to ~every 10 min on genuine renders
    # loses nothing but the repeated decrypt+encrypt+write of value_history.json.
    if total_current > 0 and not _timer_refresh:
        _now = time.time()
        if _now - st.session_state.get("_pf_snapshot_ts", 0.0) >= 600:
            record_value_snapshot(total_invested, total_current)
            st.session_state["_pf_snapshot_ts"] = _now

    # ── Overview — heading + 5-card KPI strip + open/closed/dividends previews ──
    if _section == "overview":
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            with st.container(width="content"):
                st.markdown(f'<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">{h_("Portfolio")}</div>',
                           unsafe_allow_html=True)
                st.caption(_("Cost basis, market value and realised results across open and closed positions."))
            with st.container(horizontal=True, gap="small", width="content"):
                _ov_frame = pd.DataFrame({
                    "Company": pf["name"], "Ticker": pf["ticker"], "Shares": pf["shares"],
                    "Buy price": pf["purchase_price"], "Live price": pf["live_price"],
                    "Invested": pf["purchase_value"], "Current value": pf["current_value"],
                    "Price gain": pf["price_gain"],
                })
                export_menu(_("Export"), frame=_ov_frame, file_name="uvalu_portfolio.csv", key="ov_export")
                if st.button(_("Add position"), key="ov_buy", type="primary", icon=":material/add:",
                             disabled=_is_viewer, help=_(_VIEWER_HELP) if _is_viewer else None):
                    add_position_dialog()

        # Realised P&L and a real trailing-12m dividend figure — matches
        # Uvalu.dc.html's 5-card set (Invested/Market value/Unrealised P&L/
        # Realised P&L/Dividends (12m)) exactly.
        _ov_sold_all = load_sold()
        if _ov_sold_all is not None and not _ov_sold_all.empty:
            _realised_pl = (pd.to_numeric(_ov_sold_all["sale_value"], errors="coerce") -
                            pd.to_numeric(_ov_sold_all["purchase_value"], errors="coerce")).sum()
            _realised_count = len(_ov_sold_all)
        else:
            _realised_pl, _realised_count = 0.0, 0

        if not _div_summary.empty:
            # Net of foreign withholding and the Belgian 30% roerende
            # voorheffing (WP-DIV3) — the "real" income figure, not gross.
            _div_12m = _div_summary["net_eur"].sum()
        else:
            # No dividend-history file uploaded — fall back to dividends already
            # recorded against current holdings rather than showing zero.
            _div_12m = total_dividends

        if _pf_fetch_running:
            # A genuinely cold PORTFOLIO_FETCH lane (fresh session / newly-
            # added position) — arm one poll for the whole Overview section
            # (KPI strip + the three previews below) instead of a separate
            # auto_rerun per section.
            poll_while_fetching("portfolio_overview_fetch", lane="portfolio")

        with st.container(key="pf_kpi_row"):
            _o1, _o2, _o3, _o4, _o5 = st.columns(5)
            if _pf_fetch_running:
                for _oc in (_o1, _o2, _o3, _o4, _o5):
                    with _oc:
                        st.markdown(skeleton_kpi_card_html(), unsafe_allow_html=True)
            else:
                with _o1:
                    _kpi_card(h_("Invested"), fmt_total(total_invested),
                              sub=ngettext("{count} open position", "{count} open positions", len(pf)), icon="wallet")
                with _o2:
                    _kpi_card(h_("Market value"), fmt_total(total_current), fmt_pct(price_gain_pct, signed=True),
                              price_gain >= 0, h_("current holdings"), icon="wallet")
                with _o3:
                    _kpi_card(h_("Unrealised P&L"), fmt_total(price_gain), fmt_pct(price_gain_pct, signed=True),
                              price_gain >= 0, h_("open positions"), icon="trend")
                with _o4:
                    _kpi_card(h_("Realised P&L"), fmt_total(_realised_pl),
                              sub=ngettext("{count} closed trade", "{count} closed trades", _realised_count), icon="trend")
                with _o5:
                    _kpi_card(h_("Dividends (12m)"), fmt_total(_div_12m), sub=h_("income received"), icon="coin")

        # ── Cash strip (Cash Management v1) ───────────────────────────────────
        _cash_ui.render_strip(invested_value=total_current, is_viewer=_is_viewer,
                              on_open=lambda: _goto("cash"))

        # ── Open positions preview (top 5 by market value) ────────────────────
        with st.container(key="pf_card_open_ov", border=True):
            with st.container(key="pf_panel_title_open_ov", horizontal=True, vertical_alignment="center",
                              horizontal_alignment="distribute"):
                st.markdown(_("Open positions"))
                if st.button("", key="ov_open_expand", icon=":material/open_in_full:", help=_("Open full page")):
                    _goto("open")
            _ov_open_w, _ov_open_l, _ov_open_r = _layout(_OPEN_COLUMNS)
            with st.container(key="pf_col_header_open_ov"):
                _col_header(_ov_open_w, _ov_open_l, _ov_open_r)
            if _pf_fetch_running:
                skeleton_rows(_ov_open_w, n=min(len(pf), 5),
                             key_prefix="uv_skel_row_pf_open")
            else:
                _ov_view_target = None
                _ov_open = pf.sort_values("current_value", ascending=False).head(5)
                for _idx, _prow in _ov_open.iterrows():
                    _dr = _div_row_for(_prow["ticker"])
                    _cost_val = _prow["purchase_value"] if pd.notna(_prow["purchase_value"]) and _prow["purchase_value"] else None
                    _res = portfolio_open_row(
                        key=f"pf_open_row_ov_{_idx}_{_prow['ticker']}", ticker=_prow["ticker"],
                        exchange=_exchange_label(_prow["ticker"]), name=_prow["name"],
                        shares=_prow["shares"], avg_cost=_prow["purchase_price"], price=_prow["live_price"],
                        cost_basis=_prow["purchase_value"], value=_prow["current_value"],
                        gain=_prow["price_gain"], gain_pct=_prow["price_gain_pct"],
                        weight_pct=(_prow["current_value"] / total_current * 100) if total_current else 0,
                        income_12m=_dr["net_eur"], income_12m_gross=_dr["gross_eur"],
                        ttm_yield_pct=(_dr["regular_gross_eur"] / _prow["current_value"] * 100)
                        if _prow["current_value"] else None,
                        yoc_pct=(_dr["net_eur"] / _cost_val * 100) if _cost_val else None,
                        show_edit=False, widths=_ov_open_w,
                    )
                    if _res["view"]:
                        _ov_view_target = _prow["ticker"]
                if _ov_view_target is not None:
                    _r = _all_scr_df[_all_scr_df["Ticker"] == _ov_view_target]
                    if not _r.empty:
                        _pf_dlg_pending.append((_r.iloc[0],))

        # ── Closed positions + Dividends previews (two columns) ───────────────
        # 1.55:1 ratio matches Uvalu.dc.html's own `grid-template-columns:
        # 1.55fr 1fr` for this row — Closed positions needs the extra room
        # for its 5-column table, Dividends' flat list doesn't.
        _oc1, _oc2 = st.columns([1.55, 1], gap="large")
        with _oc1:
            with st.container(key="pf_card_closed_ov", border=True):
                with st.container(key="pf_panel_title_closed_ov", horizontal=True, vertical_alignment="center",
                                  horizontal_alignment="distribute"):
                    st.markdown(f'{h_("Closed positions")} <span style="color:var(--faint);font-weight:400;">{h_("· realised")}</span>',
                               unsafe_allow_html=True)
                    if st.button("", key="ov_closed_expand", icon=":material/open_in_full:", help=_("Open full page")):
                        _goto("closed")
                _ov_closed_w, _ov_closed_l, _ov_closed_r = _layout(_CLOSED_COLUMNS)
                if _pf_fetch_running:
                    with st.container(key="pf_col_header_closed_ov"):
                        _col_header(_ov_closed_w, _ov_closed_l, _ov_closed_r)
                    skeleton_rows(_ov_closed_w, n=3, key_prefix="uv_skel_row_pf_closed")
                else:
                    _ov_sold = load_sold()
                    if _ov_sold is not None and not _ov_sold.empty:
                        _ov_sold = _ov_sold.copy()
                        _pv = pd.to_numeric(_ov_sold["purchase_value"], errors="coerce")
                        _sv = pd.to_numeric(_ov_sold["sale_value"], errors="coerce")
                        _ov_sold["_gain"] = _sv - _pv
                        _ov_sold["_gain_pct"] = (_ov_sold["_gain"] / _pv.replace(0, float("nan")) * 100).round(2)
                        _ov_sold["_buy"]  = _pv / pd.to_numeric(_ov_sold["shares"], errors="coerce")
                        _ov_sold["_sell"] = _sv / pd.to_numeric(_ov_sold["shares"], errors="coerce")
                        _ov_sold["_closed_dt"] = pd.to_datetime(
                            _ov_sold["date_out"], format="mixed", dayfirst=False, errors="coerce")
                        _ov_sold = _ov_sold.sort_values("date_out", ascending=False).head(5)
                        with st.container(key="pf_col_header_closed_ov"):
                            _col_header(_ov_closed_w, _ov_closed_l, _ov_closed_r)
                        for _sidx, _srow in _ov_sold.iterrows():
                            portfolio_closed_row(
                                key=f"pf_closed_row_ov_{_sidx}_{_srow['ticker']}", ticker=_srow["ticker"],
                                exchange=_exchange_label(_srow["ticker"]), name=_srow["name"],
                                closed_date=_srow["_closed_dt"], shares=_srow["shares"],
                                buy=_srow["_buy"], sell=_srow["_sell"], pl=_srow["_gain"], pl_pct=_srow["_gain_pct"],
                                show_edit=False, widths=_ov_closed_w,
                            )
                    else:
                        st.caption(_("No closed positions yet."))
        with _oc2:
            with st.container(key="pf_card_div_ov", border=True):
                with st.container(key="pf_panel_title_div_ov", horizontal=True, vertical_alignment="center",
                                  horizontal_alignment="distribute"):
                    st.markdown(_("Dividends received"))
                    if st.button("", key="ov_div_expand", icon=":material/open_in_full:", help=_("Open full page")):
                        _goto("dividends")
                if _pf_fetch_running:
                    with st.container(key="pf_col_header_div_ov"):
                        _col_header([6, 1.3], [_("Position"), _("Dividend")], [False, True])
                    skeleton_rows([6, 1.3], n=3, key_prefix="uv_skel_row_pf_div")
                else:
                    _ov_div = load_div_hist()
                    if _ov_div is not None and not _ov_div.empty:
                        _ov_div = dividends_in_eur(_ov_div)
                        _ov_div["date"] = pd.to_datetime(_ov_div["date"], errors="coerce")
                        # "Received" — a dividend dated ahead of its payment
                        # date hasn't happened yet, so it doesn't belong in
                        # this list (same fix as the Dashboard KPI/Portfolio
                        # totals, applied here too since this list carries
                        # the same "received" framing in its own title).
                        _ov_div = _ov_div[_ov_div["date"] <= pd.Timestamp.now()]
                    if _ov_div is not None and not _ov_div.empty:
                        _ov_div = _ov_div.sort_values("date", ascending=False).head(5)
                        with st.container(key="pf_col_header_div_ov"):
                            _col_header([6, 1.3], [_("Position"), _("Net dividend")], [False, True])
                        for _didx, _drow in _ov_div.iterrows():
                            portfolio_dividend_row(
                                key=f"pf_div_row_ov_{_didx}", name=_drow.get("name", "—"),
                                ticker=_drow.get("ticker", ""), date=_drow["date"],
                                amount=_drow.get("net_after_be_amount_eur"), show_edit=False,
                            )
                    else:
                        st.caption(_("No dividends received yet."))

    # ── Full page: Open positions ──────────────────────────────────────────────
    if _section == "open":
        if st.button(_("← Back to Positions"), key="back_open", type="tertiary"):
            _goto("overview")
        with st.container(key="pf_page_title_open", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            with st.container(width="content"):
                st.markdown(f'<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">{h_("Open positions")}</div>',
                           unsafe_allow_html=True)
                st.caption(_("Every holding at cost and at today's price. Click a row for its detail; the pencil edits or sells it."))
            if st.button(_("Add position"), key="btn_add_pos", type="primary", icon=":material/add:",
                         disabled=_is_viewer, help=_(_VIEWER_HELP) if _is_viewer else None):
                add_position_dialog()

        def _live_price_for(trade_id) -> float | None:
            _m = pf[pf["trade_id"].astype(str) == str(trade_id)]
            _p = _m.iloc[0]["live_price"] if not _m.empty else None
            return float(_p) if _p is not None and pd.notna(_p) else None

        # The drawer's "Edit" button (uvalu/drawer.py's _go_portfolio_edit)
        # navigates here first and stashes the ticker; open that holding's
        # (first lot's) Edit dialog.
        _pending_edit_ticker = st.session_state.pop("_pf_edit_ticker", None)
        if _pending_edit_ticker is not None:
            _edit_match = pf[pf["ticker"] == _pending_edit_ticker]
            if not _edit_match.empty:
                _tid = _edit_match.iloc[0]["trade_id"]
                edit_position_dialog(str(_tid), live_price=_live_price_for(_tid))

        with st.container(key="pf_card_open_full", border=True):
            _open_w, _open_l, _open_r = _layout(_OPEN_COLUMNS, name_w=240, edit=True)
            with st.container(key="pf_col_header_open_full"):
                _col_header(_open_w, _open_l, _open_r)
            _view_target = None
            _edit_target = None
            _open_sorted = sort_df(pf, "name")
            for _idx, _prow in _open_sorted.iterrows():
                _dr = _div_row_for(_prow["ticker"])
                _cost_val = _prow["purchase_value"] if pd.notna(_prow["purchase_value"]) and _prow["purchase_value"] else None
                _res = portfolio_open_row(
                    key=f"pf_open_row_{_idx}_{_prow['ticker']}", ticker=_prow["ticker"],
                    exchange=_exchange_label(_prow["ticker"]), name=_prow["name"],
                    shares=_prow["shares"], avg_cost=_prow["purchase_price"], price=_prow["live_price"],
                    cost_basis=_prow["purchase_value"], value=_prow["current_value"],
                    gain=_prow["price_gain"], gain_pct=_prow["price_gain_pct"],
                    weight_pct=(_prow["current_value"] / total_current * 100) if total_current else 0,
                    income_12m=_dr["net_eur"], income_12m_gross=_dr["gross_eur"],
                    ttm_yield_pct=(_dr["regular_gross_eur"] / _prow["current_value"] * 100)
                    if _prow["current_value"] else None,
                    yoc_pct=(_dr["net_eur"] / _cost_val * 100) if _cost_val else None,
                    show_edit=True, edit_disabled=_is_viewer, widths=_open_w,
                )
                if _res["view"]:
                    _view_target = _prow["ticker"]
                if _res["edit"]:
                    _edit_target = str(_prow["trade_id"])
            if _edit_target is not None:
                edit_position_dialog(_edit_target, live_price=_live_price_for(_edit_target))
            if _view_target is not None:
                _r = _all_scr_df[_all_scr_df["Ticker"] == _view_target]
                if not _r.empty:
                    _pf_dlg_pending.append((_r.iloc[0],))

    # ── Full page: Closed positions ───────────────────────────────────────────
    if _section == "closed":
        if st.button(_("← Back to Positions"), key="back_closed", type="tertiary"):
            _goto("overview")
        with st.container(key="pf_page_title_closed", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            with st.container(width="content"):
                st.markdown(f'<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">{h_("Closed positions")} '
                           f'<span style="color:var(--faint);font-weight:400;">{h_("· realised")}</span></div>',
                           unsafe_allow_html=True)
                st.caption(_("Realised results of sold positions. To sell a holding, use Sell shares in its Edit dialog on Open positions."))
            # Records a trade opened and closed outside this app (no cash
            # posting) — it used to be labelled "Close", which read like
            # selling one of the holdings; the dialog is "Add trade".
            if st.button(_("Add trade"), key="btn_add_closed", type="primary", icon=":material/add:",
                         disabled=_is_viewer, help=_(_VIEWER_HELP) if _is_viewer else None):
                add_closed_trade_dialog()
        sold = load_sold()
        if sold is None or sold.empty:
            st.info(_("No closed positions yet. Sell a holding, or record an earlier trade with Add trade."))
        else:
            sold = sold.reset_index(drop=True)
            _pv = pd.to_numeric(sold["purchase_value"], errors="coerce")
            _sv = pd.to_numeric(sold["sale_value"], errors="coerce")
            sold["_gain"] = _sv - _pv
            sold["_gain_pct"] = (sold["_gain"] / _pv.replace(0, float("nan")) * 100).round(2)
            sold["_buy"]  = _pv / pd.to_numeric(sold["shares"], errors="coerce")
            sold["_sell"] = _sv / pd.to_numeric(sold["shares"], errors="coerce")
            sold["_closed_dt"] = pd.to_datetime(
                sold["date_out"], format="mixed", dayfirst=False, errors="coerce")
            sold_sorted = sold.assign(
                _sort_date=pd.to_datetime(sold["date_out"], format="mixed", dayfirst=False, errors="coerce")
            ).sort_values("_sort_date", ascending=False)

            with st.container(key="pf_card_closed_full", border=True):
                _closed_w, _closed_l, _closed_r = _layout(_CLOSED_COLUMNS, name_w=400, edit=True)
                with st.container(key="pf_col_header_closed_full"):
                    _col_header(_closed_w, _closed_l, _closed_r)
                _edit_target = None
                for _idx, _srow in sold_sorted.iterrows():
                    _res = portfolio_closed_row(
                        key=f"pf_closed_row_{_idx}_{_srow['ticker']}", ticker=_srow["ticker"],
                        exchange=_exchange_label(_srow["ticker"]), name=_srow["name"],
                        closed_date=_srow["_closed_dt"], shares=_srow["shares"],
                        buy=_srow["_buy"], sell=_srow["_sell"], pl=_srow["_gain"], pl_pct=_srow["_gain_pct"],
                        show_edit=True, edit_disabled=_is_viewer, widths=_closed_w,
                    )
                    if _res["edit"]:
                        _edit_target = str(_srow["trade_id"])
                if _edit_target is not None:
                    edit_closed_trade_dialog(_edit_target)

    # ── Full page: Dividends ───────────────────────────────────────────────────
    if _section == "dividends":
        if st.button(_("← Back to Positions"), key="back_div", type="tertiary"):
            _goto("overview")
        # Auto-import from market data — once per session per user, never for
        # the read-only Viewer role (it writes the ledger). The import itself
        # only adds events on dates the user held shares, skips events already
        # logged by hand and never re-adds a deleted one
        # (portfolio.import_dividends_from_market_data).
        _auto_key = f"_div_auto_import_done_{_user.email}"
        if not _is_viewer and not st.session_state.get(_auto_key) and not pf.empty:
            st.session_state[_auto_key] = True
            with st.spinner(_("Checking market data for new dividends…")):
                _n_imported = import_dividends_from_market_data(pf, _user.email)
            if _n_imported:
                st.toast(ngettext("Imported {count} dividend event from market data.",
                                  "Imported {count} dividend events from market data.", _n_imported),
                         icon=":material/sync:")

        div_hist, _div_ids_added = ensure_div_ids(load_div_hist())
        if _div_ids_added:
            save_div_hist(div_hist)
        _has_divs = div_hist is not None and not div_hist.empty
        _div_frame = pd.DataFrame()
        if _has_divs:
            div_hist = div_hist.copy().reset_index(drop=True)
            div_hist["amount"] = pd.to_numeric(div_hist["amount"], errors="coerce")
            div_hist["date"]   = pd.to_datetime(div_hist["date"], errors="coerce")
            div_hist["shares"] = pd.to_numeric(div_hist.get("shares"), errors="coerce").fillna(0).astype(int)
            div_hist["reinvested"] = (
                div_hist["reinvested"].fillna(False).astype(bool)
                if "reinvested" in div_hist.columns else False
            )
            div_eur = dividends_in_eur(div_hist)
            div_eur["_ex_dt"] = pd.to_datetime(div_eur["ex_date"], errors="coerce")
            div_sorted = div_eur.sort_values("date", ascending=False)
            _div_frame = div_sorted[["name", "ticker", "_ex_dt", "date", "div_type", "currency",
                                     "amount", "tax_amount", "be_tax_amount", "net_after_be_amount",
                                     "source", "reinvested"]].rename(columns={
                "name": "Company", "ticker": "Ticker",
                "_ex_dt": "Ex-dividend date", "date": "Payment date",
                "div_type": "Type", "currency": "Currency", "amount": "Gross (native)",
                "tax_amount": "Foreign WH (native)", "be_tax_amount": "Belgian RV 30% (native)",
                "net_after_be_amount": "Net (native)", "source": "Source", "reinvested": "DRIP",
            })

        with st.container(key="pf_page_title_dividends", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            with st.container(width="content"):
                st.markdown(f'<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">{h_("Dividend log")}</div>',
                           unsafe_allow_html=True)
                st.caption(_("Per-holding dividend events. Auto-fetched from the market data source where dividend history is exposed; manual entry fills the gaps."))
            with st.container(horizontal=True, gap="small", width="content"):
                export_menu(_("Export"), frame=_div_frame, file_name="uvalu_dividend_log.csv",
                            key="div_export", disabled=not _has_divs)
                if st.button(_("Add dividend"), key="btn_add_div", type="primary", icon=":material/add:",
                             disabled=_is_viewer, help=_(_VIEWER_HELP) if _is_viewer else None):
                    add_dividend_dialog(pf)
        if not _has_divs:
            st.info(_("No dividend events yet. Add one with Add dividend — events for your held tickers are also fetched from market data where available."))
        else:
            # ── Summary tiles ──────────────────────────────────────────────────
            _tile_summary = dividend_income_summary(div_hist, months=12)
            _tile_gross = _tile_summary["gross_eur"].sum() if not _tile_summary.empty else 0.0
            _tile_fwh   = _tile_summary["foreign_tax_eur"].sum() if not _tile_summary.empty else 0.0
            _tile_be    = _tile_summary["be_tax_eur"].sum() if not _tile_summary.empty else 0.0
            _tile_net   = _tile_summary["net_eur"].sum() if not _tile_summary.empty else 0.0
            _tile_dates = pd.to_datetime(div_eur["date"], errors="coerce")
            _tile_now = pd.Timestamp.now()
            _tile_n_events = int(((_tile_dates <= _tile_now)
                                 & (_tile_dates > _tile_now - pd.DateOffset(months=12))).sum())
            _tile_n_holdings = _tile_summary.shape[0] if not _tile_summary.empty else 0
            with st.container(key="pf_div_tiles"):
                _t1, _t2, _t3, _t4, _t5 = st.columns(5)
                with _t1:
                    _kpi_card(h_("Gross income · 12m"), fmt_total(_tile_gross),
                             sub=(ngettext("{count} event", "{count} events", _tile_n_events) + " · "
                                  + ngettext("{count} holding", "{count} holdings", _tile_n_holdings)), icon="coin")
                with _t2:
                    _kpi_card(h_("Withholding · 12m"), "−" + fmt_total(_tile_fwh + _tile_be),
                             sub=h_("{foreign} foreign · {belgian} BE 30%",
                                    foreign=fmt_total(_tile_fwh), belgian=fmt_total(_tile_be)), icon="coin")
                with _t3:
                    _kpi_card(h_("Net income · 12m"), fmt_total(_tile_net), sub=h_("after all withholding"), icon="coin")
                with _t4:
                    _kpi_card(h_("Net yield"), fmt_pct(_safe_pct(_tile_net, total_current), 2),
                              sub=h_("on market value"), icon="trend")
                with _t5:
                    _kpi_card(h_("Net yield-on-cost"), fmt_pct(_safe_pct(_tile_net, total_invested), 2),
                             sub=h_("weighted, remaining cost basis"), icon="trend")

            with st.container(key="pf_card_div_full", border=True):
                with st.container(key="pf_col_header_div_full"):
                    _hc = st.columns(DIVIDEND_LOG_COL_SPLIT, vertical_alignment="center", gap="small")
                    with _hc[0]:
                        st.markdown(dividend_log_header_html(), unsafe_allow_html=True)
                _edit_target = None
                for _idx, _drow in div_sorted.iterrows():
                    _needs_confirm = (
                        _drow.get("source") == "auto"
                        and pd.notna(_drow.get("date")) and pd.notna(_drow.get("ex_date"))
                        and pd.Timestamp(_drow["date"]).normalize() == pd.Timestamp(_drow["ex_date"]).normalize()
                    )
                    _res = dividend_log_row(
                        key=f"pf_div_row_{_idx}", ticker=_drow.get("ticker", ""),
                        exchange=_exchange_label(_drow.get("ticker", "")), name=_drow.get("name", "—"),
                        ex_date=_drow.get("_ex_dt"), pay_date=_drow.get("date"),
                        div_type=_drow.get("div_type") or "Cash",
                        per_share=_drow.get("amount_per_share"), shares=_drow.get("shares"),
                        gross=_drow.get("amount_eur"), foreign_wh=_drow.get("tax_amount_eur"),
                        wh_note=(f"{exchange_key_for_ticker(_drow.get('ticker', '')) or '—'} "
                                f"{fmt_pct(_drow.get('tax_rate'))}"
                                if pd.notna(_drow.get("tax_rate")) and _drow.get("tax_rate") else _("no treaty WH")),
                        be_wh=_drow.get("be_tax_amount_eur"), net=_drow.get("net_after_be_amount_eur"),
                        source=_drow.get("source") or "manual", drip=bool(_drow.get("reinvested")),
                        needs_confirm=_needs_confirm, edit_disabled=_is_viewer,
                    )
                    if _res["edit"]:
                        _edit_target = str(_drow["div_id"])
                if _edit_target is not None:
                    edit_dividend_dialog(_edit_target)

            # ── Annual dividend income summary ───────────────────────────────
            _years_df = div_eur.assign(_year=pd.to_datetime(div_eur["date"], errors="coerce").dt.year)
            _year_summary = _years_df.dropna(subset=["_year"]).groupby("_year").agg(
                events=("ticker", "count"), gross=("amount_eur", "sum"),
                fwh=("tax_amount_eur", "sum"), be=("be_tax_amount_eur", "sum"),
                net=("net_after_be_amount_eur", "sum")).sort_index(ascending=False)
            _summary_frame = _year_summary.reset_index().rename(columns={
                "_year": "Year", "events": "Events", "gross": "Gross (EUR)",
                "fwh": "Foreign WH (EUR)", "be": "Belgian RV 30% (EUR)", "net": "Net (EUR)",
            })

            def _neg_eur(v: float) -> str:
                # "—" for no withholding, same as the log's Foreign WH / BE 30%
                # cells — a bare "−€0.00" reads like a real deduction.
                return "−" + fmt_money(v, "EUR") if pd.notna(v) and round(float(v), 2) != 0 else "—"

            # Design width: the summary takes the left of a 1.6 : 1 split; the
            # right-hand column is intentionally empty, reserved for future cards.
            _yc1, _yc2 = st.columns([1.6, 1], gap="large")
            with _yc1:
                with st.container(key="pf_card_tax_years", border=True):
                    with st.container(key="pf_tax_years_title", horizontal=True, vertical_alignment="center",
                                      horizontal_alignment="distribute"):
                        st.markdown(f'<div style="font-size:15px;font-weight:500;">{h_("Annual dividend income summary")}</div>'
                                   '<div style="font-size:12px;color:var(--muted);margin-top:3px;">'
                                   f'{h_("Net and gross reported separately, for your own tax filing.")}</div>',
                                   unsafe_allow_html=True, width="content")
                        export_menu(_("Export"), frame=_summary_frame, file_name="uvalu_dividend_tax_summary.csv",
                                    key="div_summary_export", disabled=_year_summary.empty)
                    if _year_summary.empty:
                        st.caption(_("No dividend history to summarise yet."))
                    else:
                        _this_year = pd.Timestamp.now().year
                        # All-proportional tracks, like the mockup. The old fixed 150px
                        # figure columns left the events column `minmax(0,1fr)` = ~0px on
                        # a narrower card, and its nowrap text spilled over Gross.
                        _grid = ("minmax(0,0.7fr) minmax(0,1.5fr) minmax(0,1fr) minmax(0,1fr) "
                                 "minmax(0,1fr) minmax(0,1fr)")
                        _num = "text-align:right;font-family:var(--uv-mono);"
                        _rows_html = (
                            f'<div style="display:grid;grid-template-columns:{_grid};gap:14px;align-items:center;'
                            f'padding:10px 20px;border-top:0.5px solid var(--line-2);'
                            f'border-bottom:0.5px solid var(--line-2);font-size:10px;letter-spacing:0.06em;'
                            f'text-transform:uppercase;color:var(--faint);">'
                            f'<div>{h_("Year")}</div><div></div><div style="text-align:right;">{h_("Gross")}</div>'
                            f'<div style="text-align:right;">{h_("Foreign WH")}</div><div style="text-align:right;">{h_("BE 30%")}</div>'
                            f'<div style="text-align:right;">{h_("Net")}</div></div>'
                        )
                        for _year, _yrow in _year_summary.iterrows():
                            _partial = h_("year to date") if int(_year) == _this_year else h_("full year")
                            _rows_html += (
                                f'<div style="display:grid;grid-template-columns:{_grid};gap:14px;align-items:center;'
                                f'padding:14px 20px;border-bottom:0.5px solid var(--line-2);">'
                                f'<div style="font-family:var(--uv-mono);font-size:13.5px;font-weight:500;">{int(_year)}</div>'
                                f'<div style="font-size:11.5px;color:var(--faint);white-space:nowrap;'
                                f'overflow:hidden;text-overflow:ellipsis;">'
                                f'{ngettext("{count} event", "{count} events", int(_yrow["events"]))} · {_partial}</div>'
                                f'<div style="{_num}font-size:12.5px;">{fmt_money(_yrow["gross"], "EUR")}</div>'
                                f'<div style="{_num}font-size:12.5px;color:var(--muted);">{_neg_eur(_yrow["fwh"])}</div>'
                                f'<div style="{_num}font-size:12.5px;color:var(--muted);">{_neg_eur(_yrow["be"])}</div>'
                                f'<div style="{_num}font-size:13px;font-weight:500;color:var(--uv-mint,#1DD6A4);">'
                                f'{fmt_money(_yrow["net"], "EUR")}</div></div>'
                            )
                        st.markdown(_rows_html, unsafe_allow_html=True)

    # ── Full page: Cash activity (Cash Management v1) ─────────────────────────
    if _section == "cash":
        _cash_ui.render_page(invested_value=total_current, is_viewer=_is_viewer,
                             on_back=lambda: _goto("overview"))

    # Dispatch at most one detail dialog per render
    if _pf_dlg_pending:
        open_drawer(*_pf_dlg_pending[0])
