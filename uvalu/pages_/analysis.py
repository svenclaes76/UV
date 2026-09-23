"""Analysis page — full-page stock deep dive, reached from the drawer's
"View full analysis" link (uvalu/drawer.py). Ticker is passed via
st.session_state["_analysis_ticker"], set right before st.switch_page()."""
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

from portfolio import (load_portfolio, load_manual_tickers, load_div_hist,
                       dividend_income_summary, exchange_key_for_ticker,
                       load_dividend_meta)
from screener import (_fcf_hard_veto, _trend_veto, LEVERAGE_EXEMPT_SECTORS,
                      sector_for, decision_reason)
from settings import (load_shared_settings, get_veto_thresholds, get_score_weights,
                      ALL_EXCHANGES, get_dividend_withholding)
from uvalu import nav as nav_registry
from uvalu.data import _load_all_screener_data, _cache_version
from uvalu.components import (signal_badge_for_decision, signal_badge_html,
                              fair_value_ladder, six_model_ladder_rows,
                              six_model_ladder_reasons, six_model_ladder_caption,
                              sub_score_bar_html, quality_score_color,
                              veto_reason_str, is_hard_veto, skeleton_chart_html)
from uvalu.formatting import fmt_eur as _fmt_eur
from uvalu.runtime import theme_colors, current_user
from uvalu.ui import _CHART_CONFIG

_EXCHANGE_LABELS = {
    "brussels": "Brussels", "amsterdam": "Amsterdam", "paris": "Paris",
    "milan": "Milan", "frankfurt": "Frankfurt", "swiss": "Swiss",
}


@st.cache_data(show_spinner=False, ttl=3600)
def _fetch_price_history_1y_cached(ticker: str) -> pd.DataFrame:
    """1Y daily OHLC for the price-vs-fair-value chart. Cached for an hour —
    this is a single quick per-ticker call (unlike the multi-ticker
    fundamentals crawl's dedicated background lanes), so caching the common
    case (revisiting a ticker already viewed this session) is the right-sized
    fix rather than standing up a background thread for it. Left undecorated
    for failures (raises instead of swallowing) so st.cache_data doesn't
    pin a transient yfinance error as this ticker's result for the full TTL —
    see _fetch_price_history_1y, which is what callers should use."""
    return yf.Ticker(ticker).history(period="1y")


def _fetch_price_history_1y(ticker: str) -> pd.DataFrame:
    try:
        return _fetch_price_history_1y_cached(ticker)
    except Exception:
        return pd.DataFrame()


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
        _cache_version(), _enabled, tuple(_manual_tickers_map.keys()), tuple(_manual_tickers_map.values()),
        get_veto_thresholds(), get_score_weights())
    *_exch_dfs, _extra_df = _dfs
    all_df = pd.concat([
        d.assign(Exchange=_EXCHANGE_LABELS.get(k, k))
        for k, d in zip(ALL_EXCHANGES, _exch_dfs)
    ] + [_extra_df], ignore_index=True)
    _match = all_df[all_df["Ticker"] == ticker]
    if _match.empty:
        st.warning(f"No data found for **{ticker}**.")
        return
    row = _match.iloc[0]
    _sector = sector_for(ticker, row.get("sector"))

    # ── Header ────────────────────────────────────────────────────────────────
    kind, label = signal_badge_for_decision(row.get("Decision"), veto=row.get("veto"))
    _score = row.get("Value Score")
    if pd.notna(_score) and _score >= 70:
        _score_rating, _score_color = "Strong", "var(--up-txt, #0F6E56)"
    elif pd.notna(_score) and _score >= 40:
        _score_rating, _score_color = "Moderate", "#C98A3A"
    elif pd.notna(_score):
        _score_rating, _score_color = "Weak", "var(--down-txt, #A32D2D)"
    else:
        _score_rating, _score_color = None, None
    _score_rating_html = (f'<div style="font-size:12px;color:{_score_color};">{_score_rating}</div>'
                         if _score_rating else "")
    with st.container(key="an_header_row"):
        st.markdown(
            # Row 1: ticker + signal badge (left) baseline-paired with the
            # composite score label/value (right).
            f'<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;">'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<span style="font-family:var(--uv-mono);font-size:26px;font-weight:500;letter-spacing:-0.02em;">{ticker}</span>'
            f'{signal_badge_html(kind, label)}</div>'
            f'<div style="text-align:right;">'
            f'<div style="font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--faint);">Composite score</div>'
            f'<div style="font-family:var(--uv-mono);font-size:30px;font-weight:500;line-height:1;margin-top:6px;">'
            f'{f"{_score:.0f}" if pd.notna(_score) else "—"}</div></div></div>'
            # Row 2: company/sector/exchange caption (left) on the same line
            # as the score rating (right), matching row 1's baseline pairing.
            f'<div style="display:flex;align-items:baseline;justify-content:space-between;gap:16px;'
            f'margin-top:5px;margin-bottom:8px;">'
            f'<div style="font-size:13.5px;color:var(--muted);">'
            f'{row.get("Name", "—")} · {_sector or "—"} · {_fv(row, "Exchange")}</div>'
            f'{_score_rating_html}</div>',
            unsafe_allow_html=True,
        )

    # ── 4-card hero ───────────────────────────────────────────────────────────
    _pf = load_portfolio()
    _held_row = None
    if _pf is not None and not _pf.empty and "ticker" in _pf.columns:
        _m = _pf[_pf["ticker"] == ticker]
        if not _m.empty:
            _held_row = _m.iloc[0]
    _held_str = (f"{_held_row.get('shares', 0):.0f} shares" if _held_row is not None else "Not held")

    _mos_val = row.get("MoS %")
    _mos_color = ("var(--up-txt, #0F6E56)" if pd.notna(_mos_val) and _mos_val >= 0
                 else "var(--down-txt, #A32D2D)" if pd.notna(_mos_val) else "inherit")

    def _hero_card(label: str, value: str, color: str = "var(--text)") -> str:
        return (f'<div style="background:var(--panel);border:0.5px solid var(--line);border-radius:12px;'
               f'padding:15px 17px;box-shadow:var(--shadow);">'
               f'<div style="font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:0.06em;">'
               f'{label}</div>'
               f'<div style="font-family:var(--uv-mono);font-size:23px;font-weight:500;margin-top:8px;'
               f'color:{color};">{value}</div></div>')

    with st.container(key="an_hero_row"):
        st.markdown(
            '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;">'
            + _hero_card("Current price", _fv(row, "Price", _fmt_eur))
            + _hero_card("Composite fair value", _fv(row, "fair_value", _fmt_eur), color="var(--mint)")
            + _hero_card("Margin of safety", _fv(row, "MoS %", lambda v: f"{v:+.1f}%"), color=_mos_color)
            + _hero_card("Your position", _held_str)
            + '</div>',
            unsafe_allow_html=True,
        )

    if is_hard_veto(row.get("veto")):
        st.markdown(
            f'<div style="background:var(--navy);border-radius:12px;padding:15px 18px;display:flex;'
            f'gap:12px;align-items:flex-start;">'
            f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.7" '
            f'stroke-linecap="round" stroke-linejoin="round" style="flex:none;margin-top:1px;">'
            f'<path d="M12 9v4M12 17h.01M10.24 3.957l-8.422 14.06a1.9 1.9 0 0 0 1.636 2.983h16.844a1.9 1.9 0 0 0 '
            f'1.636 -2.983l-8.422 -14.06a1.9 1.9 0 0 0 -3.276 0z"/></svg>'
            f'<div><div style="font-size:13px;font-weight:500;color:#fff;">Hard veto active</div>'
            f'<div style="font-size:12.5px;color:rgba(245,247,250,0.72);margin-top:3px;line-height:1.5;">'
            f'{veto_reason_str(row)}.</div></div></div>',
            unsafe_allow_html=True,
        )
    else:
        # Why this Decision — which gate keeps it out of BUY, or why Avoid vs
        # Monitor (WP-DQ9). Vetoed names already get the banner above.
        _, _, _min_mos, _buy_thr = get_veto_thresholds()
        st.caption(decision_reason(row, buy_threshold=_buy_thr, min_mos=_min_mos))

    # ── Price vs fair value chart ─────────────────────────────────────────────
    _C = theme_colors()
    with st.container(key="an_card_chart", border=True):
        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
            st.markdown('<div style="font-size:15px;font-weight:500;">Price vs composite fair value · 1Y</div>',
                       unsafe_allow_html=True)
            with st.container(horizontal=True, gap="small", width="content"):
                st.markdown('<span style="display:flex;align-items:center;gap:6px;font-size:11.5px;'
                           'color:var(--muted);"><span style="width:12px;height:2px;background:#1DD6A4;'
                           'display:inline-block;"></span>Price</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="display:flex;align-items:center;gap:6px;font-size:11.5px;'
                           f'color:var(--muted);"><span style="width:12px;height:0;border-top:1.5px dashed '
                           f'{_C.axis};display:inline-block;"></span>Fair value</span>', unsafe_allow_html=True)
        # A placeholder so the skeleton (shown only on a genuine cache miss —
        # see _fetch_price_history_1y) is replaced by the real chart in place
        # rather than both stacking on the page.
        _chart_slot = st.empty()
        if ticker not in st.session_state.get("_an_hist_cache_warm", set()):
            _chart_slot.markdown(skeleton_chart_html(height=260), unsafe_allow_html=True)
        _hist = _fetch_price_history_1y(ticker)
        st.session_state.setdefault("_an_hist_cache_warm", set()).add(ticker)
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
                _fig.add_hline(y=float(_fv_val), line=dict(color=_C.axis, width=1.5, dash="dash"),
                              annotation_text=f"Fair value {_fmt_eur(float(_fv_val))}",
                              annotation_font=dict(color=_C.axis, size=11))
            _fig.update_layout(
                margin=dict(l=0, r=0, t=8, b=0), hovermode="x unified",
                yaxis=dict(tickprefix="€", tickfont=dict(color=_C.axis), gridcolor=_C.grid),
                xaxis=dict(showgrid=False, tickfont=dict(color=_C.axis)),
                font=dict(color=_C.axis), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            _chart_slot.plotly_chart(_fig, width="stretch", height=260, config=_CHART_CONFIG)
        else:
            _chart_slot.empty()

    # ── Sub-scores | six-model fair value ─────────────────────────────────────
    _col1, _col2 = st.columns([1, 1.25])
    with _col1, st.container(key="an_card_subscores", border=True):
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:16px;">Signal sub-scores</div>',
                   unsafe_allow_html=True)
        st.caption("Weighted components of the composite score.")
        for label_, field in [("Margin of safety", "Sub MoS"), ("Risk (inverted)", "Sub Risk"),
                              ("Quality", "Sub Quality"), ("Momentum", "Sub Momentum"),
                              ("Dividend", "Sub Dividend")]:
            v = row.get(field)
            if pd.notna(v):
                # These sub-scores are all higher-is-better, the opposite sense
                # of sub_score_bar_html's risk-scale default — pass the
                # matching quality scale explicitly.
                _bar_color, _ = quality_score_color(float(v))
                st.markdown(sub_score_bar_html(label_, float(v), color=_bar_color), unsafe_allow_html=True)
    with _col2, st.container(key="an_card_sixmodel", border=True):
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:12px;">Six-model fair value</div>',
                   unsafe_allow_html=True)
        _price = row.get("Price")
        if _price is not None and pd.notna(_price):
            # Same shared row builder as uvalu/drawer.py so the two screens never
            # show different names for the identical figure (incl. the FV-3
            # book-value / FCF fallback substitution).
            fair_value_ladder(
                price=float(_price),
                models=six_model_ladder_rows(row),
                composite=row.get("fair_value"),
                reasons=six_model_ladder_reasons(row),        # FV-6
                basis_count=row.get("fv_model_count"),
                basis_thin=bool(row.get("fv_basis_thin")),
            )
            _cap = six_model_ladder_caption(row)
            if _cap:
                st.caption(_cap)
            if bool(row.get("fair_value_clamped")):
                st.caption(
                    "⚑ Composite capped at the models' median — one model ran far "
                    "above the rest and the others don't corroborate it.")

    # ── Financials & valuation | hard-veto checks ─────────────────────────────
    _col3, _col4 = st.columns([1.25, 1])
    with _col3, st.container(key="an_card_financials", border=True):
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:6px;">Financials &amp; valuation</div>',
                   unsafe_allow_html=True)
        _de_val = row.get("debtToEquity")
        # Matches Uvalu.dc.html's 9-field set (EPS/P-E·fairP-E/ROE/Debt-equity/
        # FCF yield/Operating margin/Net margin/Dividend yield/Payout ratio) —
        # P/B, EV/EBITDA, ROA and Revenue growth (not in the design spec) are
        # dropped to make room for the fields that are. "fair P/E" is the real
        # fixed 15x multiple screener.py's pe_fair_value model itself applies
        # to EPS (see _pe_fair_value/pe_fv in screener.py), not a
        # separately-fetched figure. Order/column split (odd index → right
        # column) matches the mockup's 5-then-4 layout exactly.
        _pe_val = row.get("trailingPE")
        _fin_fields = [
            ("EPS (ttm)",             _fv(row, "trailingEps", lambda v: f"€{v:.2f}"), None),
            ("P/E · fair P/E",        f"{_pe_val:.1f}× · 15.0×" if pd.notna(_pe_val) else "—", None),
            ("Return on equity",      _fv(row, "returnOnEquity", lambda v: f"{v*100:.1f}%"),
             "up" if pd.notna(row.get("returnOnEquity")) and row.get("returnOnEquity") > 0.15
             else "down" if pd.notna(row.get("returnOnEquity")) and row.get("returnOnEquity") < 0 else None),
            ("Debt / equity",         _fv(row, "debtToEquity", lambda v: f"{v:.1f}"),
             "down" if pd.notna(_de_val) and _de_val > 150 else None),
            ("Free cash-flow yield",  _fv(row, "fcfYield", lambda v: f"{v*100:.1f}%"),
             "up" if pd.notna(row.get("fcfYield")) and row.get("fcfYield") > 0.03
             else "down" if pd.notna(row.get("fcfYield")) and row.get("fcfYield") <= 0 else None),
            ("Operating margin",      _fv(row, "operatingMargins", lambda v: f"{v*100:.1f}%"),
             "up" if pd.notna(row.get("operatingMargins")) and row.get("operatingMargins") > 0.15
             else "down" if pd.notna(row.get("operatingMargins")) and row.get("operatingMargins") < 0 else None),
            ("Net margin",            _fv(row, "profitMargins", lambda v: f"{v*100:.1f}%"),
             "up" if pd.notna(row.get("profitMargins")) and row.get("profitMargins") > 0.10
             else "down" if pd.notna(row.get("profitMargins")) and row.get("profitMargins") < 0 else None),
            ("Dividend yield",        _fv(row, "dividendYield", lambda v: f"{v*100:.2f}%"), None),
            ("Payout ratio",          _fv(row, "payoutRatio", lambda v: f"{v*100:.1f}%"),
             "down" if pd.notna(row.get("payoutRatio")) and row.get("payoutRatio") > 0.80 else None),
        ]
        _warn_colors = {"up": "var(--up-txt, #0F6E56)", "down": "var(--down-txt, #A32D2D)"}
        _fg1, _fg2 = st.columns(2)
        for _i, (_flabel, _fval, _fwarn) in enumerate(_fin_fields):
            with (_fg1 if _i % 2 == 0 else _fg2):
                _fcolor = _warn_colors.get(_fwarn, "inherit")
                st.markdown(
                    f'<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;'
                    f'border-bottom:0.5px solid var(--line-2);"><span style="font-size:12.5px;color:var(--muted);">'
                    f'{_flabel}</span><span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;'
                    f'color:{_fcolor};">{_fval}</span></div>',
                    unsafe_allow_html=True)
    with _col4, st.container(key="an_card_vetochecks", border=True):
        st.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:12px;">Hard-veto checks</div>',
                   unsafe_allow_html=True)
        _max_de_thr, _, _, _ = get_veto_thresholds()
        de = row.get("debtToEquity"); fcf = row.get("freeCashflow"); fcf_y = row.get("fcfYield")
        sector = _sector
        div_flag = row.get("Div Flag"); coverage = row.get("dividendCoverage")
        volume = row.get("averageVolume")
        # Terse note phrasing (bare value, no trailing sentence) matches
        # Uvalu.dc.html's checks model exactly (see modelDefs' `checks`
        # builder: de.toFixed(2)+'×', fcfY.toFixed(1)+'% yield', etc.) — our
        # rule set/thresholds are the app's real ones (Financials & valuation
        # veto thresholds are configurable, not the mockup's fixed 2.0×/3×/
        # 90%), but the "×"-multiple convention and "% yield" note both carry
        # over directly. The FCF check's note switched from a raw absolute
        # euro amount (fmt_eur has no thousands/M-B abbreviation, so a real
        # freeCashflow value rendered as an unreadable "€92937504.00") to the
        # already-computed fcfYield percentage, matching the design's own
        # note for this exact check and sidestepping that formatting gap.
        #
        # D/E and FCF pass/fail reuse screener.py's own veto helpers
        # (LEVERAGE_EXEMPT_SECTORS, _fcf_hard_veto) instead of re-deriving
        # simplified versions — a flat `de > threshold` or `fcf < 0` check
        # disagreed with the real `_hard_veto` formula (missing the sector
        # exemption and the 3-consecutive-year FCF rule respectively),
        # showing a red ✕ for checks the stock's actual Decision doesn't
        # treat as failing. See uvalu/components.py's veto_reason_str(),
        # which mirrors the same real formula for the veto banner text.
        _de_exempt = sector in LEVERAGE_EXEMPT_SECTORS
        _de_note = _fv(row, "debtToEquity", lambda v: f"{v/100:.2f}×")
        if _de_exempt and pd.notna(de) and de > _max_de_thr:
            _de_note = f"{_de_note} (sector-exempt)"
        # Dividend is a single AND-combined sub-condition in the real formula
        # (Div Flag == "At Risk" AND coverage < 1.0×), not two independent
        # checks — matches components.py's veto_reason_str() exactly, so a
        # flagged-but-adequately-covered dividend (or vice versa) doesn't
        # show a misleading red ✕ under "Hard-veto checks" for a factor that
        # isn't actually contributing to a veto in that state.
        _div_veto = div_flag == "At Risk" and pd.notna(coverage) and coverage < 1.0
        _div_note = f"{div_flag if div_flag else '—'} · {_fv(row, 'dividendCoverage', lambda v: f'{v:.2f}×')}"
        # Multi-year deterioration checks re-use screener._trend_veto directly —
        # same anti-drift reason as the D/E and FCF rows above. It returns the
        # list of tripped reasons; empty means the row passes.
        _trend_reasons = _trend_veto(row)
        _trend_note = _trend_reasons[0] if _trend_reasons else "—"
        # Zero-volume check re-uses the same `== 0` (not `.fillna(0)`) test as
        # compute_scores's `_hard_veto` — a confirmed zero fails, a missing
        # field passes (unreported volume isn't evidence of no trading).
        _no_trade = pd.notna(volume) and volume == 0
        _checks = [
            (f"Debt / equity below {_max_de_thr/100:.1f}×",
             not (pd.notna(de) and de > _max_de_thr) or _de_exempt, _de_note),
            ("Positive free cash flow", not _fcf_hard_veto(row),
             _fv(row, "fcfYield", lambda v: f"{v*100:.1f}% yield") if pd.notna(fcf_y) else _fv(row, "freeCashflow", _fmt_eur)),
            ("Dividend coverage adequate", not _div_veto, _div_note),
            ("No adverse multi-year trend", not _trend_reasons, _trend_note),
            ("Confirmed trading volume", not _no_trade, _fv(row, "averageVolume", lambda v: f"{v:,.0f}")),
        ]
        for check_label, passed, note in _checks:
            icon = "✓" if passed else "✕"
            bg = "var(--up-bg)" if passed else "var(--down-bg)"
            color = "var(--up-txt)" if passed else "var(--down-txt)"
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:11px;padding:9px 0;'
                f'border-bottom:0.5px solid var(--line-2);">'
                f'<span style="display:flex;align-items:center;justify-content:center;width:19px;height:19px;'
                f'border-radius:6px;font-size:11px;font-weight:700;flex:none;background:{bg};color:{color};">'
                f'{icon}</span>'
                f'<span style="flex:1;font-size:12.5px;">{check_label}</span>'
                f'<span style="font-family:var(--uv-mono);font-size:11.5px;color:var(--muted,#5F5E5A);">{note}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Dividend & income (WP-DIV5) ───────────────────────────────────────────
    _dy_fwd = row.get("dividendYield")
    _dps_trailing = row.get("trailingAnnualDividendRate")
    _dps_annual = _dps_trailing if pd.notna(_dps_trailing) and _dps_trailing else row.get("dividendRate")
    _div_hist_all = load_div_hist()
    _has_div_history = (_div_hist_all is not None and not _div_hist_all.empty
                        and "ticker" in _div_hist_all.columns and (_div_hist_all["ticker"] == ticker).any())
    if (pd.notna(_dy_fwd) and _dy_fwd and _dy_fwd > 0) or _has_div_history:
        with st.container(key="an_card_dividend", border=True):
            _dm_meta = load_dividend_meta().get(ticker, {}) or {}
            _dh_title, _dh_src = st.columns([2.2, 1], vertical_alignment="center")
            with _dh_title:
                _row_freq = row.get("dividendFrequency")
                _freq_label = _dm_meta.get("frequency") or (_row_freq if pd.notna(_row_freq) else None) or "—"
                _dps_label = f"€{_dps_annual:.2f} / share" if pd.notna(_dps_annual) and _dps_annual else "—"
                st.markdown(f'<div style="display:flex;align-items:center;gap:10px;">'
                           f'<span style="font-size:15px;font-weight:500;">Dividend &amp; income</span>'
                           f'<span style="font-size:11.5px;color:var(--muted);">{_freq_label} · {_dps_label}</span></div>',
                           unsafe_allow_html=True)
            with _dh_src:
                _src_auto = bool(_has_div_history and (_div_hist_all.loc[_div_hist_all["ticker"] == ticker]
                                 .sort_values("date").iloc[-1].get("source") == "auto"))
                _src_label = "Auto-fetched" if _src_auto else ("Manual entry" if _has_div_history else "Market data")
                _src_style = ("background:var(--uv-soft,rgba(29,214,164,.08));color:var(--uv-mint,#1DD6A4);"
                             if _src_auto or not _has_div_history else "border:0.5px solid var(--line);color:var(--muted);")
                st.markdown(f'<div style="text-align:right;"><span style="font-size:9.5px;font-family:var(--uv-mono);'
                           f'padding:2px 6px;border-radius:5px;{_src_style}">{_src_label}</span></div>',
                           unsafe_allow_html=True)

            _bt = None
            if _held_row is not None:
                _div_summary = dividend_income_summary(_div_hist_all, months=12)
                _tkr = _held_row.get("ticker")
                if _tkr in _div_summary.index:
                    _bt = _div_summary.loc[_tkr]
            _price_val = row.get("Price")
            _ttm_yield = (_bt["regular_gross_eur"] / (_held_row["shares"] * _price_val) * 100
                         if _bt is not None and _held_row is not None and pd.notna(_price_val) and _price_val
                         and _held_row["shares"] else None)
            _cost_val = (_held_row.get("purchase_value") if _held_row is not None else None)
            _yoc = (_bt["net_eur"] / _cost_val * 100
                   if _bt is not None and _cost_val is not None and pd.notna(_cost_val) and _cost_val else None)

            _dcol1, _dcol2 = st.columns([1.35, 1], gap="large")
            with _dcol1:
                def _stat(label: str, value: str, color: str = "inherit") -> str:
                    return (f'<div><div style="font-size:10px;color:var(--faint);text-transform:uppercase;'
                           f'letter-spacing:0.05em;">{label}</div><div style="font-family:var(--uv-mono);'
                           f'font-size:19px;font-weight:500;margin-top:5px;color:{color};">{value}</div></div>')
                st.markdown(
                    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;">'
                    + _stat("Yield · TTM", f"{_ttm_yield:.2f}%" if _ttm_yield is not None else "—")
                    + _stat("Yield · forward", f"{_dy_fwd*100:.2f}%" if pd.notna(_dy_fwd) and _dy_fwd else "—")
                    + _stat("Yield-on-cost · net", f"{_yoc:.2f}%" if _yoc is not None else "—", "var(--uv-mint,#1DD6A4)")
                    + _stat("Increase streak", f"{int(row.get('dividend_growth_streak') or 0)} yrs")
                    + '</div>', unsafe_allow_html=True)
                _payout_eps = row.get("payoutRatio")
                _payout_fcf = row.get("cashPayoutRatio")
                _wh_pct = get_dividend_withholding(exchange_key_for_ticker(ticker), current_user().email)
                _wh_label = f"{exchange_key_for_ticker(ticker) or '—'} {_wh_pct:.1f}% + BE 30%" if _wh_pct else "BE 30% only"
                _grid_rows = [
                    ("Income 12m · net", f"€{_bt['net_eur']:,.2f}" if _bt is not None else "—"),
                    ("Income 12m · gross", f"€{_bt['gross_eur']:,.2f}" if _bt is not None else "—"),
                    ("Payout ratio · EPS", f"{_payout_eps*100:.0f}%" if pd.notna(_payout_eps) else "—"),
                    ("Payout ratio · FCF/share", f"{_payout_fcf*100:.0f}%" if pd.notna(_payout_fcf) else "—"),
                    ("Growth · 1yr", f"{row.get('dgr_1y')*100:+.1f}%" if pd.notna(row.get("dgr_1y")) else "—"),
                    ("Growth · 3yr / 5yr CAGR",
                     f"{row.get('dgr_3y')*100:+.1f}% / {row.get('dgr_5y')*100:+.1f}%"
                     if pd.notna(row.get("dgr_3y")) and pd.notna(row.get("dgr_5y")) else "—"),
                    ("Withholding", _wh_label),
                    ("Feeds DDM inputs", "automatic"),
                ]
                _rg1, _rg2 = st.columns(2)
                for _i, (_glabel, _gval) in enumerate(_grid_rows):
                    with (_rg1 if _i % 2 == 0 else _rg2):
                        _gcolor = "var(--uv-mint,#1DD6A4)" if _glabel == "Feeds DDM inputs" else "inherit"
                        st.markdown(
                            f'<div style="display:flex;align-items:center;justify-content:space-between;padding:9px 0;'
                            f'border-bottom:0.5px solid var(--line-2);"><span style="font-size:12.5px;color:var(--muted);">'
                            f'{_glabel}</span><span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;'
                            f'color:{_gcolor};">{_gval}</span></div>', unsafe_allow_html=True)

                _cut_year = row.get("dividend_last_cut_year")
                if pd.notna(_cut_year) and _cut_year:
                    st.markdown(
                        f'<div style="margin-top:14px;padding:11px 13px;border-radius:8px;background:var(--down-bg,#FCEAEA);">'
                        f'<div style="font-size:12.5px;font-weight:500;color:var(--down-txt,#A32D2D);">Dividend cut detected</div>'
                        f'<div style="font-size:12px;color:var(--muted);margin-top:2px;">Annual dividend per share fell '
                        f'in {int(_cut_year)} versus the prior year.</div></div>', unsafe_allow_html=True)
                _incr_year = row.get("dividend_last_increase_year")
                if pd.notna(_incr_year) and _incr_year and not (pd.notna(_cut_year) and _cut_year):
                    st.caption(f"Dividend increase detected in {int(_incr_year)}.")

            with _dcol2:
                st.markdown('<div style="font-size:10px;color:var(--faint);text-transform:uppercase;'
                           'letter-spacing:0.05em;margin-bottom:10px;">Payment history · per share</div>',
                           unsafe_allow_html=True)
                if _has_div_history:
                    _bars = (_div_hist_all[_div_hist_all["ticker"] == ticker]
                            .assign(_d=pd.to_datetime(_div_hist_all["date"], errors="coerce"))
                            .sort_values("_d").tail(6))
                    _mx = max(float(pd.to_numeric(_bars["amount_per_share"], errors="coerce").max() or 0), 0.01)
                    _bar_html = '<div style="display:flex;align-items:flex-end;gap:8px;height:96px;">'
                    _label_html = '<div style="display:flex;gap:8px;margin-top:6px;">'
                    for _, _brow in _bars.iterrows():
                        _ps = float(pd.to_numeric(_brow.get("amount_per_share"), errors="coerce") or 0)
                        _h = max(6, round(_ps / _mx * 74))
                        _color = "#C98A3A" if _brow.get("div_type") == "Special" else "var(--uv-teal,#1A8C6E)"
                        _lbl = _brow["_d"].strftime("%b %y") if pd.notna(_brow["_d"]) else "—"
                        _bar_html += (f'<div style="width:44px;flex:none;display:flex;flex-direction:column;'
                                     f'align-items:center;justify-content:flex-end;gap:5px;">'
                                     f'<span style="font-family:var(--uv-mono);font-size:9.5px;color:var(--muted);">'
                                     f'€{_ps:.2f}</span><div style="width:100%;border-radius:4px 4px 0 0;'
                                     f'background:{_color};height:{_h}px;"></div></div>')
                        _label_html += (f'<span style="width:44px;flex:none;text-align:center;font-family:var(--uv-mono);'
                                       f'font-size:9px;color:var(--faint);">{_lbl}</span>')
                    st.markdown(_bar_html + '</div>' + _label_html + '</div>', unsafe_allow_html=True)
                else:
                    st.caption("No dividend events recorded yet for this holding.")

    # ── Value thesis (derived from real computed fields only) ────────────────
    _thesis_card = st.container(key="an_card_thesis", border=True)
    _thesis_card.markdown('<div style="font-size:15px;font-weight:500;margin-bottom:10px;">Value thesis</div>',
                          unsafe_allow_html=True)
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
    _thesis_card.caption(" ".join(_thesis))
