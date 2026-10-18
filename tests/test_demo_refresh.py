"""Tests for the demo refresh job (demo-mode plan DM-3): budget, EODHD client,
snapshot store and tools/demo_refresh.py. No network: a fake transport
returns synthetic EODHD-shaped responses."""
import json
import logging
from datetime import date, timedelta

import pandas as pd
import pytest
import requests

from tools import demo_refresh
from uvalu.demo import eodhd, store
from uvalu.demo.budget import Budget, BudgetExhausted

TOKEN = "sekret-token-123"
TODAY = date(2026, 10, 19)


def _bars(n=5, last=TODAY, close=100.0, adj_factor=1.0):
    days = [last - timedelta(days=i) for i in range(n)][::-1]
    return [{"date": d.isoformat(), "open": close, "high": close + 1, "low": close - 1,
             "close": close + i, "adjusted_close": (close + i) * adj_factor, "volume": 1000}
            for i, d in enumerate(days)]


class FakeTransport:
    def __init__(self, replies=None, default=None):
        self.replies = dict(replies or {})       # symbol -> list of (status, body) or exception
        self.default = default if default is not None else (200, _bars())
        self.calls = []

    def __call__(self, url, params):
        self.calls.append((url, dict(params)))
        symbol = url.rsplit("/", 1)[-1]
        queue = self.replies.get(symbol)
        reply = queue.pop(0) if queue else self.default
        if isinstance(reply, Exception):
            raise reply
        return reply


# ── Budget ───────────────────────────────────────────────────────────────────

def test_budget_stops_at_18_and_persists(tmp_path):
    b = Budget(tmp_path / "budget.json", run_cap=50, day="2026-10-19")
    for _ in range(18):
        b.spend()
    with pytest.raises(BudgetExhausted, match="daily stop"):
        b.spend()
    again = Budget(tmp_path / "budget.json", day="2026-10-19")
    assert again.calls_today == 18 and again.remaining == 0


def test_budget_resets_on_a_new_day(tmp_path):
    Budget(tmp_path / "budget.json", day="2026-10-19").spend()
    assert Budget(tmp_path / "budget.json", day="2026-10-20").calls_today == 0


def test_budget_run_cap(tmp_path):
    b = Budget(tmp_path / "budget.json", run_cap=2, day="2026-10-19")
    b.spend(); b.spend()
    with pytest.raises(BudgetExhausted, match="run cap"):
        b.spend()


def test_budget_counts_before_the_call(tmp_path):
    b = Budget(tmp_path / "budget.json", day="2026-10-19")
    c = eodhd.Client(TOKEN, b, FakeTransport(default=eodhd.Transient("network error: X")))

    with pytest.raises(eodhd.Transient):
        c.eod("ABI.BR", "2025-10-19", "2026-10-19")
    assert json.loads((tmp_path / "budget.json").read_text())["calls"] == 1


# ── Client ───────────────────────────────────────────────────────────────────

def test_client_maps_statuses(tmp_path):
    b = Budget(tmp_path / "b.json", run_cap=20, day="2026-10-19")
    t = FakeTransport({"A.BR": [(404, None)], "B.BR": [(401, None)], "C.BR": [(500, None)],
                       "D.BR": [(200, {"error": "x"})]})
    c = eodhd.Client(TOKEN, b, t)
    with pytest.raises(eodhd.NotFound):
        c.eod("A.BR", "s", "e")
    with pytest.raises(eodhd.AuthError):
        c.eod("B.BR", "s", "e")
    with pytest.raises(eodhd.Transient):
        c.eod("C.BR", "s", "e")
    with pytest.raises(eodhd.Transient, match="unexpected"):
        c.eod("D.BR", "s", "e")


def test_client_limit_reply_exhausts_the_budget(tmp_path):
    b = Budget(tmp_path / "b.json", day="2026-10-19")
    c = eodhd.Client(TOKEN, b, FakeTransport(default=(402, None)))
    with pytest.raises(BudgetExhausted):
        c.eod("ABI.BR", "s", "e")
    assert Budget(tmp_path / "b.json", day="2026-10-19").remaining == 0


def test_client_sends_token_and_json_format(tmp_path):
    t = FakeTransport()
    eodhd.Client(TOKEN, Budget(tmp_path / "b.json"), t).eod("SAP.XETRA", "2025-10-19", "2026-10-19")
    url, params = t.calls[0]
    assert url.endswith("/eod/SAP.XETRA")
    assert params["api_token"] == TOKEN and params["fmt"] == "json"
    assert params["from"] == "2025-10-19" and params["to"] == "2026-10-19"


def test_client_requires_a_token(tmp_path):
    with pytest.raises(eodhd.AuthError):
        eodhd.Client("", Budget(tmp_path / "b.json"))


def test_token_never_reaches_logs_or_errors(tmp_path, monkeypatch, caplog):
    """requests puts the full URL (with api_token) in its exception text."""
    def boom(*a, **k):
        raise requests.ConnectionError(f"Max retries exceeded with url: /api/eod/X?api_token={TOKEN}")
    monkeypatch.setattr(eodhd.requests, "get", boom)
    c = eodhd.Client(TOKEN, Budget(tmp_path / "b.json"))
    with caplog.at_level(logging.DEBUG), pytest.raises(eodhd.Transient) as exc:
        c.eod("ABI.BR", "s", "e")
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    assert TOKEN not in caplog.text
    assert all(TOKEN not in str(getattr(r, "params", "")) for r in caplog.records)


# ── Store ────────────────────────────────────────────────────────────────────

def test_clean_eod_drops_bad_rows():
    rows = [{"date": "2026-10-16", "close": 10, "adjusted_close": None},
            {"date": "2026-10-17", "close": 0},
            {"date": "", "close": 5},
            {"date": "2026-10-16", "close": 11, "adjusted_close": 10.5},
            "junk"]
    df = store.clean_eod(rows)
    assert df["date"].tolist() == ["2026-10-16"]
    assert df["close"].iloc[0] == 11 and df["adjusted_close"].iloc[0] == 10.5


def test_empty_response_never_touches_history(tmp_path):
    store.write_eod(tmp_path, "ABI.BR", _bars(5))
    before = store.eod_path(tmp_path, "ABI.BR").read_text()
    assert store.write_eod(tmp_path, "ABI.BR", []) == (0, TODAY.isoformat())
    assert store.write_eod(tmp_path, "ABI.BR", {"error": "x"})[0] == 0
    assert store.eod_path(tmp_path, "ABI.BR").read_text() == before


def test_shorter_response_keeps_older_bars(tmp_path):
    store.write_eod(tmp_path, "ABI.BR", _bars(10, last=TODAY - timedelta(days=1)))
    new, last = store.write_eod(tmp_path, "ABI.BR", _bars(2))
    df = store.read_eod(tmp_path, "ABI.BR")
    assert len(df) == 11 and new == 1 and last == TODAY.isoformat()


def test_older_adjusted_closes_rescaled_after_a_dividend():
    old = store.clean_eod(_bars(6, last=TODAY - timedelta(days=1)))
    fresh = store.clean_eod(_bars(3, last=TODAY, close=103.0, adj_factor=0.9))
    merged = store.merge_eod(old, fresh)
    first_fresh = fresh["date"].min()
    o = old.set_index("date")["adjusted_close"]
    f = fresh.set_index("date")["adjusted_close"]
    m = merged.set_index("date")["adjusted_close"]
    factor = f[first_fresh] / o[first_fresh]
    oldest = old["date"].iloc[0]
    assert m[oldest] == pytest.approx(o[oldest] * factor)
    assert m[first_fresh] == pytest.approx(f[first_fresh])


def test_dividends_merge(tmp_path):
    rows = [{"date": "2026-05-01", "value": 0.82, "unadjustedValue": 0.82, "currency": "EUR",
             "paymentDate": "2026-05-08"}]
    assert store.write_dividends(tmp_path, "ABI.BR", rows) == 1
    assert store.write_dividends(tmp_path, "ABI.BR", rows) == 0
    assert store.write_dividends(tmp_path, "ABI.BR", []) == 0


def test_fx_merge(tmp_path):
    a = pd.DataFrame({"CHF": [1.07, 1.08]}, index=pd.to_datetime(["2026-10-15", "2026-10-16"]))
    b = pd.DataFrame({"CHF": [1.09], "DKK": [0.134]}, index=pd.to_datetime(["2026-10-16"]))
    store.write_fx(tmp_path, a)
    assert store.write_fx(tmp_path, b) == 2
    df = pd.read_csv(tmp_path / "fx.csv").set_index("date")
    assert df.loc["2026-10-16", "CHF"] == 1.09 and df.loc["2026-10-16", "DKK"] == 0.134
    assert store.write_fx(tmp_path, pd.DataFrame()) == 0


# ── The tool ─────────────────────────────────────────────────────────────────

def _run(tmp_path, transport=None, **kw):
    lines = []
    args = dict(root=tmp_path, tickers=["ABI.BR", "SAP.DE", "SHEL.L"], prices=True,
                dividends=False, fx=False, live=True, token=TOKEN,
                transport=transport or FakeTransport(), today=TODAY, out=lines.append,
                fx_rates=lambda *a: pd.DataFrame())
    args.update(kw)
    return demo_refresh.run(**args), lines


def test_dry_run_calls_and_writes_nothing(tmp_path):
    t = FakeTransport()
    root = tmp_path / "demo-data"
    code, lines = _run(root, t, live=False, token="")
    assert code == 0 and t.calls == [] and not root.exists()
    assert any("SAP.XETRA" in l for l in lines) and any("Would use 3 calls" in l for l in lines)


def test_live_run_writes_snapshot_and_status(tmp_path):
    t = FakeTransport()
    code, _ = _run(tmp_path, t)
    assert code == 0 and len(t.calls) == 3
    assert [u.rsplit("/", 1)[-1] for u, _ in t.calls] == ["ABI.BR", "SAP.XETRA", "SHEL.LSE"]
    assert store.read_eod(tmp_path, "SHEL.L") is not None
    status = store.read_refresh(tmp_path)
    assert status["last_bar"]["SAP.DE"] == TODAY.isoformat()
    assert status["last_run"]["calls"] == 3 and status["refreshed_at"]
    assert json.loads((tmp_path / "budget.json").read_text())["calls"] == 3


def test_not_found_is_not_retried_and_run_continues(tmp_path):
    t = FakeTransport({"SAP.XETRA": [(404, None)]})
    code, _ = _run(tmp_path, t)
    assert code == 1 and len(t.calls) == 3
    assert "SAP.DE" in store.read_refresh(tmp_path)["last_run"]["errors"]


def test_transient_is_retried_once(tmp_path):
    t = FakeTransport({"ABI.BR": [(503, None), (200, _bars())]})
    code, _ = _run(tmp_path, t, tickers=["ABI.BR"])
    assert code == 0 and len(t.calls) == 2


def test_limit_reply_stops_the_run(tmp_path):
    t = FakeTransport({"SAP.XETRA": [(429, None)]})
    code, _ = _run(tmp_path, t)
    assert code == 2 and len(t.calls) == 2          # SHEL.L never asked


def test_run_cap_stops_before_calling(tmp_path):
    t = FakeTransport()
    code, _ = _run(tmp_path, t, max_calls=1)
    assert code == 2 and len(t.calls) == 1


def test_failed_run_keeps_last_good_refresh_date(tmp_path):
    _run(tmp_path)
    first = store.read_refresh(tmp_path)["refreshed_at"]
    code, _ = _run(tmp_path, FakeTransport(default=(500, None)))
    status = store.read_refresh(tmp_path)
    assert code == 1 and status["refreshed_at"] == first
    assert status["last_bar"]["ABI.BR"] == TODAY.isoformat()


def test_main_rejects_tickers_outside_the_demo(capsys):
    with pytest.raises(SystemExit):
        demo_refresh.main(["--tickers", "AAPL.US"])
