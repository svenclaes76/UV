"""Portfolio risk page — composite score, concentration, VaR, factors, stress."""
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import risk as _risk_module
from portfolio import load_portfolio, load_sold
from screener import _load_cache
from settings import load_shared_settings, ALL_EXCHANGES
from uvalu.data import _load_all_screener_data, _cache_version, _fetch_live_data
from uvalu.runtime import theme_colors
from uvalu.drawer import open_drawer
from uvalu.ui import _DONUT_PALETTE, _row_select_table


def _risk_note(body: str) -> None:
    """Methodology note for risk page tabs — a popover so it never shifts the layout below it."""
    with st.popover("Methodology", icon=":material/info:"):
        st.markdown(body)


def _trigger_card(msg: str, kind: str = "hard", action: str | None = None) -> None:
    """Render a hard (act now) or soft (review) rebalancing trigger.

    When `action` is given, it's bundled as a second line in the same card so the
    issue and its recommended next step read as one unit instead of two lists.
    """
    label = "Act" if kind == "hard" else "Review"
    body = f"**{label}** — {msg}"
    if action:
        body += f"  \n↳ {action}"
    if kind == "hard":
        st.error(body, icon=":material/priority_high:")
    else:
        st.info(body, icon=":material/arrow_forward:")


_FACTOR_ACTIONS = {
    "Mkt-RF": "Reduce beta by adding cash or defensive/low-beta positions",
    "SMB":    "Rebalance small-cap vs large-cap mix toward target allocation",
    "HML":    "Balance value vs growth exposure across holdings",
    "RMW":    "Diversify profitability exposure — mix high- and low-margin businesses",
    "CMA":    "Balance conservative vs aggressive investment exposure",
    "WML":    "Reduce momentum concentration; add mean-reversion candidates",
}


def _factor_flag_action(msg: str) -> str | None:
    """Map a factor-exposure flag message to a concrete rebalancing action."""
    for name, action in _FACTOR_ACTIONS.items():
        if msg.startswith(f"High {name} loading") or msg.startswith(f"{name} explains"):
            return action
    return None


def render() -> None:
    # Per-run theme palette (module was split out of app.py)
    _C = theme_colors()
    _ui_effective_light = _C.effective_light
    _c_axis, _c_grid, _c_text, _c_surface = (_C.axis, _C.grid, _C.text, _C.surface)
    pf = load_portfolio()
    if pf is None or pf.empty:
        st.info("No portfolio loaded. Add positions in the Portfolio tab first.")
        st.stop()

    _risk_enabled  = tuple(load_shared_settings().get("enabled_exchanges", ALL_EXCHANGES))
    _risk_sold     = load_sold()
    _risk_sold_tickers = tuple(_risk_sold["ticker"].dropna().tolist()) if _risk_sold is not None and not _risk_sold.empty else ()
    _risk_sold_names   = tuple(_risk_sold["name"].dropna().tolist())   if _risk_sold is not None and not _risk_sold.empty else ()
    _risk_tickers  = tuple(pf["ticker"].tolist())
    _risk_names    = tuple(pf["name"].tolist())
    _risk_extra_tickers = tuple(dict.fromkeys(_risk_tickers + _risk_sold_tickers))
    _risk_extra_names   = tuple(
        {**dict(zip(_risk_sold_tickers, _risk_sold_names)), **dict(zip(_risk_tickers, _risk_names))}[t]
        for t in _risk_extra_tickers
    )
    *_risk_exch_dfs, _risk_extra_df = _load_all_screener_data(_cache_version(), _risk_enabled, _risk_extra_tickers, _risk_extra_names)
    _risk_scr_df   = pd.concat(_risk_exch_dfs + [_risk_extra_df], ignore_index=True)
    _risk_dlg_pending: list = []

    # ── Enrich portfolio with live prices, fair values, sector, country ───────
    _risk_live = _fetch_live_data(tuple(pf["ticker"].tolist()))

    def _rlv(field, default=None):
        return pf["ticker"].map(lambda t: _risk_live.get(t, {}).get(field, default))

    pf["live_price"]      = _rlv("price")
    pf["current_value"]   = pf["live_price"] * pf["shares"]
    pf["fair_value"]      = _rlv("fair_value")
    pf["sector"]          = _rlv("sector")
    pf["country"]         = _rlv("country")
    pf["div_rate"]        = _rlv("div_rate", 0).map(lambda v: v or 0)
    pf["expected_annual"] = (pf["div_rate"] * pf["shares"]).round(2)

    _risk_full_cache = _load_cache()

    # ── Income portfolio toggle (widget lives in the Summary tab; value persists
    # in session_state across reruns so it can be read here before that tab draws) ──
    _income_portfolio = st.session_state.get("risk_income_toggle", False)

    # ── Cached risk report (1-hour TTL stored in session_state) ──────────────
    _risk_cache_key = str((tuple(sorted(pf["ticker"].tolist())), _income_portfolio))
    _risk_cached    = st.session_state.get("_risk_report_cache", {})
    _risk_report: _risk_module.RiskReport | None = None

    if (_risk_cached.get("key") == _risk_cache_key and "report" in _risk_cached):
        _gen_at = datetime.fromisoformat(_risk_cached["report"].generated_at)
        _age_s  = (datetime.now(timezone.utc) - _gen_at).total_seconds()
        if _age_s < 3600:
            _risk_report = _risk_cached["report"]

    if _risk_report is None:
        try:
            _risk_report = _risk_module.assess_portfolio(pf, _risk_full_cache, _income_portfolio)
            st.session_state["_risk_report_cache"] = {"key": _risk_cache_key, "report": _risk_report}
        except Exception as _risk_err:
            st.error(f"Risk assessment failed: {_risk_err}")
            st.stop()

    r = _risk_report

    # ── Detail tabs ───────────────────────────────────────────────────────────
    (_t_summary, _t_pos, _t_conc, _t_quant, _t_factor,
     _t_income, _t_stress, _t_mc) = st.tabs([
        "Summary", "Positions", "Concentration", "Volatility & VaR",
        "Factor Exposure", "Income Risk", "Stress Tests",
        "Monte Carlo",
    ])

    # ── Tab: Summary ──────────────────────────────────────────────────────────
    with _t_summary:
        _c_note, _c_hdr, _c_tog, _c_refresh = st.columns([2, 3, 2, 1], vertical_alignment="center")
        with _c_note:
            _risk_note(
                "The composite score (0–100) aggregates six risk dimensions — Concentration, "
                "Volatility, Tail Risk, Factor, Fundamental, and Income — into a single "
                "**Low / Moderate / Elevated / High / Critical** rating.\n\n"
                "- Toggling **Income mode** re-weights the blend to emphasise income risk, for "
                "portfolios run primarily for dividend income.\n"
                "- **Hard triggers** require immediate action — a threshold breach that materially "
                "increases portfolio risk (e.g. single position >20%, beta >1.5, 99% VaR exceeding "
                "3% of portfolio, or a Critical-rated position).\n"
                "- **Soft triggers** are advisory — worth reviewing and planning around, but not "
                "requiring same-day action (e.g. HHI drift, sector overweight, Sharpe below 1.0, or "
                "a High-rated position).\n"
                "- Each trigger card shows its recommended next step (↳) directly underneath."
            )
        with _c_tog:
            st.toggle("Income mode", value=_income_portfolio, key="risk_income_toggle")
        with _c_refresh:
            if st.button("Refresh", type="tertiary", key="risk_refresh_btn"):
                st.session_state.pop("_risk_report_cache", None)
                st.rerun()

        _score_color = {
            "Low risk":      "green",
            "Moderate risk": "blue",
            "Elevated risk": "orange",
            "High risk":     "red",
            "Critical risk": "red",
        }.get(r.composite.label, "gray")

        st.markdown(f"### :{_score_color}[{r.composite.score:.0f} · {r.composite.label}]")
        st.caption(f"{r.composite.action}  \n"
                   f"€{r.portfolio_value:,.0f} · {r.n_positions} positions · "
                   f"updated {datetime.fromisoformat(r.generated_at).strftime('%H:%M UTC')}")

        # ── Sub-score bar chart ─────────────────────────────────────────────────
        _sub_scores = r.composite.sub_scores
        _ss_fig = go.Figure(go.Bar(
            x=list(_sub_scores.keys()),
            y=list(_sub_scores.values()),
            marker_color=[
                "#1DD6A4" if v < 25 else "#5B8FA8" if v < 50 else "#8BA888" if v < 70 else "#A32D2D"
                for v in _sub_scores.values()
            ],
            text=[f"{v:.0f}" for v in _sub_scores.values()],
            textposition="outside",
            textfont=dict(color=_c_axis),
        ))
        _ss_fig.update_layout(
            height=220, margin=dict(t=20, b=0, l=0, r=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(range=[0, 115], showgrid=False, visible=False),
            xaxis=dict(showgrid=False, tickfont=dict(color=_c_axis)),
            font=dict(color=_c_axis),
            showlegend=False,
        )
        st.plotly_chart(_ss_fig, width='stretch')

        st.divider()

        # ── Hard / soft triggers, each bundled with its recommended action ────
        _hard_items = [i for i in r.rebalance.items if i.severity == "hard"]
        _soft_items = [i for i in r.rebalance.items if i.severity == "soft"]

        if _hard_items:
            st.markdown(f"**{len(_hard_items)} hard trigger(s)** — take action")
            for item in _hard_items:
                _trigger_card(item.message, "hard", item.action)
        elif not _soft_items:
            st.success("No rebalancing triggers detected.", icon=":material/check:")

        if _soft_items:
            st.markdown(f"**{len(_soft_items)} soft trigger(s)** — review and plan")
            for item in _soft_items:
                _trigger_card(item.message, "soft", item.action)

        st.divider()
        st.caption(f"Risk report generated at {datetime.fromisoformat(r.generated_at).strftime('%Y-%m-%d %H:%M UTC')}. "
                   "Refreshes automatically after 1 hour or when portfolio changes.")

    # ── Tab: Positions ────────────────────────────────────────────────────────
    with _t_pos:
        _risk_note(
            "Each row profiles one portfolio position. Risk Rating aggregates all dimensions "
            "into a single label — **Low / Medium / High / Critical** — based on weight, beta, "
            "valuation, financial health and earnings quality. Use this table to quickly spot "
            "positions that deserve closer review before looking at portfolio-level metrics."
        )
        _pos_rows = []
        for p in r.position_profiles:
            _pos_rows.append({
                "Company":         p.name,
                "Ticker":          p.ticker,
                "Weight":          p.weight,
                "Beta":            p.beta,
                "VaR 95% 1d":      p.var_95_1d_eur or None,
                "MoS":             p.mos,
                "Valuation":       p.valuation_flag,
                "Div":             p.div_sustainability or "—",
                "Fin Health":      p.financial_health,
                "Earn Quality":    p.earnings_quality,
                "Risk Rating":     p.rating,
            })
        _pos_df = pd.DataFrame(_pos_rows)
        _row_h = 35
        _risk_sel_idx = _row_select_table(
            _pos_df,
            key="risk_positions_table",
            hide_index=True,
            width='stretch',
            height=35 + min(len(_pos_df), 20) * _row_h,
            column_config={
                "Company":      st.column_config.TextColumn("Company",     pinned=True,
                                    help="Company name"),
                "Ticker":       st.column_config.TextColumn("Ticker",
                                    help="Exchange ticker symbol"),
                "Weight":       st.column_config.NumberColumn("Weight",     format="percent",
                                    help="Position value as a % of total portfolio. >10% = concentrated; >15% triggers a hard flag."),
                "Beta":         st.column_config.NumberColumn("Beta",       format="%.2f",
                                    help="Market sensitivity (regression vs index). >1 = amplifies market moves; <1 = more defensive. >1.3 adds to risk rating."),
                "VaR 95% 1d":   st.column_config.NumberColumn("VaR 95% 1d", format="euro",
                                    help="Maximum expected 1-day loss for this position at 95% confidence. Estimated as position value × |beta| × market daily vol × 1.645."),
                "MoS":          st.column_config.NumberColumn("MoS",        format="percent",
                                    help="Margin of Safety = (Fair Value − Price) / Fair Value. Positive = undervalued; negative = overvalued vs the fair value model estimate."),
                "Valuation":    st.column_config.TextColumn("Valuation",
                                    help="Undervalued (MoS >10%) · Fairly Valued (MoS 0–10%) · Overvalued (MoS <0%). Overvalued positions add to the risk rating."),
                "Div":          st.column_config.TextColumn("Div",
                                    help="Dividend sustainability flag from the fair value screener. OK = all payout checks pass. At Risk = payout ratio >90%, cash payout >80%, or coverage <1.2×."),
                "Fin Health":   st.column_config.NumberColumn("Fin Health",   format="%.1f/10",
                                    help="Financial health score 0–10 (higher = healthier). Average of D/E ratio, current ratio, and interest coverage. <5 adds to risk rating."),
                "Earn Quality": st.column_config.NumberColumn("Earn Quality", format="%.1f/10",
                                    help="Earnings quality score 0–10. Measures FCF vs net income — high accruals (earnings without cash backing) score lower. <3 adds to risk rating."),
                "Risk Rating":  st.column_config.TextColumn("Risk Rating",
                                    help="Aggregated position risk: Low · Medium · High · Critical. Determined by the number of risk factors breached across weight, beta, valuation, financial health and earnings quality."),
            },
        )
        if _risk_sel_idx is not None:
            _risk_sel = _pos_df["Ticker"].iloc[_risk_sel_idx]
            _risk_scr_row = _risk_scr_df[_risk_scr_df["Ticker"] == _risk_sel]
            if not _risk_scr_row.empty:
                _risk_dlg_pending.append((_risk_scr_row.iloc[0], None))
        else:
            # Keep the drawer open across the rerun caused by the watchlist star
            _reopen = st.session_state.get("_drw_reopen_ticker")
            _r = _risk_scr_df[_risk_scr_df["Ticker"] == _reopen] if _reopen else pd.DataFrame()
            if not _r.empty:
                st.session_state.pop("_drw_reopen_ticker", None)
                _risk_dlg_pending.append((_r.iloc[0], None))

        _pos_tickers = {p.ticker for p in r.position_profiles}
        _pos_items = [i for i in r.rebalance.items if i.ticker in _pos_tickers]
        if _pos_items:
            st.divider()
            st.markdown(f"**{len(_pos_items)} flagged position(s)**")
            for item in _pos_items:
                _trigger_card(item.message, item.severity, item.action)

    # ── Tab: Concentration ────────────────────────────────────────────────────
    with _t_conc:
        _risk_note(
            "Concentration risk measures how much of the portfolio depends on a small number "
            "of positions, sectors, or geographies.\n\n"
            "- The **HHI** (Herfindahl-Hirschman Index) is the sum of squared weights — closer to "
            "0 means well spread, above 0.18 is highly concentrated.\n"
            "- Flags trigger at >15% single position, >30% single sector, or >60% single country.\n"
            "- Dividend HHI applies the same logic to income streams."
        )
        c = r.concentration
        _cc1, _cc2, _cc3 = st.columns(3)
        _cc1.metric("HHI", f"{c.hhi:.3f}", help=c.hhi_label)
        _cc2.metric("Top-1 weight", f"{c.top1_weight:.1%}", delta="Flag" if c.top1_flag else "OK",
                    delta_color="inverse" if c.top1_flag else "off")
        _cc3.metric("Top-3 weight", f"{c.top3_weight:.1%}", delta="Flag" if c.top3_flag else "OK",
                    delta_color="inverse" if c.top3_flag else "off")

        st.caption(f"**Concentration:** {c.hhi_label}  |  Top-5: {c.top5_weight:.1%}")

        _conc_c1, _conc_c2 = st.columns(2)
        with _conc_c1:
            st.markdown("**Sector weights**")
            if c.sector_weights:
                _sec_fig = go.Figure(go.Bar(
                    x=list(c.sector_weights.keys()),
                    y=[v * 100 for v in c.sector_weights.values()],
                    marker_color=["#A32D2D" if v > 0.30 else "#1DD6A4" for v in c.sector_weights.values()],
                    text=[f"{v:.0%}" for v in c.sector_weights.values()],
                    textposition="outside",
                    textfont=dict(color=_c_axis),
                ))
                _sec_fig.add_hline(y=30, line_dash="dot", line_color=_c_grid,
                                   annotation_text="30% threshold", annotation_position="top right",
                                   annotation_font_color=_c_axis)
                _sec_fig.update_layout(
                    height=260, margin=dict(t=20, b=60, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(title="Weight %", showgrid=True, gridcolor=_c_grid,
                               tickfont=dict(color=_c_axis), title_font=dict(color=_c_axis)),
                    xaxis=dict(tickangle=-30, tickfont=dict(color=_c_axis)),
                    font=dict(color=_c_axis), showlegend=False,
                )
                st.plotly_chart(_sec_fig, width='stretch')

        with _conc_c2:
            st.markdown("**Geographic weights**")
            if c.geo_weights:
                _geo_n = len(c.geo_weights)
                _geo_colors = [_DONUT_PALETTE[i % len(_DONUT_PALETTE)] for i in range(_geo_n)]
                _geo_total = sum(c.geo_weights.values())
                _geo_pcts  = [v / _geo_total * 100 for v in c.geo_weights.values()]
                _geo_text  = [f"{p:.1f}%" if p >= 4 else "" for p in _geo_pcts]
                _geo_fig = go.Figure(go.Pie(
                    labels=list(c.geo_weights.keys()),
                    values=list(c.geo_weights.values()),
                    hole=0.52,
                    text=_geo_text,
                    textinfo="text",
                    textposition="inside",
                    insidetextorientation="horizontal",
                    hovertemplate="%{label}: %{percent}<extra></extra>",
                    marker=dict(colors=_geo_colors,
                                line=dict(color=_c_surface, width=2)),
                    textfont=dict(color=_c_text, size=12),
                ))
                _geo_fig.update_layout(
                    height=max(260, 24 * _geo_n + 60),
                    margin=dict(t=10, b=10, l=0, r=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=True,
                    legend=dict(orientation="v", x=1.02, xanchor="left", y=1.0, yanchor="top",
                                font=dict(size=11, color=_c_axis), itemwidth=30),
                    font=dict(color=_c_axis),
                )
                st.plotly_chart(_geo_fig, width='stretch')

        if c.div_hhi is not None:
            st.caption(f"Dividend income HHI: {c.div_hhi:.3f} | Top-3 income share: {c.div_top3_pct:.0%}"
                       + (" — concentrated" if c.income_concentration_flag else ""))

        # ── All concentration triggers, full-width, below the charts ─────────
        _conc_triggers = []
        if c.hhi > 0.15:
            _conc_triggers.append(("soft",
                f"HHI {c.hhi:.3f} — concentration has drifted well above 0.10 diversified threshold",
                "Add uncorrelated positions or sectors to reduce concentration"))
        elif c.hhi > 0.10:
            _conc_triggers.append(("soft",
                f"HHI {c.hhi:.3f} — moderately concentrated, monitor drift",
                "Monitor concentration drift; avoid adding to largest positions"))
        if c.sector_flag and c.largest_sector:
            w = c.sector_weights.get(c.largest_sector, 0.0)
            _conc_triggers.append(("soft",
                f"{c.largest_sector} sector at {w:.0%} — exceeds 30% guideline",
                "Reduce largest sector; add exposure to lagging sectors"))
        if c.geo_flag and c.largest_geo:
            w = c.geo_weights.get(c.largest_geo, 0.0)
            _conc_triggers.append(("soft",
                f"{c.largest_geo} at {w:.0%} of portfolio — exceeds 60% country guideline",
                "Diversify into additional geographies; trim largest-country exposure"))
        if c.div_hhi is not None and c.income_concentration_flag:
            _conc_triggers.append(("soft",
                f"Dividend income HHI {c.div_hhi:.3f} — top-3 income share {c.div_top3_pct:.0%} — concentrated",
                "Diversify dividend income across more payers to reduce reliance on top payers"))

        if _conc_triggers:
            st.divider()
            for _kind, _msg, _action in _conc_triggers:
                _trigger_card(_msg, _kind, _action)

    # ── Tab: Volatility & VaR ─────────────────────────────────────────────────
    with _t_quant:
        _risk_note(
            "- **Beta** measures overall market sensitivity — above 1.2 means the portfolio "
            "amplifies market swings, below 0.8 is defensive.\n"
            "- **Annual Vol** is the standard deviation of daily returns scaled to a year; above "
            "20% is high.\n"
            "- **VaR** is the maximum expected 1-day loss at a given confidence level — e.g. a "
            "95% VaR of €500 means only 1 day in 20 should lose more than that.\n"
            "- **CVaR** (Expected Shortfall) is the average loss on those worst days, capturing "
            "tail risk beyond VaR.\n"
            "- **MDD** is the largest peak-to-trough drawdown observed in the historical window.\n"
            "- The correlation heatmap shows how positions move together — pairs above 0.80 "
            "provide little diversification benefit."
        )
        q = r.quant
        _qc1, _qc2, _qc3, _qc4, _qc5 = st.columns(5)
        _qc1.metric("Portfolio Beta", f"{q.portfolio_beta:.2f}", help=q.beta_label)
        _qc2.metric("Annual Vol",
                    f"{q.volatility_annual:.1%}" if q.volatility_annual else "N/A",
                    help=q.volatility_label)
        _qc3.metric("Sharpe",  f"{q.sharpe:.2f}"  if q.sharpe  else "N/A", help=q.ratio_label)
        _qc4.metric("Sortino", f"{q.sortino:.2f}" if q.sortino else "N/A")
        _qc5.metric("VaR 95% (1d)", f"€{q.var_95_1d_eur:,.0f}" if q.var_95_1d_eur else "N/A",
                    help="Maximum expected 1-day loss at 95% confidence (historical simulation)")

        st.divider()

        _vc1, _vc2, _vc3, _vc4, _vc5 = st.columns(5)
        _vc1.metric("VaR 99% (1d)", f"€{q.var_99_1d_eur:,.0f}" if q.var_99_1d_eur else "N/A")
        _vc2.metric("CVaR 95% (1d)", f"€{q.cvar_95_1d_eur:,.0f}" if q.cvar_95_1d_eur else "N/A",
                    help="Expected loss in the worst 5% of scenarios (Expected Shortfall)")
        _vc3.metric("MDD 1y", f"{q.mdd_1y:.1%}" if q.mdd_1y else "N/A",
                    help=f"Max drawdown over last 12 months — {q.mdd_label}")
        _vc4.metric("MDD 3y", f"{q.mdd_3y:.1%}" if q.mdd_3y else "N/A")
        _vc5.metric("MDD 5y", f"{q.mdd_5y:.1%}" if q.mdd_5y else "N/A")

        if not q.returns_available:
            st.info("Historical price data unavailable — quantitative metrics use beta-proxy estimates.")

        if q.portfolio_beta > 1.5:
            _trigger_card(f"Portfolio beta {q.portfolio_beta:.2f} exceeds 1.5 — amplified drawdown risk", "hard",
                          "Rotate into low-beta / defensive stocks")

        if q.var_99_1d_eur is not None and r.portfolio_value > 0:
            _var99_pct = q.var_99_1d_eur / r.portfolio_value
            if _var99_pct > 0.03:
                _trigger_card(f"1-day 99% VaR = €{q.var_99_1d_eur:,.0f} ({_var99_pct:.1%}) — exceeds 3% loss tolerance", "hard",
                              "Reduce high-beta/volatile positions to lower tail risk")

        if q.sharpe is not None and q.sharpe < 1.0:
            _trigger_card(f"Sharpe ratio {q.sharpe:.2f} below 1.0 — risk-adjusted return suboptimal", "soft",
                          "Reassess risk/return mix; trim volatile underperformers")

        if q.corr_matrix is not None and len(q.corr_matrix) > 1:
            st.divider()
            st.markdown("**Return correlation matrix (last 252 trading days)**")
            _corr = q.corr_matrix.round(2)
            _heat_mid = "#EEF1F5" if _ui_effective_light else "#0D1F3C"
            _heat = go.Figure(go.Heatmap(
                z=_corr.values,
                x=list(_corr.columns),
                y=list(_corr.index),
                colorscale=[
                    [0.0, "#A32D2D"],
                    [0.5, _heat_mid],
                    [1.0, "#1DD6A4"],
                ],
                zmin=-1, zmax=1,
                text=_corr.values.round(2),
                texttemplate="%{text}",
                textfont=dict(color=_c_axis),
                showscale=True,
            ))
            _heat.update_layout(
                height=max(300, len(_corr) * 40 + 80),
                margin=dict(t=20, b=60, l=80, r=20),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=_c_axis),
                xaxis=dict(tickangle=-30, tickfont=dict(color=_c_axis),
                           showline=False, zeroline=False, ticks=""),
                yaxis=dict(tickfont=dict(color=_c_axis),
                           showline=False, zeroline=False, ticks=""),
            )
            _heat.update_traces(showscale=True,
                                colorbar=dict(outlinewidth=0, tickfont=dict(color=_c_axis)))
            st.plotly_chart(_heat, width='stretch')
            if q.high_corr_pairs:
                _pairs_str = ", ".join(f"**{a}/{b}** ({c:.2f})" for a, b, c in q.high_corr_pairs)
                _trigger_card(f"High-correlation pairs (>0.80): {_pairs_str} — limited diversification", "soft",
                              "Replace one position per pair with uncorrelated exposure")
            if q.effective_diversification is not None:
                st.caption(f"Effective diversification score: {q.effective_diversification:.2f} "
                           f"(1 − avg pairwise correlation)")

    # ── Tab: Factor Exposure ──────────────────────────────────────────────────
    with _t_factor:
        _risk_note(
            "Factor analysis decomposes portfolio returns into known systematic risk factors "
            "using the **Fama-French 5-factor model** (+ momentum). Each bar is a factor loading — "
            "how much the portfolio moves per unit of that factor's return.\n\n"
            "- A loading above **±1.5** signals a concentrated factor bet.\n"
            "- **R²** shows what fraction of return variance the model explains; above 0.6 means "
            "the portfolio is factor-dominated.\n"
            "- **Alpha** is the annualised return not explained by any factor — positive alpha "
            "suggests genuine stock-picking skill, negative suggests the portfolio underperforms "
            "its factor exposures.\n\n"
            "Factors: **Mkt-RF** market premium · **SMB** small vs large cap · "
            "**HML** value vs growth · **RMW** high vs low profitability · "
            "**CMA** conservative vs aggressive investment · **WML** momentum."
        )
        f = r.factor
        if not f.available:
            st.info("Factor analysis unavailable. " + (f.flags[0] if f.flags else ""))
            st.caption("Factor data is downloaded from the Ken French data library — this needs internet access and enough price history per holding.")
        else:
            _fc1, _fc2 = st.columns(2)
            _fc1.metric("R²", f"{f.r_squared:.3f}" if f.r_squared else "—",
                        help="Fraction of portfolio return variance explained by the 5-factor model")
            _fc2.metric("Alpha (ann.)", f"{f.alpha_annualised:.2%}" if f.alpha_annualised else "—",
                        help="Annualised abnormal return above factor model prediction")

            if f.loadings:
                _fac_fig = go.Figure(go.Bar(
                    x=list(f.loadings.keys()),
                    y=list(f.loadings.values()),
                    marker_color=["#A32D2D" if abs(v) > 1.5 else "#1DD6A4" for v in f.loadings.values()],
                    text=[f"{v:+.2f}" for v in f.loadings.values()],
                    textposition="outside",
                    textfont=dict(color=_c_axis),
                ))
                _fac_fig.add_hline(y=1.5,  line_dash="dot", line_color=_c_grid,
                                   annotation_text="±1.5", annotation_font_color=_c_axis)
                _fac_fig.add_hline(y=-1.5, line_dash="dot", line_color=_c_grid)
                _fac_fig.update_layout(
                    height=280, margin=dict(t=30, b=20, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(title="Factor Loading", showgrid=True, gridcolor=_c_grid,
                               tickfont=dict(color=_c_axis), title_font=dict(color=_c_axis)),
                    xaxis=dict(tickfont=dict(color=_c_axis)),
                    font=dict(color=_c_axis), showlegend=False,
                )
                st.plotly_chart(_fac_fig, width='stretch')

            if f.flags:
                for _msg in f.flags:
                    _trigger_card(_msg, "soft", _factor_flag_action(_msg))

            st.caption("Mkt-RF: market | SMB: small vs large | HML: value vs growth | "
                       "RMW: profitability | CMA: investment | WML: momentum (if available). "
                       "Red bars = loading >1.5 — concentrated factor bet. "
                       "Dashed lines = ±1.5 threshold.")

    # ── Tab: Income Risk ──────────────────────────────────────────────────────
    with _t_income:
        _risk_note(
            "Income risk measures how vulnerable the portfolio's dividend stream is.\n\n"
            "- **Portfolio Yield** is total expected annual dividends divided by current portfolio "
            "value.\n"
            "- **Weighted DGR** (Dividend Growth Rate) is the income-weighted average of each "
            "payer's earnings growth — a DGR below inflation (~2.5%) means purchasing power of "
            "income erodes.\n"
            "- The **top-3 cut scenario** simulates the income impact if the three largest "
            "dividend payers each cut their dividend by 50% — a standard stress test for income "
            "concentration.\n"
            "- Positions flagged for sustainability have at least one of: payout ratio >80%, cash "
            "payout ratio >80%, or dividend coverage ratio <1.2×."
        )
        inc = r.income
        _ic1, _ic2, _ic3, _ic4, _ic5 = st.columns(5)
        _ic1.metric("Portfolio Yield", f"{inc.portfolio_yield:.2%}")
        _ic2.metric("Annual Income", f"€{inc.total_annual_income:,.0f}")
        _ic3.metric("Weighted DGR",
                    f"{inc.weighted_dgr:.1%}" if inc.weighted_dgr is not None else "N/A",
                    help="Income-weighted dividend growth rate (earnings growth proxy)")
        _ic4.metric("Top-3 cut scenario",
                    f"€{inc.top3_cut_eur:,.0f}" if inc.top3_cut_eur else "N/A",
                    help="Income at risk if top-3 dividend payers cut by 50%")
        _ic5.metric("Income at risk",
                    f"{inc.top3_cut_pct:.1%}" if inc.top3_cut_pct else "N/A",
                    delta="Flag" if inc.income_concentration_flag else "OK",
                    delta_color="inverse" if inc.income_concentration_flag else "off")

        if inc.top3_income_shares:
            st.markdown("**Top income contributors**")
            _inc_rows = [{"Ticker": t, "Share of income": f"{sh:.1%}"}
                         for t, sh in inc.top3_income_shares]
            st.dataframe(pd.DataFrame(_inc_rows), hide_index=True, width='content',
                         column_config={
                             "Ticker":         st.column_config.TextColumn("Ticker",
                                                   help="Exchange ticker symbol of the dividend payer"),
                             "Share of income": st.column_config.TextColumn("Share of income",
                                                   help="This payer's expected annual dividend as a fraction of total portfolio income. High concentration here amplifies the impact of a dividend cut."),
                         })

        if inc.top3_cut_pct is not None and inc.top3_cut_pct > 0.40:
            _trigger_card(f"Top-3 dividend cut scenario removes {inc.top3_cut_pct:.0%} of annual income", "hard",
                          "Diversify income across more dividend payers")

        if inc.weighted_dgr is not None and inc.weighted_dgr < 0.025:
            _trigger_card(f"Weighted portfolio DGR {inc.weighted_dgr:.1%} may trail inflation (~2.5%) — real income erosion risk", "soft",
                          "Favor payers with stronger dividend growth track records")

        if inc.flagged_payers:
            _trigger_card(
                f"Sustainability concerns ({inc.flagged_income_pct:.0%} of income): "
                + ", ".join(inc.flagged_payers),
                "soft",
                "Review payout ratios and coverage for flagged payers; consider trimming or replacing them",
            )

    # ── Tab: Stress Tests ─────────────────────────────────────────────────────
    with _t_stress:
        _risk_note(
            "Stress tests show how the portfolio might perform under adverse conditions.\n\n"
            "- **Historical scenarios** replay four real market crises. Portfolio drawdown is "
            "estimated as portfolio beta × index drawdown — a beta of 0.8 during a −50% crash "
            "implies a −40% portfolio loss. This is an approximation; actual losses depend on "
            "individual stock behaviour during the specific period.\n"
            "- **Hypothetical scenarios** apply targeted shocks: the rate-rise scenario uses each "
            "stock's P/E as a duration proxy (high P/E = more sensitive to higher rates); the "
            "recession scenario applies a 25% earnings cut to cyclical sectors and 10% to "
            "defensives; the sector crash applies a −40% shock to the largest sector holding; the "
            "credit crunch penalises high-leverage positions proportionally to D/E ratio."
        )
        st.markdown("**Historical scenarios** *(beta-adjusted approximation)*")
        _hist_rows = [{
            "Scenario":       s.name,
            "Period":         s.period,
            "Index drawdown": s.index_drawdown * 100 if s.index_drawdown else None,
            "Est. DD":        s.portfolio_drawdown * 100 if s.portfolio_drawdown else None,
            "Est. loss €":    s.portfolio_value_loss if s.portfolio_value_loss else None,
        } for s in r.stress.historical]
        st.dataframe(pd.DataFrame(_hist_rows), hide_index=True, width='stretch',
            column_config={
                "Scenario":       st.column_config.TextColumn("Scenario", width=200, pinned=True,
                                      help="Name of the historical market crisis"),
                "Period":         st.column_config.TextColumn("Period",
                                      help="Approximate date range of the crisis"),
                "Index drawdown": st.column_config.NumberColumn("Index drawdown", format="%.0f%%",
                                      help="Actual S&P 500 peak-to-trough drawdown during the crisis"),
                "Est. DD":        st.column_config.NumberColumn("Est. portfolio DD", format="%.1f%%", width=180,
                                      help="Estimated portfolio drawdown = portfolio beta × index drawdown"),
                "Est. loss €":    st.column_config.NumberColumn("Est. value loss €", format="€%.0f", width=160,
                                      help="Estimated euro loss at current portfolio value"),
            })

        st.caption("Drawdown estimated as portfolio beta × index drawdown. "
                   "For tickers with ≥5 years of history, actual returns are used where available.")

        _worst_dd = min((s.portfolio_drawdown or 0.0) for s in r.stress.historical)
        if _worst_dd < -0.40:
            _trigger_card(f"Worst-case historical scenario implies {_worst_dd:.0%} portfolio drawdown", "hard",
                          "Add defensive/uncorrelated assets to cushion tail risk")

        st.divider()
        st.markdown("**Hypothetical factor scenarios**")
        _factor_rows = [{
            "Scenario":    s["name"],
            "Description": s["description"],
            "Est. DD":     s["estimated_portfolio_impact"] * 100,
            "Est. loss €": s["estimated_loss_eur"],
        } for s in r.stress.factor_scenarios]
        st.dataframe(pd.DataFrame(_factor_rows), hide_index=True, width='stretch',
            column_config={
                "Scenario":    st.column_config.TextColumn("Scenario", width=200, pinned=True,
                                   help="Name of the hypothetical shock"),
                "Description": st.column_config.TextColumn("Description",
                                   help="How the shock is modelled"),
                "Est. DD":     st.column_config.NumberColumn("Est. portfolio loss", format="%.1f%%", width=180,
                                   help="Estimated portfolio return impact as a percentage"),
                "Est. loss €": st.column_config.NumberColumn("Est. value loss €", format="€%.0f", width=160,
                                   help="Estimated euro loss at current portfolio value"),
            })

    # ── Tab: Monte Carlo ──────────────────────────────────────────────────────
    with _t_mc:
        _risk_note(
            "Monte Carlo simulation runs **10,000 random return paths** over 1, 3, and 5 years, "
            "drawing daily returns from the historical return distribution of the portfolio.\n\n"
            "- The fan chart shows the range of outcomes: the dark line is the median path, the "
            "inner band covers the 25th–75th percentile (50% of paths), and the outer band covers "
            "the 5th–95th percentile (90% of paths).\n"
            "- **P5** is the worst-case outcome at 5% probability — what the portfolio could be "
            "worth in a persistently bad scenario.\n"
            "- **P(loss)** is the fraction of simulated paths that end below the starting value.\n"
            "- When historical price data is unavailable, returns are estimated from portfolio "
            "beta and a 5% market risk premium."
        )
        _mcs = [r.stress.mc_1y, r.stress.mc_3y, r.stress.mc_5y]
        _mc_cols = st.columns(3)
        for _col, _mc in zip(_mc_cols, _mcs):
            _col.metric(
                f"{_mc.horizon_years}y median return", f"{_mc.p50:.1%}",
                help=f"P5: {_mc.p05:.1%} | P95: {_mc.p95:.1%} | P(loss): {_mc.prob_loss:.0%}",
            )

        # Fan chart — portfolio value over time
        _years = [0, 1, 3, 5]
        _pv    = r.portfolio_value
        _fan_fig = go.Figure()

        def _build_fan(mc_list: list, color: str, label: str) -> None:
            pts_p05 = [_pv] + [_pv * (1 + m.p05) for m in mc_list]
            pts_p25 = [_pv] + [_pv * (1 + m.p25) for m in mc_list]
            pts_p50 = [_pv] + [_pv * (1 + m.p50) for m in mc_list]
            pts_p75 = [_pv] + [_pv * (1 + m.p75) for m in mc_list]
            pts_p95 = [_pv] + [_pv * (1 + m.p95) for m in mc_list]
            _fan_fig.add_trace(go.Scatter(
                x=_years, y=pts_p95, mode="lines",
                line=dict(width=0), showlegend=False, hoverinfo="skip",
            ))
            _fan_fig.add_trace(go.Scatter(
                x=_years, y=pts_p05, mode="lines",
                line=dict(width=0), fill="tonexty",
                fillcolor=f"rgba{(*_hex_to_rgb(color), 0.12)}",
                showlegend=False, hoverinfo="skip",
            ))
            _fan_fig.add_trace(go.Scatter(
                x=_years, y=pts_p75, mode="lines",
                line=dict(width=0), showlegend=False, hoverinfo="skip",
            ))
            _fan_fig.add_trace(go.Scatter(
                x=_years, y=pts_p25, mode="lines",
                line=dict(width=0), fill="tonexty",
                fillcolor=f"rgba{(*_hex_to_rgb(color), 0.20)}",
                showlegend=False, hoverinfo="skip",
            ))
            _fan_fig.add_trace(go.Scatter(
                x=_years, y=pts_p50, mode="lines+markers",
                line=dict(color=color, width=2),
                name=f"Median ({label})",
                hovertemplate="%{y:€,.0f}<extra></extra>",
            ))

        def _hex_to_rgb(h: str) -> tuple:
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

        _build_fan(_mcs, "#1DD6A4", "portfolio")
        _fan_fig.add_hline(y=_pv, line_dash="dot", line_color=_c_grid,
                           annotation_text="Current value", annotation_position="bottom right",
                           annotation_font_color=_c_axis)
        _fan_fig.update_layout(
            height=360, margin=dict(t=20, b=40, l=60, r=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="Portfolio value (€)", tickprefix="€",
                       tickformat=",.0f", showgrid=True, gridcolor=_c_grid,
                       tickfont=dict(color=_c_axis), title_font=dict(color=_c_axis)),
            xaxis=dict(title="Years", tickvals=[0, 1, 3, 5],
                       tickfont=dict(color=_c_axis), title_font=dict(color=_c_axis)),
            font=dict(color=_c_axis),
            legend=dict(x=0.02, y=0.98, font=dict(color=_c_axis)),
        )
        st.plotly_chart(_fan_fig, width='stretch')

        st.markdown("**Scenario probability table**")
        _mc_tbl = pd.DataFrame([
            {
                "Horizon":     f"{m.horizon_years}y",
                "P5 (worst)":  f"{m.p05:.1%}",
                "P25":         f"{m.p25:.1%}",
                "Median":      f"{m.p50:.1%}",
                "P75":         f"{m.p75:.1%}",
                "P95 (best)":  f"{m.p95:.1%}",
                "P(loss)":     f"{m.prob_loss:.0%}",
            }
            for m in _mcs
        ])
        st.dataframe(_mc_tbl, hide_index=True, width='content',
            column_config={
                "Horizon":    st.column_config.TextColumn("Horizon",
                                  help="Simulation time horizon"),
                "P5 (worst)": st.column_config.TextColumn("P5 (worst)",
                                  help="5th percentile total return — only 5% of paths perform worse than this"),
                "P25":        st.column_config.TextColumn("P25",
                                  help="25th percentile total return"),
                "Median":     st.column_config.TextColumn("Median",
                                  help="50th percentile — the most likely single outcome across all simulated paths"),
                "P75":        st.column_config.TextColumn("P75",
                                  help="75th percentile total return"),
                "P95 (best)": st.column_config.TextColumn("P95 (best)",
                                  help="95th percentile total return — only 5% of paths perform better than this"),
                "P(loss)":    st.column_config.TextColumn("P(loss)",
                                  help="Probability of a negative total return over this horizon"),
            })
        st.caption(f"10,000 Monte Carlo paths · daily returns drawn from historical distribution "
                   f"{'(actual returns)' if r.quant.returns_available else '(beta-proxy estimate)'}")

        _mc_1y = r.stress.mc_1y
        if _mc_1y.prob_loss > 0.35 or _mc_1y.p05 < -0.30:
            _trigger_card(
                f"1-year outlook: {_mc_1y.prob_loss:.0%} probability of loss, worst case (P5) {_mc_1y.p05:.0%}",
                "soft",
                "Reduce portfolio volatility (lower beta, diversify) to improve 1-year downside odds",
            )

    # Dispatch at most one detail dialog per render
    if _risk_dlg_pending:
        open_drawer(*_risk_dlg_pending[0])
