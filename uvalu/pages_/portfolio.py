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
                       record_value_snapshot, ensure_value_history_fresh)
from screener import get_fetch_progress, PORTFOLIO_FETCH
from uvalu.data import _fetch_prices_cached, _load_portfolio_scored, apply_live_mos
from uvalu.dialogs import (add_position_dialog, add_dividend_dialog,
                           add_closed_trade_dialog, _dialog_width_css)
from uvalu.components import (kpi_card as _kpi_card, portfolio_open_row,
                              portfolio_closed_row, portfolio_dividend_row, refresh_top_bar_html,
                              skeleton_kpi_card_html, skeleton_rows)
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

        _ov_div_all = load_div_hist()
        if _ov_div_all is not None and not _ov_div_all.empty:
            _div_dates = pd.to_datetime(_ov_div_all["date"], errors="coerce")
            _cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
            _div_12m = pd.to_numeric(
                _ov_div_all.loc[_div_dates >= _cutoff, "amount"], errors="coerce").sum()
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
                _col_header([200, 68, 88, 88, 108, 118, 132, 96],
                           ["Position", "Shares", "Avg cost", "Price", "Cost basis",
                            "Market value", "Unrealised P&L", "Weight"],
                           [False, True, True, True, True, True, True, False])
            if _pf_fetch_running:
                skeleton_rows([200, 68, 88, 88, 108, 118, 132, 96], n=min(len(pf), 5),
                             key_prefix="pf_skel_open_ov")
            else:
                _ov_view_target = None
                _ov_open = pf.sort_values("current_value", ascending=False).head(5)
                for _idx, _prow in _ov_open.iterrows():
                    _res = portfolio_open_row(
                        key=f"pf_open_row_ov_{_idx}_{_prow['ticker']}", ticker=_prow["ticker"],
                        exchange=_exchange_label(_prow["ticker"]), name=_prow["name"],
                        shares=_prow["shares"], avg_cost=_prow["purchase_price"], price=_prow["live_price"],
                        cost_basis=_prow["purchase_value"], value=_prow["current_value"],
                        gain=_prow["price_gain"], gain_pct=_prow["price_gain_pct"],
                        weight_pct=(_prow["current_value"] / total_current * 100) if total_current else 0,
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
                    skeleton_rows([300, 56, 74, 74, 110], n=3, key_prefix="pf_skel_closed_ov")
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
                    skeleton_rows([6, 1.3], n=3, key_prefix="pf_skel_div_ov")
                else:
                    _ov_div = load_div_hist()
                    if _ov_div is not None and not _ov_div.empty:
                        _ov_div = _ov_div.copy()
                        _ov_div["date"] = pd.to_datetime(_ov_div["date"], errors="coerce")
                        _ov_div["_date_str"] = _ov_div["date"].dt.strftime("%d %b %Y")
                        _ov_div = _ov_div.sort_values("date", ascending=False).head(5)
                        with st.container(key="pf_col_header_div_ov"):
                            _col_header([6, 1.3], ["Position", "Dividend"], [False, True])
                        for _didx, _drow in _ov_div.iterrows():
                            portfolio_dividend_row(
                                key=f"pf_div_row_ov_{_didx}", name=_drow.get("name", "—"),
                                ticker=_drow.get("ticker", ""), date=_drow["_date_str"] or "—",
                                amount=pd.to_numeric(_drow.get("amount"), errors="coerce"), show_edit=False,
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
            _dialog_width_css(380)
            st.markdown(f'<div style="font-size:17px;font-weight:500;letter-spacing:-0.02em;">'
                       f'Edit {_row["ticker"]}</div>', unsafe_allow_html=True)
            st.caption(_row["name"])
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

            _b1, _b2 = st.columns(2)
            with _b1:
                if st.button("Cancel", key="dlg_eop_cancel", width="stretch"):
                    st.rerun()
            with _b2:
                _do_save = st.button("Save", key="dlg_eop_save", width="stretch", type="primary")
            with st.container(key="uv_danger_btn"):
                _do_delete = st.button("Delete position", key="dlg_eop_delete", width="stretch")

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
                _col_header([240, 68, 88, 88, 108, 118, 132, 96, 32],
                           ["Position", "Shares", "Avg cost", "Price", "Cost basis",
                            "Market value", "Unrealised P&L", "Weight", ""],
                           [False, True, True, True, True, True, True, False, False])
            _view_target = None
            _edit_target = None
            _open_sorted = pf.sort_values("name", key=lambda s: s.str.lower())
            for _idx, _prow in _open_sorted.iterrows():
                _res = portfolio_open_row(
                    key=f"pf_open_row_{_idx}_{_prow['ticker']}", ticker=_prow["ticker"],
                    exchange=_exchange_label(_prow["ticker"]), name=_prow["name"],
                    shares=_prow["shares"], avg_cost=_prow["purchase_price"], price=_prow["live_price"],
                    cost_basis=_prow["purchase_value"], value=_prow["current_value"],
                    gain=_prow["price_gain"], gain_pct=_prow["price_gain_pct"],
                    weight_pct=(_prow["current_value"] / total_current * 100) if total_current else 0,
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
                _dialog_width_css(380)
                st.markdown(f'<div style="font-size:17px;font-weight:500;letter-spacing:-0.02em;">'
                           f'Edit {_row["ticker"]}</div>', unsafe_allow_html=True)
                st.caption(_row["name"])
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

                _b1, _b2 = st.columns(2)
                with _b1:
                    if st.button("Cancel", key="dlg_ecp_cancel", width="stretch"):
                        st.rerun()
                with _b2:
                    _do_save = st.button("Save", key="dlg_ecp_save", width="stretch", type="primary")
                with st.container(key="uv_danger_btn"):
                    _do_delete = st.button("Delete trade", key="dlg_ecp_delete", width="stretch")

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
        with st.container(key="pf_page_title_dividends", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Dividends received</div>',
                       unsafe_allow_html=True)
            if st.button("Add dividend", key="btn_add_div", type="primary", icon=":material/add:", disabled=_is_viewer,
                        help="Viewer role is read-only" if _is_viewer else None):
                add_dividend_dialog(pf)
        div_hist = load_div_hist()
        if div_hist is None or div_hist.empty:
            st.info("Re-upload your Excel file to load full dividend history.")
        else:
            div_hist = div_hist.copy().reset_index(drop=True)
            div_hist["amount"] = pd.to_numeric(div_hist["amount"], errors="coerce")
            div_hist["date"]   = pd.to_datetime(div_hist["date"], errors="coerce")
            div_hist["_date_str"] = div_hist["date"].dt.strftime("%d %b %Y")
            div_hist["shares"] = pd.to_numeric(div_hist.get("shares"), errors="coerce").fillna(0).astype(int)

            @st.dialog("Edit dividend", width="small")
            def _dlg_edit_dividend(orig_idx: int) -> None:
                enter_dialog()
                _row = div_hist.loc[orig_idx]
                _dialog_width_css(380)
                st.markdown(f'<div style="font-size:17px;font-weight:500;letter-spacing:-0.02em;">'
                           f'Edit {_row["ticker"]}</div>', unsafe_allow_html=True)
                st.caption(_row["name"])
                _c1, _c2 = st.columns(2)
                with _c1:
                    _shares = st.number_input("Shares", min_value=1, step=1,
                                              value=max(1, int(_row["shares"])), key="dlg_ed_shares")
                with _c2:
                    _dps0 = (_row["amount"] / _row["shares"]) if _row["shares"] else 0.0
                    _dps = st.number_input("Div/share (€)", min_value=0.0, step=0.0001,
                                           value=round(float(_dps0), 4), format="%.4f", key="dlg_ed_dps")
                _date = st.date_input("Date", value=_row["date"].date() if pd.notna(_row["date"]) else None,
                                      format="DD/MM/YYYY", key="dlg_ed_date")

                _b1, _b2 = st.columns(2)
                with _b1:
                    if st.button("Cancel", key="dlg_ed_cancel", width="stretch"):
                        st.rerun()
                with _b2:
                    _do_save = st.button("Save", key="dlg_ed_save", width="stretch", type="primary")
                with st.container(key="uv_danger_btn"):
                    _do_delete = st.button("Delete dividend", key="dlg_ed_delete", width="stretch")

                if _do_save:
                    _dh = load_div_hist()
                    _new_shares = max(1, int(_shares))
                    _dh.at[orig_idx, "shares"] = _new_shares
                    _dh.at[orig_idx, "amount"] = round(_dps * _new_shares, 2)
                    if _date is not None:
                        _dh.at[orig_idx, "date"] = pd.Timestamp(_date).isoformat()
                    update_div_hist(_dh)
                    st.rerun()
                if _do_delete:
                    _dh = load_div_hist()
                    _dh.drop(index=orig_idx, inplace=True)
                    _dh.reset_index(drop=True, inplace=True)
                    update_div_hist(_dh)
                    st.rerun()

            div_sorted = div_hist.sort_values("date", ascending=False)
            with st.container(key="pf_card_div_full", border=True):
                with st.container(key="pf_col_header_div_full"):
                    _col_header([6, 1.3, 0.4], ["Position", "Dividend", ""], [False, True, False])
                _edit_target = None
                for _idx, _drow in div_sorted.iterrows():
                    _res = portfolio_dividend_row(
                        key=f"pf_div_row_{_idx}", name=_drow.get("name", "—"),
                        ticker=_drow.get("ticker", ""), date=_drow["_date_str"] or "—",
                        amount=_drow.get("amount"), show_edit=True, edit_disabled=_is_viewer,
                    )
                    if _res["edit"]:
                        _edit_target = _idx
                if _edit_target is not None:
                    _dlg_edit_dividend(_edit_target)

    # Dispatch at most one detail dialog per render
    if _pf_dlg_pending:
        open_drawer(*_pf_dlg_pending[0])
