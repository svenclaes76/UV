"""
Fetches the full list of Euronext Brussels, Amsterdam, Paris (EPA),
Borsa Italiana (BIT), Deutsche Börse (ETR) and SIX Swiss Exchange (SWX) listed equities.

Note: Euronext's official API (EWS) requires a paid commercial contract.
      Their live-site JSON endpoints require JavaScript execution and return
      empty rows when called directly.

Primary source : stockanalysis.com — reliable public lists.
Last resort    : hardcoded index constituents.

Lists are cached per exchange in .cache/ticker_lists/ (EX-W1a): a universe
rebuild reads the cached list instead of scraping (the scrapes were 55 of the
61 seconds of a median rebuild), a stale list is served while a background
thread refreshes it, and a scrape that comes back much smaller than the last
good list is rejected rather than shrinking the universe.
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import pandas as pd
from io import StringIO
import yfinance as yf

from uvalu import logkit

_log = logkit.get_logger("uvalu.tickers")

_EXCEPTIONS_FILE  = Path(__file__).parent / ".cache" / "frankfurt_exceptions.json"
_VALIDATE_BATCH   = 30   # rejected symbols to probe per fetch run

_LIST_CACHE_DIR      = Path(__file__).parent / ".cache" / "ticker_lists"
LIST_TTL_HOURS       = 24     # a list younger than this is used as-is
LIST_RETRY_MINUTES   = 60     # after a failed or rejected scrape, wait this long before trying again
LIST_SHRINK_GUARD    = 0.70   # a new list under this share of the last good one is rejected
BACKGROUND_REFRESH   = True   # refresh a stale list off the caller's thread (tests set False)

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
MAX_PAGES = 50   # hard safety cap — well above any real exchange's page count (Frankfurt, the largest, is 22)


def _scrape_stockanalysis(url: str, suffix: str, mic: str, label: str) -> "list[dict] | None":
    """
    Fetch all pages of a stockanalysis.com exchange list; None on any error
    or an empty result.
    Stops when a page adds no symbols not already seen (primary signal — a page
    short of PAGE_SIZE always qualifies, but some listings sit right at/above
    PAGE_SIZE while the site's ?page= param is a no-op past the real last page
    and just re-serves the same rows forever; SIX Swiss Exchange does exactly
    this at 512 rows, which used to spin the loop indefinitely). MAX_PAGES is
    a hard backstop in case a listing somehow keeps producing "new" rows.
    """
    _endpoint = f"stockanalysis.{label.lower()}"
    try:
        with logkit.external_call(_endpoint, logger="uvalu.tickers") as _call:
            stocks: list[dict] = []
            seen: set[str] = set()
            page = 1
            while True:
                page_url = f"{url}?page={page}" if page > 1 else url
                resp = requests.get(page_url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                tables = pd.read_html(StringIO(resp.text), flavor='html5lib')
                if not tables:
                    raise ValueError("No tables found on page")

                df = tables[0]
                if "Symbol" not in df.columns or "Company Name" not in df.columns:
                    raise ValueError(f"Unexpected columns: {list(df.columns)}")

                new_symbols = 0
                for _, row in df.iterrows():
                    symbol = str(row["Symbol"]).strip()
                    name   = str(row["Company Name"]).strip()
                    if not symbol or symbol == "nan" or symbol in seen:
                        continue
                    seen.add(symbol)
                    new_symbols += 1
                    stocks.append({"name": name, "isin": "", "ticker": f"{symbol}{suffix}", "mic": mic})

                if len(df) < PAGE_SIZE or new_symbols == 0 or page >= MAX_PAGES:
                    break
                page += 1

            _call.note(pages=page, stocks=len(stocks),
                       status="ok" if stocks else "empty")
        return stocks or None
    except Exception:
        return None  # external_call() already logged external_call.failed


def _fetch_via_stockanalysis(url: str, suffix: str, mic: str, label: str,
                              fallback_fn) -> list[dict]:
    """A fresh scrape of a stockanalysis.com list, or `fallback_fn()` when it
    fails or comes back empty. Uncached: the fetch_*_tickers functions go
    through _cached_list instead."""
    stocks = _scrape_stockanalysis(url, suffix, mic, label)
    if stocks:
        return stocks
    _log.info("using hardcoded fallback list for %s", label,
              extra={"event": "fallback", "endpoint": f"stockanalysis.{label.lower()}"})
    return fallback_fn()


# ── Ticker-list cache (EX-W1a) ────────────────────────────────────────────────

_refresh_lock = threading.Lock()
_refreshing: set[str] = set()


def _list_file(label: str) -> Path:
    return _LIST_CACHE_DIR / f"{label.lower().replace(' ', '_')}.json"


def _read_list(label: str) -> "dict | None":
    try:
        entry = json.loads(_list_file(label).read_text(encoding="utf-8"))
        return entry if isinstance(entry, dict) else None
    except (OSError, ValueError):
        return None


def _write_list(label: str, entry: dict) -> None:
    """Atomic write: a crash mid-write never leaves a truncated list."""
    path = _list_file(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _age(ts: "str | None") -> "timedelta | None":
    try:
        when = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - when


def _refresh_list(label: str, url: str, suffix: str, mic: str) -> "list[dict] | None":
    """Scrape once and store the result if it is acceptable. Returns the new
    list, or None when the scrape failed or was rejected by the shrink guard.
    The last good list is kept either way, and the attempt is recorded so the
    next one waits LIST_RETRY_MINUTES."""
    entry = _read_list(label) or {}
    last = entry.get("stocks") or []
    now = datetime.now(timezone.utc).isoformat()
    stocks = _scrape_stockanalysis(url, suffix, mic, label)
    if stocks and (not last or len(stocks) >= LIST_SHRINK_GUARD * len(last)):
        _write_list(label, {"label": label, "source": "stockanalysis", "fetched_at": now,
                            "checked_at": now, "stocks": stocks})
        _log.info("ticker list refreshed for %s (%d stocks)", label, len(stocks),
                  extra={"event": "tickers.refreshed", "list": label, "stocks": len(stocks)})
        return stocks
    if stocks:
        _log.warning("ticker list for %s shrank from %d to %d; keeping the last good list",
                     label, len(last), len(stocks),
                     extra={"event": "tickers.shrunk", "list": label, "last": len(last), "new": len(stocks)})
    else:
        _log.warning("ticker list refresh failed for %s", label,
                     extra={"event": "tickers.refresh_failed", "list": label, "kept": len(last)})
    _write_list(label, {**entry, "label": label, "checked_at": now, "stocks": last,
                        "source": entry.get("source") or ("stockanalysis" if last else "fallback")})
    return None


def _refresh_in_background(label: str, url: str, suffix: str, mic: str) -> None:
    """Refresh a stale list without making the caller (a universe rebuild)
    wait for the scrape. One refresh per list at a time."""
    with _refresh_lock:
        if label in _refreshing:
            return
        _refreshing.add(label)

    def _run() -> None:
        try:
            _refresh_list(label, url, suffix, mic)
        finally:
            with _refresh_lock:
                _refreshing.discard(label)

    if BACKGROUND_REFRESH:
        logkit.spawn(_run, name=f"ticker_list_refresh:{label}")
    else:
        _run()


def _cached_list(url: str, suffix: str, mic: str, label: str, fallback_fn) -> list[dict]:
    """The exchange's ticker list, from the cache. A fresh list is returned
    as-is; a stale one is returned at once and refreshed in the background.
    With no usable list yet, the scrape runs now; if it fails, the hardcoded
    fallback is used and the failure throttles the next attempt."""
    entry = _read_list(label) or {}
    stocks = entry.get("stocks") or []
    ttl, retry = timedelta(hours=LIST_TTL_HOURS), timedelta(minutes=LIST_RETRY_MINUTES)
    checked = _age(entry.get("checked_at"))
    recently_tried = checked is not None and checked < retry
    if stocks:
        fetched = _age(entry.get("fetched_at"))
        if not (fetched is not None and fetched < ttl) and not recently_tried:
            _refresh_in_background(label, url, suffix, mic)
        return stocks
    if not recently_tried:
        fresh_list = _refresh_list(label, url, suffix, mic)
        if fresh_list:
            return fresh_list
    _log.info("using hardcoded fallback list for %s", label,
              extra={"event": "fallback", "endpoint": f"stockanalysis.{label.lower()}"})
    return fallback_fn()


def list_status() -> dict:
    """{label: {"fetched_at", "stocks", "source"}} of every cached list, for
    the build's log line (lineage: which list date a build used)."""
    out = {}
    if not _LIST_CACHE_DIR.exists():
        return out
    for path in sorted(_LIST_CACHE_DIR.glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[entry.get("label") or path.stem] = {"fetched_at": entry.get("fetched_at"),
                                                "stocks": len(entry.get("stocks") or []),
                                                "source": entry.get("source")}
    return out


def fetch_brussels_tickers() -> list[dict]:
    """Returns Brussels (XBRU) stocks — stockanalysis.com with BEL20 fallback."""
    return _cached_list(
        STOCKANALYSIS_URL, suffix=".BR", mic="XBRU",
        label="Brussels", fallback_fn=_hardcoded_bel20,
    )


def fetch_amsterdam_tickers() -> list[dict]:
    """Returns Amsterdam (XAMS) stocks — stockanalysis.com with AEX25 fallback."""
    return _cached_list(
        STOCKANALYSIS_AMS_URL, suffix=".AS", mic="XAMS",
        label="Amsterdam", fallback_fn=_hardcoded_aex25,
    )


def _build_hardcoded(pairs: list[tuple[str, str]], suffix: str, mic: str, label: str) -> list[dict]:
    _log.debug("using hardcoded %s list (%d stocks)", label, len(pairs),
               extra={"event": "fallback", "list": label})
    return [{"name": n, "isin": "", "ticker": f"{t}{suffix}", "mic": mic} for n, t in pairs]


def _hardcoded_bel20() -> list[dict]:
    return _build_hardcoded([
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
    ], ".BR", "XBRU", "BEL20")


def fetch_paris_tickers() -> list[dict]:
    """Returns Euronext Paris (XPAR) stocks — stockanalysis.com with CAC40 fallback."""
    return _cached_list(
        STOCKANALYSIS_PAR_URL, suffix=".PA", mic="XPAR",
        label="Paris", fallback_fn=_hardcoded_cac40,
    )


def fetch_milan_tickers() -> list[dict]:
    """Returns Borsa Italiana (XMIL) stocks — stockanalysis.com with FTSE MIB fallback."""
    return _cached_list(
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
    _log.debug("validating %d new Frankfurt symbols against Yahoo", len(unchecked),
               extra={"event": "tickers.validate", "count": len(unchecked)})
    found = []
    for sym in unchecked:
        valid = _is_valid_on_yahoo(sym)
        exceptions[sym] = valid
        if valid:
            found.append(sym)
    if found:
        _log.info("auto-added Frankfurt equity exceptions: %s", found,
                  extra={"event": "tickers.validate", "added": found})
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
    all_tickers = _cached_list(
        STOCKANALYSIS_ETR_URL, suffix=".DE", mic="XETR",
        label="Frankfurt", fallback_fn=_hardcoded_dax40,
    )
    exceptions = _load_exceptions()
    symbols     = [s["ticker"].removesuffix(".DE") for s in all_tickers]
    rejected    = [sym for sym in symbols if not _is_equity_symbol(sym, exceptions)]

    exceptions  = _auto_validate(rejected, exceptions)
    _save_exceptions(exceptions)

    filtered = [s for s in all_tickers if _is_equity_symbol(s["ticker"].removesuffix(".DE"), exceptions)]
    _log.debug("Frankfurt: kept %d/%d after equity filter", len(filtered), len(all_tickers),
               extra={"event": "tickers.filter", "kept": len(filtered), "total": len(all_tickers)})
    return filtered


def _hardcoded_dax40() -> list[dict]:
    return _build_hardcoded([
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
    ], ".DE", "XETR", "DAX40")


def fetch_swiss_tickers() -> list[dict]:
    """Returns SIX Swiss Exchange (XSWX) stocks — stockanalysis.com with SMI 20 fallback."""
    return _cached_list(
        STOCKANALYSIS_SWX_URL, suffix=".SW", mic="XSWX",
        label="Swiss", fallback_fn=_hardcoded_smi20,
    )


def _hardcoded_smi20() -> list[dict]:
    return _build_hardcoded([
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
    ], ".SW", "XSWX", "SMI20")


def _hardcoded_aex25() -> list[dict]:
    return _build_hardcoded([
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
    ], ".AS", "XAMS", "AEX25")


def _hardcoded_cac40() -> list[dict]:
    return _build_hardcoded([
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
    ], ".PA", "XPAR", "CAC40")


def _hardcoded_ftse_mib() -> list[dict]:
    return _build_hardcoded([
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
    ], ".MI", "XMIL", "FTSE MIB")
