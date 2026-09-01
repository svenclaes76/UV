"""Tests for uvalu/data.py — the screener/price cache-backed data layer
between yfinance/fetch_tickers/screener and the UI pages.

Background-fetch state now lives on screener.py's SCREENER_FETCH /
PORTFOLIO_FETCH _Fetcher instances (own thread + cache file each), so
isolating this module means pointing both fetchers' cache_file at tmp_path
and clearing their live caches — data.py reads them through the instance
(screener.SCREENER_FETCH.cache_file) rather than a by-value Path constant.

Fair value / sector / country / dividend fields used to have a second,
simpler computation here (_compute_fair_values/_fetch_fundamentals/
_fetch_live_data) that could disagree with screener.py's own multi-model
pipeline for the same ticker. That duplicate engine has been removed —
pages needing those fields now look them up from their already-loaded
scored DataFrame (_load_all_screener_data) by ticker instead. This module
now only fetches live prices (_fetch_prices_cached).
"""
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import screener
from uvalu import data as data_module
from tests.conftest import make_portfolio_df


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(screener.SCREENER_FETCH, "cache_file", tmp_path / "fundamentals.json")
    monkeypatch.setattr(screener.PORTFOLIO_FETCH, "cache_file", tmp_path / "portfolio_fundamentals.json")
    monkeypatch.setattr(screener.SCREENER_FETCH, "live_cache", {})
    monkeypatch.setattr(screener.PORTFOLIO_FETCH, "live_cache", {})
    # _fetch_prices_cached is @st.cache_data-wrapped and process-global —
    # without clearing, a later test calling it with the SAME args as an
    # earlier one would silently get that earlier test's cached return value.
    import streamlit as st
    st.cache_data.clear()
    # _debounced_bucket() keeps process-global state (last token + timestamp +
    # running flag) that would otherwise leak the debounce clock between tests.
    data_module._version_state.update(token=None, advanced_at=0.0, was_running=False)
    # The off-thread scored-universe store (uvalu.store, WP-5) is process-global
    # too — drop it so a stale/empty entry from another test doesn't stand in.
    from uvalu import store as _store
    _store._STORE.clear()
    yield


# ── _cache_version / _cache_age_str ───────────────────────────────────────

class TestCacheVersion:
    def test_returns_zero_when_missing(self):
        assert data_module._cache_version() == "0"

    def test_returns_coarsened_mtime_bucket_when_present(self):
        screener.SCREENER_FETCH.cache_file.parent.mkdir(parents=True, exist_ok=True)
        screener.SCREENER_FETCH.cache_file.write_text("{}", encoding="utf-8")
        mtime = screener.SCREENER_FETCH.cache_file.stat().st_mtime
        assert data_module._cache_version() == str(int(mtime // data_module._CACHE_VERSION_BUCKET_S))


class TestMtimeBucket:
    def test_zero_when_path_missing(self, tmp_path):
        assert data_module._mtime_bucket(tmp_path / "nope.json") == "0"

    def test_stable_across_writes_inside_one_bucket(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text("{}", encoding="utf-8")
        v1 = data_module._mtime_bucket(p, seconds=10_000)
        p.write_text('{"x": 1}', encoding="utf-8")   # rewritten, same wide bucket
        assert data_module._mtime_bucket(p, seconds=10_000) == v1

    def test_advances_once_the_bucket_rolls_over(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text("{}", encoding="utf-8")
        # seconds=1 → every whole-second mtime is its own bucket
        assert data_module._mtime_bucket(p, seconds=1) == str(int(p.stat().st_mtime))


class TestCacheVersionDebounce:
    """WP-1 — _cache_version() holds its token steady while a background
    screener fetch churns fundamentals.json, so the scored-universe store
    (keyed on it) doesn't re-score the whole universe on every ~20s
    cache-file rewrite for the full length of a cold fetch."""

    def _set_progress(self, monkeypatch, *, running, done):
        monkeypatch.setattr(data_module, "get_fetch_progress",
                            lambda *a, **k: {"running": running, "done": done, "total": 9999})

    def _set_bucket(self, monkeypatch, value):
        monkeypatch.setattr(data_module, "_mtime_bucket", lambda *a, **k: value)

    def test_no_fetch_running_passes_bucket_through(self, monkeypatch):
        self._set_progress(monkeypatch, running=False, done=0)
        self._set_bucket(monkeypatch, "100")
        assert data_module._cache_version() == "100"
        self._set_bucket(monkeypatch, "101")
        assert data_module._cache_version() == "101"   # advances freely when idle

    def test_running_fetch_holds_token_within_debounce_window(self, monkeypatch):
        self._set_progress(monkeypatch, running=True, done=500)   # well past the cold cutoff
        self._set_bucket(monkeypatch, "100")
        assert data_module._cache_version() == "100"              # first sighting → adopt
        self._set_bucket(monkeypatch, "101")
        assert data_module._cache_version() == "100"              # held: no re-score
        self._set_bucket(monkeypatch, "105")
        assert data_module._cache_version() == "100"              # still held

    def test_debounce_bypassed_while_cache_still_cold(self, monkeypatch):
        self._set_progress(monkeypatch, running=True, done=10)    # < _DEBOUNCE_COLD_DONE
        self._set_bucket(monkeypatch, "100")
        assert data_module._cache_version() == "100"
        self._set_bucket(monkeypatch, "101")
        assert data_module._cache_version() == "101"              # cold → fills every bucket

    def test_token_advances_once_debounce_window_elapses(self, monkeypatch):
        self._set_progress(monkeypatch, running=True, done=500)
        self._set_bucket(monkeypatch, "100")
        assert data_module._cache_version() == "100"
        # Backdate the last-advance stamp past the debounce window.
        data_module._version_state["advanced_at"] -= data_module.RECOMPUTE_DEBOUNCE_S + 1
        self._set_bucket(monkeypatch, "101")
        assert data_module._cache_version() == "101"

    def test_fetch_finishing_releases_the_held_token(self, monkeypatch):
        self._set_progress(monkeypatch, running=True, done=500)
        self._set_bucket(monkeypatch, "100")
        assert data_module._cache_version() == "100"
        self._set_bucket(monkeypatch, "110")
        assert data_module._cache_version() == "100"              # held while running
        self._set_progress(monkeypatch, running=False, done=500)
        assert data_module._cache_version() == "110"              # released once done

    def test_first_change_after_fetch_starts_is_allowed(self, monkeypatch):
        # Cache already warm and idle at bucket 100...
        self._set_progress(monkeypatch, running=False, done=800)
        self._set_bucket(monkeypatch, "100")
        assert data_module._cache_version() == "100"
        # ...a new fetch kicks off and writes once: that first roll should land
        # immediately (pre-existing stale data surfaces), then debounce.
        self._set_progress(monkeypatch, running=True, done=800)
        self._set_bucket(monkeypatch, "101")
        assert data_module._cache_version() == "101"
        self._set_bucket(monkeypatch, "102")
        assert data_module._cache_version() == "101"              # now held


class TestCacheAgeStr:
    def test_no_cache_yet_when_missing(self):
        assert data_module._cache_age_str() == "No cache yet"

    def test_no_cache_yet_when_no_timestamps(self):
        screener.SCREENER_FETCH.cache_file.parent.mkdir(parents=True, exist_ok=True)
        screener.SCREENER_FETCH.cache_file.write_text(json.dumps({"AAA.BR": {"Price": 100.0}}), encoding="utf-8")
        assert data_module._cache_age_str() == "No cache yet"

    def test_shows_minutes_for_recent_cache(self):
        from datetime import datetime, timezone
        screener.SCREENER_FETCH.cache_file.parent.mkdir(parents=True, exist_ok=True)
        screener.SCREENER_FETCH.cache_file.write_text(json.dumps({
            "AAA.BR": {"fetched_at": datetime.now(timezone.utc).isoformat()},
        }), encoding="utf-8")
        result = data_module._cache_age_str()
        assert result.startswith("Cache age: 0 min")

    def test_shows_hours_for_old_cache(self):
        from datetime import datetime, timedelta, timezone
        old = datetime.now(timezone.utc) - timedelta(hours=5)
        screener.SCREENER_FETCH.cache_file.parent.mkdir(parents=True, exist_ok=True)
        screener.SCREENER_FETCH.cache_file.write_text(json.dumps({
            "AAA.BR": {"fetched_at": old.isoformat()},
        }), encoding="utf-8")
        result = data_module._cache_age_str()
        assert " h " in result
        assert "TTL" in result


# ── _bust_cache ───────────────────────────────────────────────────────────

class TestBustCache:
    def test_wipes_cache_file_and_reruns(self, monkeypatch):
        # _bust_cache() calls st.rerun() unconditionally at the end. Calling
        # it unconditionally at a bare script's top level (like this test
        # does) means every rerun re-executes the same script and calls it
        # again forever — the same infinite-rerun trap documented for
        # settings.py's Excel import (see uvalu-test-isolation-patterns
        # memory). Stub st.rerun() to a no-op so the one-time cache wipe is
        # still observed without looping.
        import streamlit as st
        monkeypatch.setattr(st, "rerun", lambda *a, **k: None)

        screener.SCREENER_FETCH.cache_file.parent.mkdir(parents=True, exist_ok=True)
        screener.SCREENER_FETCH.cache_file.write_text('{"AAA.BR": {}}', encoding="utf-8")

        def _script():
            from uvalu.data import _bust_cache
            _bust_cache()

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert screener.SCREENER_FETCH.cache_file.read_text(encoding="utf-8") == "{}"

    def test_leaves_the_portfolio_lane_untouched(self, monkeypatch):
        import streamlit as st
        monkeypatch.setattr(st, "rerun", lambda *a, **k: None)

        screener.SCREENER_FETCH.cache_file.parent.mkdir(parents=True, exist_ok=True)
        screener.SCREENER_FETCH.cache_file.write_text('{"AAA.BR": {}}', encoding="utf-8")
        screener.PORTFOLIO_FETCH.cache_file.write_text('{"HELD.BR": {"Price": 1}}', encoding="utf-8")
        screener.PORTFOLIO_FETCH.live_cache["HELD.BR"] = {"Price": 1}

        def _script():
            from uvalu.data import _bust_cache
            _bust_cache()

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert screener.SCREENER_FETCH.cache_file.read_text(encoding="utf-8") == "{}"
        # Portfolio lane's file and in-process cache survive the screener bust.
        assert screener.PORTFOLIO_FETCH.cache_file.read_text(encoding="utf-8") == '{"HELD.BR": {"Price": 1}}'
        assert screener.PORTFOLIO_FETCH.live_cache == {"HELD.BR": {"Price": 1}}


# ── _fetch_prices_cached ──────────────────────────────────────────────────

class TestFetchPricesCached:
    def test_delegates_to_prices_fetch_prices(self, monkeypatch):
        monkeypatch.setattr(data_module, "fetch_prices", lambda tickers: {
            t: {"price": 42.0} for t in tickers
        })

        def _script():
            from uvalu.data import _fetch_prices_cached
            import streamlit as st
            result = _fetch_prices_cached(("AAA.BR",))
            st.text(result["AAA.BR"]["price"])

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "42.0"

    def test_empty_after_normalisation_skips_fetch(self, monkeypatch):
        def _boom(_tickers):
            raise AssertionError("fetch_prices should not be called for an empty set")
        monkeypatch.setattr(data_module, "fetch_prices", _boom)

        def _script():
            from uvalu.data import _fetch_prices_cached
            import streamlit as st
            st.text(_fetch_prices_cached(("", "  ", None)))

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "{}"

    def test_reordered_and_duplicated_tuples_share_one_fetch(self, monkeypatch):
        monkeypatch.setattr(data_module, "_price_bucket", lambda: 7)
        calls: list[tuple] = []
        monkeypatch.setattr(
            data_module, "fetch_prices",
            lambda tickers: calls.append(tickers) or {t: {"price": 1.0} for t in tickers},
        )

        def _script():
            from uvalu.data import _fetch_prices_cached
            import streamlit as st
            _fetch_prices_cached(("BBB.BR", "AAA.BR"))
            _fetch_prices_cached(("AAA.BR", " BBB.BR ", "AAA.BR"))  # reorder + pad + dupe
            st.text("done")

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert calls == [("AAA.BR", "BBB.BR")]   # normalised, fetched once, cache hit second time


class TestPriceBucket:
    def test_market_hours_window_is_60s(self, monkeypatch):
        monkeypatch.setattr(data_module, "is_market_hours", lambda: True)
        monkeypatch.setattr(data_module.time, "time", lambda: 1_000_000.0)
        assert data_module._price_bucket() == 1_000_000 // 60

    def test_off_hours_window_is_900s(self, monkeypatch):
        monkeypatch.setattr(data_module, "is_market_hours", lambda: False)
        monkeypatch.setattr(data_module.time, "time", lambda: 1_000_000.0)
        assert data_module._price_bucket() == 1_000_000 // 900

    def test_bucket_stable_within_window_then_advances(self, monkeypatch):
        monkeypatch.setattr(data_module, "is_market_hours", lambda: True)
        clock = {"now": 1_000_020.0}   # aligned to a 60s boundary (÷60 is exact)
        monkeypatch.setattr(data_module.time, "time", lambda: clock["now"])
        base = data_module._price_bucket()
        clock["now"] += 59
        assert data_module._price_bucket() == base
        clock["now"] += 2          # 61s past the start → next 60s bucket
        assert data_module._price_bucket() == base + 1


# ── _load_all_screener_data ────────────────────────────────────────────────

_FUND_ROW = {
    "Name": "Alpha Corp", "Ticker": "AAA.BR", "Price": 50.0,
    "trailingEps": 5.0, "bookValue": 20.0, "targetMeanPrice": 90.0,
    "beta": 1.0, "returnOnEquity": 0.20, "returnOnAssets": 0.10,
    "operatingMargins": 0.25, "freeCashflow": 1e9, "netIncome": 8e8,
    "debtToEquity": 50.0, "currentRatio": 2.0, "averageVolume": 1e6,
    "earningsGrowth": 0.08, "revenueGrowth": 0.06, "recommendationMean": 2.0,
}


class TestLoadAllScreenerData:
    def _patch_fetchers(self, monkeypatch, brussels_stocks, fund_df):
        monkeypatch.setattr(data_module, "fetch_brussels_tickers", lambda: brussels_stocks)
        monkeypatch.setattr(data_module, "fetch_amsterdam_tickers", lambda: [])
        monkeypatch.setattr(data_module, "fetch_paris_tickers", lambda: [])
        monkeypatch.setattr(data_module, "fetch_milan_tickers", lambda: [])
        monkeypatch.setattr(data_module, "fetch_frankfurt_tickers", lambda: [])
        monkeypatch.setattr(data_module, "fetch_swiss_tickers", lambda: [])
        monkeypatch.setattr(data_module, "fetch_fundamentals_nowait", lambda stocks, **kw: fund_df)

    def test_returns_all_empty_when_no_fundamentals(self, monkeypatch):
        self._patch_fetchers(monkeypatch, [{"name": "Alpha Corp", "isin": "", "ticker": "AAA.BR", "mic": "XBRU"}],
                            pd.DataFrame())

        def _script():
            from uvalu.data import _build_all_screener_data
            import streamlit as st
            result = _build_all_screener_data(("brussels",))
            st.text(len(result))
            st.text(all(d.empty for d in result))

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "7"
        assert at.text[1].value == "True"

    def test_splits_scored_data_per_exchange(self, monkeypatch):
        self._patch_fetchers(
            monkeypatch,
            [{"name": "Alpha Corp", "isin": "", "ticker": "AAA.BR", "mic": "XBRU"}],
            pd.DataFrame([_FUND_ROW]),
        )

        def _script():
            from uvalu.data import _build_all_screener_data
            import streamlit as st
            result = _build_all_screener_data(("brussels",))
            *exch_dfs, extra_df = result
            st.text(exch_dfs[0].iloc[0]["Ticker"])  # brussels (ALL_EXCHANGES[0])
            st.text(exch_dfs[1].empty)  # amsterdam untouched
            st.text(extra_df.empty)

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "AAA.BR"
        assert at.text[1].value == "True"
        assert at.text[2].value == "True"

    def test_extra_portfolio_tickers_scored_separately(self, monkeypatch):
        extra_row = dict(_FUND_ROW, Name="Beta Corp", Ticker="BBB.BR")
        self._patch_fetchers(
            monkeypatch,
            [{"name": "Alpha Corp", "isin": "", "ticker": "AAA.BR", "mic": "XBRU"}],
            pd.DataFrame([_FUND_ROW, extra_row]),
        )

        def _script():
            from uvalu.data import _build_all_screener_data
            import streamlit as st
            result = _build_all_screener_data(("brussels",), ("BBB.BR",), ("Beta Corp",))
            *exch_dfs, extra_df = result
            st.text(set(exch_dfs[0]["Ticker"]))
            st.text(extra_df.iloc[0]["Ticker"])

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "{'AAA.BR'}"
        assert at.text[1].value == "BBB.BR"

    def test_extra_ticker_already_in_an_exchange_is_not_duplicated(self, monkeypatch):
        self._patch_fetchers(
            monkeypatch,
            [{"name": "Alpha Corp", "isin": "", "ticker": "AAA.BR", "mic": "XBRU"}],
            pd.DataFrame([_FUND_ROW]),
        )

        def _script():
            from uvalu.data import _build_all_screener_data
            import streamlit as st
            # AAA.BR is already covered by the brussels exchange list, so it
            # should NOT be duplicated into the "extra" tickers/df.
            result = _build_all_screener_data(("brussels",), ("AAA.BR",), ("Alpha Corp",))
            *_, extra_df = result
            st.text(extra_df.empty)

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "True"


# ── screener_refresh_signature / _price_refresh_signature (WP-6) ──────────

class TestRefreshSignatures:
    def test_screener_signature_tracks_store_version_and_fetch_progress(self, monkeypatch):
        monkeypatch.setattr("uvalu.store.universe_version", lambda: 7)
        monkeypatch.setattr(data_module, "get_fetch_progress",
                            lambda *a, **k: {"running": True, "done": 63, "total": 999})
        assert data_module.screener_refresh_signature() == (7, True, 63 // 25)

    def test_screener_signature_done_is_bucketed(self, monkeypatch):
        monkeypatch.setattr("uvalu.store.universe_version", lambda: 0)
        monkeypatch.setattr(data_module, "get_fetch_progress",
                            lambda *a, **k: {"running": True, "done": 24, "total": 999})
        a = data_module.screener_refresh_signature()
        monkeypatch.setattr(data_module, "get_fetch_progress",
                            lambda *a, **k: {"running": True, "done": 25, "total": 999})
        b = data_module.screener_refresh_signature()
        assert a == (0, True, 0) and b == (0, True, 1)   # crosses a 25-ticker bucket

    def test_price_signature_tracks_bucket_and_portfolio_lane(self, monkeypatch):
        monkeypatch.setattr(data_module, "_price_bucket", lambda: 111)
        monkeypatch.setattr(data_module, "_portfolio_cache_version", lambda: "tok")
        monkeypatch.setattr(data_module, "get_fetch_progress",
                            lambda *a, **k: {"running": False, "done": 5, "total": 0})
        assert data_module._price_refresh_signature() == (111, "tok", False, 5 // 10)


# ── _portfolio_cache_version ──────────────────────────────────────────────

class TestPortfolioCacheVersion:
    def test_zero_when_missing(self):
        assert data_module._portfolio_cache_version() == "0"

    def test_coarsened_mtime_bucket_when_present(self):
        f = screener.PORTFOLIO_FETCH.cache_file
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}", encoding="utf-8")
        assert data_module._portfolio_cache_version() == str(
            int(f.stat().st_mtime // data_module._CACHE_VERSION_BUCKET_S))


# ── _load_portfolio_screener_data ────────────────────────────────────────

class TestLoadPortfolioScreenerData:
    def test_empty_when_no_tickers(self):
        def _script():
            from uvalu.data import _load_portfolio_screener_data
            import streamlit as st
            st.text(_load_portfolio_screener_data("v", (), ()).empty)

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "True"

    def test_fetches_via_portfolio_lane_with_priority_and_scores(self, monkeypatch):
        captured: dict = {}

        def _fake_nowait(stocks, fetcher=None, priority=()):
            captured["fetcher"] = fetcher
            captured["priority"] = [s["ticker"] for s in priority]
            return pd.DataFrame([_FUND_ROW])

        monkeypatch.setattr(data_module, "fetch_fundamentals_nowait", _fake_nowait)

        def _script():
            from uvalu.data import _load_portfolio_screener_data
            import streamlit as st
            df = _load_portfolio_screener_data("v", ("AAA.BR",), ("Alpha Corp",))
            st.text(df.iloc[0]["Ticker"])

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "AAA.BR"
        assert captured["fetcher"] is screener.PORTFOLIO_FETCH
        assert captured["priority"] == ["AAA.BR"]


# ── prefetch_portfolio_data ──────────────────────────────────────────────

class TestPrefetchPortfolioData:
    def test_noop_when_no_portfolio(self, isolated_data, monkeypatch):
        called: list = []
        monkeypatch.setattr(data_module, "fetch_fundamentals_nowait",
                            lambda *a, **k: called.append(1))
        data_module.prefetch_portfolio_data()
        assert called == []

    def test_swallows_errors(self, isolated_data, monkeypatch):
        import portfolio
        portfolio.save_portfolio(make_portfolio_df())

        def _boom(*a, **k):
            raise RuntimeError("cold yahoo")

        monkeypatch.setattr(data_module, "fetch_fundamentals_nowait", _boom)
        data_module.prefetch_portfolio_data()   # must not raise

    def test_warms_portfolio_lane_and_price_cache(self, isolated_data, monkeypatch):
        import portfolio
        portfolio.save_portfolio(make_portfolio_df())
        seen: dict = {}
        monkeypatch.setattr(
            data_module, "fetch_fundamentals_nowait",
            lambda stocks, fetcher=None, priority=(): seen.update(
                fetcher=fetcher, tickers=[s["ticker"] for s in stocks]))
        monkeypatch.setattr(data_module, "_fetch_prices_cached",
                            lambda tickers: seen.update(price_tickers=tuple(tickers)))
        data_module.prefetch_portfolio_data()
        assert seen["fetcher"] is screener.PORTFOLIO_FETCH
        assert "AAA.BR" in seen["tickers"]
        assert "AAA.BR" in seen["price_tickers"]


class TestApplyLiveMos:
    """WP-DQ1: refresh Price / live_price / MoS % on a scored portfolio frame
    from the live quote so the Holdings ladder's three numbers reconcile,
    without touching fair_value / Value Score / Decision."""

    def _frame(self, **over):
        row = {"Ticker": "AAA.BR", "Price": 100.0, "fair_value": 120.0,
               "MoS %": 16.7, "margin_of_safety": 0.1667, "Value Score": 70.0,
               "Decision": "Monitor"}
        row.update(over)
        return pd.DataFrame([row])

    def test_recomputes_mos_from_live_price_and_batch_fair_value(self):
        out = data_module.apply_live_mos(self._frame(), {"AAA.BR": {"price": 108.0}})
        r = out.iloc[0]
        assert r["Price"] == 108.0 and r["live_price"] == 108.0
        # (120 - 108) / 120 = 0.10
        assert r["margin_of_safety"] == pytest.approx(0.10)
        assert r["MoS %"] == pytest.approx(10.0)
        assert not r["price_stale"]
        # untouched
        assert r["fair_value"] == 120.0 and r["Value Score"] == 70.0 and r["Decision"] == "Monitor"

    def test_flags_price_stale_when_live_quote_far_from_batch(self):
        # batch 100, live 140 -> 40% gap -> the cached fundamentals row is old
        out = data_module.apply_live_mos(self._frame(), {"AAA.BR": {"price": 140.0}})
        r = out.iloc[0]
        assert r["price_stale"]
        assert r["MoS %"] == pytest.approx((120.0 - 140.0) / 120.0 * 100, abs=0.05)

    def test_missing_live_quote_keeps_batch_price_and_flags_stale(self):
        out = data_module.apply_live_mos(self._frame(), {})
        r = out.iloc[0]
        assert r["Price"] == 100.0 and pd.isna(r["live_price"]) and r["price_stale"]
        # (120 - 100) / 120 = 0.16667 -> 16.7 at 1dp
        assert r["MoS %"] == pytest.approx(16.7)

    def test_no_fair_value_column_sets_price_without_crashing(self):
        f = self._frame().drop(columns=["fair_value", "MoS %", "margin_of_safety"])
        out = data_module.apply_live_mos(f, {"AAA.BR": {"price": 108.0}})
        assert out.iloc[0]["Price"] == 108.0 and "MoS %" not in out.columns

    def test_none_or_empty_frame_passes_through(self):
        assert data_module.apply_live_mos(None, {}) is None
        empty = pd.DataFrame(columns=["Ticker"])
        assert data_module.apply_live_mos(empty, {}).empty
