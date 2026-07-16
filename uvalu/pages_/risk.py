"""Portfolio risk page — composite score, concentration, VaR, factors, stress."""
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import risk as _risk_module
from portfolio import load_portfolio, load_sold
from screener import _load_cache
from settings import load_shared_settings, get_veto_thresholds, ALL_EXCHANGES
from uvalu.data import _load_all_screener_data, _cache_version, _fetch_live_data
from uvalu.runtime import theme_colors
from uvalu.drawer import open_drawer
from uvalu.components import score_color, radial_gauge_svg
from uvalu.ui import _row_select_table


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

_TICKER_SUFFIX_EXCHANGE = {
    ".BR": "Brussels", ".AS": "Amsterdam", ".PA": "Paris",
    ".MI": "Milan", ".DE": "Frankfurt", ".SW": "Swiss",
}

_FACTOR_NOTES = {
    "Mkt-RF": "Market sensitivity",
    "SMB":    "Small vs large cap tilt",
    "HML":    "Value vs growth tilt",
    "RMW":    "Profitability tilt",
    "CMA":    "Investment conservatism tilt",
    "WML":    "Momentum tilt",
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
    *_risk_exch_dfs, _risk_extra_df = _load_all_screener_data(
        _cache_version(), _risk_enabled, _risk_extra_tickers, _risk_extra_names, get_veto_thresholds())
    _risk_scr_df   = pd.concat(_risk_exch_dfs + [_risk_extra_df], ignore_index=True)

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

    # ══ Top section — score gauge, factor/concentration, risk contribution ═══
    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Risk assessment</div>',
               unsafe_allow_html=True)
    st.caption("Factor exposures, concentration and per-holding risk contribution across the portfolio.")

    with st.container(horizontal=True, gap="small", horizontal_alignment="right"):
        st.toggle("Income mode", value=_income_portfolio, key="risk_income_toggle")
        if st.button("Refresh", type="tertiary", key="risk_refresh_btn"):
            st.session_state.pop("_risk_report_cache", None)
            st.rerun()

    _gauge_col, _metrics_col = st.columns([1, 2], vertical_alignment="center")
    with _gauge_col:
        _ring_color, _label_color = score_color(r.composite.score)
        st.markdown(f"""
<div style="position:relative;width:132px;height:132px;">
  {radial_gauge_svg(r.composite.score, _ring_color, size=132)}
  <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
    <span style="font-family:var(--uv-mono);font-size:34px;font-weight:500;">{r.composite.score:.0f}</span>
    <span style="font-size:9.5px;color:var(--faint);">/ 100</span>
  </div>
</div>
<div style="font-size:16px;font-weight:500;margin-top:8px;color:{_label_color};">{r.composite.label}</div>
<div style="font-size:12px;color:var(--muted);margin-top:4px;line-height:1.5;">
  Blended score across six risk factors, weighted by exposure and hard-veto flags. {r.composite.action}</div>
""", unsafe_allow_html=True)
    with _metrics_col:
        with st.container(border=True):
            _m1, _m2, _m3 = st.columns(3)
            with _m1:
                st.metric("Beta", f"{r.quant.portfolio_beta:.2f}")
                st.caption(r.quant.beta_label)
            with _m2:
                st.metric("Volatility", f"{r.quant.volatility_annual:.1%}" if r.quant.volatility_annual else "N/A")
                st.caption(r.quant.volatility_label)
            with _m3:
                st.metric("VaR 95% (1d)", f"€{r.quant.var_95_1d_eur:,.0f}" if r.quant.var_95_1d_eur else "N/A")
                st.caption("Max expected 1-day loss")
            _m4, _m5, _m6 = st.columns(3)
            with _m4:
                st.metric("Sharpe", f"{r.quant.sharpe:.2f}" if r.quant.sharpe else "N/A")
                st.caption(r.quant.ratio_label)
            with _m5:
                st.metric("Max drawdown (1y)", f"{r.quant.mdd_1y:.1%}" if r.quant.mdd_1y else "N/A")
                st.caption(r.quant.mdd_label)
            with _m6:
                st.metric("Positions", r.n_positions)
                st.caption("Held in portfolio")

    _hard_items = [i for i in r.rebalance.items if i.severity == "hard"]
    _soft_items = [i for i in r.rebalance.items if i.severity == "soft"]
    if _hard_items or _soft_items:
        st.divider()
        for item in _hard_items:
            _trigger_card(item.message, "hard", item.action)
        for item in _soft_items:
            _trigger_card(item.message, "soft", item.action)
    else:
        st.success("No rebalancing triggers detected.", icon=":material/check:")

    st.divider()
    _factor_col, _conc_col = st.columns(2, gap="large")

    with _factor_col:
        st.markdown("##### Risk factor breakdown")
        if r.factor.available and r.factor.loadings:
            for _fname, _fval in r.factor.loadings.items():
                _fcolor = "var(--down-txt)" if abs(_fval) > 1.5 else "var(--up-txt)"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">'
                    f'<span>{_fname}</span><span style="font-family:var(--uv-mono);color:{_fcolor};">{_fval:+.2f}</span></div>'
                    f'<div style="height:5px;border-radius:3px;background:var(--uv-track,#EEF1F5);margin-bottom:3px;">'
                    f'<div style="width:{min(100, abs(_fval)/2.0*100):.0f}%;height:5px;border-radius:3px;background:{_fcolor};"></div></div>'
                    f'<div style="font-size:11px;color:var(--faint);margin-bottom:8px;">{_FACTOR_NOTES.get(_fname, "")}</div>',
                    unsafe_allow_html=True,
                )
            st.caption("Fama-French 5-factor + momentum loadings. |loading| > 1.5 = concentrated factor bet.")
        else:
            st.caption("Factor analysis unavailable. " + (r.factor.flags[0] if r.factor.flags else ""))

    with _conc_col:
        st.markdown("##### Concentration")
        c = r.concentration
        for _label, _val, _limit in [
            ("Single name",  c.top1_weight, 0.15),
            ("Largest sector", c.sector_weights.get(c.largest_sector, 0.0) if c.largest_sector else 0.0, 0.30),
            ("Largest country", c.geo_weights.get(c.largest_geo, 0.0) if c.largest_geo else 0.0, 0.60),
        ]:
            _over = _val > _limit
            _color = "var(--down-txt)" if _over else "var(--up-txt)"
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">'
                f'<span>{_label}</span><span style="font-family:var(--uv-mono);color:{_color};">{_val:.0%} / {_limit:.0%} limit</span></div>'
                f'<div style="height:5px;border-radius:3px;background:var(--uv-track,#EEF1F5);margin-bottom:8px;">'
                f'<div style="width:{min(100, _val/_limit*100):.0f}%;height:5px;border-radius:3px;background:{_color};"></div></div>',
                unsafe_allow_html=True,
            )

        _flags = []
        if c.top1_flag:
            _flags.append(f"{c.top1_ticker} at {c.top1_weight:.0%} exceeds the 15% single-name limit")
        if c.sector_flag and c.largest_sector:
            _flags.append(f"{c.largest_sector} at {c.sector_weights.get(c.largest_sector, 0):.0%} exceeds the 30% sector limit")
        if c.geo_flag and c.largest_geo:
            _flags.append(f"{c.largest_geo} at {c.geo_weights.get(c.largest_geo, 0):.0%} exceeds the 60% country limit")
        _veto_tickers = (
            [t for t in pf["ticker"] if bool(_risk_scr_df.set_index("Ticker")["veto"].get(t, False))]
            if "veto" in _risk_scr_df.columns else []
        )
        _veto_names = pf[pf["ticker"].isin(_veto_tickers)]["name"].tolist()
        if _veto_names:
            _flags.append(f"{', '.join(_veto_names)} remain(s) under a hard veto")
        if _flags:
            st.markdown(
                f'<div style="background:var(--navy,#0D1F3C);color:#fff;border-radius:8px;padding:10px 12px;font-size:12px;margin-top:6px;">'
                f'{" · ".join(_flags)}.</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div style="background:var(--navy,#0D1F3C);color:#fff;border-radius:8px;padding:10px 12px;font-size:12px;margin-top:6px;">'
                f'All positions sit within the 15% single-name, 30% sector, and 60% country limits.</div>',
                unsafe_allow_html=True)

    st.divider()
    st.markdown("##### Risk contribution by holding")
    _contrib_rows = []
    for p in r.position_profiles:
        _exch = next((v for suf, v in _TICKER_SUFFIX_EXCHANGE.items() if p.ticker.endswith(suf)), "—")
        _contrib_rows.append({
            "Company": p.name, "Ticker": p.ticker, "Exchange": _exch, "Weight": p.weight, "Beta": p.beta,
            "VaR 95% 1d": p.var_95_1d_eur or None,
            "Contribution": round(p.weight * abs(p.beta or 0) * 100, 1),
            "Flag": p.rating,
        })
    _contrib_df = pd.DataFrame(_contrib_rows).sort_values("Contribution", ascending=False)
    _contrib_sel_idx = _row_select_table(
        _contrib_df, key="risk_contribution_table", hide_index=True, width="stretch",
        height=35 + min(len(_contrib_df), 12) * 35,
        column_config={
            "Exchange":     st.column_config.TextColumn("Exchange", help="Exchange the ticker trades on"),
            "Weight":       st.column_config.NumberColumn("Weight", format="percent"),
            "Beta":         st.column_config.NumberColumn("Beta", format="%.2f"),
            "VaR 95% 1d":   st.column_config.NumberColumn("VaR 95% 1d", format="euro"),
            "Contribution": st.column_config.ProgressColumn("Contribution to risk", min_value=0,
                                 max_value=max(1.0, _contrib_df["Contribution"].max()),
                                 help="Weight × |beta| — a simple proxy for how much each position drives portfolio-level market risk."),
            "Flag":         st.column_config.TextColumn("Flag", help="Aggregated position risk rating: Low · Medium · High · Critical."),
        },
    )
    _risk_dlg_pending: list = []
    if _contrib_sel_idx is not None:
        _sel_ticker = _contrib_df["Ticker"].iloc[_contrib_sel_idx]
        _sel_row = _risk_scr_df[_risk_scr_df["Ticker"] == _sel_ticker]
        if not _sel_row.empty:
            _risk_dlg_pending.append((_sel_row.iloc[0], None))
    else:
        _reopen = st.session_state.get("_drw_reopen_ticker")
        _r = _risk_scr_df[_risk_scr_df["Ticker"] == _reopen] if _reopen else pd.DataFrame()
        if not _r.empty:
            st.session_state.pop("_drw_reopen_ticker", None)
            _risk_dlg_pending.append((_r.iloc[0], None))

    st.divider()

    # ── Detail tabs — deeper analysis beyond the mockup's minimum set ─────────
    (_t_quant, _t_factor, _t_income, _t_stress, _t_mc) = st.tabs([
        "Volatility & VaR", "Factor Exposure", "Income Risk", "Stress Tests",
        "Monte Carlo",
    ])

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
