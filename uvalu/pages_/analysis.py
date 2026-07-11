"""Analysis page — full-page stock deep dive, reached from the drawer's
"View full analysis" link (uvalu/drawer.py). Ticker is passed via
st.session_state["_analysis_ticker"], set right before st.switch_page()."""
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

from portfolio import load_portfolio, load_manual_tickers
from settings import load_shared_settings, ALL_EXCHANGES
from uvalu import nav as nav_registry
from uvalu.data import _load_all_screener_data, _cache_version
from uvalu.components import (signal_badge_for_decision, signal_badge_html,
                              fair_value_ladder, sub_score_bar_html)
from uvalu.formatting import fmt_eur as _fmt_eur
from uvalu.runtime import theme_colors
from uvalu.ui import _CHART_CONFIG


def _fv(row, field, fmt=None):
    v = row.get(field)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return fmt(v) if fmt else str(v)


def render() -> None:
    ticker = st.session_state.get("_analysis_ticker")

    _dash_page = nav_registry.pages.get("dashboard")
    if _dash_page is not None and st.button("← Back to dashboard", key="an_back", type="tertiary"):
        st.switch_page(_dash_page)

    if not ticker:
        st.info("No stock selected. Open a stock from any table (Dashboard, Screener, "
                "Watchlist, Portfolio, Risk) to view its full analysis here.")
        return

    _settings = load_shared_settings()
    _enabled  = tuple(_settings.get("enabled_exchanges", ALL_EXCHANGES))
    _manual_tickers_map = load_manual_tickers()
    _dfs = _load_all_screener_data(
        _cache_version(), _enabled, tuple(_manual_tickers_map.keys()), tuple(_manual_tickers_map.values()))
    all_df = pd.concat(_dfs, ignore_index=True)
    _match = all_df[all_df["Ticker"] == ticker]
    if _match.empty:
        st.warning(f"No data found for **{ticker}**.")
        return
    row = _match.iloc[0]

    # ── Header ────────────────────────────────────────────────────────────────
    kind, label = signal_badge_for_decision(str(row.get("Decision", "")), veto=bool(row.get("veto")))
    _score = row.get("Value Score")
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f"## `{ticker}`")
            st.markdown(signal_badge_html(kind, label), unsafe_allow_html=True)
        with st.container(horizontal_alignment="right"):
            st.metric("Composite score", f"{_score:.0f}" if pd.notna(_score) else "—")
    st.caption(f"{row.get('Name', '—')} · {row.get('sector') or '—'} · {row.get('country') or '—'}")

    # ── 4-card hero ───────────────────────────────────────────────────────────
    _pf = load_portfolio()
    _held_row = None
    if _pf is not None and not _pf.empty and "ticker" in _pf.columns:
        _m = _pf[_pf["ticker"] == ticker]
        if not _m.empty:
            _held_row = _m.iloc[0]
    _held_str = (f"{_held_row.get('shares', 0):.0f} shares" if _held_row is not None else "Not held")

    _h1, _h2, _h3, _h4 = st.columns(4)
    with _h1:
        st.caption("Current price")
        st.markdown(f"### {_fv(row, 'Price', _fmt_eur)}")
    with _h2:
        st.caption("Composite fair value")
        st.markdown(f"### {_fv(row, 'fair_value', _fmt_eur)}")
    with _h3:
        st.caption("Margin of safety")
        st.markdown(f"### {_fv(row, 'MoS %', lambda v: f'{v:+.1f}%')}")
    with _h4:
        st.caption("Your position")
        st.markdown(f"### {_held_str}")

    if row.get("veto"):
        st.error("**Hard veto active** — this stock is excluded from BUY scoring "
                 "regardless of its composite score (excessive leverage, negative free "
                 "cash flow, or an at-risk dividend with weak coverage).")

    # ── Price vs fair value chart ─────────────────────────────────────────────
    _C = theme_colors()
    with st.spinner("Loading price history…"):
        try:
            _hist = yf.Ticker(ticker).history(period="1y")
        except Exception:
            _hist = pd.DataFrame()
    if not _hist.empty:
        _hist.index = pd.to_datetime(_hist.index).tz_localize(None)
        _fig = go.Figure()
        _fig.add_trace(go.Scatter(
            x=_hist.index, y=_hist["Close"], mode="lines", name="Price",
            line=dict(color="#1DD6A4", width=2),
            fill="tozeroy", fillcolor="rgba(29,214,164,0.07)",
        ))
        _fv_val = row.get("fair_value")
        if pd.notna(_fv_val):
            _fig.add_hline(y=float(_fv_val), line=dict(color="#5B8FA8", width=1.5, dash="dash"),
                          annotation_text=f"Fair value {_fmt_eur(float(_fv_val))}",
                          annotation_font=dict(color=_C.axis, size=11))
        _fig.update_layout(
            margin=dict(l=0, r=0, t=8, b=0), hovermode="x unified",
            yaxis=dict(tickprefix="€", tickfont=dict(color=_C.axis), gridcolor=_C.grid),
            xaxis=dict(showgrid=False, tickfont=dict(color=_C.axis)),
            font=dict(color=_C.axis), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(_fig, width="stretch", height=260, config=_CHART_CONFIG)

    # ── Sub-scores | six-model fair value ─────────────────────────────────────
    _col1, _col2 = st.columns(2)
    with _col1:
        st.markdown("##### Signal sub-scores")
        st.caption("Weighted components of the composite score.")
        for label_, field in [("Margin of safety", "Sub MoS"), ("Risk (inverted)", "Sub Risk"),
                              ("Quality", "Sub Quality"), ("Momentum", "Sub Momentum"),
                              ("Dividend", "Sub Dividend")]:
            v = row.get(field)
            if pd.notna(v):
                st.markdown(sub_score_bar_html(label_, float(v)), unsafe_allow_html=True)
    with _col2:
        st.markdown("##### Six-model fair value")
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

    # ── Financials & valuation | hard-veto checks ─────────────────────────────
    _col3, _col4 = st.columns(2)
    with _col3:
        st.markdown("##### Financials & valuation")
        st.markdown("\n".join([
            "| | |", "|:--|--:|",
            f"| P/E | {_fv(row, 'trailingPE', lambda v: f'{v:.1f}×')} |",
            f"| P/B | {_fv(row, 'priceToBook', lambda v: f'{v:.2f}×')} |",
            f"| EV/EBITDA | {_fv(row, 'enterpriseToEbitda', lambda v: f'{v:.1f}×')} |",
            f"| ROE | {_fv(row, 'returnOnEquity', lambda v: f'{v*100:.1f}%')} |",
            f"| ROA | {_fv(row, 'returnOnAssets', lambda v: f'{v*100:.1f}%')} |",
            f"| Operating margin | {_fv(row, 'operatingMargins', lambda v: f'{v*100:.1f}%')} |",
            f"| Debt / equity | {_fv(row, 'debtToEquity', lambda v: f'{v:.1f}')} |",
            f"| Dividend yield | {_fv(row, 'dividendYield', lambda v: f'{v*100:.2f}%')} |",
            f"| Revenue growth | {_fv(row, 'revenueGrowth', lambda v: f'{v*100:+.1f}%')} |",
        ]), unsafe_allow_html=True)
    with _col4:
        st.markdown("##### Hard-veto checks")
        de = row.get("debtToEquity"); fcf = row.get("freeCashflow")
        div_flag = row.get("Div Flag"); coverage = row.get("dividendCoverage")
        _checks = [
            ("Debt / equity ≤ 500%", not (pd.notna(de) and de > 500),
             f"{_fv(row, 'debtToEquity', lambda v: f'{v:.0f}%')} today."),
            ("Free cash flow ≥ €0", not (pd.notna(fcf) and fcf < 0),
             f"{_fv(row, 'freeCashflow', lambda v: _fmt_eur(v))} trailing."),
            ("Dividend not flagged at risk", div_flag != "At Risk",
             f"Dividend sustainability flag: {div_flag or '—'}."),
            ("Dividend coverage ≥ 1.0×", not (pd.notna(coverage) and coverage < 1.0),
             f"{_fv(row, 'dividendCoverage', lambda v: f'{v:.2f}×')} coverage."),
        ]
        for check_label, passed, note in _checks:
            icon = "✓" if passed else "✗"
            color = "var(--up-txt, #0F6E56)" if passed else "var(--down-txt, #A32D2D)"
            st.markdown(
                f'<div style="display:flex;gap:8px;margin-bottom:8px;">'
                f'<span style="color:{color};font-weight:600;">{icon}</span>'
                f'<div><div style="font-size:13px;">{check_label}</div>'
                f'<div style="font-size:11px;color:var(--muted,#5F5E5A);">{note}</div></div></div>',
                unsafe_allow_html=True,
            )

    # ── Value thesis (derived from real computed fields only) ────────────────
    st.markdown("##### Value thesis")
    _sub_fields = {"Margin of safety": row.get("Sub MoS"), "Risk": row.get("Sub Risk"),
                  "Quality": row.get("Sub Quality"), "Momentum": row.get("Sub Momentum"),
                  "Dividend": row.get("Sub Dividend")}
    _valid_subs = {k: v for k, v in _sub_fields.items() if pd.notna(v)}
    _thesis = [f"{row.get('Name', ticker)} trades at {_fv(row, 'Price', _fmt_eur)} against a "
              f"composite fair value of {_fv(row, 'fair_value', _fmt_eur)} "
              f"({_fv(row, 'MoS %', lambda v: f'{v:+.1f}%')} margin of safety)."]
    if _valid_subs:
        _best = max(_valid_subs, key=_valid_subs.get)
        _worst = min(_valid_subs, key=_valid_subs.get)
        if _best != _worst:
            _thesis.append(f"Scores highest on {_best.lower()} ({_valid_subs[_best]:.0f}/100) "
                           f"and weakest on {_worst.lower()} ({_valid_subs[_worst]:.0f}/100).")
    st.caption(" ".join(_thesis))
