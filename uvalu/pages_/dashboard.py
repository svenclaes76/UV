"""Dashboard page — portfolio summary metrics, treemap, movers, dividends."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import risk as _risk_module
from portfolio import portfolio_exists, load_portfolio, load_value_history
from screener import _load_cache
from settings import load_shared_settings, ALL_EXCHANGES
from uvalu.data import _load_all_screener_data, _cache_version, _fetch_prices_cached
from uvalu.formatting import safe_pct as _safe_pct
from uvalu.runtime import theme_colors
from uvalu.ui import _donut_chart, _hm_color, _CHART_CONFIG


def render() -> None:
    # Per-run state + sibling page links (module was split out of app.py)
    from uvalu import nav
    _pg_screener = nav.pages["screener"]
    _pg_settings = nav.pages["settings"]
    _pg_risk     = nav.pages["risk"]
    _C = theme_colors()
    _c_axis, _c_grid, _c_invested, _c_text, _c_surface = (
        _C.axis, _C.grid, _C.invested, _C.text, _C.surface)
    # ── Load portfolio data ────────────────────────────────────────────────────
    if not portfolio_exists():
        _, _es_col, _ = st.columns([1, 1.1, 1])
        with _es_col:
            st.container(height=48, border=False)
            st.subheader("No portfolio yet")
            st.caption("Browse the screener to identify stocks worth buying, "
                       "or import an existing Excel portfolio in Settings.")
            with st.container(horizontal=True, gap="small"):
                st.page_link(_pg_screener, label="Open screener")
                st.page_link(_pg_settings, label="Import portfolio")
        st.stop()

    _db_pf = load_portfolio()
    if _db_pf is None or _db_pf.empty:
        st.info("Your portfolio is empty.")
        st.stop()

    # Enrich with live prices
    _db_tickers = _db_pf["ticker"].dropna().astype(str).str.strip().tolist()
    _db_prices  = _fetch_prices_cached(tuple(_db_tickers))
    for _col, _key in [("live_price", "price"), ("day_change_pct", "day_change_pct"),
                        ("prev_close", "prev_close")]:
        _db_pf[_col] = _db_pf["ticker"].map(lambda t, k=_key: _db_prices.get(t, {}).get(k))

    _db_pf["purchase_value"] = pd.to_numeric(_db_pf["purchase_value"], errors="coerce")
    _db_pf["shares"]         = pd.to_numeric(_db_pf["shares"],         errors="coerce")
    _db_pf["live_price"]     = pd.to_numeric(_db_pf["live_price"],     errors="coerce")
    _db_pf["dividends"]      = pd.to_numeric(_db_pf["dividends"],      errors="coerce").fillna(0)

    _db_cost          = _db_pf["purchase_value"].where(_db_pf["purchase_value"] > 0)
    _db_pf["current_value"] = (_db_pf["shares"] * _db_pf["live_price"]).where(
        _db_pf["live_price"].notna(), _db_pf["purchase_value"])
    _db_pf["price_gain"]     = _db_pf["current_value"] - _db_pf["purchase_value"]
    _db_pf["price_gain_pct"] = (_db_pf["price_gain"] / _db_cost * 100).round(2)
    _db_pf["day_change_pct"] = pd.to_numeric(_db_pf["day_change_pct"], errors="coerce")

    _db_invested  = _db_pf["purchase_value"].sum()
    _db_current   = _db_pf["current_value"].sum()
    _db_gain      = _db_current - _db_invested
    _db_gain_pct  = _safe_pct(_db_gain, _db_invested)
    _db_divs      = _db_pf["dividends"].sum()
    _db_total_ret = _db_gain + _db_divs
    _db_ret_pct   = _safe_pct(_db_total_ret, _db_invested)

    # Avg margin of safety from screener cache
    _db_enabled = tuple(load_shared_settings().get("enabled_exchanges", ALL_EXCHANGES))
    _db_all_scr = pd.concat(list(_load_all_screener_data(_cache_version(), _db_enabled)[:-1]), ignore_index=True)
    _db_scr = _db_all_scr[_db_all_scr["Ticker"].isin(_db_tickers)].copy()
    _db_mos_vals = pd.to_numeric(_db_scr.get("MoS %", pd.Series(dtype=float)), errors="coerce").dropna()
    _db_avg_mos  = _db_mos_vals.mean() if not _db_mos_vals.empty else None

    # Forward annual income: dividendYield × current_value per holding
    _db_fwd_income = None
    if not _db_scr.empty and "dividendYield" in _db_scr.columns:
        _db_pf_cv = _db_pf.set_index("ticker")["current_value"]
        _db_scr_dy = _db_scr.set_index("Ticker")["dividendYield"]
        _db_scr_dy = pd.to_numeric(_db_scr_dy, errors="coerce").fillna(0)
        _db_fwd_income = (_db_pf_cv.reindex(_db_scr_dy.index).fillna(0) * _db_scr_dy).sum()

    # ── Row 1: KPI cards ──────────────────────────────────────────────────────
    _k1, _k2, _k3, _k4 = st.columns(4)
    _k1.metric("Current value",  f"€{_db_current:,.0f}",
               delta=f"{_db_gain_pct:+.1f}% (€{_db_gain:+,.0f})")
    _k2.metric("Total return",   f"€{_db_total_ret:,.0f}",
               delta=f"{_db_ret_pct:+.1f}%")
    if _db_fwd_income is not None:
        _k3.metric("Fwd income / yr", f"€{_db_fwd_income:,.0f}",
                   help="Estimated forward 12-month dividend income (yield × current value per holding)")
    else:
        _k3.metric("Dividends received", f"€{_db_divs:,.0f}")
    _k4.metric("Avg fair value upside",
               f"{_db_avg_mos:+.1f}%" if _db_avg_mos is not None else "—",
               help="Average margin of safety across your positions based on the fair value estimate")

    # ── Row 2: Risk banner ────────────────────────────────────────────────────
    _db_risk_cache = _load_cache()
    if _db_pf is not None and not _db_pf.empty and _db_risk_cache:
        try:
            _db_report = _risk_module.assess_portfolio(_db_pf, _db_risk_cache, False)
            _risk_score = _db_report.composite.total
            _risk_label = (
                "Low risk" if _risk_score < 35
                else "Moderate risk" if _risk_score < 65
                else "Elevated risk"
            )
            _beta_str  = f"{_db_report.quant.portfolio_beta:.2f}"
            _vol_str   = f"{_db_report.quant.volatility_annual*100:.1f}%" if _db_report.quant.volatility_annual else "—"
            _dd_str    = f"{_db_report.quant.max_drawdown*100:.1f}%" if _db_report.quant.max_drawdown else "—"
            with st.container(border=True, horizontal=True, vertical_alignment="center",
                              horizontal_alignment="distribute"):
                with st.container(width="content"):
                    st.markdown(f"**{_risk_label}** · score {_risk_score:.0f}")
                    st.caption(f"Beta **{_beta_str}** · Volatility **{_vol_str}** · "
                               f"Max drawdown **{_dd_str}**")
                st.page_link(_pg_risk, label="Full risk analysis →")
        except Exception:
            pass

    st.container(height=24, border=False)
    # ── Row 3: Today's performance + Top movers ───────────────────────────────
    _DB_ROW_H = 300  # shared height for treemap + movers table
    _hm_col, _mv_col = st.columns(2, gap="large")

    with _hm_col:
        st.subheader("Today's performance")
        _db_hm = _db_pf.dropna(subset=["name", "current_value", "day_change_pct"]).copy()
        if not _db_hm.empty:
            _clamp  = 5.0
            _normed = _db_hm["day_change_pct"].clip(-_clamp, _clamp) / _clamp
            _colors = [_hm_color(v) for v in _normed]
            _hm_labels = [
                f"<b>{row['name']}</b><br>{row['day_change_pct']:+.2f}%"
                for _, row in _db_hm.iterrows()
            ]
            _hm_hover = [
                f"<b>{row['name']}</b><br>Day: {row['day_change_pct']:+.2f}%<br>Value: €{row['current_value']:,.0f}"
                for _, row in _db_hm.iterrows()
            ]
            _hm_fig = go.Figure(go.Treemap(
                labels=_db_hm["name"].tolist(),
                parents=[""] * len(_db_hm),
                values=_db_hm["current_value"].tolist(),
                text=_hm_labels,
                customdata=_hm_hover,
                hovertemplate="%{customdata}<extra></extra>",
                textinfo="text",
                textfont=dict(color=_c_text, size=13),
                marker=dict(colors=_colors, line=dict(width=2, color=_c_surface)),
            ))
            _hm_fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                                  paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(_hm_fig, width="stretch", height=_DB_ROW_H, config=_CHART_CONFIG)
        else:
            st.caption("No daily price data available.")

    with _mv_col:
        st.subheader("Top movers today")
        _db_mv = _db_pf.dropna(subset=["name", "day_change_pct"]).copy()
        _db_mv["day_change_pct"] = pd.to_numeric(_db_mv["day_change_pct"], errors="coerce")
        _db_mv = _db_mv.dropna(subset=["day_change_pct"])
        _db_mv["_abs"] = _db_mv["day_change_pct"].abs()
        _db_top = _db_mv.sort_values("_abs", ascending=False).head(7)
        _db_top = _db_top.sort_values("day_change_pct", ascending=False)
        if not _db_top.empty:
            _db_top_disp = pd.DataFrame({
                "Company":  _db_top["name"].values,
                "Day %":    _db_top["day_change_pct"].map(lambda v: f"{v:+.2f}%"),
                "Value":    _db_top["current_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            })
            _mv_row_h = len(_db_top_disp) * 35 + 38
            st.container(height=10, border=False)
            st.dataframe(_db_top_disp, hide_index=True, width="stretch", height=_mv_row_h,
                         column_config={"Day %": st.column_config.TextColumn("Day %")})
        else:
            st.caption("No daily price data available.")

    st.container(height=24, border=False)
    # ── Row 4: Sector allocation + Upcoming dividends ─────────────────────────
    _al_col, _div_col = st.columns(2, gap="large")

    with _al_col:
        st.subheader("Sector allocation")
        _db_al = (
            _db_pf.dropna(subset=["current_value"])
              .assign(sector=_db_pf["sector"].fillna("Unknown"))
              .groupby("sector")["current_value"].sum()
              .sort_values(ascending=False)
        )
        _donut_chart(_db_al)

    with _div_col:
        st.subheader("Upcoming dividends")
        if not _db_scr.empty:
            _db_div_scr = _db_scr.copy()
            _db_div_scr["exDividendDate"] = pd.to_datetime(
                _db_div_scr.get("exDividendDate"), errors="coerce", dayfirst=True)
            _today = pd.Timestamp.today().normalize()
            _has_dates = _db_div_scr["exDividendDate"].notna().any()
            if _has_dates:
                _db_upcoming = (
                    _db_div_scr[_db_div_scr["exDividendDate"] >= _today]
                      .sort_values("exDividendDate")
                      .head(6)
                )
                if not _db_upcoming.empty:
                    _db_div_disp = pd.DataFrame({
                        "Company":  _db_upcoming["Name"].values,
                        "Ex-date":  _db_upcoming["exDividendDate"].dt.strftime("%d-%m-%Y"),
                        "Yield":    pd.to_numeric(_db_upcoming.get("dividendYield", pd.Series()), errors="coerce")
                                      .map(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
                    })
                    st.container(height=10, border=False)
                    st.dataframe(_db_div_disp, hide_index=True, width="stretch",
                                 height=len(_db_div_disp) * 35 + 38)
                else:
                    st.caption("No upcoming ex-dividend dates in the next 30 days.")
            else:
                st.caption("Ex-dividend dates not yet in cache — click Refresh in the screener.")
        else:
            st.caption("No screener data available for your holdings.")

    st.container(height=24, border=False)
    # ── Row 5: Portfolio value over time (full width) ─────────────────────────
    st.subheader("Portfolio value over time")
    _db_vh = load_value_history()
    if _db_vh is not None and not _db_vh.empty and len(_db_vh) >= 2:
        _db_vh["date"]     = pd.to_datetime(_db_vh["date"])
        _db_vh["value"]    = pd.to_numeric(_db_vh["value"],    errors="coerce")
        _db_vh["invested"] = pd.to_numeric(_db_vh["invested"], errors="coerce")
        _db_vh = _db_vh.dropna(subset=["date", "value"]).sort_values("date")

        _db_has_spx   = "benchmark_spx"   in _db_vh.columns and _db_vh["benchmark_spx"].notna().any()
        _db_has_stoxx = "benchmark_stoxx" in _db_vh.columns and _db_vh["benchmark_stoxx"].notna().any()

        if _db_has_spx or _db_has_stoxx:
            _db_cb = st.columns([1, 1, 5])
            _db_show_spx   = _db_cb[0].checkbox("S&P 500",      value=False, key="db_show_spx",   disabled=not _db_has_spx)
            _db_show_stoxx = _db_cb[1].checkbox("Euro Stoxx 50", value=False, key="db_show_stoxx", disabled=not _db_has_stoxx)
        else:
            _db_show_spx = _db_show_stoxx = False

        _db_vfig = go.Figure()
        _db_vfig.add_trace(go.Scatter(
            x=_db_vh["date"], y=_db_vh["value"],
            mode="lines", name="Portfolio value",
            line=dict(color="#1DD6A4", width=2),
            fill="tozeroy", fillcolor="rgba(29,214,164,0.07)",
        ))
        _db_vfig.add_trace(go.Scatter(
            x=_db_vh["date"], y=_db_vh["invested"],
            mode="lines", name="Amount invested",
            line=dict(color=_c_invested, width=1.5, dash="dot"),
        ))
        if _db_has_spx and _db_show_spx:
            _db_vfig.add_trace(go.Scatter(
                x=_db_vh["date"], y=pd.to_numeric(_db_vh["benchmark_spx"], errors="coerce"),
                mode="lines", name="S&P 500 (same invested)",
                line=dict(color="#5B8FA8", width=1.5, dash="dash"),
            ))
        if _db_has_stoxx and _db_show_stoxx:
            _db_vfig.add_trace(go.Scatter(
                x=_db_vh["date"], y=pd.to_numeric(_db_vh["benchmark_stoxx"], errors="coerce"),
                mode="lines", name="Euro Stoxx 50 (same invested)",
                line=dict(color="#8BA888", width=1.5, dash="dash"),
            ))
        _db_vfig.update_layout(
            margin=dict(l=0, r=0, t=8, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                        font=dict(color=_c_axis)),
            yaxis=dict(tickprefix="€", tickformat=",.0f",
                       tickfont=dict(color=_c_axis), gridcolor=_c_grid),
            xaxis=dict(showgrid=False, tickfont=dict(color=_c_axis)),
            hovermode="x unified",
            font=dict(color=_c_axis),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(_db_vfig, width="stretch", config=_CHART_CONFIG)
    else:
        st.caption("No history yet — go to Portfolio → Positions and click **Rebuild history**.")
