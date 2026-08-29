"""
Unit tests for prices.py — batch price fetching via yfinance, with a
per-ticker fast_info fallback when the batch download fails.

All yfinance network calls are mocked via monkeypatch — no real HTTP calls.
"""

import pandas as pd
import pytest
import yfinance as yf

import prices


@pytest.fixture(autouse=True)
def _clear_last_good():
    """prices._last_good is a process-global stale-price cache; clear it around
    every test so one test's successful fetch can't leak into another's."""
    prices._last_good.clear()
    yield
    prices._last_good.clear()


def _download_router(*, daily, intraday=None):
    """Fake yf.download that serves `daily` for the interval='1d' call and
    `intraday` for the interval='1m' call. Either arg may be a BaseException
    instance (raised) or None (→ empty DataFrame)."""
    def _fn(*_a, **k):
        payload = intraday if k.get("interval") == "1m" else daily
        if isinstance(payload, BaseException):
            raise payload
        return payload if payload is not None else pd.DataFrame()
    return _fn


class TestDayChange:
    def test_computes_percentage_change(self):
        assert prices._day_change(110.0, 100.0) == 10.0

    def test_negative_change(self):
        assert prices._day_change(90.0, 100.0) == -10.0

    def test_none_when_price_falsy(self):
        assert prices._day_change(None, 100.0) is None
        assert prices._day_change(0, 100.0) is None

    def test_none_when_prev_close_falsy(self):
        assert prices._day_change(100.0, None) is None
        assert prices._day_change(100.0, 0) is None


class TestFetchPricesEmptyInput:
    def test_returns_empty_dict_without_calling_download(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("yf.download should not be called for empty tickers")
        monkeypatch.setattr(yf, "download", boom)
        assert prices.fetch_prices(()) == {}


def _multiindex_download(close: dict, volume: dict, dates) -> pd.DataFrame:
    """Build a fake yf.download()-shaped MultiIndex DataFrame."""
    close_df = pd.DataFrame(close, index=dates)
    volume_df = pd.DataFrame(volume, index=dates)
    return pd.concat({"Close": close_df, "Volume": volume_df}, axis=1)


class TestFetchPricesBatchPath:
    def test_happy_path_two_tickers(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=3)
        raw = _multiindex_download(
            close={"AAA.BR": [10.0, 11.0, 12.0], "BBB.BR": [50.0, 49.0, 48.0]},
            volume={"AAA.BR": [1000, 1100, 1200], "BBB.BR": [500, 400, 300]},
            dates=dates,
        )
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw)

        result = prices.fetch_prices(("AAA.BR", "BBB.BR"))

        assert result["AAA.BR"]["price"] == 12.0
        assert result["AAA.BR"]["prev_close"] == 11.0
        assert result["AAA.BR"]["day_change_pct"] == pytest.approx(9.09, abs=0.01)
        assert result["AAA.BR"]["volume"] == 1200

        assert result["BBB.BR"]["price"] == 48.0
        assert result["BBB.BR"]["prev_close"] == 49.0
        assert result["BBB.BR"]["volume"] == 300

    def test_single_data_point_has_no_prev_close(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=1)
        raw = _multiindex_download(
            close={"AAA.BR": [10.0]}, volume={"AAA.BR": [1000]}, dates=dates,
        )
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw)

        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"]["price"] == 10.0
        assert result["AAA.BR"]["prev_close"] is None
        assert result["AAA.BR"]["day_change_pct"] is None

    def test_ticker_missing_from_response_stays_empty(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=2)
        raw = _multiindex_download(
            close={"AAA.BR": [10.0, 11.0]}, volume={"AAA.BR": [1000, 1100]}, dates=dates,
        )
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw)

        result = prices.fetch_prices(("AAA.BR", "ZZZ.BR"))
        assert result["AAA.BR"]["price"] == 11.0
        assert result["ZZZ.BR"] == dict(prices._EMPTY)

    def test_all_nan_closes_for_ticker_stays_empty(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=2)
        raw = _multiindex_download(
            close={"AAA.BR": [float("nan"), float("nan")]},
            volume={"AAA.BR": [float("nan"), float("nan")]},
            dates=dates,
        )
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw)

        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"] == dict(prices._EMPTY)


class TestFetchPricesFallbackPath:
    def test_falls_back_when_download_returns_empty(self, monkeypatch):
        monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame())

        class FakeTicker:
            def __init__(self, ticker):
                self.fast_info = {
                    "last_price": 42.0,
                    "previous_close": 40.0,
                    "three_month_average_volume": 999,
                }

        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"]["price"] == 42.0
        assert result["AAA.BR"]["prev_close"] == 40.0
        assert result["AAA.BR"]["volume"] == 999

    def test_falls_back_when_download_raises(self, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("network down")
        monkeypatch.setattr(yf, "download", boom)

        class FakeTicker:
            def __init__(self, ticker):
                self.fast_info = {"last_price": 5.0, "previous_close": 4.0}

        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"]["price"] == 5.0

    def test_fallback_uses_regular_market_price_when_last_price_missing(self, monkeypatch):
        monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame())

        class FakeTicker:
            def __init__(self, ticker):
                self.fast_info = {
                    "regular_market_price": 7.0,
                    "regular_market_previous_close": 6.0,
                }

        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"]["price"] == 7.0
        assert result["AAA.BR"]["prev_close"] == 6.0

    def test_fallback_handles_per_ticker_exception(self, monkeypatch):
        monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame())

        class FakeTicker:
            def __init__(self, ticker):
                if ticker == "BAD.BR":
                    raise RuntimeError("boom")
                self.fast_info = {"last_price": 1.0, "previous_close": 1.0}

        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        result = prices.fetch_prices(("AAA.BR", "BAD.BR"))
        assert result["AAA.BR"]["price"] == 1.0
        assert result["BAD.BR"] == dict(prices._EMPTY)


class TestFetchPricesIntradayOverlay:
    def test_intraday_last_replaces_daily_close(self, monkeypatch):
        daily = _multiindex_download(
            close={"AAA.BR": [10.0, 11.0, 12.0]},
            volume={"AAA.BR": [100, 110, 120]},
            dates=pd.date_range("2024-01-01", periods=3),
        )
        intraday = _multiindex_download(
            close={"AAA.BR": [12.5, 13.0, 13.4]},
            volume={"AAA.BR": [5, 6, 7]},
            dates=pd.date_range("2024-01-03 09:00", periods=3, freq="1min"),
        )
        monkeypatch.setattr(yf, "download", _download_router(daily=daily, intraday=intraday))

        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"]["price"] == 13.4          # 1m last, not daily 12.0
        assert result["AAA.BR"]["prev_close"] == 11.0     # still daily second-to-last
        assert result["AAA.BR"]["day_change_pct"] == pytest.approx(
            (13.4 - 11.0) / 11.0 * 100, abs=0.01)         # recomputed against 1m price
        assert result["AAA.BR"]["volume"] == 120          # untouched — daily volume
        assert result["AAA.BR"]["stale"] is False
        assert result["AAA.BR"]["as_of"] is not None

    def test_daily_close_kept_when_intraday_call_raises(self, monkeypatch):
        daily = _multiindex_download(
            close={"AAA.BR": [98.0, 100.0]}, volume={"AAA.BR": [100, 110]},
            dates=pd.date_range("2024-01-01", periods=2),
        )
        monkeypatch.setattr(yf, "download",
                            _download_router(daily=daily, intraday=ConnectionError("1m down")))
        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"]["price"] == 100.0
        assert result["AAA.BR"]["day_change_pct"] == pytest.approx(2.04, abs=0.01)

    def test_daily_close_kept_when_intraday_frame_empty(self, monkeypatch):
        daily = _multiindex_download(
            close={"AAA.BR": [98.0, 100.0]}, volume={"AAA.BR": [100, 110]},
            dates=pd.date_range("2024-01-01", periods=2),
        )
        monkeypatch.setattr(yf, "download",
                            _download_router(daily=daily, intraday=pd.DataFrame()))
        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"]["price"] == 100.0

    def test_intraday_only_ticker_still_recorded(self, monkeypatch):
        daily = _multiindex_download(
            close={"AAA.BR": [10.0, 11.0]}, volume={"AAA.BR": [1, 2]},
            dates=pd.date_range("2024-01-01", periods=2),
        )
        intraday = _multiindex_download(
            close={"BBB.BR": [50.0, 51.0]}, volume={"BBB.BR": [1, 2]},
            dates=pd.date_range("2024-01-02 09:00", periods=2, freq="1min"),
        )
        monkeypatch.setattr(yf, "download", _download_router(daily=daily, intraday=intraday))

        result = prices.fetch_prices(("AAA.BR", "BBB.BR"))
        assert result["AAA.BR"]["price"] == 11.0
        assert result["BBB.BR"]["price"] == 51.0          # purely from the 1m frame
        assert result["BBB.BR"]["prev_close"] is None     # no daily bar for it
        assert result["BBB.BR"]["stale"] is False


class TestFetchPricesStaleFallback:
    def test_serves_last_good_when_later_fetch_returns_nothing(self, monkeypatch):
        good = _multiindex_download(
            close={"AAA.BR": [48.0, 50.0]}, volume={"AAA.BR": [10, 11]},
            dates=pd.date_range("2024-01-01", periods=2),
        )
        monkeypatch.setattr(yf, "download", _download_router(daily=good, intraday=pd.DataFrame()))
        first = prices.fetch_prices(("AAA.BR",))
        assert first["AAA.BR"]["price"] == 50.0
        assert first["AAA.BR"]["stale"] is False

        # Second round: daily download empty AND fast_info raises → nothing new.
        monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame())

        class _BoomTicker:
            def __init__(self, ticker):
                raise RuntimeError("boom")

        monkeypatch.setattr(yf, "Ticker", _BoomTicker)
        second = prices.fetch_prices(("AAA.BR",))
        assert second["AAA.BR"]["price"] == 50.0
        assert second["AAA.BR"]["stale"] is True
        assert second["AAA.BR"]["as_of"] == first["AAA.BR"]["as_of"]

    def test_no_last_good_leaves_empty_result(self, monkeypatch):
        monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame())

        class _BoomTicker:
            def __init__(self, ticker):
                raise RuntimeError("boom")

        monkeypatch.setattr(yf, "Ticker", _BoomTicker)
        result = prices.fetch_prices(("NEW.BR",))
        assert result["NEW.BR"] == dict(prices._EMPTY)

    def test_successful_fetch_refreshes_last_good(self, monkeypatch):
        d1 = _multiindex_download(
            close={"AAA.BR": [10.0, 20.0]}, volume={"AAA.BR": [1, 2]},
            dates=pd.date_range("2024-01-01", periods=2),
        )
        monkeypatch.setattr(yf, "download", _download_router(daily=d1, intraday=pd.DataFrame()))
        prices.fetch_prices(("AAA.BR",))

        d2 = _multiindex_download(
            close={"AAA.BR": [20.0, 30.0]}, volume={"AAA.BR": [1, 2]},
            dates=pd.date_range("2024-01-02", periods=2),
        )
        monkeypatch.setattr(yf, "download", _download_router(daily=d2, intraday=pd.DataFrame()))
        result = prices.fetch_prices(("AAA.BR",))
        assert result["AAA.BR"]["price"] == 30.0
        assert result["AAA.BR"]["stale"] is False
        assert prices._last_good["AAA.BR"]["price"] == 30.0
