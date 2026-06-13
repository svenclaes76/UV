"""Streamlit web app — Euronext Brussels value screener + portfolio tracker."""

# ── Column help texts (shown as header tooltips and in the help dialog) ───────
COLUMN_HELP = {
    # ── Core ──────────────────────────────────────────────────────────────────
    "★":             "Watchlist — check to add this stock to your personal watchlist.",
    "Company":       "Full company name as reported by the exchange.",
    "Ticker":        "Exchange ticker symbol (suffix indicates the exchange: .BR Brussels · .AS Amsterdam · .PA Paris · .MI Milan · .DE Frankfurt · .SW Zurich).",
    "Price":         "Current market price in the stock's local currency.",
    "💎 UV":         (
        "Weighted composite intrinsic value estimate from up to 5 models: "
        "Graham Number, PE Fair Value, EPV, DDM (single + multi-stage), and Analyst Target. "
        "Weights adjust automatically: DDM weight is zero for non-dividend payers or payout > 90%."
    ),
    "Analyst Target": "Mean analyst consensus price target from covering analysts.",
    "MoS %":         (
        "Margin of Safety = (Fair Value − Price) / Fair Value. "
        "Positive = stock trades below estimated fair value; negative = above it. "
        "A buffer of 20–30% is typically required before a stock enters the buy zone."
    ),
    "TER %":         (
        "Total Expected Return = Capital Gain % + Forward Dividend Yield + Expected DGR. "
        "A combined 1-year return estimate. > 15% = attractive · 8–15% = acceptable · < 8% = unattractive."
    ),
    "Score":         (
        "Composite score 0–100 with decision signal. "
        "🟢 Strong Buy (> 70) · 🟡 Monitor (40–70) · 🔴 Avoid (< 40). "
        "Formula: 30% MoS rank + 18% (100 − Risk rank) + 22% Quality rank + 15% Momentum rank + 15% Dividend rank. "
        "Hard veto rules force Avoid regardless of score: D/E > 5×, negative FCF, or dividend coverage < 1.0× with sustainability flag."
    ),
    # ── Valuation models ──────────────────────────────────────────────────────
    "Graham #":      (
        "Graham Number = √(22.5 × EPS × BVPS). "
        "A conservative deep-value floor based on earnings and book value. "
        "Price below this level suggests potential significant undervaluation."
    ),
    "PE Fair Val":   "PE Fair Value = EPS × 15. Graham's assumed fair multiple for a no-growth company. Simple earnings-based floor.",
    "EPV":           (
        "Earnings Power Value = EBIT × (1 − tax rate) / WACC, scaled to per-share via the EV ratio. "
        "A zero-growth anchor — what the business is worth as a going concern with no future expansion assumed."
    ),
    "DDM (1-stage)": (
        "Single-stage Gordon Growth DDM: P = D₁ / (r − g). "
        "Uses earnings growth as DGR proxy, capped at 5%. Best for stable, mature dividend payers."
    ),
    "DDM (2-stage)": (
        "Two-stage DDM: 5-year high-growth phase (earnings growth as proxy) "
        "followed by a 2% stable terminal growth rate. Better captures companies still growing their dividend."
    ),
    # ── Risk & size ───────────────────────────────────────────────────────────
    "Risk Score":    (
        "Composite risk level 0–10 (higher = riskier). "
        "Average of 5 dimensions: financial health (D/E, current ratio, interest coverage), "
        "earnings quality (FCF vs net income), market risk (beta), dividend risk (payout, coverage), "
        "and liquidity (average daily volume). Inverted so 0 = lowest risk."
    ),
    "Mkt Cap":       "Market capitalisation = current price × shares outstanding.",
    "Beta":          "Market sensitivity vs benchmark index. > 1 = amplifies market moves; < 1 = more defensive.",
    "Debt/Equity":   (
        "Total debt / equity. yfinance reports this as ×100 — so 150 = 1.5×. "
        "Lower = less financial leverage. Hard veto triggers at > 5× (D/E > 500 in raw data)."
    ),
    # ── Multiples ─────────────────────────────────────────────────────────────
    "P/E":           "Price-to-Earnings ratio. Lower generally indicates cheaper valuation — always compare within the same sector.",
    "P/B":           "Price-to-Book ratio. < 1 may signal undervaluation, particularly for banks and asset-heavy companies.",
    "EV/EBITDA":     "Enterprise Value / EBITDA. Capital-structure-neutral valuation multiple — useful for comparing companies with different debt levels. Lower = cheaper.",
    # ── Quality ───────────────────────────────────────────────────────────────
    "ROE %":         "Return on Equity = net income / shareholders' equity. Measures how efficiently the company generates profit from equity. > 15% is generally strong.",
    "ROA %":         "Return on Assets = net income / total assets. Measures how efficiently the company uses its asset base to generate earnings.",
    "Op Margin %":   "Operating margin = operating income / revenue. Core profitability before interest and tax — a measure of business quality.",
    "FCF Yield %":   "Free Cash Flow Yield = FCF / Market Cap. > 5% suggests the business generates meaningful cash relative to its price.",
    # ── Growth ────────────────────────────────────────────────────────────────
    "Rev Growth %":  "Year-over-year revenue growth. Positive = growing top line.",
    "EPS Growth %":  (
        "Year-over-year earnings-per-share growth. "
        "Also used as a proxy for the dividend growth rate (DGR) where direct DPS history is unavailable."
    ),
    # ── Dividends ─────────────────────────────────────────────────────────────
    "Div Yield":     "Trailing dividend yield = annual DPS / current price. A yield significantly above the 5-year average may indicate the stock is cheap relative to its own history.",
    "5yr Avg Yield": "5-year average dividend yield for this stock. Benchmark for the current yield — current yield above this suggests potential undervaluation on an income basis.",
    "Payout Ratio":  "Earnings payout ratio = DPS / EPS. 30–70% = sustainable range; > 85% = elevated risk of a dividend cut.",
    "Cash Payout":   "Cash payout ratio = (DPS × shares) / FCF. Should be < 80% to confirm the dividend is backed by free cash flow, not just reported earnings.",
    "Div Coverage":  "Dividend coverage ratio = EPS / DPS. > 1.5× is safe; < 1.2× triggers a sustainability flag.",
    "Div Flag":      (
        "Dividend sustainability assessment. "
        "✅ OK = all payout checks pass. "
        "⚠️ At Risk = one or more thresholds breached: payout ratio > 90%, cash payout > 80%, or coverage < 1.2×. "
        "Flagged stocks require an additional Margin of Safety buffer (+5–10 pp) to compensate for income risk."
    ),
}

import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from prices import fetch_prices
from backup import export_zip, export_excel, import_zip, backup_filename

from fetch_tickers import (fetch_brussels_tickers, fetch_amsterdam_tickers,
                            fetch_paris_tickers, fetch_milan_tickers,
                            fetch_frankfurt_tickers, fetch_swiss_tickers,
                            _hardcoded_bel20, _hardcoded_aex25, _hardcoded_cac40,
                            _hardcoded_ftse_mib, _hardcoded_dax40, _hardcoded_smi20)
from screener import (CACHE_FILE, CACHE_TTL_HOURS, _load_cache,
                      run_screener_from_df, fetch_fundamentals_nowait,
                      get_fetch_progress, cancel_background_fetch,
                      clear_live_cache, _file_lock)
import risk as _risk_module
from settings import (load_shared_settings, save_shared_settings,
                      load_settings, save_settings, ALL_EXCHANGES, EXCHANGE_LABELS)
from portfolio import (parse_excel, save_portfolio, save_sold, save_div_hist,
                       load_portfolio, load_sold, load_div_hist,
                       add_position, remove_positions, update_positions,
                       sell_position,
                       add_dividend, update_div_hist,
                       save_watchlist, load_watchlist, set_user, user_data_dir, portfolio_exists,
                       load_value_history, record_value_snapshot, backfill_value_history)
from auth import register, login, verify_token, list_users, set_role, delete_user, ROLES

@st.dialog("Add user", width="large")
def _dlg_add_user():
    _c1, _c2, _c3 = st.columns([3, 3, 2])
    with _c1:
        new_email = st.text_input("Email")
    with _c2:
        new_password = st.text_input("Password", type="password")
    with _c3:
        new_role_sel = st.selectbox("Role", options=list(ROLES))
    _, _save_col = st.columns([3, 1])
    with _save_col:
        if st.button("💾 Save", key="dlg_add_user_save", width="stretch"):
            ok, msg = register(new_email, new_password, role=new_role_sel)
            if ok:
                st.rerun()
            else:
                st.error(msg)


@st.dialog("Edit users", width="large")
def _dlg_edit_user(users: list[dict]):
    current_email = st.session_state.get("user_email", "")
    _tbl = pd.DataFrame([
        {
            "🗑️":      False,
            "Email":   u["email"],
            "Role":    u["role"],
            "Created": u["created_at"][:10],
        }
        for u in users
    ])

    _row_h  = 35
    _header = 35
    _height = _header + min(len(_tbl), 8) * _row_h

    _edited = st.data_editor(
        _tbl,
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        height=_height,
        column_config={
            "🗑️":      st.column_config.CheckboxColumn("🗑️",    width=55),
            "Email":   st.column_config.TextColumn("Email",    disabled=True, pinned=True),
            "Role":    st.column_config.SelectboxColumn("Role", options=list(ROLES)),
            "Created": st.column_config.TextColumn("Created",  disabled=True),
        },
        key="dlg_edit_user_table",
    )

    to_delete  = _edited[_edited["🗑️"]].index.tolist()
    to_keep    = _edited[~_edited["🗑️"]]
    n_selected = len(to_delete)

    _del_note, _save_col = st.columns([3, 1])
    with _del_note:
        if n_selected:
            st.caption(f"🗑️ {n_selected} selected for deletion")
    with _save_col:
        if st.button("💾 Save", key="dlg_edit_user_save", width="stretch"):
            for _, row in to_keep.iterrows():
                set_role(row["Email"], row["Role"])
            for i in to_delete:
                email = _tbl.iloc[i]["Email"]
                if email != current_email:
                    delete_user(email)
            st.rerun()


def _render_admin_users():
    """User management UI — rendered inside the Settings page."""
    users = list_users()

    _u1, _u2, _ = st.columns([1, 1, 6], gap="small")
    with _u1:
        if st.button("➕ Add", key="btn_add_user"):
            _dlg_add_user()
    with _u2:
        if st.button("✏️ Edit", key="btn_edit_user", disabled=not users):
            _dlg_edit_user(users)

    if not users:
        st.info("No users found.")
        return

    _row_h  = 35
    _header = 38
    _height = min(_header + len(users) * _row_h + 4, 600)

    user_df = pd.DataFrame([
        {
            "Email":      u["email"],
            "Role":       u["role"],
            "Created":    u["created_at"][:10],
        }
        for u in users
    ])
    st.dataframe(
        user_df,
        width="stretch",
        hide_index=True,
        height=_height,
        column_config={
            "Email":   st.column_config.TextColumn("Email",   pinned=True),
            "Role":    st.column_config.TextColumn("Role"),
            "Created": st.column_config.TextColumn("Created"),
        },
    )


def _render_help():
    """Full-page column reference, one tab per section."""
    sections = {
        "Core UV":          ["★", "Company", "Ticker", "Price", "Analyst Target", "💎 UV",
                             "MoS %", "TER %", "Score"],
        "Valuation":        ["Graham #", "PE Fair Val", "EPV",
                             "DDM (1-stage)", "DDM (2-stage)"],
        "Risk & Size":      ["Risk Score", "Mkt Cap", "Beta", "Debt/Equity"],
        "Multiples":        ["P/E", "P/B", "EV/EBITDA"],
        "Quality":          ["ROE %", "ROA %", "Op Margin %", "FCF Yield %"],
        "Growth":           ["Rev Growth %", "EPS Growth %"],
        "Dividends":        ["Div Yield", "5yr Avg Yield", "Payout Ratio",
                             "Cash Payout", "Div Coverage", "Div Flag"],
    }
    tabs = st.tabs(list(sections.keys()))
    for tab, (section, cols) in zip(tabs, sections.items()):
        with tab:
            for col in cols:
                desc = COLUMN_HELP.get(col, "")
                if desc:
                    st.markdown(
                        f'<div style="display:flex;gap:10px;margin-bottom:8px;">'
                        f'<span style="min-width:120px;font-weight:600;color:#a78bfa;">{col}</span>'
                        f'<span style="color:#ccc;font-size:0.9rem;">{desc}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )


_LOADING_CSS = """
<style>
  @keyframes uv-spin { to { transform: rotate(360deg); } }
  .uv-loading-wrap {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; height: 65vh; gap: 18px;
  }
  .uv-loading-logo  { font-size: 2.4rem; }
  .uv-loading-title { font-size: 1.1rem; font-weight: 700; letter-spacing: -0.3px; }
  .uv-loading-sub   { font-size: 0.78rem; opacity: 0.45; margin-top: -10px; }
  .uv-spinner {
    width: 28px; height: 28px; border: 3px solid rgba(128,128,128,0.2);
    border-top-color: #4f8ef7; border-radius: 50%;
    animation: uv-spin 0.8s linear infinite;
  }
  .uv-loading-msg { font-size: 0.82rem; opacity: 0.5; }
</style>"""

from contextlib import contextmanager

@contextmanager
def _loading_screen(message: str = "Loading…"):
    """Show a branded full-page loading screen, then hand off to real content."""
    _slot = st.empty()
    _slot.markdown(f"""{_LOADING_CSS}
<div class="uv-loading-wrap">
  <div class="uv-loading-logo">💎</div>
  <div class="uv-loading-title">UV · Undervalued</div>
  <div class="uv-loading-sub">Portfolio tracker &amp; screener</div>
  <div class="uv-spinner"></div>
  <div class="uv-loading-msg">{message}</div>
</div>""", unsafe_allow_html=True)
    try:
        yield
    finally:
        _slot.empty()


_CHART_CONFIG = {"staticPlot": True, "displayModeBar": False}

def _static_bar(series: "pd.Series", title: str = "", color: str | None = None) -> None:
    """Render a static (non-zoomable) horizontal bar chart via Plotly."""
    _bad = {"", "nan", "none", "undefined", "<na>"}
    _pairs = [
        (str(k), v) for k, v in zip(series.index, series.values)
        if pd.notna(k) and pd.notna(v)
        and str(k).strip().lower() not in _bad
    ]
    if not _pairs:
        return
    # Reverse so highest value is at top in natural Plotly order (avoids autorange="reversed" artifact)
    _labels, _vals = zip(*reversed(_pairs))
    fig = go.Figure(go.Bar(
        x=list(_vals),
        y=list(_labels),
        orientation="h",
        marker_color=color or [
            "#ef5350" if v < 0 else "#4f8ef7" for v in _vals
        ],
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=28 if title else 24, b=0),
        title=dict(text=title or ""),
        height=max(200, len(_labels) * 32 + 60),
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True, categoryorder="array", categoryarray=list(_labels)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
    )
    st.plotly_chart(fig, width="stretch", config=_CHART_CONFIG)


def _donut_chart(series: "pd.Series", title: str = "") -> None:
    """Render a static donut chart showing proportional breakdown of a value series."""
    _bad = {"", "nan", "none", "undefined", "<na>", "n/a"}
    _clean = series[series.index.map(lambda k: pd.notna(k) and str(k).strip().lower() not in _bad)]
    _clean = _clean[_clean > 0]
    if _clean.empty:
        st.info("No data available for this breakdown.")
        return
    _labels = [str(k) for k in _clean.index]
    _vals   = _clean.values.tolist()
    _total  = sum(_vals)
    _pcts   = [v / _total * 100 for v in _vals]
    # Show pct inside slice only when slice is wide enough to fit text
    _text   = [f"{p:.1f}%" if p >= 4 else "" for p in _pcts]
    fig = go.Figure(go.Pie(
        labels=_labels,
        values=_vals,
        hole=0.52,
        text=_text,
        textinfo="text",
        textposition="inside",
        insidetextorientation="horizontal",
        hovertemplate="%{label}: €%{value:,.0f} (%{percent})<extra></extra>",
        marker=dict(line=dict(color="rgba(0,0,0,0.15)", width=1)),
    ))
    _n = len(_labels)
    fig.update_layout(
        margin=dict(l=10, r=10, t=36 if title else 10, b=10),
        title=dict(text=title or ""),
        height=max(340, 24 * _n + 60),
        showlegend=True,
        legend=dict(
            orientation="v",
            x=1.02, xanchor="left",
            y=1.0,  yanchor="top",
            font=dict(size=11),
            itemwidth=30,
            tracegroupgap=2,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
    )
    st.plotly_chart(fig, width="stretch", config=_CHART_CONFIG)


def _bust_cache() -> None:
    """Cancel any background fetch, wipe the screener disk cache, and rerun."""
    cancel_background_fetch()
    clear_live_cache()
    with _file_lock:   # prevents a concurrent background save from landing after our wipe
        try:
            CACHE_FILE.write_text("{}", encoding="utf-8")
        except OSError:
            pass
    _load_all_screener_data.clear()
    st.rerun()


def _cache_age_str() -> str:
    cache = _load_cache()
    if not cache:
        return "No cache yet"
    timestamps = [
        datetime.fromisoformat(v["fetched_at"])
        for v in cache.values()
        if v.get("fetched_at")
    ]
    if not timestamps:
        return "No cache yet"
    oldest = min(timestamps)
    age_min = (datetime.now(timezone.utc) - oldest).total_seconds() / 60
    if age_min < 60:
        return f"Cache age: {age_min:.0f} min  (TTL {CACHE_TTL_HOURS}h)"
    return f"Cache age: {age_min/60:.1f} h  (TTL {CACHE_TTL_HOURS}h)"


def _fmt_mcap(v) -> str:
    if pd.isna(v) or v is None:
        return "—"
    return f"€{v/1e9:.1f}B" if v >= 1e9 else f"€{v/1e6:.0f}M"


def _safe_pct(numerator: float, denominator: float) -> float:
    """Return numerator/denominator*100, or 0 if denominator is zero."""
    return numerator / denominator * 100 if denominator else 0


_HINT_WATCHLIST = "check ★ to add to watchlist"


def _fmt_div_flag(v) -> str:
    return {"At Risk": "⚠️ At Risk", "OK": "✅ OK", "": "—"}.get(str(v) if pd.notna(v) else "", "—")


def _cache_version() -> str:
    """Changes whenever the fundamentals JSON file is updated on disk."""
    try:
        return str(int(CACHE_FILE.stat().st_mtime))
    except OSError:
        return "0"


@st.cache_data(show_spinner=False)
def _load_all_screener_data(cache_version: str, enabled: tuple) -> tuple:  # noqa: ARG001
    """
    Build screener DataFrames from whatever is in the cache right now.
    cache_version (file mtime) and enabled (active exchanges) both bust the
    Streamlit cache when they change so the UI stays in sync automatically.
    """
    _fetch_map = {
        "brussels":  (fetch_brussels_tickers,  ".BR"),
        "amsterdam": (fetch_amsterdam_tickers, ".AS"),
        "paris":     (fetch_paris_tickers,     ".PA"),
        "milan":     (fetch_milan_tickers,     ".MI"),
        "frankfurt": (fetch_frankfurt_tickers, ".DE"),
        "swiss":     (fetch_swiss_tickers,     ".SW"),
    }
    enabled_set = set(enabled)
    empty = pd.DataFrame(columns=["Ticker"])

    stock_lists: dict[str, list[dict]] = {}
    all_stocks: list[dict] = []
    for key, (fetch_fn, _) in _fetch_map.items():
        if key in enabled_set:
            stocks = fetch_fn()
            stock_lists[key] = stocks
            all_stocks.extend(stocks)

    print(f"Loading screener data for {len(all_stocks)} stocks…")
    all_fund = fetch_fundamentals_nowait(all_stocks)

    if all_fund.empty:
        return tuple(empty for _ in ALL_EXCHANGES)

    def _exchange_df(stock_list):
        tickers = {s["ticker"] for s in stock_list}
        return run_screener_from_df(all_fund[all_fund["Ticker"].isin(tickers)])

    return tuple(
        _exchange_df(stock_lists[key]) if key in stock_lists else empty
        for key in ALL_EXCHANGES
    )


def _compute_fair_values(info: dict) -> dict:
    eps  = info.get("trailingEps")
    bvps = info.get("bookValue")

    # Graham Number: √(22.5 × EPS × BVPS) — requires positive EPS and BVPS
    graham_number = None
    if eps and bvps and eps > 0 and bvps > 0:
        graham_number = round((22.5 * eps * bvps) ** 0.5, 2)

    # PE Fair Value: EPS × 15 (Graham's assumed fair P/E for a no-growth company)
    pe_fair_value = None
    if eps and eps > 0:
        pe_fair_value = round(eps * 15, 2)

    # Graham Growth: EPS × (8.5 + 2g) where g is expected annual earnings growth (%)
    # Uses earningsGrowth (TTM) as a proxy; clamped to [-5%, 25%] to avoid extremes.
    graham_growth = None
    raw_growth = info.get("earningsGrowth") or info.get("revenueGrowth")
    if eps and eps > 0 and raw_growth is not None:
        g = max(-5.0, min(25.0, raw_growth * 100))
        graham_growth = round(eps * (8.5 + 2 * g), 2)
        if graham_growth <= 0:
            graham_growth = None

    analyst_target = info.get("targetMeanPrice")

    # Composite: average of all available positive estimates
    estimates = [v for v in [graham_number, pe_fair_value, graham_growth, analyst_target]
                 if v is not None and v > 0]
    composite = round(sum(estimates) / len(estimates), 2) if estimates else None

    return {
        "graham_number": graham_number,
        "pe_fair_value": pe_fair_value,
        "graham_growth": graham_growth,
        "fair_value":    composite,
    }


@st.cache_data(show_spinner=False, ttl=60)
def _fetch_prices_cached(tickers: tuple) -> dict:
    """Batch price feed — one HTTP call for all tickers, refreshed every 60s."""
    return fetch_prices(tickers)


@st.cache_data(show_spinner=False, ttl=21_600)
def _fetch_fundamentals(tickers: tuple) -> dict:
    """
    Per-ticker fundamentals (EPS, BVPS, analyst targets, div rate) via yf.info.
    Cached for 6 h — these change quarterly, not by the minute.
    """
    result = {}
    _empty = {
        "analyst_target": None, "div_rate": 0,
        "graham_number": None, "pe_fair_value": None,
        "graham_growth": None, "fair_value": None,
        "sector": None, "country": None,
    }
    for t in tickers:
        if not t or not isinstance(t, str):
            result[t] = dict(_empty)
            continue
        try:
            info = yf.Ticker(t).info
            fv   = _compute_fair_values(info)
            result[t] = {
                "analyst_target": info.get("targetMeanPrice"),
                "div_rate":       info.get("trailingAnnualDividendRate") or 0,
                "sector":         info.get("sector") or None,
                "country":        info.get("country") or None,
                **fv,
            }
        except Exception:
            result[t] = dict(_empty)
    return result


def _fmt_eur(v) -> str:
    """Format a value as a Euro price, or '—' if missing."""
    return f"€{v:.2f}" if pd.notna(v) else "—"


def _fetch_live_data(tickers: tuple) -> dict:
    """Merge fast batch prices with slower-moving fundamentals."""
    prices = _fetch_prices_cached(tickers)
    fundas = _fetch_fundamentals(tickers)
    return {
        t: {**fundas.get(t, {}), **prices.get(t, {})}
        for t in tickers
    }


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="UV — Undervalued",
    page_icon="💎",
    layout="wide",
)

st.markdown("""
<style>
  /* Fade content in smoothly on each navigation */
  .block-container { animation: uvFadeIn 0.18s ease; }
  @keyframes uvFadeIn { from { opacity: 0; } to { opacity: 1; } }
  /* Hide Streamlit top decoration bar (coloured stripe) — keep toolbar */
  [data-testid="stDecoration"] { display: none !important; }
  /* Remove top header bar height so content sits at the top */
  header[data-testid="stHeader"] { background: transparent !important; border-bottom: none !important; }

  /* ── Layout ─────────────────────────────────────────────────────────────── */
  .block-container          { padding-top: 2rem !important; padding-bottom: 0.5rem !important; max-width: 100% !important; }
  section[data-testid="stMain"] { width: 100% !important; }
  section[data-testid="stSidebar"][aria-expanded="true"]  ~ section[data-testid="stMain"] .block-container { padding-left: 1.5rem !important; padding-right: 1.5rem !important; }
  section[data-testid="stSidebar"][aria-expanded="false"] ~ section[data-testid="stMain"] .block-container { padding-left: 64px !important; padding-right: 1.5rem !important; padding-top: 1rem !important; }

  /* ── Sidebar — fixed width, smooth appearance ───────────────────────────── */
  section[data-testid="stSidebar"],
  section[data-testid="stSidebar"] > div:first-child { min-width: 250px !important; max-width: 250px !important; width: 250px !important; z-index: 100 !important; }
  section[data-testid="stSidebar"] { transition: none !important; }

  /* ── Hide sidebar collapse button ───────────────────────────────────────── */
  [data-testid="collapsedControl"] { display: none !important; }

  /* ── Tables ──────────────────────────────────────────────────────────────── */
  [data-testid="stDataFrame"],
  [data-testid="stDataFrameResizable"]            { width: 100% !important; }
  [data-testid="stDataFrame"] .dvn-scroller .cell-wrapper--header svg,
  [data-testid="stDataFrameResizable"] .dvn-scroller .cell-wrapper--header svg,
  .glideDataEditor .headerCellName > svg,
  .glideDataEditor [aria-label="Column menu"]     { display: none !important; }

  /* ── Metric cards ────────────────────────────────────────────────────────── */
  div[data-testid="metric-container"]                               { padding: 0.4rem 0.75rem !important; border-radius: 10px !important; background: rgba(128,128,128,0.05) !important; text-align: center !important; }
  div[data-testid="metric-container"] label                         { display: block; text-align: center !important; font-size: 0.75rem !important; opacity: 0.6; }
  div[data-testid="metric-container"] [data-testid="stMetricValue"] { text-align: center !important; font-size: 1.3rem !important; font-weight: 700 !important; }
  div[data-testid="metric-container"] [data-testid="stMetricDelta"] { justify-content: center !important; }
  /* Compact portfolio tab layout */
  [data-testid="stTabsContent"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
  [data-testid="stTabsContent"] [data-testid="stColumns"]       { align-items: flex-start !important; }
  [data-testid="stTabsContent"] [data-testid="column"]          { padding-bottom: 0 !important; }
  [data-testid="stTabsContent"] [data-testid="metric-container"]{ margin-bottom: 0 !important; padding-bottom: 0.2rem !important; }
  [data-testid="stTabsContent"] [data-testid="stMetricDelta"]   { margin-bottom: 0 !important; padding-bottom: 0 !important; }

  /* ── Tabs ────────────────────────────────────────────────────────────────── */
  div[data-testid="stTabs"] > div:first-child                    { margin-bottom: 0.5rem; }
  div[data-testid="stTabsContent"]                               { padding-top: 0 !important; padding-bottom: 0 !important; }
  /* Tighten element gaps and divider inside tab panels */
  [data-testid="stTabsContent"] [data-testid="stVerticalBlock"]  { gap: 0.25rem !important; }
  [data-testid="stTabsContent"] hr                               { margin-top: -1.5rem !important; margin-bottom: 0.25rem !important; }
  button[data-testid="stTab"]                       { color: var(--text-color) !important; opacity: 0.5; font-weight: 500; }
  button[data-testid="stTab"]:hover                 { opacity: 0.85 !important; }
  button[data-testid="stTab"][aria-selected="true"] { opacity: 1 !important; color: var(--text-color) !important; }

  /* ── Misc spacing ────────────────────────────────────────────────────────── */
  div[data-testid="stMultiSelect"] { margin-bottom: 0.25rem !important; }
  .stCaption { margin-bottom: 0 !important; }

  /* ── Mini icon nav ───────────────────────────────────────────────────────── */
  .mini-nav {
    display: flex; position: fixed; left: 0; top: 0; height: 100vh; width: 48px;
    background: var(--sidebar-background-color, var(--secondary-background-color));
    border-right: 1px solid rgba(128,128,128,0.12);
    flex-direction: column; justify-content: space-between; align-items: center; z-index: 99;
  }
  .mini-nav-top, .mini-nav-bottom { display: flex; flex-direction: column; align-items: center; gap: 16px; }
  .mini-nav-top    { padding-top: 14px; }
  .mini-nav-bottom { padding-bottom: 18px; }
  .mini-nav-link {
    font-size: 1.2rem; text-decoration: none !important; opacity: 0.4;
    transition: opacity 0.15s, background 0.15s;
    display: flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; border-radius: 8px;
  }
  .mini-nav-link:hover { opacity: 1; background: rgba(128,128,128,0.1); }
  .mini-nav-active     { opacity: 1 !important; background: rgba(79,142,247,0.18) !important; }

  /* ── Sidebar nav ─────────────────────────────────────────────────────────── */
  .uv-logo      { display: flex; align-items: center; gap: 10px; padding: 0 4px 18px; margin-top: -1.8rem; }
  .uv-logo-gem  { font-size: 2rem; line-height: 1; }
  .uv-logo-name { font-size: 1.05rem; font-weight: 800; letter-spacing: -0.3px; color: var(--text-color); }
  .uv-logo-sub  { font-size: 0.68rem; color: var(--text-color); opacity: 0.35; margin-top: 2px; }
  .uv-nav       { display: flex; flex-direction: column; gap: 1px; }
  .uv-nav-item  {
    display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px;
    font-size: 0.92rem; font-weight: 500; color: var(--text-color); opacity: 0.45;
    text-decoration: none !important; transition: background 0.12s, opacity 0.12s; white-space: nowrap;
  }
  .uv-nav-item:hover { background: rgba(128,128,128,0.08); opacity: 1; }
  .uv-nav-active     { background: rgba(79,142,247,0.14) !important; opacity: 1 !important; }
  .uv-nav-sep        { border: none; border-top: 1px solid rgba(128,128,128,0.2); margin: 5px 2px; }
  .uv-nav-icon       { font-size: 1rem; width: 1.25em; text-align: center; flex-shrink: 0; }
  .uv-nav-utils { position: fixed; bottom: 100px; left: 0; width: 250px; padding: 0 16px 4px; box-sizing: border-box; }
  .uv-bottom    {
    position: fixed; bottom: 0; left: 0; width: 250px; padding: 10px 16px 15px;
    background: var(--sidebar-background-color, var(--secondary-background-color));
    border-top: 1px solid rgba(128,128,128,0.12); box-sizing: border-box;
  }
  .uv-bottom-email { font-size: 0.7rem; color: var(--text-color); opacity: 0.45; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }
  .uv-role-badge   { display: inline-block; background: rgba(128,128,128,0.12); border-radius: 4px; padding: 1px 6px; font-size: 0.65rem; color: var(--text-color); opacity: 0.5; margin-right: 5px; vertical-align: middle; }
  .uv-logout {
    display: inline-flex; align-items: center;
    padding: 0 12px; height: 32px; line-height: 32px;
    font-size: 0.8rem; font-weight: 400;
    color: var(--text-color) !important; text-decoration: none !important;
    border: 1px solid rgba(128,128,128,0.4); border-radius: 6px;
    background: transparent; transition: border-color 0.12s, opacity 0.12s;
    white-space: nowrap; flex-shrink: 0;
  }
  .uv-logout:hover { border-color: rgba(128,128,128,0.8); opacity: 1; }
  /* Edit positions dialog — constrained width */
  [data-testid="stDialog"] [role="dialog"],
  [data-testid="stModal"] > div,
  div[aria-modal="true"],
  div[aria-label="Edit positions"] {
    max-width: 550px !important;
    width: 550px !important;
    min-width: 0 !important;
  }
  /* Action buttons (Add / Edit / View) — tight row */
  [data-testid="stMarkdown"]:has(.uv-crud-sentinel) ~ [data-testid="stHorizontalBlock"] {
    gap: 6px !important;
  }
  [data-testid="stMarkdown"]:has(.uv-crud-sentinel) ~ [data-testid="stHorizontalBlock"] button {
    padding: 0px 12px !important;
    height: 32px !important;
    min-height: 0 !important;
    font-size: 0.8rem !important;
    font-weight: 400 !important;
    line-height: 32px !important;
    white-space: nowrap !important;
    width: 100% !important;
  }
  /* JS-bridge iframes are purely functional — collapse them visually */
  [data-testid="stIFrame"] { height: 0 !important; min-height: 0 !important; max-height: 0 !important;
    margin: 0 !important; padding: 0 !important; overflow: hidden !important; line-height: 0 !important; }
  [data-testid="stIFrame"] > div,
  [data-testid="stIFrame"] iframe { height: 0 !important; min-height: 0 !important; max-height: 0 !important;
    overflow: hidden !important; visibility: hidden !important; }
</style>
""", unsafe_allow_html=True)

# ── Authentication gate ───────────────────────────────────────────────────────

# Restore JWT from _tok query param (legacy / external deep-links)
_tok_param = st.query_params.get("_tok", "")
if _tok_param:
    if not st.session_state.get("jwt_token"):
        _email_check, _role_check = verify_token(_tok_param)
        if _email_check:
            st.session_state["jwt_token"]  = _tok_param
            st.session_state["user_email"] = _email_check
            st.session_state["user_role"]  = _role_check
        else:
            # Token invalid or expired — purge from localStorage to break any redirect loop
            st.iframe("<script>localStorage.removeItem('uv_jwt');</script>", height=1)
    del st.query_params["_tok"]

# If no active Streamlit session, recover the JWT from localStorage and
# redirect with _tok so the session is restored on next load.
_has_session = bool(st.session_state.get("jwt_token"))
if not _has_session:
    st.iframe("""
<script>
(function(){
  var tok = localStorage.getItem('uv_jwt');
  if (!tok) return;
  var url = new URL(window.parent.location.href);
  if (url.searchParams.get('_tok')) return;
  url.searchParams.set('_tok', tok);
  window.parent.location.replace(url.toString());
})();
</script>
""", height=1)

def _auth_wall():
    """Show login/sign-up form and halt execution if not authenticated."""
    # Fast path: token + email already verified this session — skip re-verification
    # on every rerun (e.g. st_autorefresh) to prevent ghost login flashes.
    if st.session_state.get("jwt_token") and st.session_state.get("user_email"):
        return

    token = st.session_state.get("jwt_token")
    if token:
        email, role = verify_token(token)
        if email:
            st.session_state["user_email"] = email
            st.session_state["user_role"]  = role
            return  # already logged in

    st.markdown("""
    <style>
      .login-wrap { display:flex; flex-direction:column; align-items:center; margin: 56px auto 28px; }
      .login-logo  { font-size:2.4rem; margin-bottom:10px; }
      .login-title { font-size:1.1rem; font-weight:700; letter-spacing:-0.3px; margin-bottom:4px; }
      .login-sub   { font-size:0.78rem; opacity:0.45; }
    </style>
    <div class="login-wrap">
      <div class="login-logo">💎</div>
      <div class="login-title">UV · Undervalued</div>
      <div class="login-sub">Portfolio tracker &amp; screener</div>
    </div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 0.78, 1])
    with col:
        email    = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Log in", width="stretch", type="primary"):
            ok, result = login(email, password)
            if ok:
                _, role = verify_token(result)
                st.session_state["jwt_token"]  = result
                st.session_state["user_email"] = email.strip().lower()
                st.session_state["user_role"]  = role
                st.iframe(f"<script>localStorage.setItem('uv_jwt',{repr(result)});</script>", height=1)
                st.rerun()
            else:
                st.error(result)

    st.stop()


# ── Logout handler — runs before auth wall so it works even without a session ──
if st.query_params.get("logout") == "1":
    st.query_params.clear()
    for _k in ("jwt_token", "user_email", "user_role"):
        st.session_state.pop(_k, None)
    st.rerun()

_auth_wall()

_email        = st.session_state.get("user_email", "")
_current_role = st.session_state.get("user_role", "user")
_is_admin     = _current_role == "admin"
set_user(_email)

# Page routing via query params (default: screener)
_page = st.query_params.get("page", "screener")


# ── Sidebar (pure HTML — no Streamlit widgets) ────────────────────────────────
# Active classes are applied by JS (uvSetActive) so sidebar HTML is identical on
# every rerun — React makes no DOM changes → zero sidebar flash.

_jwt    = st.session_state.get("jwt_token", "")
_tok_qs = f"&_tok={_jwt}" if _jwt else ""


def _nav_link(page: str, icon: str, label: str, tok_qs: str,
              extra_class: str = "uv-nav-item") -> str:
    """Return an HTML nav anchor for page navigation."""
    href = f"?page={page}{tok_qs}"
    return (
        f'<a href="{href}" target="_self" data-uv-page="{page}" '
        f'class="{extra_class}">'
        f'<span class="uv-nav-icon">{icon}</span>{label}</a>'
    )


_portfolio_item = _nav_link("portfolio", "📁", "Portfolio", _tok_qs)
_settings_item  = _nav_link("settings",  "⚙️", "Settings",  _tok_qs)

_role_label = {"admin": "🔑"}.get(_current_role, "")
_role_badge_html = (
    f'<span class="uv-role-badge">{_role_label}</span>'
    if _role_label else ""
)

with st.sidebar:
    st.markdown(f"""
<div class="uv-logo">
  <div class="uv-logo-gem">💎</div>
  <div>
    <div class="uv-logo-name">UV <span style="font-weight:300;opacity:0.35;">· Undervalued</span></div>
    <div class="uv-logo-sub">Portfolio tracker &amp; screener</div>
  </div>
</div>
<nav class="uv-nav">
  {_nav_link("dashboard", "💎", "Dashboard", _tok_qs)}
  {_portfolio_item}
  {_nav_link("screener",  "🔍", "Screener",  _tok_qs)}
  {_nav_link("risk",      "⚠️", "Risk",      _tok_qs)}
</nav>
<div class="uv-nav-utils">
  <hr class="uv-nav-sep" style="margin-bottom:6px;">
  <nav class="uv-nav">{_settings_item}{_nav_link("help", "❓", "Help", _tok_qs)}</nav>
</div>
<div class="uv-bottom">
  <div class="uv-bottom-email" style="margin-bottom:8px;">{_role_badge_html}{_email}</div>
  <div style="text-align:center;">
    <a href="/?logout=1" target="_self" class="uv-logout" onclick="try{{window.parent.localStorage.removeItem('uv_jwt')}}catch(e){{}}">🚪 Log out</a>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Mini icon nav (shown when sidebar is collapsed) ───────────────────────────
# Active state is applied by uvSetActive() in JS — no Python active classes needed.
_mini_admin     = _nav_link("settings",  "⚙️", "", _tok_qs, "mini-nav-link")
_mini_portfolio = _nav_link("portfolio", "📁", "", _tok_qs, "mini-nav-link")
st.markdown(f"""
<div class="mini-nav">
  <div class="mini-nav-top">
    {_nav_link("dashboard", "💎", "", _tok_qs, "mini-nav-link")}
    {_mini_portfolio}
    {_nav_link("screener",  "🔍", "", _tok_qs, "mini-nav-link")}
    {_nav_link("risk",      "⚠️", "", _tok_qs, "mini-nav-link")}
  </div>
  <div class="mini-nav-bottom">{_mini_admin}{_nav_link("help", "❓", "", _tok_qs, "mini-nav-link")}</div>
</div>
""", unsafe_allow_html=True)

# Active nav highlight via Python-injected CSS (no JS bridge needed).
st.markdown(f"""<style>
[data-uv-page="{_page}"].uv-nav-item  {{ background:rgba(79,142,247,0.14)!important; opacity:1!important; }}
[data-uv-page="{_page}"].mini-nav-link {{ background:rgba(79,142,247,0.18)!important; opacity:1!important; }}
</style>""", unsafe_allow_html=True)

# Keep localStorage token fresh + hide sidebar collapse button.
st.iframe(f"""
<script>
(function(){{
  var tok = {repr(st.session_state.get('jwt_token', ''))};
  if (tok) localStorage.setItem('uv_jwt', tok);
  (function hideBtn() {{
    var el = window.parent.document.querySelector('[data-testid="collapsedControl"]');
    if (el) (el.closest('div') || el).style.setProperty('display','none','important');
  }})();
  new MutationObserver(function(){{
    var el = window.parent.document.querySelector('[data-testid="collapsedControl"]');
    if (el) (el.closest('div') || el).style.setProperty('display','none','important');
  }}).observe(window.parent.document.body, {{childList:true, subtree:true}});
}})();
</script>
""", height=1)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if _page == "dashboard":
    st.title("Dashboard")

    # ── Load portfolio data ────────────────────────────────────────────────────
    if not portfolio_exists():
        st.info("No portfolio found. Upload your Excel file in Settings to get started.")
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
    _db_scr = _all_scr_df[_all_scr_df["Ticker"].isin(_db_tickers)].copy() if "_all_scr_df" in dir() else pd.DataFrame()
    _db_mos_vals = pd.to_numeric(_db_scr.get("MoS %", pd.Series(dtype=float)), errors="coerce").dropna()
    _db_avg_mos  = _db_mos_vals.mean() if not _db_mos_vals.empty else None

    # ── Row 1: KPI cards ──────────────────────────────────────────────────────
    _k1, _k2, _k3, _k4 = st.columns(4)
    _k1.metric("Current value",  f"€{_db_current:,.0f}",
               delta=f"€{_db_gain:+,.0f} ({_db_gain_pct:+.1f}%)")
    _k2.metric("Total return",   f"€{_db_total_ret:,.0f}",
               delta=f"{_db_ret_pct:+.1f}%")
    _k3.metric("Dividends",      f"€{_db_divs:,.0f}")
    _k4.metric("Avg UV upside",
               f"{_db_avg_mos:+.1f}%" if _db_avg_mos is not None else "—",
               help="Average margin of safety across your positions based on UV fair value")
    st.divider()

    # ── Row 2: Heatmap + Allocation ───────────────────────────────────────────
    _hm_col, _al_col = st.columns(2)

    with _hm_col:
        st.subheader("Today's performance")
        _db_hm = _db_pf.dropna(subset=["name", "current_value", "day_change_pct"]).copy()
        if not _db_hm.empty:
            import plotly.graph_objects as go
            _clamp  = 5.0
            _normed = _db_hm["day_change_pct"].clip(-_clamp, _clamp) / _clamp
            _colors = [
                f"rgba({int(220*(1-v))},{int(220*((v+1)/2))},{int(60*(1-abs(v)))},0.85)"
                for v in _normed
            ]
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
                marker=dict(colors=_colors, line=dict(width=2, color="rgba(0,0,0,0.3)")),
            ))
            _hm_fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                                  paper_bgcolor="rgba(0,0,0,0)", height=280)
            st.plotly_chart(_hm_fig, width="stretch", config=_CHART_CONFIG)
        else:
            st.caption("No daily price data available.")

    with _al_col:
        st.subheader("Allocation")
        _db_al = (
            _db_pf.dropna(subset=["current_value"])
              .assign(sector=_db_pf["sector"].fillna("Unknown"))
              .groupby("sector")["current_value"].sum()
              .sort_values(ascending=False)
        )
        _donut_chart(_db_al)

    st.divider()

    # ── Row 3: Portfolio value over time (full width) ─────────────────────────
    st.subheader("Portfolio value over time")
    _db_vh = load_value_history()
    if _db_vh is not None and not _db_vh.empty and len(_db_vh) >= 2:
        import plotly.graph_objects as go
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
            line=dict(color="#4f8ef7", width=2),
            fill="tozeroy", fillcolor="rgba(79,142,247,0.08)",
        ))
        _db_vfig.add_trace(go.Scatter(
            x=_db_vh["date"], y=_db_vh["invested"],
            mode="lines", name="Amount invested",
            line=dict(color="#aaaaaa", width=1.5, dash="dot"),
        ))
        if _db_has_spx and _db_show_spx:
            _db_vfig.add_trace(go.Scatter(
                x=_db_vh["date"], y=pd.to_numeric(_db_vh["benchmark_spx"], errors="coerce"),
                mode="lines", name="S&P 500 (same invested)",
                line=dict(color="#f4a026", width=1.5, dash="dash"),
            ))
        if _db_has_stoxx and _db_show_stoxx:
            _db_vfig.add_trace(go.Scatter(
                x=_db_vh["date"], y=pd.to_numeric(_db_vh["benchmark_stoxx"], errors="coerce"),
                mode="lines", name="Euro Stoxx 50 (same invested)",
                line=dict(color="#a855f7", width=1.5, dash="dash"),
            ))
        _db_vfig.update_layout(
            margin=dict(l=0, r=0, t=8, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            yaxis=dict(tickprefix="€", tickformat=",.0f"),
            xaxis=dict(showgrid=False),
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(_db_vfig, width="stretch", config=_CHART_CONFIG)
    else:
        st.caption("No history yet — go to Portfolio → Positions and click **↺ Rebuild history**.")

    st.divider()

    # ── Row 4: Top movers + Upcoming dividends ────────────────────────────────
    _mv_col, _div_col = st.columns(2)

    with _mv_col:
        st.subheader("Top movers today")
        _db_mv = _db_pf.dropna(subset=["name", "day_change_pct"]).copy()
        _db_mv["day_change_pct"] = pd.to_numeric(_db_mv["day_change_pct"], errors="coerce")
        _db_mv = _db_mv.dropna(subset=["day_change_pct"]).sort_values("day_change_pct", ascending=False)
        _db_top = pd.concat([_db_mv.head(3), _db_mv.tail(3)]).drop_duplicates()
        if not _db_top.empty:
            _db_top_disp = pd.DataFrame({
                "Company":  _db_top["name"].values,
                "Day %":    _db_top["day_change_pct"].map(lambda v: f"{v:+.2f}%"),
                "Value":    _db_top["current_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            })
            st.dataframe(_db_top_disp, hide_index=True, width="stretch",
                         height=len(_db_top_disp) * 35 + 38,
                         column_config={
                             "Day %": st.column_config.TextColumn("Day %"),
                         })
        else:
            st.caption("No daily price data available.")

    with _div_col:
        st.subheader("Upcoming dividends")
        if not _db_scr.empty and "exDividendDate" in _db_scr.columns:
            _db_div_scr = _db_scr[_db_scr["Ticker"].isin(_db_tickers)].copy()
            _db_div_scr["exDividendDate"] = pd.to_datetime(
                _db_div_scr["exDividendDate"], errors="coerce")
            _today = pd.Timestamp.today().normalize()
            _db_upcoming = (
                _db_div_scr[_db_div_scr["exDividendDate"] >= _today]
                  .sort_values("exDividendDate")
                  .head(6)
            )
            if not _db_upcoming.empty:
                _db_div_disp = pd.DataFrame({
                    "Company":  _db_upcoming["Name"].values,
                    "Ex-date":  _db_upcoming["exDividendDate"].dt.strftime("%d %b %Y"),
                    "Yield":    pd.to_numeric(_db_upcoming.get("dividendYield", pd.Series()), errors="coerce")
                                  .map(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
                })
                st.dataframe(_db_div_disp, hide_index=True, width="stretch",
                             height=len(_db_div_disp) * 35 + 38)
            else:
                st.caption("No upcoming ex-dividend dates found.")
        else:
            st.caption("Screener data not loaded.")

    st.divider()

    # ── Row 5: Risk snapshot ──────────────────────────────────────────────────
    st.subheader("Risk snapshot")
    _db_risk_cache = _load_cache()
    if _db_pf is not None and not _db_pf.empty and _db_risk_cache:
        try:
            _db_report = _risk_module.assess_portfolio(_db_pf, _db_risk_cache, False)
            _r1, _r2, _r3, _r4 = st.columns(4)
            _r1.metric("Portfolio beta",   f"{_db_report.quant.portfolio_beta:.2f}",
                       help="Sensitivity to broad market moves. >1 = more volatile than market.")
            _r2.metric("Annual volatility",
                       f"{_db_report.quant.volatility_annual*100:.1f}%" if _db_report.quant.volatility_annual else "—",
                       help="Annualised standard deviation of portfolio returns.")
            _r3.metric("Risk score",       f"{_db_report.composite.total:.0f} / 100",
                       help="Composite risk score — lower is safer. See Risk page for full breakdown.")
            _r4.metric("Max drawdown",
                       f"{_db_report.quant.max_drawdown*100:.1f}%" if _db_report.quant.max_drawdown else "—",
                       help="Largest peak-to-trough decline in the past 5 years.")
            st.caption("→ [Full risk analysis](?page=risk&" + _tok_qs + ")")
        except Exception:
            st.caption("Risk data not available — visit the Risk page to compute it.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — VALUE SCREENER
# ══════════════════════════════════════════════════════════════════════════════

if _page == "screener":
    _settings = load_shared_settings()
    _enabled  = tuple(_settings.get("enabled_exchanges", ALL_EXCHANGES))
    with _loading_screen("Loading screener data…"):
        df, df_ams, df_par, df_mil, df_etr, df_swx = _load_all_screener_data(_cache_version(), _enabled)
    if not df.empty and ("fair_value" not in df.columns or "Decision" not in df.columns):
        _bust_cache()

    @st.fragment(run_every=10)
    def _fetch_progress_banner():
        prog = get_fetch_progress()
        if prog["running"] and prog["total"] > 0:
            pct  = prog["done"] / prog["total"]
            st.progress(pct, text=f"Fetching fresh data in background… {prog['done']}/{prog['total']} tickers")

    _fetch_progress_banner()

    watchlist = load_watchlist()

    def _fmt_mos(v):
        if pd.isna(v):
            return "—"
        return f"{v:+.1f}%"

    # ── Column groups ─────────────────────────────────────────────────────────
    # Core columns always shown; extra groups toggled via multiselect
    CORE_COLS = {
        "★":           (None,         None),
        "Company":     ("Name",       lambda v: v),
        "Ticker":      ("Ticker",     lambda v: v),
        "Price":             ("Price",           _fmt_eur),
        "Analyst Target":   ("targetMeanPrice", _fmt_eur),
        "💎 UV":            ("fair_value",      _fmt_eur),
        "MoS %":  ("MoS %", _fmt_mos),
        "TER %":  ("TER %", lambda v: f"{v:+.1f}%" if pd.notna(v) else "—"),
        "Score":  (None,    None),   # built row-by-row below from Decision + Value Score
    }

    EXTRA_GROUPS = {
        "Valuation models": {
            "Graham #":      ("graham_number",  _fmt_eur),
            "PE Fair Val":   ("pe_fair_value",  _fmt_eur),
            "EPV":           ("epv",            _fmt_eur),
            "DDM (1-stage)": ("ddm",            _fmt_eur),
            "DDM (2-stage)": ("ddm_multistage", _fmt_eur),
        },
        "Risk & size": {
            "Risk Score":    ("Risk Score",      lambda v: v),
            "Mkt Cap":       ("Market Cap",      _fmt_mcap),
            "Beta":          ("beta",            lambda v: f"{v:.2f}"      if pd.notna(v) else "—"),
            "Debt/Equity":   ("debtToEquity",    lambda v: f"{v:.1f}"      if pd.notna(v) else "—"),
        },
        "Multiples": {
            "P/E":           ("trailingPE",          lambda v: f"{v:.1f}"      if pd.notna(v) else "—"),
            "P/B":           ("priceToBook",          lambda v: f"{v:.2f}"      if pd.notna(v) else "—"),
            "EV/EBITDA":     ("enterpriseToEbitda",   lambda v: f"{v:.1f}"      if pd.notna(v) else "—"),
        },
        "Quality": {
            "ROE %":         ("returnOnEquity",   lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            "ROA %":         ("returnOnAssets",   lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            "Op Margin %":   ("operatingMargins", lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            "FCF Yield %":   ("fcfYield",         lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
        },
        "Growth": {
            "Rev Growth %":  ("revenueGrowth",    lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            "EPS Growth %":  ("earningsGrowth",   lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
        },
        "Dividends": {
            "Div Yield":     ("dividendYield",          lambda v: f"{v*100:.2f}%"  if pd.notna(v) else "—"),
            "5yr Avg Yield": ("fiveYearAvgDividendYield",lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
            "Payout Ratio":  ("payoutRatio",            lambda v: f"{v*100:.1f}%"  if pd.notna(v) else "—"),
            "Cash Payout":   ("cashPayoutRatio",        lambda v: f"{v*100:.1f}%"  if pd.notna(v) else "—"),
            "Div Coverage":  ("dividendCoverage",       lambda v: f"{v:.2f}×"      if pd.notna(v) else "—"),
            "Div Flag":      ("Div Flag",               _fmt_div_flag),
            "Ex-Div Date":   ("exDividendDate",         lambda v: v if pd.notna(v) else "—"),
            "Div Date":      ("dividendDate",           lambda v: v if pd.notna(v) else "—"),
        },
        "Geography & Sector": {
            "Sector":  ("sector",  lambda v: v if pd.notna(v) else "—"),
            "Country": ("country", lambda v: v if pd.notna(v) else "—"),
        },
    }

    # Column config for every possible column — help= adds hover tooltip on header
    _ch = COLUMN_HELP.get  # shorthand
    _col_config_map = {
        "★":             st.column_config.CheckboxColumn("★",             width=55,  pinned=True, help=_ch("★")),
        "Company":       st.column_config.TextColumn(    "Company",       width=180, pinned=True, help=_ch("Company")),
        "Ticker":        st.column_config.TextColumn(    "Ticker",        width=90,  help=_ch("Ticker")),
        "Price":         st.column_config.TextColumn(    "Price",         width=80,  help=_ch("Price")),
        "💎 UV":         st.column_config.TextColumn(    "💎 UV",         width=90,  help=_ch("💎 UV")),
        "Analyst Target":st.column_config.TextColumn(    "Analyst Target",width=110, help=_ch("Analyst Target")),
        "MoS %":         st.column_config.TextColumn(    "MoS %",         width=75,  help=_ch("MoS %")),
        "TER %":         st.column_config.TextColumn(    "TER %",         width=75,  help=_ch("TER %")),
        "Score":         st.column_config.TextColumn(     "Score",         width=110,
                             help="🟢 Strong Buy (>70)  ·  🟡 Monitor (40–70)  ·  🔴 Avoid (<40)"),
        "Risk Score":    st.column_config.ProgressColumn("Risk Score",    width=110,
                             min_value=0, max_value=10,  format="%.1f",   help=_ch("Risk Score")),
        "Mkt Cap":       st.column_config.TextColumn(    "Mkt Cap",       width=80,  help=_ch("Mkt Cap")),
        "Beta":          st.column_config.TextColumn(    "Beta",          width=55,  help=_ch("Beta")),
        "Debt/Equity":   st.column_config.TextColumn(    "Debt/Equity",   width=95,  help=_ch("Debt/Equity")),
        "P/E":           st.column_config.TextColumn(    "P/E",           width=60,  help=_ch("P/E")),
        "P/B":           st.column_config.TextColumn(    "P/B",           width=60,  help=_ch("P/B")),
        "EV/EBITDA":     st.column_config.TextColumn(    "EV/EBITDA",     width=90,  help=_ch("EV/EBITDA")),
        "Sector":        st.column_config.TextColumn("Sector",     width=140),
        "Country":       st.column_config.TextColumn("Country",    width=120),
        "Ex-Div Date":   st.column_config.TextColumn("Ex-Div Date", width=105),
        "Div Date":      st.column_config.TextColumn("Div Date",    width=95),
        **{c: st.column_config.TextColumn(c, width=100, help=_ch(c))
           for g in EXTRA_GROUPS.values() for c in g
           if c not in ("Risk Score", "Sector", "Country")},
    }

    def _render_table(tab_df, key_suffix, score_key=None, score_default=None):
        """Render the screener table with optional column groups, score filter, and sector filter."""
        _grp_key    = f"col_groups_{key_suffix}"
        _sector_key = f"sector_filter_{key_suffix}"

        @st.dialog("View", width="small")
        def _dlg_view():
            _sel = st.session_state.get(_grp_key, [])
            for _grp in EXTRA_GROUPS.keys():
                _checked = st.checkbox(_grp, value=(_grp in _sel), key=f"scr_colgrp_{key_suffix}_{_grp}")
                if _checked and _grp not in _sel:
                    _sel = _sel + [_grp]
                elif not _checked and _grp in _sel:
                    _sel = [g for g in _sel if g != _grp]
            st.session_state[_grp_key] = _sel
            if st.button("Apply", type="primary", width="stretch", key=f"scr_col_apply_{key_suffix}"):
                st.rerun()

        # ── Collect available sector values ───────────────────────────────────
        _sector_vals = (
            sorted(v for v in tab_df["sector"].dropna().unique() if str(v).strip())
            if "sector" in tab_df.columns else []
        )

        # ── Apply score filter ────────────────────────────────────────────────
        if score_key:
            _sf_sel = st.session_state.get(score_key, score_default or _SCORE_OPTIONS[0])
            tab_df = _apply_score_filter(tab_df, _sf_sel)
        else:
            tab_df = tab_df.reset_index(drop=True)

        # ── Apply sector filter ───────────────────────────────────────────────
        _sec_sel = st.session_state.get(_sector_key, "All sectors")
        if _sec_sel and _sec_sel != "All sectors":
            _sec_col = tab_df["sector"] if "sector" in tab_df.columns else pd.Series("", index=tab_df.index)
            tab_df = tab_df[_sec_col == _sec_sel].reset_index(drop=True)

        n_shown = len(tab_df)
        tab_df.index = range(1, n_shown + 1)

        # ── Toolbar ───────────────────────────────────────────────────────────
        st.markdown('<div class="uv-crud-sentinel"></div>', unsafe_allow_html=True)
        _vc, _bc, _, _sc, _fc = st.columns([1, 1, 3, 2, 2], gap="small")

        with _vc:
            _active = st.session_state.get(_grp_key, [])
            _view_label = f"⊞ View ({len(_active)})" if _active else "⊞ View"
            if st.button(_view_label, key=f"btn_view_{key_suffix}"):
                _dlg_view()

        with _bc:
            if st.button("🛒 Buy", key=f"btn_buy_{key_suffix}"):
                _dlg_buy_screener()

        with _sc:
            _sec_cur = st.session_state.get(_sector_key, "All sectors")
            if _sec_cur not in _sector_vals and _sec_cur != "All sectors":
                _sec_cur = "All sectors"
            with st.popover(_sec_cur, width="stretch"):
                _sec_opts = ["All sectors"] + _sector_vals
                st.radio("Sector filter", _sec_opts,
                         index=_sec_opts.index(_sec_cur),
                         key=_sector_key, label_visibility="collapsed")

        with _fc:
            if score_key:
                _sf_cur = st.session_state.get(score_key, score_default or _SCORE_OPTIONS[0])
                with st.popover(_sf_cur, width="stretch"):
                    st.radio("Score filter", _SCORE_OPTIONS, index=_SCORE_OPTIONS.index(_sf_cur),
                             key=score_key, label_visibility="collapsed")

        selected_groups = st.session_state.get(_grp_key, [])

        # Score column: emoji colour prefix + value
        _score_emoji = {"Strong Buy": "🟢", "Monitor": "🟡", "Avoid": "🔴"}
        def _fmt_score(row):
            s = row.get("Value Score")
            if pd.isna(s):
                return "—"
            e = _score_emoji.get(row.get("Decision", ""), "")
            return f"{e} {s:.1f}" if e else f"{s:.1f}"

        # Build the display DataFrame from core cols + selected extras
        display_data = {"★": tab_df["Ticker"].isin(watchlist)}
        for col, (field, fmt) in list(CORE_COLS.items())[1:]:  # skip ★, already added
            if col == "Score":
                display_data[col] = tab_df.apply(_fmt_score, axis=1).values
            elif field in tab_df.columns:
                display_data[col] = tab_df[field].map(fmt).values
            else:
                display_data[col] = "—"

        active_extra_cols = []
        for group in selected_groups:
            for col, (field, fmt) in EXTRA_GROUPS[group].items():
                display_data[col] = (
                    tab_df[field].map(fmt).values if field in tab_df.columns else "—"
                )
                active_extra_cols.append(col)

        display_df = pd.DataFrame(display_data)
        _n_rows = len(display_df)

        # Highlight extra columns with a subtle tint (same as positions table)
        if active_extra_cols:
            display_df = display_df.style.set_properties(
                subset=active_extra_cols,
                **{"background-color": "rgba(99, 102, 241, 0.07)"},
            )

        all_data_cols = [c for c in display_data.keys() if c != "★"]
        col_config    = {c: _col_config_map[c] for c in display_data.keys() if c in _col_config_map}
        disabled_cols = all_data_cols

        _row_h  = 35
        _header = 38
        _height = min(_header + _n_rows * _row_h + 4, 800)

        edited = st.data_editor(
            display_df,
            width="stretch",
            hide_index=True,
            column_config=col_config,
            disabled=disabled_cols,
            height=_height,
            key=f"table_{key_suffix}",
        )
        return edited, n_shown

    _any_data = any(not d.empty for d in [df, df_ams, df_par, df_mil, df_etr, df_swx])
    if not _any_data:
        prog = get_fetch_progress()
        if prog["running"]:
            st.info(f"Fetching data… {prog['done']}/{prog['total']} tickers complete. The screener will appear automatically.")
        else:
            st.info("No screener data yet. Data will appear once the background fetch completes.")
        st.stop()

    # ── Buy dialog (shared across all screener tabs) ──────────────────────────
    _scr_all_df = pd.concat([df, df_ams, df_par, df_mil, df_etr, df_swx], ignore_index=True)
    _scr_sorted = _scr_all_df[["Ticker", "Name"]].drop_duplicates("Ticker").sort_values("Name", key=lambda s: s.str.lower())
    _scr_t_opts   = _scr_sorted["Ticker"].tolist()
    _scr_t_labels = {row["Ticker"]: f"{row['Name']}  ({row['Ticker']})" for _, row in _scr_sorted.iterrows()}
    _scr_price_map = _scr_all_df.drop_duplicates("Ticker").set_index("Ticker")["Price"].to_dict()

    @st.dialog("Buy stock", width="large")
    def _dlg_buy_screener():
        _c1, _c2, _c3, _c4 = st.columns([3, 1, 2, 2])
        with _c1:
            ticker = st.selectbox("Company", options=_scr_t_opts, format_func=lambda t: _scr_t_labels.get(t, t))
        with _c2:
            shares = st.number_input("Shares", min_value=1, step=1, value=1)
        with _c3:
            pur_date = st.date_input("Buy Date", format="DD/MM/YYYY")
        with _c4:
            _price    = float(_scr_price_map.get(ticker) or 0.0)
            total_price = st.number_input("Invested (€)", min_value=0.0, step=0.01,
                                          value=round(_price * shares, 2), format="%.2f")
        _, _save_btn = st.columns([3, 1])
        with _save_btn:
            _do_save = st.button("💾 Save", key="dlg_buy_scr_save", width="stretch")
        if _do_save and shares > 0 and total_price > 0:
            name = _scr_t_labels.get(ticker, ticker).split("  (")[0]
            add_position({
                "name":           name,
                "google_ticker":  "",
                "ticker":         ticker,
                "shares":         shares,
                "purchase_price": round(total_price / shares, 4),
                "purchase_value": round(total_price, 2),
                "target_price":   None,
                "dividends":      0.0,
                "date_in":        pd.Timestamp(pur_date).isoformat(),
                "account":        "",
            })
            st.rerun()

    # ── Index constituents — derived from the same hardcoded lists used by the screener ──
    def _index_set(fn) -> frozenset[str]:
        return frozenset(s["ticker"] for s in fn())

    _INDEX_TICKERS: dict[str, tuple[str, frozenset[str]]] = {
        "br":  ("BEL 20",  _index_set(_hardcoded_bel20)),
        "ams": ("AEX",     _index_set(_hardcoded_aex25)),
        "par": ("CAC 40",  _index_set(_hardcoded_cac40)),
        "mil": ("MIB ESG", _index_set(_hardcoded_ftse_mib)),
        "etr": ("DAX",     _index_set(_hardcoded_dax40)),
        "swx": ("SMI",     _index_set(_hardcoded_smi20)),
    }

    # Exchange tab order mirrors ALL_EXCHANGES; map key → (label, render_key, dataframe)
    _EXCHANGE_TAB_META = [
        ("brussels",  "Euronext Brussels",  "br",  df),
        ("amsterdam", "Euronext Amsterdam", "ams", df_ams),
        ("paris",     "Euronext Paris",     "par", df_par),
        ("milan",     "Borsa Italiana",     "mil", df_mil),
        ("frankfurt", "Deutsche Börse",     "etr", df_etr),
        ("swiss",     "SIX Swiss Exchange", "swx", df_swx),
    ]
    _active_tabs = [(key, label, rkey, data)
                    for key, label, rkey, data in _EXCHANGE_TAB_META
                    if key in set(_enabled)]
    _tab_labels  = ["★ Watchlist"] + [label for _, label, _, _ in _active_tabs]
    tab_watchlist, *_exchange_tabs = st.tabs(_tab_labels)

    _SCORE_OPTIONS = [
        "🟢 Strong Buy (> 70)",
        "🟡 Monitor (40–70)",
        "🔴 Avoid (< 40)",
        "All scores",
    ]

    _DECISION_MAP = {
        "🟢 Strong Buy (> 70)": "Strong Buy",
        "🟡 Monitor (40–70)":   "Monitor",
        "🔴 Avoid (< 40)":      "Avoid",
    }

    def _apply_score_filter(df_in: pd.DataFrame, sel: str) -> pd.DataFrame:
        decision = _DECISION_MAP.get(sel)
        out = df_in[df_in["Decision"] == decision] if decision else df_in
        return out.reset_index(drop=True)

    # ── Tab: Watchlist ────────────────────────────────────────────────────────
    with tab_watchlist:
        _wl_tickers = watchlist
        _wl_col, _wl_refresh = st.columns([9, 1])
        with _wl_refresh:
            if st.button("🔄 refresh", type="tertiary", key="wl_refresh"):
                _bust_cache()
        if not _wl_tickers:
            with _wl_col:
                st.info("Check ★ next to any stock in the screener to add it to your watchlist.")
        else:
            _all_df = pd.concat([df, df_ams, df_par, df_mil, df_etr, df_swx], ignore_index=True)
            wl_df = _all_df[_all_df["Ticker"].isin(_wl_tickers)].reset_index(drop=True)
            wl_edited, n_wl = _render_table(wl_df, "watchlist",
                                             score_key="wl_score_filter",
                                             score_default=_SCORE_OPTIONS[3])
            with _wl_col:
                st.markdown(f"**{n_wl}** stocks · uncheck ★ to remove")
            still_watched = set(wl_edited.loc[wl_edited["★"], "Ticker"].tolist())
            if still_watched != _wl_tickers:
                save_watchlist(still_watched)
                st.rerun()

    def _render_exchange_tab(exchange_df: pd.DataFrame, key: str) -> None:
        """Render a screener exchange tab — toolbar, count, table, watchlist sync."""
        valued      = exchange_df["fair_value"].notna()
        n_unvalued  = (~valued).sum()
        hint        = _HINT_WATCHLIST
        _idx_info   = _INDEX_TICKERS.get(key)
        _idx_name   = _idx_info[0] if _idx_info else None
        _idx_tickers = _idx_info[1] if _idx_info else frozenset()

        cnt_col, _ti1, _ti2, refresh_col = st.columns([4, 1, 1, 1], vertical_alignment="center")
        with _ti1:
            idx_only = st.toggle(_idx_name, value=not _is_admin, key=f"{key}_idx_only") if _idx_name else False
        with _ti2:
            show_all = st.toggle("unvalued", value=False,
                                 key=f"{key}_show_unvalued") if n_unvalued > 0 else False
        with refresh_col:
            if st.button("🔄 refresh", type="tertiary", key=f"{key}_refresh"):
                _bust_cache()

        tab_df = exchange_df if show_all else exchange_df[valued].reset_index(drop=True)
        if idx_only and _idx_tickers:
            tab_df = tab_df[tab_df["Ticker"].isin(_idx_tickers)].reset_index(drop=True)
        edited, n_shown = _render_table(tab_df, key,
                                        score_key=f"{key}_score_filter",
                                        score_default=_SCORE_OPTIONS[0])
        with cnt_col:
            st.markdown(f"**{n_shown}** stocks · {hint}")

        new_wl = set(edited.loc[edited["★"], "Ticker"].tolist())
        merged = (watchlist - set(exchange_df["Ticker"])) | new_wl
        if merged != watchlist:
            save_watchlist(merged)
            st.rerun()

    for _tab, (_, _, _rkey, _data) in zip(_exchange_tabs, _active_tabs):
        with _tab:
            _render_exchange_tab(_data, _rkey)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — PORTFOLIO
# ══════════════════════════════════════════════════════════════════════════════

if _page == "portfolio":

    # ── Load saved portfolio ───────────────────────────────────────────────────
    pf = load_portfolio()
    if pf is None:
        pf = pd.DataFrame()

    # ── Migrate: ensure new fields exist ──────────────────────────────────────
    if not pf.empty:
        _dirty = False
        if "account" not in pf.columns:
            pf["account"] = ""
            _dirty = True
        if "purchase_price" not in pf.columns:
            pf["purchase_price"] = (
                pd.to_numeric(pf["purchase_value"], errors="coerce") /
                pd.to_numeric(pf["shares"],         errors="coerce")
            ).round(4)
            _dirty = True
        if _dirty:
            save_portfolio(pf)

        # ── Drop rows with no valid ticker ────────────────────────────────────
        pf = pf[pf["ticker"].notna() & (pf["ticker"].astype(str).str.strip() != "")].reset_index(drop=True)

    # ── Screener data + Add-position dialog (always needed, even for empty portfolio) ──
    with _loading_screen("Loading screener data…"):
        _all_scr_df = pd.concat(list(_load_all_screener_data(_cache_version(), tuple(ALL_EXCHANGES))), ignore_index=True)
    _all_screener = _all_scr_df[["Ticker", "Name"]].sort_values("Name", key=lambda s: s.str.lower())
    _ticker_options = _all_screener["Ticker"].tolist()
    _ticker_labels  = {
        row["Ticker"]: f"{row['Name']}  ({row['Ticker']})"
        for _, row in _all_screener.iterrows()
    }
    _port_price_map = _all_scr_df.drop_duplicates("Ticker").set_index("Ticker")["Price"].to_dict()

    @st.dialog("Add position", width="large")
    def _dlg_add_position():
        _c1, _c2, _c3, _c4 = st.columns([3, 1, 2, 2])
        with _c1:
            ticker = st.selectbox("Company", options=_ticker_options, format_func=lambda t: _ticker_labels.get(t, t))
        with _c2:
            shares = st.number_input("Shares", min_value=1, step=1, value=1)
        with _c3:
            pur_date = st.date_input("Buy Date", format="DD/MM/YYYY")
        with _c4:
            _price      = float(_port_price_map.get(ticker) or 0.0)
            total_price = st.number_input("Invested (€)", min_value=0.0, step=0.01,
                                          value=round(_price * shares, 2), format="%.2f")
        _, _save_btn = st.columns([3, 1])
        with _save_btn:
            _do_save = st.button("💾 Save", key="dlg_add_save", width="stretch")
        if _do_save and shares > 0 and total_price > 0:
            name = _ticker_labels.get(ticker, ticker).split("  (")[0]
            add_position({
                "name":           name,
                "google_ticker":  "",
                "ticker":         ticker,
                "shares":         shares,
                "purchase_price": round(total_price / shares, 4),
                "purchase_value": round(total_price, 2),
                "target_price":   None,
                "dividends":      0.0,
                "date_in":        pd.Timestamp(pur_date).isoformat(),
                "account":        "",
            })
            st.rerun()

    st_autorefresh(interval=60_000, key="portfolio_refresh")

    if pf.empty:
        # ── Empty portfolio — show Add button only ────────────────────────────
        sub_positions, sub_sold, sub_dividends = st.tabs(["Positions", "Realised", "Dividends"])
        with sub_positions:
            if st.button("🛒 Buy", key="btn_add_pos_empty"):
                _dlg_add_position()
            st.info("Your portfolio is empty. Click 🛒 Buy to add your first position.")
        with sub_dividends:
            st.info("No positions yet. Add stocks in the Positions tab first.")
        with sub_sold:
            st.info("No sold positions yet.")
        st.stop()

    # ── Fetch live prices ─────────────────────────────────────────────────────
    with _loading_screen("Fetching live prices & fair values…"):
        live_data = _fetch_live_data(tuple(pf["ticker"].tolist()))

    def _lv(field, default=None):
        return pf["ticker"].map(lambda t: live_data[t].get(field, default))

    pf["live_price"]      = _lv("price")
    pf["analyst_target"]  = _lv("analyst_target")
    pf["graham_number"]   = _lv("graham_number")
    pf["pe_fair_value"]   = _lv("pe_fair_value")
    pf["graham_growth"]   = _lv("graham_growth")
    pf["fair_value"]      = _lv("fair_value")
    pf["div_rate"]        = _lv("div_rate", 0).map(lambda v: v or 0)
    pf["day_change_pct"]  = _lv("day_change_pct")
    pf["prev_close"]      = _lv("prev_close")
    pf["sector"]          = _lv("sector")
    pf["country"]         = _lv("country")
    pf["expected_annual"] = (pf["div_rate"] * pf["shares"]).round(2)
    pf["current_value"]   = pf["live_price"] * pf["shares"]
    pf["price_gain"]      = pf["current_value"] - pf["purchase_value"]
    _cost = pf["purchase_value"].replace(0, float("nan"))
    _price = pf["live_price"].replace(0, float("nan"))
    pf["price_gain_pct"]  = (pf["price_gain"] / _cost * 100).round(2)
    pf["total_return"]    = pf["price_gain"] + pf["dividends"].fillna(0)
    pf["total_return_pct"] = (pf["total_return"] / _cost * 100).round(2)
    pf["upside_pct"]      = ((pf["analyst_target"] - pf["live_price"]) / _price * 100).round(1)
    pf["fv_upside_pct"]   = ((pf["fair_value"]     - pf["live_price"]) / _price * 100).round(1)

    _scr = _all_scr_df.set_index("Ticker")
    pf["value_score"] = pf["ticker"].map(_scr["Value Score"].to_dict() if "Value Score" in _scr.columns else {})

    def _scr_col(field: str) -> "pd.Series":
        col = _scr[field] if field in _scr.columns else pd.Series(dtype=object)
        return pf["ticker"].map(col.to_dict())

    # ── Summary cards (shared across both sub-tabs) ───────────────────────────
    total_invested   = pf["purchase_value"].sum()
    total_current    = pf["current_value"].sum()
    total_dividends  = pf["dividends"].fillna(0).sum()
    total_expected   = pf["expected_annual"].sum()
    price_gain       = total_current - total_invested
    total_return     = price_gain + total_dividends
    price_gain_pct   = _safe_pct(price_gain,   total_invested)
    total_return_pct = _safe_pct(total_return, total_invested)

    # Auto-backfill missing trading days — check BEFORE recording today's snapshot
    # so first-ever load (empty history) correctly triggers the full backfill
    _vh_check = load_value_history()
    _yesterday = (pd.Timestamp.today() - pd.Timedelta(days=1)).normalize()
    _last_date = (
        pd.to_datetime(_vh_check["date"]).max()
        if _vh_check is not None and not _vh_check.empty
        else pd.Timestamp("1970-01-01")
    )
    _needs_backfill = (
        total_current > 0
        and (_last_date < _yesterday or (_vh_check is None or len(_vh_check) <= 1))
    )
    if _needs_backfill:
        with st.spinner("Updating value history…"):
            backfill_value_history(pf, load_sold())

    if total_current > 0:
        record_value_snapshot(total_invested, total_current)

    sub_positions, sub_sold, sub_dividends = st.tabs(["Positions", "Realised", "Dividends"])

    # ── Sub-tab: Positions ────────────────────────────────────────────────────
    with sub_positions:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Invested",      f"€{total_invested:,.0f}")
        c2.metric("Current value", f"€{total_current:,.0f}",  delta=f"€{price_gain:+,.0f} ({price_gain_pct:+.1f}%)")
        c3.metric("Dividends",     f"€{total_dividends:,.0f}")
        c4.metric("Total return",  f"€{total_return:,.0f}",   delta=f"{total_return_pct:+.1f}%")
        st.divider()

        # ── CRUD actions ─────────────────────────────────────────────────────
        @st.dialog("Edit positions", width="large")
        def _dlg_edit_position():
            _edit_src = pf.sort_values("name", key=lambda s: s.str.lower()).reset_index()  # orig idx in 'index' col
            _tbl = pd.DataFrame({
                "_idx":        _edit_src["index"],
                "🗑️":          False,
                "Company":     _edit_src["name"],
                "Stocks":      pd.to_numeric(_edit_src["shares"], errors="coerce").fillna(0).astype(int),
                "Invested": (
                    pd.to_numeric(_edit_src["purchase_price"], errors="coerce") *
                    pd.to_numeric(_edit_src["shares"],         errors="coerce")
                ).round(2),
                "Date":        pd.to_datetime(
                    _edit_src["date_in"], format="mixed", dayfirst=False, errors="coerce"
                ).dt.date,
            })

            _row_h  = 35
            _header = 35
            _height = _header + min(len(_tbl), 8) * _row_h

            _edited = st.data_editor(
                _tbl.drop(columns="_idx"),
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                height=_height,
                column_config={
                    "🗑️":          st.column_config.CheckboxColumn("🗑️",               width=55),
                    "Company":     st.column_config.TextColumn("Company",              disabled=True, pinned=True),
                    "Stocks":      st.column_config.NumberColumn("Shares",             min_value=1, step=1, format="%d"),
                    "Invested":    st.column_config.NumberColumn("Invested (€)",        min_value=0.01, format="%.2f"),
                    "Date":        st.column_config.DateColumn("Buy Date",             format="DD/MM/YYYY"),
                },
                key="dlg_edit_table",
            )

            to_delete  = _edited[_edited["🗑️"]].index.tolist()
            to_keep    = _edited[~_edited["🗑️"]]
            n_selected = len(to_delete)

            _del_note, _save_col = st.columns([3, 1])
            with _del_note:
                if n_selected:
                    st.caption(f"🗑️ {n_selected} selected for deletion")
            with _save_col:
                if st.button("💾 Save", key="dlg_edit_save", width="stretch"):
                    for i, row in to_keep.iterrows():
                        orig_idx = int(_tbl.iloc[i]["_idx"])
                        new_shares = max(1, int(row["Stocks"]))
                        new_total  = float(row["Invested"])
                        pf.at[orig_idx, "shares"]         = new_shares
                        pf.at[orig_idx, "purchase_price"] = round(new_total / new_shares, 4)
                        pf.at[orig_idx, "purchase_value"] = round(new_total, 2)
                        if pd.notna(row["Date"]) and row["Date"] is not None:
                            pf.at[orig_idx, "date_in"] = pd.Timestamp(row["Date"]).isoformat()
                    if to_delete:
                        del_orig = [int(_tbl.iloc[i]["_idx"]) for i in to_delete]
                        pf.drop(index=del_orig, inplace=True)
                        pf.reset_index(drop=True, inplace=True)
                    update_positions(pf)
                    st.rerun()

        # ── Column groups (same groups as screener) ───────────────────────────
        _POS_EXTRA_GROUPS = {
            "Valuation": {
                "Analyst Target": pf["analyst_target"].map(_fmt_eur),
                "💎 UV":          pf["fair_value"].map(_fmt_eur),
                "UV Upside %":    pf["fv_upside_pct"],
            },
            "Valuation models": {
                "Graham #":       _scr_col("graham_number").map(_fmt_eur),
                "PE Fair Val":    _scr_col("pe_fair_value").map(_fmt_eur),
                "EPV":            _scr_col("epv").map(_fmt_eur),
                "DDM (1-stage)":  _scr_col("ddm").map(_fmt_eur),
                "DDM (2-stage)":  _scr_col("ddm_multistage").map(_fmt_eur),
            },
            "Risk & size": {
                "Risk Score":  _scr_col("Risk Score"),
                "Mkt Cap":     _scr_col("Market Cap").map(_fmt_mcap),
                "Beta":        _scr_col("beta").map(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
                "Debt/Equity": _scr_col("debtToEquity").map(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
            },
            "Multiples": {
                "P/E":       _scr_col("trailingPE").map(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
                "P/B":       _scr_col("priceToBook").map(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
                "EV/EBITDA": _scr_col("enterpriseToEbitda").map(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
            },
            "Quality": {
                "ROE %":       _scr_col("returnOnEquity").map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
                "ROA %":       _scr_col("returnOnAssets").map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
                "Op Margin %": _scr_col("operatingMargins").map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
                "FCF Yield %": _scr_col("fcfYield").map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            },
            "Growth": {
                "Rev Growth %": _scr_col("revenueGrowth").map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
                "EPS Growth %": _scr_col("earningsGrowth").map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            },
            "Dividends": {
                "Div/Share":     pf["div_rate"].map(lambda v: f"€{v:.4f}" if pd.notna(v) and v else "—"),
                "Expected Annual": pf["expected_annual"].map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
                "Div Yield":     _scr_col("dividendYield").map(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
                "5yr Avg Yield": _scr_col("fiveYearAvgDividendYield").map(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
                "Payout Ratio":  _scr_col("payoutRatio").map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
                "Cash Payout":   _scr_col("cashPayoutRatio").map(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
                "Div Coverage":  _scr_col("dividendCoverage").map(lambda v: f"{v:.2f}×" if pd.notna(v) else "—"),
                "Div Flag":      _scr_col("Div Flag").map(_fmt_div_flag),
            },
            "Score & date": {
                "Value Score": pf["value_score"],
                "Buy Date":    pd.to_datetime(pf["date_in"], format="mixed", dayfirst=False, errors="coerce").dt.strftime("%d-%m-%Y").fillna("—"),
            },
        }

        @st.dialog("View", width="small")
        def _dlg_columns():
            _sel = st.session_state.get("pos_col_groups", [])
            for _grp in _POS_EXTRA_GROUPS.keys():
                _checked = st.checkbox(_grp, value=(_grp in _sel), key=f"colgrp_{_grp}")
                if _checked and _grp not in _sel:
                    _sel = _sel + [_grp]
                elif not _checked and _grp in _sel:
                    _sel = [g for g in _sel if g != _grp]
            st.session_state["pos_col_groups"] = _sel
            if st.button("Apply", type="primary", width="stretch", key="btn_col_apply"):
                st.rerun()

        @st.dialog("Sell position", width="large")
        def _dlg_sell_position():
            _sell_sorted     = pf.sort_values("name", key=lambda s: s.str.lower())
            _sell_ticker_options = _sell_sorted["ticker"].tolist()
            _sell_ticker_labels  = {
                row["ticker"]: f"{row['name']}  ({row['ticker']})"
                for _, row in _sell_sorted.iterrows()
            }
            _c1, _c2, _c3, _c4 = st.columns([3, 1, 2, 2])
            with _c1:
                ticker = st.selectbox("Company", options=_sell_ticker_options,
                                      format_func=lambda t: _sell_ticker_labels.get(t, t),
                                      key="dlg_sell_ticker")
            _match = pf[pf["ticker"] == ticker]
            with _c2:
                _shares_def = str(int(pd.to_numeric(_match.iloc[0]["shares"], errors="coerce") or 0)) if not _match.empty else "0"
                _shares_raw = st.text_input("Shares", value=_shares_def, key="dlg_sell_shares")
            with _c3:
                sell_date = st.date_input("Sell Date", format="DD/MM/YYYY", key="dlg_sell_date")
            with _c4:
                _current_val = pd.to_numeric(_match.iloc[0].get("current_value"), errors="coerce") if not _match.empty else 0.0
                _proceeds_def = f"{_current_val:.2f}" if pd.notna(_current_val) and _current_val else "0.00"
                _proceeds_raw = st.text_input("Proceeds (€)", value=_proceeds_def, key="dlg_sell_proceeds")
            _, _save_col = st.columns([3, 1])
            with _save_col:
                _do_save = st.button("💾 Save", key="dlg_sell_save", width="stretch")
            try:
                _shares   = max(1, int(_shares_raw.strip()))
                _proceeds = float(_proceeds_raw.strip().replace(",", "."))
            except ValueError:
                _shares, _proceeds = 1, 0.0
            if _do_save and _shares > 0 and _proceeds > 0:
                sell_position(
                    ticker=ticker,
                    shares=_shares,
                    proceeds=_proceeds,
                    sell_date=pd.Timestamp(sell_date).isoformat(),
                )
                st.rerun()

        st.markdown('<div class="uv-crud-sentinel"></div>', unsafe_allow_html=True)
        _c1, _c2, _c3, _c4, _ = st.columns([1, 1, 1, 1, 5], gap="small")
        with _c1:
            _active_groups = st.session_state.get("pos_col_groups", [])
            _col_label = f"⊞ View ({len(_active_groups)})" if _active_groups else "⊞ View"
            if st.button(_col_label, key="btn_col_pos"):
                _dlg_columns()
        with _c2:
            if st.button("🛒 Buy", key="btn_add_pos"):
                _dlg_add_position()
        with _c3:
            if st.button("✏️ Edit", key="btn_edit_pos"):
                _dlg_edit_position()
        with _c4:
            if st.button("💰 Sell", key="btn_sell_pos"):
                _dlg_sell_position()

        _pos_groups = st.session_state.get("pos_col_groups", [])

        # Build core positions DataFrame
        pos_data = {
            "Company":        pf["name"],
            "Ticker":         pf["ticker"],
            "Shares":         pf["shares"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
            "Buy Date":       pd.to_datetime(pf["date_in"], format="mixed", dayfirst=False, errors="coerce").dt.strftime("%d/%m/%Y").fillna("—"),
            "Live Price":     pf["live_price"].map(_fmt_eur),
            "Invested":       pf["purchase_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            "Current":        pf["current_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            "Price Gain":     pf["price_gain"],
            "Dividend":       pf["dividends"].fillna(0).map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
            "Price Gain %":   pf["price_gain_pct"],
            "Total Return %": pf["total_return_pct"],
        }
        for grp in _pos_groups:
            pos_data.update(_POS_EXTRA_GROUPS[grp])

        _core_cols = {"Company", "Ticker", "Shares", "Buy Date", "Live Price",
                      "Invested", "Current", "Price Gain", "Dividend", "Price Gain %", "Total Return %"}

        positions = pd.DataFrame(pos_data).sort_values("Company", key=lambda s: s.str.lower())
        _n_rows = len(positions)

        # Highlight extra columns with a subtle tint
        _extra_cols = [c for c in positions.columns if c not in _core_cols]
        if _extra_cols:
            positions = positions.style.set_properties(
                subset=_extra_cols,
                **{"background-color": "rgba(99, 102, 241, 0.07)"},
            )

        _pos_col_config = {
            "Company":        st.column_config.TextColumn("Company",         pinned=True,
                                  help="Company name"),
            "Ticker":         st.column_config.TextColumn("Ticker",
                                  help="Exchange ticker symbol"),
            "Shares":         st.column_config.TextColumn("Shares",
                                  help="Number of shares held"),
            "Buy Date":       st.column_config.TextColumn("Buy Date",
                                  help="Date the position was opened"),
            "Live Price":     st.column_config.TextColumn("Live Price",
                                  help="Latest market price fetched from yfinance"),
            "Invested":       st.column_config.TextColumn("Invested",
                                  help="Total amount invested (purchase price × shares)"),
            "Current":        st.column_config.TextColumn("Current",
                                  help="Current market value (live price × shares)"),
            "Price Gain":     st.column_config.NumberColumn("Price Gain (€)", format="€%.0f",
                                  help="Unrealised gain/loss in euros: current value − invested"),
            "Dividend":       st.column_config.TextColumn("Dividend",
                                  help="Total dividends received for this position since purchase"),
            "Price Gain %":   st.column_config.NumberColumn("Price Gain %",   format="%.2f%%",
                                  help="Price appreciation since purchase: (current value − invested) / invested"),
            "Total Return %": st.column_config.NumberColumn("Total Return %", format="%.2f%%",
                                  help="Total return including dividends: (price gain + dividends) / invested"),
            "UV Upside %":    st.column_config.NumberColumn("UV Upside %",    format="%+.1f%%",
                                  help="Upside to the UV fair value estimate: (fair value − live price) / live price"),
            "Analyst Target": st.column_config.TextColumn("Analyst Target",
                                  help="Mean analyst consensus price target"),
            "Upside %":       st.column_config.NumberColumn("Upside %",       format="%+.1f%%",
                                  help="Upside to the analyst consensus target: (target − live price) / live price"),
            "Day Chg %":      st.column_config.TextColumn("Day Chg %",
                                  help="Intraday price change vs previous close"),
            "Div/Yr":         st.column_config.TextColumn("Div/Yr",
                                  help="Expected annual dividend income from this position (forward rate × shares)"),
            "Value Score":    st.column_config.ProgressColumn("Value Score",  min_value=0, max_value=100, format="%.1f",
                                  help="UV composite score 0–100. 🟢 Strong Buy >70 · 🟡 Monitor 40–70 · 🔴 Avoid <40"),
            "Risk Score":     st.column_config.ProgressColumn("Risk Score",   min_value=0, max_value=100, format="%.1f",
                                  help="UV risk score 0–10 (displayed as 0–100). Higher = riskier. Aggregates financial health, earnings quality, beta, dividend risk, and liquidity."),
        }

        _row_h  = 35
        _header = 38
        _height = min(_header + _n_rows * _row_h + 4, 800)
        st.dataframe(
            positions,
            width="stretch",
            hide_index=True,
            column_config=_pos_col_config,
            height=_height,
        )

        # ── 1. Gain / loss heatmap ───────────────────────────────────────────
        st.divider()
        _hm_mode_col, _ = st.columns([2, 5])
        _hm_mode = _hm_mode_col.radio(
            "Return",
            options=["Total return", "Daily return"],
            horizontal=True,
            key="hm_mode",
            label_visibility="collapsed",
        )
        st.subheader(f"Gain / loss heatmap — {_hm_mode.lower()}")

        _hm_df = pf.dropna(subset=["name", "current_value"]).copy()
        _hm_df["current_value"] = pd.to_numeric(_hm_df["current_value"], errors="coerce")

        if _hm_mode == "Daily return":
            _hm_df["_ret"] = pd.to_numeric(_hm_df["day_change_pct"], errors="coerce")
            _ret_label = "Day %"
        else:
            _hm_df["_ret"] = pd.to_numeric(_hm_df["price_gain_pct"], errors="coerce")
            _ret_label = "Total %"

        _hm_df = _hm_df.dropna(subset=["_ret", "current_value"])

        if not _hm_df.empty:
            import plotly.graph_objects as go

            _clamp  = 10.0  # colour saturates at ±10 %
            _normed = _hm_df["_ret"].clip(-_clamp, _clamp) / _clamp  # –1 … +1

            _colors = [
                f"rgba({int(220*(1-v))},{int(220*((v+1)/2))},{int(60*(1-abs(v)))},0.85)"
                for v in _normed
            ]

            _labels = [
                f"<b>{row['name']}</b><br>{row['_ret']:+.2f}%"
                for _, row in _hm_df.iterrows()
            ]
            _hover = [
                (
                    f"<b>{row['name']}</b><br>"
                    f"{_ret_label}: {row['_ret']:+.2f}%<br>"
                    f"Value: €{row['current_value']:,.0f}"
                )
                for _, row in _hm_df.iterrows()
            ]

            _hm_fig = go.Figure(go.Treemap(
                labels=_hm_df["name"].tolist(),
                parents=[""] * len(_hm_df),
                values=_hm_df["current_value"].tolist(),
                text=_labels,
                customdata=_hover,
                hovertemplate="%{customdata}<extra></extra>",
                textinfo="text",
                marker=dict(
                    colors=_colors,
                    line=dict(width=2, color="rgba(0,0,0,0.3)"),
                ),
            ))
            _hm_fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                height=340,
            )
            st.plotly_chart(_hm_fig, width="stretch", config=_CHART_CONFIG)
        else:
            st.caption("No return data available.")

        # ── 2. Portfolio value over time ──────────────────────────────────────
        st.divider()
        _vh_title_col, _vh_btn_col = st.columns([4, 1])
        with _vh_title_col:
            st.subheader("Portfolio value over time")
        with _vh_btn_col:
            if st.button("↺ Rebuild history", key="rebuild_value_history", help="Fetch full price history from Yahoo Finance"):
                with st.spinner("Fetching price history…"):
                    _sold_df = load_sold()
                    _n = backfill_value_history(pf, _sold_df)
                st.success(f"Built {_n} data points.")
                st.rerun()

        _vh = load_value_history()
        if _vh is not None and not _vh.empty and len(_vh) >= 2:
            import plotly.graph_objects as go
            _vh["date"]     = pd.to_datetime(_vh["date"])
            _vh["value"]    = pd.to_numeric(_vh["value"],    errors="coerce")
            _vh["invested"] = pd.to_numeric(_vh["invested"], errors="coerce")
            _vh = _vh.dropna(subset=["date", "value"]).sort_values("date")

            _has_spx   = "benchmark_spx"   in _vh.columns and _vh["benchmark_spx"].notna().any()
            _has_stoxx = "benchmark_stoxx" in _vh.columns and _vh["benchmark_stoxx"].notna().any()

            if _has_spx or _has_stoxx:
                _cb_cols = st.columns([1, 1, 4])
                _show_spx   = _cb_cols[0].checkbox("S&P 500",      value=False, key="vh_show_spx",   disabled=not _has_spx)
                _show_stoxx = _cb_cols[1].checkbox("Euro Stoxx 50", value=False, key="vh_show_stoxx", disabled=not _has_stoxx)
            else:
                _show_spx = _show_stoxx = False

            _vfig = go.Figure()
            _vfig.add_trace(go.Scatter(
                x=_vh["date"], y=_vh["value"],
                mode="lines", name="Portfolio value",
                line=dict(color="#4f8ef7", width=2),
                fill="tozeroy",
                fillcolor="rgba(79,142,247,0.08)",
            ))
            _vfig.add_trace(go.Scatter(
                x=_vh["date"], y=_vh["invested"],
                mode="lines", name="Amount invested",
                line=dict(color="#aaaaaa", width=1.5, dash="dot"),
            ))
            if _has_spx and _show_spx:
                _vfig.add_trace(go.Scatter(
                    x=_vh["date"], y=pd.to_numeric(_vh["benchmark_spx"], errors="coerce"),
                    mode="lines", name="S&P 500 (same invested)",
                    line=dict(color="#f4a026", width=1.5, dash="dash"),
                ))
            if _has_stoxx and _show_stoxx:
                _vfig.add_trace(go.Scatter(
                    x=_vh["date"], y=pd.to_numeric(_vh["benchmark_stoxx"], errors="coerce"),
                    mode="lines", name="Euro Stoxx 50 (same invested)",
                    line=dict(color="#a855f7", width=1.5, dash="dash"),
                ))
            _vfig.update_layout(
                margin=dict(l=0, r=0, t=32, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                yaxis=dict(tickprefix="€", tickformat=",.0f"),
                xaxis=dict(showgrid=False),
                hovermode="x unified",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(_vfig, width="stretch", config=_CHART_CONFIG)
        else:
            st.caption("No history yet — click **↺ Rebuild history** to fetch it from Yahoo Finance.")

        # ── 3. Sector / country breakdown ─────────────────────────────────────
        st.divider()
        _bd_options = {"Sector": "sector", "Country": "country"}
        _bd_by = st.radio(
            "Breakdown",
            options=list(_bd_options.keys()),
            key="pos_breakdown_by",
            horizontal=True,
            label_visibility="collapsed",
        )
        st.subheader(f"{_bd_by} breakdown")
        _bd_field = _bd_options[_bd_by]
        _bd_series = (
            pf.dropna(subset=["current_value"])
              .assign(**{_bd_field: pf[_bd_field].fillna("Unknown")})
              .groupby(_bd_field)["current_value"]
              .sum()
              .sort_values(ascending=False)
        )
        _donut_chart(_bd_series)

        # ── 3. Portfolio allocation + P&L per position ───────────────────────
        st.divider()
        ch1, ch2 = st.columns(2)
        with ch1:
            st.subheader("Portfolio allocation")
            _static_bar(
                pf.dropna(subset=["current_value", "name"])
                  .groupby("name")["current_value"].sum()
                  .sort_values(ascending=False),
                color="#4f8ef7",
            )
        with ch2:
            st.subheader("P&L per position")
            _static_bar(
                pf.dropna(subset=["price_gain", "name"])
                  .groupby("name")["price_gain"].sum()
                  .sort_values(ascending=False)
            )

    # ── Sub-tab: Dividends ────────────────────────────────────────────────────
    with sub_dividends:
        div_hist = load_div_hist()
        if div_hist is not None and not div_hist.empty:
            div_hist["amount"] = pd.to_numeric(div_hist["amount"], errors="coerce")
            div_hist["date"]   = pd.to_datetime(div_hist["date"], errors="coerce")
            total_hist = div_hist["amount"].sum()
        else:
            total_hist = total_dividends

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Total received",   f"€{total_hist:,.2f}")
        d2.metric("Current holdings", f"€{total_dividends:,.2f}")
        d3.metric("Expected 12 mths", f"€{total_expected:,.2f}")
        d4.metric("Portfolio yield",  f"{total_expected / total_current * 100:.2f}%" if total_current else "—")
        st.markdown('<div style="height:1.75rem"></div>', unsafe_allow_html=True)
        st.divider()

        # ── Dividend CRUD dialogs ─────────────────────────────────────────────
        _div_ticker_options = pf["ticker"].tolist()
        _div_ticker_labels  = {
            row["ticker"]: f"{row['name']}  ({row['ticker']})"
            for _, row in pf.iterrows()
        }

        @st.dialog("Add dividend", width="large")
        def _dlg_add_dividend():
            _c1, _c2, _c3, _c4 = st.columns([3, 1, 1, 2])
            with _c1:
                ticker = st.selectbox("Stock", options=_div_ticker_options,
                                      format_func=lambda t: _div_ticker_labels.get(t, t),
                                      key="dlg_add_div_ticker")
            with _c2:
                _shares_def = ""
                _match = pf[pf["ticker"] == ticker]
                if not _match.empty:
                    _shares_def = str(int(pd.to_numeric(_match.iloc[0]["shares"], errors="coerce") or 0))
                _shares_raw = st.text_input("Shares", value=_shares_def, key="dlg_add_div_shares")
            with _c3:
                _dps_raw = st.text_input("Div/Share (€)", value="0.0000", key="dlg_add_div_dps")
            with _c4:
                div_date = st.date_input("Date", format="DD/MM/YYYY", key="dlg_add_div_date")
            _, _save_col = st.columns([3, 1])
            with _save_col:
                _do_save = st.button("💾 Save", key="dlg_add_div_save", width="stretch")
            try:
                _shares = max(1, int(_shares_raw.strip()))
                _dps    = float(_dps_raw.strip().replace(",", "."))
            except ValueError:
                _shares, _dps = 1, 0.0
            if _do_save and _shares > 0 and _dps > 0:
                _row_match = pf[pf["ticker"] == ticker]
                _name         = _row_match.iloc[0]["name"] if not _row_match.empty else ticker
                _google_ticker = _row_match.iloc[0].get("google_ticker", "") if not _row_match.empty else ""
                add_dividend({
                    "name":          _name,
                    "google_ticker": _google_ticker,
                    "ticker":        ticker,
                    "shares":        _shares,
                    "amount":        round(_dps * _shares, 2),
                    "date":          pd.Timestamp(div_date).isoformat(),
                })
                st.rerun()

        @st.dialog("Edit dividends", width="large")
        def _dlg_edit_dividends():
            _dh = load_div_hist()
            if _dh is None or _dh.empty:
                st.info("No dividend history to edit.")
                return
            _dh = _dh.copy().reset_index(drop=True)
            _dh["amount"] = pd.to_numeric(_dh["amount"], errors="coerce").fillna(0)
            _dh["date"]   = pd.to_datetime(_dh["date"], errors="coerce")
            _dh["shares"] = pd.to_numeric(_dh.get("shares"), errors="coerce").fillna(0).astype(int)

            _tbl = pd.DataFrame({
                "_idx":      range(len(_dh)),
                "🗑️":        False,
                "Company":   _dh["name"],
                "Ticker":    _dh["ticker"],
                "Shares":    _dh["shares"],
                "Div/Share": (_dh["amount"] / _dh["shares"].replace(0, float("nan"))).round(4),
                "Total (€)": _dh["amount"],
                "Date":      _dh["date"].dt.date,
            })

            _row_h  = 35
            _header = 35
            _height = _header + min(len(_tbl), 10) * _row_h

            _edited = st.data_editor(
                _tbl.drop(columns="_idx"),
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                height=_height,
                column_config={
                    "🗑️":        st.column_config.CheckboxColumn("🗑️",           width=55),
                    "Company":   st.column_config.TextColumn("Company",          disabled=True, pinned=True),
                    "Ticker":    st.column_config.TextColumn("Ticker",           disabled=True),
                    "Shares":    st.column_config.NumberColumn("Shares",         min_value=1, step=1, format="%d"),
                    "Div/Share": st.column_config.NumberColumn("Div/Share (€)",  min_value=0.0, format="%.4f"),
                    "Total (€)": st.column_config.NumberColumn("Total (€)",      min_value=0.0, format="%.2f", disabled=True),
                    "Date":      st.column_config.DateColumn("Date",             format="DD/MM/YYYY"),
                },
                key="dlg_edit_div_table",
            )

            to_delete  = _edited[_edited["🗑️"]].index.tolist()
            to_keep    = _edited[~_edited["🗑️"]]
            n_selected = len(to_delete)

            _del_note, _save_col = st.columns([3, 1])
            with _del_note:
                if n_selected:
                    st.caption(f"🗑️ {n_selected} selected for deletion")
            with _save_col:
                if st.button("💾 Save", key="dlg_edit_div_save", width="stretch"):
                    updated = []
                    for i, row in to_keep.iterrows():
                        orig_idx = int(_tbl.iloc[i]["_idx"])
                        _new_shares = max(1, int(row["Shares"]))
                        _new_dps    = float(row["Div/Share"]) if pd.notna(row["Div/Share"]) else 0.0
                        updated.append({
                            "name":          _dh.iloc[orig_idx]["name"],
                            "google_ticker": _dh.iloc[orig_idx].get("google_ticker", ""),
                            "ticker":        _dh.iloc[orig_idx]["ticker"],
                            "shares":        _new_shares,
                            "amount":        round(_new_dps * _new_shares, 2),
                            "date":          pd.Timestamp(row["Date"]).isoformat() if pd.notna(row["Date"]) else _dh.iloc[orig_idx]["date"].isoformat(),
                        })
                    new_dh = pd.DataFrame(updated)
                    update_div_hist(new_dh)
                    st.rerun()

        st.markdown('<div class="uv-crud-sentinel"></div>', unsafe_allow_html=True)

        # Compute year options here so the selectbox can live in the toolbar row
        _div_years        = sorted(div_hist["date"].dt.year.dropna().unique().astype(int), reverse=True) if div_hist is not None and not div_hist.empty else []
        _div_year_options = ["All"] + _div_years
        _div_year_default = _div_year_options.index(datetime.now().year) if datetime.now().year in _div_year_options else 0

        _da1, _da2, _da_gap, _da_filter = st.columns([1, 1, 5, 2], gap="small")
        with _da1:
            if st.button("➕ Add", key="btn_add_div"):
                _dlg_add_dividend()
        with _da2:
            if st.button("✏️ Edit", key="btn_edit_div"):
                _dlg_edit_dividends()
        with _da_filter:
            selected_year = st.selectbox("Year", _div_year_options, index=_div_year_default,
                                         key="div_year_filter", label_visibility="collapsed")

        # Full dividend payment history
        if div_hist is not None and not div_hist.empty:

            hist_table = div_hist.copy()
            if selected_year != "All":
                hist_table = hist_table[hist_table["date"].dt.year == selected_year]
            hist_table = hist_table.sort_values("date", ascending=False).reset_index(drop=True)
            hist_shares = pd.to_numeric(hist_table.get("shares"), errors="coerce") if "shares" in hist_table.columns else None
            div_per_share = (hist_table["amount"] / hist_shares).round(4) if hist_shares is not None else None
            TAX_RATE = 0.30
            gross = hist_table["amount"]
            tax   = (gross * TAX_RATE).round(2)
            net   = (gross - tax).round(2)
            hist_display = pd.DataFrame({
                "Company":   hist_table["name"],
                "Ticker":    hist_table["ticker"],
                "Shares":    hist_shares.map(lambda v: f"{v:.0f}" if pd.notna(v) else "—") if hist_shares is not None else "—",
                "Div/Share": div_per_share.map(lambda v: f"€{v:.4f}" if pd.notna(v) else "—") if div_per_share is not None else "—",
                "Gross":     gross.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
                "Tax (30%)": tax.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
                "Net":       net.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
                "Date":      hist_table["date"].dt.strftime("%d-%m-%Y"),
            })
            st.dataframe(hist_display, width="stretch", hide_index=True,
                         height=(len(hist_display) + 1) * 35 + 10,
                         column_config={
                             "Company":   st.column_config.TextColumn("Company",   pinned=True,
                                              help="Company name"),
                             "Ticker":    st.column_config.TextColumn("Ticker",
                                              help="Exchange ticker symbol"),
                             "Shares":    st.column_config.TextColumn("Shares",
                                              help="Number of shares held at the time of the dividend payment"),
                             "Div/Share": st.column_config.TextColumn("Div/Share",
                                              help="Dividend per share = total amount ÷ shares"),
                             "Gross":     st.column_config.TextColumn("Gross",
                                              help="Total gross dividend received before tax"),
                             "Tax (30%)": st.column_config.TextColumn("Tax (30%)",
                                              help="Belgian withholding tax estimated at 30% of gross dividend"),
                             "Net":       st.column_config.TextColumn("Net",
                                              help="Net dividend after 30% withholding tax"),
                             "Date":      st.column_config.TextColumn("Date",
                                              help="Date the dividend was received or recorded"),
                         })

            st.divider()
            ch3, ch4 = st.columns(2)
            with ch3:
                st.subheader("Total received per stock")
                _div_clean = div_hist[div_hist["name"].astype(str).str.strip().isin(["", "nan", "None"]) == False]
                _static_bar(
                    _div_clean.groupby("name")["amount"].sum()
                              .sort_values(ascending=False),
                    color="#4caf80",
                )
            with ch4:
                st.subheader("Dividends by year")
                by_year = _div_clean.copy()
                by_year["year"] = by_year["date"].dt.year
                _yr_series = by_year.groupby("year")["amount"].sum().sort_index()
                _static_bar(_yr_series.rename(index=str), color="#4caf80")
        else:
            st.info("Re-upload your Excel file to load full dividend history.")

    # ── Sub-tab: Sold ─────────────────────────────────────────────────────────
    with sub_sold:
        sold = load_sold()
        if sold is None or sold.empty:
            st.info("No sold positions found in your portfolio file.")
        else:
            pv                     = pd.to_numeric(sold["purchase_value"], errors="coerce")
            sv                     = pd.to_numeric(sold["sale_value"], errors="coerce")
            sold["price_gain"]     = sv - pv
            sold["price_gain_pct"] = (sold["price_gain"] / pv * 100).round(2)
            sold["dividends"]      = pd.to_numeric(sold["dividends"], errors="coerce").fillna(0)
            sold["total_return"]   = sold["price_gain"] + sold["dividends"]
            sold["held_days"]      = (pd.to_datetime(sold["date_out"], format="mixed", dayfirst=False, errors="coerce") - pd.to_datetime(sold["date_in"], format="mixed", dayfirst=False, errors="coerce")).dt.days

            def _annual_return(row):
                if pd.isna(row["held_days"]) or row["held_days"] <= 0 or pv[row.name] <= 0:
                    return None
                total_value = sv[row.name] + row["dividends"]
                return ((total_value / pv[row.name]) ** (365 / row["held_days"]) - 1) * 100

            # Use pre-computed annual_return_pct if present, otherwise compute on the fly
            if "annual_return_pct" in sold.columns:
                _computed = sold.apply(_annual_return, axis=1)
                sold["annual_return_pct"] = sold["annual_return_pct"].combine_first(_computed).round(2)
            else:
                sold["annual_return_pct"] = sold.apply(_annual_return, axis=1).round(2)

            # Summary cards
            _pv_sum = pv.sum()
            _tr_sum = sold["total_return"].sum()
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Positions sold",  len(sold))
            s2.metric("Total invested",  f"€{_pv_sum:,.0f}")
            s3.metric("Total proceeds",  f"€{sv.sum():,.0f}")
            s4.metric("Realised return", f"€{_tr_sum:,.0f}",
                      delta=f"{_tr_sum / _pv_sum * 100:+.1f}%" if _pv_sum else "—")
            st.divider()

            # ── Edit sold dialog ──────────────────────────────────────────────
            @st.dialog("Edit realised positions", width="large")
            def _dlg_edit_sold():
                _sold_src = sold.sort_values("name", key=lambda s: s.str.lower()).reset_index()  # orig idx in 'index' col
                _tbl = pd.DataFrame({
                    "_idx":    _sold_src["index"],
                    "🗑️":      False,
                    "Company": _sold_src["name"],
                    "Shares":  pd.to_numeric(_sold_src["shares"], errors="coerce").fillna(0).astype(int),
                    "Proceeds (€)": pd.to_numeric(_sold_src["sale_value"], errors="coerce").fillna(0).round(2),
                    "Sell Date":    pd.to_datetime(_sold_src["date_out"], format="mixed", dayfirst=False, errors="coerce").dt.date,
                })

                _row_h  = 35
                _header = 35
                _height = _header + min(len(_tbl), 8) * _row_h

                _edited = st.data_editor(
                    _tbl.drop(columns="_idx"),
                    width="stretch",
                    hide_index=True,
                    num_rows="fixed",
                    height=_height,
                    column_config={
                        "🗑️":           st.column_config.CheckboxColumn("🗑️",            width=55),
                        "Company":      st.column_config.TextColumn("Company",           disabled=True, pinned=True),
                        "Shares":       st.column_config.NumberColumn("Shares",          min_value=1, step=1, format="%d"),
                        "Proceeds (€)": st.column_config.NumberColumn("Proceeds (€)",   min_value=0.0, format="%.2f"),
                        "Sell Date":    st.column_config.DateColumn("Sell Date",         format="DD/MM/YYYY"),
                    },
                    key="dlg_edit_sold_table",
                )

                to_delete  = _edited[_edited["🗑️"]].index.tolist()
                to_keep    = _edited[~_edited["🗑️"]]
                n_selected = len(to_delete)

                _del_note, _save_col = st.columns([3, 1])
                with _del_note:
                    if n_selected:
                        st.caption(f"🗑️ {n_selected} selected for deletion")
                with _save_col:
                    if st.button("💾 Save", key="dlg_edit_sold_save", width="stretch"):
                        _sold_updated = sold.copy()
                        for i, row in to_keep.iterrows():
                            orig_idx = int(_tbl.iloc[i]["_idx"])
                            _sold_updated.at[orig_idx, "shares"]     = max(1, int(row["Shares"]))
                            _sold_updated.at[orig_idx, "sale_value"] = round(float(row["Proceeds (€)"]), 2)
                            if pd.notna(row["Sell Date"]) and row["Sell Date"] is not None:
                                _sold_updated.at[orig_idx, "date_out"] = pd.Timestamp(row["Sell Date"]).isoformat()
                        if to_delete:
                            del_orig = [int(_tbl.iloc[i]["_idx"]) for i in to_delete]
                            _sold_updated.drop(index=del_orig, inplace=True)
                            _sold_updated.reset_index(drop=True, inplace=True)
                        save_sold(_sold_updated)
                        st.rerun()

            st.markdown('<div class="uv-crud-sentinel"></div>', unsafe_allow_html=True)
            _se1, _ = st.columns([1, 8], gap="small")
            with _se1:
                if st.button("✏️ Edit", key="btn_edit_sold"):
                    _dlg_edit_sold()

            _sold_date_out = pd.to_datetime(sold["date_out"], format="mixed", dayfirst=False, errors="coerce")
            sold = sold.assign(_sort_date=_sold_date_out).sort_values("_sort_date", ascending=False)

            sold_table = pd.DataFrame({
                "Company":         sold["name"],
                "Ticker":          sold["ticker"],
                "Shares":          pd.to_numeric(sold["shares"], errors="coerce").map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
                "Invested":        pd.to_numeric(sold["purchase_value"], errors="coerce").map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
                "Proceeds":        pd.to_numeric(sold["sale_value"], errors="coerce").map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
                "Price Gain":      sold["price_gain"].map(lambda v: f"€{v:+,.0f}" if pd.notna(v) else "—"),
                "Dividends":       sold["dividends"].map(lambda v: f"€{v:,.0f}"),
                "Price Gain %":    sold["price_gain_pct"],
                "Annual Return %": sold["annual_return_pct"],
                "Buy Date":        pd.to_datetime(sold["date_in"], format="mixed", dayfirst=False, errors="coerce").dt.strftime("%d-%m-%Y").fillna("—"),
                "Sell Date":       sold["_sort_date"].dt.strftime("%d-%m-%Y").fillna("—"),
            })

            st.dataframe(
                sold_table,
                width="stretch",
                hide_index=True,
                column_config={
                    "Company":         st.column_config.TextColumn("Company",           pinned=True,
                                           help="Company name"),
                    "Ticker":          st.column_config.TextColumn("Ticker",
                                           help="Exchange ticker symbol"),
                    "Shares":          st.column_config.TextColumn("Shares",
                                           help="Number of shares sold"),
                    "Invested":        st.column_config.TextColumn("Invested",
                                           help="Total amount originally invested (purchase price × shares)"),
                    "Proceeds":        st.column_config.TextColumn("Proceeds",
                                           help="Total sale proceeds received"),
                    "Price Gain":      st.column_config.TextColumn("Price Gain",
                                           help="Absolute price gain/loss: proceeds − invested"),
                    "Dividends":       st.column_config.TextColumn("Dividends",
                                           help="Total dividends collected while the position was held"),
                    "Price Gain %":    st.column_config.NumberColumn("Price Gain %",    format="%.2f%%",
                                           help="Price gain as a percentage of the original investment"),
                    "Annual Return %": st.column_config.NumberColumn("Annual Return %", format="%.2f%%",
                                           help="Annualised total return (price gain + dividends) using the CAGR formula over the holding period"),
                    "Buy Date":        st.column_config.TextColumn("Buy Date",
                                           help="Date the position was opened"),
                    "Sell Date":       st.column_config.TextColumn("Sell Date",
                                           help="Date the position was closed"),
                },
                height=(len(sold) + 1) * 35 + 10,
            )

            st.divider()
            st.subheader("Realised return per position")
            _static_bar(
                sold.dropna(subset=["name"])
                    .groupby("name")["total_return"].sum()
                    .sort_values(ascending=False)
            )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE — SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

if _page == "settings":
    if _is_admin:
        tab_admin, tab_screener, tab_import, tab_export, tab_backup = st.tabs(["🔑 Users", "⚙️ Screener", "📂 Import", "📥 Export", "💾 Backup & Restore"])
    else:
        tab_export, = st.tabs(["📥 Export"])

    if _is_admin:
        with tab_admin:
            _render_admin_users()

        with tab_import:
            st.subheader("Import portfolio")
            st.caption("Upload an Excel file to import positions, sold history and dividends. "
                       "This will replace all existing portfolio data for this account.")
            _imp_file = st.file_uploader("Choose your portfolio .xlsx file", type=["xlsx"], key="imp_portfolio")
            if _imp_file:
                with st.spinner("Parsing Excel…"):
                    try:
                        _imp_pf, _imp_sold, _imp_div = parse_excel(_imp_file)
                        if _imp_pf.empty:
                            st.error("No open EBR:/AMS:/EPA:/BIT:/ETR:/SWX: positions found. Check that your file matches the expected format.")
                        else:
                            _udir = user_data_dir(_email)
                            (_udir / "portfolio.json").unlink(missing_ok=True)
                            (_udir / "sold.json").unlink(missing_ok=True)
                            (_udir / "dividends_history.json").unlink(missing_ok=True)
                            save_portfolio(_imp_pf)
                            save_sold(_imp_sold)
                            save_div_hist(_imp_div)
                            st.success(f"Imported {len(_imp_pf)} open, {len(_imp_sold)} sold, {len(_imp_div)} dividend records.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Could not parse file: {e}")
                        st.code(traceback.format_exc())

    with tab_export:
        st.subheader("Excel export")
        st.caption("Human-readable workbook with positions, dividends, "
                   "sold history and watchlist. Useful for inspection or migration.")
        try:
            xls_bytes = export_excel()
            st.download_button(
                "⬇️ Download backup.xlsx",
                data=xls_bytes,
                file_name=backup_filename("xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except ValueError:
            st.info("Your portfolio is empty. Add positions in the Portfolio section first, then come back to export.")
        except Exception as e:
            st.error(f"Could not create Excel: {e}")

    if _is_admin:
      with tab_screener:
        st.subheader("Screener Exchanges")
        st.caption("Choose which exchanges are included in the screener and portfolio analysis.")
        _cur_settings = load_shared_settings()
        _cur_enabled  = set(_cur_settings.get("enabled_exchanges", ALL_EXCHANGES))
        _new_enabled: list[str] = []
        for _exkey, _exlabel in sorted(EXCHANGE_LABELS.items(), key=lambda x: x[1]):
            if st.checkbox(_exlabel, value=_exkey in _cur_enabled, key=f"scr_exch_{_exkey}"):
                _new_enabled.append(_exkey)
        if st.button("💾 Save", key="btn_save_screener_settings", type="primary"):
            if not _new_enabled:
                st.error("At least one exchange must be enabled.")
            else:
                _cur_settings["enabled_exchanges"] = _new_enabled
                save_shared_settings(_cur_settings)
                _load_all_screener_data.clear()
                st.success("Screener settings saved.")
                st.rerun()

    if _is_admin:
      with tab_backup:
        st.subheader("Encrypted backup (ZIP)")
        st.caption("Bundles all user data and the encryption key. "
                   "Required for a full restore on another machine.")
        try:
            zip_bytes = export_zip(_email)
            st.download_button(
                "⬇️ Download backup.zip",
                data=zip_bytes,
                file_name=backup_filename("zip"),
                mime="application/zip",
            )
        except Exception as e:
            st.error(f"Could not create ZIP: {e}")

        st.divider()
        st.subheader("Restore from ZIP")
        st.warning("Restoring will **overwrite** your current data. "
                   "Download a backup first if you want to keep it.", icon="⚠️")
        uploaded = st.file_uploader("Upload a backup ZIP", type="zip",
                                    key="backup_restore_upload")
        if uploaded:
            if st.button("Restore", type="primary", key="btn_restore"):
                try:
                    restored = import_zip(uploaded.read(), _email)
                    st.success(f"Restored: {', '.join(restored)}")
                    st.cache_data.clear()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — HELP
# ══════════════════════════════════════════════════════════════════════════════

if _page == "help":
    _render_help()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — PORTFOLIO RISK
# ══════════════════════════════════════════════════════════════════════════════

if _page == "risk":
    pf = load_portfolio()
    if pf is None or pf.empty:
        st.info("No portfolio loaded. Add positions in the Portfolio tab first.")
        st.stop()

    # ── Enrich portfolio with live prices, fair values, sector, country ───────
    with _loading_screen("Fetching live data for risk assessment…"):
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

    # ── Income portfolio toggle ───────────────────────────────────────────────
    _c_hdr, _c_tog = st.columns([5, 1])
    with _c_hdr:
        st.subheader("Portfolio Risk Assessment")
    with _c_tog:
        _income_portfolio = st.toggle("Income mode", value=False, key="risk_income_toggle",
                                      help="Elevates income risk weight in composite score")

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
        with st.spinner("Running risk assessment — fetching 5-year price history and computing metrics…"):
            try:
                _risk_report = _risk_module.assess_portfolio(pf, _risk_full_cache, _income_portfolio)
                st.session_state["_risk_report_cache"] = {"key": _risk_cache_key, "report": _risk_report}
            except Exception as _risk_err:
                st.error(f"Risk assessment failed: {_risk_err}")
                st.stop()

    r = _risk_report

    # ── Composite score banner ────────────────────────────────────────────────
    _score_color = {
        "Low risk":      "#22c55e",
        "Moderate risk": "#eab308",
        "Elevated risk": "#f97316",
        "High risk":     "#ef4444",
        "Critical risk": "#7f1d1d",
    }.get(r.composite.label, "#6b7280")

    st.markdown(f"""
<div style="display:flex;align-items:center;gap:1.5rem;padding:1rem 1.25rem;
            border-radius:12px;background:rgba(128,128,128,0.07);margin-bottom:1rem;">
  <div style="font-size:2.8rem;font-weight:900;color:{_score_color};line-height:1;">
    {r.composite.score:.0f}
  </div>
  <div>
    <div style="font-size:1.1rem;font-weight:700;color:{_score_color};">{r.composite.label}</div>
    <div style="font-size:0.82rem;opacity:0.6;margin-top:2px;">{r.composite.action}</div>
    <div style="font-size:0.75rem;opacity:0.4;margin-top:2px;">
      €{r.portfolio_value:,.0f} · {r.n_positions} positions ·
      updated {datetime.fromisoformat(r.generated_at).strftime("%H:%M UTC")}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Hard / soft triggers ──────────────────────────────────────────────────
    if r.rebalance.hard_triggers:
        for msg in r.rebalance.hard_triggers:
            st.error(f"🚨 {msg}", icon=None)
    elif not r.rebalance.soft_triggers:
        st.success("No rebalancing triggers detected.", icon="✅")

    if r.rebalance.soft_triggers:
        with st.expander(f"⚠️ {len(r.rebalance.soft_triggers)} soft trigger(s)", expanded=False):
            for msg in r.rebalance.soft_triggers:
                st.warning(msg, icon=None)

    st.divider()

    # ── Sub-score bar chart ───────────────────────────────────────────────────
    _sub_scores = r.composite.sub_scores
    _ss_fig = go.Figure(go.Bar(
        x=list(_sub_scores.keys()),
        y=list(_sub_scores.values()),
        marker_color=[
            "#22c55e" if v < 25 else "#eab308" if v < 50 else "#f97316" if v < 70 else "#ef4444"
            for v in _sub_scores.values()
        ],
        text=[f"{v:.0f}" for v in _sub_scores.values()],
        textposition="outside",
    ))
    _ss_fig.update_layout(
        height=220, margin=dict(t=20, b=0, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(range=[0, 115], showgrid=False, visible=False),
        xaxis=dict(showgrid=False),
        font=dict(color="white"),
        showlegend=False,
    )
    st.plotly_chart(_ss_fig, use_container_width=True)

    # ── Detail tabs ───────────────────────────────────────────────────────────
    (_t_pos, _t_conc, _t_quant, _t_factor,
     _t_income, _t_stress, _t_mc, _t_rebal) = st.tabs([
        "Positions", "Concentration", "Volatility & VaR",
        "Factor Exposure", "Income Risk", "Stress Tests",
        "Monte Carlo", "Rebalancing",
    ])

    # ── Tab: Positions ────────────────────────────────────────────────────────
    with _t_pos:
        with st.expander("ℹ️ How to read this tab", expanded=False):
            st.markdown(
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
                "Weight":          f"{p.weight:.1%}",
                "Beta":            f"{p.beta:.2f}" if p.beta is not None else "—",
                "VaR 95% 1d":      f"€{p.var_95_1d_eur:,.0f}" if p.var_95_1d_eur else "—",
                "MoS":             f"{p.mos:.1%}" if p.mos is not None else "—",
                "Valuation":       p.valuation_flag,
                "Div":             p.div_sustainability or "—",
                "Fin Health":      f"{p.financial_health:.1f}/10",
                "Earn Quality":    f"{p.earnings_quality:.1f}/10",
                "Risk Rating":     p.rating,
            })
        _pos_df = pd.DataFrame(_pos_rows)
        _row_h = 35
        st.dataframe(
            _pos_df,
            hide_index=True,
            use_container_width=True,
            height=35 + min(len(_pos_df), 20) * _row_h,
            column_config={
                "Company":      st.column_config.TextColumn("Company",     pinned=True,
                                    help="Company name"),
                "Ticker":       st.column_config.TextColumn("Ticker",
                                    help="Exchange ticker symbol"),
                "Weight":       st.column_config.TextColumn("Weight",
                                    help="Position value as a % of total portfolio. >10% = concentrated; >15% triggers a hard flag."),
                "Beta":         st.column_config.TextColumn("Beta",
                                    help="Market sensitivity (regression vs index). >1 = amplifies market moves; <1 = more defensive. >1.3 adds to risk rating."),
                "VaR 95% 1d":   st.column_config.TextColumn("VaR 95% 1d",
                                    help="Maximum expected 1-day loss for this position at 95% confidence. Estimated as position value × |beta| × market daily vol × 1.645."),
                "MoS":          st.column_config.TextColumn("MoS",
                                    help="Margin of Safety = (Fair Value − Price) / Fair Value. Positive = undervalued; negative = overvalued vs the UV model estimate."),
                "Valuation":    st.column_config.TextColumn("Valuation",
                                    help="Undervalued (MoS >10%) · Fairly Valued (MoS 0–10%) · Overvalued (MoS <0%). Overvalued positions add to the risk rating."),
                "Div":          st.column_config.TextColumn("Div",
                                    help="Dividend sustainability flag from the UV screener. OK = all payout checks pass. At Risk = payout ratio >90%, cash payout >80%, or coverage <1.2×."),
                "Fin Health":   st.column_config.TextColumn("Fin Health",
                                    help="Financial health score 0–10 (higher = healthier). Average of D/E ratio, current ratio, and interest coverage. <5 adds to risk rating."),
                "Earn Quality": st.column_config.TextColumn("Earn Quality",
                                    help="Earnings quality score 0–10. Measures FCF vs net income — high accruals (earnings without cash backing) score lower. <3 adds to risk rating."),
                "Risk Rating":  st.column_config.TextColumn("Risk Rating",
                                    help="Aggregated position risk: Low · Medium · High · Critical. Determined by the number of risk factors breached across weight, beta, valuation, financial health and earnings quality."),
            },
        )

    # ── Tab: Concentration ────────────────────────────────────────────────────
    with _t_conc:
        with st.expander("ℹ️ How to read this tab", expanded=False):
            st.markdown(
                "Concentration risk measures how much of the portfolio depends on a small number "
                "of positions, sectors, or geographies. The **HHI** (Herfindahl-Hirschman Index) "
                "is the sum of squared weights — closer to 0 means well spread, above 0.18 is "
                "highly concentrated. Flags trigger at >15% single position, >30% single sector, "
                "or >60% single country. Dividend HHI applies the same logic to income streams."
            )
        c = r.concentration
        _cc1, _cc2, _cc3 = st.columns(3)
        _cc1.metric("HHI", f"{c.hhi:.3f}", help=c.hhi_label)
        _cc2.metric("Top-1 weight", f"{c.top1_weight:.1%}", delta="⚠️ Flag" if c.top1_flag else "✓ OK",
                    delta_color="inverse" if c.top1_flag else "off")
        _cc3.metric("Top-3 weight", f"{c.top3_weight:.1%}", delta="⚠️ Flag" if c.top3_flag else "✓ OK",
                    delta_color="inverse" if c.top3_flag else "off")

        st.caption(f"**Concentration:** {c.hhi_label}  |  Top-5: {c.top5_weight:.1%}")

        _conc_c1, _conc_c2 = st.columns(2)
        with _conc_c1:
            st.markdown("**Sector weights**")
            if c.sector_weights:
                _sec_fig = go.Figure(go.Bar(
                    x=list(c.sector_weights.keys()),
                    y=[v * 100 for v in c.sector_weights.values()],
                    marker_color=["#ef4444" if v > 0.30 else "#4f8ef7" for v in c.sector_weights.values()],
                    text=[f"{v:.0%}" for v in c.sector_weights.values()],
                    textposition="outside",
                ))
                _sec_fig.add_hline(y=30, line_dash="dot", line_color="orange",
                                   annotation_text="30% threshold", annotation_position="top right")
                _sec_fig.update_layout(
                    height=260, margin=dict(t=20, b=60, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(title="Weight %", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
                    xaxis=dict(tickangle=-30),
                    font=dict(color="white"), showlegend=False,
                )
                st.plotly_chart(_sec_fig, use_container_width=True)
            if c.sector_flag:
                st.warning(f"Sector concentration: {c.largest_sector} at {c.sector_weights.get(c.largest_sector or '', 0):.0%}")

        with _conc_c2:
            st.markdown("**Geographic weights**")
            if c.geo_weights:
                _geo_fig = go.Figure(go.Pie(
                    labels=list(c.geo_weights.keys()),
                    values=list(c.geo_weights.values()),
                    hole=0.4,
                    textinfo="label+percent",
                ))
                _geo_fig.update_layout(
                    height=260, margin=dict(t=10, b=10, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"), showlegend=False,
                )
                st.plotly_chart(_geo_fig, use_container_width=True)
            if c.geo_flag:
                st.warning(f"Geographic concentration: {c.largest_geo} at {c.geo_weights.get(c.largest_geo or '', 0):.0%}")

        if c.div_hhi is not None:
            st.caption(f"Dividend income HHI: {c.div_hhi:.3f} | Top-3 income share: {c.div_top3_pct:.0%}"
                       + (" ⚠️" if c.income_concentration_flag else ""))

    # ── Tab: Volatility & VaR ─────────────────────────────────────────────────
    with _t_quant:
        with st.expander("ℹ️ How to read this tab", expanded=False):
            st.markdown(
                "**Beta** measures overall market sensitivity — above 1.2 means the portfolio "
                "amplifies market swings, below 0.8 is defensive. **Annual Vol** is the standard "
                "deviation of daily returns scaled to a year; above 20% is high. "
                "**VaR** is the maximum expected 1-day loss at a given confidence level — "
                "e.g. a 95% VaR of €500 means only 1 day in 20 should lose more than that. "
                "**CVaR** (Expected Shortfall) is the *average* loss on those worst days, capturing "
                "tail risk beyond VaR. **MDD** is the largest peak-to-trough drawdown observed in the "
                "historical window. The correlation heatmap shows how positions move together — "
                "pairs above 0.80 provide little diversification benefit."
            )
        q = r.quant
        _qc1, _qc2, _qc3, _qc4 = st.columns(4)
        _qc1.metric("Portfolio Beta", f"{q.portfolio_beta:.2f}", help=q.beta_label)
        _qc2.metric("Annual Vol",
                    f"{q.volatility_annual:.1%}" if q.volatility_annual else "N/A",
                    help=q.volatility_label)
        _qc3.metric("Sharpe",  f"{q.sharpe:.2f}"  if q.sharpe  else "N/A", help=q.ratio_label)
        _qc4.metric("Sortino", f"{q.sortino:.2f}" if q.sortino else "N/A")

        st.divider()

        _vc1, _vc2, _vc3 = st.columns(3)
        _vc1.metric("VaR 95% (1d)", f"€{q.var_95_1d_eur:,.0f}" if q.var_95_1d_eur else "N/A",
                    help="Maximum expected 1-day loss at 95% confidence (historical simulation)")
        _vc2.metric("VaR 99% (1d)", f"€{q.var_99_1d_eur:,.0f}" if q.var_99_1d_eur else "N/A")
        _vc3.metric("CVaR 95% (1d)", f"€{q.cvar_95_1d_eur:,.0f}" if q.cvar_95_1d_eur else "N/A",
                    help="Expected loss in the worst 5% of scenarios (Expected Shortfall)")

        st.divider()

        _mc1, _mc2, _mc3 = st.columns(3)
        _mc1.metric("MDD 1y", f"{q.mdd_1y:.1%}" if q.mdd_1y else "N/A",
                    help=f"Max drawdown over last 12 months — {q.mdd_label}")
        _mc2.metric("MDD 3y", f"{q.mdd_3y:.1%}" if q.mdd_3y else "N/A")
        _mc3.metric("MDD 5y", f"{q.mdd_5y:.1%}" if q.mdd_5y else "N/A")

        if not q.returns_available:
            st.info("Historical price data unavailable — quantitative metrics use beta-proxy estimates.")

        if q.corr_matrix is not None and len(q.corr_matrix) > 1:
            st.divider()
            st.markdown("**Return correlation matrix (last 252 trading days)**")
            _corr = q.corr_matrix.round(2)
            _heat = go.Figure(go.Heatmap(
                z=_corr.values,
                x=list(_corr.columns),
                y=list(_corr.index),
                colorscale="RdBu_r",
                zmin=-1, zmax=1,
                text=_corr.values.round(2),
                texttemplate="%{text}",
                showscale=True,
            ))
            _heat.update_layout(
                height=max(300, len(_corr) * 40 + 80),
                margin=dict(t=20, b=60, l=80, r=20),
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
                xaxis=dict(tickangle=-30),
            )
            st.plotly_chart(_heat, use_container_width=True)
            if q.high_corr_pairs:
                _pairs_str = ", ".join(f"**{a}/{b}** ({c:.2f})" for a, b, c in q.high_corr_pairs)
                st.warning(f"High-correlation pairs (>0.80): {_pairs_str} — limited diversification")
            if q.effective_diversification is not None:
                st.caption(f"Effective diversification score: {q.effective_diversification:.2f} "
                           f"(1 − avg pairwise correlation)")

    # ── Tab: Factor Exposure ──────────────────────────────────────────────────
    with _t_factor:
        with st.expander("ℹ️ How to read this tab", expanded=False):
            st.markdown(
                "Factor analysis decomposes portfolio returns into known systematic risk factors "
                "using the **Fama-French 5-factor model** (+ momentum). Each bar is a *factor loading* — "
                "how much the portfolio moves per unit of that factor's return. "
                "A loading above **±1.5** signals a concentrated factor bet. "
                "**R²** shows what fraction of return variance the model explains; above 0.6 means "
                "the portfolio is factor-dominated. **Alpha** is the annualised return not explained "
                "by any factor — positive alpha suggests genuine stock-picking skill, negative suggests "
                "the portfolio underperforms its factor exposures.  \n\n"
                "Factors: **Mkt-RF** market premium · **SMB** small vs large cap · "
                "**HML** value vs growth · **RMW** high vs low profitability · "
                "**CMA** conservative vs aggressive investment · **WML** momentum."
            )
        f = r.factor
        if not f.available:
            st.info("Factor analysis unavailable. " + (f.flags[0] if f.flags else ""))
            st.caption("Install `pandas-datareader` and ensure internet access to Fama-French data library.")
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
                    marker_color=["#ef4444" if abs(v) > 1.5 else "#4f8ef7" for v in f.loadings.values()],
                    text=[f"{v:+.2f}" for v in f.loadings.values()],
                    textposition="outside",
                ))
                _fac_fig.add_hline(y=1.5,  line_dash="dot", line_color="orange")
                _fac_fig.add_hline(y=-1.5, line_dash="dot", line_color="orange")
                _fac_fig.update_layout(
                    height=280, margin=dict(t=30, b=20, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(title="Factor Loading", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
                    font=dict(color="white"), showlegend=False,
                )
                st.plotly_chart(_fac_fig, use_container_width=True)

            if f.flags:
                for _msg in f.flags:
                    st.warning(_msg)

            st.caption("Mkt-RF: market | SMB: small vs large | HML: value vs growth | "
                       "RMW: profitability | CMA: investment | WML: momentum (if available). "
                       "Red bars = loading >1.5 — concentrated factor bet. "
                       "Dashed lines = ±1.5 threshold.")

    # ── Tab: Income Risk ──────────────────────────────────────────────────────
    with _t_income:
        with st.expander("ℹ️ How to read this tab", expanded=False):
            st.markdown(
                "Income risk measures how vulnerable the portfolio's dividend stream is. "
                "**Portfolio Yield** is total expected annual dividends divided by current portfolio value. "
                "**Weighted DGR** (Dividend Growth Rate) is the income-weighted average of each payer's "
                "earnings growth — a DGR below inflation (~2.5%) means purchasing power of income erodes. "
                "The **top-3 cut scenario** simulates the income impact if the three largest dividend "
                "payers each cut their dividend by 50% — a standard stress test for income concentration. "
                "Positions flagged for sustainability have at least one of: payout ratio >80%, "
                "cash payout ratio >80%, or dividend coverage ratio <1.2×."
            )
        inc = r.income
        _ic1, _ic2, _ic3 = st.columns(3)
        _ic1.metric("Portfolio Yield", f"{inc.portfolio_yield:.2%}")
        _ic2.metric("Annual Income", f"€{inc.total_annual_income:,.0f}")
        _ic3.metric("Weighted DGR",
                    f"{inc.weighted_dgr:.1%}" if inc.weighted_dgr is not None else "N/A",
                    help="Income-weighted dividend growth rate (earnings growth proxy)")

        st.divider()

        _ic4, _ic5 = st.columns(2)
        _ic4.metric("Top-3 cut scenario (50%)",
                    f"€{inc.top3_cut_eur:,.0f}" if inc.top3_cut_eur else "N/A",
                    help="Income at risk if top-3 dividend payers cut by 50%")
        _ic5.metric("Income at risk",
                    f"{inc.top3_cut_pct:.1%}" if inc.top3_cut_pct else "N/A",
                    delta="⚠️ Flag" if inc.income_concentration_flag else "✓ OK",
                    delta_color="inverse" if inc.income_concentration_flag else "off")

        if inc.top3_income_shares:
            st.markdown("**Top income contributors**")
            _inc_rows = [{"Ticker": t, "Share of income": f"{sh:.1%}"}
                         for t, sh in inc.top3_income_shares]
            st.dataframe(pd.DataFrame(_inc_rows), hide_index=True, use_container_width=False,
                         column_config={
                             "Ticker":         st.column_config.TextColumn("Ticker",
                                                   help="Exchange ticker symbol of the dividend payer"),
                             "Share of income": st.column_config.TextColumn("Share of income",
                                                   help="This payer's expected annual dividend as a fraction of total portfolio income. High concentration here amplifies the impact of a dividend cut."),
                         })

        if inc.flagged_payers:
            st.warning(f"Sustainability concerns ({inc.flagged_income_pct:.0%} of income): "
                       + ", ".join(inc.flagged_payers))

    # ── Tab: Stress Tests ─────────────────────────────────────────────────────
    with _t_stress:
        with st.expander("ℹ️ How to read this tab", expanded=False):
            st.markdown(
                "Stress tests show how the portfolio might perform under adverse conditions.  \n\n"
                "**Historical scenarios** replay four real market crises. Portfolio drawdown is "
                "estimated as *portfolio beta × index drawdown* — a beta of 0.8 during a −50% "
                "crash implies a −40% portfolio loss. This is an approximation; actual losses "
                "depend on individual stock behaviour during the specific period.  \n\n"
                "**Hypothetical scenarios** apply targeted shocks: the rate-rise scenario uses "
                "each stock's P/E as a duration proxy (high P/E = more sensitive to higher rates); "
                "the recession scenario applies a 25% earnings cut to cyclical sectors and 10% to "
                "defensives; the sector crash applies a −40% shock to the largest sector holding; "
                "the credit crunch penalises high-leverage positions proportionally to D/E ratio."
            )
        st.markdown("**Historical scenarios** *(beta-adjusted approximation)*")
        _hist_rows = [{
            "Scenario":          s.name,
            "Period":            s.period,
            "Index drawdown":    f"{s.index_drawdown:.0%}" if s.index_drawdown else "—",
            "Est. portfolio DD": f"{s.portfolio_drawdown:.1%}" if s.portfolio_drawdown else "—",
            "Est. value loss":   f"€{s.portfolio_value_loss:,.0f}" if s.portfolio_value_loss else "—",
        } for s in r.stress.historical]
        st.dataframe(pd.DataFrame(_hist_rows), hide_index=True, use_container_width=True,
            column_config={
                "Scenario":          st.column_config.TextColumn("Scenario",
                                         help="Name of the historical market crisis"),
                "Period":            st.column_config.TextColumn("Period",
                                         help="Approximate date range of the crisis"),
                "Index drawdown":    st.column_config.TextColumn("Index drawdown",
                                         help="Actual S&P 500 peak-to-trough drawdown during the crisis"),
                "Est. portfolio DD": st.column_config.TextColumn("Est. portfolio DD",
                                         help="Estimated portfolio drawdown = portfolio beta × index drawdown"),
                "Est. value loss":   st.column_config.TextColumn("Est. value loss",
                                         help="Estimated euro loss at current portfolio value"),
            })

        st.caption("Drawdown estimated as portfolio beta × index drawdown. "
                   "For tickers with ≥5 years of history, actual returns are used where available.")

        st.divider()
        st.markdown("**Hypothetical factor scenarios**")
        _factor_rows = [{
            "Scenario":           s["name"],
            "Description":        s["description"],
            "Est. portfolio loss": f"{s['estimated_portfolio_impact']:.1%}",
            "Est. value loss €":  f"€{s['estimated_loss_eur']:,.0f}",
            **({"Note": s["note"]} if "note" in s else {}),
        } for s in r.stress.factor_scenarios]
        st.dataframe(pd.DataFrame(_factor_rows), hide_index=True, use_container_width=True,
            column_config={
                "Scenario":            st.column_config.TextColumn("Scenario",
                                           help="Name of the hypothetical shock"),
                "Description":         st.column_config.TextColumn("Description",
                                           help="How the shock is modelled"),
                "Est. portfolio loss":  st.column_config.TextColumn("Est. portfolio loss",
                                           help="Estimated portfolio return impact as a percentage"),
                "Est. value loss €":   st.column_config.TextColumn("Est. value loss €",
                                           help="Estimated euro loss at current portfolio value"),
                "Note":                st.column_config.TextColumn("Note",
                                           help="Additional context for this scenario"),
            })

    # ── Tab: Monte Carlo ──────────────────────────────────────────────────────
    with _t_mc:
        with st.expander("ℹ️ How to read this tab", expanded=False):
            st.markdown(
                "Monte Carlo simulation runs **10,000 random return paths** over 1, 3, and 5 years, "
                "drawing daily returns from the historical return distribution of the portfolio. "
                "The fan chart shows the range of outcomes: the dark line is the median path, "
                "the inner band covers the 25th–75th percentile (50% of paths), and the outer "
                "band covers the 5th–95th percentile (90% of paths).  \n\n"
                "**P5** is the worst-case outcome at 5% probability — what the portfolio could be "
                "worth in a persistently bad scenario. **P(loss)** is the fraction of simulated "
                "paths that end below the starting value. When historical price data is unavailable, "
                "returns are estimated from portfolio beta and a 5% market risk premium."
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

        _build_fan(_mcs, "#4f8ef7", "portfolio")
        _fan_fig.add_hline(y=_pv, line_dash="dot", line_color="rgba(255,255,255,0.3)",
                           annotation_text="Current value", annotation_position="bottom right")
        _fan_fig.update_layout(
            height=360, margin=dict(t=20, b=40, l=60, r=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="Portfolio value (€)", tickprefix="€",
                       tickformat=",.0f", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            xaxis=dict(title="Years", tickvals=[0, 1, 3, 5]),
            font=dict(color="white"), legend=dict(x=0.02, y=0.98),
        )
        st.plotly_chart(_fan_fig, use_container_width=True)

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
        st.dataframe(_mc_tbl, hide_index=True, use_container_width=False,
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

    # ── Tab: Rebalancing ──────────────────────────────────────────────────────
    with _t_rebal:
        with st.expander("ℹ️ How to read this tab", expanded=False):
            st.markdown(
                "Rebalancing signals are split into two tiers:  \n\n"
                "**Hard triggers** require immediate action — they indicate a threshold breach "
                "that materially increases portfolio risk (e.g. single position >20%, beta >1.5, "
                "99% VaR exceeding 3% of portfolio, or a Critical-rated position).  \n\n"
                "**Soft triggers** are advisory — worth reviewing and planning around, but not "
                "requiring same-day action (e.g. HHI drift, sector overweight, Sharpe below 1.0, "
                "or a High-rated position).  \n\n"
                "The **actions table** maps each issue to a concrete next step. Prioritise "
                "hard-trigger actions first, then work through soft triggers in order of their "
                "impact on the composite risk score."
            )
        if r.rebalance.actions:
            _act_df = pd.DataFrame(r.rebalance.actions)
            st.dataframe(
                _act_df,
                hide_index=True,
                use_container_width=True,
                height=35 + min(len(_act_df), 15) * 40,
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker / Scope",
                                  help="The position or scope (e.g. 'Portfolio', a sector name, or a ticker) this action applies to"),
                    "issue":  st.column_config.TextColumn("Issue",
                                  help="The specific risk threshold or flag that triggered this action"),
                    "action": st.column_config.TextColumn("Recommended Action",
                                  help="Suggested rebalancing step to address the issue"),
                },
            )
        else:
            st.success("No immediate rebalancing actions required.")

        st.divider()

        if r.rebalance.hard_triggers:
            st.markdown("**Hard triggers** *(act immediately)*")
            for msg in r.rebalance.hard_triggers:
                st.error(f"🚨 {msg}", icon=None)

        if r.rebalance.soft_triggers:
            st.markdown("**Soft triggers** *(review and plan)*")
            for msg in r.rebalance.soft_triggers:
                st.warning(f"⚠️ {msg}", icon=None)

        st.divider()
        st.caption(f"Risk report generated at {datetime.fromisoformat(r.generated_at).strftime('%Y-%m-%d %H:%M UTC')}. "
                   "Refreshes automatically after 1 hour or when portfolio changes.")
        if st.button("🔄 Refresh risk report", key="risk_refresh_btn"):
            st.session_state.pop("_risk_report_cache", None)
            st.rerun()

