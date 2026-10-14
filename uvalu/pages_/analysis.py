"""Analysis page — full-page stock deep dive, reached from the drawer's
"View full analysis" link (uvalu/drawer.py). Ticker is passed via
st.session_state["_analysis_ticker"], set right before st.switch_page()."""
import html

import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

from portfolio import (load_portfolio, load_manual_tickers, load_div_hist,
                       dividend_income_summary, exchange_key_for_ticker,
                       load_dividend_meta)
from scoring import DIV_COVERAGE_MIN, dividend_risk_reasons
from screener import (_fcf_hard_veto, _trend_veto, LEVERAGE_EXEMPT_SECTORS,
                      sector_for, signal_reason)
from settings import (load_shared_settings, get_veto_thresholds, get_score_weights,
                      ALL_EXCHANGES, get_dividend_withholding)
from uvalu import nav as nav_registry
from uvalu.data import _load_all_screener_data, _cache_version
from uvalu.components import (_esc, back_link, fmt_mos_pct, model_signal_badge_html, signal_provenance_html, founder_notice_html,
                              fair_value_ladder, six_model_ladder_rows,
                              six_model_ladder_reasons, six_model_ladder_caption,
                              sub_score_bar_html, quality_score_color, score_band_label, mos_text_color,
                              veto_reason_str, is_hard_veto, skeleton_chart_html, empty_results_html)
from uvalu.formatting import display_name, exchange_label, fmt_eur as _fmt_eur
from uvalu.i18n import (N_, _, fmt_date, fmt_int, fmt_money, fmt_num, fmt_pct, h_, localize_fig,
                        lowercase_noun, ngettext, plotly_money_axis, tr)
from uvalu.runtime import brand_hoverlabel, theme_colors, current_user
from uvalu.ui import _CHART_CONFIG

_EXCHANGE_LABELS = {
    "brussels": N_("Brussels"), "amsterdam": N_("Amsterdam"), "paris": N_("Paris"),
    "milan": N_("Milan"), "frankfurt": N_("Frankfurt"), "swiss": N_("Swiss"),
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


_PANEL_TITLE = '<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:10px;">{title}</div>'
_KV_ROW = ('<div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;padding:8px 0;'
           'border-bottom:0.5px solid var(--line-2);font-size:12.5px;"><span style="color:var(--muted);">{k}</span>'
           '<span style="color:var(--text);line-height:1.5;">{v}</span></div>')


def _render_history_and_sensitivity(row, ticker: str, enabled: tuple, manual: dict) -> None:
    """Badge history of the last 12 months (REC-7, uvalu.compliance.signal_history)
    and the fair value at a ±1 pp discount rate (REC-6, display only, D2)."""
    from screener import DDM_STABLE_GROWTH, effective_min_mos, fair_value_sensitivity
    from uvalu.compliance import signal_history
    from uvalu.components import model_signal_badge_html
    from uvalu.data import universe_reference_for

    _h_col, _s_col = st.columns(2)
    with _h_col, st.container(key="an_card_history", border=True):
        st.markdown(_PANEL_TITLE.format(title=h_("Model signal history · 12 months")), unsafe_allow_html=True)
        try:
            _hist = signal_history.history_for(ticker)
        except Exception:
            _hist = []
        if not _hist:
            st.caption(_("No badge change recorded for this stock yet."))
        else:
            _rows = []
            _prev = None
            for rec in _hist:
                code = rec.get("signal_code")
                _from = (model_signal_badge_html(_prev) + ' <span style="color:var(--muted);">→</span> '
                         if _prev else "")
                _mos = rec.get("margin_of_safety")
                _note = _("score {score} · margin of safety {mos} · model {version}",
                          score=fmt_num(rec.get("Value Score"), 0),
                          mos=fmt_pct(_mos, 0, fraction=True, signed=True) if _mos is not None else "—",
                          version=str(rec.get("model_version") or "—"))
                # Date and badge(s) on one line, the inputs under the badge.
                _rows.append(
                    '<div style="display:grid;grid-template-columns:92px minmax(0,1fr);column-gap:12px;row-gap:5px;'
                    'align-items:center;padding:10px 0;border-bottom:0.5px solid var(--line-2);">'
                    f'<div style="font-family:var(--uv-mono);font-size:11.5px;color:var(--muted);">'
                    f'{html.escape(fmt_date(rec.get("signal_computed_at")))}</div>'
                    f'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">{_from}{model_signal_badge_html(code)}</div>'
                    f'<div></div><div style="font-size:12px;color:var(--muted);">{html.escape(_note)}</div></div>')
                _prev = code
            st.markdown("".join(reversed(_rows)), unsafe_allow_html=True)
        st.caption(_("Full log with inputs and model version is kept for every badge change."))

    with _s_col, st.container(key="an_card_sensitivity", border=True):
        from screener import MODEL_VERSION
        # Title with the shared-settings note on the same row (design reference).
        st.markdown(
            '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:10px;">'
            f'<span role="heading" aria-level="2" style="font-size:15px;font-weight:500;">{h_("Assumptions & sensitivity")}</span>'
            # Translators: Analysis › Assumptions & sensitivity, note beside the card title: the settings are the same for every user; {model} is the model version, e.g. "M1".
            f'<span style="font-size:11px;color:var(--muted);white-space:nowrap;">{h_("Shared settings · model {model}", model=MODEL_VERSION)}</span></div>',
            unsafe_allow_html=True)
        _thr = get_veto_thresholds()
        _ref_key = (tuple(enabled), tuple(manual.keys()), tuple(manual.values()),
                    tuple(_thr), tuple(get_score_weights()))
        _ref = universe_reference_for(_ref_key)
        _sens = fair_value_sensitivity(row, _ref) if _ref is not None else []
        _base = next((x for x in _sens if x["shift"] == 0.0), None)
        st.markdown(
            '<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:8px;">'
            + "".join(f'<div><div style="font-size:10px;color:var(--muted);text-transform:uppercase;'
                      f'letter-spacing:0.05em;">{k}</div><div style="font-family:var(--uv-mono);font-size:14px;'
                      f'margin-top:4px;">{v}</div></div>' for k, v in (
                          (h_("Discount rate"), fmt_pct(_base["discount_rate"], 1, fraction=True) if _base else "—"),
                          (h_("Terminal growth"), fmt_pct(DDM_STABLE_GROWTH, 1, fraction=True)),
                          (h_("MoS setting"), fmt_pct(effective_min_mos(_thr[2]), 0, fraction=True)),
                          (h_("Score setting"), fmt_num(_thr[3], 0))))
            + "</div>", unsafe_allow_html=True)
        def _sens_label(x) -> str:
            # Translators: Analysis › sensitivity row label: fair value at this discount rate, e.g. "Discount 8.0%".
            _lbl = _("Discount {rate}", rate=fmt_pct(x["discount_rate"], 1, fraction=True))
            # Translators: Analysis › sensitivity row: marks the discount rate in force, e.g. "Discount 8.0% · current".
            return _("{label} · current", label=_lbl) if x["shift"] == 0.0 else _lbl

        if _sens:
            # Label · fair value · margin of safety. No badge per scenario
            # (G17, D2): a shifted fair value never changes a signal.
            _sg = "display:grid;grid-template-columns:minmax(0,1.4fr) 80px 70px;gap:12px;align-items:center;"
            _num = "text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
            st.markdown("".join(
                f'<div style="{_sg}padding:8px 0;border-bottom:0.5px solid var(--line-2);font-size:12.5px;">'
                f'<span style="color:var(--muted);">'
                f'{html.escape(_sens_label(x))}</span>'
                f'<span style="{_num}">{_fmt_eur(x["fair_value"]) if x["fair_value"] is not None else "—"}</span>'
                f'<span style="{_num}color:{mos_text_color(x["margin_of_safety"] * 100 if x["margin_of_safety"] is not None else None)};">'
                f'{fmt_pct(x["margin_of_safety"], 0, fraction=True, signed=True) if x["margin_of_safety"] is not None else "—"}'
                f'</span></div>'
                for x in _sens), unsafe_allow_html=True)
        else:
            st.caption(_("The sensitivity table appears once the full stock universe has been scored."))
        st.caption(_("Fair values are model estimates of value, not forecasts of where the price will go. With 2% growth, raising the "
                     "discount rate from 8% to 9% lowers a dividend-model fair value by about 14%.") + " "
                   + _("The settings are shared model settings, the same for every user; this table changes no "
                       "score or signal."))


def _render_sources_and_producer(row, ticker: str) -> None:
    """Data sources with a freshness flag (REC-3) and who produces the
    output, with the founder disclosure (REC-1, REC-8)."""
    from screener import DATA_FLAG_LABELS, FOUNDER_HOLDS_NOTICE
    from uvalu.compliance import disclosures as d
    from uvalu.shell import enterprise_number, producer_name

    _d_col, _p_col = st.columns(2)
    with _d_col, st.container(key="an_card_sources", border=True):
        st.markdown(_PANEL_TITLE.format(title=h_("Data sources")), unsafe_allow_html=True)
        st.markdown("".join(_KV_ROW.format(k=h_(k), v=h_(v)) for k, v in d.DATA_SOURCE_ROWS),
                    unsafe_allow_html=True)
        _flags = row.get("data_flags")
        _flags = [f for f in (_flags if isinstance(_flags, list) else []) if f in DATA_FLAG_LABELS]
        _dot = "var(--amber-fill)" if _flags else "var(--mint)"
        _msg = " ".join(tr(DATA_FLAG_LABELS[f]) for f in _flags) if _flags else _("No data quality flags for this stock.")
        st.markdown(f'<div style="display:flex;gap:9px;align-items:flex-start;padding:10px 0 2px;font-size:12px;">'
                    f'<span style="width:7px;height:7px;border-radius:50%;flex:none;margin-top:5px;background:{_dot};"></span>'
                    f'<span style="color:var(--text);line-height:1.5;">{html.escape(_msg)}</span></div>',
                    unsafe_allow_html=True)

    with _p_col, st.container(key="an_card_producer", border=True):
        st.markdown(_PANEL_TITLE.format(title=h_("Producer & conflicts")), unsafe_allow_html=True)
        # The negative statement only when the flag is known; an unknown flag
        # (older cache) states nothing rather than "does not hold".
        _holds = row.get("founder_holds")
        _known = _holds is not None and not pd.isna(_holds)
        _founder = (tr(FOUNDER_HOLDS_NOTICE) if _known and bool(_holds)
                    else _("The founder does not hold {ticker}. A holding of any size would be shown here.",
                           ticker=ticker) if _known else None)
        _lines = [
            _("Produced automatically by {producer} ({number}).", producer=producer_name(),
              number=enterprise_number()) + " " + tr(d.NOT_SUPERVISED),
            _founder,
            # "No income" only while the beta is free (it must not outlive the paywall).
            (_("No payment from the issuer, brokers or data providers. Uvalu has no income during the free beta.")
             if d.BETA else _("No payment from the issuer, brokers or data providers.")),
        ]
        _lines = [x for x in _lines if x]
        st.markdown('<div style="display:flex;flex-direction:column;gap:8px;font-size:12.5px;color:var(--muted);'
                    'line-height:1.55;">' + "".join(f"<div>{html.escape(x)}</div>" for x in _lines)
                    + f'<a href="/legal?doc=conflicts" target="_self" style="color:var(--link);text-decoration:none;">'
                    f'{html.escape(_("Conflicts of interest policy →"))}</a></div>', unsafe_allow_html=True)


def _render_model_summary(row, ticker: str) -> None:
    """The plain-language model summary (derived from real computed fields
    only), the last card on the page (mockup), ending with the sentence that
    it is the same for every user and not a recommendation."""
    _thesis_card = st.container(key="an_card_thesis", border=True)
    _thesis_card.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:10px;">{h_("Model summary")}</div>',
                          unsafe_allow_html=True)
    _sub_fields = {N_("Margin of safety"): row.get("Sub MoS"), N_("Risk"): row.get("Sub Risk"),
                  N_("Quality"): row.get("Sub Quality"), N_("Momentum"): row.get("Sub Momentum"),
                  N_("Dividend"): row.get("Sub Dividend")}
    _valid_subs = {k: v for k, v in _sub_fields.items() if pd.notna(v)}
    _thesis = [_("{name} trades at {price} against an estimated model fair value of {fair_value} ({mos} margin of safety).",
                 name=display_name(row.get('Name')) or ticker, price=_fv(row, 'Price', _fmt_eur),
                 fair_value=_fv(row, 'fair_value', _fmt_eur),
                 mos=_fv(row, 'MoS %', lambda v: fmt_mos_pct(v, compact=True)))]
    if _valid_subs:
        _best = max(_valid_subs, key=_valid_subs.get)
        _worst = min(_valid_subs, key=_valid_subs.get)
        if _best != _worst:
            _thesis.append(_("Scores highest on {best} ({best_score}/100) and weakest on {worst} ({worst_score}/100).",
                             best=lowercase_noun(tr(_best)), best_score=fmt_num(_valid_subs[_best], 0),
                             worst=lowercase_noun(tr(_worst)), worst_score=fmt_num(_valid_subs[_worst], 0)))
    _thesis.append(_("Generated from the model outputs above; the same text is shown to every user. "
                     "It is general information, not personal advice: it does not take your situation or objectives into account."))
    _thesis_card.markdown(f'<div style="font-size:13.5px;color:var(--muted);line-height:1.65;">'
                          f'{html.escape(" ".join(_thesis))}</div>', unsafe_allow_html=True)


def render() -> None:
    ticker = st.session_state.get("_analysis_ticker")

    # Back to the page the stock was opened from (uvalu/nav.py), not always
    # the Dashboard.
    _back_page, _back_key = nav_registry.back_target("analysis")
    if _back_page is not None and back_link(_("← Back to {page}", page=_back_page.title), key="an_back"):
        st.switch_page(_back_page)

    if not ticker:
        # The app's own empty state, not Streamlit's blue st.info banner.
        with st.container(key="an_empty", border=True):
            st.markdown(empty_results_html(
                h_("No stock selected. Open a stock from any table (Dashboard, Screener, Watchlist, Portfolio, Risk) to view its full analysis here.")),
                unsafe_allow_html=True)
            _scr_page = nav_registry.pages.get("screener")
            if _scr_page is not None:
                with st.container(horizontal_alignment="center"):
                    if st.button(_("Open the screener"), key="an_empty_screener", type="primary"):
                        st.switch_page(_scr_page)
        return

    _settings = load_shared_settings()
    _enabled  = tuple(_settings.get("enabled_exchanges", ALL_EXCHANGES))
    _manual_tickers_map = load_manual_tickers()
    _dfs = _load_all_screener_data(
        _cache_version(), _enabled, tuple(_manual_tickers_map.keys()), tuple(_manual_tickers_map.values()),
        get_veto_thresholds(), get_score_weights())
    _exch_dfs, _extra_df = list(_dfs[:-1]), _dfs[-1]
    all_df = pd.concat([
        d.assign(Exchange=_EXCHANGE_LABELS.get(k, k))
        for k, d in zip(ALL_EXCHANGES, _exch_dfs)
    ] + [_extra_df], ignore_index=True)
    _match = all_df[all_df["Ticker"] == ticker]
    if _match.empty:
        st.warning(_("No data found for **{ticker}**.", ticker=ticker))
        return
    row = _match.iloc[0]
    _sector = sector_for(ticker, row.get("sector"))

    # ── Header ────────────────────────────────────────────────────────────────
    _score = row.get("Value Score")
    _excluded = is_hard_veto(row.get("veto"))
    # Where the score sits on the model scale (PER-4: no verdict words). A
    # stock that fails a quality screen is excluded from scoring: its stored
    # 0 is not a position on the scale, so show "—" and say why, the way the
    # drawer's "excluded" does (the header used to read "0 · Lower range").
    # The band label is a position, not good or bad news: --up-txt for every
    # band (mockup), muted when there is no position on the scale.
    _score_rating = score_band_label(_score, excluded=_excluded)
    _score_color = "var(--muted)" if _excluded or pd.isna(_score) else "var(--up-txt)"
    _score_rating_html = (f'<div style="font-size:12px;color:{_score_color};">{_score_rating}</div>'
                         if _score_rating else "")
    with st.container(key="an_header_row"):
        st.markdown(
            # Row 1: ticker + signal badge (left) baseline-paired with the
            # composite score label/value (right).
            f'<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;">'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<span style="font-family:var(--uv-mono);font-size:26px;font-weight:500;letter-spacing:-0.02em;">{_esc(ticker)}</span>'
            f'{model_signal_badge_html(row.get("signal_code"), veto=row.get("veto"), qualified=True)}</div>'
            f'<div style="text-align:right;">'
            f'<div style="font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--muted);">{h_("Composite score")}</div>'
            f'<div style="font-family:var(--uv-mono);font-size:30px;font-weight:500;line-height:1;margin-top:6px;">'
            f'{"—" if _excluded else fmt_num(_score, 0)}</div></div></div>'
            # Row 2: company/sector/exchange caption (left) on the same line
            # as the score rating (right), matching row 1's baseline pairing.
            f'<div style="display:flex;align-items:baseline;justify-content:space-between;gap:16px;'
            f'margin-top:5px;margin-bottom:8px;">'
            f'<div style="font-size:13.5px;color:var(--muted);">'
            f'{html.escape(display_name(row.get("Name")) or "—")} · {tr(_sector) if _sector else "—"} · {exchange_label(ticker, row.get("Exchange"))}</div>'
            f'{_score_rating_html}</div>'
            f'{signal_provenance_html(row)}{founder_notice_html(row)}',
            unsafe_allow_html=True,
        )

    # ── 4-card hero ───────────────────────────────────────────────────────────
    _pf = load_portfolio()
    _held_row = None
    if _pf is not None and not _pf.empty and "ticker" in _pf.columns:
        _m = _pf[_pf["ticker"] == ticker]
        if not _m.empty:
            _held_row = _m.iloc[0]
    if _held_row is not None:
        _held_n = int(_held_row.get('shares', 0) or 0)
        _held_px = row.get("Price")
        _held_str = (h_("{count} shares · {value}", count=fmt_num(_held_n, 0),
                        value=_fmt_eur(_held_n * float(_held_px))) if pd.notna(_held_px) else
                     ngettext("{count} share", "{count} shares", _held_n))
    else:
        _held_str = h_("Not held")

    _mos_val = row.get("MoS %")
    _mos_color = mos_text_color(_mos_val)

    def _hero_card(label: str, value: str, color: str = "var(--text)", *, small: bool = False) -> str:
        _value_font = ("font-size:13px;margin-top:14px;" if small else
                       "font-family:var(--uv-mono);font-size:23px;margin-top:8px;")
        return (f'<div style="background:var(--panel);border:0.5px solid var(--line);border-radius:12px;'
               f'padding:15px 17px;box-shadow:var(--shadow);">'
               f'<div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;">'
               f'{label}</div>'
               f'<div style="{_value_font}font-weight:500;color:{color};">{value}</div></div>')

    with st.container(key="an_hero_row"):
        st.markdown(
            '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;">'
            + _hero_card(h_("Current price"), _fv(row, "Price", _fmt_eur))
            + _hero_card(h_("Composite fair value · estimate"), _fv(row, "fair_value", _fmt_eur), color="var(--text)")
            + _hero_card(h_("Margin of safety"), _fv(row, "MoS %", fmt_mos_pct), color=_mos_color)
            + _hero_card(h_("Your position"), _held_str, small=True)
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
            f'<div><div style="font-size:13px;font-weight:500;color:#fff;">{h_("Screened out")}</div>'
            f'<div style="font-size:12.5px;color:rgba(245,247,250,0.72);margin-top:3px;line-height:1.5;">'
            f'{veto_reason_str(row)}.</div></div></div>',
            unsafe_allow_html=True,
        )
    else:
        # Which rule produced this signal (REC-2, WP-DQ9). Names failing the
        # quality screen already get the banner above.
        _min_mos, _buy_thr = get_veto_thresholds()[2:4]
        st.caption(signal_reason(row, buy_threshold=_buy_thr, min_mos=_min_mos))

    # ── Price vs fair value chart ─────────────────────────────────────────────
    _C = theme_colors()
    with st.container(key="an_card_chart", border=True):
        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
            st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;">{h_("Price vs composite fair value · 1Y")}</div>',
                       unsafe_allow_html=True)
            with st.container(horizontal=True, gap="small", width="content"):
                st.markdown('<span style="display:flex;align-items:center;gap:6px;font-size:11.5px;'
                           'color:var(--muted);"><span style="width:12px;height:2px;background:#1DD6A4;'
                           f'display:inline-block;"></span>{h_("Price")}</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="display:flex;align-items:center;gap:6px;font-size:11.5px;'
                           f'color:var(--muted);"><span style="width:12px;height:0;border-top:1.5px dashed '
                           f'{_C.axis};display:inline-block;"></span>{h_("Fair value")}</span>', unsafe_allow_html=True)
        # A placeholder so the skeleton (shown only on a genuine cache miss —
        # see _fetch_price_history_1y) is replaced by the real chart in place
        # rather than both stacking on the page.
        _chart_slot = st.empty()
        if ticker not in st.session_state.get("_an_hist_cache_warm", set()):
            _chart_slot.markdown(skeleton_chart_html(height=200), unsafe_allow_html=True)
        _hist = _fetch_price_history_1y(ticker)
        st.session_state.setdefault("_an_hist_cache_warm", set()).add(ticker)
        if not _hist.empty:
            _hist.index = pd.to_datetime(_hist.index).tz_localize(None)
            _fig = go.Figure()
            _fig.add_trace(go.Scatter(
                x=_hist.index, y=_hist["Close"], mode="lines", name=_("Price"),
                line=dict(color="#1DD6A4", width=2),
                fill="tozeroy", fillcolor="rgba(29,214,164,0.07)",
            ))
            _fv_val = row.get("fair_value")
            if pd.notna(_fv_val):
                _fig.add_hline(y=float(_fv_val), line=dict(color=_C.axis, width=1.5, dash="dash"),
                              annotation_text=_("Fair value {amount}", amount=_fmt_eur(float(_fv_val))),
                              annotation_font=dict(color=_C.axis, size=11))
            _fig.update_layout(
                margin=dict(l=0, r=0, t=8, b=0), hovermode="x unified",
                yaxis=dict(**plotly_money_axis("EUR", decimals=0), tickfont=dict(color=_C.axis), gridcolor=_C.grid),
                xaxis=dict(showgrid=False, tickfont=dict(color=_C.axis)),
                font=dict(color=_C.axis), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                hoverlabel=brand_hoverlabel(_C),
            )
            localize_fig(_fig)
            _chart_slot.plotly_chart(_fig, width="stretch", height=200, config=_CHART_CONFIG)
        else:
            _chart_slot.empty()

    # ── Sub-scores | six-model fair value ─────────────────────────────────────
    # Row proportions of the design reference: the models table gets the
    # extra room here, the financials grid in the next row; badge history /
    # sensitivity and sources / producer split 1 : 1.
    _col1, _col2 = st.columns([1, 1.25])
    with _col1, st.container(key="an_card_subscores", border=True):
        st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:16px;">{h_("Signal sub-scores")}</div>',
                   unsafe_allow_html=True)
        st.caption(_("Weighted components of the composite score."))
        for label_, field in [(h_("Margin of safety"), "Sub MoS"), (h_("Risk (inverted)"), "Sub Risk"),
                              (h_("Quality"), "Sub Quality"), (h_("Momentum"), "Sub Momentum"),
                              (h_("Dividend"), "Sub Dividend")]:
            v = row.get(field)
            if pd.notna(v):
                # These sub-scores are all higher-is-better, the opposite sense
                # of sub_score_bar_html's risk-scale default — pass the
                # matching quality scale explicitly.
                st.markdown(sub_score_bar_html(label_, float(v), color=quality_score_color(float(v))),
                            unsafe_allow_html=True)
    with _col2, st.container(key="an_card_sixmodel", border=True):
        st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:12px;">{h_("Model fair values")}</div>',
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
                st.caption(_("⚑ Composite capped at the models' median — one model ran far above the rest and the others don't corroborate it."))

    # ── Financials & valuation | hard-veto checks ─────────────────────────────
    _col3, _col4 = st.columns([1.25, 1])
    with _col3, st.container(key="an_card_financials", border=True):
        st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:6px;">{h_("Financials & valuation")}</div>',
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
            (h_("EPS (ttm)"),         _fv(row, "trailingEps", lambda v: fmt_money(v, "EUR")), None),
            (h_("P/E · fair P/E"),    f"{fmt_num(_pe_val, 1)}× · {fmt_num(15.0, 1)}×" if pd.notna(_pe_val) else "—", None),
            (h_("Return on equity"),  _fv(row, "returnOnEquity", lambda v: fmt_pct(v, fraction=True)),
             "up" if pd.notna(row.get("returnOnEquity")) and row.get("returnOnEquity") > 0.15
             else "down" if pd.notna(row.get("returnOnEquity")) and row.get("returnOnEquity") < 0 else None),
            (h_("Debt / equity"),     _fv(row, "debtToEquity", lambda v: fmt_num(v, 1)),
             "down" if pd.notna(_de_val) and _de_val > 150 else None),
            (h_("Free cash-flow yield"), _fv(row, "fcfYield", lambda v: fmt_pct(v, fraction=True)),
             "up" if pd.notna(row.get("fcfYield")) and row.get("fcfYield") > 0.03
             else "down" if pd.notna(row.get("fcfYield")) and row.get("fcfYield") <= 0 else None),
            (h_("Operating margin"),  _fv(row, "operatingMargins", lambda v: fmt_pct(v, fraction=True)),
             "up" if pd.notna(row.get("operatingMargins")) and row.get("operatingMargins") > 0.15
             else "down" if pd.notna(row.get("operatingMargins")) and row.get("operatingMargins") < 0 else None),
            (h_("Net margin"),        _fv(row, "profitMargins", lambda v: fmt_pct(v, fraction=True)),
             "up" if pd.notna(row.get("profitMargins")) and row.get("profitMargins") > 0.10
             else "down" if pd.notna(row.get("profitMargins")) and row.get("profitMargins") < 0 else None),
            (h_("Dividend yield"),    _fv(row, "dividendYield", lambda v: fmt_pct(v, 2, fraction=True)), None),
            (h_("Payout ratio"),      _fv(row, "payoutRatio", lambda v: fmt_pct(v, fraction=True)),
             "down" if pd.notna(row.get("payoutRatio")) and row.get("payoutRatio") > 0.80 else None),
        ]
        # Financial warnings in amber: red is reserved for a failed quality screen.
        _warn_colors = {"up": "var(--up-txt)", "down": "var(--amber-txt)"}
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
        st.markdown(f'<div role="heading" aria-level="2" style="font-size:15px;font-weight:500;margin-bottom:12px;">{h_("Quality screen checks")}</div>',
                   unsafe_allow_html=True)
        _max_de_thr = get_veto_thresholds()[0]
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
        # showing a red ✕ for checks the stock's actual signal doesn't
        # treat as failing. See uvalu/components.py's veto_reason_str(),
        # which mirrors the same real formula for the veto banner text.
        _de_exempt = sector in LEVERAGE_EXEMPT_SECTORS
        _de_note = _fv(row, "debtToEquity", lambda v: f"{fmt_num(v / 100, 2)}×")
        if _de_exempt and pd.notna(de) and de > _max_de_thr:
            _de_note = _("{value} (sector-exempt)", value=_de_note)
        # Dividend is a single AND-combined sub-condition in the real formula
        # (Div Flag == "At Risk" AND coverage < 1.0×), not two independent
        # checks — matches components.py's veto_reason_str() exactly, so a
        # flagged-but-adequately-covered dividend (or vice versa) doesn't
        # show a misleading red ✕ under "Hard-veto checks" for a factor that
        # isn't actually contributing to a veto in that state.
        _div_veto = div_flag == "At Risk" and pd.notna(coverage) and coverage < 1.0
        _div_note = _fv(row, "dividendCoverage", lambda v: fmt_num(v, 2) + "×")
        # Flagged "At Risk" but not vetoed (still covered by earnings): an
        # amber warning with the reason, not a green ✓ next to "At Risk".
        _div_warn = div_flag == "At Risk" and not _div_veto
        if div_flag == "At Risk":
            _reason_text = {
                "payout": lambda: _("payout {pct}", pct=fmt_pct(row.get("payoutRatio"), 0, fraction=True)),
                "cash_payout": lambda: _("FCF payout {pct}", pct=fmt_pct(row.get("cashPayoutRatio"), 0, fraction=True)),
                "coverage": lambda: _("cover under {ratio}", ratio=fmt_num(DIV_COVERAGE_MIN, 1) + "×"),
                "recent_cut": lambda: _("cut in {year}", year=str(int(row.get("dividend_last_cut_year")))),
            }
            _reasons = [_reason_text[r]() for r in dividend_risk_reasons(row, max_payout=get_veto_thresholds()[1])]
            if _reasons:
                # Without a coverage figure there's nothing to put before the
                # "·" (it read "— · at risk: payout 774%").
                _div_note = (_("{coverage} · at risk: {reasons}", coverage=_div_note, reasons=", ".join(_reasons))
                             if _div_note != "—" else _("at risk: {reasons}", reasons=", ".join(_reasons)))
        # Multi-year deterioration checks re-use screener._trend_veto directly —
        # same anti-drift reason as the D/E and FCF rows above. It returns the
        # list of tripped reasons; empty means the row passes.
        _trend_reasons = _trend_veto(row)
        _trend_note = tr(_trend_reasons[0]) if _trend_reasons else "—"
        # Zero-volume check re-uses the same `== 0` (not `.fillna(0)`) test as
        # compute_scores's `_hard_veto` — a confirmed zero fails, a missing
        # field passes (unreported volume isn't evidence of no trading).
        _no_trade = pd.notna(volume) and volume == 0
        _checks = [
            (h_("Debt / equity below {limit}×", limit=fmt_num(_max_de_thr / 100, 1)),
             not (pd.notna(de) and de > _max_de_thr) or _de_exempt, _de_note),
            (h_("Positive free cash flow"), not _fcf_hard_veto(row),
             _fv(row, "fcfYield", lambda v: _("{value}% yield", value=fmt_num(v * 100, 1)))
             if pd.notna(fcf_y) else _fv(row, "freeCashflow", _fmt_eur)),
            (h_("Dividend covered by earnings"), "warn" if _div_warn else not _div_veto, _div_note),
            (h_("No adverse multi-year trend"), not _trend_reasons, _trend_note),
            (h_("Confirmed trading volume"), not _no_trade, _fv(row, "averageVolume", fmt_int)),
        ]
        for check_label, passed, note in _checks:
            if passed == "warn":   # passes the veto, but flagged — see the dividend row
                icon, bg, color = "!", "var(--amber-bg)", "var(--amber-txt)"
            else:
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
                _freq_label = _dm_meta.get("frequency") or (_row_freq if pd.notna(_row_freq) else None)
                _freq_label = tr(_freq_label) if _freq_label else "—"
                _dps_label = (h_("{amount} / share", amount=fmt_money(_dps_annual, "EUR"))
                              if pd.notna(_dps_annual) and _dps_annual else "—")
                st.markdown(f'<div style="display:flex;align-items:center;gap:10px;">'
                           f'<span role="heading" aria-level="2" style="font-size:15px;font-weight:500;">{h_("Dividend & income")}</span>'
                           f'<span style="font-size:11.5px;color:var(--muted);">{_freq_label} · {_dps_label}</span></div>',
                           unsafe_allow_html=True)
            with _dh_src:
                _src_auto = bool(_has_div_history and (_div_hist_all.loc[_div_hist_all["ticker"] == ticker]
                                 .sort_values("date").iloc[-1].get("source") == "auto"))
                _src_label = h_("Auto-fetched") if _src_auto else (h_("Manual entry") if _has_div_history else h_("Market data"))
                _src_style = ("background:var(--soft);color:var(--up-txt);"
                             if _src_auto or not _has_div_history else "border:0.5px solid var(--line);color:var(--muted);")
                st.markdown(f'<div style="text-align:right;"><span style="font-size:9.5px;font-family:var(--uv-mono);'
                           f'padding:2px 6px;border-radius:6px;{_src_style}">{_src_label}</span></div>',
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
                    return (f'<div><div style="font-size:10px;color:var(--muted);text-transform:uppercase;'
                           f'letter-spacing:0.05em;">{label}</div><div style="font-family:var(--uv-mono);'
                           f'font-size:19px;font-weight:500;margin-top:5px;color:{color};">{value}</div></div>')
                st.markdown(
                    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;">'
                    + _stat(h_("Yield · TTM"), fmt_pct(_ttm_yield, 2) if _ttm_yield is not None else "—")
                    + _stat(h_("Yield · forward"), fmt_pct(_dy_fwd, 2, fraction=True) if pd.notna(_dy_fwd) and _dy_fwd else "—")
                    + _stat(h_("Yield-on-cost · net"), fmt_pct(_yoc, 2) if _yoc is not None else "—", "var(--up-txt)")
                    + _stat(h_("Increase streak"), ngettext("{count} yr", "{count} yrs",
                                                           int(row.get('dividend_growth_streak') or 0)))
                    + '</div>', unsafe_allow_html=True)
                _payout_eps = row.get("payoutRatio")
                _payout_fcf = row.get("cashPayoutRatio")
                _wh_pct = get_dividend_withholding(exchange_key_for_ticker(ticker), current_user().email)
                _wh_label = (h_("{exchange} {rate}% + BE 30%", exchange=exchange_key_for_ticker(ticker) or '—',
                                rate=fmt_num(_wh_pct, 1)) if _wh_pct else h_("BE 30% only"))
                _ddm_label = h_("Feeds DDM inputs")
                _grid_rows = [
                    (h_("Income 12m · net"), fmt_money(_bt['net_eur'], "EUR") if _bt is not None else "—"),
                    (h_("Income 12m · gross"), fmt_money(_bt['gross_eur'], "EUR") if _bt is not None else "—"),
                    (h_("Payout ratio · EPS"), fmt_pct(_payout_eps, 0, fraction=True) if pd.notna(_payout_eps) else "—"),
                    (h_("Payout ratio · FCF/share"), fmt_pct(_payout_fcf, 0, fraction=True) if pd.notna(_payout_fcf) else "—"),
                    (h_("Growth · 1yr"), fmt_pct(row.get('dgr_1y'), fraction=True, signed=True) if pd.notna(row.get("dgr_1y")) else "—"),
                    (h_("Growth · 3yr / 5yr CAGR"),
                     f"{fmt_pct(row.get('dgr_3y'), fraction=True, signed=True)} / {fmt_pct(row.get('dgr_5y'), fraction=True, signed=True)}"
                     if pd.notna(row.get("dgr_3y")) and pd.notna(row.get("dgr_5y")) else "—"),
                    (h_("Withholding"), _wh_label),
                    (_ddm_label, h_("automatic")),
                ]
                _rg1, _rg2 = st.columns(2)
                for _i, (_glabel, _gval) in enumerate(_grid_rows):
                    with (_rg1 if _i % 2 == 0 else _rg2):
                        _gcolor = "var(--up-txt)" if _glabel == _ddm_label else "inherit"
                        st.markdown(
                            f'<div style="display:flex;align-items:center;justify-content:space-between;padding:9px 0;'
                            f'border-bottom:0.5px solid var(--line-2);"><span style="font-size:12.5px;color:var(--muted);">'
                            f'{_glabel}</span><span style="font-family:var(--uv-mono);font-size:12.5px;'
                            f'color:{_gcolor};">{_gval}</span></div>', unsafe_allow_html=True)

                _cut_year = row.get("dividend_last_cut_year")
                if pd.notna(_cut_year) and _cut_year:
                    st.markdown(
                        f'<div style="margin-top:14px;padding:11px 13px;border-radius:8px;background:var(--amber-bg);">'
                        f'<div style="font-size:12.5px;font-weight:500;color:var(--amber-txt);">{h_("Dividend cut detected")}</div>'
                        f'<div style="font-size:12px;color:var(--muted);margin-top:2px;">'
                        f'{h_("Annual dividend per share fell in {year} versus the prior year.", year=str(int(_cut_year)))}</div></div>',
                        unsafe_allow_html=True)
                _incr_year = row.get("dividend_last_increase_year")
                if pd.notna(_incr_year) and _incr_year and not (pd.notna(_cut_year) and _cut_year):
                    st.caption(_("Dividend increase detected in {year}.", year=str(int(_incr_year))))

            with _dcol2:
                st.markdown('<div style="font-size:10px;color:var(--muted);text-transform:uppercase;'
                           f'letter-spacing:0.05em;margin-bottom:10px;">{h_("Payment history · per share")}</div>',
                           unsafe_allow_html=True)
                if _has_div_history:
                    _bars = (_div_hist_all[_div_hist_all["ticker"] == ticker]
                            .assign(_d=pd.to_datetime(_div_hist_all["date"], errors="coerce"))
                            .sort_values("_d").tail(6))
                    _mx = max(float(pd.to_numeric(_bars["amount_per_share"], errors="coerce").max() or 0), 0.01)
                    _bar_html = '<div style="display:flex;align-items:flex-end;gap:8px;height:96px;">'
                    _label_html = '<div style="display:flex;gap:8px;margin-top:6px;">'
                    for _bidx, _brow in _bars.iterrows():
                        _ps = float(pd.to_numeric(_brow.get("amount_per_share"), errors="coerce") or 0)
                        _h = max(6, round(_ps / _mx * 74))
                        _color = "#C98A3A" if _brow.get("div_type") == "Special" else "var(--teal)"
                        _lbl = fmt_date(_brow["_d"], skeleton="yyMMM") if pd.notna(_brow["_d"]) else "—"
                        _bar_html += (f'<div style="width:44px;flex:none;display:flex;flex-direction:column;'
                                     f'align-items:center;justify-content:flex-end;gap:5px;">'
                                     f'<span style="font-family:var(--uv-mono);font-size:9.5px;color:var(--muted);">'
                                     f'{fmt_money(_ps, "EUR")}</span><div style="width:100%;border-radius:4px 4px 0 0;'
                                     f'background:{_color};height:{_h}px;"></div></div>')
                        _label_html += (f'<span style="width:44px;flex:none;text-align:center;font-family:var(--uv-mono);'
                                       f'font-size:9px;color:var(--muted);">{_lbl}</span>')
                    st.markdown(_bar_html + '</div>' + _label_html + '</div>', unsafe_allow_html=True)
                else:
                    st.caption(_("No dividend events recorded yet for this holding."))

    # ── Badge history | assumptions & sensitivity (REC-6, REC-7) ─────────────
    _render_history_and_sensitivity(row, ticker, _enabled, _manual_tickers_map)
    # ── Data sources | producer & conflicts (REC-1, REC-3, REC-8) ────────────
    _render_sources_and_producer(row, ticker)
    # ── Model summary: the last card, a reading of everything above ──────────
    _render_model_summary(row, ticker)

