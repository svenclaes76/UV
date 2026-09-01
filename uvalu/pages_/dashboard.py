"""Dashboard page — portfolio overview matching the Uvalu.dc.html mockup:
KPI strip, value chart + conviction/risk card, holdings fair-value ladder,
sector allocation, upcoming dividends, top movers."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import risk as _risk_module
from portfolio import portfolio_exists, load_portfolio, load_value_history
from screener import load_fundamentals_cache
from settings import load_shared_settings
from uvalu.data import _load_portfolio_scored, _fetch_prices_cached, load_portfolio_risk
from uvalu.drawer import open_drawer
from uvalu.formatting import safe_pct as _safe_pct
from uvalu.runtime import theme_colors
from uvalu.components import (fair_value_legend_row, radial_gauge_svg,
                              kpi_card as _kpi_card, chip_html as _chip_html,
                              holdings_row_html as _holdings_row_html, HOLDINGS_GRID_COLS as _HOLD_GRID)
from uvalu.ui import _donut_chart, _CHART_CONFIG, price_autorefresh

# Matches Uvalu.dc.html's own rangesArr exactly (['1M','3M','1Y','ALL'],
# uvalu_dc.html ~line 2137) — the mockup has no 6M option.
_RANGES = {"1M": 30, "3M": 91, "1Y": 365, "All": None}


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

    # Refresh live prices on the shared portfolio cadence (see uvalu/ui.py) —
    # without this the dashboard's quotes only move when the user interacts.
    price_autorefresh("dashboard_refresh")

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

    # Scored rows for just this portfolio's holdings, via the dedicated
    # PORTFOLIO_FETCH lane — no full-universe scoring on the render path (WP-3).
    _db_scr = _load_portfolio_scored(_db_pf).copy()
    _db_mos_vals = pd.to_numeric(_db_scr.get("MoS %", pd.Series(dtype=float)), errors="coerce").dropna()
    _db_avg_mos  = _db_mos_vals.mean() if not _db_mos_vals.empty else None

    _db_fwd_income = None
    if not _db_scr.empty and "dividendYield" in _db_scr.columns:
        # groupby(...).sum(), not set_index(...) — the same ticker can appear
        # in multiple rows (separate lots, see the holdings-loop comment
        # below), which would leave a duplicate-labelled index and make
        # .reindex() raise ValueError: cannot reindex on an axis with
        # duplicate labels.
        _db_pf_cv = _db_pf.groupby("ticker")["current_value"].sum()
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
        with st.container(key="db_refresh_btn", width="content"):
            if st.button("Refresh", key="db_refresh", icon=":material/refresh:", type="tertiary"):
                st.cache_data.clear()
                st.rerun()

    # ── KPI strip ─────────────────────────────────────────────────────────────
    # Wrapped in a keyed container (styles.py) purely so CSS can give this
    # row's stHorizontalBlock an explicit min-height — Streamlit's own
    # height estimate for a kpi_card()'s raw-HTML markdown under-measures
    # its real rendered height (same class of bug hit repeatedly for the
    # Holdings rows/column header), so the row was reporting itself 16px
    # shorter than the cards actually are, leaving the *next* section
    # rendered flush against the overflow instead of with a proper gap.
    with st.container(key="db_kpi_row"):
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
            _kpi_card("Avg margin of safety",
                     f"{_db_avg_mos:+.1f}%" if _db_avg_mos is not None else "—",
                     "", (_db_avg_mos or 0) >= 0, "vs six-model fair value", icon="target")

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

            _title_col, _range_col = st.columns([2, 2], vertical_alignment="top")
            with _range_col, st.container(horizontal_alignment="right"):
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
            with _title_col:
                st.markdown(f"""
<div style="font-size:15px;font-weight:500;">Portfolio value over time</div>
<div style="display:flex;align-items:center;gap:10px;margin-top:4px;">
  <span style="font-family:var(--uv-mono);font-size:20px;font-weight:500;letter-spacing:-0.02em;">€{_db_last_val:,.0f}</span>
  {_chip_html(f"{_db_range_pct:+.1f}%", _db_range_pct >= 0)}
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
        _conv_score = None
        if not _db_scr.empty and "Value Score" in _db_scr.columns:
            # groupby(...).sum(), not set_index(...) — see the fwd-income
            # comment above; a duplicate ticker (multiple lots) would raise
            # here otherwise.
            _scr_cv = _db_pf.groupby("ticker")["current_value"].sum()
            _scr_vs = pd.to_numeric(_db_scr.set_index("Ticker")["Value Score"], errors="coerce")
            _w = _scr_cv.reindex(_scr_vs.index).fillna(0)
            if _w.sum() > 0:
                _conv_score = float((_scr_vs.fillna(0) * _w).sum() / _w.sum())
        _n_veto = int(_db_scr.get("veto", pd.Series(dtype=bool)).fillna(False).sum()) if "veto" in _db_scr.columns else 0

        # Risk report comes from the SAME shared builder the Risk page uses
        # (uvalu/data.py::load_portfolio_risk) — session-cached, enriched
        # frame, hard-veto lookup, targets — so the score shown here can never
        # disagree with the Risk page's gauge for one portfolio (WP-DQ4). It
        # used to call assess_portfolio(_db_pf, cache, False) with none of
        # that, which drifted a few points (Dashboard 32 vs Risk page 29).
        # The `_db_risk_cache` gate is kept: a cold fundamentals cache means
        # assess_portfolio would do an unpriced history fetch for nothing.
        _db_risk_cache = load_fundamentals_cache()
        _risk_score = _beta_str = _vol_str = _dd_str = None
        _risk_label = "—"
        if _db_pf is not None and not _db_pf.empty and _db_risk_cache:
            try:
                _db_report = load_portfolio_risk(_db_pf).report
                _risk_score = float(_db_report.composite.score)
                # Bucketed at risk.py's own SCORE_LOW/SCORE_MODERATE (25/50) —
                # not separate hand-picked numbers — so this card's Low/
                # Moderate never contradicts the Risk page's own labelling for
                # the same score. This card's 3-tier gauge (mockup constraint)
                # can't show risk.py's full Low/Moderate/Elevated/High/
                # Critical taxonomy, so Elevated/High/Critical are
                # deliberately collapsed into one "Elevated" bucket here —
                # coarser, but never disagrees with what the Risk page says.
                _risk_label = ("Low" if _risk_score <= _risk_module.SCORE_LOW
                              else "Moderate" if _risk_score <= _risk_module.SCORE_MODERATE
                              else "Elevated")
                _beta_str = f"{_db_report.quant.portfolio_beta:.2f}"
                _vol_str  = f"{_db_report.quant.volatility_annual*100:.1f}%" if _db_report.quant.volatility_annual else "—"
                _dd_str   = f"{_db_report.quant.mdd_1y*100:.1f}%" if _db_report.quant.mdd_1y else "—"
            except Exception:
                pass

        if _conv_score is not None:
            # Matches Uvalu.dc.html's conviction viewmodel exactly: labels
            # "High conviction"/"Constructive"/"Cautious" at 75/55 thresholds
            # (not this card's earlier "Strong/Moderate/Weak conviction" at
            # 70/40), and the label is always mint-colored regardless of
            # tier — the spec hardcodes `color:var(--mint)` unconditionally,
            # not a tier-dependent color.
            _conv_label = ("High conviction" if _conv_score >= 75 else
                          "Constructive" if _conv_score >= 55 else "Cautious")
            st.markdown(f"""
<div style="display:flex;align-items:center;gap:18px;margin-top:14px;">
  <div style="position:relative;width:118px;height:118px;flex:none;">
    {radial_gauge_svg(_conv_score, "#1DD6A4", size=118)}
    <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
      <span style="font-family:var(--uv-mono);font-size:27px;font-weight:500;line-height:1;color:var(--text);">{_conv_score:.0f}</span>
      <span style="font-size:9.5px;letter-spacing:0.08em;color:var(--faint);margin-top:3px;">/ 100</span>
    </div>
  </div>
  <div>
    <div style="font-size:12px;color:var(--faint);text-transform:uppercase;letter-spacing:0.06em;">Composite conviction</div>
    <div style="font-size:15px;font-weight:500;margin-top:4px;color:var(--mint);">{_conv_label}</div>
    <div style="font-size:12px;color:var(--muted);margin-top:8px;line-height:1.5;">Weighted mean signal score across scored holdings.{f" {_n_veto} position(s) under hard veto." if _n_veto else ""}</div>
  </div>
</div>""", unsafe_allow_html=True)
        else:
            st.caption("Not enough scored holdings for a conviction score.")

        if _risk_score is not None:
            _marker_pct = min(100.0, max(0.0, _risk_score))
            _risk_num_color = ("var(--up-txt)" if _risk_score <= _risk_module.SCORE_LOW else
                               "#C98A3A" if _risk_score <= _risk_module.SCORE_MODERATE else "var(--down-txt)")
            st.markdown(f"""
<div style="margin-top:16px;padding-top:15px;border-top:0.5px solid var(--line-2);">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;">
    <span style="font-size:12px;color:var(--muted);">Portfolio risk score</span>
    <span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;">
      <span style="color:{_risk_num_color};">{_risk_score:.0f}</span> · {_risk_label}</span>
  </div>
  <div style="height:7px;border-radius:4px;background:linear-gradient(90deg,#1DD6A4 0%,#1DD6A4 {_risk_module.SCORE_LOW}%,#C98A3A {_risk_module.SCORE_LOW}%,#C98A3A {_risk_module.SCORE_MODERATE}%,#A32D2D {_risk_module.SCORE_MODERATE}%,#A32D2D 100%);position:relative;opacity:0.85;">
    <div style="position:absolute;left:{_marker_pct:.1f}%;top:-3px;width:3px;height:13px;border-radius:2px;background:var(--text);box-shadow:0 0 0 2px var(--panel);"></div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:9.5px;color:var(--faint);margin-top:5px;font-family:var(--uv-mono);"><span>LOW</span><span>MODERATE</span><span>ELEVATED</span></div>
</div>""", unsafe_allow_html=True)

            with st.container(key="db_conv_metrics"):
                _dd_metric_defs = [("Beta", _beta_str, None), ("Volatility", _vol_str, None),
                                   ("Max drawdown", _dd_str, "var(--down-txt)")]
                _dd_cells = "".join(
                    f'<div><div style="font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:0.05em;">{_l}</div>'
                    f'<div style="font-family:var(--uv-mono);font-size:16px;font-weight:500;margin-top:3px;{f"color:{_c};" if _c else ""}">{_v}</div></div>'
                    for _l, _v, _c in _dd_metric_defs
                )
                st.markdown(f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">{_dd_cells}</div>',
                           unsafe_allow_html=True)

    st.container(height=4, border=False, key="db_gap_2")

    # ── Holdings · price vs fair value ────────────────────────────────────────
    with st.container(key="db_holdings_card", border=True):
        with st.container(key="db_holdings_header", horizontal=True,
                          vertical_alignment="center", horizontal_alignment="distribute"):
            with st.container(width="content"):
                st.markdown("""
<div style="font-size:15px;font-weight:500;">Holdings · price vs fair value</div>
<div style="font-size:12px;color:var(--muted);margin-top:2px;">Each track runs from €0 to the
six-model fair-value estimate. Gap to the marker is your remaining margin of safety.</div>""",
                           unsafe_allow_html=True)
            with st.container(width="content"):
                fair_value_legend_row()
        if not _db_scr.empty:
            _hold = _db_pf.merge(_db_scr, left_on="ticker", right_on="Ticker", how="left", suffixes=("", "_scr"))
            _hold["weight"] = _hold["current_value"] / _db_current if _db_current else 0
            _hold = _hold.sort_values("current_value", ascending=False).reset_index(drop=True)

            with st.container(key="db_holdings_colheader"):
                _hh_align = ("left", "left", "left", "right", "right", "right", "right")
                _hh_labels = ("Position", "Signal", "Fair-value ladder", "Margin of safety", "Weight", "Value", "Today")
                _hh_cells = "".join(
                    f'<div style="text-align:{_a};">{_l}</div>' for _l, _a in zip(_hh_labels, _hh_align))
                st.markdown(f'<div style="display:grid;grid-template-columns:{_HOLD_GRID};gap:14px;'
                           f'font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                           f'color:var(--faint);">{_hh_cells}</div>', unsafe_allow_html=True)

            # Row-click opens the shared drawer (same right-edge sidepanel used
            # by Screener/Watchlist/Portfolio) — @st.dialog can't be invoked
            # from inside the row loop itself, so the clicked ticker is just
            # tracked here and the dialog opened once after the loop, matching
            # the pattern in uvalu/pages_/screener.py. Each row is one raw CSS
            # Grid (holdings_row_html, matching Uvalu.dc.html's fixed-px grid
            # exactly) rendered via a single st.markdown() call — an earlier
            # version split content|button across a 2-column st.columns() row,
            # but Streamlit's per-column height measurement reliably
            # undersized the CSS-Grid content column (a 43px-tall grid
            # measured internally as 27px, confirmed live, immune to
            # align-items/display:contents overrides at every level of the
            # wrapper chain), leaving the row visibly off-center no matter
            # what. Making the whole row ONE element removes that competing
            # measurement entirely. The click target is now an invisible
            # st.button absolutely positioned over the full row (styles.py)
            # instead of a small "→" — closer to the mockup's own cursor:
            # pointer-on-the-whole-row behavior anyway, not just an icon.
            _drawer_target = None
            for _hidx, _hr in _hold.iterrows():
                # Keyed by row position, not ticker — the same ticker can appear in
                # two rows if a user bought it in separate lots (add_position()
                # appends rather than merging), which would otherwise collide.
                with st.container(key=f"db_hold_{_hidx}"):
                    # `_hr.get("Decision")` returns the actual NaN float (not
                    # the "" default) for holdings with no screener match —
                    # the "Decision" key exists as a merged column, it's just
                    # empty for that row — so str()-ing it unguarded would
                    # produce the literal text "nan" in the signal badge.
                    _decision = _hr.get("Decision")
                    _decision = str(_decision) if pd.notna(_decision) else ""
                    _w = _hr.get("weight", 0)
                    _w = float(_w) if _w is not None and pd.notna(_w) else 0.0
                    _cv = _hr.get("current_value")
                    _cv = float(_cv) if _cv is not None and pd.notna(_cv) else 0.0
                    st.markdown(_holdings_row_html(
                        ticker=_hr.get("ticker", ""), sector=_hr.get("sector"), name=_hr.get("name", ""),
                        decision=_decision, veto=bool(_hr.get("veto")),
                        price=_hr.get("live_price"), fair_value=_hr.get("fair_value"), mos_pct=_hr.get("MoS %"),
                        weight=_w, value=_cv, day_change_pct=_hr.get("day_change_pct"),
                    ), unsafe_allow_html=True)
                    _hr_ticker = _hr.get("Ticker")
                    if pd.notna(_hr_ticker):
                        if st.button("View details", key=f"db_holdbtn_{_hidx}"):
                            _drawer_target = _hidx

            if _drawer_target is not None:
                open_drawer(_hold.iloc[_drawer_target])
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
                    # groupby(...).sum(), not set_index(...) — same
                    # duplicate-ticker hazard as above; .map() from a
                    # duplicate-indexed Series raises InvalidIndexError.
                    _db_shares_map = _db_pf.groupby("ticker")["shares"].sum()
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
  <span style="width:64px;text-align:right;flex:none;">{_chip_html(f"{_mr['day_change_pct']:+.2f}%", _pos)}</span>
</div>""", unsafe_allow_html=True)
        else:
            st.caption("No daily price data available.")
