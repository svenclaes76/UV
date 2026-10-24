"""Shadow build of the expanded universe (exchange expansion release 2).

Open item EX3, model review M6, decisions D36/D37: for about a week before
release 2, every exchange in the registry (covered and planned) is fetched
and scored in the background, not shown, and compared day by day. The report
gives, per exchange:

- listed lines, lines in the universe and the reasons for the rest (EX-8);
- data quality: share with a fair value, `currency_unverified`,
  `risk_free_rate_missing`, median P/E;
- the signal mix and the Undervalued share against the universe's;
- go/no-go (D36): fair value for at least 60%, under 5% currency_unverified,
  Undervalued at most 3x the universe's; London also needs the golden sample
  (M4: 20 FTSE companies and Maersk, P/E within 0.8-1.25x of price over the
  latest annual net income per share (V7: Yahoo's own P/E mixes currencies), fair value
  between 0.2x and 5x the price). Since 17 October every exchange goes on at
  release (plan §0), so the go/no-go is a check, not a gate;
- peer group: how many of today's six exchanges' stocks change signal only
  because the peer group grows;
- pooled vs regional sector medians (D37, M1): the Undervalued share per
  exchange with each region scored on its own medians; a market above 3x
  the average is flagged;
- flicker: signal changes per exchange against the previous shadow day.

Everything stays in .cache/shadow/: its own fundamentals cache, listing
choices, logs, daily signals and reports. Nothing goes into the signal
history, the app's caches or the app's logs. The shadow cache is first
seeded with the app's newer rows (read only), so the shadow build fetches
only what the app doesn't: the planned exchanges and secondary lines.

Usage:
    python tools/shadow_build.py run              # fetch, score, write today's report
    python tools/shadow_build.py run --no-fetch   # score what is cached, no Yahoo calls
    python tools/shadow_build.py summary          # the week so far, one table

A full first run fetches a few thousand lines from Yahoo and takes hours;
run it in the background, once a day, after the European close.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

SHADOW_DIR = ROOT / ".cache" / "shadow"
APP_CACHE = ROOT / ".cache" / "fundamentals.json"

COVERED_TODAY = ("brussels", "amsterdam", "paris", "milan", "frankfurt", "swiss")

# Model review M1/D37: four regions for the sector x region comparison.
REGIONS = {
    "Western Europe": {"Belgium", "Netherlands", "France", "Germany", "Switzerland", "Austria"},
    "UK & Ireland": {"United Kingdom", "Ireland"},
    "Nordics": {"Sweden", "Denmark", "Finland", "Norway", "Iceland"},
    "Southern & Central Europe": {"Italy", "Spain", "Portugal", "Greece", "Poland",
                                  "Estonia", "Latvia", "Lithuania"},
}

# M4: 20 FTSE 100 companies (USD and EUR reporters, banks, insurers, REITs,
# miners) and Maersk (DKK quote, USD reports) as a non-UK control.
GOLDEN_SAMPLE = (
    "SHEL.L", "BP.L", "HSBA.L", "GLEN.L", "ULVR.L", "AZN.L", "RIO.L", "AAL.L", "BARC.L",
    "LLOY.L", "LGEN.L", "AV.L", "LAND.L", "BLND.L", "SGRO.L", "GSK.L", "DGE.L", "BATS.L",
    "VOD.L", "NG.L", "MAERSK-B.CO",
)

MIN_FAIR_VALUE = 0.60          # D36
MAX_CURRENCY_UNVERIFIED = 0.05
MAX_UNDERVALUED_RATIO = 3.0
# Decided 24 October 2026: the 3x test needs at least this many Undervalued
# stocks, so one stock on a 20-line exchange (Dublin) can't fail it.
MIN_UNDERVALUED_FOR_RATIO = 5
# V7: Yahoo's own trailingPE divides a GBP price by a USD EPS for some London
# lines (Shell), so the reference is the price over the latest annual net income
# per share, both in the quote currency. Trailing EPS against the last full
# year: a band that still catches a currency error (USD/GBP is 1.33x); a profit
# that moved more than 25% in a year is flagged for a look.
GOLDEN_PE_RANGE = (0.8, 1.25)
GOLDEN_FV_RANGE = (0.2, 5.0)


# ── pure helpers (unit-tested in tests/test_shadow_build.py) ────────────────

def exchange_key(ticker: str) -> "str | None":
    from uvalu import exchanges
    ex = exchanges.for_ticker(ticker)
    return ex.key if ex else None


def region_of(key: str) -> "str | None":
    from uvalu import exchanges
    ex = exchanges.KNOWN_BY_KEY.get(key)
    return next((r for r, countries in REGIONS.items() if ex and ex.country in countries), None)


def _flag_share(scored: pd.DataFrame, flag: str) -> float:
    if scored.empty or "data_flags" not in scored.columns:
        return 0.0
    return float(scored["data_flags"].map(lambda f: isinstance(f, list) and flag in f).mean())


def _undervalued_share(scored: pd.DataFrame) -> float:
    return float((scored["signal_code"] == "undervalued").mean()) if len(scored) else 0.0


def exchange_stats(scored: pd.DataFrame, listed: dict[str, int],
                   excluded: dict[str, str]) -> dict[str, dict]:
    """Per exchange key: counts, data quality and signal mix."""
    scored = scored.assign(_key=scored["Ticker"].map(exchange_key))
    reasons: dict[str, Counter] = {}
    for t, why in excluded.items():
        reasons.setdefault(exchange_key(t) or "?", Counter())[why] += 1
    out = {}
    for key in sorted(set(listed) | set(scored["_key"].dropna())):
        part = scored[scored["_key"] == key]
        pe = pd.to_numeric(part.get("trailingPE"), errors="coerce") if "trailingPE" in part else pd.Series(dtype=float)
        out[key] = {
            "listed": int(listed.get(key, 0)),
            "in_universe": int(len(part)),
            "excluded": dict(reasons.get(key, {})),
            "fair_value": round(float(part["fair_value"].notna().mean()), 3) if len(part) else 0.0,
            "currency_unverified": round(_flag_share(part, "currency_unverified"), 3),
            "rate_missing": round(_flag_share(part, "risk_free_rate_missing"), 3),
            "median_pe": round(float(pe[pe > 0].median()), 1) if (pe > 0).any() else None,
            "signals": dict(Counter(part["signal_code"])),
            "undervalued": round(_undervalued_share(part), 3),
        }
    return out


def go_no_go(stats: dict[str, dict], universe_undervalued: float,
             golden_ok: "bool | None" = None) -> dict[str, dict]:
    """D36 per exchange: {key: {"go": bool, "fails": [...]}}."""
    out = {}
    for key, s in stats.items():
        fails = []
        if s["in_universe"] == 0:
            fails.append("no lines in the universe")
        if s["fair_value"] < MIN_FAIR_VALUE:
            fails.append(f"fair value for {s['fair_value']:.0%} (< {MIN_FAIR_VALUE:.0%})")
        if s["currency_unverified"] >= MAX_CURRENCY_UNVERIFIED:
            fails.append(f"currency_unverified {s['currency_unverified']:.0%} (>= {MAX_CURRENCY_UNVERIFIED:.0%})")
        if (universe_undervalued > 0 and s["undervalued"] > MAX_UNDERVALUED_RATIO * universe_undervalued
                and s.get("signals", {}).get("undervalued", 0) >= MIN_UNDERVALUED_FOR_RATIO):
            fails.append(f"Undervalued {s['undervalued']:.1%} > {MAX_UNDERVALUED_RATIO:g}x universe "
                         f"{universe_undervalued:.1%}")
        if key == "london" and golden_ok is not True:
            fails.append("golden sample " + ("failed" if golden_ok is False else "not checked"))
        out[key] = {"go": not fails, "fails": fails}
    return out


def golden_sample(scored: pd.DataFrame, raw: pd.DataFrame) -> dict:
    """M4 with V7: per sample ticker, our P/E against price over the latest
    annual net income per share, and fair value / price.
    {"ok": bool|None, "rows": {...}, "missing": [...]}. `raw` is kept for
    the report's Yahoo P/E column."""
    yahoo_pe = dict(zip(raw["Ticker"], pd.to_numeric(raw.get("trailingPE"), errors="coerce"))) \
        if "trailingPE" in raw else {}
    rows, missing = {}, []
    by_ticker = scored.set_index("Ticker") if len(scored) else scored
    for t in GOLDEN_SAMPLE:
        if t not in getattr(by_ticker, "index", ()):
            missing.append(t)
            continue
        r = by_ticker.loc[t]
        price, eps, fv, shares = (pd.to_numeric(r.get(c), errors="coerce")
                                  for c in ("Price", "trailingEps", "fair_value", "sharesOutstanding"))
        hist = r.get("netIncomeHistory")
        ni = next((x for x in hist if isinstance(x, (int, float)) and x == x and x != 0), None) \
            if isinstance(hist, (list, tuple)) else None
        ours = price / eps if pd.notna(price) and pd.notna(eps) and eps > 0 else None
        anchor = (price / (ni / shares) if ni and ni > 0 and pd.notna(shares) and shares > 0
                  and pd.notna(price) else None)
        pe_ok = (ours is not None and anchor is not None
                 and GOLDEN_PE_RANGE[0] <= ours / anchor <= GOLDEN_PE_RANGE[1])
        ratio = fv / price if pd.notna(fv) and pd.notna(price) and price > 0 else None
        fv_ok = ratio is not None and GOLDEN_FV_RANGE[0] <= ratio <= GOLDEN_FV_RANGE[1]
        theirs = yahoo_pe.get(t)
        rows[t] = {"pe": None if ours is None else round(float(ours), 2),
                   "pe_net_income": None if anchor is None else round(float(anchor), 2),
                   "yahoo_pe": None if theirs is None or pd.isna(theirs) else round(float(theirs), 2),
                   "fv_price": None if ratio is None else round(float(ratio), 2),
                   "per_share_ccy": r.get("per_share_ccy"),
                   "ok": bool(pe_ok and fv_ok)}
    ok = None if not rows else all(v["ok"] for v in rows.values()) and not missing
    return {"ok": ok, "rows": rows, "missing": missing}


def signal_changes(today: dict[str, str], previous: dict[str, str]) -> dict[str, int]:
    """Signal changes per exchange key against the previous shadow day."""
    out: Counter = Counter()
    for t, code in today.items():
        if t in previous and previous[t] != code:
            out[exchange_key(t) or "?"] += 1
    return dict(out)


def peer_group_effect(full: pd.DataFrame, six: pd.DataFrame) -> dict:
    """Today's six exchanges' stocks: signal in a six-exchange peer group vs
    the full universe. Only the peer group differs."""
    a = dict(zip(six["Ticker"], six["signal_code"]))
    b = dict(zip(full["Ticker"], full["signal_code"]))
    common = [t for t in a if t in b]
    moves = Counter((a[t], b[t]) for t in common if a[t] != b[t])
    return {"stocks": len(common), "changed": sum(moves.values()),
            "moves": {f"{x} -> {y}": n for (x, y), n in moves.most_common()}}


def regional_tilt(pooled: dict[str, float], regional: dict[str, float],
                  counts: "dict[str, int] | None" = None) -> dict:
    """D37: Undervalued share per exchange, pooled vs regional medians, and
    the exchanges above 3x the average under pooled medians."""
    avg = sum(pooled.values()) / len(pooled) if pooled else 0.0
    flagged = sorted(k for k, v in pooled.items() if avg > 0 and v > MAX_UNDERVALUED_RATIO * avg
                     and (counts is None or counts.get(k, 0) >= MIN_UNDERVALUED_FOR_RATIO))
    return {"average": round(avg, 4), "flagged": flagged,
            "by_exchange": {k: {"pooled": round(pooled[k], 4), "regional": round(regional.get(k, 0.0), 4)}
                            for k in sorted(pooled)}}


def render_markdown(report: dict) -> str:
    lines = [f"# Shadow build {report['date']}", "",
             f"Model {report['model_version']}, {report['universe']} lines in the universe, "
             f"Undervalued {report['universe_undervalued']:.1%}. Fetch: {report['fetch']}.", "",
             "| Exchange | Listed | In | FV | Ccy unverif. | Rate missing | Median P/E | Undervalued | "
             "Changes | Go | Why not |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for key, s in report["exchanges"].items():
        g = report["go_no_go"].get(key, {})
        lines.append(f"| {key} | {s['listed']} | {s['in_universe']} | {s['fair_value']:.0%} | "
                     f"{s['currency_unverified']:.0%} | {s['rate_missing']:.0%} | {s['median_pe'] or '—'} | "
                     f"{s['undervalued']:.1%} | {report['changes'].get(key, 0)} | "
                     f"{'yes' if g.get('go') else 'no'} | {'; '.join(g.get('fails', []))} |")
    pg = report["peer_group"]
    lines += ["", f"**Peer group:** {pg['changed']} of {pg['stocks']} stocks on today's six exchanges "
                  f"change signal when the peer group grows: {pg['moves'] or 'none'}.", ""]
    rt = report["regional"]
    lines += [f"**Pooled vs regional medians:** average Undervalued {rt['average']:.1%}; above 3x: "
              f"{', '.join(rt['flagged']) or 'none'}.", "",
              "| Exchange | Pooled | Regional |", "| --- | ---: | ---: |"]
    lines += [f"| {k} | {v['pooled']:.1%} | {v['regional']:.1%} |" for k, v in rt["by_exchange"].items()]
    gs = report["golden"]
    lines += ["", f"**London golden sample:** {'passes' if gs['ok'] else 'does not pass' if gs['ok'] is False else 'not checked'}"
                  + (f"; missing {', '.join(gs['missing'])}" if gs["missing"] else "") + "."]
    bad = {t: r for t, r in gs["rows"].items() if not r["ok"]}
    if bad:
        lines += ["", "| Ticker | Our P/E | Price / net income per share | Yahoo P/E | FV / price | EPS currency |",
                  "| --- | ---: | ---: | ---: | ---: | --- |"]
        lines += [f"| {t} | {r['pe']} | {r.get('pe_net_income')} | {r['yahoo_pe']} | {r['fv_price']} | "
                  f"{r.get('per_share_ccy') or '—'} |" for t, r in bad.items()]
    return "\n".join(lines) + "\n"


# ── the run ─────────────────────────────────────────────────────────────────

def _setup(shadow_dir: Path):
    """Point everything that writes at the shadow folder, and return its fetcher."""
    shadow_dir.mkdir(parents=True, exist_ok=True)
    from uvalu import logkit, universe
    from uvalu.logkit import setup as lk_setup
    lk_setup.init_logging(synchronous=True, log_dir=shadow_dir / "logs")
    universe.LISTING_CHOICE_FILE = shadow_dir / "listing_choice.json"
    # Frankfurt's exceptions: a copy, never the app's file (this branch saves
    # it in a newer format the app on master can't read).
    import shutil
    import fetch_tickers
    own = shadow_dir / "frankfurt_exceptions.json"
    if not own.exists() and fetch_tickers._EXCEPTIONS_FILE.exists():
        shutil.copyfile(fetch_tickers._EXCEPTIONS_FILE, own)
    fetch_tickers._EXCEPTIONS_FILE = own
    # Quote units (EX-W5): a copy too, so the two processes never overwrite
    # each other's additions. The ticker lists are shared: same format, and
    # written atomically.
    import marketdata
    units = shadow_dir / "quote_units.json"
    if not units.exists() and marketdata._UNITS_FILE.exists():
        shutil.copyfile(marketdata._UNITS_FILE, units)
    marketdata._UNITS_FILE, marketdata._units = units, None
    import screener
    screener.refresh_model_switches = lambda shared=None: dict(screener._m5_state)
    screener._m5_state.update(dict.fromkeys(screener.M5_SWITCHES, True))
    return screener._Fetcher(shadow_dir / "fundamentals.json"), logkit.get_logger("uvalu.shadow")


def seed_from_app(shadow_file: Path, app_file: Path) -> int:
    """Copy the app's rows that are newer than the shadow's (read only on
    the app's side). Returns the number of rows copied."""
    try:
        app = json.loads(app_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    try:
        mine = json.loads(shadow_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mine = {}
    copied = 0
    for t, row in app.items():
        if isinstance(row, dict) and str(row.get("fetched_at") or "") > str((mine.get(t) or {}).get("fetched_at") or ""):
            mine[t] = row
            copied += 1
    shadow_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = shadow_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(mine), encoding="utf-8")
    tmp.replace(shadow_file)
    return copied


def _fetch(stocks: list[dict], fetcher, fetch: bool, log) -> pd.DataFrame:
    import screener
    if not fetch:
        screener._warm_live_cache(fetcher)
        return screener._df_from_cache(stocks, fetcher.live_cache)
    screener.fetch_fundamentals_nowait(stocks, fetcher=fetcher)
    started = time.monotonic()
    while fetcher.bg_thread is not None and fetcher.bg_thread.is_alive():
        fetcher.bg_thread.join(timeout=60)
        with fetcher.state_lock:
            done, total = fetcher.state["done"], fetcher.state["total"]
        log.info("shadow fetch %d / %d (%.0f min)", done, total, (time.monotonic() - started) / 60,
                 extra={"event": "shadow.fetch_progress", "done": done, "total": total})
    return screener._df_from_cache(stocks, fetcher.live_cache)


def _score(df: pd.DataFrame, previous: dict, thresholds, weights) -> pd.DataFrame:
    import screener
    if df.empty:
        return df
    max_de, max_payout, min_mos, buy = thresholds
    return screener.run_screener_from_df(df.copy(), max_debt_equity=max_de, max_payout=max_payout,
                                         min_mos=min_mos, buy_threshold=buy, weights=weights,
                                         previous_signals=previous, founder_holdings=frozenset())


def run(shadow_dir: Path = SHADOW_DIR, app_cache: Path = APP_CACHE, fetch: bool = True,
        today: "date | None" = None) -> Path:
    today = today or date.today()
    fetcher, log = _setup(shadow_dir)
    import fetch_tickers
    import settings
    from uvalu import exchanges, universe

    seeded = seed_from_app(fetcher.cache_file, app_cache)
    if not fetch:   # cached lists as they are; no Yahoo probe for Frankfurt
        fetch_tickers.LIST_TTL_HOURS = 10 ** 6
        fetch_tickers._is_valid_on_yahoo = lambda symbol: None
    keys = list(exchanges.KNOWN_BY_KEY)
    lists = {k: fetch_tickers.fetch_exchange_tickers(k) for k in keys}
    listed = {k: len(v) for k, v in lists.items()}
    screener_mod = __import__("screener")
    screener_mod._warm_live_cache(fetcher)
    known_country = {t: r.get("country") for t, r in fetcher.live_cache.items() if isinstance(r, dict)}
    candidates = [s for k in keys for s in lists[k]
                  if not universe.known_foreign(s["ticker"], known_country.get(s["ticker"]))]
    t0 = time.monotonic()
    fund = _fetch(candidates, fetcher, fetch, log)
    minutes = (time.monotonic() - t0) / 60

    fund = fund.copy()
    fund["traded_value_eur"] = screener_mod._traded_value_eur(fund)
    cols = [c for c in ("country", "averageVolume", "traded_value_eur", "sharesOutstanding",
                        "quoteType", "Name") if c in fund.columns]
    info = {t: dict(zip(cols, vals)) for t, *vals in zip(fund["Ticker"], *(fund[c] for c in cols))}
    choice = universe.choose_primary_lines(candidates, info,
                                           enabled_suffixes={e.suffix for e in exchanges.KNOWN_BY_KEY.values()},
                                           today=today)
    universe.save_choices(choice.choices)
    kept = {s["ticker"] for s in choice.kept}
    uni = fund[fund["Ticker"].isin(kept)].reset_index(drop=True)

    signals_dir = shadow_dir / "signals"
    signals_dir.mkdir(exist_ok=True)
    prev_files = sorted(p for p in signals_dir.glob("*.json") if p.stem < today.isoformat())
    previous = json.loads(prev_files[-1].read_text(encoding="utf-8")) if prev_files else {}
    thresholds, weights = settings.get_veto_thresholds(), settings.get_score_weights()

    full = _score(uni, previous, thresholds, weights)
    six_suffixes = {exchanges.KNOWN_BY_KEY[k].suffix for k in COVERED_TODAY}
    six_df = uni[uni["Ticker"].map(lambda t: "." + t.rsplit(".", 1)[-1] in six_suffixes)]
    six = _score(six_df, previous, thresholds, weights)

    regional_scores: dict[str, float] = {}
    for region in REGIONS:
        part = uni[uni["Ticker"].map(lambda t: region_of(exchange_key(t) or "") == region)]
        scored = _score(part, previous, thresholds, weights)
        if len(scored):
            for key, grp in scored.groupby(scored["Ticker"].map(exchange_key)):
                regional_scores[key] = _undervalued_share(grp)

    stats = exchange_stats(full, listed, choice.excluded)
    universe_uv = _undervalued_share(full)
    golden = golden_sample(full, fund)
    today_signals = dict(zip(full["Ticker"], full["signal_code"]))
    (signals_dir / f"{today.isoformat()}.json").write_text(json.dumps(today_signals), encoding="utf-8")

    report = {
        "date": today.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_version": screener_mod.model_version(),
        "thresholds": list(thresholds),
        "universe": len(full),
        "universe_undervalued": round(universe_uv, 4),
        "fetch": (f"{len(candidates)} candidate lines, {minutes:.0f} min, {seeded} rows seeded from the app"
                  if fetch else f"none (cache only, {seeded} rows seeded from the app)"),
        "exchanges": stats,
        "go_no_go": go_no_go(stats, universe_uv, golden["ok"]),
        "golden": golden,
        "peer_group": peer_group_effect(full, six),
        "regional": regional_tilt({k: s["undervalued"] for k, s in stats.items() if s["in_universe"]},
                                  regional_scores,
                                  {k: s["signals"].get("undervalued", 0) for k, s in stats.items()}),
        "changes": signal_changes(today_signals, previous),
        "previous_day": prev_files[-1].stem if prev_files else None,
        "switches": choice.switches,
    }
    reports = shadow_dir / "reports"
    reports.mkdir(exist_ok=True)
    (reports / f"{today.isoformat()}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = reports / f"{today.isoformat()}.md"
    md.write_text(render_markdown(report), encoding="utf-8")
    log.info("shadow build report written", extra={"event": "shadow.report", "path": str(md)})
    return md


def summary(shadow_dir: Path = SHADOW_DIR) -> str:
    """One table for the week: per exchange, Undervalued share and signal
    changes per day, and today's go/no-go."""
    reports = [json.loads(p.read_text(encoding="utf-8"))
               for p in sorted((shadow_dir / "reports").glob("*.json"))]
    if not reports:
        return "No shadow reports yet.\n"
    days = [r["date"] for r in reports]
    keys = sorted({k for r in reports for k in r["exchanges"]})
    lines = ["| Exchange | " + " | ".join(days) + " | Go (last) |",
             "| --- | " + " | ".join("---:" for _ in days) + " | --- |"]
    for k in keys:
        cells = []
        for r in reports:
            s = r["exchanges"].get(k)
            cells.append("—" if not s else f"{s['undervalued']:.1%} · {r['changes'].get(k, 0)}")
        go = reports[-1]["go_no_go"].get(k, {})
        lines.append(f"| {k} | " + " | ".join(cells) + f" | {'yes' if go.get('go') else 'no'} |")
    return ("Undervalued share · signal changes against the day before\n\n" + "\n".join(lines) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch, score and write today's report")
    r.add_argument("--no-fetch", action="store_true", help="score what is cached; no Yahoo calls")
    r.add_argument("--app-cache", type=Path, default=APP_CACHE, help="the app's fundamentals.json (read only)")
    sub.add_parser("summary", help="the week so far")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        path = run(app_cache=args.app_cache, fetch=not args.no_fetch)
        print(path.read_text(encoding="utf-8"))
    else:
        print(summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
