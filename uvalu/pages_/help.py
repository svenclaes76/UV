"""Help page — column reference tables, one tab per section."""
import streamlit as st

from uvalu.formatting import COLUMN_HELP


def render():
    """Full-page column reference, one tab per section."""
    sections = {
        "Core":             ["★", "Company", "Ticker", "Price", "Analyst Target", "UV",
                             "MoS %", "TER %", "Score"],
        "Valuation":        ["Graham #", "PE Fair Val", "EPV",
                             "DDM (1-stage)", "DDM (2-stage)"],
        "Risk & Size":      ["Risk Score", "Mkt Cap", "Beta", "Debt/Equity"],
        "Multiples":        ["P/E", "P/B", "EV/EBITDA"],
        "Quality":          ["ROE %", "ROA %", "Op Margin %", "FCF Yield %"],
        "Growth":           ["Rev Growth %", "EPS Growth %"],
        "Dividends":        ["Div Yield", "5yr Avg Yield", "Payout Ratio",
                             "Cash Payout", "Div Coverage", "Div Flag"],
        "Portfolio Risk":   [],
    }

    def _help_table(rows: list[tuple[str, str]]) -> None:
        st.markdown("\n".join(
            ["| Column | Description |", "|:--|:--|"]
            + [f"| `{col}` | {desc} |" for col, desc in rows]
        ))

    tabs = st.tabs(list(sections.keys()))
    for tab, (section, cols) in zip(tabs, sections.items()):
        with tab:
            if section == "Portfolio Risk":
                _risk_help_rows = [
                    ("Composite score",   "Weighted aggregate of six sub-scores (0–100, higher = more risk). Sub-scores: Concentration 25%, Volatility 20%, Tail risk 20%, Factor exposure 15%, Fundamental 15%, Income risk 5%."),
                    ("Position Weight",   "Position value as a percentage of total portfolio. Above 10% is concentrated; above 15% triggers a hard rebalancing flag."),
                    ("Beta",              "Market sensitivity estimated by regression against the benchmark index. Above 1.2 amplifies market swings; below 0.8 is defensive. A portfolio beta above 1.5 triggers a hard flag."),
                    ("VaR 95% (1d)",      "Maximum expected 1-day loss at 95% confidence using historical simulation. Interpreted as: on average, only 1 trading day in 20 should lose more than this amount."),
                    ("CVaR 95% (1d)",     "Expected Shortfall — the average loss on the worst 5% of days. Captures tail risk that VaR alone understates."),
                    ("MDD",               "Maximum drawdown: the largest peak-to-trough decline observed over the measurement period (1y / 3y / 5y windows)."),
                    ("HHI",               "Herfindahl-Hirschman Index — sum of squared portfolio weights. Ranges from near 0 (fully diversified) to 1 (single position). Above 0.18 is considered highly concentrated."),
                    ("Factor loading",    "Sensitivity of portfolio returns to a systematic risk factor (Fama-French 5-factor model + momentum). A loading above ±1.5 signals a concentrated factor bet."),
                    ("R²",                "Fraction of portfolio return variance explained by the factor model. Above 0.6 means the portfolio is predominantly factor-driven rather than stock-specific."),
                    ("Alpha",             "Annualised return above what the factor model predicts. Positive alpha suggests stock selection adds value beyond systematic factor exposure."),
                    ("Portfolio Yield",   "Total expected annual dividend income divided by current portfolio value. Computed from each holding's dividend rate and share count."),
                    ("Weighted DGR",      "Income-weighted dividend growth rate — proxy for how fast the dividend stream is growing. Below ~2.5% means purchasing power of income erodes in real terms."),
                    ("Top-3 cut (50%)",   "Stress scenario: income impact if the three largest dividend payers each cut their dividend by 50%. Quantifies income concentration risk."),
                    ("Hard trigger",      "A threshold breach that materially increases risk and requires prompt action (e.g. position >20%, portfolio beta >1.5, or a Critical-rated position)."),
                    ("Soft trigger",      "An advisory signal worth monitoring and planning around, but not requiring same-day action (e.g. sector overweight, Sharpe below 1.0, or a High-rated position)."),
                    ("Monte Carlo P5",    "5th percentile portfolio value after simulating 10,000 random return paths — the worst-case outcome at 5% probability over the stated horizon."),
                    ("P(loss)",           "Probability of a negative total return over the simulation horizon, derived from the fraction of Monte Carlo paths that finish below the starting value."),
                ]
                _help_table(_risk_help_rows)
            else:
                _help_table([(col, COLUMN_HELP[col])
                             for col in cols if COLUMN_HELP.get(col)])
