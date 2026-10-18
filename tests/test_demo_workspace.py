"""Tests for demo mode at run time (demo-mode plan DM-5): the workspace, the
offline stand-ins, the fundamentals rows, the demo universe in the screener
and the per-session sample portfolio.

The real price files are generated (gitignored on master), so a synthetic
snapshot is built in tmp_path from generated prices plus the committed
fundamentals and sector reference. No test reaches the network: a socket
guard fails any connection attempt.
"""
import json
import shutil
import socket
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from uvalu import datamode
from uvalu.demo import rows as demo_rows
from uvalu.demo import universe, workspace

ROOT = Path(__file__).resolve().parent.parent
LAST = pd.Timestamp("2026-10-16")
LEVEL = {"ASML.AS": 1400.0, "SHEL.L": 3900.0, "NOVO-B.CO": 260.0, "^STOXX50E": 6200.0}


def _write_snapshot(root: Path) -> None:
    days = pd.bdate_range(end=LAST, periods=260)
    rng = np.random.default_rng(7)
    market = np.cumsum(rng.normal(0, 0.01, len(days)))
    (root / "eod").mkdir(parents=True)
    for i, key in enumerate(universe.SERIES):
        own = np.cumsum(rng.normal(0, 0.012, len(days)))
        px = LEVEL.get(key, 80.0 + 10 * i) * np.exp(0.8 * market + own)
        pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "open": px, "high": px * 1.01, "low": px * 0.99,
                      "close": px, "adjusted_close": px, "volume": 10_000}).to_csv(
            root / "eod" / f"{key}.csv", index=False)
    (root / "dividends").mkdir()
    pd.DataFrame([{"date": "2026-05-07", "value": 1.0, "unadjusted_value": 1.0, "currency": "EUR",
                   "payment_date": "2026-05-11"}]).to_csv(root / "dividends" / "ABI.BR.csv", index=False)
    pd.DataFrame([{"date": "2026-08-14", "value": 0.36, "unadjusted_value": 0.36, "currency": "USD",
                   "payment_date": "2026-09-22"}]).to_csv(root / "dividends" / "SHEL.L.csv", index=False)
    fx_days = pd.date_range(end=LAST, periods=400, freq="D")
    pd.DataFrame({"date": fx_days.strftime("%Y-%m-%d"), "CHF": 1.07, "DKK": 0.134, "GBP": 1.18,
                  "USD": 0.89}).to_csv(root / "fx.csv", index=False)
    shutil.copytree(ROOT / "demo-data" / "fundamentals", root / "fundamentals")
    shutil.copytree(ROOT / "demo-data" / "reference", root / "reference")


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("demo mode tried to reach the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def ws(tmp_path, monkeypatch, no_network):
    src = tmp_path / "demo-data"
    _write_snapshot(src)
    monkeypatch.setenv(datamode.ENV_VAR, "demo")
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    w = workspace.activate(src)
    yield w
    workspace.reset_for_tests()


# ── workspace ────────────────────────────────────────────────────────────────

def test_every_data_path_points_into_the_workspace(ws):
    import importlib
    for mod_name, attr, rel in workspace.REDIRECTS:
        assert getattr(importlib.import_module(mod_name), attr) == ws.root / rel, (mod_name, attr)
    import screener
    assert screener.SCREENER_FETCH.cache_file.parent == ws.root / ".cache"


def test_no_loaded_module_still_points_at_the_repo_data(ws):
    """A new data path added to some module must be added to REDIRECTS."""
    import sys
    repo_data = {ROOT / "data", ROOT / ".cache"}
    offenders = []
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None) or ""
        parts = Path(f).parts
        # App code only: tests and the offline tools/ scripts never run in the app.
        if not f.startswith(str(ROOT)) or "tests" in parts or "tools" in parts or ".venv" in f:
            continue
        for attr, val in vars(mod).items():
            if isinstance(val, Path) and any(val == d or d in val.parents for d in repo_data):
                offenders.append(f"{name}.{attr}")
            # A default argument is bound when the module loads, so a redirect
            # never reaches it (the L32 founder-holdings bug).
            for default in (getattr(val, "__defaults__", None) or ()):
                if isinstance(default, Path) and any(default == d or d in default.parents for d in repo_data):
                    offenders.append(f"{name}.{attr}() default")
    assert offenders == []


def test_reset_restores_the_personal_paths(tmp_path, monkeypatch, no_network):
    import marketdata
    import yfinance
    before = (marketdata._HISTORY_DIR, yfinance.download)
    src = tmp_path / "demo-data"
    _write_snapshot(src)
    monkeypatch.setenv(datamode.ENV_VAR, "demo")
    workspace.activate(src)
    assert marketdata._HISTORY_DIR != before[0]
    workspace.reset_for_tests()
    assert (marketdata._HISTORY_DIR, yfinance.download) == before
    assert workspace.current() is None


def test_throwaway_secrets_are_set(ws):
    import os
    assert os.environ.get("ENCRYPTION_KEY") and os.environ.get("AUTH_SECRET")


def test_founder_holdings_reach_the_demo(tmp_path, monkeypatch, no_network):
    """L32: the committed demo file and the personal file both count."""
    import screener
    src = tmp_path / "demo-data"
    _write_snapshot(src)
    (src / "compliance").mkdir()
    (src / "compliance" / "founder_holdings.json").write_text(json.dumps({"tickers": ["ASML.AS"]}))
    personal = tmp_path / "personal_holdings.json"
    personal.write_text(json.dumps({"updated": "2026-10-18", "tickers": ["SHEL.L"]}))
    monkeypatch.setattr(screener, "FOUNDER_HOLDINGS_FILE", personal)
    monkeypatch.setenv(datamode.ENV_VAR, "demo")
    try:
        workspace.activate(src)
        assert screener.load_founder_holdings() == {"ASML.AS", "SHEL.L"}
        from settings import ALL_EXCHANGES
        from uvalu import data
        u, _extra = data._build_all_screener_data(tuple(ALL_EXCHANGES))
        held = set(u.loc[u["founder_holds"].astype(bool), "Ticker"]) if "founder_holds" in u.columns else set()
        assert held == {"ASML.AS", "SHEL.L"}
    finally:
        workspace.reset_for_tests()


def test_committed_demo_founder_file_is_valid():
    import screener
    held = screener.load_founder_holdings(ROOT / "demo-data" / "compliance" / "founder_holdings.json")
    assert held <= set(universe.TICKERS)


# ── offline stand-ins ────────────────────────────────────────────────────────

def test_price_history_and_fx_come_from_the_snapshot(ws):
    import fx
    import marketdata
    h = marketdata.price_history(["SHEL.L", "^STOXX50E"], period="1y")
    assert h.index.max() == LAST
    assert h["SHEL.L"].iloc[-1] < 100          # pence → pounds (EX-14)
    assert fx.get_rate("CHF").rate == pytest.approx(1.07)


def test_price_feed_gives_last_two_closes(ws):
    import prices
    p = prices.fetch_prices(("ABI.BR", "NOVO-B.CO"))
    assert p["ABI.BR"]["price"] and p["ABI.BR"]["prev_close"]


def test_yfinance_shape_and_unknown_symbols(ws):
    import yfinance as yf
    raw = yf.download(["ABI.BR", "KBC.BR"], period="5d")
    assert isinstance(raw.columns, pd.MultiIndex) and "Close" in raw.columns.get_level_values(0)
    assert yf.download(["AAPL"], period="5d").empty
    assert yf.download(["ABI.BR"], period="1d", interval="1m").empty       # no intraday
    assert yf.Ticker("AAPL").info == {}
    assert yf.Ticker("SHEL.L").info["currency"] == "GBp"


def test_shell_dividend_declared_in_usd_comes_back_in_pence(ws):
    import yfinance as yf
    d = yf.Ticker("SHEL.L").dividends
    assert d.iloc[-1] == pytest.approx(0.36 * 0.89 / 1.18 * 100)


def test_factor_download_is_off(ws):
    import risk
    with pytest.raises(RuntimeError):
        risk._fetch_ff_csv("https://example.invalid/ff.zip")


# ── rows ─────────────────────────────────────────────────────────────────────

def test_rows_follow_yahoo_conventions(ws):
    abi, shel, kbc = ws.rows["ABI.BR"], ws.rows["SHEL.L"], ws.rows["KBC.BR"]
    assert abi["financialCurrency"] == "USD" and abi["Currency"] == "EUR"
    assert abi["trailingEps"] == 3.45 and abi["netIncome"] == 6837e6
    assert abi["fcfHistory"] == [(14883 - 3656) * 1e6, (15055 - 3863) * 1e6, (13265 - 4638) * 1e6]
    assert shel["Currency"] == "GBP" and shel["Price"] < 100
    assert kbc["ebit"] is None and kbc["freeCashflow"] is None          # bank
    assert ws.rows["VWCE.DE"].get("trailingEps") is None                # the ETF has no fundamentals


def test_sector_multiples_are_clipped_like_medians(ws):
    import screener
    pe, pb = ws.sector_multiples
    lo, hi = screener.PE_MULTIPLE_BAND
    assert all(lo <= v <= hi for v in pe.values())
    assert pe["Technology"] == hi                                       # Damodaran 35 → 30


# ── the screener's demo universe ─────────────────────────────────────────────

def test_screener_scores_all_nine_with_the_reference(ws):
    from settings import ALL_EXCHANGES
    from uvalu import data
    u, _extra = data._build_all_screener_data(tuple(ALL_EXCHANGES))
    assert set(u["Ticker"]) == set(universe.STOCKS)
    assert {"copenhagen", "london"} <= set(u["exchange_key"])
    assert u["fair_value"].notna().sum() >= 8


def test_sector_multiples_change_pe_fair_values():
    import screener
    row = pd.DataFrame([{"Ticker": "X.BR", "sector": "Technology", "Price": 100.0, "trailingEps": 5.0,
                         "trailingPE": 20.0, "bookValue": 20.0, "priceToBook": 5.0}])
    lo = screener.compute_scores(row.copy(), sector_multiples=({"Technology": 10.0}, {}))
    hi = screener.compute_scores(row.copy(), sector_multiples=({"Technology": 30.0}, {}))
    assert hi["pe_fair_value"].iloc[0] > lo["pe_fair_value"].iloc[0]


def test_personal_mode_still_fetches(monkeypatch):
    """The fetch guard only applies in demo mode."""
    import screener
    monkeypatch.delenv(datamode.ENV_VAR, raising=False)
    started = []
    monkeypatch.setattr(screener.logkit, "spawn", lambda *a, **k: started.append(a) or None)
    f = screener._Fetcher(Path("unused.json"))
    f.live_cache["X.BR"] = {"next_fetch_at": "2000-01-01T00:00:00+00:00"}
    monkeypatch.setattr(screener, "_warm_live_cache", lambda _f=None: None)
    screener.fetch_fundamentals_nowait([{"ticker": "X.BR", "name": "X", "isin": ""}], fetcher=f)
    assert started


# ── per-session sample portfolio ─────────────────────────────────────────────

def test_seed_and_reset_session(ws):
    import portfolio
    email = workspace.session_email("abc123")
    assert workspace.seed_session(email) is True
    assert workspace.seed_session(email) is False          # only once
    pf = portfolio.load_portfolio()
    assert sorted(pf["ticker"]) == sorted(t for t, _e, _d in workspace.SAMPLE_BUYS)
    assert 23_000 < pf["purchase_value"].sum() <= 25_000
    assert portfolio.load_watchlist() == set(workspace.SAMPLE_WATCHLIST)

    portfolio.save_portfolio(pf.iloc[:1])
    workspace.reset_session(email)
    assert len(portfolio.load_portfolio()) == len(workspace.SAMPLE_BUYS)


def test_sessions_are_separate(ws):
    import portfolio
    a, b = workspace.session_email("aaa"), workspace.session_email("bbb")
    workspace.seed_session(a)
    portfolio.save_portfolio(portfolio.load_portfolio().iloc[:2])
    workspace.seed_session(b)
    assert len(portfolio.load_portfolio()) == len(workspace.SAMPLE_BUYS)
    portfolio.set_user(a)
    assert len(portfolio.load_portfolio()) == 2


def test_status_dates(ws):
    assert workspace.last_refresh() == LAST.date()
    assert workspace.fundamentals_as_of() == "2025-12-31"


# ── a newer snapshot without a restart ───────────────────────────────────────

def _add_day(src: Path, day: str, close: float, chf: float) -> None:
    import os
    import time as _time
    p = src / "eod" / "ABI.BR.csv"
    df = pd.read_csv(p)
    df.loc[len(df)] = {"date": day, "open": close, "high": close, "low": close, "close": close,
                       "adjusted_close": close, "volume": 10_000}
    df.to_csv(p, index=False)
    fxp = src / "fx.csv"
    f = pd.read_csv(fxp)
    f.loc[len(f)] = {"date": day, "CHF": chf, "DKK": 0.134, "GBP": 1.18, "USD": 0.89}
    f.to_csv(fxp, index=False)
    old = _time.time() - workspace.SETTLE_S - 5      # settled, like a finished git pull
    for q in src.rglob("*"):
        if q.is_file():
            os.utime(q, (old, old))


def test_newer_snapshot_is_loaded_in_place(ws):
    import fx
    import marketdata
    import screener
    src = ws.src
    assert workspace.refresh_if_newer(now=1e9) is False          # nothing changed
    _add_day(src, "2026-10-17", 123.45, 1.05)
    assert workspace.refresh_if_newer(now=1e9 + 1) is False      # checked too recently
    assert workspace.refresh_if_newer(now=1e9 + 2 * workspace.CHECK_EVERY_S) is True
    assert workspace.last_refresh() == pd.Timestamp("2026-10-17").date()
    h = marketdata.price_history(["ABI.BR"], period="1y")
    assert h.index.max() == pd.Timestamp("2026-10-17") and h["ABI.BR"].iloc[-1] == pytest.approx(123.45)
    assert fx.get_rate("CHF").rate == pytest.approx(1.05)
    cached = json.loads(screener.SCREENER_FETCH.cache_file.read_text(encoding="utf-8"))
    assert cached["ABI.BR"]["Price"] == pytest.approx(123.45)


def test_snapshot_still_being_written_waits(ws):
    import os
    import time as _time
    _add_day(ws.src, "2026-10-17", 99.0, 1.05)
    now = _time.time()
    os.utime(ws.src / "fx.csv", (now, now))                     # a file written just now
    assert workspace.refresh_if_newer(now=1e9) is False
    assert workspace.last_refresh() == LAST.date()
