"""Which listings make up the public coverage universe.

Model M2 (V2) kept home listings only: the company's country is the
exchange's country. That dropped European companies registered in another
country than their exchange (Airbus, Stellantis and STMicro are Dutch,
ArcelorMittal is from Luxembourg, Shell and Unilever on Amsterdam are UK).

Exchange expansion EX-W4 (EX-4 to EX-8, decisions D1–D3, architecture
review A2/A3) replaces it with **one line per company, on its primary
listing** among the enabled exchanges:

1. the company is registered in a European country (D3) or is on the
   allow-list (D2);
2. among that company's lines it is the home-exchange line, or, if there is
   none, the most-traded line in EUR (D1). The choice is saved in
   ``.cache/listing_choice.json`` and only switches when another line has
   traded at least SWITCH_FACTOR times more in two checks at least
   SWITCH_CONFIRM_DAYS apart (A3); a home line is fixed;
3. it trades (a confirmed zero average volume is dormant).

"Same company" (EX-5) = same normalised name, same country and same share
class, and share counts within 5% of each other (or one missing). A line
left out records why (EX-8): not_european, secondary_listing, dormant, fund,
country_unknown. A user's own holding on any line is still scored, as one
of their extra tickers, against this universe (PER-2).

No Streamlit import; unit-tested in tests/test_universe.py.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from uvalu import exchanges, logkit

_log = logkit.get_logger("uvalu.universe")

EXCHANGE_COUNTRY: dict[str, str] = {e.suffix: e.country for e in exchanges.EXCHANGES}

# D3: the EEA, the UK, Switzerland, the Crown dependencies, Gibraltar, Monaco
# and Liechtenstein, by the provider's country name.
EUROPE = frozenset({
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Czechia",
    "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Iceland",
    "Ireland", "Italy", "Latvia", "Liechtenstein", "Lithuania", "Luxembourg", "Malta",
    "Netherlands", "Norway", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia",
    "Spain", "Sweden", "Switzerland", "United Kingdom",
    "Jersey", "Guernsey", "Isle of Man", "Gibraltar", "Monaco",
})

# D2: companies registered outside Europe whose primary listing really is in
# Europe. Reviewed by hand; starts small.
ALLOW_LIST: dict[str, str] = {
    "HAFNI.OL": "Hafnia: registered in Singapore, primary listing Oslo",
    "BWLPG.OL": "BW LPG: registered in Singapore, primary listing Oslo (OBX member)",
}

REASONS = ("not_european", "secondary_listing", "dormant", "fund", "country_unknown")

LISTING_CHOICE_FILE = Path(__file__).resolve().parent.parent / ".cache" / "listing_choice.json"
SWITCH_FACTOR = 2.0        # A3: another line must trade this many times more ...
SWITCH_CONFIRM_DAYS = 7    # ... in two checks at least this many days apart
SHARES_TOLERANCE = 0.05    # EX-5: share counts within 5% are the same share line

_FUND_TYPES = {"ETF", "MUTUALFUND", "FUND"}

# A second trading line of the same shares on the same exchange: SIX's
# "2. Linie" buy-back lines, Euronext's "USD" lines. Never the primary line.
_SECOND_LINE_NAME = re.compile(r"\b2[.,]\s*linie\b|\susd$", re.IGNORECASE)
# Borsa Italiana's Global Equity Market: "1"-prefixed Milan lines of shares
# whose primary listing is elsewhere (997 in the 23 October 2026 cache, one of
# them Italian, itself a cross-listing). Never a primary line.
_GEM_LINE = re.compile(r"^\d.*\.MI$")

# A line away from the company's home exchange stands as its primary listing
# only when it trades at least this much a day (EUR): a thin cross-line (HSBC
# or Novo Nordisk on Xetra, Medtronic or Chubb in Frankfurt, Ferrovial on
# Xetra) is not where the company's shares are priced, and the company waits
# for its home exchange. No floor when the company's country has no exchange
# in the registry (Solutions 30 in Paris, from Luxembourg), or when both the
# line and the home exchange are Euronext markets, one market group (Onward
# Medical, Dutch, in Brussels). Set on the 23 October 2026 cache: real dual
# listings trade far above it (Shell on Amsterdam EUR 202M, ArcelorMittal
# EUR 89M).
NON_HOME_MIN_VALUE_EUR = 1_000_000
EURONEXT_SUFFIXES = frozenset({".BR", ".AS", ".PA", ".MI", ".OL", ".LS", ".IR", ".AT"})

# Legal-form words dropped from company names (EX-5).
_LEGAL_FORMS = {
    "sa", "ag", "se", "nv", "plc", "asa", "ab", "oyj", "spa", "ltd", "limited", "inc",
    "corp", "corporation", "co", "company", "holding", "holdings", "group", "publ",
    "as", "a/s", "bv", "kgaa", "gmbh", "sca", "sab", "oy", "hf", "srl", "s", "a", "p",
    "the", "de", "cv", "ord", "reg", "n", "v",
}


# EX-35: what the public universe is made of, for the signal history: the
# coverage rule and the enabled exchanges. A build whose fingerprint differs
# from the last logged one marks its signal changes as `universe_change`.
COVERAGE_RULE = "primary-listing-1"   # EX-W4; bump when the coverage rule changes


def fingerprint(enabled_keys) -> str:
    """Short stable id of the coverage rule and the enabled exchanges."""
    import hashlib
    payload = COVERAGE_RULE + "|" + ",".join(sorted(str(k) for k in enabled_keys))
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def exchange_country(ticker: str) -> str | None:
    """The country of the ticker's exchange if that exchange is covered, or
    None (a planned exchange isn't part of the public universe yet)."""
    ex = exchanges.for_ticker(ticker)
    return ex.country if ex and ex.key in exchanges.BY_KEY else None


def is_home_listing(ticker: str, country: object) -> bool:
    """True when `country` (the company's, from the provider) is the country
    of the ticker's exchange. Unknown country → False."""
    home = exchange_country(ticker)
    return bool(home) and isinstance(country, str) and country.strip() == home


def is_european(ticker: str, country: object) -> bool:
    """D2/D3: registered in Europe, or on the allow-list."""
    return ticker in ALLOW_LIST or (isinstance(country, str) and country.strip() in EUROPE)


def known_foreign(ticker: str, country: object) -> bool:
    """True when the company's country is known and outside Europe (and the
    line isn't allow-listed): such a listing never enters the universe, so it
    needn't be fetched for it. An unknown country still gets fetched. A
    European company's line on another country's exchange is fetched: it may
    be the company's primary listing (EX-4)."""
    return isinstance(country, str) and bool(country.strip()) and not is_european(ticker, country)


def is_dormant(average_volume: object) -> bool:
    """A confirmed zero average volume: the line doesn't trade (treasury
    shares, a dormant second line). A missing volume is not evidence of
    that and doesn't count."""
    try:
        return float(average_volume) == 0.0
    except (TypeError, ValueError):
        return False


def home_listings(stocks: list[dict], country_by_ticker: dict[str, object],
                  volume_by_ticker: dict[str, object] | None = None) -> list[dict]:
    """M2's rule: the stocks from an exchange list that are home listings and
    trade. Kept for comparison; the build uses choose_primary_lines."""
    volume_by_ticker = volume_by_ticker or {}
    return [s for s in stocks
            if is_home_listing(s["ticker"], country_by_ticker.get(s["ticker"]))
            and not is_dormant(volume_by_ticker.get(s["ticker"]))]


# ── Company identity (EX-5) ────────────────────────────────────────────────

def normalise_name(name: object) -> str:
    """Lower case, no accents or punctuation, legal-form words removed."""
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\([^)]*\)", " ", s)           # "(publ)"
    s = re.sub(r"[.,'&/\-]", " ", s)
    words = [w for w in s.split() if w not in _LEGAL_FORMS]
    return " ".join(words)


def _num(value) -> "float | None":
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


@dataclass
class Line:
    ticker: str
    name: str
    country: str
    share_class: str
    value_eur: "float | None"
    shares: "float | None"

    @property
    def company(self) -> str:
        return f"{normalise_name(self.name)}|{self.country}|{self.share_class}"

    @property
    def home(self) -> bool:
        # Any registry exchange, covered or planned: the build only passes
        # lines of enabled exchanges, and the shadow build enables them all.
        ex = exchanges.for_ticker(self.ticker)
        return bool(ex) and ex.country == self.country


def _suffix(ticker: str) -> str:
    return "." + ticker.rsplit(".", 1)[-1] if "." in ticker else ""


def _home_suffixes(country: str) -> set[str]:
    """Every registry exchange (covered or planned) in the country."""
    return {e.suffix for e in exchanges.KNOWN_BY_SUFFIX.values() if e.country == country}


def _eligible(line: Line) -> bool:
    """May this line be its company's primary listing? A home line always;
    another line when it trades NON_HOME_MIN_VALUE_EUR a day, or when the
    company's country has no exchange in the registry, or when line and home
    exchange are both Euronext markets."""
    if line.home:
        return True
    home = _home_suffixes(line.country)
    if not home or (_suffix(line.ticker) in EURONEXT_SUFFIXES and home <= EURONEXT_SUFFIXES):
        return True
    return (line.value_eur or 0) >= NON_HOME_MIN_VALUE_EUR


def _same_shares(a: "float | None", b: "float | None") -> bool:
    if not a or not b:
        return True
    return abs(a - b) / max(a, b) <= SHARES_TOLERANCE


def _clusters(lines: list[Line]) -> list[list[Line]]:
    """Lines of one company key split by share count (EX-5): a line joins the
    first cluster whose lines all have a share count within 5%."""
    out: list[list[Line]] = []
    for line in sorted(lines, key=lambda l: -(l.value_eur or 0)):
        for cluster in out:
            # EX-4 compares lines on different exchanges: two lines on one
            # exchange are share classes (ordinary and preference), never merged.
            if all(_same_shares(line.shares, other.shares)
                   and _suffix(line.ticker) != _suffix(other.ticker) for other in cluster):
                cluster.append(line)
                break
        else:
            out.append([line])
    return out


# ── Saved choices (A3) ─────────────────────────────────────────────────────

def load_choices(path: "Path | None" = None) -> dict:
    path = path or LISTING_CHOICE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_choices(choices: dict, path: "Path | None" = None) -> None:
    path = path or LISTING_CHOICE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(choices, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def secondary_lines(choices: "dict | None" = None) -> set[str]:
    """Every saved line that isn't its company's chosen line. The fetcher
    refreshes these weekly (A2)."""
    choices = load_choices() if choices is None else choices
    return {t for c in choices.values() for t in c.get("lines", []) if t != c.get("chosen")}


_secondary_cache: dict = {"mtime": None, "lines": frozenset()}


def secondary_lines_cached() -> frozenset:
    """secondary_lines() of the saved file, re-read only when it changes
    (the fetcher asks once per row)."""
    try:
        mtime = LISTING_CHOICE_FILE.stat().st_mtime
    except OSError:
        return frozenset()
    if _secondary_cache["mtime"] != mtime:
        _secondary_cache.update(mtime=mtime, lines=frozenset(secondary_lines()))
    return _secondary_cache["lines"]


def company_lines(tickers, choices: "dict | None" = None) -> set[str]:
    """Every line of the companies the tickers belong to (founder-holdings
    disclosure P1, "hide positions I own" D19): AIR.DE brings AIR.PA."""
    choices = load_choices() if choices is None else choices
    held = {str(t) for t in tickers}
    out = set(held)
    for c in choices.values():
        lines = set(c.get("lines", []))
        if lines & held:
            out |= lines
    return out


def _days(since: "str | None", today: date) -> int:
    try:
        return (today - date.fromisoformat(since)).days
    except (TypeError, ValueError):
        return 0


def _pick(cluster: list[Line], saved: "dict | None", enabled_suffixes: set[str],
          today: date) -> "tuple[Line | None, dict | None, tuple[str, str] | None]":
    """The chosen line of one company (None: none of its lines qualifies),
    its saved record (None = don't save) and a (old, new) switch if one
    happened."""
    lines = {l.ticker: l for l in cluster}
    tickers = sorted(lines)
    homes = [l for l in cluster if l.home]
    if homes:   # A3: a home line is fixed, no measurement
        chosen = max(homes, key=lambda l: l.value_eur or 0)
        old = (saved or {}).get("chosen")
        record = {"chosen": chosen.ticker, "lines": tickers, "reason": "home",
                  "since": (saved or {}).get("since") if old == chosen.ticker else today.isoformat()}
        return chosen, record, ((old, chosen.ticker) if old and old != chosen.ticker else None)

    cluster = [l for l in cluster if _eligible(l)]
    if not cluster:   # its primary listing is elsewhere: none of these lines
        return None, None, None
    lines = {l.ticker: l for l in cluster}
    by_value = sorted(cluster, key=lambda l: -(l.value_eur or 0))
    top = by_value[0]
    old = (saved or {}).get("chosen")
    if not old:
        return top, {"chosen": top.ticker, "lines": tickers, "reason": "most_traded",
                     "since": today.isoformat()}, None
    if old not in lines and old in {l.ticker for l in cluster} | set(tickers):
        # The saved line no longer reaches the floor: choose again.
        return top, {"chosen": top.ticker, "lines": tickers, "reason": "most_traded",
                     "since": today.isoformat()}, (old, top.ticker)
    if old not in lines:
        # EX-6: the saved line's exchange is switched off, or the line left
        # its list. A disabled exchange is temporary: use the next line, keep
        # the record. A line that's gone: choose again.
        suffix = "." + old.rsplit(".", 1)[-1] if "." in old else ""
        if suffix and suffix not in enabled_suffixes:
            return top, None, None
        return top, {"chosen": top.ticker, "lines": tickers, "reason": "most_traded",
                     "since": today.isoformat()}, (old, top.ticker)

    current = lines[old]
    record = dict(saved, lines=sorted(set(tickers) | set(saved.get("lines", []))))
    challenger = next((l for l in by_value if l.ticker != old), None)
    stronger = (challenger is not None and challenger.value_eur
                and challenger.value_eur >= SWITCH_FACTOR * (current.value_eur or 0))
    if not stronger:
        record.pop("challenger", None)
        record.pop("challenger_since", None)
        return current, record, None
    if record.get("challenger") != challenger.ticker:
        record["challenger"], record["challenger_since"] = challenger.ticker, today.isoformat()
        return current, record, None
    if _days(record.get("challenger_since"), today) < SWITCH_CONFIRM_DAYS:
        return current, record, None
    record = {"chosen": challenger.ticker, "lines": record["lines"], "reason": "most_traded",
              "since": today.isoformat()}
    return challenger, record, (old, challenger.ticker)


@dataclass
class Choice:
    """The outcome of one universe build."""
    kept: list[dict]                      # stock dicts in the public universe
    excluded: dict[str, str]              # ticker → reason (REASONS)
    switches: list[tuple[str, str]]       # (old, new) chosen-line switches
    choices: dict                         # the saved records after this build

    def counts(self) -> dict[str, dict[str, int]]:
        """{exchange suffix: {reason: count}} for the log (EX-8)."""
        out: dict[str, Counter] = {}
        for t, reason in self.excluded.items():
            suffix = "." + t.rsplit(".", 1)[-1] if "." in t else ""
            out.setdefault(suffix, Counter())[reason] += 1
        return {k: dict(v) for k, v in sorted(out.items())}


def _record_key(company: str, cluster: list[Line], choices: dict) -> str:
    """The saved record for this cluster: the one that already holds one of
    its lines, else a new key (company, or company|first ticker when the
    company has several share lines)."""
    tickers = {l.ticker for l in cluster}
    for key, record in choices.items():
        if key.split("|")[:3] == company.split("|") and tickers & set(record.get("lines", [])):
            return key
    return company if company not in choices else f"{company}|{min(tickers)}"


def choose_primary_lines(stocks: list[dict], info: dict[str, dict], *,
                         choices: "dict | None" = None,
                         enabled_suffixes: "set[str] | None" = None,
                         today: "date | None" = None) -> Choice:
    """EX-4: the stocks (from the enabled exchanges' lists) that are their
    company's primary line. ``info``: ticker → {"country", "averageVolume",
    "traded_value_eur", "sharesOutstanding", "quoteType"} from the fetch.
    ``choices``: the saved records (load_choices()); the returned Choice
    holds the updated ones, for save_choices()."""
    today = today or date.today()
    choices = dict(load_choices() if choices is None else choices)
    enabled_suffixes = enabled_suffixes or {"." + s["ticker"].rsplit(".", 1)[-1]
                                            for s in stocks if "." in s["ticker"]}
    excluded: dict[str, str] = {}
    lines: dict[str, Line] = {}
    stock_of = {s["ticker"]: s for s in stocks}
    for s in stocks:
        t = s["ticker"]
        row = info.get(t) or {}
        country = row.get("country")
        if str(row.get("quoteType") or "").upper() in _FUND_TYPES:
            excluded[t] = "fund"
        elif is_dormant(row.get("averageVolume")):
            excluded[t] = "dormant"
        elif not (isinstance(country, str) and country.strip()):
            excluded[t] = "country_unknown"
        elif not is_european(t, country):
            excluded[t] = "not_european"
        elif _GEM_LINE.match(t) or _SECOND_LINE_NAME.search(str(row.get("Name") or "").strip()):
            excluded[t] = "secondary_listing"
        else:
            lines[t] = Line(t, s.get("name") or row.get("Name") or t, country.strip(),
                            str(s.get("share_class") or ""),
                            _num(row.get("traded_value_eur")), _num(row.get("sharesOutstanding")))

    by_company: dict[str, list[Line]] = {}
    for line in lines.values():
        by_company.setdefault(line.company, []).append(line)

    kept: list[str] = []
    switches: list[tuple[str, str]] = []
    for company, company_lines_ in by_company.items():
        for cluster in _clusters(company_lines_):
            key = _record_key(company, cluster, choices)
            if len(cluster) == 1 and key not in choices:
                line = cluster[0]
                if _eligible(line):
                    kept.append(line.ticker)
                else:
                    excluded[line.ticker] = "secondary_listing"
                continue
            chosen, record, switch = _pick(cluster, choices.get(key), enabled_suffixes, today)
            if chosen is None:
                excluded.update({l.ticker: "secondary_listing" for l in cluster})
                continue
            kept.append(chosen.ticker)
            excluded.update({l.ticker: "secondary_listing" for l in cluster if l is not chosen})
            if record is not None:
                choices[key] = record
            if switch:
                switches.append(switch)
                _log.info("primary line of %s switched from %s to %s", company, *switch,
                          extra={"event": "listing.switched", "company": company,
                                 "old": switch[0], "new": switch[1]})
    kept_set = set(kept)
    return Choice([stock_of[t] for t in stock_of if t in kept_set], excluded, switches, choices)
