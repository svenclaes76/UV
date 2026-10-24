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


def match_universe(tickers, choices: "dict | None" = None) -> "tuple[dict[str, list[str]], dict[str, list[str]]]":
    """EX-26: index members matched to the universe's chosen lines, by company
    (uvalu/universe.company_lines): a DAX member listed as AIR.DE matches
    AIR.PA. Returns ({universe ticker: [index keys, display order]},
    {index key: [member tickers that match no row]})."""
    from uvalu import universe
    in_universe = set(tickers)
    choices = universe.load_choices() if choices is None else choices
    out: dict[str, list[str]] = {}
    unmatched: dict[str, list[str]] = {}
    for key in keys():
        for m in members(key):
            hits = universe.company_lines({m["ticker"]}, choices) & in_universe
            if not hits:
                unmatched.setdefault(key, []).append(m["ticker"])
            for t in sorted(hits):
                if key not in out.setdefault(t, []):
                    out[t].append(key)
    return out, unmatched
