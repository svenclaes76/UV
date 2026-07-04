"""The shared 4-tab stock detail dialog (opened from every stock table)."""
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import streamlit as st

from portfolio import save_watchlist, load_watchlist, load_manual_tickers, save_manual_tickers
from uvalu.formatting import fmt_eur as _fmt_eur
from uvalu.runtime import theme_colors
from uvalu.ui import _CHART_CONFIG


@st.dialog("Stock details", width="large")
def _dlg_stock_detail(row: "pd.Series", pf_context: dict | None = None) -> None:
    """4-tab stock detail modal. Sizes to content; scrolls natively."""
    # Resolve per-run state locally (module was split out of app.py)
    _C = theme_colors()
    _c_axis, _c_grid, _c_invested = _C.axis, _C.grid, _C.invested
    watchlist = load_watchlist()
    st.markdown("""
<style>
/* ── Hide redundant "Stock details" title ─────────────────────── */
[data-testid="stDialog"] div[role="dialog"] > div:first-child {
display: none !important;
}

/* ── Fixed width (prevents tabs from resizing the dialog);
     min-height keeps tab switches from collapsing short tabs;
     position/backdrop/colours come from the native theme ── */
[data-testid="stDialog"] div[role="dialog"] {
width: 860px !important;
max-width: calc(100vw - 2rem) !important;
min-height: 600px !important;
}
/* ── Remove default top padding inside tab panels ─────────────── */
[data-testid="stDialog"] div[role="tabpanel"] > div:first-child {
padding-top: 0 !important;
}

/* ── Compact borderless key/value markdown tables inside dialog ── */
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] table {
width: 100% !important;
table-layout: fixed !important;
font-size: 12px;
border: none !important;
margin-top: 14px;
}
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] table th,
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] table td {
padding: 3px 0;
overflow-wrap: break-word;
border: none !important;
background: transparent !important;
}
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] table th {
border-bottom: 1px solid rgba(128,128,128,0.25) !important;
white-space: nowrap;
overflow: visible;
font-size: 0.875rem;   /* match st.caption ("Signals" label) */
font-weight: 400;
opacity: 0.6;
}
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] table td:first-child {
opacity: 0.55;
}
/* ── Equal-width severity badges so signal text aligns ── */
[data-testid="stDialog"] span.stMarkdownBadge {
min-width: 46px !important;
text-align: center !important;
}
/* ── Close (×) button — force visible in dark mode ─────── */
[data-testid="stDialog"] button[aria-label="Close"] {
color: inherit !important;
opacity: 0.7;
}
[data-testid="stDialog"] button[aria-label="Close"]:hover {
opacity: 1;
}
</style>""", unsafe_allow_html=True)

    decision = str(row.get("Decision", ""))
    score    = row.get("Value Score")
    badge_color = {
        "Strong Buy": "green",
        "Monitor":    "orange",
        "Avoid":      "red",
    }.get(decision, "red")
    badge_label = {
        "Strong Buy": "BUY",
        "Monitor":    "MONITOR",
        "Avoid":      "AVOID",
    }.get(decision, decision.upper() if decision else "—")
    if row.get("veto"):
        badge_color, badge_label = "gray", "VETO"

    score_str = f"{score:.1f}%" if pd.notna(score) else "—"

    # Height of the content block above Signals — identical in every tab so
    # the Signals section always starts at the same vertical position.
    _DLG_TOP_H = 260

    def _fv(field, fmt=None):
        v = row.get(field)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        return fmt(v) if fmt else str(v)

    def _kv_table(label, rows):
        """Render a section label + label/value pairs as a markdown table."""
        st.markdown("\n".join(
            [f"| {label} |  |", "|:--|--:|"]
            + [f"| {lbl} | {val} |" for lbl, val in rows]
        ))

    # ── Header: company name · ticker · decision badge · watchlist star ──
    _dlg_ticker   = str(row.get("Ticker", ""))
    _in_watchlist = _dlg_ticker in watchlist
    _star_lbl  = "★" if _in_watchlist else "☆"
    _star_help = "Remove from watchlist" if _in_watchlist else "Add to watchlist"
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f"#### {row.get('Name', '—')} :gray[`{_dlg_ticker}`]")
        st.markdown(f":{badge_color}-badge[{badge_label}]")
        if st.button(_star_lbl, key="dlg_star", help=_star_help, type="tertiary"):
            save_watchlist((watchlist - {_dlg_ticker}) if _in_watchlist else (watchlist | {_dlg_ticker}))
            if _in_watchlist:
                _mt = load_manual_tickers()
                if _dlg_ticker in _mt:
                    del _mt[_dlg_ticker]
                    save_manual_tickers(_mt)
            st.session_state["_dlg_star_rerun"] = True
            st.rerun()

    def _render_signals(tips) -> None:
        if not tips:
            return
        _badges = {"warn": ":red-badge[HIGH]", "caution": ":orange-badge[NOTE]",
                   "ok": ":green-badge[OK]", "neutral": ":gray-badge[INFO]"}
        st.caption("Signals")
        st.caption("  \n".join(
            f"{_badges.get(sev, _badges['neutral'])} {tip}" for sev, tip in tips
        ))

    _tab_today, _tab_hist, _tab_risk, _tab_val = st.tabs(
        ["Snapshot", "Price History", "Risk & Fit", "Model Estimates"]
    )

    # ── Tab 1: Snapshot ───────────────────────────────────────────────────
    with _tab_today:
        _dps = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
        _dps_str = f"€{_dps:.2f}" if _dps and pd.notna(_dps) else "—"

        # Fixed-height block so Signals starts at the same y in every tab
        with st.container(height=_DLG_TOP_H, border=False):
            _snap_c1, _snap_c2, _snap_c3 = st.columns(3, gap="medium")
            with _snap_c1:
                _kv_table("Valuation", [
                    ("Price",       _fv("Price",      _fmt_eur)),
                    ("Fair value",  _fv("fair_value", _fmt_eur)),
                    ("MoS",         _fv("MoS %",      lambda v: f"{v:+.1f}%")),
                    ("Exp. return", _fv("TER %",      lambda v: f"{v:+.1f}%")),
                    ("Score",       score_str),
                ])
            with _snap_c2:
                _kv_table("Quality", [
                    ("P/E",         _fv("trailingPE",        lambda v: f"{v:.1f}×")),
                    ("P/B",         _fv("priceToBook",        lambda v: f"{v:.2f}×")),
                    ("EV/EBITDA",   _fv("enterpriseToEbitda", lambda v: f"{v:.1f}×")),
                    ("ROE",         _fv("returnOnEquity",     lambda v: f"{v*100:.1f}%")),
                    ("ROA",         _fv("returnOnAssets",     lambda v: f"{v*100:.1f}%")),
                    ("Op margin",   _fv("operatingMargins",   lambda v: f"{v*100:.1f}%")),
                ])
            with _snap_c3:
                _kv_table("Dividends & growth", [
                    ("DPS",         _dps_str),
                    ("Yield",       _fv("dividendYield",  lambda v: f"{v*100:.2f}%")),
                    ("Payout",      _fv("payoutRatio",    lambda v: f"{v*100:.1f}%")),
                    ("Ex-div",      _fv("exDividendDate")),
                    ("EPS growth",  _fv("earningsGrowth", lambda v: f"{v*100:+.1f}%")),
                    ("Rev growth",  _fv("revenueGrowth",  lambda v: f"{v*100:+.1f}%")),
                ])
        # ── Snapshot signals ──────────────────────────────────────────────
        _snap_tips = []
        _sc_v = row.get("Value Score"); _mos_v = row.get("MoS %"); _fv_v = row.get("fair_value")
        _eg_v = row.get("earningsGrowth"); _rg_v = row.get("revenueGrowth")
        _dy_v = row.get("dividendYield")
        if pd.notna(_sc_v):
            sc = float(_sc_v)
            if sc >= 70:   _snap_tips.append(("ok",      f"Score {sc:.1f} — strong buy signal across valuation and quality criteria."))
            elif sc >= 40: _snap_tips.append(("neutral",  f"Score {sc:.1f} — monitor; does not yet meet the buy threshold."))
            else:          _snap_tips.append(("warn",     f"Score {sc:.1f} — below buy threshold; review fundamentals before investing."))
        if pd.notna(_mos_v) and pd.notna(_fv_v):
            m = float(_mos_v)
            if m >= 30:    _snap_tips.append(("ok",      f"Margin of safety {m:+.1f}% — significant discount to fair value {_fmt_eur(float(_fv_v))}."))
            elif m >= 10:  _snap_tips.append(("neutral",  f"Margin of safety {m:+.1f}% — modest discount; limited downside buffer."))
            elif m >= 0:   _snap_tips.append(("caution",  f"Stock near fair value ({m:+.1f}%) — little buffer if estimates prove optimistic."))
            else:          _snap_tips.append(("warn",     f"Stock {abs(m):.1f}% above fair value {_fmt_eur(float(_fv_v))} — consider waiting for a pullback."))
        if pd.notna(_eg_v):
            g = float(_eg_v) * 100
            if g >= 15:    _snap_tips.append(("ok",      f"EPS growth {g:+.1f}% — strong earnings momentum."))
            elif g >= 0:   _snap_tips.append(("neutral",  f"EPS growth {g:+.1f}% — modest positive trend."))
            else:          _snap_tips.append(("caution",  f"EPS growth {g:+.1f}% — earnings contracting; verify if temporary."))
        if pd.notna(_rg_v):
            g = float(_rg_v) * 100
            if g >= 10:    _snap_tips.append(("ok",      f"Revenue growth {g:+.1f}% — healthy top-line expansion."))
            elif g >= 0:   _snap_tips.append(("neutral",  f"Revenue growth {g:+.1f}% — slow but positive."))
            else:          _snap_tips.append(("caution",  f"Revenue declining {g:+.1f}% — assess competitive position."))
        if pd.notna(_dy_v) and float(_dy_v) > 0:
            dy = float(_dy_v) * 100
            if dy >= 4:    _snap_tips.append(("ok",      f"Dividend yield {dy:.2f}% — attractive income level."))
            elif dy >= 2:  _snap_tips.append(("neutral",  f"Dividend yield {dy:.2f}% — moderate income."))
        _render_signals(_snap_tips)

    # ── Tab 2: Price history ───────────────────────────────────────────────
    with _tab_hist:
        _fv_val = row.get("fair_value")
        _at_val = row.get("targetMeanPrice")
        _price  = row.get("Price")

        import yfinance as yf
        _ticker_sym = str(row.get("Ticker", ""))
        with st.container(height=_DLG_TOP_H, border=False):
            with st.spinner("Loading price history…"):
                try:
                    _hist = yf.Ticker(_ticker_sym).history(period="2y")
                except Exception:
                    _hist = pd.DataFrame()
            if _hist.empty:
                st.caption("No price history available.")
            else:
                _hist.index = pd.to_datetime(_hist.index).tz_localize(None)
                _fig_h = go.Figure()
                _fig_h.add_trace(go.Scatter(
                    x=_hist.index, y=_hist["Close"],
                    mode="lines", name="Price",
                    line=dict(color="#1DD6A4", width=2),
                    fill="tozeroy", fillcolor="rgba(29,214,164,0.07)",
                ))
                if pd.notna(_fv_val):
                    _fig_h.add_hline(
                        y=float(_fv_val),
                        line=dict(color="#5B8FA8", width=1.5, dash="dash"),
                        annotation_text=f"Fair value {_fmt_eur(float(_fv_val))}",
                        annotation_position="top left",
                        annotation_font=dict(color=_c_axis, size=11),
                    )
                if pd.notna(_at_val):
                    _fig_h.add_hline(
                        y=float(_at_val),
                        line=dict(color=_c_invested, width=1.5, dash="dot"),
                        annotation_text=f"Analyst {_fmt_eur(float(_at_val))}",
                        annotation_position="bottom left",
                        annotation_font=dict(color=_c_axis, size=11),
                    )
                _fig_h.update_layout(
                    margin=dict(l=0, r=0, t=8, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                xanchor="left", x=0, font=dict(color=_c_axis)),
                    yaxis=dict(tickprefix="€", tickformat=",.2f",
                               tickfont=dict(color=_c_axis), gridcolor=_c_grid),
                    xaxis=dict(showgrid=False, tickfont=dict(color=_c_axis)),
                    hovermode="x unified",
                    font=dict(color=_c_axis),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(_fig_h, width="stretch", height=220, config=_CHART_CONFIG)
        # ── Price history signals ─────────────────────────────────────────
        if not _hist.empty:
            _hist_tips = []
            if pd.notna(_price) and pd.notna(_fv_val):
                _gap = (float(_fv_val) - float(_price)) / float(_price) * 100
                if _gap >= 20:   _hist_tips.append(("ok",      f"Price {_fmt_eur(float(_price))} is {_gap:.1f}% below fair value {_fmt_eur(float(_fv_val))} — significant upside potential."))
                elif _gap >= 5:  _hist_tips.append(("neutral",  f"Price {_fmt_eur(float(_price))} is {_gap:.1f}% below fair value — modest upside."))
                elif _gap >= -5: _hist_tips.append(("caution",  f"Price is near fair value {_fmt_eur(float(_fv_val))} — limited margin of safety."))
                else:            _hist_tips.append(("warn",     f"Price {_fmt_eur(float(_price))} is {abs(_gap):.1f}% above fair value {_fmt_eur(float(_fv_val))} — overvalued vs model."))
            if pd.notna(_price) and pd.notna(_at_val):
                _at_gap = (float(_at_val) - float(_price)) / float(_price) * 100
                if _at_gap >= 15:  _hist_tips.append(("ok",     f"Analyst target {_fmt_eur(float(_at_val))} implies {_at_gap:.1f}% upside from current price."))
                elif _at_gap >= 5: _hist_tips.append(("neutral", f"Analyst target {_fmt_eur(float(_at_val))} implies {_at_gap:.1f}% upside."))
                elif _at_gap >= 0: _hist_tips.append(("caution", f"Analyst target {_fmt_eur(float(_at_val))} is near current price — limited consensus upside."))
                else:              _hist_tips.append(("warn",    f"Analyst target {_fmt_eur(float(_at_val))} is {abs(_at_gap):.1f}% below current price — analysts see downside."))
            _ret_1m = (_hist["Close"].iloc[-1] / _hist["Close"].iloc[max(-21, -len(_hist))] - 1) * 100
            _ret_6m = (_hist["Close"].iloc[-1] / _hist["Close"].iloc[max(-126, -len(_hist))] - 1) * 100
            if _ret_1m >= 5:   _hist_tips.append(("ok",     f"Up {_ret_1m:.1f}% over the past month — strong recent momentum."))
            elif _ret_1m <= -5:_hist_tips.append(("caution", f"Down {abs(_ret_1m):.1f}% over the past month — near-term weakness."))
            if _ret_6m >= 20:  _hist_tips.append(("ok",     f"Up {_ret_6m:.1f}% over 6 months — sustained uptrend."))
            elif _ret_6m <= -20:_hist_tips.append(("warn",   f"Down {abs(_ret_6m):.1f}% over 6 months — prolonged decline; check for structural issues."))
            _render_signals(_hist_tips)

    # ── Tab 3: Risk ───────────────────────────────────────────────────────
    with _tab_risk:
        _has_pf = pf_context and pf_context.get("total", 0) > 0

        # ── Compute portfolio fit data first ──────────────────────────────
        _pf_tips: list[tuple[str, str]] = []
        _fit_rows: list[tuple[str, str]] = []
        if _has_pf:
            _pf_sector  = row.get("sector")
            _pf_country = row.get("country")
            _sw = pf_context["sector_weights"]
            _cw = pf_context["country_weights"]

            _fit_badges = {"ok": " :green-badge[OK]", "caution": " :orange-badge[NOTE]",
                           "warn": " :red-badge[HIGH]", "neutral": ""}

            _sec_w = float(_sw.get(_pf_sector, 0) or 0) if _pf_sector else 0.0
            if not _pf_sector:
                _sec_sev = "neutral"; _sec_val = "Unknown"
                _sec_tip = "Sector data not available for this stock."
            elif _sec_w > 0.30:
                _sec_sev = "warn";    _sec_val = _pf_sector
                _sec_tip = f"Your portfolio already has {_sec_w:.0%} in {_pf_sector}. Adding this stock increases sector concentration significantly."
            elif _sec_w > 0.15:
                _sec_sev = "caution"; _sec_val = _pf_sector
                _sec_tip = f"{_pf_sector} is at {_sec_w:.0%} of your portfolio. Consider whether further exposure fits your targets."
            elif _sec_w > 0:
                _sec_sev = "ok";      _sec_val = _pf_sector
                _sec_tip = f"Low {_pf_sector} exposure ({_sec_w:.0%}) — this stock adds sector diversification."
            else:
                _sec_sev = "neutral"; _sec_val = _pf_sector
                _sec_tip = f"{_pf_sector} is not yet in your portfolio — this adds a new sector."

            _cnt_w = float(_cw.get(_pf_country, 0) or 0) if _pf_country else 0.0
            if not _pf_country:
                _cnt_sev = "neutral"; _cnt_val = "Unknown"
                _cnt_tip = "Country data not available for this stock."
            elif _cnt_w > 0.50:
                _cnt_sev = "warn";    _cnt_val = _pf_country
                _cnt_tip = f"Your portfolio is already {_cnt_w:.0%} in {_pf_country}. Adding more increases geographic concentration."
            elif _cnt_w > 0.30:
                _cnt_sev = "caution"; _cnt_val = _pf_country
                _cnt_tip = f"{_pf_country} already represents {_cnt_w:.0%} of your portfolio. Monitor geographic balance."
            elif _cnt_w > 0:
                _cnt_sev = "ok";      _cnt_val = _pf_country
                _cnt_tip = f"Low {_pf_country} exposure ({_cnt_w:.0%}) — adding this stock improves geographic diversification."
            else:
                _cnt_sev = "neutral"; _cnt_val = _pf_country
                _cnt_tip = f"{_pf_country} is not yet in your portfolio — this adds new geographic exposure."

            _fit_rows = [
                ("Sector",  f"{_sec_val}{_fit_badges.get(_sec_sev, '')}"),
                ("Country", f"{_cnt_val}{_fit_badges.get(_cnt_sev, '')}"),
            ]
            _pf_tips = [(_sec_sev, _sec_tip), (_cnt_sev, _cnt_tip)]

        with st.container(height=_DLG_TOP_H, border=False):
            _rf_c1, _rf_c2 = st.columns(2, gap="large")
            with _rf_c1:
                _kv_table("Risk & size", [
                    ("Beta",              _fv("beta",             lambda v: f"{v:.2f}")),
                    ("Debt / equity",     _fv("debtToEquity",     lambda v: f"{v:.1f}")),
                    ("Current ratio",     _fv("currentRatio",     lambda v: f"{v:.2f}")),
                    ("Interest coverage", _fv("interestCoverage", lambda v: f"{v:.1f}×")),
                    ("Risk score",        _fv("Risk Score",       lambda v: f"{v:.1f} / 10")),
                ])
            with _rf_c2:
                if _fit_rows:
                    _kv_table("Portfolio fit", _fit_rows)

        # ── Signals — right column ────────────────────────────────────────
        _beta_v = row.get("beta");  _de_v = row.get("debtToEquity");  _rs_v = row.get("Risk Score")
        _risk_tips: list[tuple[str, str]] = []
        if pd.notna(_beta_v):
            _b = float(_beta_v)
            if _b < 0.5:    _risk_tips.append(("neutral", f"Beta {_b:.2f} — low volatility."))
            elif _b < 1.0:  _risk_tips.append(("neutral", f"Beta {_b:.2f} — below market."))
            elif _b < 1.3:  _risk_tips.append(("neutral", f"Beta {_b:.2f} — in line with market."))
            else:           _risk_tips.append(("caution", f"Beta {_b:.2f} — high volatility."))
        if pd.notna(_de_v):
            _de = float(_de_v)
            if _de > 5:    _risk_tips.append(("caution", f"D/E {_de:.1f} — high leverage."))
            elif _de > 2:  _risk_tips.append(("neutral", f"D/E {_de:.1f} — moderate leverage."))
            else:          _risk_tips.append(("neutral", f"D/E {_de:.1f} — conservative."))
        if pd.notna(_rs_v):
            _rs = float(_rs_v)
            if _rs <= 3:   _risk_tips.append(("ok",      f"Risk score {_rs:.1f}/10 — low."))
            elif _rs <= 6: _risk_tips.append(("neutral", f"Risk score {_rs:.1f}/10 — moderate."))
            else:          _risk_tips.append(("warn",    f"Risk score {_rs:.1f}/10 — elevated."))

        _render_signals(_risk_tips + _pf_tips)


    # ── Tab 4: Valuation ──────────────────────────────────────────────────
    with _tab_val:
        _val_models = [
            ("Graham number",  "graham_number"),
            ("PE fair value",  "pe_fair_value"),
            ("DDM",            "ddm"),
            ("Analyst target", "targetMeanPrice"),
        ]
        _price = row.get("Price")
        _valid_models = [
            (lbl, float(row.get(field)))
            for lbl, field in _val_models
            if row.get(field) is not None and pd.notna(row.get(field))
        ]
        with st.container(height=_DLG_TOP_H, border=False):
            if _valid_models and pd.notna(_price):
                _vlabels = [lbl for lbl, _ in _valid_models]
                _vvalues = [val for _, val in _valid_models]
                _vcolors = ["#1DD6A4" if v > float(_price) else "#E05C5C" for v in _vvalues]
                _fig_v   = go.Figure()
                _fig_v.add_trace(go.Bar(
                    x=_vvalues, y=_vlabels, orientation="h",
                    marker_color=_vcolors,
                    text=[_fmt_eur(v) for v in _vvalues],
                    textposition="outside",
                    cliponaxis=False,
                ))
                _fig_v.add_vline(
                    x=float(_price),
                    line=dict(color=_c_axis, width=2),
                    annotation_text=f"Price {_fmt_eur(float(_price))}",
                    annotation_position="top",
                    annotation_font=dict(color=_c_axis, size=11),
                )
                _fig_v.update_layout(
                    margin=dict(l=0, r=80, t=28, b=8),
                    bargap=0.25,
                    xaxis=dict(tickprefix="€", tickformat=",.0f",
                               tickfont=dict(color=_c_axis), showgrid=False),
                    yaxis=dict(tickfont=dict(color=_c_axis), gridcolor=_c_grid),
                    font=dict(color=_c_axis),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(_fig_v, width="stretch", height=220, config=_CHART_CONFIG)
            else:
                st.caption("Not enough model data to render chart.")
        # ── Model signals ─────────────────────────────────────────────────
        _mdl_tips = []
        _mdl_price = row.get("Price")
        _mdl_all = [
            ("Graham number",  "graham_number"),
            ("PE fair value",  "pe_fair_value"),
            ("DDM",            "ddm"),
            ("Analyst target", "targetMeanPrice"),
        ]
        if pd.notna(_mdl_price):
            _mdl_valid = [(l, float(row.get(f))) for l, f in _mdl_all if row.get(f) is not None and pd.notna(row.get(f))]
            _n_above = sum(1 for _, v in _mdl_valid if v > float(_mdl_price))
            _n_total = len(_mdl_valid)
            if _n_total > 0:
                if _n_above == _n_total:
                    _mdl_tips.append(("ok",      f"All {_n_total} models above current price — broad consensus of undervaluation."))
                elif _n_above >= _n_total // 2 + 1:
                    _mdl_tips.append(("neutral",  f"{_n_above}/{_n_total} models above current price — majority suggests undervaluation."))
                elif _n_above > 0:
                    _mdl_tips.append(("caution",  f"Only {_n_above}/{_n_total} models above current price — mixed valuation signals."))
                else:
                    _mdl_tips.append(("warn",     f"No models above current price — all estimates suggest overvaluation."))
            for lbl, fld in _mdl_all:
                v = row.get(fld)
                if v is not None and pd.notna(v):
                    v = float(v); p = float(_mdl_price)
                    diff = (v - p) / p * 100
                    if diff >= 20:    _mdl_tips.append(("ok",     f"{lbl} {_fmt_eur(v)} — {diff:.1f}% above price."))
                    elif diff >= 5:   _mdl_tips.append(("neutral", f"{lbl} {_fmt_eur(v)} — {diff:.1f}% above price."))
                    elif diff >= -5:  _mdl_tips.append(("caution", f"{lbl} {_fmt_eur(v)} — near current price ({diff:+.1f}%)."))
                    else:             _mdl_tips.append(("warn",    f"{lbl} {_fmt_eur(v)} — {abs(diff):.1f}% below price."))
        _render_signals(_mdl_tips)
