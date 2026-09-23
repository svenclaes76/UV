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
                       save_sold, update_positions, update_div_hist,
                       record_value_snapshot, ensure_value_history_fresh,
                       dividends_in_eur, dividend_income_summary,
                       import_dividends_from_market_data, dismiss_auto_dividend,
                       exchange_key_for_ticker, currency_for_ticker)
from settings import get_dividend_withholding
from screener import get_fetch_progress, PORTFOLIO_FETCH
from uvalu.data import _fetch_prices_cached, _load_portfolio_scored, apply_live_mos
from uvalu.dialogs import (add_position_dialog, add_dividend_dialog,
                           add_closed_trade_dialog, _dialog_width_css, _num_or,
                           dialog_frame, identity_row, dialog_actions, dividend_tax_preview,
                           _dividend_tax_breakdown, DIV_TYPE_OPTIONS)
from uvalu.components import (kpi_card as _kpi_card, portfolio_open_row,
                              portfolio_closed_row, portfolio_dividend_row, dividend_log_row,
                              dividend_log_header_html, DIVIDEND_LOG_COL_SPLIT,
                              refresh_top_bar_html, skeleton_kpi_card_html, skeleton_rows)
from uvalu.formatting import safe_pct as _safe_pct
from uvalu.runtime import current_user
from uvalu.drawer import open_drawer
from uvalu.ui import price_autorefresh, consumed_tick, enter_dialog, poll_while_fetching

# Same suffix->exchange mapping already used in uvalu/pages_/risk.py — the
# row components render a compact mono exchange chip next to the ticker.
_TICKER_SUFFIX_EXCHANGE = {
    ".BR": "Brussels", ".AS": "Amsterdam", ".PA": "Paris",
    ".MI": "Milan", ".DE": "Frankfurt", ".SW": "Swiss",
}


def _exchange_label(ticker: str) -> str:
    for suffix, label in _TICKER_SUFFIX_EXCHANGE.items():
        if str(ticker).endswith(suffix):
            return label
    return "—"


def _col_header(widths: list, labels: list[str], rights: list[bool]) -> None:
    """One row of 10px uppercase faint column labels, matching Uvalu.dc.html's
    column-header spec — right-aligned for numeric columns, left for text."""
    for _c, _lbl, _right in zip(st.columns(widths, vertical_alignment="center"), labels, rights):
        with _c:
            _align = "text-align:right;" if _right else ""
            # white-space:nowrap — narrower columns (e.g. Closed positions'
            # 56px Shares column) are tight enough that "SHARES" at 10px
            # uppercase/letter-spacing wraps to two lines without this,
            # doubling that one column's own content height and throwing
            # off the whole header row's vertical centering (confirmed
            # live: Shares rendered 32px tall vs every sibling's 16px).
            st.markdown(f'<div style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                       f'white-space:nowrap;color:var(--faint);{_align}">{_lbl}</div>', unsafe_allow_html=True)


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
        if _dirty:
            save_portfolio(pf)

        # ── Drop rows with no valid ticker ────────────────────────────────────
        pf = pf[pf["ticker"].notna() & (pf["ticker"].astype(str).str.strip() != "")].reset_index(drop=True)

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
        # ── Empty portfolio — show Add button only ────────────────────────────
        if st.button("Add", key="btn_add_pos_empty", icon=":material/add:", disabled=_is_viewer,
                    help="Viewer role is read-only" if _is_viewer else None):
            add_position_dialog()
        st.info("Your portfolio is empty. Click Add to record your first position.")
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

    _section = st.session_state.get("port_section", "overview")

    def _goto(section: str) -> None:
        st.session_state["port_section"] = section
        st.rerun()

    # ── Overview — heading + 5-card KPI strip + open/closed/dividends previews ──
    if _section == "overview":
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            with st.container(width="content"):
                st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Portfolio</div>',
                           unsafe_allow_html=True)
                st.caption("Cost basis, market value and realised results across open and closed positions.")
            with st.container(horizontal=True, gap="small", width="content"):
                _ov_csv = pd.DataFrame({
                    "Company": pf["name"], "Ticker": pf["ticker"], "Shares": pf["shares"],
                    "Buy price": pf["purchase_price"], "Live price": pf["live_price"],
                    "Invested": pf["purchase_value"], "Current value": pf["current_value"],
                    "Price gain": pf["price_gain"],
                }).to_csv(index=False)
                st.download_button("Export CSV", data=_ov_csv, file_name="uvalu_portfolio.csv",
                                   mime="text/csv", key="ov_export", icon=":material/download:")
                if st.button("Add", key="ov_buy", type="primary", icon=":material/add:", disabled=_is_viewer,
                            help="Viewer role is read-only" if _is_viewer else None):
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
                    _kpi_card("Invested", f"€{total_invested:,.0f}", sub=f"{len(pf)} open positions", icon="wallet")
                with _o2:
                    _kpi_card("Market value", f"€{total_current:,.0f}", f"{price_gain_pct:+.1f}%",
                              price_gain >= 0, "current holdings", icon="wallet")
                with _o3:
                    _kpi_card("Unrealised P&L", f"€{price_gain:,.0f}", f"{price_gain_pct:+.1f}%",
                              price_gain >= 0, "open positions", icon="trend")
                with _o4:
                    _kpi_card("Realised P&L", f"€{_realised_pl:,.0f}", sub=f"{_realised_count} closed trades", icon="trend")
                with _o5:
                    _kpi_card("Dividends (12m)", f"€{_div_12m:,.0f}", sub="income received", icon="coin")

        # ── Open positions preview (top 5 by market value) ────────────────────
        with st.container(key="pf_card_open_ov", border=True):
            with st.container(key="pf_panel_title_open_ov", horizontal=True, vertical_alignment="center",
                              horizontal_alignment="distribute"):
                st.markdown("Open positions")
                if st.button("", key="ov_open_expand", icon=":material/open_in_full:", help="Open full page"):
                    _goto("open")
            with st.container(key="pf_col_header_open_ov"):
                _col_header([200, 68, 88, 88, 108, 118, 132, 96, 60, 70, 96],
                           ["Position", "Shares", "Avg cost", "Price", "Cost basis",
                            "Market value", "Unrealised P&L", "Income 12m", "Yield", "YoC net", "Weight"],
                           [False, True, True, True, True, True, True, True, True, True, False])
            if _pf_fetch_running:
                skeleton_rows([200, 68, 88, 88, 108, 118, 132, 96, 60, 70, 96], n=min(len(pf), 5),
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
                        show_edit=False,
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
                    st.markdown('Closed positions <span style="color:var(--faint);font-weight:400;">· realised</span>',
                               unsafe_allow_html=True)
                    if st.button("", key="ov_closed_expand", icon=":material/open_in_full:", help="Open full page"):
                        _goto("closed")
                if _pf_fetch_running:
                    with st.container(key="pf_col_header_closed_ov"):
                        _col_header([300, 56, 74, 74, 110],
                                   ["Position", "Shares", "Buy", "Sell", "Realised P&L"],
                                   [False, True, True, True, True])
                    skeleton_rows([300, 56, 74, 74, 110], n=3, key_prefix="uv_skel_row_pf_closed")
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
                        _ov_sold["_closed_str"] = pd.to_datetime(
                            _ov_sold["date_out"], format="mixed", dayfirst=False, errors="coerce").dt.strftime("%b %Y")
                        _ov_sold = _ov_sold.sort_values("date_out", ascending=False).head(5)
                        with st.container(key="pf_col_header_closed_ov"):
                            _col_header([300, 56, 74, 74, 110],
                                       ["Position", "Shares", "Buy", "Sell", "Realised P&L"],
                                       [False, True, True, True, True])
                        for _sidx, _srow in _ov_sold.iterrows():
                            portfolio_closed_row(
                                key=f"pf_closed_row_ov_{_sidx}_{_srow['ticker']}", ticker=_srow["ticker"],
                                exchange=_exchange_label(_srow["ticker"]), name=_srow["name"],
                                closed_date=_srow["_closed_str"] or "—", shares=_srow["shares"],
                                buy=_srow["_buy"], sell=_srow["_sell"], pl=_srow["_gain"], pl_pct=_srow["_gain_pct"],
                                show_edit=False,
                            )
                    else:
                        st.caption("No closed positions yet.")
        with _oc2:
            with st.container(key="pf_card_div_ov", border=True):
                with st.container(key="pf_panel_title_div_ov", horizontal=True, vertical_alignment="center",
                                  horizontal_alignment="distribute"):
                    st.markdown("Dividends received")
                    if st.button("", key="ov_div_expand", icon=":material/open_in_full:", help="Open full page"):
                        _goto("dividends")
                if _pf_fetch_running:
                    with st.container(key="pf_col_header_div_ov"):
                        _col_header([6, 1.3], ["Position", "Dividend"], [False, True])
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
                        _ov_div["_date_str"] = _ov_div["date"].dt.strftime("%d %b %Y")
                        _ov_div = _ov_div.sort_values("date", ascending=False).head(5)
                        with st.container(key="pf_col_header_div_ov"):
                            _col_header([6, 1.3], ["Position", "Net dividend"], [False, True])
                        for _didx, _drow in _ov_div.iterrows():
                            portfolio_dividend_row(
                                key=f"pf_div_row_ov_{_didx}", name=_drow.get("name", "—"),
                                ticker=_drow.get("ticker", ""), date=_drow["_date_str"] or "—",
                                amount=_drow.get("net_after_be_amount_eur"), show_edit=False,
                            )
                    else:
                        st.caption("No dividends received yet.")

    # ── Full page: Open positions ──────────────────────────────────────────────
    if _section == "open":
        if st.button("← Back to Positions", key="back_open", type="tertiary"):
            _goto("overview")
        with st.container(key="pf_page_title_open", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Open positions</div>',
                       unsafe_allow_html=True)
            if st.button("Add", key="btn_add_pos", type="primary", icon=":material/add:", disabled=_is_viewer,
                        help="Viewer role is read-only" if _is_viewer else None):
                add_position_dialog()

        @st.dialog("Edit position", width="small")
        def _dlg_edit_open_position(orig_idx: int) -> None:
            enter_dialog()
            _row = pf.loc[orig_idx]
            dialog_frame("Update shares, invested amount or buy date.")
            identity_row(ticker=str(_row["ticker"]), name=str(_row["name"]),
                         key_prefix=f"dlg_eop_id_{orig_idx}", locked=True)
            _c1, _c2 = st.columns(2)
            with _c1:
                _shares = st.number_input("Shares", min_value=1, step=1,
                                          value=max(1, int(_row["shares"])), key="dlg_eop_shares")
            with _c2:
                _invested = st.number_input("Invested (€)", min_value=0.01, step=0.01,
                                            value=round(float(_row["purchase_value"]), 2),
                                            format="%.2f", key="dlg_eop_invested")
            _date0 = pd.to_datetime(_row["date_in"], format="mixed", dayfirst=False, errors="coerce")
            _date = st.date_input("Buy date", value=_date0.date() if pd.notna(_date0) else None,
                                  format="DD/MM/YYYY", key="dlg_eop_date")

            _do_save, _do_delete = dialog_actions("dlg_eop", delete=True)

            if _do_save:
                pf.at[orig_idx, "shares"] = max(1, int(_shares))
                pf.at[orig_idx, "purchase_price"] = round(_invested / max(1, int(_shares)), 4)
                pf.at[orig_idx, "purchase_value"] = round(_invested, 2)
                if _date is not None:
                    pf.at[orig_idx, "date_in"] = pd.Timestamp(_date).isoformat()
                update_positions(pf)
                st.rerun()
            if _do_delete:
                pf.drop(index=orig_idx, inplace=True)
                pf.reset_index(drop=True, inplace=True)
                update_positions(pf)
                st.rerun()

        # The drawer's "Edit" button (uvalu/drawer.py's _go_portfolio_edit)
        # can't call this dialog directly — it's defined inside this page's
        # own render() closure, and the drawer needs a full page navigation
        # first anyway. It stashes the ticker here instead; resolve it to
        # this run's row index and open the dialog ourselves.
        _pending_edit_ticker = st.session_state.pop("_pf_edit_ticker", None)
        if _pending_edit_ticker is not None:
            _edit_match = pf[pf["ticker"] == _pending_edit_ticker]
            if not _edit_match.empty:
                _dlg_edit_open_position(_edit_match.index[0])

        with st.container(key="pf_card_open_full", border=True):
            with st.container(key="pf_col_header_open_full"):
                _col_header([240, 68, 88, 88, 108, 118, 132, 96, 60, 70, 96, 32],
                           ["Position", "Shares", "Avg cost", "Price", "Cost basis",
                            "Market value", "Unrealised P&L", "Income 12m", "Yield", "YoC net", "Weight", ""],
                           [False, True, True, True, True, True, True, True, True, True, False, False])
            _view_target = None
            _edit_target = None
            _open_sorted = pf.sort_values("name", key=lambda s: s.str.lower())
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
                    show_edit=True, edit_disabled=_is_viewer,
                )
                if _res["view"]:
                    _view_target = _prow["ticker"]
                if _res["edit"]:
                    _edit_target = _idx
            if _edit_target is not None:
                _dlg_edit_open_position(_edit_target)
            if _view_target is not None:
                _r = _all_scr_df[_all_scr_df["Ticker"] == _view_target]
                if not _r.empty:
                    _pf_dlg_pending.append((_r.iloc[0],))

    # ── Full page: Closed positions ───────────────────────────────────────────
    if _section == "closed":
        if st.button("← Back to Positions", key="back_closed", type="tertiary"):
            _goto("overview")
        with st.container(key="pf_page_title_closed", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Closed positions '
                       '<span style="color:var(--faint);font-weight:400;">· realised</span></div>',
                       unsafe_allow_html=True)
            if st.button("Close", key="btn_add_closed", type="primary", icon=":material/add:", disabled=_is_viewer,
                        help="Viewer role is read-only" if _is_viewer else None):
                add_closed_trade_dialog()
        sold = load_sold()
        if sold is None or sold.empty:
            st.info("No sold positions found in your portfolio file.")
        else:
            sold = sold.reset_index(drop=True)
            _pv = pd.to_numeric(sold["purchase_value"], errors="coerce")
            _sv = pd.to_numeric(sold["sale_value"], errors="coerce")
            sold["_gain"] = _sv - _pv
            sold["_gain_pct"] = (sold["_gain"] / _pv.replace(0, float("nan")) * 100).round(2)
            sold["_buy"]  = _pv / pd.to_numeric(sold["shares"], errors="coerce")
            sold["_sell"] = _sv / pd.to_numeric(sold["shares"], errors="coerce")
            sold["_closed_str"] = pd.to_datetime(
                sold["date_out"], format="mixed", dayfirst=False, errors="coerce").dt.strftime("%b %Y")
            sold_sorted = sold.assign(
                _sort_date=pd.to_datetime(sold["date_out"], format="mixed", dayfirst=False, errors="coerce")
            ).sort_values("_sort_date", ascending=False)

            @st.dialog("Edit trade", width="small")
            def _dlg_edit_closed_position(orig_idx: int) -> None:
                enter_dialog()
                _row = sold.loc[orig_idx]
                dialog_frame("Update shares, proceeds or sell date.")
                identity_row(ticker=str(_row["ticker"]), name=str(_row["name"]),
                             key_prefix=f"dlg_ecp_id_{orig_idx}", locked=True)
                _c1, _c2 = st.columns(2)
                with _c1:
                    _shares = st.number_input("Shares", min_value=1, step=1,
                                              value=max(1, int(_row["shares"])), key="dlg_ecp_shares")
                with _c2:
                    _proceeds = st.number_input("Proceeds (€)", min_value=0.0, step=0.01,
                                                value=round(float(_row["sale_value"]), 2),
                                                format="%.2f", key="dlg_ecp_proceeds")
                _date0 = pd.to_datetime(_row["date_out"], format="mixed", dayfirst=False, errors="coerce")
                _date = st.date_input("Sell date", value=_date0.date() if pd.notna(_date0) else None,
                                      format="DD/MM/YYYY", key="dlg_ecp_date")

                _do_save, _do_delete = dialog_actions("dlg_ecp", delete=True)

                if _do_save:
                    _sold_fresh = load_sold()
                    _sold_fresh.at[orig_idx, "shares"] = max(1, int(_shares))
                    _sold_fresh.at[orig_idx, "sale_value"] = round(_proceeds, 2)
                    if _date is not None:
                        _sold_fresh.at[orig_idx, "date_out"] = pd.Timestamp(_date).isoformat()
                    save_sold(_sold_fresh)
                    st.rerun()
                if _do_delete:
                    _sold_fresh = load_sold()
                    _sold_fresh.drop(index=orig_idx, inplace=True)
                    _sold_fresh.reset_index(drop=True, inplace=True)
                    save_sold(_sold_fresh)
                    st.rerun()

            with st.container(key="pf_card_closed_full", border=True):
                with st.container(key="pf_col_header_closed_full"):
                    _col_header([400, 56, 74, 74, 110, 32],
                               ["Position", "Shares", "Buy", "Sell", "Realised P&L", ""],
                               [False, True, True, True, True, False])
                _edit_target = None
                for _idx, _srow in sold_sorted.iterrows():
                    _res = portfolio_closed_row(
                        key=f"pf_closed_row_{_idx}_{_srow['ticker']}", ticker=_srow["ticker"],
                        exchange=_exchange_label(_srow["ticker"]), name=_srow["name"],
                        closed_date=_srow["_closed_str"] or "—", shares=_srow["shares"],
                        buy=_srow["_buy"], sell=_srow["_sell"], pl=_srow["_gain"], pl_pct=_srow["_gain_pct"],
                        show_edit=True, edit_disabled=_is_viewer,
                    )
                    if _res["edit"]:
                        _edit_target = _idx
                if _edit_target is not None:
                    _dlg_edit_closed_position(_edit_target)

    # ── Full page: Dividends ───────────────────────────────────────────────────
    if _section == "dividends":
        if st.button("← Back to Positions", key="back_div", type="tertiary"):
            _goto("overview")
        # Auto-import from market data — once per session per user, never for
        # the read-only Viewer role (it writes the ledger). The import itself
        # only adds events on dates the user held shares, skips events already
        # logged by hand and never re-adds a deleted one
        # (portfolio.import_dividends_from_market_data).
        _auto_key = f"_div_auto_import_done_{_user.email}"
        if not _is_viewer and not st.session_state.get(_auto_key) and not pf.empty:
            st.session_state[_auto_key] = True
            with st.spinner("Checking market data for new dividends…"):
                _n_imported = import_dividends_from_market_data(pf, _user.email)
            if _n_imported:
                st.toast(f"Imported {_n_imported} dividend event(s) from market data.", icon=":material/sync:")

        div_hist = load_div_hist()
        _has_divs = div_hist is not None and not div_hist.empty
        _div_csv = ""
        if _has_divs:
            div_hist = div_hist.copy().reset_index(drop=True)
            div_hist["amount"] = pd.to_numeric(div_hist["amount"], errors="coerce")
            div_hist["date"]   = pd.to_datetime(div_hist["date"], errors="coerce")
            # NaT.strftime() is NaN, not None -- and NaN is truthy in Python,
            # so a later `x or "-"` fallback at the call site wouldn't catch
            # it (rendered literal "nan" text instead of a dash). Blank out
            # missing dates here instead, before any such fallback runs.
            div_hist["_date_str"] = div_hist["date"].dt.strftime("%d %b %Y").fillna("—")
            div_hist["shares"] = pd.to_numeric(div_hist.get("shares"), errors="coerce").fillna(0).astype(int)
            div_hist["reinvested"] = (
                div_hist["reinvested"].fillna(False).astype(bool)
                if "reinvested" in div_hist.columns else False
            )
            div_eur = dividends_in_eur(div_hist)
            div_eur["_date_str"] = div_hist["_date_str"]
            div_eur["_ex_str"] = (pd.to_datetime(div_eur["ex_date"], errors="coerce")
                                  .dt.strftime("%d %b %Y").fillna("—"))
            div_sorted = div_eur.sort_values("date", ascending=False)
            _div_csv = div_sorted[["name", "ticker", "_ex_str", "_date_str", "div_type", "currency",
                                   "amount", "tax_amount", "be_tax_amount", "net_after_be_amount",
                                   "source", "reinvested"]].rename(columns={
                "name": "Company", "ticker": "Ticker",
                "_ex_str": "Ex-dividend date", "_date_str": "Payment date",
                "div_type": "Type", "currency": "Currency", "amount": "Gross (native)",
                "tax_amount": "Foreign WH (native)", "be_tax_amount": "Belgian RV 30% (native)",
                "net_after_be_amount": "Net (native)", "source": "Source", "reinvested": "DRIP",
            }).to_csv(index=False)

        with st.container(key="pf_page_title_dividends", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            with st.container(width="content"):
                st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Dividend log</div>',
                           unsafe_allow_html=True)
                st.caption("Per-holding dividend events. Auto-fetched from the market data source where "
                          "dividend history is exposed; manual entry fills the gaps.")
            with st.container(horizontal=True, gap="small", width="content"):
                st.download_button("Export", data=_div_csv, file_name="uvalu_dividend_log.csv",
                                   mime="text/csv", key="div_export", icon=":material/download:",
                                   disabled=not _has_divs)
                if st.button("Add dividend", key="btn_add_div", type="primary", icon=":material/add:", disabled=_is_viewer,
                            help="Viewer role is read-only" if _is_viewer else None):
                    add_dividend_dialog(pf)
        if not _has_divs:
            st.info("No dividend events yet. Add one with Add dividend — events for your held tickers are "
                    "also fetched from market data where available.")
        else:
            @st.dialog("Edit dividend", width="small")
            def _dlg_edit_dividend(orig_idx: int) -> None:
                import datetime as _dt

                enter_dialog()
                _row = div_hist.loc[orig_idx]
                dialog_frame("Update this dividend's dates, amounts or type.")
                identity_row(ticker=str(_row["ticker"]), name=str(_row["name"]),
                             key_prefix=f"dlg_ed_id_{orig_idx}", locked=True)
                if bool(_row.get("reinvested")):
                    st.caption("Reinvested (DRIP) — the purchased shares were already added to "
                              "this position and aren't re-applied by editing this record.")
                # A missing currency comes back as NaN (truthy), which used to
                # render the label as "Gross / share (nan)".
                _ccy = _row.get("currency")
                if not isinstance(_ccy, str) or not _ccy.strip():
                    _ccy = currency_for_ticker(str(_row["ticker"])) or "EUR"

                def _parse_date(v):
                    d = pd.to_datetime(v, errors="coerce")
                    return d.date() if pd.notna(d) else None

                _row_pay = _row["date"].date() if pd.notna(_row["date"]) else None
                _max_date = max(_dt.date.today(), _row_pay) if _row_pay else _dt.date.today()

                # Same fields/order as add_dividend_dialog — declaration/record
                # dates and frequency were dropped from both. Saving leaves any
                # declaration/record date a record already carries untouched.
                _c1, _c2 = st.columns(2)
                with _c1:
                    _ex = st.date_input("Ex-dividend date *", value=_parse_date(_row.get("ex_date")),
                                        format="DD/MM/YYYY", max_value=_max_date, key="dlg_ed_ex")
                with _c2:
                    _date = st.date_input("Payment date *", value=_row_pay, format="DD/MM/YYYY",
                                          max_value=_max_date, key="dlg_ed_date")

                _c5, _c6, _c7 = st.columns(3)
                with _c5:
                    _shares = st.number_input("Shares held", min_value=0, step=1,
                                              value=max(0, int(_num_or(_row["shares"], 0))), key="dlg_ed_shares")
                with _c6:
                    _sh0 = float(_num_or(_row["shares"], 0))
                    _dps0 = float(_num_or(_row.get("amount_per_share"), 0.0)) or (
                        float(_num_or(_row["amount"], 0.0)) / _sh0 if _sh0 else 0.0)
                    _dps = st.number_input(f"Per share ({_ccy})", min_value=0.0, step=0.0001,
                                           value=round(float(_dps0), 4), format="%.4f", key="dlg_ed_dps")
                with _c7:
                    _tax_rate = st.number_input("Foreign WH (%)", min_value=0.0, max_value=100.0,
                                                step=0.5, value=float(_num_or(_row.get("tax_rate"), 0.0)),
                                                key="dlg_ed_tax")

                _type0 = _row.get("div_type") or "Cash"
                _type = st.selectbox("Type", options=DIV_TYPE_OPTIONS,
                                     index=DIV_TYPE_OPTIONS.index(_type0) if _type0 in DIV_TYPE_OPTIONS else 0,
                                     key="dlg_ed_type")

                _gross = round(_dps * _shares, 2)
                _fwh, _be, _net = _dividend_tax_breakdown(_gross, _tax_rate, _type)
                dividend_tax_preview(_gross, _fwh, _be, _net)

                _do_save, _do_delete = dialog_actions("dlg_ed", delete=True)

                if _do_save:
                    if _ex is None:
                        st.error("Ex-dividend date is required.")
                        return
                    if _date is None:
                        st.error("Payment date is required.")
                        return
                    _dh = load_div_hist()
                    _dh.at[orig_idx, "shares"] = int(_shares)
                    _dh.at[orig_idx, "amount"] = _gross
                    _dh.at[orig_idx, "amount_per_share"] = round(_dps, 4)
                    _dh.at[orig_idx, "tax_rate"] = round(_tax_rate, 2)
                    _dh.at[orig_idx, "tax_amount"] = _fwh
                    _dh.at[orig_idx, "div_type"] = _type
                    _dh.at[orig_idx, "ex_date"] = pd.Timestamp(_ex).isoformat()
                    _dh.at[orig_idx, "date"] = pd.Timestamp(_date).isoformat()
                    update_div_hist(_dh)
                    st.rerun()
                if _do_delete:
                    _dh = load_div_hist()
                    if _dh.at[orig_idx, "source"] == "auto":
                        dismiss_auto_dividend(str(_dh.at[orig_idx, "ticker"]), _dh.at[orig_idx, "ex_date"])
                    _dh.drop(index=orig_idx, inplace=True)
                    _dh.reset_index(drop=True, inplace=True)
                    update_div_hist(_dh)
                    st.rerun()

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
                    _kpi_card("Gross income · 12m", f"€{_tile_gross:,.0f}",
                             sub=f"{_tile_n_events} events · {_tile_n_holdings} holdings", icon="coin")
                with _t2:
                    _kpi_card("Withholding · 12m", f"−€{(_tile_fwh + _tile_be):,.0f}",
                             sub=f"€{_tile_fwh:,.0f} foreign · €{_tile_be:,.0f} BE 30%", icon="coin")
                with _t3:
                    _kpi_card("Net income · 12m", f"€{_tile_net:,.0f}", sub="after all withholding", icon="coin")
                with _t4:
                    _kpi_card("Net yield", f"{_safe_pct(_tile_net, total_current):.2f}%", sub="on market value", icon="trend")
                with _t5:
                    _kpi_card("Net yield-on-cost", f"{_safe_pct(_tile_net, total_invested):.2f}%",
                             sub="weighted, remaining cost basis", icon="trend")

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
                        ex_date=_drow.get("_ex_str") or "—", pay_date=_drow.get("_date_str") or "—",
                        div_type=_drow.get("div_type") or "Cash",
                        per_share=_drow.get("amount_per_share"), shares=_drow.get("shares"),
                        gross=_drow.get("amount_eur"), foreign_wh=_drow.get("tax_amount_eur"),
                        wh_note=(f"{exchange_key_for_ticker(_drow.get('ticker', '')) or '—'} "
                                f"{_drow.get('tax_rate'):.1f}%"
                                if pd.notna(_drow.get("tax_rate")) and _drow.get("tax_rate") else "no treaty WH"),
                        be_wh=_drow.get("be_tax_amount_eur"), net=_drow.get("net_after_be_amount_eur"),
                        source=_drow.get("source") or "manual", drip=bool(_drow.get("reinvested")),
                        needs_confirm=_needs_confirm, edit_disabled=_is_viewer,
                    )
                    if _res["edit"]:
                        _edit_target = _idx
                if _edit_target is not None:
                    _dlg_edit_dividend(_edit_target)

            # ── Annual dividend income summary ───────────────────────────────
            _years_df = div_eur.assign(_year=pd.to_datetime(div_eur["date"], errors="coerce").dt.year)
            _year_summary = _years_df.dropna(subset=["_year"]).groupby("_year").agg(
                events=("ticker", "count"), gross=("amount_eur", "sum"),
                fwh=("tax_amount_eur", "sum"), be=("be_tax_amount_eur", "sum"),
                net=("net_after_be_amount_eur", "sum")).sort_index(ascending=False)
            _summary_csv = _year_summary.reset_index().rename(columns={
                "_year": "Year", "events": "Events", "gross": "Gross (EUR)",
                "fwh": "Foreign WH (EUR)", "be": "Belgian RV 30% (EUR)", "net": "Net (EUR)",
            }).to_csv(index=False)

            def _neg_eur(v: float) -> str:
                # "—" for no withholding, same as the log's Foreign WH / BE 30%
                # cells — a bare "−€0.00" reads like a real deduction.
                return f"−€{v:,.2f}" if pd.notna(v) and round(float(v), 2) != 0 else "—"

            # Design width: the summary takes the left of a 1.6 : 1 split; the
            # right-hand column is intentionally empty, reserved for future cards.
            _yc1, _yc2 = st.columns([1.6, 1], gap="large")
            with _yc1:
                with st.container(key="pf_card_tax_years", border=True):
                    with st.container(key="pf_tax_years_title", horizontal=True, vertical_alignment="center",
                                      horizontal_alignment="distribute"):
                        st.markdown('<div style="font-size:15px;font-weight:500;">Annual dividend income summary</div>'
                                   '<div style="font-size:12px;color:var(--muted);margin-top:3px;">'
                                   'Net and gross reported separately, for your own tax filing.</div>',
                                   unsafe_allow_html=True, width="content")
                        st.download_button("Export", data=_summary_csv, file_name="uvalu_dividend_tax_summary.csv",
                                           mime="text/csv", key="div_summary_export", icon=":material/download:",
                                           disabled=_year_summary.empty)
                    if _year_summary.empty:
                        st.caption("No dividend history to summarise yet.")
                    else:
                        _this_year = pd.Timestamp.now().year
                        _grid = ("minmax(0,110px) minmax(0,1fr) minmax(0,150px) minmax(0,150px) "
                                 "minmax(0,150px) minmax(0,150px)")
                        _num = "text-align:right;font-family:var(--uv-mono);"
                        _rows_html = (
                            f'<div style="display:grid;grid-template-columns:{_grid};gap:14px;align-items:center;'
                            f'padding:10px 20px;border-top:0.5px solid var(--line-2);'
                            f'border-bottom:0.5px solid var(--line-2);font-size:10px;letter-spacing:0.06em;'
                            f'text-transform:uppercase;color:var(--faint);">'
                            f'<div>Year</div><div></div><div style="text-align:right;">Gross</div>'
                            f'<div style="text-align:right;">Foreign WH</div><div style="text-align:right;">BE 30%</div>'
                            f'<div style="text-align:right;">Net</div></div>'
                        )
                        for _year, _yrow in _year_summary.iterrows():
                            _partial = "year to date" if int(_year) == _this_year else "full year"
                            _rows_html += (
                                f'<div style="display:grid;grid-template-columns:{_grid};gap:14px;align-items:center;'
                                f'padding:14px 20px;border-bottom:0.5px solid var(--line-2);">'
                                f'<div style="font-family:var(--uv-mono);font-size:13.5px;font-weight:500;">{int(_year)}</div>'
                                f'<div style="font-size:11.5px;color:var(--faint);white-space:nowrap;">'
                                f'{int(_yrow["events"])} events · {_partial}</div>'
                                f'<div style="{_num}font-size:12.5px;">€{_yrow["gross"]:,.2f}</div>'
                                f'<div style="{_num}font-size:12.5px;color:var(--muted);">{_neg_eur(_yrow["fwh"])}</div>'
                                f'<div style="{_num}font-size:12.5px;color:var(--muted);">{_neg_eur(_yrow["be"])}</div>'
                                f'<div style="{_num}font-size:13px;font-weight:500;color:var(--uv-mint,#1DD6A4);">'
                                f'€{_yrow["net"]:,.2f}</div></div>'
                            )
                        st.markdown(_rows_html, unsafe_allow_html=True)

    # Dispatch at most one detail dialog per render
    if _pf_dlg_pending:
        open_drawer(*_pf_dlg_pending[0])
