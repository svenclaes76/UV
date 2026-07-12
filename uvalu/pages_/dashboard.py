"""Dashboard page — portfolio overview matching the Uvalu.dc.html mockup:
KPI strip, value chart + conviction/risk card, holdings fair-value ladder,
sector allocation, upcoming dividends, top movers."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import risk as _risk_module
from portfolio import portfolio_exists, load_portfolio, load_value_history, add_position
from screener import _load_cache
from settings import load_shared_settings, get_veto_thresholds, ALL_EXCHANGES
from uvalu.data import _load_all_screener_data, _cache_version, _fetch_prices_cached
from uvalu.formatting import safe_pct as _safe_pct, fmt_eur as _fmt_eur
from uvalu.runtime import theme_colors, current_user
from uvalu.components import (signal_badge_for_decision, signal_badge_html,
                              fair_value_bar_compact, score_color, radial_gauge_svg)
from uvalu.ui import _donut_chart, _CHART_CONFIG

_RANGES = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "All": None}


def _kpi_card(label: str, value: str, delta_text: str, positive: bool, sub: str) -> None:
    color = "var(--up-txt)" if positive else "var(--down-txt)"
    st.markdown(f"""
<div style="background:var(--panel);border:0.5px solid var(--line);border-radius:12px;padding:15px 17px;box-shadow:var(--shadow);">
  <div style="font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--faint);font-weight:500;">{label}</div>
  <div style="font-family:var(--uv-mono);font-size:26px;font-weight:500;letter-spacing:-0.02em;margin-top:10px;line-height:1;color:var(--text);">{value}</div>
  <div style="margin-top:9px;display:flex;align-items:center;gap:8px;">
    <span style="color:{color};font-size:12px;font-weight:500;">{delta_text}</span>
    <span style="font-size:11px;color:var(--faint);">{sub}</span>
  </div>
</div>""", unsafe_allow_html=True)


@st.dialog("Buy stock", width="large")
def _dlg_dashboard_buy(t_opts, t_labels, price_map):
    _c1, _c2, _c3, _c4 = st.columns([3, 1, 2, 2])
    with _c1:
        ticker = st.selectbox("Company", options=t_opts, format_func=lambda t: t_labels.get(t, t))
    with _c2:
        shares = st.number_input("Shares", min_value=1, step=1, value=1)
    with _c3:
        pur_date = st.date_input("Buy Date", format="DD/MM/YYYY")
    with _c4:
        _price = float(price_map.get(ticker) or 0.0)
        total_price = st.number_input("Invested (€)", min_value=0.0, step=0.01,
                                      value=round(_price * shares, 2), format="%.2f")
    _, _save_col = st.columns([3, 1])
    with _save_col:
        _do_save = st.button("Save", key="dlg_buy_dash_save", width="stretch")
    if _do_save and shares > 0 and total_price > 0:
        name = t_labels.get(ticker, ticker).split("  (")[0]
        add_position({
            "name": name, "google_ticker": "", "ticker": ticker, "shares": shares,
            "purchase_price": round(total_price / shares, 4), "purchase_value": round(total_price, 2),
            "target_price": None, "dividends": 0.0,
            "date_in": pd.Timestamp(pur_date).isoformat(), "account": "",
        })
        st.rerun()


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
            st.caption(f"{len(_db_pf)} positions across {_n_exch} exchanges · "
                      "valued against a six-model fair-value estimate.")
        with st.container(horizontal=True, gap="small", width="content"):
            if st.button("Refresh", key="db_refresh"):
                st.cache_data.clear()
                st.rerun()
            _is_viewer = current_user().is_viewer
            if not _db_scr.empty and st.button("Buy", key="db_buy", type="primary", disabled=_is_viewer,
                                               help="Viewer role is read-only" if _is_viewer else None):
                _sorted = _db_all_scr[["Ticker", "Name"]].drop_duplicates("Ticker").sort_values(
                    "Name", key=lambda s: s.str.lower())
                _t_opts = _sorted["Ticker"].tolist()
                _t_labels = {r["Ticker"]: f"{r['Name']}  ({r['Ticker']})" for _, r in _sorted.iterrows()}
                _price_map = _db_all_scr.drop_duplicates("Ticker").set_index("Ticker")["Price"].to_dict()
                _dlg_dashboard_buy(_t_opts, _t_labels, _price_map)

    # ── KPI strip ─────────────────────────────────────────────────────────────
    _k1, _k2, _k3, _k4 = st.columns(4)
    with _k1:
        _kpi_card("Current value", f"€{_db_current:,.0f}",
                 f"{_db_gain_pct:+.1f}%", _db_gain >= 0, f"€{_db_gain:+,.0f}")
    with _k2:
        _kpi_card("Total return", f"€{_db_total_ret:,.0f}",
                 f"{_db_ret_pct:+.1f}%", _db_total_ret >= 0, "incl. dividends")
    with _k3:
        if _db_fwd_income is not None:
            _kpi_card("Fwd income / yr", f"€{_db_fwd_income:,.0f}", "", True, "estimated")
        else:
            _kpi_card("Dividends received", f"€{_db_divs:,.0f}", "", True, "")
    with _k4:
        _kpi_card("Avg fair value upside",
                 f"{_db_avg_mos:+.1f}%" if _db_avg_mos is not None else "—",
                 "", (_db_avg_mos or 0) >= 0, "margin of safety")

    st.container(height=18, border=False)

    # ── Value chart + Conviction & risk ───────────────────────────────────────
    _chart_col, _conv_col = st.columns([1.62, 1], gap="large")

    with _chart_col:
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:6px;">Portfolio value over time</div>',
                   unsafe_allow_html=True)
        _db_vh = load_value_history()
        if _db_vh is not None and not _db_vh.empty and len(_db_vh) >= 2:
            _db_vh["date"]     = pd.to_datetime(_db_vh["date"])
            _db_vh["value"]    = pd.to_numeric(_db_vh["value"],    errors="coerce")
            _db_vh["invested"] = pd.to_numeric(_db_vh["invested"], errors="coerce")
            _db_vh = _db_vh.dropna(subset=["date", "value"]).sort_values("date")

            _range_sel = st.segmented_control("Range", options=list(_RANGES.keys()), default="All",
                                              key="db_range", label_visibility="collapsed")
            _days = _RANGES.get(_range_sel or "All")
            _vh_view = _db_vh
            if _days is not None:
                _cutoff = _db_vh["date"].max() - pd.Timedelta(days=_days)
                _vh_view = _db_vh[_db_vh["date"] >= _cutoff]

            _db_has_spx   = "benchmark_spx"   in _vh_view.columns and _vh_view["benchmark_spx"].notna().any()
            _db_has_stoxx = "benchmark_stoxx" in _vh_view.columns and _vh_view["benchmark_stoxx"].notna().any()
            if _db_has_spx or _db_has_stoxx:
                _db_cb = st.columns([1, 1, 5])
                _db_show_spx   = _db_cb[0].checkbox("S&P 500",      value=False, key="db_show_spx",   disabled=not _db_has_spx)
                _db_show_stoxx = _db_cb[1].checkbox(
                    "Euro Stoxx 50",
                    value=bool(load_shared_settings().get("benchmark_stoxx", False)),
                    key="db_show_stoxx", disabled=not _db_has_stoxx)
            else:
                _db_show_spx = _db_show_stoxx = False

            _db_vfig = go.Figure()
            _db_vfig.add_trace(go.Scatter(
                x=_vh_view["date"], y=_vh_view["value"], mode="lines", name="Portfolio value",
                line=dict(color="#1DD6A4", width=2), fill="tozeroy", fillcolor="rgba(29,214,164,0.07)"))
            _db_vfig.add_trace(go.Scatter(
                x=_vh_view["date"], y=_vh_view["invested"], mode="lines", name="Amount invested",
                line=dict(color=_c_invested, width=1.5, dash="dot")))
            if _db_has_spx and _db_show_spx:
                _db_vfig.add_trace(go.Scatter(
                    x=_vh_view["date"], y=pd.to_numeric(_vh_view["benchmark_spx"], errors="coerce"),
                    mode="lines", name="S&P 500 (same invested)", line=dict(color="#5B8FA8", width=1.5, dash="dash")))
            if _db_has_stoxx and _db_show_stoxx:
                _db_vfig.add_trace(go.Scatter(
                    x=_vh_view["date"], y=pd.to_numeric(_vh_view["benchmark_stoxx"], errors="coerce"),
                    mode="lines", name="Euro Stoxx 50 (same invested)", line=dict(color="#8BA888", width=1.5, dash="dash")))
            _db_vfig.update_layout(
                margin=dict(l=0, r=0, t=8, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(color=_c_axis)),
                yaxis=dict(tickprefix="€", tickformat=",.0f", tickfont=dict(color=_c_axis), gridcolor=_c_grid),
                xaxis=dict(showgrid=False, tickfont=dict(color=_c_axis)),
                hovermode="x unified", font=dict(color=_c_axis),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(_db_vfig, width="stretch", height=280, config=_CHART_CONFIG)
        else:
            st.caption("No history yet — go to Portfolio → Positions and click **Rebuild history**.")

    with _conv_col:
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:10px;">Conviction &amp; risk</div>',
                   unsafe_allow_html=True)
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
                _ring_color, _ = score_color(_conv_score)
                st.markdown(f"""
<div style="position:relative;width:96px;height:96px;flex:none;">
  {radial_gauge_svg(_conv_score, "#1DD6A4", size=96)}
  <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
    <span style="font-family:var(--uv-mono);font-size:22px;font-weight:500;color:var(--text);">{_conv_score:.0f}</span>
    <span style="font-size:9px;color:var(--faint);">/ 100</span>
  </div>
</div>""", unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:12px;color:var(--muted);">Weighted mean signal score '
                           f'across scored holdings.{f" {_n_veto} position(s) under hard veto." if _n_veto else ""}</div>',
                           unsafe_allow_html=True)
            else:
                st.caption("Not enough scored holdings for a conviction score.")

        if _risk_score is not None:
            st.container(height=10, border=False)
            _marker_pct = min(100.0, max(0.0, _risk_score))
            st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;">
  <span style="font-size:12px;color:var(--muted);">Portfolio risk score</span>
  <span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;">{_risk_score:.0f} · {_risk_label}</span>
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

    st.container(height=18, border=False)

    # ── Holdings · price vs fair value ────────────────────────────────────────
    st.markdown('<div style="font-size:15px;font-weight:500;">Holdings · price vs fair value</div>',
               unsafe_allow_html=True)
    if not _db_scr.empty:
        _hold = _db_pf.merge(_db_scr, left_on="ticker", right_on="Ticker", how="left", suffixes=("", "_scr"))
        _hold["weight"] = _hold["current_value"] / _db_current if _db_current else 0
        _hold = _hold.sort_values("current_value", ascending=False)
        for _, _hr in _hold.iterrows():
            with st.container(key=f"db_hold_{_hr.get('ticker', '')}", border=True):
                _hc1, _hc2, _hc3, _hc4, _hc5 = st.columns([2.2, 0.9, 2.4, 0.9, 0.9], vertical_alignment="center")
                with _hc1:
                    st.markdown(f"**{_hr.get('name', _hr.get('ticker'))}**  "
                               f"<span style='color:var(--faint);font-size:11px;'>{_hr.get('ticker', '')}</span>",
                               unsafe_allow_html=True)
                with _hc2:
                    _kind, _label = signal_badge_for_decision(str(_hr.get("Decision", "")), veto=bool(_hr.get("veto")))
                    st.markdown(signal_badge_html(_kind, _label), unsafe_allow_html=True)
                with _hc3:
                    fair_value_bar_compact(_hr.get("live_price"), _hr.get("fair_value"), _hr.get("MoS %"))
                with _hc4:
                    st.caption(f"{_hr.get('weight', 0)*100:.1f}% weight")
                with _hc5:
                    st.markdown(f"<span style='font-family:var(--uv-mono);'>{_fmt_eur(_hr.get('current_value') or 0)}</span>",
                               unsafe_allow_html=True)
    else:
        st.caption("No screener data available for your holdings.")

    st.container(height=18, border=False)

    # ── Bottom row: sector allocation | upcoming dividends | top movers ──────
    _al_col, _div_col, _mv_col = st.columns(3, gap="large")

    with _al_col:
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

    with _div_col:
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:8px;">Upcoming dividends</div>',
                   unsafe_allow_html=True)
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
                    _db_div_disp = pd.DataFrame({
                        "Company":  _db_upcoming["Name"].values,
                        "Ex-date":  _db_upcoming["exDividendDate"].dt.strftime("%d-%m-%Y"),
                        "Yield":    pd.to_numeric(_db_upcoming.get("dividendYield", pd.Series()), errors="coerce")
                                      .map(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
                    })
                    st.dataframe(_db_div_disp, hide_index=True, width="stretch",
                                height=len(_db_div_disp) * 35 + 38)
                else:
                    st.caption("No upcoming ex-dividend dates in the next 30 days.")
            else:
                st.caption("Ex-dividend dates not yet in cache — click Refresh in the screener.")
        else:
            st.caption("No screener data available for your holdings.")

    with _mv_col:
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:8px;">Top movers today</div>',
                   unsafe_allow_html=True)
        _db_mv = _db_pf.dropna(subset=["name", "day_change_pct"]).copy()
        _db_mv["day_change_pct"] = pd.to_numeric(_db_mv["day_change_pct"], errors="coerce")
        _db_mv = _db_mv.dropna(subset=["day_change_pct"])
        _db_mv["_abs"] = _db_mv["day_change_pct"].abs()
        _db_top = _db_mv.sort_values("_abs", ascending=False).head(6).sort_values("day_change_pct", ascending=False)
        if not _db_top.empty:
            for _, _mr in _db_top.iterrows():
                _pos = _mr["day_change_pct"] >= 0
                _color = "var(--up-txt)" if _pos else "var(--down-txt)"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:5px 0;font-size:12.5px;">'
                    f'<span>{_mr["name"]}</span>'
                    f'<span style="color:{_color};font-family:var(--uv-mono);">{_mr["day_change_pct"]:+.2f}%</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No daily price data available.")
