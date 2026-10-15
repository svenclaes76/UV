"""Dashboard page — portfolio overview matching the Uvalu.dc.html mockup:
KPI strip, value chart + conviction/risk card, holdings fair-value ladder,
sector allocation, upcoming dividends, top movers."""

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio import (portfolio_exists, load_portfolio, load_value_history, load_sold,
                       record_value_snapshot,
                       ensure_value_history_fresh, load_div_hist, dividends_in_eur,
                       exchange_key_for_ticker, BE_WITHHOLDING_RATE)
from screener import load_fundamentals_cache, sector_for, get_fetch_progress, PORTFOLIO_FETCH
from settings import load_shared_settings, get_dividend_withholding
from uvalu import a11y
from uvalu.data import (_load_portfolio_scored, peer_reference_pending, _fetch_prices_cached,
                        load_portfolio_risk, apply_live_prices)
from uvalu.dialogs import add_position_dialog
from uvalu.drawer import open_drawer
from uvalu.formatting import display_name, safe_pct as _safe_pct
from uvalu.i18n import (N_, _, conversion_note, frozen, fmt_date, fmt_num, fmt_pct, fmt_total, h_,
                        localize_fig, ngettext, pgettext, plotly_money_axis, to_display, tr)
from uvalu.runtime import brand_hoverlabel, theme_colors, current_user
from uvalu.components import (fair_value_legend_html, list_provenance_html, page_header, score_band_label,
                              donut_html, dividend_row_html, mover_row_html, radial_gauge_svg, risk_score_meter_html,
                              kpi_card as _kpi_card, chip_html as _chip_html,
                              holdings_row_html as _holdings_row_html, HOLDINGS_GRID_COLS as _HOLD_GRID, fit_grid_cols,
                              signal_tooltip, skeleton_kpi_card_html, skeleton_holdings_table_html,
                              skeleton_chart_html, skeleton_gauge_card_html,
                              skeleton_metrics_grid_html, skeleton_text_html,
                              refresh_top_bar_html)
from uvalu.ui import _CHART_CONFIG, price_autorefresh, poll_while_fetching, consumed_tick, _auto_rerun

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
        _es_col = st.columns([1, 1.1, 1])[1]
        with _es_col:
            st.container(height=48, border=False)
            st.subheader(_("No portfolio yet"))
            st.caption(_("Browse the screener to explore stocks and their model valuations, or import an existing Excel portfolio in Settings."))
            with st.container(horizontal=True, gap="small"):
                st.page_link(_pg_screener, label=_("Open screener"))
                st.page_link(_pg_settings, label=_("Import portfolio"))
        st.stop()

    _db_pf = load_portfolio()
    if _db_pf is None or _db_pf.empty:
        st.info(_("Your portfolio is empty."))
        st.stop()

    # Refresh live prices on the shared portfolio cadence (see uvalu/ui.py) —
    # without this the dashboard's quotes only move when the user interacts.
    price_autorefresh("dashboard_refresh")
    # A timer-triggered rerun (not a real navigation) gets a slim top-of-page
    # sweep instead of the page just silently repainting — matches the
    # "Data refresh" half of the Loading Patterns design (never a disruptive
    # blank flash for a page that already has real data on screen). It only
    # renders for this one script run; the next run (real or timed) starts
    # clean, so it never lingers.
    if consumed_tick("dashboard_refresh"):
        # uv_hidden_util: the sweep is position:fixed (zero layout height),
        # but its own element-container would still eat a full row-gap in
        # the page's vertical block and push the heading down (same trick
        # as uvalu/shell.py's topbar CSS injection).
        with st.container(key="uv_hidden_util_refresh_sweep"):
            st.markdown(refresh_top_bar_html(), unsafe_allow_html=True)

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

    # Dividends actually received — filtered to date <= today (a dividend
    # logged ahead of its payment date shouldn't count as "received" yet)
    # and excluding DRIP/reinvested records (that cash never left the
    # position, so counting it here would double-count it against the
    # position's own already-larger market value). EUR-converted per record
    # via dividends_in_eur() (fx.py — ECB rates via frankfurter) since a Swiss
    # holding pays in CHF, not EUR. Two totals: "open" (this page's own
    # holdings, feeds Total return alongside the open-positions-only
    # unrealised gain above) and "lifetime" (open + sold positions, matches
    # what the Portfolio page's own Dividends-received total already means —
    # previously this KPI only summed open positions and silently dropped
    # dividends earned on since-sold holdings).
    _db_div_hist_all = load_div_hist()
    if _db_div_hist_all is not None and not _db_div_hist_all.empty:
        _db_div_eur = dividends_in_eur(_db_div_hist_all)
        _db_div_dates = pd.to_datetime(_db_div_eur.get("date"), errors="coerce")
        if "reinvested" in _db_div_eur.columns:
            _db_div_reinv = _db_div_eur["reinvested"].fillna(False).astype(bool)
        else:
            _db_div_reinv = pd.Series(False, index=_db_div_eur.index)
        _db_div_received = _db_div_eur[(_db_div_dates <= pd.Timestamp.now()) & (~_db_div_reinv)]
        _db_divs = _db_div_received["amount_eur"].sum()
        _db_divs_open = _db_div_received[
            _db_div_received["ticker"].isin(set(_db_tickers))]["amount_eur"].sum()
    else:
        _db_divs, _db_divs_open = 0.0, 0.0
    _db_total_ret = _db_gain + _db_divs_open
    _db_ret_pct   = _safe_pct(_db_total_ret, _db_invested)

    # Scored rows for just this portfolio's holdings, via the dedicated
    # PORTFOLIO_FETCH lane — no full-universe scoring on the render path (WP-3).
    # apply_live_prices adds the live quote next to the scored figures; the
    # ladder's price, fair value and margin of safety stay those the signal
    # was computed from, so all three reconcile with the badge (B3).
    _db_scr = apply_live_prices(_load_portfolio_scored(_db_pf), _db_prices).copy()
    # True only while there's genuinely nothing scored yet AND the background
    # fetch is still working on it — an empty _db_scr for any other reason
    # (fetch finished with nothing to show) falls through to the plain "no
    # data" captions below instead of an endless skeleton.
    _db_fetch_running = _db_scr.empty and bool(get_fetch_progress(PORTFOLIO_FETCH).get("running"))
    # Cold start: the holdings are scored but can't be ranked until the
    # universe's peer reference exists — every signal would read "No signal",
    # the fair values would lack sector medians and the composite would
    # average only the failed-screen rows (0/100). Everything that depends on
    # the ranking shows its skeleton until then (G1).
    _db_ref_pending = not _db_scr.empty and peer_reference_pending()
    # G13: weighted by each holding's current value (all its lots), like the
    # mockup's "weighted MoS" — a 1% position no longer counts as much as a 20% one.
    _db_avg_mos = None
    if not _db_scr.empty and "MoS %" in _db_scr.columns:
        _db_mos_by_t = pd.to_numeric(_db_scr.drop_duplicates("Ticker").set_index("Ticker")["MoS %"],
                                     errors="coerce").dropna()
        _db_cv_by_t = _db_pf.groupby("ticker")["current_value"].sum().reindex(_db_mos_by_t.index).fillna(0)
        if _db_cv_by_t.sum() > 0:
            _db_avg_mos = float((_db_mos_by_t * _db_cv_by_t).sum() / _db_cv_by_t.sum())
        elif not _db_mos_by_t.empty:
            _db_avg_mos = float(_db_mos_by_t.mean())

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
    # REC-4 / REC-5: the provenance is the third line of the page header, in
    # the same place as on the Screener and Watchlist.
    _db_actions = page_header(
        _("Portfolio overview"),
        ngettext("{positions} across {count} European exchange · valued against a model fair-value estimate.",
                 "{positions} across {count} European exchanges · valued against a model fair-value estimate.",
                 _n_exch, positions=ngettext("{count} position", "{count} positions", len(_db_pf))),
        provenance="" if _db_ref_pending else list_provenance_html(_db_scr))
    with _db_actions:
        with st.container(key="db_refresh_btn", width="content"):
            if st.button(_("Refresh"), key="db_refresh", icon=":material/refresh:", type="tertiary"):
                st.cache_data.clear()
                st.rerun()
        _db_viewer = current_user().is_viewer
        if st.button(_("Add position"), key="db_add_position", type="primary", icon=":material/add:",
                     disabled=_db_viewer, help=_("Viewer role is read-only") if _db_viewer else None):
            add_position_dialog()

    # ── KPI strip ─────────────────────────────────────────────────────────────
    # Wrapped in a keyed container (styles.py) purely so CSS can give this
    # row's stHorizontalBlock an explicit min-height — Streamlit's own
    # height estimate for a kpi_card()'s raw-HTML markdown under-measures
    # its real rendered height (same class of bug hit repeatedly for the
    # Holdings rows/column header), so the row was reporting itself 16px
    # shorter than the cards actually are, leaving the *next* section
    # rendered flush against the overflow instead of with a proper gap.
    # Cash Management v1 (Uvalu Cash Management.dc.html): Current value includes
    # the cash balance, and a Cash tile sits next to it. Cash never enters the
    # risk model — the tile says so.
    from uvalu.pages_.cash import dashboard_cash_tile_values
    _db_cash = dashboard_cash_tile_values(_db_current)
    with st.container(key="db_kpi_row"):
        _k1, _kc, _k2, _k3, _k4 = st.columns(5)
        with _k1:
            # UX2: what the total is made of, with no return chip (the Total
            # return tile carries the return); the holdings figure matches the
            # sector total and the value chart's last point.
            _kpi_card(h_("Current value"), fmt_total(_db_current + _db_cash['balance']), "", True,
                     (h_("holdings {holdings} + cash {cash}", holdings=fmt_total(_db_current),
                         cash=fmt_total(_db_cash['balance'])) if _db_cash["count"]
                      else h_("holdings, no cash recorded")), icon="wallet")
        with _kc:
            _kpi_card(h_("Cash"), fmt_total(_db_cash['balance']), fmt_pct(_db_cash['cash_pct']), True,
                     h_("of total value · not in risk"), icon="cash", delta_style=_db_cash["chip_style"])
        with _k2:
            _kpi_card(h_("Total return"), fmt_total(_db_total_ret),
                     fmt_pct(_db_ret_pct, signed=True), _db_total_ret >= 0,
                     h_("open positions: unrealised + dividends"), icon="trend")
        with _k3:
            if _db_fwd_income is not None:
                _db_blended_yield = _safe_pct(_db_fwd_income, _db_current)
                _kpi_card(h_("Fwd income / yr"), fmt_total(_db_fwd_income),
                         fmt_pct(_db_blended_yield), True, h_("blended yield"), icon="coin")
            else:
                _kpi_card(h_("Dividends received"), fmt_total(_db_divs), "", True, "", icon="coin")
        with _k4:
            if (_db_avg_mos is None and _db_fetch_running) or _db_ref_pending:
                st.markdown(skeleton_kpi_card_html(), unsafe_allow_html=True)
            else:
                # "model": an outline tag, not an up/down chip — the figure is a
                # model estimate, not a gain.
                _kpi_card(h_("Avg margin of safety"), fmt_pct(_db_avg_mos, signed=True),
                          h_("model"), True, h_("weighted MoS"), icon="target",
                          delta_style="display:inline-flex;font-size:11px;color:var(--muted);padding:2px 7px;"
                                      "border-radius:6px;border:0.5px solid var(--line);")
    _conv_note = conversion_note()
    if _conv_note:
        st.caption(_conv_note)

    st.container(height=4, border=False, key="db_gap_1")

    # ── Value chart + Conviction & risk ───────────────────────────────────────
    _chart_col, _conv_col = st.columns([1.62, 1], gap="large")

    with _chart_col, st.container(key="db_card_chart", border=True):
        # UX2: the value history only gained a point when the Portfolio page
        # was opened, so the chart could end days ago at a figure no tile
        # showed. Record today's point here too (one per day, upserted;
        # throttled like the Portfolio page's own call).
        if _db_current > 0:
            import time as _time
            _now = _time.time()
            if _now - st.session_state.get("_db_snapshot_ts", 0.0) >= 600:
                record_value_snapshot(float(_db_invested), float(_db_current))
                st.session_state["_db_snapshot_ts"] = _now
        _db_vh = load_value_history()
        if _db_vh is not None and not _db_vh.empty and len(_db_vh) >= 2:
            _db_vh["date"]     = pd.to_datetime(_db_vh["date"])
            _db_vh["value"]    = pd.to_numeric(_db_vh["value"],    errors="coerce")
            _db_vh["invested"] = pd.to_numeric(_db_vh["invested"], errors="coerce")
            _db_vh = _db_vh.dropna(subset=["date", "value"]).sort_values("date")

            _title_col, _range_col = st.columns([2, 2], vertical_alignment="top")
            # Opens on the past year (design reference, G03); a portfolio with
            # less than a year of history opens on All, which is the same span.
            _span_days = (_db_vh["date"].max() - _db_vh["date"].min()).days
            _range_default = "1Y" if _span_days >= _RANGES["1Y"] else "All"
            with _range_col, st.container(horizontal_alignment="right"):
                _range_sel = st.segmented_control(_("Range"), options=list(_RANGES.keys()), default=_range_default,
                                                  format_func=frozen(lambda k: {"1M": pgettext("chart_range", "1M"),
                                                                  "3M": pgettext("chart_range", "3M"),
                                                                  "1Y": pgettext("chart_range", "1Y"),
                                                                  "All": _("All")}[k]),
                                                  key="db_range", label_visibility="collapsed")
            _days = _RANGES.get(_range_sel or "All")
            _vh_view = _db_vh
            if _days is not None:
                _cutoff = _db_vh["date"].max() - pd.Timedelta(days=_days)
                _vh_view = _db_vh[_db_vh["date"] >= _cutoff]

            _db_last_val   = float(_vh_view["value"].iloc[-1])
            _db_first_val  = float(_vh_view["value"].iloc[0])
            _db_range_pct  = _safe_pct(_db_last_val - _db_first_val, _db_first_val)
            # The change in value over the range, deposits included — not a
            # return (that's the Total return tile); say so next to the chip.
            _range_txt = {
                # Translators: Dashboard chart subtitle: the change shown is over the past month and includes deposits (not a return).
                "1M": _("Past month · incl. deposits"),
                # Translators: Dashboard chart subtitle: the change shown is over the past 3 months and includes deposits (not a return).
                "3M": _("Past 3 months · incl. deposits"),
                # Translators: Dashboard chart subtitle: the change shown is over the past year and includes deposits (not a return).
                "1Y": _("Past year · incl. deposits"),
            }.get(_range_sel or "All",
                  # Translators: Dashboard chart subtitle: the change shown is over the whole history and includes deposits (not a return).
                  _("All time · incl. deposits"))
            with _title_col:
                st.markdown(f"""
<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;">{h_("Portfolio value over time")}</div>
<div style="display:flex;align-items:center;gap:10px;margin-top:7px;">
  <span style="font-family:var(--uv-mono);font-size:24px;font-weight:500;letter-spacing:-0.02em;">{fmt_total(_db_last_val)}</span>
  {_chip_html(fmt_pct(_db_range_pct, signed=True), _db_range_pct >= 0)}
  <span style="font-size:11px;color:var(--muted);">{_range_txt}</span>
</div>
<div style="font-size:11px;color:var(--muted);margin-top:4px;">{h_("Your holdings, without cash.")}</div>""", unsafe_allow_html=True)

            _db_has_spx   = "benchmark_spx"   in _vh_view.columns and _vh_view["benchmark_spx"].notna().any()
            _db_has_stoxx = "benchmark_stoxx" in _vh_view.columns and _vh_view["benchmark_stoxx"].notna().any()

            _db_bench_opts = ([("S&P 500")] if _db_has_spx else []) + (["Euro Stoxx 50"] if _db_has_stoxx else [])
            _db_bench_default = [o for o in
                                 (["Euro Stoxx 50"] if load_shared_settings().get("benchmark_stoxx", False) else [])
                                 if o in _db_bench_opts]
            _db_bench_sel = st.session_state.get("db_bench_pills", _db_bench_default)
            _db_show_spx   = "S&P 500" in _db_bench_sel
            _db_show_stoxx = "Euro Stoxx 50" in _db_bench_sel

            # Chart values are EUR; shown in the display currency at today's
            # rate when that isn't EUR (same ≈ note as the KPI tiles).
            _fx_f, _fx_ccy, _fx_conv = to_display(1.0)
            _db_vfig = go.Figure()
            _db_vfig.add_trace(go.Scatter(
                x=_vh_view["date"], y=_vh_view["value"] * _fx_f, mode="lines", name=_("Portfolio value"),
                line=dict(color="#1DD6A4", width=2), fill="tozeroy", fillcolor="rgba(29,214,164,0.07)"))
            _db_vfig.add_trace(go.Scatter(
                x=_vh_view["date"], y=_vh_view["invested"] * _fx_f, mode="lines", name=_("Amount invested"),
                line=dict(color=_c_invested, width=1.5, dash="dot")))
            if _db_has_spx:
                _db_vfig.add_trace(go.Scatter(
                    x=_vh_view["date"], y=pd.to_numeric(_vh_view["benchmark_spx"], errors="coerce") * _fx_f,
                    mode="lines", name=_("S&P 500 (same invested)"), line=dict(color="#5B8FA8", width=1.5, dash="dash"),
                    visible=True if _db_show_spx else "legendonly"))
            if _db_has_stoxx:
                _db_vfig.add_trace(go.Scatter(
                    x=_vh_view["date"], y=pd.to_numeric(_vh_view["benchmark_stoxx"], errors="coerce") * _fx_f,
                    mode="lines", name=_("Euro Stoxx 50 (same invested)"), line=dict(color="#8BA888", width=1.5, dash="dash"),
                    visible=True if _db_show_stoxx else "legendonly"))
            _db_vfig.update_layout(
                margin=dict(l=0, r=0, t=16, b=0),
                showlegend=False,
                yaxis=dict(**plotly_money_axis(_fx_ccy), tickfont=dict(color=_c_axis), gridcolor=_c_grid),
                xaxis=dict(showgrid=False, tickfont=dict(color=_c_axis)),
                hovermode="x unified", font=dict(color=_c_axis),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                hoverlabel=brand_hoverlabel(),
            )
            localize_fig(_db_vfig)
            # AC6: screen readers get one sentence instead of the axis ticks.
            _ch_start, _ch_end = fmt_date(_vh_view["date"].iloc[0]), fmt_date(_vh_view["date"].iloc[-1])
            _ch_invested = fmt_total(float(_vh_view["invested"].iloc[-1]))
            a11y.image("db_value_chart", _(
                "Chart: your holdings were worth {first} on {start} and {last} on {end}; amount invested {invested}.",
                first=fmt_total(float(_vh_view["value"].iloc[0])), start=_ch_start,
                last=fmt_total(_db_last_val), end=_ch_end, invested=_ch_invested) if _ch_start != _ch_end else _(
                "Chart: your holdings were worth {last} on {end}; amount invested {invested}.",
                last=fmt_total(_db_last_val), end=_ch_end, invested=_ch_invested))
            with st.container(key="db_value_chart"):
                st.plotly_chart(_db_vfig, width="stretch", height=250, config=_CHART_CONFIG)

            # ── Unified legend bar — swatches for the two always-on series,
            # plus clickable chip toggles (st.pills, same idiom as the
            # Screener's Signal/Hide-owned chips) for the optional benchmarks
            # — one legend row matching Uvalu.dc.html's benchChip toggles
            # instead of a separate native-checkbox row. ──
            with st.container(key="db_chart_legend_row", horizontal=True,
                              vertical_alignment="center", horizontal_alignment="distribute"):
                with st.container(width="content"):
                    st.markdown(f"""
<div style="display:flex;align-items:center;gap:18px;">
  <div style="display:flex;align-items:center;gap:7px;font-size:11.5px;color:var(--muted);">
    <span style="width:14px;height:2px;background:var(--mint);border-radius:4px;display:inline-block;"></span>{h_("Portfolio value")}</div>
  <div style="display:flex;align-items:center;gap:7px;font-size:11.5px;color:var(--muted);">
    <span style="width:14px;height:0;border-top:1.4px dashed var(--axis);display:inline-block;"></span>{h_("Amount invested")}</div>
</div>""", unsafe_allow_html=True)
                if _db_bench_opts:
                    with st.container(width="content"):
                        st.pills(_("Benchmarks"), options=_db_bench_opts, selection_mode="multi",
                                default=_db_bench_default, key="db_bench_pills",
                                label_visibility="collapsed")
        elif ensure_value_history_fresh(_db_pf, load_sold(), current_user().email):
            # Backfill is running in the background (kicked off from here or
            # from Portfolio, whichever the user visited first) — paint the
            # chart's shape immediately and poll until it fills in on its own.
            st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:6px;">{h_("Portfolio value over time")}</div>',
                       unsafe_allow_html=True)
            st.markdown(skeleton_chart_html(), unsafe_allow_html=True)
            _auto_rerun(5, "dashboard_value_history_backfill")
        else:
            st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:6px;">{h_("Portfolio value over time")}</div>',
                       unsafe_allow_html=True)
            st.caption(_("No history yet — it will appear after your first portfolio snapshot."))

    with _conv_col, st.container(key="db_card_conviction", border=True):
        _cvh_col, _cvh_link_col = st.columns([2, 1], vertical_alignment="top")
        with _cvh_col:
            st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;">{h_("Score & risk")}</div>',
                       unsafe_allow_html=True)
        with _cvh_link_col:
            if st.button(_("Full analysis →"), key="db_conv_full_analysis", type="tertiary", width="stretch"):
                st.switch_page(nav.pages["risk"])
        _conv_score = None
        if not _db_scr.empty and "Value Score" in _db_scr.columns:
            # groupby(...).sum(), not set_index(...) — see the fwd-income
            # comment above; a duplicate ticker (multiple lots) would raise
            # here otherwise.
            _scr_cv = _db_pf.groupby("ticker")["current_value"].sum()
            _scr_vs = pd.to_numeric(_db_scr.set_index("Ticker")["Value Score"], errors="coerce")
            # Only holdings with a model score count: "No signal" rows (no
            # peer basis yet, PER-1) have none, so they're left out rather
            # than averaged in as 0. A failed quality screen counts as its 0.
            _scr_vs = _scr_vs.dropna()
            _w = _scr_cv.reindex(_scr_vs.index).fillna(0)
            if _w.sum() > 0:
                _conv_score = float((_scr_vs * _w).sum() / _w.sum())
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
        _risk_pending = False
        if _db_pf is not None and not _db_pf.empty and _db_risk_cache:
            try:
                _db_risk_bundle = load_portfolio_risk(_db_pf)
                if _db_risk_bundle is None:
                    # Still computing in the background (uvalu/data.py) —
                    # distinct from "no risk data" (the bare except below).
                    _risk_pending = True
                else:
                    _db_report = _db_risk_bundle.report
                    _risk_score = float(_db_report.composite.score)
                    # The exact band label from risk.RISK_BANDS (minus the
                    # trailing " risk"), so this card shows the same
                    # Low/Moderate/Elevated/High/Critical word as the Risk
                    # page's gauge for one score — the old 3-way re-bucket
                    # here collapsed Elevated/High/Critical into one word.
                    _risk_label = tr(_db_report.composite.label.replace(" risk", ""))
                    _beta_str = fmt_num(_db_report.quant.portfolio_beta, 2)
                    _vol_str  = fmt_pct(_db_report.quant.volatility_annual, fraction=True) if _db_report.quant.volatility_annual else "—"
                    _dd_str   = fmt_pct(_db_report.quant.mdd_1y, fraction=True) if _db_report.quant.mdd_1y else "—"
            except Exception:
                pass

        if _db_fetch_running or _risk_pending or _db_ref_pending:
            # Either half of this card can independently still be computing
            # (conviction from the PORTFOLIO_FETCH lane, risk score from the
            # background risk report) — one combined skeleton covers both
            # rather than a half-real/half-shimmer card.
            st.markdown(skeleton_gauge_card_html(118), unsafe_allow_html=True)
            st.markdown(skeleton_metrics_grid_html(n_cells=3, n_cols=3), unsafe_allow_html=True)
            _auto_rerun(5, "dashboard_conviction_pending")
        else:
            if _conv_score is not None:
                # PER-4: describes where the portfolio sits on the model's
                # scale, no "conviction" verdict (legal design, Uvalu.dc.html).
                # Bands follow the signal thresholds (components.score_band_label).
                # The ring is always Mint (mockup): a position on the scale, never red.
                _conv_label = score_band_label(_conv_score)
                _conv_ring = "#1DD6A4"
                _conv_text = h_("Value-weighted mean of model scores across scored holdings. Describes the portfolio.")
                if _n_veto:
                    _conv_text += " " + ngettext("{count} position fails a quality screen.",
                                                 "{count} positions fail a quality screen.", _n_veto)
                st.markdown(f"""
<div style="display:flex;align-items:center;gap:18px;margin-top:14px;">
  <div style="position:relative;width:118px;height:118px;flex:none;">
    {radial_gauge_svg(_conv_score, _conv_ring, size=118)}
    <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
      <span style="font-family:var(--uv-mono);font-size:27px;font-weight:500;line-height:1;color:var(--text);">{fmt_num(_conv_score, 0)}</span>
      <span style="font-size:9.5px;letter-spacing:0.08em;color:var(--muted);margin-top:3px;">/ 100</span>
    </div>
  </div>
  <div>
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;">{h_("Weighted composite score")}</div>
    <div style="font-size:15px;font-weight:500;margin-top:4px;color:var(--up-txt);">{_conv_label}</div>
    <div style="font-size:12px;color:var(--muted);margin-top:8px;line-height:1.5;">{_conv_text}</div>
  </div>
</div>""", unsafe_allow_html=True)
            else:
                st.caption(_("Not enough scored holdings for a weighted composite score."))

            if _risk_score is not None:
                # Shared renderer (uvalu/components.risk_score_meter_html) — same
                # risk.RISK_BANDS gradient stops (green→amber at SCORE_LOW,
                # amber→red at SCORE_ELEVATED) and the same score-number colour
                # as the Risk page's composite gauge, so the two screens can't
                # disagree on one portfolio's risk colour again.
                st.markdown(
                    '<div style="margin-top:16px;padding-top:15px;border-top:0.5px solid var(--line-2);">'
                    + risk_score_meter_html(_risk_score, _risk_label,
                                            dark=not theme_colors().effective_light)
                    + "</div>", unsafe_allow_html=True)

                with st.container(key="db_conv_metrics"):
                    _dd_metric_defs = [(h_("Beta"), _beta_str, None), (h_("Volatility"), _vol_str, None),
                                       (h_("Max drawdown"), _dd_str, "var(--down-txt)")]
                    _dd_cells = "".join(
                        f'<div><div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em;">{_l}</div>'
                        f'<div style="font-family:var(--uv-mono);font-size:16px;font-weight:500;margin-top:3px;{f"color:{_c};" if _c else ""}">{_v}</div></div>'
                        for _l, _v, _c in _dd_metric_defs
                    )
                    st.markdown(f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">{_dd_cells}</div>',
                               unsafe_allow_html=True)

    st.container(height=4, border=False, key="db_gap_2")

    # ── Holdings · price vs fair value ────────────────────────────────────────
    with st.container(key="db_holdings_card", border=True):
        with st.container(key="db_holdings_header"):
            # Title with the fair-value legend right-aligned on the same row
            # (it explains the bars below); wraps under the title when narrow.
            st.markdown(f"""
<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:6px 16px;">
<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;">{h_("Holdings · price vs fair value")}</div>{fair_value_legend_html()}</div>
<div style="font-size:12px;color:var(--muted);margin-top:2px;">{h_("Each track runs from zero to the model fair-value estimate. Gap to the marker is the model margin of safety. Fair values are estimates.")} {h_("Model signals are the same for every user and don't take your holdings into account.")}</div>""",
                        unsafe_allow_html=True)
        # Column header renders for the real table AND the fetch-in-progress
        # skeleton below (never just the header floating over a blank body,
        # never rows with no header) — only the genuine "nothing here" case
        # (fetch finished, still no data) drops it entirely.
        # Fixed-px tracks widened to the translated labels (the ladder's 1fr
        # track gives up the room); header, rows and skeleton share it.
        _hold_grid = fit_grid_cols(_HOLD_GRID, [_("Position"), _("Model signal"), "", _("Margin of safety"), _("Weight"),
                                                _("Value"), _("P&L")])
        if not _db_scr.empty or _db_fetch_running:
            with st.container(key="db_holdings_colheader"):
                _hh_align = ("left", "left", "left", "right", "right", "right", "right")
                # L13 (docs/legal/signal-label-review.md): the signal sits next to
                # the user's own position, so the header says it's the shared
                # model signal and its tooltip says it ignores the user's holdings.
                _hh_labels = (h_("Position"), h_("Model signal"), h_("Fair-value ladder"), h_("Margin of safety"), h_("Weight"),
                              h_("Value"), h_("P&L"))
                _hh_titles = list(_hh_labels)
                # Translators: Dashboard › Holdings table › tooltip on the "Model signal" column header; the standard signal tooltip follows it.
                _hh_titles[1] = html.escape(_("Same for every user; it doesn't take your holdings into account.")
                                             + " " + signal_tooltip(), quote=True)
                _hh_cells = "".join(
                    f'<div title="{_t}" style="text-align:{_a};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_l}</div>' for _l, _t, _a in zip(_hh_labels, _hh_titles, _hh_align))
                st.markdown(f'<div style="display:grid;grid-template-columns:{_hold_grid};gap:14px;'
                           f'font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
                           f'color:var(--muted);">{_hh_cells}</div>', unsafe_allow_html=True)

        if not _db_scr.empty and not _db_ref_pending:
            _hold = _db_pf.merge(_db_scr, left_on="ticker", right_on="Ticker", how="left", suffixes=("", "_scr"))
            _hold["weight"] = _hold["current_value"] / _db_current if _db_current else 0
            _hold = _hold.sort_values("price_gain", ascending=False).reset_index(drop=True)

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
                    # `_hr.get("signal_code")` returns the actual NaN float
                    # (not the "" default) for holdings with no screener
                    # match — the key exists as a merged column, it's just
                    # empty for that row — so str()-ing it unguarded would
                    # produce the literal text "nan".
                    _signal_code = _hr.get("signal_code")
                    _signal_code = str(_signal_code) if pd.notna(_signal_code) else ""
                    _w = _hr.get("weight", 0)
                    _w = float(_w) if _w is not None and pd.notna(_w) else 0.0
                    _cv = _hr.get("current_value")
                    _cv = float(_cv) if _cv is not None and pd.notna(_cv) else 0.0
                    _ps = _hr.get("price_stale")
                    _dt = _hr.get("data_thin")
                    st.markdown(_holdings_row_html(
                        ticker=_hr.get("ticker", ""),
                        sector=sector_for(_hr.get("ticker"), _hr.get("sector")), name=_hr.get("name", ""),
                        signal_code=_signal_code, veto=_hr.get("veto"),
                        price=_hr.get("Price"), fair_value=_hr.get("fair_value"), mos_pct=_hr.get("MoS %"),
                        weight=_w, value=_cv, total_gain=_hr.get("price_gain"),
                        price_stale=bool(_ps) if pd.notna(_ps) else False,
                        data_thin=bool(_dt) if pd.notna(_dt) else False, grid_cols=_hold_grid,
                    ), unsafe_allow_html=True)
                    _hr_ticker = _hr.get("Ticker")
                    if pd.notna(_hr_ticker):
                        a11y.label(f"db_holdbtn_{_hidx}", _("View {stock}", stock=a11y.stock_name(
                            str(_hr.get("ticker", "")), display_name(_hr.get("name", "")))))
                        if st.button(_("View details"), key=f"db_holdbtn_{_hidx}"):
                            _drawer_target = _hidx

            # AC2: the rows are a table for screen readers (uvalu/a11y.py).
            a11y.table("db_holdings_card", _("Holdings · price vs fair value"), header="db_holdings_colheader",
                       rows=[f"db_hold_{_i}" for _i in range(len(_hold))])
            if _drawer_target is not None:
                open_drawer(_hold.iloc[_drawer_target])
        elif _db_ref_pending:
            # Scored, but the peer reference is still being built — the
            # universe recompute's poll fills the real rows in (G1).
            poll_while_fetching("dashboard_peer_reference", lane="screener")
            st.markdown(skeleton_holdings_table_html(grid_cols=_hold_grid), unsafe_allow_html=True)
        elif _db_fetch_running:
            # Nothing scored yet, but the PORTFOLIO_FETCH lane is still
            # working on it — paint the table's real shape immediately
            # instead of a blank/captioned panel, and arm a short auto-rerun
            # so it resolves into real rows on its own. Same cold-cache idiom
            # as Screener's loading_skeleton_html (uvalu/pages_/screener.py),
            # shaped like this table's own grid instead of a generic bar list.
            poll_while_fetching("dashboard_portfolio_fetch", lane="portfolio")
            st.markdown(skeleton_holdings_table_html(grid_cols=_hold_grid), unsafe_allow_html=True)
        else:
            st.caption(_("No screener data available for your holdings."))

    st.container(height=4, border=False, key="db_gap_3")

    # ── Bottom row: sector allocation | upcoming dividends | top movers ──────
    _al_col, _div_col, _mv_col = st.columns(3, gap="large")

    with _al_col, st.container(key="db_card_sector", border=True):
        st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:8px;">{h_("Sector allocation")}</div>',
                   unsafe_allow_html=True)
        if _db_fetch_running:
            # Without real sector data yet, every holding would fall back to
            # "Unknown" below — a skeleton is honest about "still loading"
            # instead of a misleading all-Unknown donut for a few seconds.
            st.markdown(skeleton_chart_html(180), unsafe_allow_html=True)
        else:
            _db_sector_map = (
                _db_scr.drop_duplicates("Ticker").set_index("Ticker")["sector"]
                if not _db_scr.empty and "sector" in _db_scr.columns else pd.Series(dtype=object)
            )
            _db_al = (
                _db_pf.dropna(subset=["current_value"])
                  .assign(sector=_db_pf["ticker"].map(
                      lambda t: sector_for(t, _db_sector_map.get(t)) or N_("Unknown")))
                  .groupby("sector")["current_value"].sum()
                  .sort_values(ascending=False)
            )
            _db_donut = donut_html(_db_al)
            if _db_donut:
                st.markdown(_db_donut, unsafe_allow_html=True)
            else:
                st.caption(_("No data available for this breakdown."))

    with _div_col, st.container(key="db_card_dividends", border=True):
        _dh_title_col, _dh_total_col = st.columns([2, 1.4], vertical_alignment="center")
        with _dh_title_col:
            st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;">{h_("Upcoming dividends")}</div>',
                       unsafe_allow_html=True)
        with _dh_total_col:
            if _db_fwd_income is not None:
                st.markdown(f'<div style="text-align:right;font-family:var(--uv-mono);font-size:11px;'
                           f'color:var(--up-txt);">{h_("{amount} / yr fwd", amount=fmt_total(_db_fwd_income))}</div>',
                           unsafe_allow_html=True)
        if _db_fetch_running:
            st.markdown(skeleton_text_html((85, 92, 70, 88)), unsafe_allow_html=True)
        elif not _db_scr.empty:
            _db_div_scr = _db_scr.copy()
            # Prefer the forecast screener._next_expected_ex_div derives from
            # the full payment history (screener.py's nextExDividendDate,
            # wired in via _fetch_one) over yfinance's own raw exDividendDate
            # field — that field is usually the *last* ex-div date rather
            # than a forecast, so filtering it `>= today` mostly came up
            # empty. Falls back to the raw field when there's no usable
            # payment history yet to forecast from.
            for _col in ("nextExDividendDate", "exDividendDate"):
                if _col not in _db_div_scr.columns:
                    _db_div_scr[_col] = None
            _db_next_ex = pd.to_datetime(_db_div_scr["nextExDividendDate"], errors="coerce", dayfirst=True)
            _db_raw_ex  = pd.to_datetime(_db_div_scr["exDividendDate"], errors="coerce", dayfirst=True)
            _db_div_scr["exDividendDate"] = _db_next_ex.fillna(_db_raw_ex)
            _today = pd.Timestamp.today().normalize()
            if _db_div_scr["exDividendDate"].notna().any():
                _db_upcoming = (
                    _db_div_scr[_db_div_scr["exDividendDate"] >= _today]
                      .sort_values("exDividendDate").head(5)
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
                    # The payment date is yfinance's dividendDate when it falls
                    # on or after the ex-date (otherwise it's the last payment).
                    _db_pay = (pd.to_datetime(_db_upcoming["dividendDate"], errors="coerce", dayfirst=True)
                               if "dividendDate" in _db_upcoming.columns
                               else pd.Series(pd.NaT, index=_db_upcoming.index))
                    _dv_rows = []
                    for _dr_idx, _dr in _db_upcoming.iterrows():
                        _gross = float(_dr["_shares"]) * float(_dr["_rate"])
                        _wh_pct = get_dividend_withholding(exchange_key_for_ticker(_dr["Ticker"]), current_user().email)
                        _fwh = _gross * _wh_pct / 100
                        _net = round(_gross - _fwh - max(0.0, _gross - _fwh) * BE_WITHHOLDING_RATE, 2)
                        _dv_rows.append(dividend_row_html(
                            name=display_name(_dr["Name"]), ex_date=_dr["exDividendDate"],
                            pay_date=_db_pay.get(_dr_idx), net=_net, gross=_gross))
                    st.markdown(
                        '<div style="display:flex;justify-content:space-between;font-size:10px;letter-spacing:0.06em;'
                        'text-transform:uppercase;color:var(--muted);padding:6px 0;border-bottom:0.5px solid var(--line-2);">'
                        f'<span>{h_("Ex-date · payment")}</span><span>{h_("Net est.")}</span></div>'
                        + "".join(_dv_rows), unsafe_allow_html=True)
                else:
                    st.caption(_("No upcoming ex-dividend dates in the next 30 days."))
            else:
                st.caption(_("Ex-dividend dates not yet in cache — click Refresh in the screener."))
        else:
            st.caption(_("No screener data available for your holdings."))

    with _mv_col, st.container(key="db_card_movers", border=True):
        st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:8px;">{h_("Top movers today")}</div>',
                   unsafe_allow_html=True)
        _db_mv = _db_pf.dropna(subset=["name", "day_change_pct"]).copy()
        _db_mv["day_change_pct"] = pd.to_numeric(_db_mv["day_change_pct"], errors="coerce")
        _db_mv = _db_mv.dropna(subset=["day_change_pct"])
        _db_mv["_abs"] = _db_mv["day_change_pct"].abs()
        _db_top = _db_mv.sort_values("_abs", ascending=False).head(6).sort_values("day_change_pct", ascending=False)
        if not _db_top.empty:
            _mv_max = float(_db_top["_abs"].max()) or 1.0
            # The whole row opens the stock drawer (an invisible button over
            # it, as the Holdings rows do).
            _mv_scored = (_db_scr.drop_duplicates("Ticker").set_index("Ticker")
                          if not _db_scr.empty and "Ticker" in _db_scr.columns else pd.DataFrame())
            _mv_target = None
            for _mv_i, (_mr_idx, _mr) in enumerate(_db_top.iterrows()):
                with st.container(key=f"db_mover_{_mv_i}"):
                    st.markdown(mover_row_html(ticker=str(_mr["ticker"]), name=display_name(_mr["name"]),
                                               change_pct=float(_mr["day_change_pct"]), max_abs=_mv_max),
                                unsafe_allow_html=True)
                    if _mr["ticker"] in _mv_scored.index:
                        a11y.label(f"db_moverbtn_{_mv_i}", _("View {stock}", stock=a11y.stock_name(
                            str(_mr["ticker"]), display_name(_mr["name"]))))
                        if st.button(_("View details"), key=f"db_moverbtn_{_mv_i}"):
                            _mv_target = _mr
            if _mv_target is not None:
                # Same merged holding + scored row the Holdings table passes.
                open_drawer(_db_pf[_db_pf["ticker"] == _mv_target["ticker"]].merge(
                    _db_scr, left_on="ticker", right_on="Ticker", how="left", suffixes=("", "_scr")).iloc[0])
        else:
            st.caption(_("No daily price data available."))
