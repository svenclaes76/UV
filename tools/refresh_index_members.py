"""Draft an update of the index-member snapshot (uvalu/index_members.json).

Exchange expansion plan EX-W9, decision D8: index members are a committed,
hand-checked snapshot with an "as of" date per index, refreshed after each
quarterly index review (third Friday of March, June, September, December;
open item EX6). This script drafts that refresh; it never runs in the app.

Usage:
    python tools/refresh_index_members.py            # fetch, print the diff, write nothing
    python tools/refresh_index_members.py --write    # also write uvalu/index_members.json
    python tools/refresh_index_members.py --only dax,cac_40

Sources, per index (see INDICES):

- "tickers": a Wikipedia constituents table with a ticker column. Tickers
  are turned into Yahoo's form ("OSE: EQNR" → "EQNR.OL", "MAERSK B" →
  "MAERSK-B.CO", "BT.A" → "BT-A.L").
- "names": a table with company names (and a country) but no tickers, as for
  Stoxx Europe 50 and the ATX. Names are matched against the exchanges' own
  ticker lists (fetch_tickers.fetch_exchange_tickers), on the company's home
  exchange first, then on every known exchange. Every match is printed so it
  can be checked; names that don't match are listed as unresolved.
- "manual": no usable public table (WIG20, OMX Baltic Benchmark). The entry is
  kept as it is in the snapshot and must be filled or checked by hand.

Every resolved ticker is also checked against its exchange's ticker list,
and the member count against the index's size; anything off is printed.
Wikipedia is a starting point, not the authority: check each diff against
the index provider's own constituent list before --write.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uvalu import exchanges  # noqa: E402

SNAPSHOT = ROOT / "uvalu" / "index_members.json"
HEADERS = {"User-Agent": "uvalu-index-refresh/1.0 (index membership; contact via repository)"}

# key: (display name, owner, expected size, source kind, url, default suffix, extra)
INDICES: dict[str, dict] = {
    "euro_stoxx_50": dict(name="EURO STOXX 50", owner="STOXX", size=50, kind="tickers",
                          url="https://en.wikipedia.org/wiki/EURO_STOXX_50"),
    "stoxx_europe_50": dict(name="STOXX Europe 50", owner="STOXX", size=50, kind="names",
                            url="https://de.wikipedia.org/wiki/STOXX_Europe_50",
                            name_col="Name", country_col="Land"),
    "aex": dict(name="AEX", owner="Euronext", size=25, kind="tickers", suffix=".AS",
                url="https://en.wikipedia.org/wiki/AEX_index"),
    "atx": dict(name="ATX", owner="Wiener Börse", size=20, kind="names", country="Austria",
                url="https://de.wikipedia.org/wiki/Austrian_Traded_Index", name_col="Name"),
    "bel_20": dict(name="BEL 20", owner="Euronext", size=20, kind="tickers", suffix=".BR",
                   url="https://en.wikipedia.org/wiki/BEL_20", table_hint="Index weighting"),
    "cac_40": dict(name="CAC 40", owner="Euronext", size=40, kind="tickers", suffix=".PA",
                   url="https://en.wikipedia.org/wiki/CAC_40"),
    "dax": dict(name="DAX", owner="Deutsche Börse", size=40, kind="tickers", suffix=".DE",
                url="https://en.wikipedia.org/wiki/DAX"),
    "ftse_100": dict(name="FTSE 100", owner="FTSE Russell", size=100, kind="tickers", suffix=".L",
                     url="https://en.wikipedia.org/wiki/FTSE_100_Index"),
    "ftse_athex_large_cap": dict(name="FTSE/Athex Large Cap", owner="FTSE Russell / Euronext Athens",
                                 size=25, kind="tickers", suffix=".AT",
                                 url="https://en.wikipedia.org/wiki/FTSE/Athex_Large_Cap",
                                 ticker_col="Traded as"),
    "ftse_mib": dict(name="FTSE MIB", owner="FTSE Russell", size=40, kind="tickers", suffix=".MI",
                     url="https://en.wikipedia.org/wiki/FTSE_MIB"),
    "ibex_35": dict(name="IBEX 35", owner="BME", size=35, kind="tickers", suffix=".MC",
                    url="https://en.wikipedia.org/wiki/IBEX_35"),
    "iseq_20": dict(name="ISEQ 20", owner="Euronext", size=20, kind="tickers", suffix=".IR",
                    url="https://en.wikipedia.org/wiki/ISEQ_20"),
    "obx": dict(name="OBX", owner="Euronext", size=25, kind="tickers", suffix=".OL",
                url="https://en.wikipedia.org/wiki/OBX_Index"),
    "omx_baltic_benchmark": dict(name="OMX Baltic Benchmark", owner="Nasdaq", size=None, kind="manual",
                                 url="https://nasdaqbaltic.com/"),
    "omxc25": dict(name="OMX Copenhagen 25", owner="Nasdaq", size=25, kind="tickers", suffix=".CO",
                   url="https://en.wikipedia.org/wiki/OMX_Copenhagen_25"),
    "omxh25": dict(name="OMX Helsinki 25", owner="Nasdaq", size=25, kind="tickers", suffix=".HE",
                   url="https://en.wikipedia.org/wiki/OMX_Helsinki_25"),
    "omxi15": dict(name="OMX Iceland 15", owner="Nasdaq", size=15, kind="tickers", suffix=".IC",
                   url="https://en.wikipedia.org/wiki/OMX_Iceland_15"),
    "omxs30": dict(name="OMX Stockholm 30", owner="Nasdaq", size=30, kind="tickers", suffix=".ST",
                   url="https://en.wikipedia.org/wiki/OMX_Stockholm_30"),
    "psi": dict(name="PSI", owner="Euronext", size=None, kind="tickers", suffix=".LS",
                url="https://en.wikipedia.org/wiki/PSI-20"),
    "smi": dict(name="SMI", owner="SIX", size=20, kind="tickers", suffix=".SW",
                url="https://en.wikipedia.org/wiki/Swiss_Market_Index"),
    "wig20": dict(name="WIG20", owner="GPW Benchmark", size=20, kind="manual",
                  url="https://gpwbenchmark.pl/"),
}

# German country names on de.wikipedia → the registry's English names.
_DE_COUNTRIES = {
    "Belgien": "Belgium", "Deutschland": "Germany", "Dänemark": "Denmark", "Frankreich": "France",
    "Irland": "Ireland", "Italien": "Italy", "Niederlande": "Netherlands", "Schweiz": "Switzerland",
    "Spanien": "Spain", "Vereinigtes Königreich": "United Kingdom", "Schweden": "Sweden",
    "Finnland": "Finland", "Norwegen": "Norway", "Österreich": "Austria", "Portugal": "Portugal",
    "Luxemburg": "Luxembourg",
}

# Names no source can match automatically (a different name in the index
# table and in the exchange list), resolved by hand with the reason. Checked
# against the exchange lists on every run like any other member.
_NAME_FIXES = {
    "Münchener Rück": "MUV2.DE",           # Munich Re in the DAX table
    "Richemont": "CFR.SW",                  # Compagnie Financière Richemont in the SMI table
    "DHL": "DHL.DE",                        # Deutsche Post's ticker since 2023; DPW is the old one
    "Linde": "LIN.DE",                      # primary listing New York; the Xetra line is the European one
    "Austria Technologie & Systemtechnik AG": "ATS.VI",   # AT&S
    "Österreichische Post AG": "POST.VI",
}

_LEGAL = {"ag", "sa", "se", "plc", "nv", "n", "v", "ab", "asa", "as", "a", "s", "oyj", "spa", "p", "bv",
          "inc", "ltd", "limited", "group", "holding", "holdings", "the", "co", "company", "corp",
          "kgaa", "publ", "aktiengesellschaft", "societe", "anonyme", "de", "et", "cie", "sca"}


def _fold(text: str) -> str:
    t = str(text).replace("’", "'").replace("`", "'")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return " ".join(w for w in re.split(r"[^a-z0-9]+", t) if w and w not in _LEGAL)


def _tables(url: str) -> list[pd.DataFrame]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def _pick_table(tables: list[pd.DataFrame], cfg: dict, want: str) -> tuple[pd.DataFrame, str, str]:
    """The constituents table: has the wanted column, closest to the index
    size; (table, ticker-or-name column, name column)."""
    size = cfg.get("size") or 20
    best = None
    for t in tables:
        cols = [str(c) for c in t.columns]
        if cfg.get("table_hint") and not any(cfg["table_hint"].lower() in c.lower() for c in cols):
            continue
        if want == "tickers":
            col = cfg.get("ticker_col") or next((c for c in cols if any(w in c.lower()
                                                 for w in ("ticker", "symbol", "mnem"))), None)
        else:
            col = cfg.get("name_col")
        if not col or col not in cols or not (5 <= len(t) <= 150):
            continue
        name_col = next((c for c in cols if c.lower() in ("company", "name", "constituent")), col)
        score = abs(len(t) - size)
        if best is None or score < best[0]:
            best = (score, t, col, name_col)
    if best is None:
        raise ValueError("no constituents table found")
    return best[1], best[2], best[3]


def _clean(text: object) -> str:
    """Cell text without Wikipedia footnote marks ("TITC[6]", "Kojamo [fi]")."""
    return re.sub(r"\s*\[[^\]]*\]", "", str(text).replace("\xa0", " ")).strip()


def _to_yahoo(raw: str, default_suffix: "str | None") -> "str | None":
    t = _clean(raw)
    if not t or t.lower() == "nan":
        return None
    t = t.split(":")[-1].strip()                       # "OSE: EQNR", "Euronext Dublin: A5G"
    norm = exchanges.normalize_ticker(t)
    if exchanges.for_ticker(norm):
        return norm                                    # already has a known suffix ("AIR.PA")
    return f"{exchanges.yahoo_symbol(t)}{default_suffix}" if default_suffix else None


def _from_tickers(key: str, cfg: dict) -> tuple[list[dict], list[str]]:
    table, tcol, ncol = _pick_table(_tables(cfg["url"]), cfg, "tickers")
    members, problems = [], []
    for _, r in table.iterrows():
        ticker = _to_yahoo(r[tcol], cfg.get("suffix"))
        name = _clean(r[ncol])
        if ticker is None:
            if name and name.lower() != "nan":
                problems.append(f"no ticker in row {name!r}")
            continue
        members.append({"ticker": ticker, "name": name})
    return members, problems


_LISTS: dict[str, list[dict]] = {}
# Members already resolved from the ticker tables (national indices). A name
# is matched against these first: they are the lines the index providers use,
# where an exchange list also has secondary lines (Bayer's "BAYA", UBS's "UBSGE").
_RESOLVED: list[dict] = []


def _exchange_list(key: str) -> list[dict]:
    if key not in _LISTS:
        import fetch_tickers
        try:
            _LISTS[key] = fetch_tickers.fetch_exchange_tickers(key)
        except Exception as exc:                       # a list we can't read can't match anything
            print(f"  ! could not read the {key} list: {exc}")
            _LISTS[key] = []
    return _LISTS[key]


def _match_name(name: str, country: "str | None") -> "tuple[str, str] | None":
    target = _fold(name)
    if not target:
        return None
    if name in _NAME_FIXES:
        return _NAME_FIXES[name], "manual fix"
    home_suffixes = {e.suffix for e in (*exchanges.EXCHANGES, *exchanges.PLANNED) if e.country == country}

    def _best(cands: list[dict]) -> "dict | None":
        home = [m for m in cands if any(m["ticker"].endswith(sfx) for sfx in home_suffixes)]
        return (home or cands or [None])[0]

    exact = [m for m in _RESOLVED if _fold(m["name"]) == target]
    prefix = [m for m in _RESOLVED if _fold(m["name"]).startswith(target + " ")
              or target.startswith(_fold(m["name"]) + " ")]
    hit = _best(exact) or _best(prefix)
    if hit:
        return hit["ticker"], hit["name"]
    home = [e.key for e in (*exchanges.EXCHANGES, *exchanges.PLANNED) if e.country == country]
    order = home + [e.key for e in (*exchanges.EXCHANGES, *exchanges.PLANNED) if e.key not in home]
    for scope in (home, order):
        for key in scope:
            stocks = _exchange_list(key)
            exact = [s for s in stocks if _fold(s["name"]) == target]
            prefix = [s for s in stocks if _fold(s["name"]).startswith(target + " ")
                      or target.startswith(_fold(s["name"]) + " ")]
            hit = exact or prefix
            if hit:
                plain = [s for s in hit if not s.get("share_class")] or hit
                return plain[0]["ticker"], plain[0]["name"]
    return None


def _from_names(key: str, cfg: dict) -> tuple[list[dict], list[str]]:
    table, ncol, _ = _pick_table(_tables(cfg["url"]), cfg, "names")
    members, problems = [], []
    for _, r in table.iterrows():
        name = _clean(r[ncol])
        if not name or name.lower() == "nan":
            continue
        country = cfg.get("country") or _DE_COUNTRIES.get(str(r.get(cfg.get("country_col"), "")).strip())
        hit = _match_name(name, country)
        if hit is None:
            problems.append(f"unresolved: {name!r} ({country or '?'})")
            continue
        print(f"    {name!r:38} → {hit[0]:14} ({hit[1]})")
        members.append({"ticker": hit[0], "name": name})
    return members, problems


def _check(key: str, cfg: dict, members: list[dict]) -> list[str]:
    problems = []
    if cfg.get("size") and len(members) != cfg["size"]:
        problems.append(f"{len(members)} members, expected {cfg['size']}")
    for m in members:
        ex = exchanges.for_ticker(m["ticker"])
        if ex is None:
            problems.append(f"{m['ticker']}: no known exchange")
            continue
        listed = {s["ticker"] for s in _exchange_list(ex.key)}
        if listed and m["ticker"] not in listed:
            problems.append(f"{m['ticker']} ({m['name']}): not in the {ex.name} list")
    return problems


def load_snapshot() -> dict:
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"indices": {}}


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="write uvalu/index_members.json")
    ap.add_argument("--only", help="comma-separated index keys")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    snap = load_snapshot()
    old = snap.get("indices", {})
    keys = args.only.split(",") if args.only else list(INDICES)
    # Ticker tables first, so name-only indices can match against them.
    keys = sorted(keys, key=lambda k: INDICES[k]["kind"] != "tickers")
    today = date.today().isoformat()
    new = dict(old)
    for key in keys:
        cfg = INDICES[key]
        print(f"\n== {cfg['name']} ({key})")
        entry = {k: cfg[k] for k in ("name", "owner")} | {"source_url": cfg["url"], "size": cfg.get("size")}
        if cfg["kind"] == "manual":
            kept = old.get(key) or {**entry, "as_of": None, "members": [], "status": "to_fill"}
            print(f"  manual: kept as is ({len(kept.get('members', []))} members, status {kept.get('status')})")
            new[key] = kept
            continue
        try:
            members, problems = (_from_tickers if cfg["kind"] == "tickers" else _from_names)(key, cfg)
        except Exception as exc:
            print(f"  ! source failed, keeping the snapshot entry: {exc}")
            continue
        problems += _check(key, cfg, members)
        members = sorted({m["ticker"]: m for m in members}.values(), key=lambda m: m["ticker"])
        if cfg["kind"] == "tickers":
            _RESOLVED.extend(members)
        before = {m["ticker"] for m in old.get(key, {}).get("members", [])}
        after = {m["ticker"] for m in members}
        print(f"  {len(members)} members; added {sorted(after - before) or '-'}; removed {sorted(before - after) or '-'}")
        for p in problems:
            print(f"  ? {p}")
        new[key] = {**entry, "as_of": today, "members": members,
                    "status": "check" if problems else "ok", "problems": problems}

    if args.write:
        out = {
            "_note": ("Index members as published, refreshed by hand after each quarterly review "
                      "with tools/refresh_index_members.py. Today's members only: not point-in-time, "
                      "so never use this for a backtest or a performance claim (it would be "
                      "survivorship-biased; model review M9). Index names are trademarks of their owners."),
            "indices": {k: new[k] for k in INDICES if k in new},
        }
        SNAPSHOT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {SNAPSHOT.relative_to(ROOT)}")
    else:
        print("\n(dry run: nothing written; add --write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
