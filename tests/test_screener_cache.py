"""Tests for screener.py's cache persistence, freshness checks, the
yfinance fetch-one row builder, and the background-fetch orchestration.

All yfinance access is mocked — no real network calls. The background
fetch (_run_fetch/fetch_fundamentals_nowait) spawns a REAL daemon thread;
tests join it directly rather than polling, and time.sleep is stubbed to
keep the (mocked, instant) retry/backoff paths from actually sleeping.
"""
import json
import threading
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
import yfinance as yf

import screener


@pytest.fixture(autouse=True)
def isolated_screener_state(tmp_path, monkeypatch):
    monkeypatch.setattr(screener, "CACHE_FILE", tmp_path / "fundamentals.json")
    monkeypatch.setattr(screener, "_live_cache", {})
    monkeypatch.setattr(screener, "_bg_thread", None)
    monkeypatch.setattr(screener, "_bg_state", {"done": 0, "total": 0, "running": False})
    screener._bg_cancelled.clear()
    yield
    # Always leave the shared cancel flag clear for whichever test runs next.
    screener._bg_cancelled.clear()


# ── _load_cache / _save_cache ─────────────────────────────────────────────

class TestLoadSaveCache:
    def test_load_returns_empty_dict_when_missing(self):
        assert screener._load_cache() == {}

    def test_load_returns_empty_dict_on_corrupt_file(self):
        screener.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        screener.CACHE_FILE.write_text("not valid json{{{", encoding="utf-8")
        assert screener._load_cache() == {}

    def test_save_then_load_roundtrip(self):
        screener._save_cache({"AAA.BR": {"Price": 100.0}})
        assert screener._load_cache() == {"AAA.BR": {"Price": 100.0}}

    def test_save_creates_parent_directory(self, tmp_path, monkeypatch):
        nested = tmp_path / "nested_cache_dir" / "fundamentals.json"
        monkeypatch.setattr(screener, "CACHE_FILE", nested)
        assert not nested.parent.exists()
        screener._save_cache({})
        assert nested.parent.exists()


# ── _is_fresh ──────────────────────────────────────────────────────────────

class TestIsFresh:
    def test_fresh_via_next_fetch_at_in_future(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        assert screener._is_fresh({"next_fetch_at": future}) is True

    def test_stale_via_next_fetch_at_in_past(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert screener._is_fresh({"next_fetch_at": past}) is False

    def test_legacy_fetched_at_fresh_within_ttl(self):
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert screener._is_fresh({"fetched_at": recent}) is True

    def test_legacy_fetched_at_stale_beyond_ttl(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        assert screener._is_fresh({"fetched_at": old}) is False

    def test_malformed_entry_is_not_fresh(self):
        assert screener._is_fresh({}) is False
        assert screener._is_fresh({"fetched_at": "not-a-date"}) is False
        assert screener._is_fresh({"next_fetch_at": "garbage"}) is False


class TestNextFetchAt:
    def test_returns_iso_string_within_jitter_range(self):
        result = screener._next_fetch_at()
        parsed = datetime.fromisoformat(result)
        delta_hours = (parsed - datetime.now(timezone.utc)).total_seconds() / 3600
        lo = screener.CACHE_TTL_HOURS - screener.CACHE_TTL_JITTER
        hi = screener.CACHE_TTL_HOURS + screener.CACHE_TTL_JITTER
        assert lo - 0.1 <= delta_hours <= hi + 0.1


# ── _safe_float ────────────────────────────────────────────────────────────

class TestSafeFloat:
    def test_none_returns_none(self):
        assert screener._safe_float(None) is None

    def test_valid_numeric_converts(self):
        assert screener._safe_float("3.5") == 3.5
        assert screener._safe_float(3) == 3.0

    def test_invalid_returns_none(self):
        assert screener._safe_float("not-a-number") is None
        assert screener._safe_float(object()) is None


# ── _df_from_cache ─────────────────────────────────────────────────────────

class TestDfFromCache:
    def test_returns_rows_present_in_cache(self):
        stocks = [{"ticker": "AAA.BR"}, {"ticker": "BBB.BR"}]
        cache = {"AAA.BR": {"Ticker": "AAA.BR", "Price": 100.0}}
        df = screener._df_from_cache(stocks, cache)
        assert list(df["Ticker"]) == ["AAA.BR"]

    def test_empty_when_nothing_cached(self):
        df = screener._df_from_cache([{"ticker": "AAA.BR"}], {})
        assert df.empty
        assert list(df.columns) == ["Ticker"]


# ── _fetch_one ─────────────────────────────────────────────────────────────

class TestFetchOne:
    def _fake_ticker(self, info: dict):
        return lambda t: type("T", (), {"info": info})()

    def test_extracts_basic_fields(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "shortName": "Alpha Corp", "currentPrice": 100.0, "currency": "EUR",
            "marketCap": 5e9, "sector": "Technology", "country": "Belgium",
        }))
        row = screener._fetch_one("AAA.BR", {"name": "Fallback", "isin": "BE1234"})
        assert row["Name"] == "Alpha Corp"
        assert row["Price"] == 100.0
        assert row["sector"] == "Technology"
        assert row["country"] == "Belgium"
        assert row["ISIN"] == "BE1234"

    def test_falls_back_to_stock_name_when_no_shortname(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({"regularMarketPrice": 50.0}))
        row = screener._fetch_one("AAA.BR", {"name": "Fallback Name", "isin": ""})
        assert row["Name"] == "Fallback Name"
        assert row["Price"] == 50.0

    def test_dividend_yield_computed_from_rate_and_price(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "dividendRate": 4.0,
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["dividendYield"] == pytest.approx(0.04)

    def test_dividend_yield_falls_back_to_raw_field_with_scale_heuristic(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "dividendYield": 6.65,  # >1 -> treated as percent
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["dividendYield"] == pytest.approx(0.0665)

    def test_debt_to_equity_extreme_outlier_rejected(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "debtToEquity": 5000.0,
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["debtToEquity"] is None

    def test_trailing_pe_outside_sane_bounds_rejected(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "trailingPE": 50_000.0,
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["trailingPE"] is None

    def test_fcf_yield_derived_from_fcf_and_market_cap(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "marketCap": 1000.0, "freeCashflow": 50.0,
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["fcfYield"] == pytest.approx(0.05)

    def test_cash_payout_and_coverage_derived(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "dividendRate": 2.0, "sharesOutstanding": 1000.0,
            "freeCashflow": 1000.0, "trailingEps": 5.0,
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["cashPayoutRatio"] == pytest.approx((2.0 * 1000.0) / 1000.0)
        assert row["dividendCoverage"] == pytest.approx(5.0 / 2.0)

    def test_ex_dividend_date_converted_from_unix_timestamp(self, monkeypatch):
        import time
        ts = int(time.mktime((2024, 3, 15, 0, 0, 0, 0, 0, 0)))
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "exDividendDate": ts,
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["exDividendDate"] is not None
        assert "/" in row["exDividendDate"]

    def test_bad_timestamp_becomes_none(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "exDividendDate": "not-a-timestamp",
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["exDividendDate"] is None


# ── get_fetch_progress / cancel_background_fetch / clear_live_cache ─────────

class TestProgressAndCancel:
    def test_get_fetch_progress_returns_copy(self):
        progress = screener.get_fetch_progress()
        assert progress == {"done": 0, "total": 0, "running": False}
        progress["running"] = True
        assert screener._bg_state["running"] is False  # copy, not a live reference

    def test_cancel_sets_event_and_marks_not_running(self):
        screener._bg_state["running"] = True
        screener.cancel_background_fetch()
        assert screener._bg_cancelled.is_set()
        assert screener.get_fetch_progress()["running"] is False

    def test_clear_live_cache_empties_it(self):
        screener._live_cache["AAA.BR"] = {"Price": 1.0}
        screener.clear_live_cache()
        assert screener._live_cache == {}


class TestWarmLiveCache:
    def test_populates_from_disk_only_when_empty(self):
        screener._save_cache({"AAA.BR": {"Price": 100.0}})
        screener._warm_live_cache()
        assert screener._live_cache == {"AAA.BR": {"Price": 100.0}}

    def test_does_not_overwrite_already_warm_cache(self):
        screener._live_cache["BBB.BR"] = {"Price": 5.0}
        screener._save_cache({"AAA.BR": {"Price": 100.0}})
        screener._warm_live_cache()
        assert screener._live_cache == {"BBB.BR": {"Price": 5.0}}


# ── _run_fetch (background worker) ─────────────────────────────────────────

class TestRunFetch:
    def test_fetches_and_persists_all_stale_tickers(self, monkeypatch):
        monkeypatch.setattr(screener, "_fetch_one", lambda ticker, stock: {
            "Name": stock["name"], "Ticker": ticker, "Price": 100.0,
        })
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        cache = {}
        stale = [{"ticker": "AAA.BR", "name": "Alpha", "isin": ""},
                 {"ticker": "BBB.BR", "name": "Beta", "isin": ""}]
        screener._bg_state.update({"done": 0, "total": len(stale), "running": True})
        screener._run_fetch(stale, cache)

        assert set(cache.keys()) == {"AAA.BR", "BBB.BR"}
        assert screener._bg_state["running"] is False
        assert screener._bg_state["done"] == 2
        assert screener._load_cache() == cache

    def test_not_found_error_short_circuits_without_retry(self, monkeypatch):
        calls = []

        def _fake_fetch_one(ticker, stock):
            calls.append(ticker)
            raise ValueError("404 Quote not found")

        monkeypatch.setattr(screener, "_fetch_one", _fake_fetch_one)
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        stale = [{"ticker": "BAD.BR", "name": "Bad", "isin": ""}]
        cache = {}
        screener._run_fetch(stale, cache)

        assert calls == ["BAD.BR"]  # no retries for a definitive 404
        assert cache["BAD.BR"]["fetched_at"] == ""

    def test_rate_limit_retries_then_succeeds(self, monkeypatch):
        attempts = {"n": 0}

        def _fake_fetch_one(ticker, stock):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise ValueError("429 Too Many Requests")
            return {"Name": stock["name"], "Ticker": ticker, "Price": 100.0}

        monkeypatch.setattr(screener, "_fetch_one", _fake_fetch_one)
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        stale = [{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}]
        cache = {}
        screener._run_fetch(stale, cache)

        assert attempts["n"] == 2
        assert cache["AAA.BR"]["Price"] == 100.0

    def test_cancellation_stops_processing(self, monkeypatch):
        def _fake_fetch_one(ticker, stock):
            raise AssertionError("should not be called once cancelled")

        monkeypatch.setattr(screener, "_fetch_one", _fake_fetch_one)
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        screener._bg_cancelled.set()
        stale = [{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}]
        cache = {}
        screener._run_fetch(stale, cache)
        assert cache == {}


# ── fetch_fundamentals_nowait ────────────────────────────────────────────────

class TestFetchFundamentalsNowait:
    def test_all_fresh_serves_from_cache_without_spawning_thread(self, monkeypatch):
        fresh_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        screener._live_cache["AAA.BR"] = {"Ticker": "AAA.BR", "Price": 100.0, "next_fetch_at": fresh_at}

        def _boom(*a, **k):
            raise AssertionError("should not spawn a background fetch for fresh data")
        monkeypatch.setattr(threading, "Thread", _boom)

        result = screener.fetch_fundamentals_nowait([{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}])
        assert list(result["Ticker"]) == ["AAA.BR"]

    def test_stale_spawns_background_thread_that_populates_cache(self, monkeypatch):
        monkeypatch.setattr(screener, "_fetch_one", lambda ticker, stock: {
            "Name": stock["name"], "Ticker": ticker, "Price": 100.0,
        })
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)

        stocks = [{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}]
        result = screener.fetch_fundamentals_nowait(stocks)
        # Whether `result` already has the row depends on a genuine
        # thread-scheduling race (the mocked fetch is instant, so the
        # background thread can legitimately finish before this returns) —
        # not asserted either way. The join below is the deterministic check.
        assert screener._bg_thread is not None

        screener._bg_thread.join(timeout=10)
        assert not screener._bg_thread.is_alive()
        assert screener._live_cache["AAA.BR"]["Price"] == 100.0
        assert screener.get_fetch_progress()["running"] is False
