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
    # All background-fetch state now lives on the SCREENER_FETCH / PORTFOLIO_FETCH
    # _Fetcher instances (screener.py), not module globals — patch their fields
    # so tests never touch the real .cache/*.json or spawn a real fetch.
    for _name, _f in (("fundamentals.json", screener.SCREENER_FETCH),
                      ("portfolio_fundamentals.json", screener.PORTFOLIO_FETCH)):
        monkeypatch.setattr(_f, "cache_file", tmp_path / _name)
        monkeypatch.setattr(_f, "live_cache", {})
        monkeypatch.setattr(_f, "bg_thread", None)
        monkeypatch.setattr(_f, "state", {"done": 0, "total": 0, "running": False})
        _f.cancelled.clear()
    yield
    # Always leave the shared cancel flags clear for whichever test runs next.
    screener.SCREENER_FETCH.cancelled.clear()
    screener.PORTFOLIO_FETCH.cancelled.clear()


# ── _load_cache / _save_cache ─────────────────────────────────────────────

class TestLoadSaveCache:
    def test_load_returns_empty_dict_when_missing(self):
        assert screener._load_cache() == {}

    def test_load_returns_empty_dict_on_corrupt_file(self):
        screener.SCREENER_FETCH.cache_file.parent.mkdir(parents=True, exist_ok=True)
        screener.SCREENER_FETCH.cache_file.write_text("not valid json{{{", encoding="utf-8")
        assert screener._load_cache() == {}

    def test_save_then_load_roundtrip(self):
        screener._save_cache({"AAA.BR": {"Price": 100.0}})
        assert screener._load_cache() == {"AAA.BR": {"Price": 100.0}}

    def test_save_creates_parent_directory(self, tmp_path, monkeypatch):
        nested = tmp_path / "nested_cache_dir" / "fundamentals.json"
        monkeypatch.setattr(screener.SCREENER_FETCH, "cache_file", nested)
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

    def test_short_flag_uses_short_ttl(self):
        parsed = datetime.fromisoformat(screener._next_fetch_at(short=True))
        delta_hours = (parsed - datetime.now(timezone.utc)).total_seconds() / 3600
        assert screener.CACHE_TTL_SHORT_HOURS - 1.1 <= delta_hours <= screener.CACHE_TTL_SHORT_HOURS + 1.1
        assert delta_hours < screener.CACHE_TTL_HOURS - screener.CACHE_TTL_JITTER


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


# ── _row_is_scorable (WP-A gate) ──────────────────────────────────────────

class TestRowIsScorable:
    def test_positive_eps_is_scorable(self):
        assert screener._row_is_scorable({"trailingEps": 4.2}) is True

    def test_analyst_target_alone_is_scorable(self):
        assert screener._row_is_scorable({"targetMeanPrice": 88.0}) is True

    def test_dividend_needs_payout_to_count(self):
        assert screener._row_is_scorable({"dividendRate": 4.0}) is False
        assert screener._row_is_scorable({"dividendRate": 4.0, "payoutRatio": 0.6}) is True

    def test_book_value_needs_a_sane_pe_to_count(self):
        assert screener._row_is_scorable({"bookValue": 80.0}) is False
        assert screener._row_is_scorable({"bookValue": 80.0, "trailingPE": 6.0}) is True
        assert screener._row_is_scorable({"bookValue": 80.0, "trailingPE": 999.0}) is False

    def test_ebit_history_needs_enterprise_value(self):
        assert screener._row_is_scorable({"ebitHistory": [10.0, 11.0, 12.0]}) is False
        assert screener._row_is_scorable(
            {"ebitHistory": [10.0, 11.0, 12.0], "enterpriseValue": 5e8}) is True

    def test_degraded_portfolio_row_is_rescued_by_pe_plus_book(self):
        # AED.BR / CPINV.BR / FGR.PA as they sat in portfolio_fundamentals.json:
        # no EPS / payout / target / EV, but a sane P/E and a book value — which
        # WP-B turns into a usable EPS, so the gate must treat it as scorable and
        # NOT send it round the thin-payload retry.
        degraded = {
            "Price": 68.1, "trailingPE": 5.93, "bookValue": 79.8, "dividendRate": 4.0,
            "trailingEps": None, "payoutRatio": None, "targetMeanPrice": None,
            "enterpriseValue": None,
        }
        assert screener._row_is_scorable(degraded) is True
        # Strip the P/E too and there is genuinely nothing to value it on.
        assert screener._row_is_scorable({**degraded, "trailingPE": None}) is False

    def test_nan_values_are_treated_as_missing(self):
        assert screener._row_is_scorable({"trailingEps": float("nan")}) is False

    def test_accepts_a_pandas_series(self):
        assert screener._row_is_scorable(pd.Series({"trailingEps": 3.0})) is True


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

    def test_trailing_eps_recovered_from_pe_when_missing(self, monkeypatch):
        # Partial-payload shape: P/E present, trailingEps absent (WP-B).
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 68.1, "trailingPE": 5.9269,
        }))
        row = screener._fetch_one("AED.BR", {"name": "Aedifica", "isin": ""})
        assert row["trailingEps"] == pytest.approx(11.49, abs=0.01)
        assert row["trailingEps_derived"] is True

    def test_trailing_eps_not_recovered_when_pe_absurd(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "trailingPE": 0.4,   # inside 0<pe<10_000 but outside _PE_DERIVE_BAND
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["trailingEps"] is None
        assert row["trailingEps_derived"] is False

    def test_real_trailing_eps_is_left_untouched(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({
            "currentPrice": 100.0, "trailingPE": 8.0, "trailingEps": 9.99,
        }))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["trailingEps"] == 9.99
        assert row["trailingEps_derived"] is False

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

    def test_statement_history_folded_into_row(self, monkeypatch):
        cols = pd.to_datetime(["2024-12-31", "2023-12-31", "2022-12-31"])

        def _mkstmt(rows):
            return pd.DataFrame({n: pd.Series(v, index=cols) for n, v in rows.items()}).T

        def _fake(_t):
            obj = type("T", (), {})()
            obj.info = {"currentPrice": 100.0}
            obj.income_stmt = _mkstmt({"Total Revenue": [300.0, 250.0, 200.0],
                                       "EBIT": [60.0, 50.0, 40.0]})
            obj.balance_sheet = _mkstmt({"Total Assets": [1000.0, 950.0, 900.0]})
            obj.cashflow = _mkstmt({"Free Cash Flow": [55.0, 45.0, 35.0],
                                    "Operating Cash Flow": [70.0, 60.0, 50.0]})
            return obj

        monkeypatch.setattr(yf, "Ticker", _fake)
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["revenueHistory"] == [300.0, 250.0, 200.0]
        assert row["ebitHistory"] == [60.0, 50.0, 40.0]
        assert row["cfoHistory"] == [70.0, 60.0, 50.0]
        assert row["totalAssetsHistory"] == [1000.0, 950.0, 900.0]
        assert row["fcfHistory"] == [55.0, 45.0, 35.0]
        assert row["retainedEarningsHistory"] is None   # row not exposed

    def test_statement_history_absent_ticker_attrs_leave_none_keys(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", self._fake_ticker({"currentPrice": 100.0}))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        for k in screener._STATEMENT_HISTORY_KEYS:
            assert row[k] is None


# ── get_fetch_progress / cancel_background_fetch / clear_live_cache ─────────

class TestProgressAndCancel:
    def test_get_fetch_progress_returns_copy(self):
        progress = screener.get_fetch_progress()
        assert progress == {"done": 0, "total": 0, "running": False}
        progress["running"] = True
        assert screener.SCREENER_FETCH.state["running"] is False  # copy, not a live reference

    def test_cancel_sets_event_and_marks_not_running(self):
        screener.SCREENER_FETCH.state["running"] = True
        screener.cancel_background_fetch()
        assert screener.SCREENER_FETCH.cancelled.is_set()
        assert screener.get_fetch_progress()["running"] is False

    def test_clear_live_cache_empties_it(self):
        screener.SCREENER_FETCH.live_cache["AAA.BR"] = {"Price": 1.0}
        screener.clear_live_cache()
        assert screener.SCREENER_FETCH.live_cache == {}


class TestWarmLiveCache:
    def test_populates_from_disk_only_when_empty(self):
        screener._save_cache({"AAA.BR": {"Price": 100.0}})
        screener._warm_live_cache()
        assert screener.SCREENER_FETCH.live_cache == {"AAA.BR": {"Price": 100.0}}

    def test_does_not_overwrite_already_warm_cache(self):
        screener.SCREENER_FETCH.live_cache["BBB.BR"] = {"Price": 5.0}
        screener._save_cache({"AAA.BR": {"Price": 100.0}})
        screener._warm_live_cache()
        assert screener.SCREENER_FETCH.live_cache == {"BBB.BR": {"Price": 5.0}}


# ── _run_fetch (background worker) ─────────────────────────────────────────

class TestRunFetch:
    def test_fetches_and_persists_all_stale_tickers(self, monkeypatch):
        # trailingEps present -> _row_is_scorable is True, so the row isn't
        # treated as a thin partial payload and retried (WP-A).
        monkeypatch.setattr(screener, "_fetch_one", lambda ticker, stock: {
            "Name": stock["name"], "Ticker": ticker, "Price": 100.0, "trailingEps": 5.0,
        })
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        cache = {}
        stale = [{"ticker": "AAA.BR", "name": "Alpha", "isin": ""},
                 {"ticker": "BBB.BR", "name": "Beta", "isin": ""}]
        screener.SCREENER_FETCH.state.update({"done": 0, "total": len(stale), "running": True})
        screener._run_fetch(stale, cache)

        assert set(cache.keys()) == {"AAA.BR", "BBB.BR"}
        assert screener.SCREENER_FETCH.state["running"] is False
        assert screener.SCREENER_FETCH.state["done"] == 2
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
            return {"Name": stock["name"], "Ticker": ticker, "Price": 100.0, "trailingEps": 5.0}

        monkeypatch.setattr(screener, "_fetch_one", _fake_fetch_one)
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        stale = [{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}]
        cache = {}
        screener._run_fetch(stale, cache)

        assert attempts["n"] == 2
        assert cache["AAA.BR"]["Price"] == 100.0

    def test_thin_priced_row_retried_then_cached_on_short_ttl(self, monkeypatch):
        calls = []

        def _fake_fetch_one(ticker, stock):
            calls.append(ticker)
            # Priced, but nothing any fair-value model can use (WP-A).
            return {"Name": stock["name"], "Ticker": ticker, "Price": 100.0}

        monkeypatch.setattr(screener, "_fetch_one", _fake_fetch_one)
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        cache = {}
        screener._run_fetch([{"ticker": "AED.BR", "name": "Aedifica", "isin": ""}], cache)

        assert len(calls) == 1 + screener._THIN_ROW_RETRIES        # one try + the retries
        row = cache["AED.BR"]
        assert row["Price"] == 100.0                               # still cached, holding keeps a price
        delta_h = (datetime.fromisoformat(row["next_fetch_at"])
                   - datetime.now(timezone.utc)).total_seconds() / 3600
        assert 0 < delta_h < screener.CACHE_TTL_HOURS - screener.CACHE_TTL_JITTER

    def test_thin_row_without_price_is_not_retried(self, monkeypatch):
        calls = []

        def _fake_fetch_one(ticker, stock):
            calls.append(ticker)
            return {"Name": stock["name"], "Ticker": ticker}   # dead / blocked symbol

        monkeypatch.setattr(screener, "_fetch_one", _fake_fetch_one)
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        cache = {}
        screener._run_fetch([{"ticker": "DEAD.BR", "name": "Dead", "isin": ""}], cache)

        assert calls == ["DEAD.BR"]            # no spin on a symbol retrying can't fix
        assert "DEAD.BR" in cache

    def test_thin_row_that_recovers_on_retry_is_kept(self, monkeypatch):
        attempts = {"n": 0}

        def _fake_fetch_one(ticker, stock):
            attempts["n"] += 1
            base = {"Name": stock["name"], "Ticker": ticker, "Price": 100.0}
            if attempts["n"] >= 2:
                base["trailingEps"] = 5.0          # second call comes back complete
            return base

        monkeypatch.setattr(screener, "_fetch_one", _fake_fetch_one)
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        cache = {}
        screener._run_fetch([{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}], cache)

        assert attempts["n"] == 2
        assert cache["AAA.BR"]["trailingEps"] == 5.0
        assert "next_fetch_at" not in cache["AAA.BR"]   # not forced onto the short TTL

    def test_cancellation_stops_processing(self, monkeypatch):
        def _fake_fetch_one(ticker, stock):
            raise AssertionError("should not be called once cancelled")

        monkeypatch.setattr(screener, "_fetch_one", _fake_fetch_one)
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        screener.SCREENER_FETCH.cancelled.set()
        stale = [{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}]
        cache = {}
        screener._run_fetch(stale, cache)
        assert cache == {}


# ── fetch_fundamentals_nowait ────────────────────────────────────────────────

class TestFetchFundamentalsNowait:
    def test_all_fresh_serves_from_cache_without_spawning_thread(self, monkeypatch):
        fresh_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        screener.SCREENER_FETCH.live_cache["AAA.BR"] = {"Ticker": "AAA.BR", "Price": 100.0, "next_fetch_at": fresh_at}

        def _boom(*a, **k):
            raise AssertionError("should not spawn a background fetch for fresh data")
        monkeypatch.setattr(threading, "Thread", _boom)

        result = screener.fetch_fundamentals_nowait([{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}])
        assert list(result["Ticker"]) == ["AAA.BR"]

    def test_stale_spawns_background_thread_that_populates_cache(self, monkeypatch):
        monkeypatch.setattr(screener, "_fetch_one", lambda ticker, stock: {
            "Name": stock["name"], "Ticker": ticker, "Price": 100.0, "trailingEps": 5.0,
        })
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)

        stocks = [{"ticker": "AAA.BR", "name": "Alpha", "isin": ""}]
        result = screener.fetch_fundamentals_nowait(stocks)
        # Whether `result` already has the row depends on a genuine
        # thread-scheduling race (the mocked fetch is instant, so the
        # background thread can legitimately finish before this returns) —
        # not asserted either way. The join below is the deterministic check.
        assert screener.SCREENER_FETCH.bg_thread is not None

        screener.SCREENER_FETCH.bg_thread.join(timeout=10)
        assert not screener.SCREENER_FETCH.bg_thread.is_alive()
        assert screener.SCREENER_FETCH.live_cache["AAA.BR"]["Price"] == 100.0
        assert screener.get_fetch_progress()["running"] is False


# ── priority queue + two-lane independence + load_fundamentals_cache ─────────

class TestPriorityAndLanes:
    def _stub_fetch(self, monkeypatch, order):
        monkeypatch.setattr(screener, "MAX_WORKERS", 1)   # sequential → deterministic order
        monkeypatch.setattr(screener.time, "sleep", lambda *_: None)
        monkeypatch.setattr(screener, "_fetch_one", lambda t, s: (
            order.append(t) or {"Ticker": t, "Name": s["name"], "Price": 1.0, "trailingEps": 0.5}))

    def test_priority_tickers_fetched_before_the_rest(self, monkeypatch):
        order: list[str] = []
        self._stub_fetch(monkeypatch, order)
        stocks = [{"ticker": f"T{i}.BR", "name": f"n{i}", "isin": ""} for i in range(8)]
        priority = stocks[5:]   # T5/T6/T7 — given last, must still be fetched first
        screener.fetch_fundamentals_nowait(stocks, priority=priority)
        screener.SCREENER_FETCH.bg_thread.join(timeout=10)
        assert order[:3] == ["T5.BR", "T6.BR", "T7.BR"]

    def test_portfolio_lane_is_independent_of_screener_lane(self, monkeypatch):
        order: list[str] = []
        self._stub_fetch(monkeypatch, order)
        screener.fetch_fundamentals_nowait(
            [{"ticker": "P.BR", "name": "P", "isin": ""}], fetcher=screener.PORTFOLIO_FETCH)
        screener.PORTFOLIO_FETCH.bg_thread.join(timeout=10)

        assert "P.BR" in screener.PORTFOLIO_FETCH.live_cache
        assert screener.PORTFOLIO_FETCH.cache_file.exists()
        assert screener.SCREENER_FETCH.live_cache == {}          # untouched
        assert not screener.SCREENER_FETCH.cache_file.exists()   # untouched
        assert screener.SCREENER_FETCH.bg_thread is None

    def test_load_fundamentals_cache_merges_both_lanes_portfolio_wins(self):
        screener.SCREENER_FETCH.live_cache.update({"A.BR": {"Price": 1}, "B.BR": {"Price": 2}})
        screener.PORTFOLIO_FETCH.live_cache.update({"B.BR": {"Price": 99}, "C.BR": {"Price": 3}})
        merged = screener.load_fundamentals_cache()
        assert merged == {"A.BR": {"Price": 1}, "B.BR": {"Price": 99}, "C.BR": {"Price": 3}}
