"""
Fetches the full list of Euronext Brussels, Amsterdam, Paris (EPA),
Borsa Italiana (BIT), Deutsche Börse (ETR) and SIX Swiss Exchange (SWX) listed equities.

Note: Euronext's official API (EWS) requires a paid commercial contract.
      Their live-site JSON endpoints require JavaScript execution and return
      empty rows when called directly.

Primary source : stockanalysis.com — reliable public lists.
Last resort    : hardcoded index constituents.
"""

import json
from pathlib import Path

import requests
import pandas as pd
from io import StringIO
import yfinance as yf

_EXCEPTIONS_FILE  = Path(__file__).parent / ".cache" / "frankfurt_exceptions.json"
_VALIDATE_BATCH   = 30   # rejected symbols to probe per fetch run

STOCKANALYSIS_URL     = "https://stockanalysis.com/list/euronext-brussels/"
STOCKANALYSIS_AMS_URL = "https://stockanalysis.com/list/euronext-amsterdam/"
STOCKANALYSIS_PAR_URL = "https://stockanalysis.com/list/euronext-paris/"
STOCKANALYSIS_MIL_URL = "https://stockanalysis.com/list/borsa-italiana/"
STOCKANALYSIS_ETR_URL = "https://stockanalysis.com/list/frankfurt-stock-exchange/"
STOCKANALYSIS_SWX_URL = "https://stockanalysis.com/list/six-swiss-exchange/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


PAGE_SIZE = 500


def _fetch_via_stockanalysis(url: str, suffix: str, mic: str, label: str,
                              fallback_fn) -> list[dict]:
    """
    Fetch all pages of a stockanalysis.com exchange list.
    Stops when a page returns fewer than PAGE_SIZE rows.
    Falls back to `fallback_fn()` on any error.
    """
    try:
        stocks: list[dict] = []
        seen: set[str] = set()
        page = 1
        while True:
            page_url = f"{url}?page={page}" if page > 1 else url
            resp = requests.get(page_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            tables = pd.read_html(StringIO(resp.text))
            if not tables:
                raise ValueError("No tables found on page")

            df = tables[0]
            if "Symbol" not in df.columns or "Company Name" not in df.columns:
                raise ValueError(f"Unexpected columns: {list(df.columns)}")

            rows_this_page = 0
            for _, row in df.iterrows():
                symbol = str(row["Symbol"]).strip()
                name   = str(row["Company Name"]).strip()
                if not symbol or symbol == "nan" or symbol in seen:
                    continue
                seen.add(symbol)
                stocks.append({"name": name, "isin": "", "ticker": f"{symbol}{suffix}", "mic": mic})
                rows_this_page += 1

            if rows_this_page < PAGE_SIZE:
                break
            page += 1

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


def fetch_paris_tickers() -> list[dict]:
    """Returns Euronext Paris (XPAR) stocks — stockanalysis.com with CAC40 fallback."""
    return _fetch_via_stockanalysis(
        STOCKANALYSIS_PAR_URL, suffix=".PA", mic="XPAR",
        label="Paris", fallback_fn=_hardcoded_cac40,
    )


def fetch_milan_tickers() -> list[dict]:
    """Returns Borsa Italiana (XMIL) stocks — stockanalysis.com with FTSE MIB fallback."""
    return _fetch_via_stockanalysis(
        STOCKANALYSIS_MIL_URL, suffix=".MI", mic="XMIL",
        label="Milan", fallback_fn=_hardcoded_ftse_mib,
    )


def _load_exceptions() -> dict[str, bool]:
    """Load {symbol: is_equity} cache from disk."""
    if _EXCEPTIONS_FILE.exists():
        try:
            return json.loads(_EXCEPTIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"P911": True, "1COV": True}  # seed with known exceptions


def _save_exceptions(data: dict[str, bool]) -> None:
    _EXCEPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _EXCEPTIONS_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _is_valid_on_yahoo(symbol: str) -> bool:
    """Quick probe: True if Yahoo Finance knows this ticker as an equity."""
    try:
        info = yf.Ticker(f"{symbol}.DE").fast_info
        return getattr(info, "last_price", None) is not None
    except Exception:
        return False


def _auto_validate(rejected: list[str], exceptions: dict[str, bool]) -> dict[str, bool]:
    """
    Check up to _VALIDATE_BATCH symbols not yet in the exceptions cache.
    Updates and returns the cache dict; caller is responsible for saving.
    """
    unchecked = [s for s in rejected if s not in exceptions][:_VALIDATE_BATCH]
    if not unchecked:
        return exceptions
    print(f"[fetch_tickers] Validating {len(unchecked)} new Frankfurt symbols against Yahoo…")
    found = []
    for sym in unchecked:
        valid = _is_valid_on_yahoo(sym)
        exceptions[sym] = valid
        if valid:
            found.append(sym)
    if found:
        print(f"[fetch_tickers] Auto-added Frankfurt exceptions: {found}")
    return exceptions


def _is_equity_symbol(symbol: str, exceptions: dict[str, bool] | None = None) -> bool:
    """
    True for symbols that look like real equities on Frankfurt/XETR.

    Real German equity tickers (DAX/MDAX/SDAX):
      - 1–4 chars, uppercase
      - At most one digit, and only as the last character (e.g. DB1, VOW3, MUV2)
      - Never start with a digit

    Rejected patterns (ETFs, warrants, structured products):
      - Start with a digit:      1YD0, 3V6, 4AB0
      - Multiple digits:         TL01, FB20, ASM0 (ends 0 = certificate series)
      - Digit not at end:        A1BC
    """
    if exceptions and exceptions.get(symbol):
        return True
    if not symbol or len(symbol) > 4 or not symbol.isupper():
        return False
    if symbol[0].isdigit():
        return False
    digits = [c for c in symbol if c.isdigit()]
    if len(digits) > 1:
        return False
    if digits and not symbol[-1].isdigit():
        return False
    if symbol.endswith("0"):
        return False
    return True


def fetch_frankfurt_tickers() -> list[dict]:
    """Returns Deutsche Börse (XETR) stocks — stockanalysis.com with DAX 40 fallback."""
    all_tickers = _fetch_via_stockanalysis(
        STOCKANALYSIS_ETR_URL, suffix=".DE", mic="XETR",
        label="Frankfurt", fallback_fn=_hardcoded_dax40,
    )
    exceptions = _load_exceptions()
    symbols     = [s["ticker"].removesuffix(".DE") for s in all_tickers]
    rejected    = [sym for sym in symbols if not _is_equity_symbol(sym, exceptions)]

    exceptions  = _auto_validate(rejected, exceptions)
    _save_exceptions(exceptions)

    filtered = [s for s in all_tickers if _is_equity_symbol(s["ticker"].removesuffix(".DE"), exceptions)]
    print(f"[fetch_tickers] Frankfurt: {len(filtered)}/{len(all_tickers)} kept after equity filter")
    return filtered


def _hardcoded_dax40() -> list[dict]:
    """DAX 40 constituents as a last-resort fallback."""
    entries = [
        ("Adidas",                  "ADS"),   ("Airbus",              "AIR"),
        ("Allianz",                 "ALV"),   ("BASF",                "BAS"),
        ("Bayer",                   "BAYN"),  ("Beiersdorf",          "BEI"),
        ("BMW",                     "BMW"),   ("Brenntag",            "BNR"),
        ("Commerzbank",             "CBK"),   ("Continental",         "CON"),
        ("Covestro",                "1COV"),  ("Daimler Truck",       "DTG"),
        ("Deutsche Bank",           "DBK"),   ("Deutsche Börse",      "DB1"),
        ("Deutsche Post",           "DHL"),   ("Deutsche Telekom",    "DTE"),
        ("E.ON",                    "EOAN"),  ("Fresenius",           "FRE"),
        ("Fresenius Medical Care",  "FME"),   ("Hannover Re",         "HNR1"),
        ("Heidelberg Materials",    "HEIG"),  ("Henkel",              "HEN3"),
        ("Infineon",                "IFX"),   ("Mercedes-Benz",       "MBG"),
        ("Merck",                   "MRK"),   ("MTU Aero Engines",    "MTX"),
        ("Münchener Rück",          "MUV2"),  ("Porsche AG",          "P911"),
        ("Porsche SE",              "PAH3"),  ("Qiagen",              "QIA"),
        ("RWE",                     "RWE"),   ("SAP",                 "SAP"),
        ("Sartorius",               "SRT3"),  ("Siemens",             "SIE"),
        ("Siemens Energy",          "ENR"),   ("Siemens Healthineers","SHL"),
        ("Symrise",                 "SY1"),   ("Volkswagen",          "VOW3"),
        ("Vonovia",                 "VNA"),   ("Zalando",             "ZAL"),
    ]
    print(f"[fetch_tickers] Using hardcoded DAX40 ({len(entries)} stocks)")
    return [{"name": n, "isin": "", "ticker": f"{t}.DE", "mic": "XETR"} for n, t in entries]


def fetch_swiss_tickers() -> list[dict]:
    """Returns SIX Swiss Exchange (XSWX) stocks — stockanalysis.com with SMI 20 fallback."""
    return _fetch_via_stockanalysis(
        STOCKANALYSIS_SWX_URL, suffix=".SW", mic="XSWX",
        label="Swiss", fallback_fn=_hardcoded_smi20,
    )


def _hardcoded_smi20() -> list[dict]:
    """SMI 20 constituents as a last-resort fallback."""
    entries = [
        ("ABB",                 "ABBN"),  ("Alcon",            "ALC"),
        ("Geberit",             "GEBN"),  ("Givaudan",         "GIVN"),
        ("Holcim",              "HOLN"),  ("Julius Baer",      "BAER"),
        ("Kühne+Nagel",         "KNIN"),  ("Lindt & Sprüngli", "LISP"),
        ("Lonza",               "LONN"),  ("Nestlé",           "NESN"),
        ("Novartis",            "NOVN"),  ("Partners Group",   "PGHN"),
        ("Richemont",           "CFR"),   ("Roche",            "ROG"),
        ("Schindler",           "SCHN"),  ("SGS",              "SGSN"),
        ("Sika",                "SIKA"),  ("Sonova",           "SOON"),
        ("Swiss Life",          "SLHN"),  ("Swiss Re",         "SREN"),
        ("Swisscom",            "SCMN"),  ("UBS",              "UBSG"),
        ("Zurich Insurance",    "ZURN"),
    ]
    print(f"[fetch_tickers] Using hardcoded SMI20 ({len(entries)} stocks)")
    return [{"name": n, "isin": "", "ticker": f"{t}.SW", "mic": "XSWX"} for n, t in entries]


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


def _hardcoded_cac40() -> list[dict]:
    """CAC 40 constituents as a last-resort fallback."""
    entries = [
        ("Air Liquide",        "AI"),    ("Airbus",           "AIR"),
        ("AXA",                "CS"),    ("BNP Paribas",      "BNP"),
        ("Bouygues",           "EN"),    ("Capgemini",        "CAP"),
        ("Carrefour",          "CA"),    ("Compagnie de Saint-Gobain", "SGO"),
        ("Crédit Agricole",    "ACA"),   ("Danone",           "BN"),
        ("Dassault Systèmes",  "DSY"),   ("Engie",            "ENGI"),
        ("EssilorLuxottica",   "EL"),    ("Hermès",           "RMS"),
        ("Kering",             "KER"),   ("Legrand",          "LR"),
        ("L'Oréal",            "OR"),    ("LVMH",             "MC"),
        ("Michelin",           "ML"),    ("Orange",           "ORA"),
        ("Pernod Ricard",      "RI"),    ("Publicis Groupe",  "PUB"),
        ("Renault",            "RNO"),   ("Safran",           "SAF"),
        ("Sanofi",             "SAN"),   ("Schneider Electric","SU"),
        ("Société Générale",   "GLE"),   ("Stellantis",       "STLAM"),
        ("STMicroelectronics", "STM"),   ("TotalEnergies",    "TTE"),
        ("Unibail-Rodamco",    "URW"),   ("Veolia",           "VIE"),
        ("Vinci",              "DG"),    ("Vivendi",          "VIV"),
        ("Worldline",          "WLN"),   ("Accor",            "AC"),
        ("ArcelorMittal",      "MT"),    ("Teleperformance",  "TEP"),
        ("Thales",             "HO"),    ("Valeo",            "FR"),
    ]
    print(f"[fetch_tickers] Using hardcoded CAC40 ({len(entries)} stocks)")
    return [{"name": n, "isin": "", "ticker": f"{t}.PA", "mic": "XPAR"} for n, t in entries]


def _hardcoded_ftse_mib() -> list[dict]:
    """FTSE MIB constituents as a last-resort fallback."""
    entries = [
        ("Amplifon",           "AMP"),   ("Assicurazioni Generali", "G"),
        ("Atlantia",           "ATL"),   ("Banca Mediolanum",  "BMED"),
        ("Banco BPM",          "BAMI"),  ("BPER Banca",        "BPE"),
        ("Buzzi",              "BZU"),   ("CNH Industrial",    "CNHI"),
        ("DiaSorin",           "DIA"),   ("ENI",               "ENI"),
        ("Enel",               "ENEL"),  ("Ferrari",           "RACE"),
        ("FinecoBank",         "FBK"),   ("Infrastrutture Wireless","INWIT"),
        ("Intesa Sanpaolo",    "ISP"),   ("Iveco Group",       "IVG"),
        ("Leonardo",           "LDO"),   ("Mediobanca",        "MB"),
        ("Moncler",            "MONC"),  ("Nexi",              "NEXI"),
        ("Pirelli",            "PIRC"),  ("Poste Italiane",    "PST"),
        ("Prysmian",           "PRY"),   ("Recordati",         "REC"),
        ("Saipem",             "SPM"),   ("Snam",              "SRG"),
        ("STMicroelectronics", "STMMI"), ("Telecom Italia",    "TIT"),
        ("Tenaris",            "TEN"),   ("Terna",             "TRN"),
        ("UniCredit",          "UCG"),   ("Unipol",            "UNI"),
        ("Webuild",            "WBD"),   ("Brunello Cucinelli","BC"),
        ("De' Longhi",         "DLG"),   ("Interpump Group",   "IP"),
        ("OVS",                "OVS"),   ("Salvatore Ferragamo","SFER"),
        ("Tod's",              "TOD"),   ("Tamburi",           "TIP"),
    ]
    print(f"[fetch_tickers] Using hardcoded FTSE MIB ({len(entries)} stocks)")
    return [{"name": n, "isin": "", "ticker": f"{t}.MI", "mic": "XMIL"} for n, t in entries]
