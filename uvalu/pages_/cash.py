"""Cash Management v1 — the Portfolio page's cash strip and the full "Cash
activity" page (Uvalu Cash Management.dc.html).

Not a navigation page of its own: uvalu/pages_/portfolio.py renders the strip
on its Overview and routes ``port_section == "cash"`` here, the same way it
routes its Open / Closed / Dividends full pages. The ledger itself lives in
cash.py; this module only draws it.

Roles (plan D1): Owner/Editor = any non-Viewer on their own portfolio; the
Viewer role sees everything and can export, but the add/deposit/withdraw
controls are hidden.
"""
import streamlit as st

import cash
from portfolio import base_currency
from uvalu.components import (kpi_card, cash_balance_block_html, cash_alloc_html,
                              cash_ledger_table_html, MINT_CHIP_STYLE)
from uvalu.dialogs import cash_transaction_dialog

_PAGE_ROWS = 200   # rows drawn before "Show all" — the ledger is kept forever


def reconcile_once(email: str, is_viewer: bool) -> None:
    """Mirror due dividends into the ledger once per session (a dividend
    dated in the future posts when its pay date arrives; an earlier FX
    outage is retried). Skipped for the read-only Viewer role, like the
    dividend auto-import."""
    key = f"_cash_reconcile_done_{email}"
    if is_viewer or st.session_state.get(key):
        return
    st.session_state[key] = True
    try:
        cash.reconcile_dividend_postings()
    except Exception:
        # Never block the page on bookkeeping — retried next session.
        pass


def _last_text(s: dict) -> str:
    if not s["count"]:
        return "No entries yet · buys top up automatically"
    return f"Last entry {cash.fmt_date(s['last_date'])} · {str(s['last_type']).lower()}"


def render_strip(*, invested_value: float, is_viewer: bool, on_open) -> None:
    """The Overview card: balance, invested-vs-cash bar, Deposit/Withdraw."""
    base = base_currency()
    s = cash.summary(cash.load_ledger(), invested_value)
    with st.container(key="pf_card_cash_ov", border=True):
        with st.container(key="pf_panel_title_cash_ov", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            st.markdown('Cash balance <span style="font-family:var(--uv-mono);font-size:9.5px;font-weight:400;'
                        'padding:1px 6px;border-radius:4px;border:0.5px solid var(--line);color:var(--muted);'
                        f'margin-left:6px;">{base} base</span>', unsafe_allow_html=True)
            if st.button("", key="ov_cash_expand", icon=":material/open_in_full:", help="Open full page"):
                on_open()
        with st.container(key="pf_cash_strip_body"):
            _cols = st.columns([1.1, 3.4, 1.1] if not is_viewer else [1.1, 4.5],
                               vertical_alignment="center", gap="large")
            _c1, _c2 = _cols[0], _cols[1]
            with _c1:
                st.markdown(cash_balance_block_html(cash.money(s["balance"], base), _last_text(s)),
                            unsafe_allow_html=True)
            with _c2:
                st.markdown(cash_alloc_html(s["invested_pct"], s["cash_pct"], cash.money(s["total"], base, 0)),
                            unsafe_allow_html=True)
            if not is_viewer:
                with _cols[2]:
                    with st.container(horizontal=True, gap="small", horizontal_alignment="right"):
                        if st.button("Deposit", key="ov_cash_deposit"):
                            cash_transaction_dialog("Deposit")
                        if st.button("Withdraw", key="ov_cash_withdraw"):
                            cash_transaction_dialog("Withdrawal")


def _signed0(v: float, base: str) -> str:
    return ("+" if v >= 0 else "−") + cash.money(abs(v), base, 0)


def render_page(*, invested_value: float, is_viewer: bool, on_back) -> None:
    """The full Cash activity page."""
    base = base_currency()
    entries = cash.load_ledger()
    s = cash.summary(entries, invested_value)

    if st.button("← Back to Positions", key="back_cash", type="tertiary"):
        on_back()
    with st.container(key="pf_page_title_cash", horizontal=True, vertical_alignment="center",
                      horizontal_alignment="distribute"):
        with st.container(width="content"):
            st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Cash activity</div>',
                        unsafe_allow_html=True)
            st.caption(f"Every movement in this portfolio's cash, converted to {base}. "
                       "The balance is the running sum of the ledger.")
        with st.container(horizontal=True, gap="small", width="content", vertical_alignment="center"):
            if is_viewer:
                st.markdown('<span style="font-size:11px;font-family:var(--uv-mono);padding:4px 9px;'
                            'border-radius:6px;border:0.5px solid var(--line);color:var(--muted);'
                            'white-space:nowrap;">Viewer · read-only</span>', unsafe_allow_html=True,
                            width="content")
            st.download_button("Export CSV", data=cash.export_csv(entries),
                               file_name=f"uvalu-cash-activity-{base}.csv", mime="text/csv",
                               key="cash_export", icon=":material/download:", disabled=not entries)
            if not is_viewer:
                if st.button("Add transaction", key="btn_add_cash", type="primary", icon=":material/add:"):
                    cash_transaction_dialog("Deposit")

    with st.container(key="pf_cash_tiles"):
        _t = st.columns(5)
        with _t[0]:
            kpi_card("Cash balance", cash.money(s["balance"], base, 0),
                     sub=f"{s['cash_pct']:.1f}% of total portfolio value", icon="cash")
        with _t[1]:
            kpi_card("Net deposits", _signed0(s["net_deposits"], base), sub="deposits − withdrawals", icon="wallet")
        with _t[2]:
            kpi_card("Trade flow", _signed0(s["trade_flow"], base), sub="sells − buys, incl. fees", icon="trend")
        with _t[3]:
            kpi_card("Income", _signed0(s["income"], base), sub="net dividends + interest", icon="coin",
                     value_color="var(--mint)")
        with _t[4]:
            kpi_card("Fees & corrections", _signed0(s["fees_corrections"], base),
                     sub=f"excl. opening balance · {s['corrections']} corrections", icon="target")

    if s["negative"]:
        st.warning("The running balance dips below zero somewhere in this ledger — usually after a dividend "
                   "was edited or deleted. Record a deposit or an adjustment on that date to correct it.",
                   icon=":material/warning:")

    with st.container(key="pf_card_cash_full", border=True):
        rows_all = list(reversed(cash.replay(entries)))
        with st.container(key="pf_cash_filter_row", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            group = st.pills("Filter", options=list(cash.FILTER_GROUPS.keys()), default="All",
                             selection_mode="single", key="cash_filter", label_visibility="collapsed") or "All"
            rows = cash.filter_rows(rows_all, group)
            st.markdown(f'<span style="font-size:11.5px;color:var(--faint);font-family:var(--uv-mono);'
                        f'white-space:nowrap;">{len(rows)} of {len(rows_all)} entries</span>',
                        unsafe_allow_html=True, width="content")
        if not rows_all:
            st.caption("No cash entries yet. Record a deposit, or an Adjustment to set an opening balance. "
                       "Buys never wait for cash: a shortfall is covered by an automatic top-up deposit.")
        elif not rows:
            st.caption("No entries of this type.")
        else:
            show_all = st.session_state.get("_cash_show_all", False)
            shown = rows if show_all else rows[:_PAGE_ROWS]
            st.markdown(cash_ledger_table_html(shown, base), unsafe_allow_html=True)
            if len(rows) > len(shown):
                if st.button(f"Show all {len(rows)} entries", key="cash_show_all", type="tertiary"):
                    st.session_state["_cash_show_all"] = True
                    st.rerun()

    st.caption(f"Entries can be made in any currency and are converted to {base} at the ECB reference rate for "
               "the transaction date (frankfurter.dev), stored with the entry. When no rate is available the "
               "rate is entered manually and flagged. Buy/sell trades and received dividend payments post "
               "automatically; a buy the balance can't cover adds a linked top-up deposit so the balance never "
               "goes below zero.")


def dashboard_cash_tile_values(invested_value: float) -> dict:
    """Balance / % for the Dashboard KPI strip and Risk banner."""
    s = cash.summary(cash.load_ledger(), invested_value)
    s["base"] = base_currency()
    s["chip_style"] = MINT_CHIP_STYLE
    return s

