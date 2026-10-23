"""The demo's runtime workspace (demo-mode plan DM-5).

``activate()`` runs once per process in demo mode, before the first page:

1. Makes a fresh temporary folder and points every place the app reads or
   writes data (``data/…``, ``.cache/…``: portfolios, settings, users,
   compliance logs, schema state, market-data caches) into it. A local demo
   run therefore never touches the personal data in the repo folder, and on
   Community Cloud nothing outlives the process (DM-D4: per-session edits).
2. Swaps the network for the snapshot: ``yfinance`` answers from
   uvalu/demo/yfshim.py, ``fx`` from the snapshot's ECB rates, and the Ken
   French factor download is switched off (no data API at run time, §1).
3. Warms the caches through the app's own code (price history, dividends,
   quote units) and writes the fundamentals rows (uvalu/demo/rows.py) into
   both fetch lanes' cache files.

Each browser session then gets its own pseudo-user (``session_email``) whose
storage folder is seeded with the sample portfolio and watchlist (DM-D15);
``reset_session`` puts the sample back.

``refresh_if_newer()`` (called on every run, checks at most every 5 minutes)
loads a newer snapshot in place: Community Cloud pulls the evening's data
commit into the running app without restarting it, and the snapshot would
otherwise stay the one read at start until the next reboot or sleep.
"""
from __future__ import annotations

import importlib
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from uvalu import datamode, logkit

_log = logkit.get_logger("uvalu.demo")
_lock = threading.RLock()


@dataclass
class Workspace:
    root: Path
    snapshot: object
    rows: dict
    sector_multiples: tuple
    src: Path = Path(".")
    signature: tuple = ()


_WS: "Workspace | None" = None
_SAVED: list = []      # (object, attribute, original value) for reset_for_tests()

# (module, attribute, path under the workspace root)
REDIRECTS: tuple[tuple[str, str, str], ...] = (
    ("portfolio", "_BASE_DIR", "data/portfolio"),
    ("portfolio", "_CACHE_DIR", ".cache"),
    ("settings", "_DATA_DIR", "data/settings"),
    ("settings", "_SHARED_FILE", "data/settings/shared.json"),
    ("backup", "_SHARED_FILE", "data/settings/shared.json"),
    ("backup", "_BACKUPS_DIR", "data/backups"),
    ("backup", "_BACKUPS_MANIFEST", "data/backups/manifest.json"),
    ("auth", "USERS_FILE", ".cache/users.json"),
    ("uvalu.compliance.signal_history", "COMPLIANCE_DIR", "data/compliance"),
    ("uvalu.compliance.signal_history", "HISTORY_FILE", "data/compliance/signal_history.jsonl"),
    ("uvalu.compliance.signal_history", "SNAPSHOT_DIR", "data/compliance/signal_snapshots"),
    ("uvalu.compliance.admin_access", "ACCESS_FILE", "data/compliance/admin_access.jsonl"),
    ("uvalu.compliance.settings_audit", "AUDIT_FILE", "data/compliance/settings_audit.jsonl"),
    ("uvalu.migrations.runner", "DATA_DIR", "data"),
    ("uvalu.migrations.runner", "CACHE_DIR", ".cache"),
    ("fetch_tickers", "_EXCEPTIONS_FILE", ".cache/frankfurt_exceptions.json"),
    ("fetch_tickers", "_LIST_CACHE_DIR", ".cache/ticker_lists"),
    ("screener", "FOUNDER_HOLDINGS_FILE", "data/compliance/founder_holdings.json"),
    ("marketdata", "_HISTORY_DIR", ".cache/history"),
    ("marketdata", "_UNITS_FILE", ".cache/quote_units.json"),
    ("marketdata", "_DIVIDEND_DIR", ".cache/dividends"),
    ("fx", "_CACHE_FILE", ".cache/fx_frankfurter.json"),
    ("risk", "_FACTORS_DIR", ".cache/factors"),
)

# Sample portfolio (DM-D15): about €25,000 in 6 of the 9 stocks, uneven
# weights, bought on different dates inside the snapshot's year; it keeps the
# CHF, DKK and GBX lines and two dividend payers. (ticker, EUR, buy date)
SAMPLE_BUYS: tuple[tuple[str, float, str], ...] = (
    ("ASML.AS",   6000.0, "2025-11-03"),
    ("TTE.PA",    4500.0, "2025-12-01"),
    ("ABI.BR",    4000.0, "2026-01-12"),
    ("NESN.SW",   4000.0, "2026-02-16"),
    ("NOVO-B.CO", 3500.0, "2026-03-02"),
    ("SHEL.L",    3000.0, "2026-04-13"),
)
# The ETF (VWCE) isn't starred: the app lists only stocks with fundamentals.
SAMPLE_WATCHLIST: tuple[str, ...] = ("KBC.BR", "SAP.DE", "MC.PA")
SESSION_DOMAIN = "demo.uvalu.invalid"

# A newer snapshot is looked for at most this often, and loaded only once its
# newest file is this old (a git pull still writing files isn't read half-way).
CHECK_EVERY_S = 300
SETTLE_S = 30
_last_check = 0.0


def current() -> "Workspace | None":
    return _WS


def _set(obj, attr: str, value) -> None:
    _SAVED.append((obj, attr, getattr(obj, attr)))
    setattr(obj, attr, value)


def _redirect(root: Path) -> None:
    for mod_name, attr, rel in REDIRECTS:
        mod = importlib.import_module(mod_name)
        if not hasattr(mod, attr):
            raise AttributeError(f"demo workspace: {mod_name}.{attr} no longer exists")
        target = root / rel
        (target if not target.suffix else target.parent).mkdir(parents=True, exist_ok=True)
        _set(mod, attr, target)
    import screener
    _set(screener.SCREENER_FETCH, "cache_file", root / ".cache" / "fundamentals.json")
    _set(screener.PORTFOLIO_FETCH, "cache_file", root / ".cache" / "portfolio_fundamentals.json")
    import fx
    import marketdata
    _set(marketdata, "_units", None)
    _set(fx, "_cache", None)
    _set(fx, "_currencies", None)


def _install_founder_holdings(src: Path, personal: Path) -> None:
    """The founder's positions in the demo (conflicts policy, open item L32):
    the committed demo-data/compliance/founder_holdings.json, plus the
    personal file when it exists on this machine, so a local demo run can't
    miss a holding the personal app discloses. Written to the redirected
    screener.FOUNDER_HOLDINGS_FILE; an unreadable file raises, as in the app."""
    import screener
    tickers = set(screener.load_founder_holdings(Path(src) / "compliance" / "founder_holdings.json"))
    tickers |= set(screener.load_founder_holdings(personal))
    screener.FOUNDER_HOLDINGS_FILE.write_text(
        json.dumps({"updated": date.today().isoformat(), "tickers": sorted(tickers)}), encoding="utf-8")


def _fx_http_get(snap):
    """A stand-in for fx._http_get answering frankfurter's two request
    shapes from the snapshot's ECB rates."""
    import fx
    import pandas as pd

    def get(path: str, params: "dict | None" = None) -> dict:
        params = params or {}
        if path == "currencies":
            return {c: c for c in ["EUR", *snap.fx.columns]}
        if ".." in path:
            lo, hi = (date.fromisoformat(x) for x in path.split(".."))
            frm, to = (params.get("base") or "EUR").upper(), (params.get("symbols") or "EUR").upper()
            rates = {}
            for ts in snap.fx.index:
                d = ts.date()
                if lo <= d <= hi:
                    r = snap.rate(frm, to, d)
                    if r and not pd.isna(r):
                        rates[d.isoformat()] = {to: r}
            return {"base": frm, "rates": rates}
        raise fx.FxUnavailable(f"demo: no FX data for {path}")
    return get


def _no_factor_download(url: str):
    raise RuntimeError("factor data isn't part of the demo")


def _install_network(snap, rows: dict) -> None:
    import fx
    import risk
    import yfinance
    from uvalu.demo import yfshim
    yfshim.install(snap, rows)
    _set(yfinance, "download", yfshim.download)
    _set(yfinance, "Ticker", yfshim.Ticker)
    _set(fx, "_http_get", _fx_http_get(snap))
    _set(risk, "_fetch_ff_csv", _no_factor_download)


def _warm_caches(snap) -> None:
    import marketdata
    from uvalu.demo import universe
    for t in universe.TICKERS:
        marketdata.record_quote_currency(t, "GBp" if t.endswith(".L") else universe.BY_TICKER[t].currency)
    marketdata.price_history(list(universe.SERIES), period="10y")
    for t in universe.TICKERS:
        marketdata.dividends(t)


def _write_rows(root: Path, rows: dict) -> None:
    import screener
    for t, row in rows.items():
        # Dividend statistics and the next expected ex-date, from the dividend
        # cache warmed above, exactly as _fetch_one adds them.
        row.update(screener._dividend_stats(t))
        row.update(screener._next_expected_ex_div(t))
    text = json.dumps(rows, default=str)
    for f in (screener.SCREENER_FETCH, screener.PORTFOLIO_FETCH):
        f.cache_file.write_text(text, encoding="utf-8")
        f.live_cache.clear()


def activate(src: "Path | None" = None) -> Workspace:
    """Set up the demo workspace once per process; later calls return it."""
    global _WS
    with _lock:
        if _WS is not None:
            return _WS
        from uvalu.demo import rows as rows_mod, snapshot
        # Throwaway secrets: demo data lives only as long as the process.
        os.environ.setdefault("ENCRYPTION_KEY", secrets.token_urlsafe(32))
        os.environ.setdefault("AUTH_SECRET", secrets.token_urlsafe(32))
        root = Path(tempfile.mkdtemp(prefix="uvalu-demo-"))
        src = Path(src or datamode.DEMO_DATA_DIR)
        signature = _signature(src)
        snap = snapshot.load(src)
        rows = rows_mod.build_all(snap)
        import screener
        personal_holdings = screener.FOUNDER_HOLDINGS_FILE
        _redirect(root)
        _install_founder_holdings(src, personal_holdings)
        # A fresh data folder at the current schema, as run_app.py does in
        # production before Streamlit starts (VM-08/VM-09).
        from uvalu import migrations
        migrations.reset_cache()
        migrations.upgrade()
        _install_network(snap, rows)
        _warm_caches(snap)
        _write_rows(root, rows)
        _WS = Workspace(root=root, snapshot=snap, rows=rows,
                        sector_multiples=rows_mod.sector_multiples(snap),
                        src=src, signature=signature)
        _log.info("demo workspace ready", extra={
            "event": "demo.workspace_ready", "root": str(root), "rows": len(rows),
            "last_bar": str(snap.last_bar()), "fundamentals": len(snap.fundamentals)})
        return _WS


def _signature(src: Path) -> tuple:
    """(path, modification time, size) of every file in the snapshot folder."""
    src = Path(src)
    out = []
    for p in sorted(src.rglob("*")):
        if p.is_file():
            st_ = p.stat()
            out.append((p.relative_to(src).as_posix(), st_.st_mtime, st_.st_size))
    return tuple(out)


def refresh_if_newer(now: "float | None" = None) -> bool:
    """Load the snapshot again when demo-data/ changed since it was read.
    Cheap on most runs (a clock check); True when it reloaded, so the caller
    clears Streamlit's caches. Sessions keep their own portfolios."""
    global _last_check
    ws = _WS
    if ws is None:
        return False
    now = time.monotonic() if now is None else now
    if now - _last_check < CHECK_EVERY_S:
        return False
    _last_check = now
    sig = _signature(ws.src)
    if sig == ws.signature or time.time() - max((m for _p, m, _s in sig), default=0.0) < SETTLE_S:
        return False
    with _lock:
        if _WS is not ws or ws.signature == sig:
            return False
        _reload(ws, sig)
    return True


def _reload(ws: Workspace, sig: tuple) -> None:
    import fx
    import marketdata
    from uvalu.demo import rows as rows_mod, snapshot, yfshim
    old_bar = ws.snapshot.last_bar()
    snap = snapshot.load(ws.src)
    rows = rows_mod.build_all(snap)
    yfshim.install(snap, rows)
    fx._http_get = _fx_http_get(snap)      # the original stays saved from activate()
    # The caches warmed from the old snapshot go; the app's own code fills
    # them again from the new one, as at start.
    for d in (marketdata._HISTORY_DIR, marketdata._DIVIDEND_DIR):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    with fx._lock:
        Path(fx._CACHE_FILE).unlink(missing_ok=True)
        fx._cache = None
        fx._currencies = None
    _warm_caches(snap)
    _write_rows(ws.root, rows)
    ws.snapshot, ws.rows, ws.signature = snap, rows, sig
    ws.sector_multiples = rows_mod.sector_multiples(snap)
    _log.info("demo snapshot reloaded", extra={
        "event": "demo.snapshot_reloaded", "last_bar": str(snap.last_bar()),
        "previous_last_bar": str(old_bar), "rows": len(rows)})


def reset_for_tests() -> None:
    """Undo activate(): restore every redirected path and patched function
    and forget the workspace (tests only; a demo process never goes back)."""
    global _WS
    with _lock:
        import screener
        for f in (screener.SCREENER_FETCH, screener.PORTFOLIO_FETCH):
            f.live_cache.clear()
        while _SAVED:
            obj, attr, value = _SAVED.pop()
            setattr(obj, attr, value)
        if _WS is not None:
            shutil.rmtree(_WS.root, ignore_errors=True)
        _WS = None
        global _last_check
        _last_check = 0.0


# ── per-session sample portfolio ─────────────────────────────────────────────

def session_email(session_id: str) -> str:
    return f"demo-{session_id}@{SESSION_DOMAIN}"


def _trading_day_on_or_after(closes, day: date):
    sel = closes[closes.index >= str(day)]
    return (sel.index[0], float(sel.iloc[0])) if not sel.empty else (None, None)


def seed_session(email: str) -> bool:
    """Seed this session's storage with the sample portfolio and watchlist
    when it has none yet. Returns True when it seeded."""
    import pandas as pd
    import portfolio
    from uvalu.demo import rows as rows_mod, universe
    ws = activate()
    portfolio.set_user(email)
    if portfolio.portfolio_exists():
        return False
    snap = ws.snapshot
    for ticker, eur, day in SAMPLE_BUYS:
        closes = snap.closes(ticker, adjusted=False)
        ts, close = _trading_day_on_or_after(closes, date.fromisoformat(day))
        if ts is None:
            continue
        price_q = close / rows_mod.quote_divisor(ticker)
        rate = snap.eur_per(universe.BY_TICKER[ticker].currency, ts.date())
        if not rate:
            continue
        price_eur = price_q * rate
        shares = max(1, int(eur // price_eur))
        portfolio.record_buy({
            "name": universe.BY_TICKER[ticker].name, "ticker": ticker, "shares": shares,
            "purchase_price": round(price_eur, 4), "purchase_value": round(shares * price_eur, 2),
            "dividends": 0.0, "date_in": pd.Timestamp(ts).isoformat(),
        })
    portfolio.save_watchlist(set(SAMPLE_WATCHLIST))
    # The dividends paid since each buy, as the Dividend log's auto-import
    # would add them, so income shows from the first screen.
    pf = portfolio.load_portfolio()
    if pf is not None and not pf.empty:
        portfolio.import_dividends_from_market_data(pf, email)
    _log.info("demo sample portfolio seeded", extra={"event": "demo.sample_seeded"})
    return True


def reset_session(email: str) -> None:
    """Put the sample back: drop this session's storage and seed it again."""
    import portfolio
    portfolio.set_user(email)
    shutil.rmtree(portfolio.user_data_dir(email), ignore_errors=True)
    seed_session(email)


def last_refresh() -> "date | None":
    ws = current()
    return ws.snapshot.last_bar() if ws else None


def fundamentals_as_of() -> "str | None":
    ws = current()
    if not ws:
        return None
    dates = sorted({r.get("fundamentals_as_of") for r in ws.rows.values() if r.get("fundamentals_as_of")})
    return dates[-1] if dates else None
