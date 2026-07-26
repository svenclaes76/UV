"""Tests for uvalu/data.py — the screener/price/fundamentals cache-backed
data layer between yfinance/fetch_tickers/screener and the UI pages.

data.py imports CACHE_FILE (a plain Path constant) from screener.py BY
VALUE — same gotcha as backup.py/settings.py's _SHARED_FILE (see
uvalu-test-isolation-patterns memory) — so isolating it requires patching
BOTH screener.CACHE_FILE (read by _load_cache(), a function that resolves
its own module's globals at call time) AND data.CACHE_FILE (data.py's own
separate copy, used directly in _cache_version()/_bust_cache()).
"""
import json

import pandas as pd
import pytest
import yfinance as yf
from streamlit.testing.v1 import AppTest

import screener
from uvalu import data as data_module


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "fundamentals.json"
    monkeypatch.setattr(screener, "CACHE_FILE", cache_file)
    monkeypatch.setattr(data_module, "CACHE_FILE", cache_file)
    monkeypatch.setattr(screener, "_live_cache", {})
    # _load_all_screener_data/_fetch_prices_cached/_fetch_fundamentals are all
    # @st.cache_data-wrapped and process-global — without clearing, a later
    # test calling one with the SAME args (e.g. the same literal
    # cache_version string) as an earlier test would silently get that
    # earlier test's cached return value instead of actually re-executing.
    import streamlit as st
    st.cache_data.clear()
    yield


# ── _compute_fair_values ──────────────────────────────────────────────────

class TestComputeFairValues:
    def test_all_models_available(self):
        info = {
            "trailingEps": 5.0, "bookValue": 20.0,
            "earningsGrowth": 0.08, "targetMeanPrice": 90.0,
        }
        result = data_module._compute_fair_values(info)
        assert result["graham_number"] == round((22.5 * 5.0 * 20.0) ** 0.5, 2)
        assert result["pe_fair_value"] == 75.0
        assert result["graham_growth"] is not None
        assert result["fair_value"] is not None

    def test_no_eps_or_bvps_gives_no_graham(self):
        result = data_module._compute_fair_values({"trailingEps": None, "bookValue": None})
        assert result["graham_number"] is None
        assert result["pe_fair_value"] is None
        assert result["fair_value"] is None

    def test_negative_eps_gives_no_models(self):
        result = data_module._compute_fair_values({"trailingEps": -2.0, "bookValue": 20.0})
        assert result["graham_number"] is None
        assert result["pe_fair_value"] is None

    def test_growth_clamped_and_uses_revenue_growth_fallback(self):
        result = data_module._compute_fair_values({
            "trailingEps": 5.0, "bookValue": 20.0, "revenueGrowth": 0.5,  # clamps to 25%
        })
        assert result["graham_growth"] == round(5.0 * (8.5 + 2 * 25.0), 2)

    def test_negative_graham_growth_becomes_none(self):
        result = data_module._compute_fair_values({
            "trailingEps": 1.0, "bookValue": 5.0, "earningsGrowth": -0.20,  # clamps to -5%
        })
        # 1.0 * (8.5 + 2*-5) = -1.5 -> negative -> None
        assert result["graham_growth"] is None

    def test_composite_averages_only_available_positive_estimates(self):
        result = data_module._compute_fair_values({"trailingEps": 5.0, "bookValue": 20.0})
        gn = round((22.5 * 5.0 * 20.0) ** 0.5, 2)
        pe = 75.0
        assert result["fair_value"] == round((gn + pe) / 2, 2)


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


# ── _fetch_fundamentals ────────────────────────────────────────────────────

class TestFetchFundamentals:
    def test_extracts_expected_fields(self, monkeypatch):
        class FakeTicker:
            def __init__(self, t):
                self.info = {
                    "targetMeanPrice": 90.0, "trailingAnnualDividendRate": 2.5,
                    "sector": "Technology", "country": "Belgium",
                    "trailingEps": 5.0, "bookValue": 20.0,
                }
        monkeypatch.setattr(yf, "Ticker", FakeTicker)

        def _script():
            from uvalu.data import _fetch_fundamentals
            import streamlit as st
            result = _fetch_fundamentals(("AAA.BR",))
            st.json(result)

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        result = json.loads(at.json[0].value)
        assert result["AAA.BR"]["analyst_target"] == 90.0
        assert result["AAA.BR"]["div_rate"] == 2.5
        assert result["AAA.BR"]["sector"] == "Technology"
        assert result["AAA.BR"]["fair_value"] is not None

    def test_invalid_ticker_type_gets_default(self, monkeypatch):
        def _script():
            from uvalu.data import _fetch_fundamentals
            import streamlit as st
            result = _fetch_fundamentals((None,))
            st.json(result)

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        result = json.loads(at.json[0].value)
        # json.dumps spells a None dict key as the JSON string "null".
        assert result["null"]["analyst_target"] is None

    def test_exception_per_ticker_gets_default(self, monkeypatch):
        def boom(t):
            raise RuntimeError("no such ticker")
        monkeypatch.setattr(yf, "Ticker", boom)

        def _script():
            from uvalu.data import _fetch_fundamentals
            import streamlit as st
            result = _fetch_fundamentals(("BAD.BR",))
            st.json(result)

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        result = json.loads(at.json[0].value)
        assert result["BAD.BR"]["analyst_target"] is None
        assert result["BAD.BR"]["div_rate"] == 0


# ── _fetch_live_data ────────────────────────────────────────────────────────

class TestFetchLiveData:
    def test_merges_prices_and_fundamentals(self, monkeypatch):
        monkeypatch.setattr(data_module, "_fetch_prices_cached",
                            lambda tickers: {"AAA.BR": {"price": 100.0}})
        monkeypatch.setattr(data_module, "_fetch_fundamentals",
                            lambda tickers: {"AAA.BR": {"sector": "Technology", "fair_value": 120.0}})

        def _script():
            from uvalu.data import _fetch_live_data
            import streamlit as st
            result = _fetch_live_data(("AAA.BR",))
            st.json(result)

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        result = json.loads(at.json[0].value)
        assert result["AAA.BR"]["price"] == 100.0
        assert result["AAA.BR"]["sector"] == "Technology"
        assert result["AAA.BR"]["fair_value"] == 120.0


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
