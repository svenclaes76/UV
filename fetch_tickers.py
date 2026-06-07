"""
Fetches the full list of Euronext Brussels and Amsterdam listed equities.

Note: Euronext's official API (EWS) requires a paid commercial contract.
      Their live-site JSON endpoints require JavaScript execution and return
      empty rows when called directly.

Primary source : stockanalysis.com — reliable public lists.
Last resort    : hardcoded BEL20 / AEX25 constituents.
"""

import requests
import pandas as pd
from io import StringIO

STOCKANALYSIS_URL     = "https://stockanalysis.com/list/euronext-brussels/"
STOCKANALYSIS_AMS_URL = "https://stockanalysis.com/list/euronext-amsterdam/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def _fetch_via_stockanalysis(url: str, suffix: str, mic: str, label: str,
                              fallback_fn) -> list[dict]:
    """
    Shared fetch logic for any stockanalysis.com exchange list.
    On failure falls back to `fallback_fn()`.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
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
            stocks.append({"name": name, "isin": "", "ticker": f"{symbol}{suffix}", "mic": mic})

        if stocks:
            print(f"[fetch_tickers] Loaded {len(stocks)} {label} stocks from stockanalysis.com")
            return stocks

    except Exception as e:
        print(f"[fetch_tickers] stockanalysis.com {label} failed: {e}. Using fallback.")

    return fallback_fn()


def fetch_brussels_tickers() -> list[dict]:
    """Returns Brussels (XBRU) stocks — stockanalysis.com with BEL20 fallback."""
    return _fetch_via_stockanalysis(
        STOCKANALYSIS_URL, suffix=".BR", mic="XBRU",
        label="Brussels", fallback_fn=_hardcoded_bel20,
    )


def fetch_amsterdam_tickers() -> list[dict]:
    """Returns Amsterdam (XAMS) stocks — stockanalysis.com with AEX25 fallback."""
    return _fetch_via_stockanalysis(
        STOCKANALYSIS_AMS_URL, suffix=".AS", mic="XAMS",
        label="Amsterdam", fallback_fn=_hardcoded_aex25,
    )


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


def _hardcoded_aex25() -> list[dict]:
    """AEX25 constituents as a last-resort fallback."""
    entries = [
        ("ASML",            "ASML"),  ("Shell",           "SHEL"),
        ("ING",             "INGA"),  ("Heineken",        "HEIA"),
        ("Unilever",        "UNA"),   ("Philips",         "PHIA"),
        ("ABN AMRO",        "ABN"),   ("Aegon",           "AGN"),
        ("Akzo Nobel",      "AKZA"),  ("NN Group",        "NN"),
        ("Wolters Kluwer",  "WKL"),   ("Randstad",        "RAND"),
        ("ArcelorMittal",   "MT"),    ("DSM-Firmenich",   "DSFIR"),
        ("Adyen",           "ADYEN"), ("ASR Nederland",   "ASRNL"),
        ("Signify",         "LIGHT"), ("Flow Traders",    "FLOW"),
        ("Fugro",           "FUR"),   ("Corbion",         "CRBN"),
        ("OCI",             "OCI"),   ("SBM Offshore",    "SBMO"),
        ("Aalberts",        "AALB"),  ("Besi",            "BESI"),
        ("Just Eat",        "TKWY"),
    ]
    print(f"[fetch_tickers] Using hardcoded AEX25 ({len(entries)} stocks)")
    return [{"name": n, "isin": "", "ticker": f"{t}.AS", "mic": "XAMS"} for n, t in entries]
