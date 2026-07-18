"""Dashboard page — portfolio overview matching the Uvalu.dc.html mockup:
KPI strip, value chart + conviction/risk card, holdings fair-value ladder,
sector allocation, upcoming dividends, top movers."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import risk as _risk_module
from portfolio import portfolio_exists, load_portfolio, load_value_history
from screener import _load_cache
from settings import load_shared_settings, get_veto_thresholds, ALL_EXCHANGES
from uvalu.data import _load_all_screener_data, _cache_version, _fetch_prices_cached
from uvalu.dialogs import add_position_dialog
from uvalu.formatting import safe_pct as _safe_pct, fmt_eur as _fmt_eur
from uvalu.runtime import theme_colors, current_user
from uvalu.components import (signal_badge_for_decision, signal_badge_html,
                              fair_value_bar_compact, fair_value_legend_row, radial_gauge_svg,
                              kpi_card as _kpi_card)
from uvalu.ui import _donut_chart, _CHART_CONFIG

_RANGES = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "All": None}


def render() -> None:
    from uvalu import nav
    _pg_screener = nav.pages["screener"]
    _pg_settings = nav.pages["settings"]
    _C = theme_colors()
    _c_axis, _c_grid, _c_invested = _C.axis, _C.grid, _C.invested

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

    _db_tickers = _db_pf["ticker"].dropna().astype(str).str.strip().tolist()
    _db_prices  = _fetch_prices_cached(tuple(_db_tickers))
    for _col, _key in [("live_price", "price"), ("day_change_pct", "day_change_pct"),
                        ("prev_close", "prev_close")]:
        _db_pf[_col] = _db_pf["ticker"].map(lambda t, k=_key: _db_prices.get(t, {}).get(k))

    _db_pf["purchase_value"] = pd.to_numeric(_db_pf["purchase_value"], errors="coerce")
    _db_pf["shares"]         = pd.to_numeric(_db_pf["shares"],         errors="coerce")
    _db_pf["live_price"]     = pd.to_numeric(_db_pf["live_price"],     errors="coerce")
    _db_pf["dividends"]      = pd.to_numeric(_db_pf["dividends"],      errors="coerce").fillna(0)

    _db_cost = _db_pf["purchase_value"].where(_db_pf["purchase_value"] > 0)
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

    _db_enabled = tuple(load_shared_settings().get("enabled_exchanges", ALL_EXCHANGES))
    _db_all_scr = pd.concat(list(_load_all_screener_data(
        _cache_version(), _db_enabled, thresholds=get_veto_thresholds())[:-1]), ignore_index=True)
    _db_scr = _db_all_scr[_db_all_scr["Ticker"].isin(_db_tickers)].copy()
    _db_mos_vals = pd.to_numeric(_db_scr.get("MoS %", pd.Series(dtype=float)), errors="coerce").dropna()
    _db_avg_mos  = _db_mos_vals.mean() if not _db_mos_vals.empty else None

    _db_fwd_income = None
    if not _db_scr.empty and "dividendYield" in _db_scr.columns:
        _db_pf_cv = _db_pf.set_index("ticker")["current_value"]
        _db_scr_dy = pd.to_numeric(_db_scr.set_index("Ticker")["dividendYield"], errors="coerce").fillna(0)
        _db_fwd_income = (_db_pf_cv.reindex(_db_scr_dy.index).fillna(0) * _db_scr_dy).sum()

    # ── Heading ───────────────────────────────────────────────────────────────
    _n_exch = len({t.split(".")[-1] for t in _db_tickers if "." in t})
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
        with st.container(width="content"):
            st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Portfolio overview</div>',
                       unsafe_allow_html=True)
            st.caption(f"{len(_db_pf)} positions across {_n_exch} European "
                      f"{'exchange' if _n_exch == 1 else 'exchanges'} · "
                      "valued against a six-model fair-value estimate.")
        with st.container(horizontal=True, gap="small", width="content"):
            if st.button("Refresh", key="db_refresh"):
                st.cache_data.clear()
                st.rerun()
            _is_viewer = current_user().is_viewer
            if st.button("Buy", key="db_buy", type="primary", disabled=_is_viewer,
                        help="Viewer role is read-only" if _is_viewer else None):
                add_position_dialog()

    # ── KPI strip ─────────────────────────────────────────────────────────────
    _k1, _k2, _k3, _k4 = st.columns(4)
    with _k1:
        _kpi_card("Current value", f"€{_db_current:,.0f}",
                 f"{_db_gain_pct:+.1f}%", _db_gain >= 0, f"€{_db_gain:+,.0f} unrealised", icon="wallet")
    with _k2:
        _kpi_card("Total return", f"€{_db_total_ret:,.0f}",
                 f"{_db_ret_pct:+.1f}%", _db_total_ret >= 0, "incl. dividends", icon="trend")
    with _k3:
        if _db_fwd_income is not None:
            _db_blended_yield = _safe_pct(_db_fwd_income, _db_current)
            _kpi_card("Fwd income / yr", f"€{_db_fwd_income:,.0f}",
                     f"{_db_blended_yield:.1f}%", True, "blended yield", icon="coin")
        else:
            _kpi_card("Dividends received", f"€{_db_divs:,.0f}", "", True, "", icon="coin")
    with _k4:
        _kpi_card("Avg fair value upside",
                 f"{_db_avg_mos:+.1f}%" if _db_avg_mos is not None else "—",
                 "", (_db_avg_mos or 0) >= 0, "margin of safety", icon="target")

    st.container(height=4, border=False, key="db_gap_1")

    # ── Value chart + Conviction & risk ───────────────────────────────────────
    _chart_col, _conv_col = st.columns([1.62, 1], gap="large")

    with _chart_col, st.container(key="db_card_chart", border=True):
        _db_vh = load_value_history()
        if _db_vh is not None and not _db_vh.empty and len(_db_vh) >= 2:
            _db_vh["date"]     = pd.to_datetime(_db_vh["date"])
            _db_vh["value"]    = pd.to_numeric(_db_vh["value"],    errors="coerce")
            _db_vh["invested"] = pd.to_numeric(_db_vh["invested"], errors="coerce")
            _db_vh = _db_vh.dropna(subset=["date", "value"]).sort_values("date")

            _title_col, _range_col = st.columns([2, 2], vertical_alignment="bottom")
            with _range_col:
                _range_sel = st.segmented_control("Range", options=list(_RANGES.keys()), default="All",
                                                  key="db_range", label_visibility="collapsed")
            _days = _RANGES.get(_range_sel or "All")
            _vh_view = _db_vh
            if _days is not None:
                _cutoff = _db_vh["date"].max() - pd.Timedelta(days=_days)
                _vh_view = _db_vh[_db_vh["date"] >= _cutoff]

            _db_last_val   = float(_vh_view["value"].iloc[-1])
            _db_first_val  = float(_vh_view["value"].iloc[0])
            _db_range_pct  = _safe_pct(_db_last_val - _db_first_val, _db_first_val)
            _db_range_color = "var(--up-txt)" if _db_range_pct >= 0 else "var(--down-txt)"
            with _title_col:
                st.markdown(f"""
<div style="font-size:15px;font-weight:500;">Portfolio value over time</div>
<div style="display:flex;align-items:baseline;gap:10px;margin-top:4px;">
  <span style="font-family:var(--uv-mono);font-size:20px;font-weight:500;letter-spacing:-0.02em;">€{_db_last_val:,.0f}</span>
  <span style="color:{_db_range_color};font-size:12px;font-weight:500;">{_db_range_pct:+.1f}%</span>
  <span style="font-size:11px;color:var(--faint);">{_range_sel or "All"}</span>
</div>""", unsafe_allow_html=True)

            _db_has_spx   = "benchmark_spx"   in _vh_view.columns and _vh_view["benchmark_spx"].notna().any()
            _db_has_stoxx = "benchmark_stoxx" in _vh_view.columns and _vh_view["benchmark_stoxx"].notna().any()

            _db_bench_opts = ([("S&P 500")] if _db_has_spx else []) + (["Euro Stoxx 50"] if _db_has_stoxx else [])
            _db_bench_default = [o for o in
                                 (["Euro Stoxx 50"] if load_shared_settings().get("benchmark_stoxx", False) else [])
                                 if o in _db_bench_opts]
            _db_bench_sel = st.session_state.get("db_bench_pills", _db_bench_default)
            _db_show_spx   = "S&P 500" in _db_bench_sel
            _db_show_stoxx = "Euro Stoxx 50" in _db_bench_sel

            _db_vfig = go.Figure()
            _db_vfig.add_trace(go.Scatter(
                x=_vh_view["date"], y=_vh_view["value"], mode="lines", name="Portfolio value",
                line=dict(color="#1DD6A4", width=2), fill="tozeroy", fillcolor="rgba(29,214,164,0.07)"))
            _db_vfig.add_trace(go.Scatter(
                x=_vh_view["date"], y=_vh_view["invested"], mode="lines", name="Amount invested",
                line=dict(color=_c_invested, width=1.5, dash="dot")))
            if _db_has_spx:
                _db_vfig.add_trace(go.Scatter(
                    x=_vh_view["date"], y=pd.to_numeric(_vh_view["benchmark_spx"], errors="coerce"),
                    mode="lines", name="S&P 500 (same invested)", line=dict(color="#5B8FA8", width=1.5, dash="dash"),
                    visible=True if _db_show_spx else "legendonly"))
            if _db_has_stoxx:
                _db_vfig.add_trace(go.Scatter(
                    x=_vh_view["date"], y=pd.to_numeric(_vh_view["benchmark_stoxx"], errors="coerce"),
                    mode="lines", name="Euro Stoxx 50 (same invested)", line=dict(color="#8BA888", width=1.5, dash="dash"),
                    visible=True if _db_show_stoxx else "legendonly"))
            _db_vfig.update_layout(
                margin=dict(l=0, r=0, t=16, b=0),
                showlegend=False,
                yaxis=dict(tickprefix="€", tickformat=",.0f", tickfont=dict(color=_c_axis), gridcolor=_c_grid),
                xaxis=dict(showgrid=False, tickfont=dict(color=_c_axis)),
                hovermode="x unified", font=dict(color=_c_axis),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(_db_vfig, width="stretch", height=250, config=_CHART_CONFIG)

            # ── Unified legend bar — swatches for the two always-on series,
            # plus clickable chip toggles (st.pills, same idiom as the
            # Screener's Signal/Hide-owned chips) for the optional benchmarks
            # — one legend row matching Uvalu.dc.html's benchChip toggles
            # instead of a separate native-checkbox row. ──
            with st.container(key="db_chart_legend_row", horizontal=True,
                              vertical_alignment="center", horizontal_alignment="distribute"):
                with st.container(width="content"):
                    st.markdown("""
<div style="display:flex;align-items:center;gap:18px;">
  <div style="display:flex;align-items:center;gap:7px;font-size:11.5px;color:var(--muted);">
    <span style="width:14px;height:2px;background:var(--mint);border-radius:2px;display:inline-block;"></span>Portfolio value</div>
  <div style="display:flex;align-items:center;gap:7px;font-size:11.5px;color:var(--muted);">
    <span style="width:14px;height:0;border-top:1.4px dashed var(--axis);display:inline-block;"></span>Amount invested</div>
</div>""", unsafe_allow_html=True)
                if _db_bench_opts:
                    with st.container(width="content"):
                        st.pills("Benchmarks", options=_db_bench_opts, selection_mode="multi",
                                default=_db_bench_default, key="db_bench_pills",
                                label_visibility="collapsed")
        else:
            st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:6px;">Portfolio value over time</div>',
                       unsafe_allow_html=True)
            st.caption("No history yet — go to Portfolio → Positions and click **Rebuild history**.")

    with _conv_col, st.container(key="db_card_conviction", border=True):
        _cvh_col, _cvh_link_col = st.columns([2, 1], vertical_alignment="top")
        with _cvh_col:
            st.markdown('<div style="font-size:15px;font-weight:500;">Conviction &amp; risk</div>',
                       unsafe_allow_html=True)
        with _cvh_link_col:
            if st.button("Full analysis →", key="db_conv_full_analysis", type="tertiary", width="stretch"):
                st.switch_page(nav.pages["risk"])
        st.container(height=4, border=False)
        _conv_score = None
        if not _db_scr.empty and "Value Score" in _db_scr.columns:
            _scr_cv = _db_pf.set_index("ticker")["current_value"]
            _scr_vs = pd.to_numeric(_db_scr.set_index("Ticker")["Value Score"], errors="coerce")
            _w = _scr_cv.reindex(_scr_vs.index).fillna(0)
            if _w.sum() > 0:
                _conv_score = float((_scr_vs.fillna(0) * _w).sum() / _w.sum())
        _n_veto = int(_db_scr.get("veto", pd.Series(dtype=bool)).fillna(False).sum()) if "veto" in _db_scr.columns else 0

        _db_risk_cache = _load_cache()
        _risk_score = _beta_str = _vol_str = _dd_str = None
        _risk_label = "—"
        if _db_pf is not None and not _db_pf.empty and _db_risk_cache:
            try:
                _db_report = _risk_module.assess_portfolio(_db_pf, _db_risk_cache, False)
                _risk_score = float(_db_report.composite.total)
                _risk_label = ("Low" if _risk_score < 35 else "Moderate" if _risk_score < 65 else "Elevated")
                _beta_str = f"{_db_report.quant.portfolio_beta:.2f}"
                _vol_str  = f"{_db_report.quant.volatility_annual*100:.1f}%" if _db_report.quant.volatility_annual else "—"
                _dd_str   = f"{_db_report.quant.max_drawdown*100:.1f}%" if _db_report.quant.max_drawdown else "—"
            except Exception:
                pass

        with st.container(horizontal=True, gap="medium", vertical_alignment="center"):
            if _conv_score is not None:
                if _conv_score >= 70:
                    _conv_rating, _conv_rating_color = "Strong conviction", "var(--up-txt)"
                elif _conv_score >= 40:
                    _conv_rating, _conv_rating_color = "Moderate conviction", "#C98A3A"
                else:
                    _conv_rating, _conv_rating_color = "Weak conviction", "var(--down-txt)"
                st.markdown(f"""
<div style="position:relative;width:118px;height:118px;flex:none;">
  {radial_gauge_svg(_conv_score, "#1DD6A4", size=118)}
  <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
    <span style="font-family:var(--uv-mono);font-size:27px;font-weight:500;color:var(--text);">{_conv_score:.0f}</span>
    <span style="font-size:9.5px;color:var(--faint);">/ 100</span>
  </div>
</div>""", unsafe_allow_html=True)
                st.markdown(f"""
<div style="font-size:12px;color:var(--faint);text-transform:uppercase;letter-spacing:0.06em;">Composite conviction</div>
<div style="font-size:15px;font-weight:500;margin-top:4px;color:{_conv_rating_color};">{_conv_rating}</div>
<div style="font-size:12px;color:var(--muted);margin-top:8px;line-height:1.5;">Weighted mean signal score across scored holdings.
{f" {_n_veto} position(s) under hard veto." if _n_veto else ""}</div>""", unsafe_allow_html=True)
            else:
                st.caption("Not enough scored holdings for a conviction score.")

        if _risk_score is not None:
            st.container(height=10, border=False)
            _marker_pct = min(100.0, max(0.0, _risk_score))
            _risk_num_color = ("var(--up-txt)" if _risk_score < 35 else
                               "#C98A3A" if _risk_score < 65 else "var(--down-txt)")
            st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;">
  <span style="font-size:12px;color:var(--muted);">Portfolio risk score</span>
  <span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;">
    <span style="color:{_risk_num_color};">{_risk_score:.0f}</span> · {_risk_label}</span>
</div>
<div style="height:7px;border-radius:4px;background:linear-gradient(90deg,#1DD6A4 0%,#1DD6A4 33%,#C98A3A 33%,#C98A3A 66%,#A32D2D 66%,#A32D2D 100%);position:relative;opacity:0.85;">
  <div style="position:absolute;left:{_marker_pct:.1f}%;top:-3px;width:2px;height:13px;background:var(--text);"></div>
</div>
<div style="display:flex;justify-content:space-between;font-size:9.5px;color:var(--faint);margin-top:5px;">
  <span>LOW</span><span>MODERATE</span><span>ELEVATED</span>
</div>""", unsafe_allow_html=True)

            st.container(height=12, border=False)
            _m1, _m2, _m3 = st.columns(3)
            with _m1:
                st.caption("Beta")
                st.markdown(f'<span style="font-family:var(--uv-mono);font-size:15px;">{_beta_str}</span>', unsafe_allow_html=True)
            with _m2:
                st.caption("Volatility")
                st.markdown(f'<span style="font-family:var(--uv-mono);font-size:15px;">{_vol_str}</span>', unsafe_allow_html=True)
            with _m3:
                st.caption("Max drawdown")
                st.markdown(f'<span style="font-family:var(--uv-mono);font-size:15px;color:var(--down-txt);">{_dd_str}</span>', unsafe_allow_html=True)

    st.container(height=4, border=False, key="db_gap_2")

    # ── Holdings · price vs fair value ────────────────────────────────────────
    _hold_title_col, _hold_legend_col = st.columns([2, 2], vertical_alignment="center")
    with _hold_title_col:
        st.markdown('<div style="font-size:15px;font-weight:500;">Holdings · price vs fair value</div>',
                   unsafe_allow_html=True)
    with _hold_legend_col:
        fair_value_legend_row()
    if not _db_scr.empty:
        _hold = _db_pf.merge(_db_scr, left_on="ticker", right_on="Ticker", how="left", suffixes=("", "_scr"))
        _hold["weight"] = _hold["current_value"] / _db_current if _db_current else 0
        _hold = _hold.sort_values("current_value", ascending=False)

        _hh1, _hh2, _hh3, _hh4, _hh5, _hh6, _hh7 = st.columns(
            [2.0, 0.8, 2.2, 0.7, 0.7, 0.8, 0.7], vertical_alignment="center")
        for _hh, _label in zip((_hh1, _hh2, _hh3, _hh4, _hh5, _hh6, _hh7),
                               ("Position", "Signal", "Fair-value ladder", "Upside", "Weight", "Value", "Today")):
            with _hh:
                st.markdown(f'<span style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                           f'color:var(--faint);">{_label}</span>', unsafe_allow_html=True)

        for _hidx, _hr in _hold.reset_index(drop=True).iterrows():
            # Keyed by row position, not ticker — the same ticker can appear in
            # two rows if a user bought it in separate lots (add_position()
            # appends rather than merging), which would otherwise collide.
            with st.container(key=f"db_hold_{_hidx}", border=True):
                _hc1, _hc2, _hc3, _hc4, _hc5, _hc6, _hc7 = st.columns(
                    [2.0, 0.8, 2.2, 0.7, 0.7, 0.8, 0.7], vertical_alignment="center")
                with _hc1:
                    _sector = _hr.get("sector")
                    _sector_html = (f"<span style='font-size:9.5px;color:var(--muted);border:0.5px solid "
                                   f"var(--line);border-radius:5px;padding:1px 6px;margin-left:6px;'>{_sector}</span>"
                                   if _sector and pd.notna(_sector) else "")
                    st.markdown(f"<span style='font-family:var(--uv-mono);font-size:13px;font-weight:500;'>"
                               f"{_hr.get('ticker', '')}</span>{_sector_html}<br>"
                               f"<span style='color:var(--muted);font-size:12px;'>{_hr.get('name', '')}</span>",
                               unsafe_allow_html=True)
                with _hc2:
                    _kind, _label = signal_badge_for_decision(str(_hr.get("Decision", "")), veto=bool(_hr.get("veto")))
                    st.markdown(signal_badge_html(_kind, _label), unsafe_allow_html=True)
                with _hc3:
                    fair_value_bar_compact(_hr.get("live_price"), _hr.get("fair_value"), _hr.get("MoS %"))
                with _hc4:
                    _mos = _hr.get("MoS %")
                    _mos = float(_mos) if _mos is not None and pd.notna(_mos) else None
                    _mos_color = "var(--up-txt)" if (_mos or 0) >= 0 else "var(--down-txt)"
                    st.markdown(f"<span style='font-family:var(--uv-mono);font-size:13px;font-weight:500;"
                               f"color:{_mos_color};'>{_mos:+.1f}%</span>" if _mos is not None else "—",
                               unsafe_allow_html=True)
                with _hc5:
                    _w = _hr.get("weight", 0)
                    _w = float(_w) if _w is not None and pd.notna(_w) else 0.0
                    st.caption(f"{_w*100:.1f}%")
                with _hc6:
                    _cv = _hr.get("current_value")
                    _cv = float(_cv) if _cv is not None and pd.notna(_cv) else 0.0
                    st.markdown(f"<span style='font-family:var(--uv-mono);'>{_fmt_eur(_cv)}</span>",
                               unsafe_allow_html=True)
                with _hc7:
                    _day = _hr.get("day_change_pct")
                    _day = float(_day) if _day is not None and pd.notna(_day) else None
                    if _day is not None:
                        _day_color = "var(--up-txt)" if _day >= 0 else "var(--down-txt)"
                        st.markdown(f"<span style='font-family:var(--uv-mono);font-size:12.5px;"
                                   f"color:{_day_color};'>{_day:+.2f}%</span>", unsafe_allow_html=True)
                    else:
                        st.caption("—")
    else:
        st.caption("No screener data available for your holdings.")

    st.container(height=4, border=False, key="db_gap_3")

    # ── Bottom row: sector allocation | upcoming dividends | top movers ──────
    _al_col, _div_col, _mv_col = st.columns(3, gap="large")

    with _al_col, st.container(key="db_card_sector", border=True):
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:8px;">Sector allocation</div>',
                   unsafe_allow_html=True)
        _db_sector_map = (
            _db_scr.drop_duplicates("Ticker").set_index("Ticker")["sector"]
            if not _db_scr.empty and "sector" in _db_scr.columns else pd.Series(dtype=object)
        )
        _db_al = (
            _db_pf.dropna(subset=["current_value"])
              .assign(sector=_db_pf["ticker"].map(_db_sector_map).fillna("Unknown"))
              .groupby("sector")["current_value"].sum()
              .sort_values(ascending=False)
        )
        _donut_chart(_db_al)

    with _div_col, st.container(key="db_card_dividends", border=True):
        _dh_title_col, _dh_total_col = st.columns([2, 1.4], vertical_alignment="center")
        with _dh_title_col:
            st.markdown('<div style="font-size:15px;font-weight:500;">Upcoming dividends</div>',
                       unsafe_allow_html=True)
        with _dh_total_col:
            if _db_fwd_income is not None:
                st.markdown(f'<div style="text-align:right;font-family:var(--uv-mono);font-size:13px;'
                           f'color:var(--mint);">€{_db_fwd_income:,.0f} / yr</div>', unsafe_allow_html=True)
        if not _db_scr.empty:
            _db_div_scr = _db_scr.copy()
            _db_div_scr["exDividendDate"] = pd.to_datetime(
                _db_div_scr.get("exDividendDate"), errors="coerce", dayfirst=True)
            _today = pd.Timestamp.today().normalize()
            if _db_div_scr["exDividendDate"].notna().any():
                _db_upcoming = (
                    _db_div_scr[_db_div_scr["exDividendDate"] >= _today]
                      .sort_values("exDividendDate").head(6)
                )
                if not _db_upcoming.empty:
                    _db_shares_map = _db_pf.set_index("ticker")["shares"]
                    _db_upcoming = _db_upcoming.assign(
                        _shares=_db_upcoming["Ticker"].map(_db_shares_map).fillna(0),
                        _rate=pd.to_numeric(_db_upcoming.get("dividendRate"), errors="coerce").fillna(0),
                    )
                    for _, _dr in _db_upcoming.iterrows():
                        _amount = float(_dr["_shares"]) * float(_dr["_rate"])
                        _yld = _dr.get("dividendYield")
                        _yld_str = f"{float(_yld)*100:.2f}%" if pd.notna(_yld) else "—"
                        st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;">
  <div>
    <div style="font-size:12.5px;">{_dr['Name']}</div>
    <div style="font-size:11px;color:var(--faint);">{_dr['exDividendDate'].strftime('%d-%m-%Y')} · {_yld_str} yield</div>
  </div>
  <span style="font-family:var(--uv-mono);font-size:12.5px;color:var(--mint);">€{_amount:,.0f}</span>
</div>""", unsafe_allow_html=True)
                else:
                    st.caption("No upcoming ex-dividend dates in the next 30 days.")
            else:
                st.caption("Ex-dividend dates not yet in cache — click Refresh in the screener.")
        else:
            st.caption("No screener data available for your holdings.")

    with _mv_col, st.container(key="db_card_movers", border=True):
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:8px;">Top movers today</div>',
                   unsafe_allow_html=True)
        _db_mv = _db_pf.dropna(subset=["name", "day_change_pct"]).copy()
        _db_mv["day_change_pct"] = pd.to_numeric(_db_mv["day_change_pct"], errors="coerce")
        _db_mv = _db_mv.dropna(subset=["day_change_pct"])
        _db_mv["_abs"] = _db_mv["day_change_pct"].abs()
        _db_top = _db_mv.sort_values("_abs", ascending=False).head(6).sort_values("day_change_pct", ascending=False)
        if not _db_top.empty:
            _mv_max = float(_db_top["_abs"].max()) or 1.0
            for _, _mr in _db_top.iterrows():
                _pos = _mr["day_change_pct"] >= 0
                _color = "var(--up-txt)" if _pos else "var(--down-txt)"
                _bar_pct = min(100.0, abs(_mr["day_change_pct"]) / _mv_max * 100)
                st.markdown(f"""
<div style="display:flex;align-items:center;gap:9px;padding:5px 0;font-size:12.5px;">
  <span style="font-family:var(--uv-mono);color:var(--faint);width:64px;flex:none;white-space:nowrap;">{_mr['ticker']}</span>
  <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_mr['name']}</span>
  <span style="width:36px;height:5px;border-radius:3px;background:var(--line-2);position:relative;flex:none;">
    <span style="position:absolute;left:0;top:0;height:5px;border-radius:3px;background:{_color};width:{_bar_pct:.0f}%;"></span>
  </span>
  <span style="color:{_color};font-family:var(--uv-mono);width:58px;text-align:right;flex:none;">{_mr['day_change_pct']:+.2f}%</span>
</div>""", unsafe_allow_html=True)
        else:
            st.caption("No daily price data available.")
