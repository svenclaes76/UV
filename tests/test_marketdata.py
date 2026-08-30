"""
Unit tests for marketdata.py — the per-ticker, disk-cached price-history
provider that risk._fetch_history delegates to.

No real network calls: most tests stub marketdata._download_closes directly;
the MultiIndex-unwrap test stubs yf.download one level lower.
"""
import datetime as _dt

import pandas as pd
import pytest
import yfinance as yf

import marketdata


@pytest.fixture(autouse=True)
def _tmp_history_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(marketdata, "_HISTORY_DIR", tmp_path / "history")
    yield


def _series(start: str, n: int, base: float = 100.0) -> pd.Series:
    idx = pd.bdate_range(start, periods=n)
    return pd.Series([base + i for i in range(n)], index=idx, dtype=float)


def _series_through_today(n: int = 300, base: float = 100.0) -> pd.Series:
    idx = pd.bdate_range(end=pd.Timestamp(_dt.date.today()), periods=n)
    return pd.Series([base + i for i in range(n)], index=idx, dtype=float)


def _fake_download(frames: dict[str, pd.Series]):
    """Return a stand-in for marketdata._download_closes that yields `frames`
    (ticker -> close Series) for whatever tickers it's asked about, and records
    every call's kwargs on `.calls`."""
    def _fn(tickers, start=None, period="5y"):
        _fn.calls.append({"tickers": list(tickers), "start": start, "period": period})
        cols = {t: frames[t] for t in tickers if t in frames}
        return pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()
    _fn.calls = []
    return _fn


def _boom(*_a, **_k):
    raise AssertionError("marketdata._download_closes should not have been called")


# ── Calendar helpers ─────────────────────────────────────────────────────────

class TestCalendarHelpers:
    def test_period_start_uses_calendar_span(self):
        today = _dt.date(2026, 8, 30)
        assert marketdata._period_start("5y", today) == today - _dt.timedelta(days=1827)
        assert marketdata._period_start("1y", today) == today - _dt.timedelta(days=366)

    def test_period_start_unknown_period_falls_back_to_5y(self):
        today = _dt.date(2026, 8, 30)
        assert marketdata._period_start("bogus", today) == marketdata._period_start("5y", today)

    def test_prev_business_day_skips_weekend(self):
        # 2026-08-31 is a Monday → previous business day is Friday the 28th.
        assert marketdata._prev_business_day(_dt.date(2026, 8, 31)) == _dt.date(2026, 8, 28)
        # Tuesday → Monday
        assert marketdata._prev_business_day(_dt.date(2026, 9, 1)) == _dt.date(2026, 8, 31)


# ── price_history ───────────────────────────────────────────────────────────

class TestPriceHistory:
    def test_empty_input_makes_no_call(self, monkeypatch):
        monkeypatch.setattr(marketdata, "_download_closes", _boom)
        assert marketdata.price_history([]).empty

    def test_cold_fetch_writes_csv_and_returns_frame(self, monkeypatch):
        col = _series("2024-01-01", 400)
        dl = _fake_download({"AAA.BR": col})
        monkeypatch.setattr(marketdata, "_download_closes", dl)

        out = marketdata.price_history(["AAA.BR"])

        assert list(out.columns) == ["AAA.BR"]
        assert len(out) == 400
        assert marketdata._cache_path("AAA.BR").exists()
        assert len(dl.calls) == 1 and dl.calls[0]["start"] is None

        # Round-trips through the CSV cache.
        reread = marketdata._read_cache("AAA.BR")
        assert reread.iloc[-1] == col.iloc[-1]

    def test_second_call_same_day_makes_no_network_call(self, monkeypatch):
        col = _series_through_today(300)
        monkeypatch.setattr(marketdata, "_download_closes", _fake_download({"AAA.BR": col}))
        marketdata.price_history(["AAA.BR"])

        # Cache now reaches today → treated as complete, no fetch on the next call.
        monkeypatch.setattr(marketdata, "_download_closes", _boom)
        out = marketdata.price_history(["AAA.BR"])
        assert len(out) == 300

    def test_stale_cache_refetches_only_the_tail(self, monkeypatch):
        old = _series("2024-01-01", 200)                       # ends well in the past
        marketdata._write_cache("AAA.BR", old)

        tail_start = old.index.max().date() + _dt.timedelta(days=1)
        tail = pd.Series(
            [999.0, 1000.0, 1001.0],
            index=pd.bdate_range(tail_start, periods=3), dtype=float,
        )
        dl = _fake_download({"AAA.BR": tail})
        monkeypatch.setattr(marketdata, "_download_closes", dl)

        out = marketdata.price_history(["AAA.BR"])

        assert len(dl.calls) == 1
        assert dl.calls[0]["start"] == tail_start            # only the gap was requested
        assert out["AAA.BR"].iloc[-1] == 1001.0              # tail merged in
        assert len(out) == 203                               # old 200 + 3 new, deduped

    def test_fetch_failure_serves_existing_cache(self, monkeypatch):
        old = _series("2024-01-01", 150)
        marketdata._write_cache("AAA.BR", old)
        monkeypatch.setattr(marketdata, "_download_closes",
                            lambda *a, **k: pd.DataFrame())   # total failure

        out = marketdata.price_history(["AAA.BR"])
        assert len(out) == 150
        assert out["AAA.BR"].iloc[-1] == old.iloc[-1]

    def test_unknown_ticker_absent_from_frame(self, monkeypatch):
        monkeypatch.setattr(marketdata, "_download_closes",
                            _fake_download({"AAA.BR": _series("2024-01-01", 100)}))
        out = marketdata.price_history(["AAA.BR", "NOPE.BR"])
        assert list(out.columns) == ["AAA.BR"]
        assert not marketdata._cache_path("NOPE.BR").exists()

    def test_mixed_cold_and_warm_tickers(self, monkeypatch):
        warm = _series("2024-01-01", 120)
        marketdata._write_cache("WARM.BR", warm)              # stale on disk
        tail_start = warm.index.max().date() + _dt.timedelta(days=1)

        frames = {
            "COLD.BR": _series("2024-06-03", 60, base=20.0),
            "WARM.BR": pd.Series([1.0, 2.0],
                                 index=pd.bdate_range(tail_start, periods=2), dtype=float),
        }
        dl = _fake_download(frames)
        monkeypatch.setattr(marketdata, "_download_closes", dl)

        out = marketdata.price_history(["COLD.BR", "WARM.BR"])

        assert set(out.columns) == {"COLD.BR", "WARM.BR"}
        # one batch call for cold (start=None), one for the stale tail (start set)
        starts = sorted(c["start"] is None for c in dl.calls)
        assert starts == [False, True]
        assert marketdata._cache_path("COLD.BR").exists()

    def test_period_slice_trims_rows_older_than_window(self, monkeypatch):
        idx = pd.DatetimeIndex(
            [pd.Timestamp("2018-01-02"), pd.Timestamp("2019-01-02")]
        ).append(pd.bdate_range("2024-01-01", periods=50))
        col = pd.Series(range(len(idx)), index=idx, dtype=float)
        marketdata._write_cache("AAA.BR", col)
        monkeypatch.setattr(marketdata, "_download_closes", lambda *a, **k: pd.DataFrame())

        out = marketdata.price_history(["AAA.BR"], period="5y")
        assert out.index.min() >= pd.Timestamp(marketdata._period_start("5y"))
        assert pd.Timestamp("2018-01-02") not in out.index


# ── _download_closes ────────────────────────────────────────────────────────

def _multiindex_download(close: dict, dates) -> pd.DataFrame:
    """A yf.download()-shaped MultiIndex (Field, Ticker) frame."""
    close_df = pd.DataFrame(close, index=dates)
    return pd.concat({"Close": close_df, "Volume": close_df}, axis=1)


class TestDownloadCloses:
    def test_unwraps_multiindex_close(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=3)
        raw = _multiindex_download({"AAA.BR": [10.0, 11.0, 12.0],
                                    "BBB.BR": [50.0, 49.0, 48.0]}, dates)
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw)

        out = marketdata._download_closes(["AAA.BR", "BBB.BR"], start=None, period="5y")
        assert list(out.columns) == ["AAA.BR", "BBB.BR"]
        assert out["AAA.BR"].tolist() == [10.0, 11.0, 12.0]

    def test_empty_response_returns_empty_frame(self, monkeypatch):
        monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame())
        assert marketdata._download_closes(["AAA.BR"], start=None, period="5y").empty

    def test_non_transient_error_returns_empty_frame(self, monkeypatch):
        def boom(*a, **k):
            raise ValueError("malformed symbol")
        monkeypatch.setattr(yf, "download", boom)
        assert marketdata._download_closes(["AAA.BR"], start=None, period="5y").empty

    def test_tz_aware_index_is_localised_away(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=2, tz="America/New_York")
        raw = _multiindex_download({"AAA.BR": [1.0, 2.0]}, dates)
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw)

        out = marketdata._download_closes(["AAA.BR"], start=None, period="5y")
        assert out.index.tz is None
