"""Index membership, from the committed snapshot uvalu/index_members.json.

Exchange expansion plan EX-W9 (decisions D7, D8). The snapshot is drafted by
tools/refresh_index_members.py and checked by hand after each quarterly index
review (open item EX6); nothing here scrapes at run time. It holds today's
members only: never use it for a backtest or a performance claim (model
review M9).

Used for the hardcoded fallback ticker lists (fetch_tickers, EX-13) and, from
EX-W10, the Screener's Index filter and the drawer's index tags.

No Streamlit import; unit-tested in tests/test_indices.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

SNAPSHOT = Path(__file__).parent / "index_members.json"

# Fixed order for the filter (EX-25): the two Stoxx indices first, then the
# national indices by name.
_FIRST = ("euro_stoxx_50", "stoxx_europe_50")


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("indices", {})
    except (OSError, ValueError):
        return {}


def keys() -> list[str]:
    """Every index with at least one member, in display order."""
    d = _data()
    have = [k for k, v in d.items() if v.get("members")]
    rest = sorted((k for k in have if k not in _FIRST), key=lambda k: d[k]["name"].lower())
    return [k for k in _FIRST if k in have] + rest


def name(key: str) -> str:
    """The index's official name, never translated (D11)."""
    return _data().get(key, {}).get("name", key)


def as_of(key: str) -> "str | None":
    """ISO date the index's members were last refreshed."""
    return _data().get(key, {}).get("as_of")


def members(key: str) -> list[dict]:
    """[{"ticker", "name"}] of an index, Yahoo tickers."""
    return list(_data().get(key, {}).get("members", []))


def tickers(key: str) -> set[str]:
    return {m["ticker"] for m in members(key)}


def indices_for(ticker: str) -> list[str]:
    """The indices a ticker is a member of, in display order."""
    return [k for k in keys() if ticker in tickers(k)]


def fallback_stocks(key: str, suffix: str, mic: str) -> list[dict]:
    """An index's members on one exchange, as a ticker list
    (fetch_tickers' fallback when an exchange list can't be read, EX-13)."""
    return [{"name": m["name"], "isin": "", "ticker": m["ticker"], "mic": mic}
            for m in members(key) if m["ticker"].endswith(suffix)]


# ── Self-checking membership (decided 24 October 2026) ──────────────────────
# Index members are kept by company, not by one ticker; each index knows its
# provider's review calendar; and every build checks each index before it is
# shown. A stale or badly matched index is hidden (and logged) instead of
# tagging the wrong stocks.

REVIEW_GRACE_DAYS = 30   # after a scheduled review, this long to refresh the members
MIN_COVERAGE = 0.90      # share of the expected members that must match the universe


def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _first_weekday(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def review_dates(key: str, year: int) -> list[date]:
    """The index's scheduled review dates in `year`, from the snapshot's
    "review" entry: {"months": [3, 6, 9, 12], "day": "third_friday" |
    "first_weekday"}. Empty when the index has no schedule."""
    rule = _data().get(key, {}).get("review") or {}
    day = _first_weekday if rule.get("day") == "first_weekday" else _third_friday
    return [day(year, m) for m in rule.get("months", [])]


def last_review(key: str, on: date) -> "date | None":
    """The latest scheduled review on or before `on`."""
    past = [d for y in (on.year - 1, on.year) for d in review_dates(key, y) if d <= on]
    return max(past) if past else None


def is_stale(key: str, today: "date | None" = None) -> bool:
    """True when a scheduled review took effect after the members were last
    checked (`as_of`), and the grace period after it is over."""
    today = today or date.today()
    checked = as_of(key)
    if not checked:
        return True
    last = last_review(key, today - timedelta(days=REVIEW_GRACE_DAYS))
    return last is not None and date.fromisoformat(checked) < last


@dataclass
class IndexCheck:
    key: str
    expected: int        # members listed on an enabled exchange
    matched: int
    stale: bool
    visible: bool
    reason: str = ""

    @property
    def coverage(self) -> float:
        return self.matched / self.expected if self.expected else 0.0


@dataclass
class Match:
    by_ticker: dict      # universe ticker -> [visible index keys, display order]
    unmatched: dict      # index key -> [member tickers that match no row]
    checks: dict         # index key -> IndexCheck


def _member_names(m: dict) -> set[str]:
    from uvalu import universe
    names = [m.get("name"), *m.get("aka", [])]
    return {n for n in (universe.normalise_name(x) for x in names if x) if n}


# Members our coverage rules leave out on purpose: they don't count against
# an index (JBT Marel in the OMX Iceland 15 has its primary listing in New York).
OUT_OF_SCOPE_REASONS = frozenset({"not_european", "secondary_listing", "fund"})


def match_universe(tickers, choices: "dict | None" = None, *, names: "dict | None" = None,
                   enabled_suffixes: "set[str] | None" = None, today: "date | None" = None,
                   excluded: "dict | None" = None) -> Match:
    """EX-26 + the quality gate. Each member is matched to the universe by
    company, in this order: its ticker; another line of the same company
    (uvalu/universe.company_lines, so a DAX member listed as AIR.DE matches
    AIR.PA); its name or an "aka" name, normalised, when exactly one universe
    row has that name (a ticker change). An index is visible only when it is
    not stale and at least MIN_COVERAGE of its expected members match.
    Only members listed on an enabled exchange are expected (and tagged), so
    a national index appears only once its own exchange is on."""
    from uvalu import universe
    in_universe = set(tickers)
    choices = universe.load_choices() if choices is None else choices
    names = names or {}
    enabled_suffixes = enabled_suffixes if enabled_suffixes is not None else {
        "." + t.rsplit(".", 1)[-1] for t in in_universe if "." in t}
    by_name: dict[str, list[str]] = {}
    for t, n in names.items():
        if t in in_universe and n:
            by_name.setdefault(universe.normalise_name(n), []).append(t)

    hits_by_key: dict[str, dict[str, set]] = {}
    unmatched: dict[str, list[str]] = {}
    checks: dict[str, IndexCheck] = {}
    for key in keys():
        hits: dict[str, set] = {}
        expected = matched = 0
        for m in members(key):
            t = m["ticker"]
            found = universe.company_lines({t}, choices) & in_universe
            if not found:
                for n in _member_names(m):
                    rows = by_name.get(n, [])
                    if len(rows) == 1:
                        found = {rows[0]}
                        break
            suffix = "." + t.rsplit(".", 1)[-1] if "." in t else ""
            if suffix not in enabled_suffixes:
                continue   # its exchange isn't covered: not expected, not tagged
            if not found and (excluded or {}).get(t) in OUT_OF_SCOPE_REASONS:
                continue   # left out of the universe on purpose (``excluded``: Choice.excluded)
            expected += 1
            if found:
                matched += 1
                hits[t] = found
            else:
                unmatched.setdefault(key, []).append(t)
        stale = is_stale(key, today)
        check = IndexCheck(key, expected, matched, stale, visible=False)
        if stale:
            check.reason = f"members as of {as_of(key)}, before the review of {last_review(key, (today or date.today()) - timedelta(days=REVIEW_GRACE_DAYS))}"
        elif not expected:
            check.reason = "no member on an enabled exchange"
        elif check.coverage < MIN_COVERAGE:
            check.reason = f"{matched} of {expected} members matched ({check.coverage:.0%} < {MIN_COVERAGE:.0%})"
        else:
            check.visible = True
        checks[key] = check
        hits_by_key[key] = hits

    by_ticker: dict[str, list[str]] = {}
    for key in keys():
        if not checks[key].visible:
            continue
        for found in hits_by_key[key].values():
            for t in sorted(found):
                if key not in by_ticker.setdefault(t, []):
                    by_ticker[t].append(key)
    return Match(by_ticker, unmatched, checks)


_PAN_EUROPEAN = {"euro_stoxx_50", "stoxx_europe_50"}


def home_country_hints() -> dict[str, str]:
    """{ticker: country} for members of a national blue-chip index, by the
    country of the member's own exchange: membership of the CAC 40 as ML.PA
    is good evidence that Michelin is French. Used only where the data
    provider gives no country (Michelin and Linde had none on 24 Oct 2026,
    so they were left out as country_unknown)."""
    from uvalu import exchanges
    out: dict[str, str] = {}
    for key in keys():
        if key in _PAN_EUROPEAN:
            continue
        for m in members(key):
            ex = exchanges.for_ticker(m["ticker"])
            if ex:
                out.setdefault(m["ticker"], ex.country)
    return out
