"""
Unit tests for fetch_tickers.py — exchange ticker-list fetching via
stockanalysis.com HTML tables, with hardcoded-index fallbacks and Frankfurt's
equity-vs-ETF/warrant symbol filter.

All HTTP (requests.get) and Yahoo (yfinance.Ticker) calls are mocked via
monkeypatch — no real network access. The Frankfurt exceptions cache file
is redirected into tmp_path so nothing touches the real .cache/ directory.
"""

import json

import pandas as pd
import pytest
import requests
import yfinance as yf

import fetch_tickers


@pytest.fixture(autouse=True)
def isolated_exceptions_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_tickers, "_EXCEPTIONS_FILE", tmp_path / "frankfurt_exceptions.json")


def _table_html(symbols, names):
    df = pd.DataFrame({"Symbol": symbols, "Company Name": names})
    return df.to_html(index=False)


class FakeResponse:
    def __init__(self, html, ok=True):
        self.text = html
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise requests.HTTPError("bad status")


# ── _fetch_via_stockanalysis ──────────────────────────────────────────────

class TestFetchViaStockanalysis:
    def test_single_page_returns_parsed_stocks(self, monkeypatch):
        html = _table_html(["AAA", "BBB"], ["Alpha Corp", "Beta Corp"])
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(html))

        result = fetch_tickers._fetch_via_stockanalysis(
            "http://example.test/list", suffix=".BR", mic="XBRU",
            label="Test", fallback_fn=lambda: [{"fallback": True}],
        )
        assert result == [
            {"name": "Alpha Corp", "isin": "", "ticker": "AAA.BR", "mic": "XBRU"},
            {"name": "Beta Corp", "isin": "", "ticker": "BBB.BR", "mic": "XBRU"},
        ]

    def test_paginates_until_short_page(self, monkeypatch):
        monkeypatch.setattr(fetch_tickers, "PAGE_SIZE", 2)
        pages = {
            "http://example.test/list": FakeResponse(_table_html(["AAA", "BBB"], ["A", "B"])),
            "http://example.test/list?page=2": FakeResponse(_table_html(["CCC"], ["C"])),
        }
        monkeypatch.setattr(requests, "get", lambda url, **k: pages[url])

        result = fetch_tickers._fetch_via_stockanalysis(
            "http://example.test/list", suffix=".BR", mic="XBRU",
            label="Test", fallback_fn=lambda: [],
        )
        assert [s["ticker"] for s in result] == ["AAA.BR", "BBB.BR", "CCC.BR"]

    def test_dedupes_repeated_symbols_within_a_page(self, monkeypatch):
        html = _table_html(["AAA", "AAA"], ["Alpha Corp", "Alpha Corp Duplicate"])
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(html))

        result = fetch_tickers._fetch_via_stockanalysis(
            "http://example.test/list", suffix=".BR", mic="XBRU",
            label="Test", fallback_fn=lambda: [],
        )
        assert len(result) == 1

    def test_skips_blank_and_nan_symbol_rows(self, monkeypatch):
        html = _table_html(["AAA", "", "nan"], ["Alpha Corp", "Blank", "NaN Row"])
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(html))

        result = fetch_tickers._fetch_via_stockanalysis(
            "http://example.test/list", suffix=".BR", mic="XBRU",
            label="Test", fallback_fn=lambda: [],
        )
        assert len(result) == 1
        assert result[0]["ticker"] == "AAA.BR"

    def test_falls_back_on_http_error(self, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("network down")
        monkeypatch.setattr(requests, "get", boom)

        result = fetch_tickers._fetch_via_stockanalysis(
            "http://example.test/list", suffix=".BR", mic="XBRU",
            label="Test", fallback_fn=lambda: [{"fallback": True}],
        )
        assert result == [{"fallback": True}]

    def test_falls_back_on_missing_expected_columns(self, monkeypatch):
        html = pd.DataFrame({"Foo": [1, 2]}).to_html(index=False)
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(html))

        result = fetch_tickers._fetch_via_stockanalysis(
            "http://example.test/list", suffix=".BR", mic="XBRU",
            label="Test", fallback_fn=lambda: [{"fallback": True}],
        )
        assert result == [{"fallback": True}]

    def test_falls_back_when_no_tables_found(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse("<p>no tables here</p>"))

        result = fetch_tickers._fetch_via_stockanalysis(
            "http://example.test/list", suffix=".BR", mic="XBRU",
            label="Test", fallback_fn=lambda: [{"fallback": True}],
        )
        assert result == [{"fallback": True}]

    def test_falls_back_when_no_stocks_parsed(self, monkeypatch):
        html = _table_html([], [])
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(html))

        result = fetch_tickers._fetch_via_stockanalysis(
            "http://example.test/list", suffix=".BR", mic="XBRU",
            label="Test", fallback_fn=lambda: [{"fallback": True}],
        )
        assert result == [{"fallback": True}]


class TestExchangeFetchers:
    @pytest.mark.parametrize("fn,url_attr,suffix,mic", [
        (fetch_tickers.fetch_brussels_tickers, "STOCKANALYSIS_URL", ".BR", "XBRU"),
        (fetch_tickers.fetch_amsterdam_tickers, "STOCKANALYSIS_AMS_URL", ".AS", "XAMS"),
        (fetch_tickers.fetch_paris_tickers, "STOCKANALYSIS_PAR_URL", ".PA", "XPAR"),
        (fetch_tickers.fetch_milan_tickers, "STOCKANALYSIS_MIL_URL", ".MI", "XMIL"),
        (fetch_tickers.fetch_swiss_tickers, "STOCKANALYSIS_SWX_URL", ".SW", "XSWX"),
    ])
    def test_uses_stockanalysis_when_available(self, monkeypatch, fn, url_attr, suffix, mic):
        html = _table_html(["AAA"], ["Alpha Corp"])
        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(html))
        result = fn()
        assert result == [{"name": "Alpha Corp", "isin": "", "ticker": f"AAA{suffix}", "mic": mic}]

    @pytest.mark.parametrize("fn,expected_mic,expected_suffix,expected_count", [
        (fetch_tickers.fetch_brussels_tickers, "XBRU", ".BR", 20),
        (fetch_tickers.fetch_amsterdam_tickers, "XAMS", ".AS", 25),
        (fetch_tickers.fetch_paris_tickers, "XPAR", ".PA", 40),
        (fetch_tickers.fetch_milan_tickers, "XMIL", ".MI", 40),
        (fetch_tickers.fetch_swiss_tickers, "XSWX", ".SW", 23),
    ])
    def test_falls_back_to_hardcoded_index_on_network_failure(
        self, monkeypatch, fn, expected_mic, expected_suffix, expected_count,
    ):
        monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError()))
        result = fn()
        assert len(result) == expected_count
        assert all(s["mic"] == expected_mic and s["ticker"].endswith(expected_suffix) for s in result)


# ── _is_equity_symbol ─────────────────────────────────────────────────────

class TestIsEquitySymbol:
    @pytest.mark.parametrize("symbol", ["SAP", "BMW", "DB1", "VOW3", "MUV2", "HNR1"])
    def test_valid_equity_patterns(self, symbol):
        assert fetch_tickers._is_equity_symbol(symbol) is True

    @pytest.mark.parametrize("symbol", [
        "1YD0",   # starts with digit
        "TL01",   # multiple digits
        "A1BC",   # digit not at end
        "AB0",    # ends in 0 (certificate series)
        "TOOLONG",  # more than 4 chars
        "abc",    # lowercase
        "",       # empty
    ])
    def test_rejected_patterns(self, symbol):
        assert fetch_tickers._is_equity_symbol(symbol) is False

    def test_exceptions_override_rejection(self):
        assert fetch_tickers._is_equity_symbol("P911", {"P911": True}) is True

    def test_exceptions_false_does_not_force_acceptance(self):
        # "P911" fails the base heuristic regardless of an explicit False entry.
        assert fetch_tickers._is_equity_symbol("P911", {"P911": False}) is False

    def test_no_exceptions_dict_is_safe(self):
        assert fetch_tickers._is_equity_symbol("SAP", None) is True


# ── exceptions cache persistence ─────────────────────────────────────────

class TestExceptionsCache:
    def test_load_returns_seed_defaults_when_missing(self):
        assert fetch_tickers._load_exceptions() == {"P911": True, "1COV": True}

    def test_load_returns_seed_defaults_on_corrupt_file(self):
        fetch_tickers._EXCEPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        fetch_tickers._EXCEPTIONS_FILE.write_text("not valid json{{{", encoding="utf-8")
        assert fetch_tickers._load_exceptions() == {"P911": True, "1COV": True}

    def test_save_and_load_roundtrip(self):
        fetch_tickers._save_exceptions({"FOO": True, "BAR": False})
        assert fetch_tickers._load_exceptions() == {"FOO": True, "BAR": False}

    def test_save_creates_parent_directory(self, tmp_path, monkeypatch):
        nested = tmp_path / "nested_cache_dir" / "frankfurt_exceptions.json"
        monkeypatch.setattr(fetch_tickers, "_EXCEPTIONS_FILE", nested)
        assert not nested.parent.exists()
        fetch_tickers._save_exceptions({"FOO": True})
        assert nested.parent.exists()


# ── _is_valid_on_yahoo / _auto_validate ───────────────────────────────────

class FakeFastInfo:
    def __init__(self, last_price):
        self.last_price = last_price


class TestIsValidOnYahoo:
    def test_true_when_last_price_present(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", lambda t: type("T", (), {"fast_info": FakeFastInfo(42.0)})())
        assert fetch_tickers._is_valid_on_yahoo("FOO") is True

    def test_false_when_last_price_missing(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", lambda t: type("T", (), {"fast_info": FakeFastInfo(None)})())
        assert fetch_tickers._is_valid_on_yahoo("FOO") is False

    def test_false_on_exception(self, monkeypatch):
        def boom(t):
            raise RuntimeError("no such ticker")
        monkeypatch.setattr(yf, "Ticker", boom)
        assert fetch_tickers._is_valid_on_yahoo("FOO") is False


class TestAutoValidate:
    def test_marks_valid_and_invalid_symbols(self, monkeypatch):
        monkeypatch.setattr(fetch_tickers, "_is_valid_on_yahoo", lambda s: s == "GOOD")
        result = fetch_tickers._auto_validate(["GOOD", "BAD"], {})
        assert result == {"GOOD": True, "BAD": False}

    def test_skips_symbols_already_in_cache(self, monkeypatch):
        calls = []
        monkeypatch.setattr(fetch_tickers, "_is_valid_on_yahoo", lambda s: calls.append(s) or True)
        fetch_tickers._auto_validate(["ALREADY"], {"ALREADY": False})
        assert calls == []

    def test_respects_validate_batch_limit(self, monkeypatch):
        monkeypatch.setattr(fetch_tickers, "_VALIDATE_BATCH", 2)
        calls = []
        monkeypatch.setattr(fetch_tickers, "_is_valid_on_yahoo", lambda s: calls.append(s) or True)
        fetch_tickers._auto_validate(["A", "B", "C", "D"], {})
        assert calls == ["A", "B"]

    def test_returns_input_unchanged_when_nothing_to_check(self, monkeypatch):
        def boom(s):
            raise AssertionError("should not be called")
        monkeypatch.setattr(fetch_tickers, "_is_valid_on_yahoo", boom)
        existing = {"A": True}
        assert fetch_tickers._auto_validate([], existing) == existing
        assert fetch_tickers._auto_validate(["A"], existing) == existing


# ── fetch_frankfurt_tickers integration ───────────────────────────────────

class TestFetchFrankfurtTickers:
    def test_filters_and_persists_exceptions_using_hardcoded_fallback(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError()))
        # Force every not-yet-cached symbol to fail Yahoo validation so this
        # test makes no real network calls.
        monkeypatch.setattr(fetch_tickers, "_is_valid_on_yahoo", lambda s: False)

        result = fetch_tickers.fetch_frankfurt_tickers()
        all_dax40 = fetch_tickers._hardcoded_dax40()

        # Every DAX40 symbol either passes the base heuristic or is covered
        # by the seeded exceptions (P911, 1COV) -> nothing should be dropped.
        assert len(result) == len(all_dax40)
        assert {s["ticker"] for s in result} == {s["ticker"] for s in all_dax40}

        # The exceptions cache should have been persisted to disk.
        saved = fetch_tickers._load_exceptions()
        assert saved["P911"] is True
        assert saved["1COV"] is True

    def test_drops_symbols_that_fail_both_heuristic_and_yahoo_probe(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError()))
        monkeypatch.setattr(fetch_tickers, "_is_valid_on_yahoo", lambda s: False)
        # Pre-seed the cache so P911/1COV are explicitly rejected instead of
        # relying on the built-in seed defaults.
        fetch_tickers._save_exceptions({"P911": False, "1COV": False})

        result = fetch_tickers.fetch_frankfurt_tickers()
        tickers = {s["ticker"] for s in result}
        assert "P911.DE" not in tickers
        assert "1COV.DE" not in tickers
