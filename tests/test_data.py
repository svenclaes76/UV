"""Tests for uvalu/data.py — the screener/price cache-backed data layer
between yfinance/fetch_tickers/screener and the UI pages.

data.py imports CACHE_FILE (a plain Path constant) from screener.py BY
VALUE — same gotcha as backup.py/settings.py's _SHARED_FILE (see
uvalu-test-isolation-patterns memory) — so isolating it requires patching
BOTH screener.CACHE_FILE (read by _load_cache(), a function that resolves
its own module's globals at call time) AND data.CACHE_FILE (data.py's own
separate copy, used directly in _cache_version()/_bust_cache()).

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


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "fundamentals.json"
    monkeypatch.setattr(screener, "CACHE_FILE", cache_file)
    monkeypatch.setattr(data_module, "CACHE_FILE", cache_file)
    monkeypatch.setattr(screener, "_live_cache", {})
    # _load_all_screener_data/_fetch_prices_cached are @st.cache_data-wrapped
    # and process-global — without clearing, a later test calling one with
    # the SAME args (e.g. the same literal cache_version string) as an
    # earlier test would silently get that earlier test's cached return
    # value instead of actually re-executing.
    import streamlit as st
    st.cache_data.clear()
    yield


# ── _cache_version / _cache_age_str ───────────────────────────────────────

class TestCacheVersion:
    def test_returns_zero_when_missing(self):
        assert data_module._cache_version() == "0"

    def test_returns_mtime_string_when_present(self):
        data_module.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data_module.CACHE_FILE.write_text("{}", encoding="utf-8")
        version = data_module._cache_version()
        assert version == str(int(data_module.CACHE_FILE.stat().st_mtime))


class TestCacheAgeStr:
    def test_no_cache_yet_when_missing(self):
        assert data_module._cache_age_str() == "No cache yet"

    def test_no_cache_yet_when_no_timestamps(self):
        screener.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        screener.CACHE_FILE.write_text(json.dumps({"AAA.BR": {"Price": 100.0}}), encoding="utf-8")
        assert data_module._cache_age_str() == "No cache yet"

    def test_shows_minutes_for_recent_cache(self):
        from datetime import datetime, timezone
        screener.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        screener.CACHE_FILE.write_text(json.dumps({
            "AAA.BR": {"fetched_at": datetime.now(timezone.utc).isoformat()},
        }), encoding="utf-8")
        result = data_module._cache_age_str()
        assert result.startswith("Cache age: 0 min")

    def test_shows_hours_for_old_cache(self):
        from datetime import datetime, timedelta, timezone
        old = datetime.now(timezone.utc) - timedelta(hours=5)
        screener.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        screener.CACHE_FILE.write_text(json.dumps({
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

        data_module.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data_module.CACHE_FILE.write_text('{"AAA.BR": {}}', encoding="utf-8")

        def _script():
            from uvalu.data import _bust_cache
            _bust_cache()

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert data_module.CACHE_FILE.read_text(encoding="utf-8") == "{}"


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
        monkeypatch.setattr(data_module, "fetch_fundamentals_nowait", lambda stocks: fund_df)

    def test_returns_all_empty_when_no_fundamentals(self, monkeypatch):
        self._patch_fetchers(monkeypatch, [{"name": "Alpha Corp", "isin": "", "ticker": "AAA.BR", "mic": "XBRU"}],
                            pd.DataFrame())

        def _script():
            from uvalu.data import _load_all_screener_data
            import streamlit as st
            result = _load_all_screener_data("v1", ("brussels",))
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
            from uvalu.data import _load_all_screener_data
            import streamlit as st
            result = _load_all_screener_data("v1", ("brussels",))
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
            from uvalu.data import _load_all_screener_data
            import streamlit as st
            result = _load_all_screener_data("v1", ("brussels",), ("BBB.BR",), ("Beta Corp",))
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
            from uvalu.data import _load_all_screener_data
            import streamlit as st
            # AAA.BR is already covered by the brussels exchange list, so it
            # should NOT be duplicated into the "extra" tickers/df.
            result = _load_all_screener_data("v1", ("brussels",), ("AAA.BR",), ("Alpha Corp",))
            *_, extra_df = result
            st.text(extra_df.empty)

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "True"
