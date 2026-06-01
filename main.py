"""Entry point: fetch tickers → screen → generate HTML report."""

import webbrowser
from fetch_tickers import fetch_brussels_tickers
from screener import run_screener
from report import generate_html

OUTPUT = "report.html"

if __name__ == "__main__":
    print("Step 1/3  Fetching Euronext Brussels ticker list...")
    stocks = fetch_brussels_tickers()
    print(f"          {len(stocks)} stocks found\n")

    print("Step 2/3  Fetching fundamentals & scoring...")
    df = run_screener(stocks)
    print(f"          Done. Top 5 by value score:")
    print(df[["Name", "Ticker", "Value Score"]].head())
    print()

    print("Step 3/3  Generating HTML report...")
    generate_html(df, OUTPUT)

    webbrowser.open(OUTPUT)
