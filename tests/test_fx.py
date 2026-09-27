"""Unit tests for fx.py — the frankfurter.dev client (the app's single FX
source). conftest's autouse ``_fx_isolated`` already points the cache at
tmp_path and makes ``_http_get`` an outage; tests here install a fake API."""
from datetime import date, timedelta

import pandas as pd
import pytest

import fx


class FakeApi:
    """Serves frankfurter-shaped time-series bodies from a {ccy: {iso: rate}}
    table (rates = EUR per 1 unit), recording every request."""

    def __init__(self, table, currencies=("EUR", "USD", "CHF", "GBP")):
        self.table = table
        self.currencies = currencies
        self.calls: list[tuple[str, dict]] = []
        self.down = False

    def __call__(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        if self.down:
            raise fx.FxUnavailable("down")
        if path == "currencies":
            return {c: c for c in self.currencies}
        start, end = path.split("..")
        ccy = params["base"]
        if ccy not in self.table:
            raise fx.FxUnavailable("404")
        rates = {d: {params["symbols"]: v} for d, v in self.table[ccy].items() if start <= d <= end}
        return {"base": ccy, "rates": rates}


@pytest.fixture
def api(monkeypatch):
    table = {"USD": {"2026-01-02": 0.85, "2026-01-05": 0.86, "2026-01-06": 0.87},
             "CHF": {"2026-01-02": 1.07, "2026-01-05": 1.08}}
    a = FakeApi(table)
    monkeypatch.setattr(fx, "_http_get", a)
    return a


class TestGetRate:
    def test_base_currency_is_one_without_fetching(self, api):
        q = fx.get_rate("EUR", "EUR", date(2026, 1, 5))
        assert (q.rate, q.source) == (1.0, "base")
        assert api.calls == []

    def test_business_day_rate(self, api):
        q = fx.get_rate("USD", "EUR", date(2026, 1, 5))
        assert q.rate == 0.86 and q.rate_date == date(2026, 1, 5) and q.source == "ecb"
        assert api.calls[0][1] == {"base": "USD", "symbols": "EUR"}

    def test_weekend_resolves_to_previous_business_day(self, api):
        q = fx.get_rate("USD", "EUR", date(2026, 1, 4))   # Sunday
        assert q.rate == 0.85 and q.rate_date == date(2026, 1, 2)

    def test_second_lookup_is_served_from_cache(self, api):
        fx.get_rate("USD", "EUR", date(2026, 1, 5))
        n = len(api.calls)
        assert fx.get_rate("USD", "EUR", date(2026, 1, 5)).rate == 0.86
        assert len(api.calls) == n

    def test_cache_persists_to_disk(self, api):
        fx.get_rate("USD", "EUR", date(2026, 1, 5))
        fx._reset_for_tests()
        api.down = True
        assert fx.get_rate("USD", "EUR", date(2026, 1, 5)).rate == 0.86

    def test_outage_without_cache_raises(self, api):
        api.down = True
        with pytest.raises(fx.FxUnavailable):
            fx.get_rate("USD", "EUR", date(2026, 1, 5))

    def test_unknown_currency_raises(self, api):
        with pytest.raises(fx.FxUnavailable):
            fx.get_rate("XYZ", "EUR", date(2026, 1, 5))

    def test_before_ecb_start_raises(self, api):
        with pytest.raises(fx.FxUnavailable):
            fx.get_rate("USD", "EUR", date(1998, 12, 31))


class TestRatesFrame:
    def test_frame_columns_and_values(self, api):
        f = fx.rates_frame(["USD", "CHF", "EUR", "", None], start="2026-01-01", end="2026-01-06")
        assert set(f.columns) == {"USD", "CHF"}
        assert f.loc[pd.Timestamp("2026-01-05"), "USD"] == 0.86

    def test_all_base_returns_empty_without_fetching(self, api):
        assert fx.rates_frame(["EUR", "eur"], start="2026-01-01").empty
        assert api.calls == []

    def test_unknown_currency_is_omitted(self, api):
        f = fx.rates_frame(["USD", "XYZ"], start="2026-01-01", end="2026-01-06")
        assert list(f.columns) == ["USD"]

    def test_incremental_extension_fetches_only_the_tail(self, api):
        fx.rates_frame(["USD"], start="2026-01-01", end="2026-01-03")
        api.calls.clear()
        fx.rates_frame(["USD"], start="2026-01-01", end="2026-01-06")
        assert [c[0] for c in api.calls] == ["2026-01-04..2026-01-06"]

    def test_outage_returns_cached_data(self, api):
        fx.rates_frame(["USD"], start="2026-01-01", end="2026-01-06")
        api.down = True
        f = fx.rates_frame(["USD"], start="2026-01-01", end="2026-01-06")
        assert len(f) == 3

    def test_long_ranges_are_chunked(self, api):
        fx.rates_frame(["USD"], start=date(2020, 1, 1), end=date(2022, 6, 30))
        assert len(api.calls) >= 3

    def test_frame_matches_get_rate(self, api):
        """dividends_in_eur (frame + ffill) and the cash ledger (get_rate)
        must convert the same day at the same rate."""
        f = fx.rates_frame(["USD"], start="2026-01-01", end="2026-01-06")
        on = pd.Timestamp("2026-01-04")
        ffilled = f["USD"].reindex(f.index.union([on])).sort_index().ffill()[on]
        assert ffilled == fx.get_rate("USD", "EUR", on.date()).rate


class TestSupportedCurrencies:
    def test_common_set_first(self, api):
        api.currencies = ("JPY", "USD", "CHF", "EUR", "GBP")
        out = fx.supported_currencies()
        assert out[:4] == ["EUR", "USD", "GBP", "CHF"]
        assert "JPY" in out

    def test_fallback_on_outage(self, api):
        api.down = True
        assert fx.supported_currencies() == fx.FALLBACK_CURRENCIES


def test_recent_window_is_refreshed_after_ttl(api, monkeypatch):
    today = date.today()
    api.table["USD"][(today - timedelta(days=1)).isoformat()] = 0.9
    fx.get_rate("USD", "EUR", today)
    n = len(api.calls)
    fx.get_rate("USD", "EUR", today)
    assert len(api.calls) == n                        # within TTL: cached
    api.table["USD"][today.isoformat()] = 0.91         # today's fixing gets published
    fx._entry("EUR", "USD")["fetched_at"] = 0          # expire the recent window
    assert fx.get_rate("USD", "EUR", today).rate == 0.91
    assert len(api.calls) == n + 1
