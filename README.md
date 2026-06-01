# UV — Undervalued

A value screener and portfolio tracker for Euronext Brussels-listed stocks.

## What it does

- **Screener** — fetches fundamentals for ~125 Brussels stocks via yfinance and ranks them by a composite value score (P/E, P/B, EV/EBITDA, Debt/Equity, Dividend Yield). Higher score = relatively cheaper.
- **Portfolio tracker** — import your positions from an Excel file, then track live prices, analyst targets, Graham numbers, P&L, dividends, and sold positions in one dashboard.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Install

```bash
uv sync
```

Or with pip:

```bash
pip install streamlit pandas yfinance openpyxl streamlit-autorefresh
```

## Run

**Web app (recommended)**

```bash
streamlit run app.py
```

**CLI report** — generates a standalone `report.html` and opens it in your browser:

```bash
python main.py
```

## Portfolio import

On first launch, upload your broker Excel file (sheet name: `beleggingen`). The app reads open positions, sold positions, and dividend history automatically. Data is cached locally in `.cache/` and never leaves your machine.

## How the value score works

Each metric is percentile-ranked across the full Brussels universe (0–100). The final score is the average of all five percentiles. Scores are cached for 1 hour to avoid hammering the yfinance API.

> Not financial advice.
