"""Column help texts and pure value formatters shared across pages."""
import pandas as pd

# ── Column help texts (shown as header tooltips and on the Help page) ─────────
COLUMN_HELP = {
    # ── Core ──────────────────────────────────────────────────────────────────
    "★":             "Watchlist — check to add this stock to your personal watchlist.",
    "Company":       "Full company name as reported by the exchange.",
    "Ticker":        "Exchange ticker symbol (suffix indicates the exchange: .BR Brussels · .AS Amsterdam · .PA Paris · .MI Milan · .DE Frankfurt · .SW Zurich).",
    "Price":         "Current market price in the stock's local currency.",
    "UV":         (
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

_HINT_WATCHLIST = "click a row to view details · star in popup to add to watchlist"


def fmt_eur(v) -> str:
    """Format a value as a Euro price, or '—' if missing."""
    return f"€{v:.2f}" if pd.notna(v) else "—"


def fmt_div_flag(v) -> str:
    return {"At Risk": "⚠️ At Risk", "OK": "✅ OK", "": "—"}.get(str(v) if pd.notna(v) else "", "—")


def safe_pct(numerator: float, denominator: float) -> float:
    """Return numerator/denominator*100, or 0 if denominator is zero."""
    return numerator / denominator * 100 if denominator else 0


def f_str(v):
    """Pass through a value, or '—' if missing (for text table columns)."""
    return v if pd.notna(v) else "—"
