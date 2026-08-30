"""Portfolio risk page — composite score, concentration, VaR, factors, stress."""
from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st

import risk as _risk_module
from portfolio import (load_portfolio, load_sold, load_targets,
                       load_risk_snapshot, save_risk_snapshot)
from portfolio_enrichment import enrich_for_risk
from screener import load_fundamentals_cache
from settings import load_shared_settings, get_veto_thresholds, ALL_EXCHANGES
from uvalu.data import (_load_all_screener_data, _cache_version, _fetch_prices_cached,
                        _load_portfolio_screener_data, _portfolio_cache_version)
from uvalu.drawer import open_drawer
from uvalu.components import score_color, radial_gauge_svg, risk_holding_row_html, RISK_HOLDINGS_GRID_COLS
from uvalu.ui import price_autorefresh

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


def _loading_tier(abs_val: float) -> tuple[str, str]:
    """(tier word, color) for a factor loading's absolute value — matches
    Uvalu.dc.html's f.rate/f.rateColor. Elevated's 1.5 boundary is the same
    real threshold this page's own caption/heatmap already use for
    "concentrated factor bet"; Low/Moderate splits the remaining range at
    half that, since the real data only ever documented the one cutoff."""
    if abs_val <= 0.75:
        return "Low", "var(--uv-mint)"
    if abs_val <= 1.5:
        return "Moderate", "#C98A3A"
    return "Elevated", "var(--down-txt)"


def render() -> None:
    pf = load_portfolio()
    if pf is None or pf.empty:
        st.info("No portfolio loaded. Add positions in the Portfolio tab first.")
        st.stop()

    # Live prices on the shared portfolio cadence (see uvalu/ui.py).
    price_autorefresh("risk_refresh")

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
    *_risk_exch_dfs, _ = _load_all_screener_data(
        _cache_version(), _risk_enabled, thresholds=get_veto_thresholds())
    _risk_port_df  = _load_portfolio_screener_data(
        _portfolio_cache_version(), _risk_extra_tickers, _risk_extra_names, get_veto_thresholds())
    # Held tickers that also sit on an enabled exchange appear in both frames;
    # keep="last" lets the portfolio lane's row (priority-fetched, its own
    # cadence) win so every downstream lookup — _veto_lookup, _risk_scr_by_ticker
    # — agrees on one row per ticker.
    _risk_scr_df   = pd.concat(list(_risk_exch_dfs) + [_risk_port_df], ignore_index=True)
    if "Ticker" in _risk_scr_df.columns:
        _risk_scr_df = _risk_scr_df.drop_duplicates(subset="Ticker", keep="last").reset_index(drop=True)

    # Real hard-veto lookup (screener's own `veto` column) — feeds both
    # assess_portfolio()'s Stage 8 rebalance trigger below and the concentration
    # alert box / holdings table's Flag column further down.
    _veto_lookup = _risk_scr_df.set_index("Ticker")["veto"].to_dict() if "veto" in _risk_scr_df.columns else {}

    # ── Enrich the portfolio for the risk engine — live price + the
    # fundamentals-derived fields (fair value, sector, country, dividend rate)
    # looked up from the screener's own scored DataFrame so this page's numbers
    # match the Screener/Analysis pages. See portfolio_enrichment. ────────────
    _risk_scr_by_ticker = _risk_scr_df.drop_duplicates(subset="Ticker", keep="first").set_index("Ticker")
    _risk_live = _fetch_prices_cached(tuple(pf["ticker"].tolist()))
    pf = enrich_for_risk(pf, _risk_scr_by_ticker, _risk_live)

    _risk_full_cache = load_fundamentals_cache()

    _income_portfolio = False

    # Target allocation + the prior day's snapshot feed Stage 8's drift triggers.
    _targets        = load_targets()
    _prior_snapshot = load_risk_snapshot()

    # ── Cached risk report (1-hour TTL stored in session_state) ──────────────
    # Not keyed on the snapshot: writing today's snapshot below would otherwise
    # self-invalidate the cache on the very next render. The 1-hour TTL covers
    # day rollover in practice.
    _risk_cache_key = str((tuple(sorted(pf["ticker"].tolist())), _income_portfolio,
                           tuple(sorted(_veto_lookup.items())),
                           repr(sorted(_targets.items()))))
    _risk_cached    = st.session_state.get("_risk_report_cache", {})
    _risk_report: _risk_module.RiskReport | None = None

    if (_risk_cached.get("key") == _risk_cache_key and "report" in _risk_cached):
        _gen_at = datetime.fromisoformat(_risk_cached["report"].generated_at)
        _age_s  = (datetime.now(timezone.utc) - _gen_at).total_seconds()
        if _age_s < 3600:
            _risk_report = _risk_cached["report"]

    if _risk_report is None:
        try:
            _risk_report = _risk_module.assess_portfolio(
                pf, _risk_full_cache, _income_portfolio, _veto_lookup,
                targets=_targets, prior_snapshot=_prior_snapshot)
            st.session_state["_risk_report_cache"] = {"key": _risk_cache_key, "report": _risk_report}
        except Exception as _risk_err:
            st.error(f"Risk assessment failed: {_risk_err}")
            st.stop()

        # Upsert today's snapshot as the reference point for future drift
        # checks — only once per day, so the diff is against a real prior run.
        if _prior_snapshot.get("date") != date.today().isoformat():
            try:
                save_risk_snapshot(_risk_module.snapshot_from_report(_risk_report))
            except Exception:
                pass

    r = _risk_report

    # ══ Top section — score gauge, factor/concentration, risk contribution ═══
    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Risk assessment</div>',
               unsafe_allow_html=True)
    st.caption("Factor exposures, concentration and per-holding risk contribution across the portfolio.")

    # ── Score gauge + metric grid — matches Uvalu.dc.html's 300px/1fr card row,
    # both panels stretched to the row's tallest via risk_card_'s shared CSS.
    # Widened from the spec's literal 300px:1fr (~1:3.55) to 1:2.2 per Sven's
    # feedback — the gauge card's wrapped 3-line description needed more
    # room than a pixel-exact ratio gave it at this app's content width. ────
    _gauge_col, _metrics_col = st.columns([1, 2.2])
    with _gauge_col, st.container(key="risk_card_gauge", border=True):
        _ring_color, _label_color = score_color(r.composite.score)
        st.markdown(f"""<div style="display:flex;flex-direction:column;align-items:center;text-align:center;">
<div style="position:relative;width:132px;height:132px;">
  {radial_gauge_svg(r.composite.score, _ring_color, size=132)}
  <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">
    <span style="font-family:var(--uv-mono);font-size:34px;font-weight:500;line-height:1;">{r.composite.score:.0f}</span>
    <span style="font-size:9.5px;letter-spacing:0.08em;color:var(--faint);margin-top:3px;">/ 100</span>
  </div>
</div>
<div style="font-size:16px;font-weight:500;margin-top:14px;color:{_label_color};">{r.composite.label} risk</div>
<div style="font-size:12px;color:var(--muted);margin-top:6px;line-height:1.5;">Blended score across six risk factors, weighted by exposure and hard-veto flags.</div>
</div>""", unsafe_allow_html=True)
    with _metrics_col, st.container(key="risk_card_metrics", border=True):
        # Plain grid cells (no st.metric()) — st.metric() is styled app-wide
        # as a boxed mint-tinted KPI tile (styles.py's stMetric rule), which
        # doesn't match the mockup's unboxed 3x2 stat grid here.
        # Show the direct-regression beta alongside the weighted-sum one when
        # they diverge enough to be worth a second look.
        _beta_sub = r.quant.beta_label
        _pbr = r.quant.portfolio_beta_regression
        if _pbr is not None and abs(_pbr - r.quant.portfolio_beta) >= 0.15:
            _beta_sub = f"{r.quant.beta_label} · regression {_pbr:.2f}"

        _metric_defs = [
            ("BETA", f"{r.quant.portfolio_beta:.2f}", _beta_sub),
            ("VOLATILITY", f"{r.quant.volatility_annual:.1%}" if r.quant.volatility_annual else "N/A", r.quant.volatility_label),
            ("MAX DRAWDOWN (1Y)", f"{r.quant.mdd_1y:.1%}" if r.quant.mdd_1y else "N/A", r.quant.mdd_label),
            ("SHARPE", f"{r.quant.sharpe:.2f}" if r.quant.sharpe else "N/A", r.quant.ratio_label),
            ("VAR 95% (1D)", f"{r.quant.var_95_1d_pct:.1%}" if r.quant.var_95_1d_pct else "N/A", "Max expected 1-day loss"),
            ("SECTOR HHI", f"{r.concentration.hhi:.2f}", r.concentration.hhi_label),
        ]
        _cells = "".join(
            f'<div style="padding:18px 20px;">'
            f'<div style="font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--faint);">{_l}</div>'
            f'<div style="font-family:var(--uv-mono);font-size:24px;font-weight:500;margin-top:9px;line-height:1;">{_v}</div>'
            f'<div style="font-size:11px;color:var(--faint);margin-top:7px;">{_s}</div></div>'
            for _l, _v, _s in _metric_defs
        )
        st.markdown(f'<div style="display:grid;grid-template-columns:repeat(3,1fr);">{_cells}</div>',
                   unsafe_allow_html=True)

    # ── Factor breakdown + concentration — matches the mockup's 1.35fr/1fr
    # card row; kept on real Fama-French loadings/concentration data, only
    # the chrome (card panel, 7px bars, plain-text values) matches the spec —
    # the mockup's own factor list (Concentration/Leverage/Market/Volatility/
    # Cyclicality/FX exposure, 0-100 scale) is illustrative demo data, not a
    # second real model this app computes. ──────────────────────────────────
    _factor_col, _conc_col = st.columns([1.35, 1])

    with _factor_col, st.container(key="risk_card_factors", border=True):
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:16px;">Risk factor breakdown</div>',
                   unsafe_allow_html=True)
        if r.factor.available and r.factor.loadings:
            for _fname, _fval in r.factor.loadings.items():
                _rate, _fcolor = _loading_tier(abs(_fval))
                st.markdown(
                    f'<div style="margin-bottom:15px;">'
                    f'<div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:7px;">'
                    f'<span style="font-size:12.5px;font-weight:500;">{_fname}</span>'
                    f'<span style="font-size:11px;font-weight:500;color:{_fcolor};font-family:var(--uv-mono);">{_rate} · {_fval:+.2f}</span></div>'
                    f'<div style="height:7px;border-radius:4px;background:var(--panel-2);overflow:hidden;">'
                    f'<div style="width:{min(100, abs(_fval)/2.0*100):.0f}%;height:7px;border-radius:4px;background:{_fcolor};"></div></div>'
                    f'<div style="font-size:11px;color:var(--faint);margin-top:6px;">{_FACTOR_NOTES.get(_fname, "")}</div></div>',
                    unsafe_allow_html=True,
                )
            _prov = []
            if r.factor.factor_set:
                _prov.append(f"{r.factor.factor_set.title()} 5-factor + momentum set")
            if r.factor.as_of:
                _prov.append(f"as of {r.factor.as_of}")
            if r.factor.stale:
                _prov.append("cached — source unreachable")
            _prov_txt = (" · " + " · ".join(_prov)) if _prov else ""
            st.caption(f"Fama-French factor loadings{_prov_txt}. |loading| > 1.5 = concentrated factor bet.")
        else:
            st.caption("Factor analysis unavailable. " + (r.factor.flags[0] if r.factor.flags else ""))

    with _conc_col, st.container(key="risk_card_conc", border=True):
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:16px;">Concentration</div>',
                   unsafe_allow_html=True)
        c = r.concentration
        # Matches Uvalu.dc.html's 3-row set (Top 3 positions/Largest sector/
        # Largest single name) instead of Single name/Largest sector/Largest
        # country — geo concentration is still surfaced via the flag banner
        # below when c.geo_flag trips, just not as one of these 3 bars.
        # Top 3's 35% limit is the same real threshold top3_flag already uses.
        # pd.notna(), not a bare truthiness check — a position missing sector
        # metadata makes largest_sector an actual NaN float (not None), and
        # NaN is truthy in Python (same recurring gotcha noted across this
        # redesign, see [[uvalu-redesign-v2]]) — `if c.largest_sector` let the
        # literal string "nan" through into the label/flag text.
        _has_sector = pd.notna(c.largest_sector)
        _sector_label = f"Largest sector — {c.largest_sector}" if _has_sector else "Largest sector"
        for _label, _val, _limit in [
            ("Top 3 positions", c.top3_weight, 0.35),
            (_sector_label,     c.sector_weights.get(c.largest_sector, 0.0) if _has_sector else 0.0, 0.30),
            ("Largest single name", c.top1_weight, 0.15),
        ]:
            # Only the bar is status-colored (red once over its limit) — the
            # value text itself stays plain, matching the mockup's `c.value`
            # (no conditional color in the template, unlike the old version
            # here which colored both).
            _bar_color = "var(--down-txt)" if _val > _limit else "var(--teal)"
            st.markdown(
                f'<div style="margin-bottom:16px;">'
                f'<div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:7px;">'
                f'<span style="font-size:12.5px;color:var(--muted);">{_label}</span>'
                f'<span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;">{_val:.1%}</span></div>'
                f'<div style="height:7px;border-radius:4px;background:var(--panel-2);overflow:hidden;">'
                f'<div style="width:{min(100, _val/_limit*100):.0f}%;height:7px;border-radius:4px;background:{_bar_color};"></div></div></div>',
                unsafe_allow_html=True,
            )

        _flags = []
        if c.top1_flag:
            _flags.append(f"{c.top1_ticker} at {c.top1_weight:.0%} exceeds the 15% single-name limit")
        if c.sector_flag and _has_sector:
            _flags.append(f"{c.largest_sector} at {c.sector_weights.get(c.largest_sector, 0):.0%} exceeds the 30% sector limit")
        if c.geo_flag and c.largest_geo:
            _flags.append(f"{c.largest_geo} at {c.geo_weights.get(c.largest_geo, 0):.0%} exceeds the 60% country limit")
        _veto_tickers = [t for t in pf["ticker"] if bool(_veto_lookup.get(t, False))]
        _veto_names = pf[pf["ticker"].isin(_veto_tickers)]["name"].tolist()
        if _veto_names:
            _flags.append(f"{', '.join(_veto_names)} remain(s) under a hard veto")
        _alert_msg = (" · ".join(_flags) + ".") if _flags else \
            "All positions sit within the 15% single-name, 30% sector, and 60% country limits."
        # Same navy alert-box + warning-triangle icon as Analysis's hard-veto
        # box (analysis.py) — matches Uvalu.dc.html's Risk-screen concentration
        # alert exactly (16px icon here vs. Analysis's 18px, per that page's
        # own spec).
        st.markdown(
            f'<div style="margin-top:4px;padding:12px 14px;border-radius:10px;background:var(--navy);'
            f'display:flex;gap:10px;align-items:flex-start;">'
            f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.7" '
            f'stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px;">'
            f'<path d="M12 9v4M12 17h.01M10.24 3.957l-8.422 14.06a1.9 1.9 0 0 0 1.636 2.983h16.844a1.9 1.9 0 0 0 '
            f'1.636 -2.983l-8.422 -14.06a1.9 1.9 0 0 0 -3.276 0z"/></svg>'
            f'<div style="font-size:11.5px;color:rgba(245,247,250,0.8);line-height:1.5;">{_alert_msg}</div></div>',
            unsafe_allow_html=True,
        )

    # ── Risk contribution by holding — CSS-grid rows (components.py's
    # risk_holding_row_html) matching the mockup's fixed-px grid-template,
    # same convention as the Dashboard's db_hold_ rows (whole-row click via
    # an invisible trailing button, not st.columns per cell). ─────────────
    with st.container(key="risk_card_holdings", border=True):
        with st.container(key="risk_col_header"):
            _rh_labels = ("Position", "Weight", "Beta", "Vol", "Contribution to risk", "Flag")
            _rh_align = ("left", "right", "right", "right", "left", "left")
            _rh_cells = "".join(
                f'<div style="text-align:{_a};">{_l}</div>' for _l, _a in zip(_rh_labels, _rh_align))
            st.markdown(f'<div style="display:grid;grid-template-columns:{RISK_HOLDINGS_GRID_COLS};gap:14px;'
                       f'font-size:10px;letter-spacing:0.06em;text-transform:uppercase;color:var(--faint);">'
                       f'{_rh_cells}</div>', unsafe_allow_html=True)

        _contrib_rows = []
        for p in r.position_profiles:
            _exch = next((v for suf, v in _TICKER_SUFFIX_EXCHANGE.items() if p.ticker.endswith(suf)), "—")
            _contrib_rows.append({"p": p, "exch": _exch, "raw": p.weight * abs(p.beta or 0)})
        _total_raw = sum(row["raw"] for row in _contrib_rows) or 1.0
        _max_pct = max((row["raw"] / _total_raw * 100 for row in _contrib_rows), default=1.0) or 1.0
        _contrib_rows.sort(key=lambda row: row["raw"], reverse=True)

        _risk_dlg_pending: list = []
        for _idx, _crow in enumerate(_contrib_rows):
            p = _crow["p"]
            _contrib_pct = _crow["raw"] / _total_raw * 100
            # Flag mirrors the mockup's Leverage-veto/High-volatility/Size
            # semantics but stays on real fields: a real hard veto (from the
            # screener's own `veto` column) beats the aggregated position
            # rating, which is only surfaced here for High/Critical — Low/
            # Medium render blank, matching the mockup's mostly-empty column.
            if bool(_veto_lookup.get(p.ticker, False)):
                _flag, _flag_color = "Veto", "var(--down-txt)"
            elif p.rating == "Critical":
                _flag, _flag_color = "Critical", "var(--down-txt)"
            elif p.rating == "High":
                _flag, _flag_color = "High risk", "#C98A3A"
            else:
                _flag, _flag_color = "", "var(--faint)"
            with st.container(key=f"risk_hold_{_idx}_{p.ticker}"):
                st.markdown(risk_holding_row_html(
                    ticker=p.ticker, exchange=_crow["exch"], name=p.name,
                    weight_pct=p.weight * 100, beta=p.beta,
                    vol_pct=p.vol_annual * 100 if p.vol_annual is not None else None,
                    contrib_pct=_contrib_pct, contrib_bar_pct=_contrib_pct / _max_pct * 100,
                    flag=_flag, flag_color=_flag_color,
                ), unsafe_allow_html=True)
                if st.button("View", key=f"risk_hold_{_idx}_{p.ticker}_view"):
                    _sel_row = _risk_scr_df[_risk_scr_df["Ticker"] == p.ticker]
                    if not _sel_row.empty:
                        _risk_dlg_pending.append((_sel_row.iloc[0], None))

    # Dispatch at most one detail dialog per render
    if _risk_dlg_pending:
        open_drawer(*_risk_dlg_pending[0])
