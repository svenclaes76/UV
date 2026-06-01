"""
Fetches the full list of Euronext Brussels listed equities.

Primary source: stockanalysis.com (scrapes ~125 common stocks, no auth required).
Fallback: hardcoded BEL20 list.
"""

import requests
import pandas as pd
from io import StringIO

STOCKANALYSIS_URL = "https://stockanalysis.com/list/euronext-brussels/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


def fetch_brussels_tickers() -> list[dict]:
    """
    Downloads all Euronext Brussels-listed common stocks.
    Returns a list of dicts with keys: name, isin, ticker, mic.
    """
    try:
        resp = requests.get(STOCKANALYSIS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        if not tables:
            raise ValueError("No tables found on page")

        df = tables[0]
        # Expected columns: No., Symbol, Company Name, Market Cap, ...
        if "Symbol" not in df.columns or "Company Name" not in df.columns:
            raise ValueError(f"Unexpected columns: {list(df.columns)}")

        stocks = []
        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).strip()
            name = str(row["Company Name"]).strip()
            if not symbol or symbol == "nan":
                continue
            stocks.append({
                "name": name,
                "isin": "",
                "ticker": f"{symbol}.BR",
                "mic": "XBRU",
            })

        if stocks:
            print(f"[fetch_tickers] Loaded {len(stocks)} stocks from stockanalysis.com")
            return stocks

    except Exception as e:
        print(f"[fetch_tickers] Primary source failed: {e}. Falling back to BEL20.")

    return _hardcoded_bel20()


def _hardcoded_bel20() -> list[dict]:
    """BEL20 constituents as a fallback."""
    entries = [
        ("AB InBev", "ABI"), ("Ageas", "AGS"), ("Ahold Delhaize", "AD"),
        ("Aperam", "APAM"), ("Argenx", "ARGEN"), ("Cofinimmo", "COFB"),
        ("Colruyt", "COLR"), ("D'Ieteren", "DIE"), ("Elia", "ELI"),
        ("GBL", "GBLB"), ("ING", "ING"), ("KBC", "KBC"),
        ("Lotus Bakeries", "LOTB"), ("Melexis", "MELE"), ("Proximus", "PROX"),
        ("Sofina", "SOF"), ("Solvay", "SOLB"), ("UCB", "UCB"),
        ("Umicore", "UMI"), ("WDP", "WDP"),
    ]
    return [{"name": n, "isin": "", "ticker": f"{t}.BR", "mic": "XBRU"} for n, t in entries]


if __name__ == "__main__":
    tickers = fetch_brussels_tickers()
    print(f"Found {len(tickers)} stocks")
    for t in tickers[:10]:
        print(t)
