"""Slide-in quick-preview panel for a single stock — the universal row-click
target across Screener/Watchlist/Portfolio/Risk/Dashboard tables. Replaces the
old centered uvalu/stock_dialog.py modal (retired).

Implemented as a restyled @st.dialog: Streamlit has no native right-edge
slide-in panel, so CSS pins the dialog to the right edge and narrows it,
while every existing row-click-to-dialog call site keeps working unchanged
(same (row, pf_context) call signature as the old _dlg_stock_detail).

Matches Uvalu.dc.html's "Detail drawer" section exactly: header with an X
close button (no watchlist star — this drawer is a pure quick-preview, not a
watchlist management surface), price/fair-value/MoS hero tiles, a veto
banner, the six-model fair-value ladder, a Position & metrics list that
varies by held/not-held state, and a primary "View full analysis" action.
"""
import pandas as pd
import streamlit as st

from portfolio import load_watchlist, load_portfolio
from uvalu import nav as nav_registry
from uvalu.components import (signal_badge_for_decision, signal_badge_html,
                              fair_value_ladder, veto_reason_str)
from uvalu.dialogs import add_position_dialog, sell_position_dialog
from uvalu.formatting import fmt_eur as _fmt_eur
from uvalu.runtime import current_user

_DRAWER_CSS = """
[data-testid="stDialog"] [role="dialog"] {
  position: fixed !important; top: 0 !important; right: 0 !important; left: auto !important;
  height: 100vh !important; max-height: 100vh !important;
  width: 452px !important; max-width: 92vw !important;
  border-radius: 0 !important; margin: 0 !important;
  overflow-y: auto !important;
  animation: uvDrawerIn 0.18s ease;
  /* Streamlit's dialog default background happens to equal --panel-2 in
     light mode, so the hero tiles' --panel-2 tint had zero contrast against
     it. The design pins the drawer's own background to --panel (white)
     specifically so the nested --panel-2 tiles read as visibly distinct
     cards — match that here. */
  background: var(--panel) !important;
}
@keyframes uvDrawerIn { from { transform: translateX(24px); opacity: 0; } to { transform: none; opacity: 1; } }
/* Two separate native-chrome elements to hide, replaced by our own header:
   the dialog's title (an <h2 slot="title"> — NOT the role="dialog"
   element's first child; that's actually the native close button. The
   role="dialog" element itself is a <section>, not a <div> — a `div[role=
   "dialog"]` type-qualified selector, or a `> div:first-child` positional
   one, silently matches nothing at all, confirmed live via the real DOM)
   and its native close button, which rendered almost exactly on top of our
   own "✕" button (aria-label="Close" is a stable target; its actual
   wrapper/position isn't). */
[data-testid="stDialog"] [role="dialog"] h2[slot="title"] { display: none !important; }
[data-testid="stDialog"] button[aria-label="Close"] { display: none !important; }
.st-key-drw_close button {
  width: 30px !important; height: 30px !important; min-height: 30px !important; padding: 0 !important;
  border-radius: 8px !important; border: 0.5px solid var(--line, rgba(13,31,60,0.1)) !important;
}
.st-key-drw_sell button { color: var(--down-txt, #A32D2D) !important; border-color: var(--down-txt, #A32D2D) !important; }
.st-key-drw_buy button  { color: var(--mint, #1DD6A4) !important; border-color: var(--mint, #1DD6A4) !important; }
"""


def _section_header(text: str) -> None:
    """Uppercase small-caps section label — matches Uvalu.dc.html's
    "Six-model fair value" / "Position & metrics" heading style exactly
    (distinct from Streamlit's plain st.caption, which isn't uppercase and
    has no letter-spacing)."""
    st.markdown(f'<div style="margin-top:20px;font-size:11px;letter-spacing:0.06em;'
               f'text-transform:uppercase;color:var(--faint);margin-bottom:8px;">{text}</div>',
               unsafe_allow_html=True)


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


def dispatch_pending_drawer_action() -> None:
    """Call once near the top of each page's render(), outside any dialog
    context — opens the Buy/Sell dialog the drawer's own buttons requested
    (see open_drawer's Buy/Sell handlers for why this two-step handoff is
    needed instead of calling the dialog directly)."""
    _pending = st.session_state.pop("_drw_action", None)
    if not _pending:
        return
    if _pending["kind"] == "buy":
        add_position_dialog(preset_ticker=_pending["ticker"], preset_name=_pending["name"],
                            preset_price=_pending["price"])
    elif _pending["kind"] == "sell":
        _pf = load_portfolio()
        if _pf is not None and not _pf.empty:
            sell_position_dialog(_pf, _pending["ticker"], preset_price=_pending["price"])


def _go_portfolio_edit(ticker: str) -> None:
    """Edit has no per-ticker dialog of its own here — it reuses Portfolio's
    own per-row edit dialog (uvalu/pages_/portfolio.py's
    _dlg_edit_open_position), which is defined inside that page's own
    render() closure and needs the row's DataFrame index, not just a
    ticker. Stash the target ticker + section via session_state and
    navigate there; portfolio.py's Open positions section checks for
    "_pf_edit_ticker" on load, resolves it to a row index, and opens the
    dialog itself. st.switch_page() works fine from inside an open
    @st.dialog (confirmed live — this contradicts an earlier, stale
    finding from before a Streamlit version bump)."""
    st.session_state["port_section"] = "open"
    st.session_state["_pf_edit_ticker"] = ticker
    _page = nav_registry.pages.get("portfolio")
    if _page is not None:
        st.switch_page(_page)


@st.dialog("Stock preview", width="small")
def open_drawer(row: "pd.Series", pf_context: dict | None = None) -> None:
    st.markdown(f"<style>{_DRAWER_CSS}</style>", unsafe_allow_html=True)

    ticker = str(row.get("Ticker", ""))
    kind, label = signal_badge_for_decision(str(row.get("Decision", "")), veto=bool(row.get("veto")))

    with st.container(horizontal=True, vertical_alignment="top", horizontal_alignment="distribute"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f'<span style="font-family:var(--uv-mono);font-size:18px;font-weight:500;">'
                       f'{ticker}</span>', unsafe_allow_html=True)
            st.markdown(signal_badge_html(kind, label), unsafe_allow_html=True)
        if st.button("✕", key="drw_close", type="tertiary", help="Close"):
            # @st.dialog bodies rerun as their own fragment — a plain widget
            # click alone just re-renders this same function unchanged, it
            # doesn't close the dialog. st.rerun() breaks out to a full-script
            # rerun; since nothing there re-invokes open_drawer() for this
            # ticker, the dialog stays closed. Same mechanism the old
            # watchlist-star handler used to force-close-then-reopen.
            st.rerun()
    st.markdown(f'<div style="padding-bottom:16px;border-bottom:0.5px solid var(--line);">'
               f'<span style="font-size:13px;color:var(--muted);">{row.get("Name", "—")} · {_fv(row, "sector")}</span></div>',
               unsafe_allow_html=True)

    # ── Hero: price / fair value / MoS — three bordered panel-2 tiles,
    # matching the mockup's nested-elevation card treatment (not plain
    # columns; a visible border on top of the background tint so they read
    # unambiguously as cards). ───────────────────────────────────────────────
    _mos = row.get("MoS %")
    _mos_color = ("var(--up-txt)" if pd.notna(_mos) and _mos >= 0 else "var(--down-txt)") if pd.notna(_mos) else "inherit"
    # Tighter side padding/gap/letter-spacing than a first pass at this (13px
    # 14px padding, 12px gap, 0.06em spacing) — "Margin of safety" wrapped to
    # 2 lines at 452px drawer width with those values, throwing off vertical
    # alignment between the 3 tiles' values. Confirmed via live DOM
    # measurement (scrollWidth vs clientWidth) that this combination is the
    # minimum squeeze needed to keep all 3 labels on one line.
    _tile = 'flex:1;background:var(--panel-2);border:0.5px solid var(--line);border-radius:10px;padding:13px 10px;'
    _label = 'font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:0.02em;white-space:nowrap;'
    st.markdown(
        f'<div style="display:flex;gap:8px;margin-top:16px;">'
        f'<div style="{_tile}">'
        f'<div style="{_label}">Price</div>'
        f'<div style="font-family:var(--uv-mono);font-size:21px;font-weight:500;margin-top:5px;">{_fv(row, "Price", _fmt_eur)}</div></div>'
        f'<div style="{_tile}">'
        f'<div style="{_label}">Fair value</div>'
        f'<div style="font-family:var(--uv-mono);font-size:21px;font-weight:500;margin-top:5px;color:var(--mint);">{_fv(row, "fair_value", _fmt_eur)}</div></div>'
        f'<div style="{_tile}">'
        f'<div style="{_label}">Margin of safety</div>'
        f'<div style="font-family:var(--uv-mono);font-size:21px;font-weight:500;margin-top:5px;color:{_mos_color};">{_fv(row, "MoS %", lambda v: f"{v:+.1f}%")}</div></div>'
        f'</div>', unsafe_allow_html=True)

    if row.get("veto"):
        st.markdown(
            f'<div style="margin-top:14px;background:var(--navy);border-radius:10px;padding:13px 15px;display:flex;gap:11px;align-items:flex-start;">'
            f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px;">'
            f'<path d="M12 9v4M12 17h.01M10.24 3.957l-8.422 14.06a1.9 1.9 0 0 0 1.636 2.983h16.844a1.9 1.9 0 0 0 1.636 -2.983l-8.422 -14.06a1.9 1.9 0 0 0 -3.276 0z"/></svg>'
            f'<div><div style="font-size:12.5px;font-weight:500;color:#fff;">Hard veto triggered</div>'
            f'<div style="font-size:12px;color:rgba(245,247,250,0.7);margin-top:3px;line-height:1.5;">{veto_reason_str(row)}.</div></div></div>',
            unsafe_allow_html=True)

    _section_header("Six-model fair value")
    _price = row.get("Price")
    if _price is not None and pd.notna(_price):
        fair_value_ladder(
            price=float(_price),
            # Labels match Uvalu.dc.html's model list ("Graham Number"/"P/E
            # fair value"/"EPV"/"Dividend discount"/.../"Analyst target") —
            # "Dividend discount" is this app's single-stage DDM (the
            # classic Gordon Growth dividend-discount model); the design's
            # 5th slot is "DCF", which this app doesn't compute, so that
            # slot keeps its own real model (2-stage DDM) rather than
            # mislabeling it as a DCF figure it isn't.
            models=[
                ("Graham Number",     row.get("graham_number")),
                ("P/E fair value",    row.get("pe_fair_value")),
                ("EPV",                row.get("epv")),
                ("Dividend discount",  row.get("ddm")),
                ("DDM 2-stage",       row.get("ddm_multistage")),
                ("Analyst Target",    row.get("targetMeanPrice")),
            ],
            composite=row.get("fair_value"),
            bar_width=96,
        )

    # ── Position & metrics — matches Uvalu.dc.html's rowsD builder exactly:
    # 4 always-shown fields, then either 3 held-position fields or a single
    # "not held" status row. ─────────────────────────────────────────────────
    _section_header("Position & metrics")
    _pf = load_portfolio()
    _held_row = None
    if _pf is not None and not _pf.empty and "ticker" in _pf.columns:
        _match = _pf[_pf["ticker"] == ticker]
        if not _match.empty:
            _held_row = _match.iloc[0]
    _held = _held_row is not None

    _veto = bool(row.get("veto"))
    _score = row.get("Value Score")
    _score_str = "excluded" if _veto else _fv(row, "Value Score", lambda v: f"{v:.0f} / 100")
    _score_color = "var(--down-txt)" if _veto else ("var(--mint)" if pd.notna(_score) else "inherit")
    _pe = row.get("trailingPE")
    _pe_str = f"{_pe:.1f}× · 15.0×" if pd.notna(_pe) else "—"
    _dy_str = _fv(row, "dividendYield", lambda v: f"{v*100:.1f}%")

    _rows = [
        ("Composite score", _score_str, _score_color),
        ("P/E · fair P/E", _pe_str, "inherit"),
        ("Dividend yield", _dy_str, "inherit"),
        ("Exchange", _fv(row, "Exchange"), "inherit"),
    ]
    if _held:
        _shares = _safe_float(_held_row.get("shares"))
        _position_value = _shares * _safe_float(row.get("Price"))
        _purchase_value = _held_row.get("purchase_value")
        _purchase_value = (float(_purchase_value) if _purchase_value is not None and pd.notna(_purchase_value)
                           else _shares * _safe_float(_held_row.get("purchase_price")))
        _pnl = _position_value - _purchase_value
        _pnl_pct = (_pnl / _purchase_value * 100) if _purchase_value else 0.0
        _rows += [
            ("Shares held", f"{_shares:,.0f}", "inherit"),
            ("Position value", f"€{_position_value:,.0f}", "inherit"),
            ("Unrealised P&L", f"{'+' if _pnl >= 0 else '-'}€{abs(_pnl):,.0f} ({_pnl_pct:+.1f}%)",
             "var(--up-txt)" if _pnl >= 0 else "var(--down-txt)"),
        ]
    else:
        _status = "Not held · watchlist" if ticker in load_watchlist() else "Not held"
        _rows.append(("Portfolio status", _status, "var(--muted)"))

    st.markdown("".join(
        f'<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:0.5px solid var(--line-2);">'
        f'<span style="font-size:12.5px;color:var(--muted);">{_label}</span>'
        f'<span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;color:{_color};">{_value}</span></div>'
        for _label, _value, _color in _rows
    ), unsafe_allow_html=True)
    st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)

    _is_viewer = current_user().is_viewer
    _vhelp = "Viewer role is read-only" if _is_viewer else None
    if _held:
        _act1, _act2, _act3 = st.columns([2, 1, 1])
        with _act1:
            if st.button("View full analysis", key="drw_analysis", width="stretch", type="primary"):
                _go_analysis(ticker)
        with _act2:
            if st.button("Edit", key="drw_edit", width="stretch", disabled=_is_viewer, help=_vhelp):
                _go_portfolio_edit(ticker)
        with _act3:
            if st.button("Close", key="drw_sell", width="stretch", disabled=_is_viewer, help=_vhelp):
                # Streamlit forbids nesting one @st.dialog inside another —
                # sell_position_dialog can't be called directly from here.
                # Stash the request and st.rerun() to close this dialog first;
                # dispatch_pending_drawer_action() (called at each page's
                # top level, outside any dialog) opens it on the next run.
                st.session_state["_drw_action"] = {"kind": "sell", "ticker": ticker,
                                                   "price": _safe_float(row.get("Price"))}
                st.rerun()
    else:
        _act1, _act2 = st.columns([2, 1])
        with _act1:
            if st.button("View full analysis", key="drw_analysis", width="stretch", type="primary"):
                _go_analysis(ticker)
        with _act2:
            if st.button("Add", key="drw_buy", width="stretch", disabled=_is_viewer, help=_vhelp):
                st.session_state["_drw_action"] = {"kind": "buy", "ticker": ticker,
                                                   "name": str(row.get("Name", "")),
                                                   "price": _safe_float(row.get("Price"))}
                st.rerun()
