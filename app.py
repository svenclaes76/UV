"""Streamlit web app — Euronext Brussels value screener + portfolio tracker."""

# ── Column help texts (shown as header tooltips and in the help dialog) ───────
COLUMN_HELP = {
    # ── Core ──────────────────────────────────────────────────────────────────
    "★":             "Watchlist — check to add this stock to your personal watchlist.",
    "Company":       "Full company name as reported by the exchange.",
    "Ticker":        "Exchange ticker symbol on Euronext Brussels (.BR suffix).",
    "Price":         "Current market price in EUR.",
    "Fair Value":    (
        "Weighted composite intrinsic value estimate from up to 5 models: "
        "Graham Number, PE Fair Value, EPV, DDM (single + multi-stage), and Analyst Target. "
        "Weights auto-adjust: DDM weight is zero for non-dividend payers or payout > 90%."
    ),
    "MoS %":         (
        "Margin of Safety = (Fair Value − Price) / Fair Value. "
        "Positive = stock trades below estimated fair value. "
        "The algorithm requires MoS > 20–30% before a stock enters the buy zone."
    ),
    "TER %":         (
        "Total Expected Return = Capital Gain % + Forward Dividend Yield + Expected DGR. "
        "A complete 1-year return estimate. > 15% = attractive, 8–15% = acceptable, < 8% = unattractive."
    ),
    "Decision":      (
        "Final signal from the composite score. "
        "🟢 Strong Buy (score > 70) | 🟡 Monitor (40–70) | 🔴 Avoid (< 40). "
        "Hard veto rules can force Avoid regardless of score: D/E > 5×, negative FCF, or dividend coverage < 1.0× with sustainability flag."
    ),
    "Value Score":   (
        "Composite score 0–100. Formula: "
        "30% × MoS rank + 18% × (100 − Risk rank) + 22% × Quality rank + 15% × Momentum rank + 15% × Dividend rank. "
        "All components are percentile-ranked across the full universe before weighting."
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
from streamlit_autorefresh import st_autorefresh

from prices import fetch_prices

from fetch_tickers import fetch_brussels_tickers
from screener import CACHE_FILE, CACHE_TTL_HOURS, _load_cache, run_screener
from portfolio import (parse_excel, save_portfolio, save_sold, save_div_hist,
                       load_portfolio, load_sold, load_div_hist, portfolio_exists,
                       PORTFOLIO_FILE, save_watchlist, load_watchlist)
from auth import register, login, verify_token, list_users, set_role, delete_user, ROLES

@st.dialog("⚙️ Admin — User management", width="large")
def _show_admin_dialog():
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
                key=f"dlg_role_{u['email']}",
                label_visibility="collapsed",
            )
            if col_save.button("Save", key=f"dlg_save_{u['email']}", use_container_width=True):
                ok, msg = set_role(u["email"], new_role)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            current_email = st.session_state.get("user_email", "")
            if u["email"] != current_email:
                if col_del.button("🗑️", key=f"dlg_del_{u['email']}", use_container_width=True,
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
    with st.form("dlg_admin_create_user"):
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


@st.dialog("📖 Column Reference", width="large")
def _show_help_dialog():
    """Modal that explains every column in the screener."""
    sections = {
        "Core columns": ["★", "Company", "Ticker", "Price", "Fair Value",
                         "MoS %", "TER %", "Decision", "Value Score"],
        "Valuation models": ["Graham #", "PE Fair Val", "EPV",
                             "DDM (1-stage)", "DDM (2-stage)"],
        "Risk & size":      ["Risk Score", "Mkt Cap", "Beta", "Debt/Equity"],
        "Multiples":        ["P/E", "P/B", "EV/EBITDA"],
        "Quality":          ["ROE %", "ROA %", "Op Margin %", "FCF Yield %"],
        "Growth":           ["Rev Growth %", "EPS Growth %"],
        "Dividends":        ["Div Yield", "5yr Avg Yield", "Payout Ratio",
                             "Cash Payout", "Div Coverage", "Div Flag"],
    }
    for section, cols in sections.items():
        st.markdown(f"**{section}**")
        for col in cols:
            desc = COLUMN_HELP.get(col, "")
            if desc:
                st.markdown(
                    f'<div style="display:flex;gap:10px;margin-bottom:6px;">'
                    f'<span style="min-width:120px;font-weight:600;color:#a78bfa;">{col}</span>'
                    f'<span style="color:#ccc;font-size:0.9rem;">{desc}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.divider()


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


@st.cache_data(show_spinner=False)
def load_screener_data() -> pd.DataFrame:
    stocks = fetch_brussels_tickers()
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
  /* Reduce default padding */
  .block-container { padding-top: 1.5rem !important; padding-bottom: 0.5rem !important; }
  /* Tighten metric cards */
  div[data-testid="metric-container"] { padding: 0.3rem 0.5rem !important; }
  /* Compact inner tab bar (Portfolio sub-tabs) */
  div[data-testid="stTabs"] > div:first-child { margin-bottom: 0.25rem; }
  /* Tighten caption spacing */
  .stCaption { margin-bottom: 0 !important; }

  /* ── Sidebar nav radio → styled nav items ────────────────────────────── */
  /* Hide the group label */
  section[data-testid="stSidebar"] div[data-testid="stRadio"] > label { display:none !important; }
  /* Stack vertically, full width */
  section[data-testid="stSidebar"] div[data-testid="stRadio"] > div {
    display: flex !important;
    flex-direction: column !important;
    gap: 2px !important;
  }
  /* Each nav item */
  section[data-testid="stSidebar"] div[data-testid="stRadio"] > div > label {
    display: flex !important;
    align-items: center !important;
    padding: 8px 12px !important;
    border-radius: 8px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    color: #aaa !important;
    transition: background 0.12s, color 0.12s !important;
    width: 100% !important;
  }
  section[data-testid="stSidebar"] div[data-testid="stRadio"] > div > label:hover {
    background: rgba(255,255,255,0.06) !important;
    color: #eee !important;
  }
  /* Active nav item */
  section[data-testid="stSidebar"] div[data-testid="stRadio"] > div > label:has(input:checked) {
    background: rgba(79,142,247,0.15) !important;
    color: #fff !important;
  }
  /* Hide radio circle */
  section[data-testid="stSidebar"] div[data-testid="stRadio"] input[type="radio"] { display:none !important; }
  section[data-testid="stSidebar"] div[data-testid="stRadio"] > div > label > div:first-child { display:none !important; }

  /* Sidebar action buttons (admin / help) as plain text links */
  section[data-testid="stSidebar"] button[data-testid="stBaseButton-tertiary"] {
    color: #666 !important;
    font-size: 0.82rem !important;
    padding: 2px 12px !important;
    min-height: 0 !important;
    height: auto !important;
    line-height: 1.8 !important;
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
  }
  section[data-testid="stSidebar"] button[data-testid="stBaseButton-tertiary"]:hover { color: #bbb !important; }
</style>
""", unsafe_allow_html=True)

# ── Authentication gate ───────────────────────────────────────────────────────

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
                st.rerun()
            else:
                st.error(result)

    st.stop()


_auth_wall()

_current_role = st.session_state.get("user_role", "normal")
_is_admin = _current_role == "administrator"
_is_demo  = _current_role == "demo"
_email    = st.session_state.get("user_email", "")
_badge    = {"administrator": "🔑", "demo": "👁️"}.get(_current_role, "")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # Logo + wordmark
    st.markdown("""
<div style="display:flex;align-items:center;gap:10px;padding:4px 0 20px 0;">
  <svg width="36" height="36" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg">
    <rect width="56" height="56" rx="12" fill="#1a1d26"/>
    <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle"
          font-family="'Segoe UI',sans-serif" font-size="22" font-weight="800"
          fill="url(#sg)">UV</text>
    <defs>
      <linearGradient id="sg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#4f8ef7"/>
        <stop offset="100%" stop-color="#a78bfa"/>
      </linearGradient>
    </defs>
  </svg>
  <div>
    <div style="font-size:1.1rem;font-weight:800;line-height:1.1;letter-spacing:-0.3px;">
      UV <span style="font-weight:300;color:#666;">· Undervalued</span>
    </div>
    <div style="font-size:0.72rem;color:#666;margin-top:1px;">Portfolio tracker &amp; screener</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # Nav
    _nav_options = ["🔍 Screener", "★ Watchlist"] if _is_demo else ["🔍 Screener", "★ Watchlist", "📁 Portfolio"]
    _active_page = st.radio("Navigation", _nav_options, key="nav_page")

    # Spacer pushes account section to bottom
    st.markdown('<div style="flex:1;min-height:60px;"></div>', unsafe_allow_html=True)
    st.divider()

    # Admin + help
    if _is_admin:
        if st.button("⚙️ admin", type="tertiary", key="hdr_admin"):
            st.session_state["show_admin"] = True
            st.rerun()
    if st.button("❓ help", type="tertiary", key="hdr_help"):
        st.session_state["show_help"] = True
        st.rerun()

    # Account info + logout
    st.markdown(
        f'<div style="font-size:0.78rem;color:#555;padding:8px 12px 4px 12px;line-height:1.6;">'
        f'{_badge} {_email}<br>'
        f'<a href="/?logout=1" target="_self" style="color:#555;text-decoration:none;">log out</a>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Logout query-param handler ────────────────────────────────────────────────
if st.query_params.get("logout") == "1":
    st.query_params.clear()
    for _k in ("jwt_token", "user_email", "user_role"):
        st.session_state.pop(_k, None)
    st.rerun()

if st.session_state.pop("show_admin", False):
    _show_admin_dialog()

if st.session_state.pop("show_help", False):
    _show_help_dialog()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — VALUE SCREENER
# ══════════════════════════════════════════════════════════════════════════════

if _active_page == "🔍 Screener":
    if _is_demo:
        st.info("👁️ Demo mode — read only. Sign up for a full account to track a portfolio and manage your watchlist.")


    with st.spinner("Loading screener data…"):
        df = load_screener_data()
        # If the cached DataFrame predates the algorithm rework, bust caches and
        # rerun the script so the cleared cache takes effect from a clean start.
        if "fair_value" not in df.columns or "Decision" not in df.columns:
            try:
                CACHE_FILE.write_text("{}", encoding="utf-8")
            except OSError:
                pass
            st.cache_data.clear()
            st.rerun()

    watchlist = load_watchlist()

    def _fmt_mos(v):
        if pd.isna(v):
            return "—"
        return f"{v:+.1f}%"

    def _fmt_decision(v):
        return {"Strong Buy": "🟢 Strong Buy", "Monitor": "🟡 Monitor", "Avoid": "🔴 Avoid"}.get(v, v)

    def _fmt_div_flag(v):
        return {"At Risk": "⚠️ At Risk", "OK": "✅ OK", "": "—"}.get(str(v) if pd.notna(v) else "", "—")

    # ── Column groups ─────────────────────────────────────────────────────────
    # Core columns always shown; extra groups toggled via multiselect
    CORE_COLS = {
        "★":           (None,         None),
        "Company":     ("Name",       lambda v: v),
        "Ticker":      ("Ticker",     lambda v: v),
        "Price":       ("Price",      lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
        "Fair Value":  ("fair_value", lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
        "MoS %":       ("MoS %",      _fmt_mos),
        "TER %":       ("TER %",      lambda v: f"{v:+.1f}%" if pd.notna(v) else "—"),
        "Decision":    ("Decision",   _fmt_decision),
        "Value Score": ("Value Score",lambda v: v),
    }

    EXTRA_GROUPS = {
        "Valuation models": {
            "Graham #":      ("graham_number",   lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "PE Fair Val":   ("pe_fair_value",   lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "EPV":           ("epv",             lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "DDM (1-stage)": ("ddm",             lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "DDM (2-stage)": ("ddm_multistage",  lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
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
    def _h(col): return COLUMN_HELP.get(col)

    _col_config_map = {
        "★":            st.column_config.CheckboxColumn("★",            width=40,  help=_h("★")),
        "Company":      st.column_config.TextColumn(    "Company",      width=180, help=_h("Company")),
        "Ticker":       st.column_config.TextColumn(    "Ticker",       width=90,  help=_h("Ticker")),
        "Price":        st.column_config.TextColumn(    "Price",        width=80,  help=_h("Price")),
        "Fair Value":   st.column_config.TextColumn(    "Fair Value",   width=90,  help=_h("Fair Value")),
        "MoS %":        st.column_config.TextColumn(    "MoS %",        width=75,  help=_h("MoS %")),
        "TER %":        st.column_config.TextColumn(    "TER %",        width=75,  help=_h("TER %")),
        "Decision":     st.column_config.TextColumn(    "Decision",     width=130, help=_h("Decision")),
        "Value Score":  st.column_config.ProgressColumn("Value Score",  width=120,
                             min_value=0, max_value=100, format="%.1f", help=_h("Value Score")),
        "Risk Score":   st.column_config.ProgressColumn("Risk Score",   width=110,
                             min_value=0, max_value=10,  format="%.1f", help=_h("Risk Score")),
        "Mkt Cap":      st.column_config.TextColumn(    "Mkt Cap",      width=80,  help=_h("Mkt Cap")),
        "Beta":         st.column_config.TextColumn(    "Beta",         width=55,  help=_h("Beta")),
        "Debt/Equity":  st.column_config.TextColumn(    "Debt/Equity",  width=95,  help=_h("Debt/Equity")),
        "P/E":          st.column_config.TextColumn(    "P/E",          width=60,  help=_h("P/E")),
        "P/B":          st.column_config.TextColumn(    "P/B",          width=60,  help=_h("P/B")),
        "EV/EBITDA":    st.column_config.TextColumn(    "EV/EBITDA",    width=90,  help=_h("EV/EBITDA")),
        **{c: st.column_config.TextColumn(c, width=100, help=_h(c))
           for g in EXTRA_GROUPS.values() for c in g
           if c not in ("Risk Score",)},
    }

    def _render_table(tab_df, key_suffix):
        """Render the screener table with optional column groups."""
        selected_groups = st.multiselect(
            "➕ Add columns",
            options=list(EXTRA_GROUPS.keys()),
            default=[],
            key=f"col_groups_{key_suffix}",
            placeholder="Show additional column groups…",
        )

        # Build the display DataFrame from core cols + selected extras
        display_data = {"★": tab_df["Ticker"].isin(watchlist)}
        for col, (field, fmt) in list(CORE_COLS.items())[1:]:  # skip ★, already added
            if field in tab_df.columns:
                display_data[col] = tab_df[field].map(fmt).values
            else:
                display_data[col] = "—"

        active_extra_cols = []
        for group in selected_groups:
            for col, (field, fmt) in EXTRA_GROUPS[group].items():
                if field in tab_df.columns:
                    display_data[col] = tab_df[field].map(fmt).values
                else:
                    display_data[col] = "—"
                active_extra_cols.append(col)

        display_df = pd.DataFrame(display_data)

        all_data_cols = [c for c in display_df.columns if c != "★"]
        col_config    = {c: _col_config_map[c] for c in display_df.columns if c in _col_config_map}
        disabled_cols = all_data_cols if _is_demo else all_data_cols

        edited = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config=col_config,
            disabled=disabled_cols if _is_demo else all_data_cols,
            height=500,
            key=f"table_{key_suffix}",
        )
        return edited

    # Filter row: unvalued toggle + refresh button on same row
    _valued     = df["fair_value"].notna()
    _n_unvalued = (~_valued).sum()
    _col_toggle, _col_refresh = st.columns([9, 1])
    with _col_toggle:
        _show_all = st.toggle(
            f"Include {_n_unvalued} unvalued stocks (no fair value estimate available)",
            value=False,
            key="show_unvalued",
        ) if _n_unvalued > 0 else False
    with _col_refresh:
        if st.button("🔄 refresh", type="tertiary", key="screener_refresh"):
            try:
                CACHE_FILE.write_text("{}", encoding="utf-8")
            except OSError:
                pass
            st.cache_data.clear()
            st.rerun()
    _screener_df = df if _show_all else df[_valued].reset_index(drop=True)
    _screener_df.index = range(1, len(_screener_df) + 1)

    _hint = "check ★ to add to watchlist" if not _is_demo else "read-only in demo mode"
    st.markdown(f"**{len(_screener_df)}** stocks · {_hint}")
    edited = _render_table(_screener_df, "main")

    if not _is_demo:
        new_watchlist = set(edited.loc[edited["★"], "Ticker"].tolist())
        if new_watchlist != watchlist:
            save_watchlist(new_watchlist)
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
# PAGE — WATCHLIST
# ══════════════════════════════════════════════════════════════════════════════

if _active_page == "★ Watchlist":
    with st.spinner("Loading screener data…"):
        df = load_screener_data()
        if "fair_value" not in df.columns or "Decision" not in df.columns:
            try:
                CACHE_FILE.write_text("{}", encoding="utf-8")
            except OSError:
                pass
            st.cache_data.clear()
            st.rerun()
    watchlist = load_watchlist()

    def _fmt_mos(v):
        if pd.isna(v): return "—"
        return f"{v:+.1f}%"
    def _fmt_decision(v):
        return {"Strong Buy": "🟢 Strong Buy", "Monitor": "🟡 Monitor", "Avoid": "🔴 Avoid"}.get(v, v)

    wl_tickers = load_watchlist()
    if not wl_tickers:
        st.info("No stocks on your watchlist yet. Go to 🔍 Screener and check ★ next to any stock to add it.")
    else:
        wl_df = df[df["Ticker"].isin(wl_tickers)].reset_index(drop=True)
        wl_df.index += 1
        st.markdown(f"**{len(wl_df)}** stocks on watchlist · uncheck ★ to remove")
        _wl_display = {
            "★":          wl_df["Ticker"].isin(wl_tickers),
            "Company":    wl_df["Name"],
            "Ticker":     wl_df["Ticker"],
            "Price":      wl_df["Price"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "Fair Value": wl_df["fair_value"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "MoS %":      wl_df["MoS %"].map(_fmt_mos),
            "TER %":      wl_df["TER %"].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "—"),
            "Decision":   wl_df["Decision"].map(_fmt_decision),
            "Value Score":wl_df["Value Score"],
        }
        _wl_edited = st.data_editor(
            pd.DataFrame(_wl_display),
            use_container_width=True,
            hide_index=True,
            column_config={
                "★":           st.column_config.CheckboxColumn("★",           width=40),
                "Company":     st.column_config.TextColumn(    "Company",     width=180),
                "Ticker":      st.column_config.TextColumn(    "Ticker",      width=90),
                "Price":       st.column_config.TextColumn(    "Price",       width=80),
                "Fair Value":  st.column_config.TextColumn(    "Fair Value",  width=90),
                "MoS %":       st.column_config.TextColumn(    "MoS %",       width=75),
                "TER %":       st.column_config.TextColumn(    "TER %",       width=75),
                "Decision":    st.column_config.TextColumn(    "Decision",    width=130),
                "Value Score": st.column_config.ProgressColumn("Value Score", width=120,
                                   min_value=0, max_value=100, format="%.1f"),
            },
            disabled=["Company","Ticker","Price","Fair Value","MoS %","TER %","Decision","Value Score"],
            height=500,
            key="table_watchlist",
        )
        if not _is_demo:
            still_watched = set(_wl_edited.loc[_wl_edited["★"], "Ticker"].tolist())
            if still_watched != wl_tickers:
                save_watchlist(still_watched)
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE — PORTFOLIO
# ══════════════════════════════════════════════════════════════════════════════

if _active_page == "📁 Portfolio" and not _is_demo:

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
                        st.error("No open EBR: positions found. Check that your file matches the expected format.")
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

    # Attach screener value score
    screener_scores = load_screener_data().set_index("Ticker")["Value Score"].to_dict()
    pf["value_score"] = pf["ticker"].map(screener_scores)

    # ── Summary cards (shared across both sub-tabs) ───────────────────────────
    total_invested   = pf["purchase_value"].sum()
    total_current    = pf["current_value"].sum()
    total_dividends  = pf["dividends"].fillna(0).sum()
    total_return     = total_current - total_invested + total_dividends
    total_return_pct = total_return / total_invested * 100 if total_invested else 0
    total_expected   = pf["expected_annual"].sum()

    price_gain     = total_current - total_invested
    price_gain_pct = price_gain / total_invested * 100 if total_invested else 0
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Invested",            f"€{total_invested:,.0f}")
    c2.metric("Current value",       f"€{total_current:,.0f}",
              delta=f"€{price_gain:+,.0f}")
    c3.metric("Price gain",          f"{price_gain_pct:+.1f}%",
              delta=f"€{price_gain:+,.0f}")
    c4.metric("Dividends received",  f"€{total_dividends:,.0f}")
    c5.metric("Total return",        f"€{total_return:+,.0f}",
              delta=f"{total_return_pct:+.1f}%")

    sub_positions, sub_dividends, sub_sold = st.tabs(["Positions", "Dividends", "Realised"])

    # ── Sub-tab: Positions ────────────────────────────────────────────────────
    with sub_positions:
        st_autorefresh(interval=60_000, key="portfolio_refresh")
        positions = pd.DataFrame({
            "Company":        pf["name"],
            "Ticker":         pf["ticker"],
            "Shares":         pf["shares"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
            "Live Price":     pf["live_price"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "Day Chg %":      pf["day_change_pct"],
            "Fair Value":     pf["fair_value"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "FV Upside %":    pf["fv_upside_pct"],
            "Analyst Target": pf["analyst_target"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "Invested":       pf["purchase_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            "Current":        pf["current_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            "Price Gain %":   pf["price_gain_pct"],
            "Total Return %": pf["total_return_pct"],
            "Value Score":    pf["value_score"],
            "Buy Date":       pd.to_datetime(pf["date_in"]).dt.strftime("%d-%m-%Y").fillna("—"),
        }).sort_values("Total Return %", ascending=False)

        st.dataframe(
            positions,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Day Chg %":      st.column_config.NumberColumn("Day Chg %",      format="%+.2f%%"),
                "FV Upside %":    st.column_config.NumberColumn("FV Upside %",    format="%+.1f%%"),
                "Price Gain %":   st.column_config.NumberColumn("Price Gain %",   format="%.2f%%"),
                "Total Return %": st.column_config.NumberColumn("Total Return %", format="%.2f%%"),
                "Value Score":    st.column_config.ProgressColumn(
                    "Value Score", min_value=0, max_value=100, format="%.1f"),
            },
            height=(len(pf) + 1) * 35 + 10,
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
        d1.metric("Total received (history)", f"€{total_hist:,.2f}")
        d2.metric("Current holdings received", f"€{total_dividends:,.2f}")
        d3.metric("Expected next 12 mths",     f"€{total_expected:,.2f}")
        d4.metric("Portfolio yield",
                  f"{total_expected / total_current * 100:.2f}%" if total_current else "—")

        st.divider()

        # Per-position summary for current holdings
        st.subheader("Current holdings — dividend summary")
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
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Positions sold",   len(sold))
            s2.metric("Total invested",   f"€{pd.to_numeric(sold['purchase_value'], errors='coerce').sum():,.0f}")
            s3.metric("Total proceeds",   f"€{pd.to_numeric(sold['sale_value'], errors='coerce').sum():,.0f}")
            s4.metric("Total realised return", f"€{sold['total_return'].sum():+,.0f}",
                      delta=f"{sold['total_return'].sum() / pd.to_numeric(sold['purchase_value'], errors='coerce').sum() * 100:+.1f}%")

            st.divider()

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


