"""
Fetches the full list of Euronext Brussels listed equities.

Note: Euronext's official API (EWS) requires a paid commercial contract.
      Their live-site JSON endpoints require JavaScript execution and return
      empty rows when called directly.

Primary source : stockanalysis.com — reliable public list of ~125 XBRU equities.
Last resort    : hardcoded BEL20 constituents.
"""

import requests
import pandas as pd
from io import StringIO

STOCKANALYSIS_URL = "https://stockanalysis.com/list/euronext-brussels/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def fetch_brussels_tickers() -> list[dict]:
    """
    Returns a list of dicts with keys: name, isin, ticker, mic.
    Tries stockanalysis.com first, falls back to hardcoded BEL20.
    """
    try:
        resp = requests.get(STOCKANALYSIS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        if not tables:
            raise ValueError("No tables found on page")

        df = tables[0]
        if "Symbol" not in df.columns or "Company Name" not in df.columns:
            raise ValueError(f"Unexpected columns: {list(df.columns)}")

        stocks = []
        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).strip()
            name   = str(row["Company Name"]).strip()
            if not symbol or symbol == "nan":
                continue
            stocks.append({
                "name":   name,
                "isin":   "",
                "ticker": f"{symbol}.BR",
                "mic":    "XBRU",
            })

        if stocks:
            print(f"[fetch_tickers] Loaded {len(stocks)} stocks from stockanalysis.com")
            return stocks

    except Exception as e:
        print(f"[fetch_tickers] stockanalysis.com failed: {e}. Falling back to BEL20.")

    return _hardcoded_bel20()


def _hardcoded_bel20() -> list[dict]:
    """BEL20 constituents as a last-resort fallback."""
    entries = [
        ("AB InBev",        "ABI"),  ("Ageas",          "AGS"),
        ("Ahold Delhaize",  "AD"),   ("Aperam",         "APAM"),
        ("Argenx",          "ARGX"), ("Cofinimmo",      "COFB"),
        ("Colruyt",         "COLR"), ("D'Ieteren",      "DIE"),
        ("Elia",            "ELI"),  ("GBL",            "GBLB"),
        ("ING",             "ING"),  ("KBC",            "KBC"),
        ("Lotus Bakeries",  "LOTB"), ("Melexis",        "MELE"),
        ("Proximus",        "PROX"), ("Sofina",         "SOF"),
        ("Solvay",          "SOLB"), ("UCB",            "UCB"),
        ("Umicore",         "UMI"),  ("WDP",            "WDP"),
    ]
    print(f"[fetch_tickers] Using hardcoded BEL20 ({len(entries)} stocks)")
    return [{"name": n, "isin": "", "ticker": f"{t}.BR", "mic": "XBRU"} for n, t in entries]


if __name__ == "__main__":
    tickers = fetch_brussels_tickers()
    print(f"\nTotal: {len(tickers)} stocks")
    for t in tickers[:10]:
        print(t)
