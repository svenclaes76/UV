"""Streamlit web app — Euronext Brussels value screener + portfolio tracker."""

# ── Column help texts (shown as header tooltips and in the help dialog) ───────
COLUMN_HELP = {
    # ── Core ──────────────────────────────────────────────────────────────────
    "★":             "Watchlist — check to add this stock to your personal watchlist.",
    "Company":       "Full company name as reported by the exchange.",
    "Ticker":        "Exchange ticker symbol on Euronext Brussels (.BR suffix).",
    "Price":           "Current market price in EUR.",
    "💎 UV":           (
        "Weighted composite intrinsic value estimate from up to 5 models: "
        "Graham Number, PE Fair Value, EPV, DDM (single + multi-stage), and Analyst Target. "
        "Weights auto-adjust: DDM weight is zero for non-dividend payers or payout > 90%."
    ),
    "Analyst Target": "Mean analyst consensus price target from Wall Street analysts covering the stock.",
    "MoS %":          (
        "Margin of Safety = (Fair Value − Price) / Fair Value. "
        "Positive = stock trades below estimated fair value. "
        "The algorithm requires MoS > 20–30% before a stock enters the buy zone."
    ),
    "TER %":         (
        "Total Expected Return = Capital Gain % + Forward Dividend Yield + Expected DGR. "
        "A complete 1-year return estimate. > 15% = attractive, 8–15% = acceptable, < 8% = unattractive."
    ),
    "Score":         (
        "Composite score 0–100 with decision signal. "
        "🟢 Strong Buy (> 70) · 🟡 Monitor (40–70) · 🔴 Avoid (< 40). "
        "Formula: 30% × MoS rank + 18% × (100 − Risk rank) + 22% × Quality rank + 15% × Momentum rank + 15% × Dividend rank. "
        "Hard veto rules force Avoid regardless of score: D/E > 5×, negative FCF, or dividend coverage < 1.0× with sustainability flag."
    ),
    # ── Valuation models ──────────────────────────────────────────────────────
    "Graham #":      (
        "Graham Number = √(22.5 × EPS × BVPS). "
        "A conservative deep-value floor. Price below this level suggests potential significant undervaluation."
    ),
    "PE Fair Val":   "PE Fair Value = EPS × 15. Graham's assumed fair multiple for a no-growth company.",
    "EPV":           (
        "Earnings Power Value = EBIT × (1 − tax rate) / WACC, scaled to price via the EV ratio. "
        "A zero-growth downside anchor — what the business is worth as a going concern with no expansion."
    ),
    "DDM (1-stage)": (
        "Single-stage Gordon Growth DDM: P = D₁ / (r − g). "
        "Uses earnings growth as DGR proxy, capped at 5%. Best for stable, mature dividend payers."
    ),
    "DDM (2-stage)": (
        "Two-stage DDM: 5-year high-growth phase (using earnings growth as proxy) "
        "followed by a 2% stable terminal phase. Better captures dividend-growing companies."
    ),
    # ── Risk & size ───────────────────────────────────────────────────────────
    "Risk Score":    (
        "Composite risk level 0–10 (higher = riskier). "
        "Average of 5 dimensions: financial health (D/E, current ratio, interest coverage), "
        "earnings quality (FCF vs net income), market risk (beta), dividend risk (payout, coverage), "
        "and liquidity (average daily volume). Then inverted so 0 = safest."
    ),
    "Mkt Cap":       "Market capitalisation = price × shares outstanding.",
    "Beta":          "Market sensitivity vs index. Beta > 1 = more volatile; < 1 = more defensive.",
    "Debt/Equity":   (
        "Total debt / equity (yfinance reports as ×100, so 150 = 1.5×). "
        "Lower = less leverage. Hard veto triggers at > 5×."
    ),
    # ── Multiples ─────────────────────────────────────────────────────────────
    "P/E":           "Price-to-Earnings. Lower generally indicates cheaper valuation — compare within sector.",
    "P/B":           "Price-to-Book. < 1 may signal undervaluation, especially for banks and asset-heavy companies.",
    "EV/EBITDA":     "Enterprise Value / EBITDA. Capital-structure-neutral multiple. Lower = cheaper.",
    # ── Quality ───────────────────────────────────────────────────────────────
    "ROE %":         "Return on Equity — net income as % of shareholders' equity. > 15% is generally strong.",
    "ROA %":         "Return on Assets — net income as % of total assets. Measures asset utilisation efficiency.",
    "Op Margin %":   "Operating margin — operating income as % of revenue. Core profitability before interest and tax.",
    "FCF Yield %":   "Free Cash Flow Yield = FCF / Market Cap. > 5% is typically attractive.",
    # ── Growth ────────────────────────────────────────────────────────────────
    "Rev Growth %":  "Year-over-year revenue growth. Positive = growing top line.",
    "EPS Growth %":  (
        "Year-over-year earnings-per-share growth. "
        "Also used as a proxy for dividend growth rate (DGR) where direct DPS history is unavailable."
    ),
    # ── Dividends ─────────────────────────────────────────────────────────────
    "Div Yield":     "Trailing dividend yield = annual DPS / price. Higher yield vs 5-year average may indicate undervaluation.",
    "5yr Avg Yield": "5-year average dividend yield for this stock. Used as a benchmark: current yield above this suggests the stock may be cheap relative to its own history.",
    "Payout Ratio":  "DPS / EPS. 30–70% = sustainable; > 85% = at risk of a cut.",
    "Cash Payout":   "Cash payout ratio = (DPS × shares) / FCF. Should be < 80% to confirm free cash flow supports the dividend.",
    "Div Coverage":  "Dividend coverage ratio = EPS / DPS. > 1.5× is safe; < 1.2× triggers a sustainability flag.",
    "Div Flag":      (
        "Dividend sustainability assessment. "
        "✅ OK = all payout checks pass. "
        "⚠️ At Risk = one or more thresholds breached: payout > 90%, cash payout > 80%, or coverage < 1.2×. "
        "Flagged stocks require a higher Margin of Safety (+5–10 pp) to compensate."
    ),
}

import math
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf
import streamlit as st
import streamlit.components.v1 as st_components
from streamlit_autorefresh import st_autorefresh

from prices import fetch_prices

from fetch_tickers import fetch_brussels_tickers, fetch_amsterdam_tickers
from screener import CACHE_FILE, CACHE_TTL_HOURS, _load_cache, run_screener
from portfolio import (parse_excel, save_portfolio, save_sold, save_div_hist,
                       load_portfolio, load_sold, load_div_hist, portfolio_exists,
                       PORTFOLIO_FILE, save_watchlist, load_watchlist)
from auth import register, login, verify_token, list_users, set_role, delete_user, ROLES

def _render_admin_users():
    """User management UI — rendered inside the Settings page."""
    users = list_users()
    if not users:
        st.info("No users found.")
    else:
        for u in users:
            col_email, col_role, col_save, col_del = st.columns([3, 2, 1, 1])
            col_email.markdown(f"**{u['email']}**  \n<small>{u['created_at'][:10]}</small>",
                               unsafe_allow_html=True)
            new_role = col_role.selectbox(
                "Role",
                options=list(ROLES),
                index=list(ROLES).index(u["role"]),
                key=f"adm_role_{u['email']}",
                label_visibility="collapsed",
            )
            if col_save.button("Save", key=f"adm_save_{u['email']}", use_container_width=True):
                ok, msg = set_role(u["email"], new_role)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            current_email = st.session_state.get("user_email", "")
            if u["email"] != current_email:
                if col_del.button("🗑️", key=f"adm_del_{u['email']}", use_container_width=True,
                                  help=f"Delete {u['email']}"):
                    ok, msg = delete_user(u["email"])
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                col_del.markdown("&nbsp;", unsafe_allow_html=True)

    st.divider()
    st.subheader("Create account")
    with st.form("adm_create_user"):
        new_email    = st.text_input("Email")
        new_password = st.text_input("Password", type="password")
        new_role_sel = st.selectbox("Role", options=list(ROLES))
        if st.form_submit_button("Create", use_container_width=True):
            ok, msg = register(new_email, new_password, role=new_role_sel)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


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


def _bust_cache() -> None:
    """Wipe the screener disk cache, clear Streamlit's data cache, and rerun."""
    try:
        CACHE_FILE.write_text("{}", encoding="utf-8")
    except OSError:
        pass
    st.cache_data.clear()
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
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"€{v/1e9:.1f}B" if v >= 1e9 else f"€{v/1e6:.0f}M"


def _fmt_div_flag(v) -> str:
    return {"At Risk": "⚠️ At Risk", "OK": "✅ OK", "": "—"}.get(str(v) if pd.notna(v) else "", "—")


@st.cache_data(show_spinner=False)
def load_screener_data() -> pd.DataFrame:
    stocks = fetch_brussels_tickers()
    return run_screener(stocks)


@st.cache_data(show_spinner=False)
def load_amsterdam_screener_data() -> pd.DataFrame:
    stocks = fetch_amsterdam_tickers()
    return run_screener(stocks)


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


@st.cache_data(show_spinner=False, ttl=120)
def _fetch_prices_cached(tickers: tuple) -> dict:
    """Batch price feed — one HTTP call for all tickers, refreshed every 2 min."""
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
    }
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            fv   = _compute_fair_values(info)
            result[t] = {
                "analyst_target": info.get("targetMeanPrice"),
                "div_rate":       info.get("trailingAnnualDividendRate") or 0,
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
  .uv-nav-utils { position: fixed; bottom: 62px; left: 0; width: 250px; padding: 0 16px 4px; box-sizing: border-box; }
  .uv-bottom    {
    position: fixed; bottom: 0; left: 0; width: 250px; padding: 8px 16px 15px;
    background: var(--sidebar-background-color, var(--secondary-background-color));
    border-top: 1px solid rgba(128,128,128,0.12); box-sizing: border-box;
  }
  .uv-bottom-email { font-size: 0.7rem; color: var(--text-color); opacity: 0.45; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }
  .uv-role-badge   { display: inline-block; background: rgba(128,128,128,0.12); border-radius: 4px; padding: 1px 6px; font-size: 0.65rem; color: var(--text-color); opacity: 0.5; margin-right: 5px; vertical-align: middle; }
  .uv-logout       { font-size: 0.75rem; color: var(--text-color); opacity: 0.4; text-decoration: none !important; transition: opacity 0.12s; }
  .uv-logout:hover { opacity: 0.8; }
</style>
""", unsafe_allow_html=True)

# ── Authentication gate ───────────────────────────────────────────────────────

# Restore JWT from localStorage via _tok query param (set by nav links)
_tok_param = st.query_params.get("_tok", "")
if _tok_param:
    if not st.session_state.get("jwt_token"):
        _email_check, _role_check = verify_token(_tok_param)
        if _email_check:
            st.session_state["jwt_token"]  = _tok_param
            st.session_state["user_email"] = _email_check
            st.session_state["user_role"]  = _role_check
    # Remove _tok silently without triggering a rerun — just update the browser URL via JS
    del st.query_params["_tok"]

# Inject JS that reads localStorage and, if a token is stored but no active
# session exists, sets ?_tok= and reloads — bridges hard page reloads.
_has_session = bool(st.session_state.get("jwt_token"))
if not _has_session:
    st_components.html("""
<script>
(function(){
  var tok = localStorage.getItem('uv_jwt');
  if (!tok) return;
  var url = new URL(window.parent.location.href);
  if (url.searchParams.get('_tok')) return;  // already set, avoid loop
  url.searchParams.set('_tok', tok);
  window.parent.location.replace(url.toString());
})();
</script>
""", height=0)

def _auth_wall():
    """Show login/sign-up form and halt execution if not authenticated."""
    token = st.session_state.get("jwt_token")
    if token:
        email, role = verify_token(token)
        if email:
            st.session_state["user_email"] = email
            st.session_state["user_role"]  = role
            return  # already logged in

    st.markdown("""
    <style>
      .login-wrap { max-width:320px; margin: 60px auto 0; }
    </style>
    <div class="login-wrap">
      <div style="text-align:center;margin-bottom:32px;">
        <div style="font-size:2rem;font-weight:800;margin-bottom:4px;">💎 UV</div>
        <div style="color:#888;white-space:nowrap;">Undervalued · Portfolio tracker &amp; screener</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 0.78, 1])
    with col:
        email    = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Log in", use_container_width=True, type="primary"):
            ok, result = login(email, password)
            if ok:
                _, role = verify_token(result)
                st.session_state["jwt_token"]  = result
                st.session_state["user_email"] = email.strip().lower()
                st.session_state["user_role"]  = role
                st_components.html(f"<script>localStorage.setItem('uv_jwt',{repr(result)});</script>", height=0)
                st.rerun()
            else:
                st.error(result)

    st.stop()


_auth_wall()

_current_role = st.session_state.get("user_role", "normal")
_is_admin = _current_role == "administrator"
_is_demo  = _current_role == "demo"
_email    = st.session_state.get("user_email", "")

# Page routing via query params (default: screener)
_page = st.query_params.get("page", "screener")
if _is_demo and _page == "portfolio":
    _page = "screener"

# ── Sidebar (pure HTML — no Streamlit widgets) ────────────────────────────────
# Active classes are applied by JS (uvSetActive) so sidebar HTML is identical on
# every rerun — React makes no DOM changes → zero sidebar flash.

# _tok_qs embeds the JWT into fallback hrefs so the session survives a hard reload
_jwt    = st.session_state.get("jwt_token", "")
_tok_qs = f"&_tok={_jwt}" if _jwt else ""


def _nav_link(page: str, icon: str, label: str, tok_qs: str,
              extra_class: str = "uv-nav-item") -> str:
    """Return an HTML nav anchor that triggers uvNav() (WebSocket) with an href fallback."""
    href = f"?page={page}{tok_qs}"
    return (
        f'<a href="{href}" target="_self" data-uv-page="{page}" '
        f'onclick="if(typeof uvNav===\'function\'){{uvNav(\'{page}\');return false;}}" '
        f'class="{extra_class}">'
        f'<span class="uv-nav-icon">{icon}</span>{label}</a>'
    )


_portfolio_item = _nav_link("portfolio", "📁", "Portfolio", _tok_qs) if not _is_demo else ""
_admin_item     = _nav_link("settings",  "⚙️", "Settings",  _tok_qs) if _is_admin else ""

_role_label = {"administrator": "🔑", "demo": "demo"}.get(_current_role, "")
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
  {_nav_link("screener",  "🔍", "Screener",  _tok_qs)}
  {_portfolio_item}
</nav>
<div class="uv-nav-utils">
  <hr class="uv-nav-sep" style="margin-bottom:6px;">
  <nav class="uv-nav">
    {_admin_item}
    {_nav_link("help", "❓", "Help", _tok_qs)}
  </nav>
</div>
<div class="uv-bottom">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
    <div class="uv-bottom-email" style="margin:0;min-width:0;">{_role_badge_html}{_email}</div>
    <a href="/?logout=1" target="_self" class="uv-logout" style="flex-shrink:0;">log out</a>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Mini icon nav (shown when sidebar is collapsed) ───────────────────────────
# Active state is applied by uvSetActive() in JS — no Python active classes needed.
_mini_admin     = _nav_link("settings",  "⚙️", "", _tok_qs, "mini-nav-link") if _is_admin else ""
_mini_portfolio = _nav_link("portfolio", "📁", "", _tok_qs, "mini-nav-link") if not _is_demo else ""
st.markdown(f"""
<div class="mini-nav">
  <div class="mini-nav-top">
    {_nav_link("dashboard", "💎", "", _tok_qs, "mini-nav-link")}
    {_nav_link("screener",  "🔍", "", _tok_qs, "mini-nav-link")}
    {_mini_portfolio}
  </div>
  <div class="mini-nav-bottom">
    {_mini_admin}
    {_nav_link("help", "❓", "", _tok_qs, "mini-nav-link")}
  </div>
</div>
""", unsafe_allow_html=True)

# Navigation component — intercepts nav clicks via Streamlit.setComponentValue
# so page switches happen over the existing WebSocket (no browser reload = no flash).
_nav_target = st_components.html(f"""
<script>
// Apply active nav highlight via an injected <style> tag (not via Python classes).
// This keeps sidebar HTML identical on every Python rerun → React no-op → no flash.
function uvSetActive(page) {{
  var doc = window.parent.document;
  var s = doc.getElementById('_uv_nav_style');
  if (!s) {{
    s = doc.createElement('style');
    s.id = '_uv_nav_style';
    doc.head.appendChild(s);
  }}
  s.textContent =
    '[data-uv-page="' + page + '"].uv-nav-item  {{ background:rgba(79,142,247,0.14)!important; opacity:1!important; }}' +
    '[data-uv-page="' + page + '"].mini-nav-link {{ background:rgba(79,142,247,0.18)!important; opacity:1!important; }}';
}}
// Set initial active state from current page
uvSetActive({repr(_page)});

// Register uvNav — updates active style then notifies Python via WebSocket
window.parent.uvNav = function(page) {{
  uvSetActive(page);
  Streamlit.setComponentValue(page);
}};
Streamlit.setFrameHeight(0);

// Keep localStorage token fresh
(function(){{
  var tok = {repr(st.session_state.get('jwt_token', ''))};
  if (tok) localStorage.setItem('uv_jwt', tok);
}})();

// Hide sidebar collapse/expand button
(function hideBtn() {{
  var el = window.parent.document.querySelector('[data-testid="collapsedControl"]');
  if (el) (el.closest('div') || el).style.setProperty('display','none','important');
}})();
new MutationObserver(function(){{
  var el = window.parent.document.querySelector('[data-testid="collapsedControl"]');
  if (el) (el.closest('div') || el).style.setProperty('display','none','important');
}}).observe(window.parent.document.body, {{childList:true, subtree:true}});
</script>
""", height=0)

_valid_pages = {"dashboard", "screener", "portfolio", "settings", "help"}

@st.fragment
def _render_page():
    """Handles nav clicks via WebSocket — updates query param without page reload."""
    if isinstance(_nav_target, str) and _nav_target in _valid_pages:
        st.query_params["page"] = _nav_target
        st.rerun(scope="fragment")

_render_page()

# ── Logout handler (outside fragment so it can clear session properly) ────────
if st.query_params.get("logout") == "1":
    st.query_params.clear()
    for _k in ("jwt_token", "user_email", "user_role"):
        st.session_state.pop(_k, None)
    st_components.html("<script>localStorage.removeItem('uv_jwt');</script>", height=0)
    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if _page == "dashboard":
    st.info("💎 Dashboard — coming soon.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — VALUE SCREENER
# ══════════════════════════════════════════════════════════════════════════════

if _page == "screener":
    if _is_demo:
        st.info("👁️ Demo mode — read only. Sign up for a full account to track a portfolio and manage your watchlist.")


    with st.spinner("Loading screener data…"):
        df     = load_screener_data()
        df_ams = load_amsterdam_screener_data()
        # If the cached DataFrame predates the algorithm rework, bust caches and
        # rerun the script so the cleared cache takes effect from a clean start.
        if "fair_value" not in df.columns or "Decision" not in df.columns:
            _bust_cache()

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
        **{c: st.column_config.TextColumn(c, width=100, help=_ch(c))
           for g in EXTRA_GROUPS.values() for c in g
           if c not in ("Risk Score",)},
    }

    def _render_table(tab_df, key_suffix):
        """Render the screener table with optional column groups."""
        selected_groups = st.multiselect(
            "Add columns",
            label_visibility="collapsed",
            options=list(EXTRA_GROUPS.keys()),
            default=[],
            key=f"col_groups_{key_suffix}",
            placeholder="Show additional column groups…",
        )

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
        disabled_cols = list(display_data.keys()) if _is_demo else all_data_cols

        _row_h  = 35
        _header = 38
        _height = min(_header + _n_rows * _row_h + 4, 800)

        edited = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config=col_config,
            disabled=disabled_cols,
            height=_height,
            key=f"table_{key_suffix}",
        )
        return edited

    tab_watchlist, tab_amsterdam, tab_brussels = st.tabs(
        ["★ Watchlist", "Euronext Amsterdam", "Euronext Brussels"]
    )

    # ── Tab: Watchlist ────────────────────────────────────────────────────────
    with tab_watchlist:
        _wl_tickers = watchlist
        _wl_col, _wl_refresh = st.columns([9, 1])
        with _wl_refresh:
            if st.button("🔄 refresh", type="tertiary", key="wl_refresh"):
                _bust_cache()
        if not _wl_tickers:
            st.info("Check ★ next to any stock in Brussels or Amsterdam to add it to your watchlist.")
        else:
            _all_df = pd.concat([df, df_ams], ignore_index=True)
            wl_df = _all_df[_all_df["Ticker"].isin(_wl_tickers)].reset_index(drop=True)
            wl_df.index += 1
            with _wl_col:
                st.markdown(f"**{len(wl_df)}** stocks · uncheck ★ to remove")
            wl_edited = _render_table(wl_df, "watchlist")
            if not _is_demo:
                still_watched = set(wl_edited.loc[wl_edited["★"], "Ticker"].tolist())
                if still_watched != _wl_tickers:
                    save_watchlist(still_watched)
                    st.rerun()

    # ── Tab: Euronext Brussels ────────────────────────────────────────────────
    with tab_brussels:
        _valued     = df["fair_value"].notna()
        _n_unvalued = (~_valued).sum()

        _br_col, _br_toggle, _br_refresh = st.columns([7, 2, 1])
        with _br_refresh:
            if st.button("🔄 refresh", type="tertiary", key="screener_refresh"):
                _bust_cache()
        with _br_toggle:
            _show_all = st.toggle(
                "unvalued stocks",
                value=False,
                key="show_unvalued",
            ) if _n_unvalued > 0 else False

        _screener_df = df if _show_all else df[_valued].reset_index(drop=True)
        _screener_df.index = range(1, len(_screener_df) + 1)

        _hint = "check ★ to add to watchlist" if not _is_demo else "read-only in demo mode"
        with _br_col:
            st.markdown(f"**{len(_screener_df)}** stocks · {_hint}")
        edited = _render_table(_screener_df, "main")

        if not _is_demo:
            br_new = set(edited.loc[edited["★"], "Ticker"].tolist())
            merged_br = (watchlist - set(df["Ticker"])) | br_new
            if merged_br != watchlist:
                save_watchlist(merged_br)
                st.rerun()

    # ── Tab: Euronext Amsterdam ───────────────────────────────────────────────
    with tab_amsterdam:
        _ams_valued     = df_ams["fair_value"].notna()
        _ams_n_unvalued = (~_ams_valued).sum()

        _ams_col, _ams_toggle, _ams_refresh = st.columns([7, 2, 1])
        with _ams_refresh:
            if st.button("🔄 refresh", type="tertiary", key="ams_refresh"):
                _bust_cache()
        with _ams_toggle:
            _ams_show_all = st.toggle(
                "unvalued stocks",
                value=False,
                key="ams_show_unvalued",
            ) if _ams_n_unvalued > 0 else False

        _ams_df = df_ams if _ams_show_all else df_ams[_ams_valued].reset_index(drop=True)
        _ams_df.index = range(1, len(_ams_df) + 1)

        _ams_hint = "check ★ to add to watchlist" if not _is_demo else "read-only in demo mode"
        with _ams_col:
            st.markdown(f"**{len(_ams_df)}** stocks · {_ams_hint}")
        ams_edited = _render_table(_ams_df, "ams")

        if not _is_demo:
            ams_new_watchlist = set(ams_edited.loc[ams_edited["★"], "Ticker"].tolist())
            merged_watchlist  = (watchlist - set(df_ams["Ticker"])) | ams_new_watchlist
            if merged_watchlist != watchlist:
                save_watchlist(merged_watchlist)
                st.rerun()

        col_dist, col_decision = st.columns(2)
        with col_dist:
            with st.expander("Score distribution"):
                st.bar_chart(
                    df["Value Score"].dropna()
                    .value_counts(bins=10, sort=False).sort_index().rename("Count")
                )
        with col_decision:
            with st.expander("Decision breakdown"):
                counts = df["Decision"].value_counts().rename("Count")
                st.bar_chart(counts)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — PORTFOLIO
# ══════════════════════════════════════════════════════════════════════════════

if _page == "portfolio" and not _is_demo:

    # ── Upload (once) ─────────────────────────────────────────────────────────
    if not portfolio_exists():
        st.subheader("Import portfolio")
        st.info("Upload your Excel file once. Only open EBR: positions will be imported.")
        uploaded = st.file_uploader("Choose your portfolio .xlsx file", type=["xlsx"])
        if uploaded:
            with st.spinner("Parsing Excel…"):
                try:
                    pf, sold, div_hist = parse_excel(uploaded)
                    if pf.empty:
                        st.error("No open EBR:/EAM: positions found. Check that your file matches the expected format.")
                    else:
                        save_portfolio(pf)
                        save_sold(sold)
                        save_div_hist(div_hist)
                        st.success(f"Imported {len(pf)} open, {len(sold)} sold, {len(div_hist)} dividend records. Reloading…")
                        st.rerun()
                except Exception as e:
                    st.error(f"Could not parse file: {e}")
                    st.code(traceback.format_exc())
        st.stop()

    # ── Load saved portfolio ───────────────────────────────────────────────────
    pf = load_portfolio()
    if pf is None or pf.empty:
        st.error("Portfolio file is empty or corrupted.")
        if st.button("Remove and re-upload"):
            PORTFOLIO_FILE.unlink(missing_ok=True)
            st.rerun()
        st.stop()

    # ── Fetch live prices ─────────────────────────────────────────────────────
    with st.spinner("Fetching live prices & fair value estimates…"):
        live_data = _fetch_live_data(tuple(pf["ticker"].tolist()))

    pf["live_price"]      = pf["ticker"].map(lambda t: live_data[t]["price"])
    pf["analyst_target"]  = pf["ticker"].map(lambda t: live_data[t]["analyst_target"])
    pf["graham_number"]   = pf["ticker"].map(lambda t: live_data[t]["graham_number"])
    pf["pe_fair_value"]   = pf["ticker"].map(lambda t: live_data[t]["pe_fair_value"])
    pf["graham_growth"]   = pf["ticker"].map(lambda t: live_data[t]["graham_growth"])
    pf["fair_value"]      = pf["ticker"].map(lambda t: live_data[t]["fair_value"])
    pf["div_rate"]        = pf["ticker"].map(lambda t: live_data[t]["div_rate"] or 0)
    pf["expected_annual"] = (pf["div_rate"] * pf["shares"]).round(2)
    pf["current_value"]   = pf["live_price"] * pf["shares"]
    pf["price_gain"]      = pf["current_value"] - pf["purchase_value"]
    pf["price_gain_pct"]  = (pf["price_gain"] / pf["purchase_value"] * 100).round(2)
    pf["total_return"]    = pf["price_gain"] + pf["dividends"].fillna(0)
    pf["total_return_pct"] = (pf["total_return"] / pf["purchase_value"] * 100).round(2)
    pf["upside_pct"]      = ((pf["analyst_target"] - pf["live_price"]) / pf["live_price"] * 100).round(1)
    pf["fv_upside_pct"]   = ((pf["fair_value"] - pf["live_price"]) / pf["live_price"] * 100).round(1)
    pf["day_change_pct"]  = pf["ticker"].map(lambda t: live_data[t].get("day_change_pct"))
    pf["prev_close"]      = pf["ticker"].map(lambda t: live_data[t].get("prev_close"))

    # Attach screener data (value score + all extra column fields) — Brussels + Amsterdam
    _scr = pd.concat(
        [load_screener_data(), load_amsterdam_screener_data()], ignore_index=True
    ).set_index("Ticker")
    pf["value_score"] = pf["ticker"].map(_scr["Value Score"].to_dict() if "Value Score" in _scr.columns else {})

    def _scr_col(field: str) -> "pd.Series":
        """Return screener field values aligned to portfolio tickers."""
        col = _scr[field] if field in _scr.columns else pd.Series(dtype=object)
        return pf["ticker"].map(col.to_dict())

    # ── Summary cards (shared across both sub-tabs) ───────────────────────────
    total_invested   = pf["purchase_value"].sum()
    total_current    = pf["current_value"].sum()
    total_dividends  = pf["dividends"].fillna(0).sum()
    total_return     = total_current - total_invested + total_dividends
    total_return_pct = total_return / total_invested * 100 if total_invested else 0
    total_expected   = pf["expected_annual"].sum()

    price_gain     = total_current - total_invested
    price_gain_pct = price_gain / total_invested * 100 if total_invested else 0

    st_autorefresh(interval=60_000, key="portfolio_refresh")
    sub_positions, sub_dividends, sub_sold = st.tabs(["Positions", "Dividends", "Realised"])

    # ── Sub-tab: Positions ────────────────────────────────────────────────────
    with sub_positions:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Invested",      f"€{total_invested:,.0f}")
        c2.metric("Current value", f"€{total_current:,.0f}",  delta=f"{price_gain_pct:+.1f}%")
        c3.metric("Dividends",     f"€{total_dividends:,.0f}")
        c4.metric("Total return",  f"€{total_return:,.0f}",   delta=f"{total_return_pct:+.1f}%")
        st.divider()

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
                "Buy Date":    pd.to_datetime(pf["date_in"]).dt.strftime("%d-%m-%Y").fillna("—"),
            },
        }

        _pos_groups = st.multiselect(
            "Add columns",
            label_visibility="collapsed",
            options=list(_POS_EXTRA_GROUPS.keys()),
            default=[],
            key="pos_col_groups",
            placeholder="Show additional column groups…",
        )

        # Build core positions DataFrame
        pos_data = {
            "Company":        pf["name"],
            "Ticker":         pf["ticker"],
            "Shares":         pf["shares"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
            "Live Price":     pf["live_price"].map(_fmt_eur),
            "Day Chg %":      pf["day_change_pct"],
            "Invested":       pf["purchase_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            "Current":        pf["current_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            "Price Gain %":   pf["price_gain_pct"],
            "Total Return %": pf["total_return_pct"],
        }
        for grp in _pos_groups:
            pos_data.update(_POS_EXTRA_GROUPS[grp])

        _core_cols = {"Company", "Ticker", "Shares", "Live Price", "Day Chg %",
                      "Invested", "Current", "Price Gain %", "Total Return %"}

        positions = pd.DataFrame(pos_data).sort_values("Total Return %", ascending=False)
        _n_rows = len(positions)

        # Highlight extra columns with a subtle tint
        _extra_cols = [c for c in positions.columns if c not in _core_cols]
        if _extra_cols:
            positions = positions.style.set_properties(
                subset=_extra_cols,
                **{"background-color": "rgba(99, 102, 241, 0.07)"},
            )

        _pos_col_config = {
            "Company":        st.column_config.TextColumn("Company",         pinned=True),
            "Day Chg %":      st.column_config.NumberColumn("Day Chg %",      format="%+.2f%%"),
            "UV Upside %":    st.column_config.NumberColumn("UV Upside %",    format="%+.1f%%"),
            "Price Gain %":   st.column_config.NumberColumn("Price Gain %",   format="%.2f%%"),
            "Total Return %": st.column_config.NumberColumn("Total Return %", format="%.2f%%"),
            "Value Score":    st.column_config.ProgressColumn("Value Score",  min_value=0, max_value=100, format="%.1f"),
            "Risk Score":     st.column_config.ProgressColumn("Risk Score",   min_value=0, max_value=100, format="%.1f"),
        }

        _row_h  = 35
        _header = 38
        _height = min(_header + _n_rows * _row_h + 4, 800)
        st.dataframe(
            positions,
            use_container_width=True,
            hide_index=True,
            column_config=_pos_col_config,
            height=_height,
        )

        ch1, ch2 = st.columns(2)
        with ch1:
            st.subheader("P&L per position")
            st.bar_chart(pf.set_index("name")["price_gain"].dropna().sort_values())
        with ch2:
            st.subheader("Portfolio allocation")
            st.bar_chart(pf.set_index("name")["current_value"].dropna().sort_values(ascending=False))

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
        st.markdown('<div style="height:3.5rem"></div>', unsafe_allow_html=True)
        _gross = pf["dividends"].fillna(0)
        _tax   = (_gross * 0.30).round(2)
        _net   = (_gross - _tax).round(2)
        div_table = pd.DataFrame({
            "Company":   pf["name"],
            "Ticker":    pf["ticker"],
            "Shares":    pf["shares"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
            "Div/Share": pf["div_rate"].map(lambda v: f"€{v:.4f}" if pd.notna(v) and v else "—"),
            "Gross":     _gross.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
            "Tax (30%)": _tax.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
            "Net":       _net.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
            "Date":      pd.to_datetime(pf["date_in"]).dt.strftime("%d-%m-%Y").fillna("—"),
        })
        st.dataframe(div_table, use_container_width=True, hide_index=True,
                     height=(len(pf) + 1) * 35 + 10)

        st.divider()

        # Full dividend payment history
        if div_hist is not None and not div_hist.empty:
            st.subheader("Dividend history")

            years = sorted(div_hist["date"].dt.year.dropna().unique().astype(int), reverse=True)
            year_options = ["All"] + years
            default_idx = year_options.index(datetime.now().year) if datetime.now().year in year_options else 0
            selected_year = st.selectbox("Filter by year", year_options, index=default_idx, key="div_year_filter")

            hist_table = div_hist.copy()
            if selected_year != "All":
                hist_table = hist_table[hist_table["date"].dt.year == selected_year]
            hist_table = hist_table.sort_values("date", ascending=True)
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
            st.dataframe(hist_display, use_container_width=True, hide_index=True,
                         height=(len(hist_display) + 1) * 35 + 10)

            st.divider()
            ch3, ch4 = st.columns(2)
            with ch3:
                st.subheader("Total received per stock")
                st.bar_chart(
                    div_hist.groupby("name")["amount"].sum().sort_values(ascending=False)
                )
            with ch4:
                st.subheader("Dividends by year")
                by_year = div_hist.copy()
                by_year["year"] = by_year["date"].dt.year
                st.bar_chart(by_year.groupby("year")["amount"].sum())
        else:
            st.info("Re-upload your Excel file to load full dividend history.")

    # ── Sub-tab: Sold ─────────────────────────────────────────────────────────
    with sub_sold:
        sold = load_sold()
        if sold is None or sold.empty:
            st.info("No sold EBR: positions found in your portfolio file.")
        else:
            pv                     = pd.to_numeric(sold["purchase_value"], errors="coerce")
            sv                     = pd.to_numeric(sold["sale_value"], errors="coerce")
            sold["price_gain"]     = sv - pv
            sold["price_gain_pct"] = (sold["price_gain"] / pv * 100).round(2)
            sold["dividends"]      = pd.to_numeric(sold["dividends"], errors="coerce").fillna(0)
            sold["total_return"]   = sold["price_gain"] + sold["dividends"]
            sold["held_days"]      = (pd.to_datetime(sold["date_out"]) - pd.to_datetime(sold["date_in"])).dt.days

            def _annual_return(row):
                if pd.isna(row["held_days"]) or row["held_days"] <= 0 or pv[row.name] <= 0:
                    return None
                total_value = sv[row.name] + row["dividends"]
                return ((total_value / pv[row.name]) ** (365 / row["held_days"]) - 1) * 100

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
            st.markdown('<div style="height:3.5rem"></div>', unsafe_allow_html=True)

            sold_table = pd.DataFrame({
                "Company":         sold["name"],
                "Ticker":          sold["ticker"],
                "Shares":          pd.to_numeric(sold["shares"], errors="coerce").map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
                "Invested":        pd.to_numeric(sold["purchase_value"], errors="coerce").map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
                "Proceeds":        pd.to_numeric(sold["sale_value"], errors="coerce").map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
                "Price Gain":      sold["price_gain"].map(lambda v: f"€{v:+,.0f}" if pd.notna(v) else "—"),
                "Price Gain %":    sold["price_gain_pct"],
                "Dividends":       sold["dividends"].map(lambda v: f"€{v:,.0f}"),
                "Annual Return %": sold["annual_return_pct"],
                "Buy Date":        pd.to_datetime(sold["date_in"]).dt.strftime("%d-%m-%Y").fillna("—"),
                "Sell Date":       pd.to_datetime(sold["date_out"]).dt.strftime("%d-%m-%Y").fillna("—"),
            })

            st.dataframe(
                sold_table,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Price Gain %":    st.column_config.NumberColumn("Price Gain %",    format="%.2f%%"),
                    "Annual Return %": st.column_config.NumberColumn("Annual Return %", format="%.2f%%"),
                },
                height=(len(sold) + 1) * 35 + 10,
            )

            st.divider()
            st.subheader("Realised return per position")
            st.bar_chart(sold.set_index("name")["total_return"].sort_values())

    # ── Re-upload option ──────────────────────────────────────────────────────
    if not _is_demo:
        st.divider()
    with st.expander("Re-upload portfolio file", expanded=False) if not _is_demo else st.empty():
        st.warning("This will replace your current portfolio data.")
        new_file = st.file_uploader("Upload new .xlsx", type=["xlsx"], key="reupload")
        if new_file:
            try:
                new_pf, new_sold, new_div_hist = parse_excel(new_file)
                if new_pf.empty:
                    st.error("No open EBR: positions found.")
                else:
                    save_portfolio(new_pf)
                    save_sold(new_sold)
                    save_div_hist(new_div_hist)
                    st.cache_data.clear()
                    st.success(f"Portfolio updated with {len(new_pf)} positions.")
                    st.rerun()
            except Exception as e:
                st.error(f"Could not parse file: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

if _page == "settings":
    if _is_admin:
        tab_admin, = st.tabs(["🔑 Users"])
        with tab_admin:
            _render_admin_users()
    else:
        st.info("No settings available for your account.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — HELP
# ══════════════════════════════════════════════════════════════════════════════

if _page == "help":
    _render_help()

