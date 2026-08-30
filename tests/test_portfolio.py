"""
Unit tests for portfolio.py — persistence, CRUD helpers, dividend syncing,
value-history bookkeeping, and the fixed-layout Excel importer.

Every test redirects portfolio._BASE_DIR into tmp_path and uses a fixed
ENCRYPTION_KEY, so nothing here touches the real data/portfolio directory.
"""

import datetime as dt

import pandas as pd
import pytest

import portfolio


@pytest.fixture(autouse=True)
def isolated_portfolio(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(portfolio, "_BASE_DIR", tmp_path / "portfolio")
    portfolio.set_user("test@example.com")
    yield
    portfolio.set_user("")


# ── user dir / persistence primitives ────────────────────────────────────

class TestUserDir:
    def test_different_emails_get_different_dirs(self):
        assert portfolio.user_data_dir("a@example.com") != portfolio.user_data_dir("b@example.com")

    def test_same_email_is_stable(self):
        assert portfolio.user_data_dir("a@example.com") == portfolio.user_data_dir("a@example.com")

    def test_no_email_falls_back_to_active_user(self):
        assert portfolio.user_data_dir("") == portfolio.user_data_dir("test@example.com")


class TestSaveLoadRoundtrip:
    def test_portfolio_roundtrip(self):
        df = pd.DataFrame([{"ticker": "AAA.BR", "shares": 10, "purchase_value": 100.0}])
        portfolio.save_portfolio(df)
        loaded = portfolio.load_portfolio()
        assert loaded.iloc[0]["ticker"] == "AAA.BR"
        assert loaded.iloc[0]["shares"] == 10

    def test_load_returns_none_when_file_missing(self):
        assert portfolio.load_portfolio() is None

    def test_load_returns_none_on_corrupt_file(self):
        from crypto import write_encrypted
        path = portfolio.user_data_dir() / "portfolio.json"
        write_encrypted(path, "not valid json{{{")
        assert portfolio.load_portfolio() is None

    def test_portfolio_exists_reflects_file_presence(self):
        assert not portfolio.portfolio_exists()
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR"}]))
        assert portfolio.portfolio_exists()

    def test_sold_and_div_hist_roundtrip(self):
        portfolio.save_sold(pd.DataFrame([{"ticker": "AAA.BR", "sale_value": 50.0}]))
        portfolio.save_div_hist(pd.DataFrame([{"ticker": "AAA.BR", "amount": 5.0}]))
        assert portfolio.load_sold().iloc[0]["sale_value"] == 50.0
        assert portfolio.load_div_hist().iloc[0]["amount"] == 5.0


# ── CRUD helpers ──────────────────────────────────────────────────────────

class TestAddPosition:
    def test_appends_to_existing_portfolio(self):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR", "shares": 10}]))
        portfolio.add_position({"ticker": "BBB.BR", "shares": 5})
        loaded = portfolio.load_portfolio()
        assert set(loaded["ticker"]) == {"AAA.BR", "BBB.BR"}

    def test_creates_portfolio_when_none_exists(self):
        portfolio.add_position({"ticker": "AAA.BR", "shares": 10})
        loaded = portfolio.load_portfolio()
        assert len(loaded) == 1
        assert loaded.iloc[0]["ticker"] == "AAA.BR"


class TestRemovePositions:
    def test_drops_rows_by_index(self):
        portfolio.save_portfolio(pd.DataFrame([
            {"ticker": "AAA.BR"}, {"ticker": "BBB.BR"}, {"ticker": "CCC.BR"},
        ]))
        portfolio.remove_positions([1])
        loaded = portfolio.load_portfolio()
        assert list(loaded["ticker"]) == ["AAA.BR", "CCC.BR"]

    def test_noop_when_no_portfolio(self):
        portfolio.remove_positions([0])
        assert portfolio.load_portfolio() is None


class TestUpdatePositions:
    def test_overwrites_portfolio_file(self):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR"}]))
        portfolio.update_positions(pd.DataFrame([{"ticker": "ZZZ.BR"}]))
        loaded = portfolio.load_portfolio()
        assert list(loaded["ticker"]) == ["ZZZ.BR"]


# ── annual return / sell_position ────────────────────────────────────────

class TestAnnualReturnPct:
    def test_known_cagr(self):
        # 1000 -> 1200 (no dividends) over exactly 365 days = +20%
        result = portfolio._annual_return_pct(1000.0, 1200.0, 0.0, "2023-01-01", "2024-01-01")
        assert result == 20.0

    def test_dividends_are_included_in_total_return(self):
        result = portfolio._annual_return_pct(1000.0, 1100.0, 100.0, "2023-01-01", "2024-01-01")
        assert result == 20.0

    def test_zero_or_negative_holding_period_returns_none(self):
        assert portfolio._annual_return_pct(1000.0, 1200.0, 0.0, "2024-01-01", "2024-01-01") is None
        assert portfolio._annual_return_pct(1000.0, 1200.0, 0.0, "2024-01-01", "2023-01-01") is None

    def test_non_positive_purchase_value_returns_none(self):
        assert portfolio._annual_return_pct(0.0, 1200.0, 0.0, "2023-01-01", "2024-01-01") is None

    def test_invalid_dates_return_none(self):
        assert portfolio._annual_return_pct(1000.0, 1200.0, 0.0, "not-a-date", "also-not-a-date") is None

    def test_non_numeric_purchase_value_is_caught_and_returns_none(self):
        assert portfolio._annual_return_pct("not-a-number", 1200.0, 0.0, "2023-01-01", "2024-01-01") is None


class TestSellPosition:
    def test_moves_position_from_open_to_sold(self):
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Test Corp", "google_ticker": "EBR:TESTX",
            "purchase_value": 1000.0, "dividends": 50.0, "date_in": "2023-01-01",
        }]))
        portfolio.sell_position("AAA.BR", 10, 1200.0, "2024-01-01")

        assert portfolio.load_portfolio().empty
        sold = portfolio.load_sold()
        assert len(sold) == 1
        row = sold.iloc[0]
        assert row["ticker"] == "AAA.BR"
        assert row["shares"] == 10
        assert row["sale_value"] == 1200.0
        assert row["annual_return_pct"] == pytest.approx(25.0)

    def test_only_matching_ticker_is_removed(self):
        portfolio.save_portfolio(pd.DataFrame([
            {"ticker": "AAA.BR", "purchase_value": 1000.0, "dividends": 0.0, "date_in": "2023-01-01"},
            {"ticker": "BBB.BR", "purchase_value": 500.0, "dividends": 0.0, "date_in": "2023-01-01"},
        ]))
        portfolio.sell_position("AAA.BR", 10, 1200.0, "2024-01-01")
        remaining = portfolio.load_portfolio()
        assert list(remaining["ticker"]) == ["BBB.BR"]

    def test_nan_purchase_value_and_dividends_fall_back_to_zero(self):
        # `float(row.get(...) or 0)` doesn't catch NaN (bool(nan) is True in
        # Python) -- a row with a missing/NaN purchase_value or dividends
        # field (e.g. from a partially-migrated record) must still fall back
        # to 0 rather than silently persisting NaN into the sold record.
        portfolio.save_portfolio(pd.DataFrame([
            {"ticker": "AAA.BR", "purchase_value": 1000.0, "dividends": 0.0, "date_in": "2023-01-01"},
            {"ticker": "BBB.BR", "purchase_value": float("nan"), "dividends": float("nan"),
             "date_in": "2023-01-01"},
        ]))
        portfolio.sell_position("BBB.BR", 5, 400.0, "2024-01-01")
        sold = portfolio.load_sold()
        row = sold[sold["ticker"] == "BBB.BR"].iloc[0]
        assert row["purchase_value"] == 0.0
        assert row["dividends"] == 0.0
        assert not pd.isna(row["purchase_value"])
        assert not pd.isna(row["dividends"])

    def test_noop_when_no_portfolio(self):
        portfolio.sell_position("AAA.BR", 10, 1200.0, "2024-01-01")
        assert portfolio.load_portfolio() is None
        assert portfolio.load_sold() is None

    def test_noop_when_ticker_not_found(self):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR", "purchase_value": 1000.0,
                                                  "dividends": 0.0, "date_in": "2023-01-01"}]))
        portfolio.sell_position("ZZZ.BR", 10, 1200.0, "2024-01-01")
        assert len(portfolio.load_portfolio()) == 1
        assert portfolio.load_sold() is None


class TestAddClosedTrade:
    def test_appends_to_sold_directly(self):
        portfolio.add_closed_trade({"ticker": "AAA.BR", "sale_value": 300.0})
        sold = portfolio.load_sold()
        assert len(sold) == 1
        assert sold.iloc[0]["ticker"] == "AAA.BR"

    def test_appends_to_existing_sold(self):
        portfolio.save_sold(pd.DataFrame([{"ticker": "AAA.BR"}]))
        portfolio.add_closed_trade({"ticker": "BBB.BR"})
        assert set(portfolio.load_sold()["ticker"]) == {"AAA.BR", "BBB.BR"}


# ── dividends ─────────────────────────────────────────────────────────────

class TestDividendSync:
    def test_add_dividend_updates_portfolio_totals(self):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR", "dividends": 0.0}]))
        portfolio.add_dividend({"ticker": "AAA.BR", "amount": 10.0})
        assert portfolio.load_portfolio().iloc[0]["dividends"] == 10.0
        assert portfolio.load_div_hist().iloc[0]["amount"] == 10.0

    def test_multiple_dividends_for_same_ticker_are_summed(self):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR", "dividends": 0.0}]))
        portfolio.add_dividend({"ticker": "AAA.BR", "amount": 10.0})
        portfolio.add_dividend({"ticker": "AAA.BR", "amount": 15.0})
        assert portfolio.load_portfolio().iloc[0]["dividends"] == 25.0

    def test_ticker_without_dividend_records_keeps_existing_value(self):
        portfolio.save_portfolio(pd.DataFrame([
            {"ticker": "AAA.BR", "dividends": 0.0},
            {"ticker": "BBB.BR", "dividends": 7.0},
        ]))
        portfolio.add_dividend({"ticker": "AAA.BR", "amount": 10.0})
        loaded = portfolio.load_portfolio().set_index("ticker")
        assert loaded.loc["BBB.BR", "dividends"] == 7.0

    def test_sync_is_noop_when_no_portfolio(self):
        portfolio.add_dividend({"ticker": "AAA.BR", "amount": 10.0})
        assert portfolio.load_portfolio() is None
        assert portfolio.load_div_hist().iloc[0]["amount"] == 10.0

    def test_update_div_hist_persists_and_syncs(self):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR", "dividends": 0.0}]))
        portfolio.update_div_hist(pd.DataFrame([{"ticker": "AAA.BR", "amount": 12.0}]))
        assert portfolio.load_div_hist().iloc[0]["amount"] == 12.0
        assert portfolio.load_portfolio().iloc[0]["dividends"] == 12.0


# ── cash ──────────────────────────────────────────────────────────────────

class TestCash:
    def test_roundtrip(self):
        portfolio.save_cash(pd.DataFrame([{"currency": "EUR", "amount": 500.0}]))
        loaded = portfolio.load_cash()
        assert loaded.iloc[0]["amount"] == 500.0

    def test_returns_none_when_missing(self):
        assert portfolio.load_cash() is None


# ── value history ─────────────────────────────────────────────────────────

class TestValueHistory:
    def test_load_returns_none_when_missing(self):
        assert portfolio.load_value_history() is None

    def test_record_snapshot_appends_new_day(self):
        portfolio.save_value_history(pd.DataFrame([
            {"date": "2000-01-01", "invested": 100.0, "value": 110.0},
        ]))
        portfolio.record_value_snapshot(200.0, 250.0)
        hist = portfolio.load_value_history()
        assert len(hist) == 2
        assert "2000-01-01" in list(hist["date"])

    def test_record_snapshot_replaces_same_day_entry(self):
        portfolio.record_value_snapshot(100.0, 110.0)
        portfolio.record_value_snapshot(200.0, 260.0)
        hist = portfolio.load_value_history()
        today = dt.date.today().isoformat()
        rows = hist[hist["date"] == today]
        assert len(rows) == 1
        assert rows.iloc[0]["value"] == 260.0

    def test_backfill_returns_zero_when_no_valid_segments(self):
        # All rows missing ticker/shares/date_in -> no segments built, no
        # yfinance network call should even be attempted.
        open_df = pd.DataFrame([{"ticker": "", "shares": None, "date_in": None, "purchase_value": None}])
        assert portfolio.backfill_value_history(open_df, None) == 0

    def test_backfill_builds_value_and_benchmark_history(self, monkeypatch):
        import yfinance as yf

        dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
        close = pd.DataFrame({
            "AAA.BR": [10.0, 11.0, 12.0],
            "^GSPC": [100.0, 101.0, 102.0],
            "^STOXX50E": [50.0, 51.0, 52.0],
        }, index=dates)
        raw = pd.concat({"Close": close}, axis=1)
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw)

        open_df = pd.DataFrame([{
            "ticker": "AAA.BR", "shares": 10, "date_in": "2024-01-01", "purchase_value": 1000.0,
        }])
        written = portfolio.backfill_value_history(open_df, None)
        assert written == 3

        hist = portfolio.load_value_history().set_index("date")
        row1 = hist.loc["2024-01-01"]
        assert row1["invested"] == 1000.0
        assert row1["value"] == 100.0
        assert row1["benchmark_spx"] == 1000.0
        assert row1["benchmark_stoxx"] == 1000.0

        row3 = hist.loc["2024-01-03"]
        assert row3["value"] == 120.0
        assert row3["benchmark_spx"] == 1020.0
        assert row3["benchmark_stoxx"] == 1040.0


# ── watchlist / manual tickers ────────────────────────────────────────────

class TestWatchlist:
    def test_roundtrip(self):
        portfolio.save_watchlist({"AAA.BR", "BBB.BR"})
        assert portfolio.load_watchlist() == {"AAA.BR", "BBB.BR"}

    def test_defaults_to_empty_set(self):
        assert portfolio.load_watchlist() == set()

    def test_corrupt_file_falls_back_to_default(self):
        from crypto import write_encrypted
        write_encrypted(portfolio.user_data_dir() / "watchlist.json", "not valid json{{{")
        assert portfolio.load_watchlist() == set()


class TestManualTickers:
    def test_roundtrip(self):
        portfolio.save_manual_tickers({"AAA.BR": "Test Corp"})
        assert portfolio.load_manual_tickers() == {"AAA.BR": "Test Corp"}

    def test_defaults_to_empty_dict(self):
        assert portfolio.load_manual_tickers() == {}


class TestTargets:
    def test_roundtrip_and_validation(self):
        portfolio.save_targets({
            "sectors": {"Technology": 0.30, "Bad": -0.1, "TooBig": 1.5, "NaN": "x"},
            "tickers": {"AAA.BR": 0.12},
            "hhi_max": 0.15,
        })
        t = portfolio.load_targets()
        assert t["sectors"] == {"Technology": 0.30}          # invalid entries dropped
        assert t["tickers"] == {"AAA.BR": 0.12}
        assert t["hhi_max"] == 0.15

    def test_defaults_to_empty_dict(self):
        assert portfolio.load_targets() == {}

    def test_bad_hhi_max_is_dropped(self):
        portfolio.save_targets({"hhi_max": "oops"})
        assert "hhi_max" not in portfolio.load_targets()


class TestRiskSnapshot:
    def test_defaults_to_empty_dict(self):
        assert portfolio.load_risk_snapshot() == {}

    def test_roundtrip_stamps_date(self):
        portfolio.save_risk_snapshot({"hhi": 0.14, "sharpe": 0.9})
        s = portfolio.load_risk_snapshot()
        assert s["hhi"] == 0.14 and s["sharpe"] == 0.9
        assert s["date"] == dt.date.today().isoformat()

    def test_explicit_date_is_preserved(self):
        portfolio.save_risk_snapshot({"date": "2020-01-01", "hhi": 0.2})
        assert portfolio.load_risk_snapshot()["date"] == "2020-01-01"


# ── Excel parsing ─────────────────────────────────────────────────────────

class TestPrepSection:
    def _raw(self, rows):
        """Build an 18-column raw DataFrame from a list of {col_index: value} dicts."""
        data = []
        for row in rows:
            data.append([row.get(i) for i in range(18)])
        return pd.DataFrame(data)

    def test_filters_rows_without_recognised_prefix(self):
        raw = self._raw([
            {1: "EBR:VALID"},
            {1: "XYZ:INVALID"},
            {1: None},
        ])
        section = portfolio._prep_section(raw, slice(0, 3))
        assert list(section["google_ticker"]) == ["EBR:VALID"]
        assert section.iloc[0]["ticker"] == "VALID.BR"

    @pytest.mark.parametrize("prefix,suffix", [
        ("EBR", ".BR"), ("AMS", ".AS"), ("EPA", ".PA"),
        ("BIT", ".MI"), ("ETR", ".DE"), ("SWX", ".SW"),
    ])
    def test_maps_all_known_exchange_suffixes(self, prefix, suffix):
        raw = self._raw([{1: f"{prefix}:TICK"}])
        section = portfolio._prep_section(raw, slice(0, 1))
        assert section.iloc[0]["ticker"] == f"TICK{suffix}"


class TestParseExcel:
    def _build_workbook(self, tmp_path):
        n_cols = 18
        rows = [[None] * n_cols for _ in range(110)]

        # Open position at 0-indexed row 1 (Excel row 2)
        rows[1][0] = "Test Corp"
        rows[1][1] = "EBR:TESTX"
        rows[1][2] = 10
        rows[1][4] = 50.0
        rows[1][6] = 1000.0
        rows[1][10] = 5.0
        rows[1][16] = "2024-01-01"

        # Dividend at 0-indexed row 19 (Excel row 20)
        rows[19][0] = "Test Corp"
        rows[19][1] = "EBR:TESTX"
        rows[19][2] = 10
        rows[19][6] = 25.0
        rows[19][16] = "2024-03-01"

        # Sold position at 0-indexed row 94 (Excel row 95)
        rows[94][0] = "Test Corp"
        rows[94][1] = "EBR:TESTX"
        rows[94][2] = 5
        rows[94][6] = 500.0
        rows[94][7] = 600.0
        rows[94][10] = 2.0
        rows[94][16] = "2023-01-01"
        rows[94][17] = "2023-06-01"

        path = tmp_path / "portfolio_export.xlsx"
        pd.DataFrame(rows).to_excel(path, sheet_name="beleggingen", header=False, index=False)
        return path

    def test_extracts_open_sold_and_dividend_sections(self, tmp_path):
        path = self._build_workbook(tmp_path)
        open_df, sold_df, div_df = portfolio.parse_excel(path)

        assert len(open_df) == 1
        assert open_df.iloc[0]["ticker"] == "TESTX.BR"
        assert open_df.iloc[0]["shares"] == 10
        assert open_df.iloc[0]["purchase_value"] == 1000.0

        assert len(sold_df) == 1
        assert sold_df.iloc[0]["sale_value"] == 600.0
        assert sold_df.iloc[0]["date_out"] == pd.Timestamp("2023-06-01")

        assert len(div_df) == 1
        assert div_df.iloc[0]["amount"] == 25.0
        assert div_df.iloc[0]["date"] == pd.Timestamp("2024-03-01")
