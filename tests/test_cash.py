"""Unit tests for cash.py — the Cash Management v1 ledger — and the
cash-posting trade wrappers in portfolio.py (record_buy / record_sell).

Persistence goes to tmp_path (same isolation as tests/test_portfolio.py);
FX is stubbed per test (conftest's autouse _fx_isolated makes the real API an
outage)."""
import csv
import io
from datetime import date, timedelta

import pandas as pd
import pytest

import cash
import fx
import portfolio


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(portfolio, "_BASE_DIR", tmp_path / "portfolio")
    portfolio.set_user("cash@example.com")
    yield
    portfolio.set_user("")


@pytest.fixture
def ecb(monkeypatch):
    """Fixed ECB rates: USD 0.85, CHF 1.07, GBP 1.16 (EUR per unit)."""
    rates = {"USD": 0.85, "CHF": 1.07, "GBP": 1.16}

    def fake(ccy, base="EUR", on=None):
        ccy = ccy.upper()
        if ccy == base:
            return fx.FxQuote(1.0, on or date.today(), "base")
        if ccy not in rates:
            raise fx.FxUnavailable("no rate")
        return fx.FxQuote(rates[ccy], on or date.today(), "ecb")

    monkeypatch.setattr(fx, "get_rate", fake)
    return rates


D = date(2026, 3, 2)


def _bal():
    return cash.balance()


# ── meta / ids ───────────────────────────────────────────────────────────────

class TestMeta:
    def test_base_currency_defaults_to_eur_and_is_persisted(self):
        assert portfolio.base_currency() == "EUR"
        assert portfolio.load_portfolio_meta()["base_currency"] == "EUR"

    def test_ids_are_sequential_and_never_reused(self):
        assert portfolio.next_id("trade") == "TRD-0001"
        assert portfolio.next_id("trade") == "TRD-0002"
        assert portfolio.next_id("cash") == "C-000001"
        assert portfolio.reserve_ids("dividend", 2) == ["DIV-0001", "DIV-0002"]

    def test_ensure_div_ids_fills_only_blanks(self):
        df = pd.DataFrame([{"ticker": "A", "div_id": "DIV-0007"}, {"ticker": "B"}])
        out, changed = portfolio.ensure_div_ids(df)
        assert changed and out.loc[0, "div_id"] == "DIV-0007"
        assert out.loc[1, "div_id"].startswith("DIV-")
        _, changed2 = portfolio.ensure_div_ids(out)
        assert not changed2


# ── manual entries ───────────────────────────────────────────────────────────

class TestManual:
    def test_signs(self):
        cash.post_manual("Deposit", D, 1000)
        cash.post_manual("Interest", D, 10)
        cash.post_manual("Fee", D, 5)
        cash.post_manual("Withdrawal", D, 100)
        types = {e["type"]: e["amount"] for e in cash.load_ledger()}
        assert types == {"Deposit": 1000.0, "Interest": 10.0, "Fee": -5.0, "Withdrawal": -100.0}
        assert _bal() == 905.0

    def test_amount_must_be_positive(self):
        for bad in (0, -5, "abc", None):
            with pytest.raises(cash.CashError, match="greater than zero"):
                cash.post_manual("Deposit", D, bad)

    def test_foreign_currency_stores_ecb_rate(self, ecb):
        e = cash.post_manual("Deposit", D, 2500, "USD", note="Transfer")
        assert (e["currency"], e["fx_rate"], e["fx_source"]) == ("USD", 0.85, "ecb")
        assert e["amount_base"] == 2125.0
        assert _bal() == 2125.0

    def test_manual_rate_is_flagged(self):
        e = cash.post_manual("Deposit", D, 1500, "GBP", manual_rate=1.1612)
        assert e["fx_source"] == "manual" and e["amount_base"] == 1741.8

    def test_outage_propagates_so_ui_can_ask_for_manual_rate(self):
        with pytest.raises(fx.FxUnavailable):
            cash.post_manual("Deposit", D, 100, "USD")

    def test_withdrawal_beyond_balance_is_blocked_and_writes_nothing(self):
        cash.post_manual("Deposit", D, 100)
        with pytest.raises(cash.CashError, match=r"Blocked: .*−€50\.00.*cannot go negative"):
            cash.post_manual("Withdrawal", D, 150)
        assert len(cash.load_ledger()) == 1
        assert portfolio.load_portfolio_meta()["cash_seq"] == 1   # no id burned

    def test_backdated_withdrawal_that_breaks_a_later_point_is_blocked(self):
        cash.post_manual("Deposit", D, 100)
        cash.post_manual("Withdrawal", D + timedelta(days=10), 80)
        # final balance would be −30 only because of the later withdrawal
        with pytest.raises(cash.CashError):
            cash.post_manual("Withdrawal", D + timedelta(days=5), 50)

    def test_backdated_withdrawal_shielded_by_later_adjustment_is_allowed(self):
        cash.post_manual("Deposit", D, 100)
        cash.post_adjustment(D + timedelta(days=10), 500)
        # dips to −20 only until the adjustment resets the balance ... still blocked
        with pytest.raises(cash.CashError):
            cash.post_manual("Withdrawal", D + timedelta(days=5), 120)
        cash.post_manual("Withdrawal", D + timedelta(days=5), 100)   # dips to 0: fine
        assert _bal() == 500.0


class TestAdjustment:
    def test_first_adjustment_is_the_opening_balance(self):
        e = cash.post_adjustment(D, 12000, "Opening balance · broker statement")
        assert e["opening"] and e["target_balance"] == 12000 and e["delta_at_entry"] == 12000
        assert _bal() == 12000

    def test_sets_balance_and_logs_delta(self):
        cash.post_manual("Deposit", D, 1000)
        e = cash.post_adjustment(D + timedelta(days=1), 987.6)
        assert not e["opening"] and e["delta_at_entry"] == -12.4
        rows = cash.replay(cash.load_ledger())
        assert rows[-1]["base"] == -12.4 and rows[-1]["bal"] == 987.6

    def test_negative_target_rejected(self):
        with pytest.raises(cash.CashError):
            cash.post_adjustment(D, -1)

    def test_backdated_entry_is_absorbed_by_later_adjustment(self):
        cash.post_manual("Deposit", D, 1000)
        cash.post_adjustment(D + timedelta(days=10), 1000)
        cash.post_manual("Deposit", D + timedelta(days=5), 200)
        assert _bal() == 1000.0            # the adjustment still sets 1000
        adj = [r for r in cash.replay(cash.load_ledger()) if r["type"] == "Adjustment"][0]
        assert adj["base"] == -200.0


class TestReplay:
    def test_orders_by_date_then_seq(self):
        cash.post_manual("Deposit", D + timedelta(days=2), 1)
        cash.post_manual("Deposit", D, 2)
        cash.post_manual("Deposit", D, 3)
        rows = cash.replay(cash.load_ledger())
        assert [r["amount"] for r in rows] == [2.0, 3.0, 1.0]
        assert [r["bal"] for r in rows] == [2.0, 5.0, 6.0]

    def test_ledger_roundtrip_keeps_none_not_nan(self):
        cash.post_manual("Deposit", D, 10)
        e = cash.load_ledger()[0]
        assert e["target_balance"] is None and e["ref_id"] is None
        assert e["auto"] is False

    def test_legacy_shape_migrates_to_opening_adjustment(self):
        portfolio.save_cash(pd.DataFrame([{"currency": "EUR", "amount": 500.0},
                                          {"currency": "EUR", "amount": 250.0}]))
        led = cash.load_ledger()
        assert len(led) == 1 and led[0]["type"] == "Adjustment" and led[0]["opening"]
        assert _bal() == 750.0


# ── trades: auto-posting + top-up (D3) ───────────────────────────────────────

class TestTrades:
    def test_buy_with_enough_cash_posts_one_entry(self):
        cash.post_manual("Deposit", D, 10_000)
        posted = cash.post_trade("Buy", trade_id="TRD-0001", ticker="TTE.PA", shares=60,
                                 gross=3534.0, fee=9.9, on=D)
        assert [p["type"] for p in posted] == ["Buy"]
        assert posted[0]["amount"] == -3543.9 and posted[0]["auto"]
        assert posted[0]["ref_label"] == "TRD-0001 · TTE.PA"
        assert "Bought 60 TTE.PA × €58.90 · fee €9.90" == posted[0]["note"]
        assert _bal() == pytest.approx(6456.1)

    def test_buy_with_empty_ledger_is_fully_topped_up(self):
        posted = cash.post_trade("Buy", trade_id="TRD-0001", ticker="X", shares=1, gross=100, fee=1, on=D)
        assert [p["type"] for p in posted] == ["Deposit", "Buy"]
        top = posted[0]
        assert top["topup"] and top["auto"] and top["amount"] == 101.0
        assert top["ref_id"] == "TRD-0001" and top["seq"] < posted[1]["seq"]
        assert _bal() == 0.0

    def test_partly_covered_buy_tops_up_the_shortfall(self):
        cash.post_manual("Deposit", D, 40)
        posted = cash.post_trade("Buy", trade_id="T", ticker="X", shares=1, gross=100, on=D)
        assert posted[0]["amount"] == 60.0
        assert _bal() == 0.0

    def test_backdated_buy_is_sized_against_later_withdrawals(self):
        cash.post_manual("Deposit", D, 100)
        cash.post_manual("Withdrawal", D + timedelta(days=10), 100)
        posted = cash.post_trade("Buy", trade_id="T", ticker="X", shares=1, gross=30,
                                 on=D + timedelta(days=5))
        assert posted[0]["topup"] and posted[0]["amount"] == 30.0
        assert not cash.has_negative_history(cash.load_ledger())
        assert _bal() == 0.0

    def test_sell_posts_proceeds_minus_fee(self):
        cash.post_trade("Sell", trade_id="T", ticker="X", shares=10, gross=500, fee=5, on=D)
        assert _bal() == 495.0

    def test_preview_matches_post(self):
        cash.post_manual("Deposit", D, 50)
        p = cash.preview_trade("Buy", 100, 2, on=D)
        assert p == {"amount": -102.0, "topup": 52.0, "after": 0.0}
        p2 = cash.preview_trade("Buy", 20, 0, on=D)
        assert p2["topup"] == 0.0 and p2["after"] == 30.0


class TestRecordWrappers:
    def _row(self, **kw):
        row = {"name": "Total", "ticker": "TTE.PA", "shares": 10, "purchase_price": 50.0,
               "purchase_value": 500.0, "dividends": 0.0, "date_in": "2026-03-02T00:00:00"}
        row.update(kw)
        return row

    def test_record_buy_links_position_and_cash(self):
        posted = portfolio.record_buy(self._row(), fee=5)
        pf = portfolio.load_portfolio()
        tid = pf.iloc[0]["trade_id"]
        assert tid == "TRD-0001" and pf.iloc[0]["fee"] == 5.0
        assert {p["ref_id"] for p in posted} == {tid}
        assert _bal() == 0.0 and posted[0]["amount"] == 505.0

    def test_record_buy_rolls_back_position_when_cash_fails(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("disk full")
        monkeypatch.setattr(cash, "post_trade", boom)
        with pytest.raises(RuntimeError):
            portfolio.record_buy(self._row())
        pf = portfolio.load_portfolio()
        assert pf is None or pf.empty
        assert cash.load_ledger() == []

    def test_record_sell_partial_keeps_remainder_and_posts_proceeds(self):
        portfolio.record_buy(self._row())
        sold = portfolio.record_sell("TTE.PA", 4, 60.0, 2.0, "2026-06-01T00:00:00")
        pf = portfolio.load_portfolio()
        assert pf.iloc[0]["shares"] == 6 and pf.iloc[0]["purchase_value"] == 300.0
        assert sold["shares"] == 4 and sold["purchase_value"] == 200.0 and sold["sale_value"] == 240.0
        assert sold["trade_id"] == "TRD-0002"
        assert _bal() == 238.0

    def test_record_sell_rolls_back_on_cash_failure(self, monkeypatch):
        portfolio.record_buy(self._row())
        pf_before = portfolio.load_portfolio()
        monkeypatch.setattr(cash, "post_trade", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
        with pytest.raises(RuntimeError):
            portfolio.record_sell("TTE.PA", 4, 60.0, 0, "2026-06-01T00:00:00")
        pd.testing.assert_frame_equal(portfolio.load_portfolio(), pf_before)
        assert portfolio.load_sold() is None


class TestPartialSell:
    def test_fifo_across_lots(self):
        portfolio.save_portfolio(pd.DataFrame([
            {"ticker": "A", "shares": 10, "purchase_value": 1000.0, "dividends": 10.0, "date_in": "2024-02-01"},
            {"ticker": "A", "shares": 10, "purchase_value": 800.0, "dividends": 0.0, "date_in": "2023-01-01"},
        ]))
        sold = portfolio.sell_position("A", 15, 1500.0, "2025-01-01")
        pf = portfolio.load_portfolio()
        assert len(pf) == 1 and pf.iloc[0]["date_in"] == "2024-02-01"
        assert pf.iloc[0]["shares"] == 5 and pf.iloc[0]["purchase_value"] == 500.0
        assert pf.iloc[0]["dividends"] == 5.0
        assert sold["shares"] == 15 and sold["purchase_value"] == 1300.0
        assert sold["date_in"] == "2023-01-01"

    def test_partial_within_one_lot(self):
        portfolio.save_portfolio(pd.DataFrame([
            {"ticker": "A", "shares": 10, "purchase_value": 1000.0, "dividends": 0.0, "date_in": "2024-02-01"}]))
        portfolio.sell_position("A", 3, 330.0, "2025-01-01")
        pf = portfolio.load_portfolio()
        assert pf.iloc[0]["shares"] == 7 and pf.iloc[0]["purchase_value"] == 700.0

    def test_selling_everything_closes_all_lots(self):
        portfolio.save_portfolio(pd.DataFrame([
            {"ticker": "A", "shares": 10, "purchase_value": 1000.0, "date_in": "2024-02-01"},
            {"ticker": "A", "shares": 5, "purchase_value": 400.0, "date_in": "2023-02-01"}]))
        sold = portfolio.sell_position("A", 15, 1500.0, "2025-01-01")
        assert portfolio.load_portfolio().empty and sold["purchase_value"] == 1400.0


# ── dividends mirrored into the ledger ───────────────────────────────────────

class TestDividendMirroring:
    PAST = "2026-01-15T00:00:00"

    def _div(self, **kw):
        row = {"name": "Allianz", "ticker": "ALV.DE", "amount": 100.0, "tax_amount": 0.0,
               "currency": "EUR", "date": self.PAST, "div_type": "Cash", "shares": 10}
        row.update(kw)
        return row

    def test_add_posts_net_of_all_withholding(self):
        portfolio.add_dividend(self._div(tax_amount=10.0))
        led = cash.load_ledger()
        assert len(led) == 1 and led[0]["type"] == "Dividend" and led[0]["auto"]
        # gross 100 − foreign 10 − BE 30% of 90 (27) = 63
        assert led[0]["amount"] == 63.0
        div = portfolio.load_div_hist()
        assert led[0]["ref_id"] == div.iloc[0]["div_id"]
        assert led[0]["ref_label"] == f"{div.iloc[0]['div_id']} · ALV.DE"

    def test_edit_updates_and_delete_removes_mirror(self):
        portfolio.add_dividend(self._div())
        df = portfolio.load_div_hist()
        df.loc[0, "amount"] = 200.0
        portfolio.update_div_hist(df)
        assert cash.load_ledger()[0]["amount"] == 140.0
        portfolio.update_div_hist(df.drop(index=0).reset_index(drop=True))
        assert cash.load_ledger() == []

    def test_drip_stock_and_future_dividends_do_not_post(self):
        future = (pd.Timestamp.now() + pd.Timedelta(days=30)).isoformat()
        portfolio.add_dividend(self._div(reinvested=True))
        portfolio.add_dividend(self._div(div_type="Stock", date="2026-02-15T00:00:00"))
        portfolio.add_dividend(self._div(date=future))
        assert cash.load_ledger() == []

    def test_future_dividend_posts_once_due(self, monkeypatch):
        portfolio.add_dividend(self._div(date="2026-12-01T00:00:00"))
        real_date = cash.date

        class _Later(real_date):
            @classmethod
            def today(cls):
                return real_date(2026, 12, 2)

        monkeypatch.setattr(cash, "date", _Later)
        assert cash.reconcile_dividend_postings() == 1

    def test_foreign_dividend_uses_ecb_rate_and_matches_dividends_page(self, ecb, monkeypatch):
        monkeypatch.setattr(fx, "rates_frame", lambda *a, **k: pd.DataFrame(
            {"CHF": [1.07]}, index=pd.to_datetime(["2026-01-15"])))
        portfolio.add_dividend(self._div(ticker="NESN.SW", currency="CHF"))
        e = cash.load_ledger()[0]
        assert (e["currency"], e["fx_rate"], e["fx_source"]) == ("CHF", 1.07, "ecb")
        page = portfolio.dividends_in_eur(portfolio.load_div_hist())
        assert e["amount_base"] == pytest.approx(round(page.loc[0, "net_after_be_amount_eur"], 2))

    def test_foreign_dividend_waits_when_fx_unavailable(self):
        portfolio.add_dividend(self._div(ticker="NESN.SW", currency="CHF"))
        assert cash.load_ledger() == []          # no guessed rate


# ── summary + export ─────────────────────────────────────────────────────────

class TestSummaryAndExport:
    def _seed(self, ecb=None):
        cash.post_adjustment(D, 1000, "Opening")
        cash.post_manual("Deposit", D + timedelta(days=1), 500, note='Salary, "March"')
        cash.post_manual("Fee", D + timedelta(days=2), 20)
        cash.post_trade("Buy", trade_id="TRD-0001", ticker="X", shares=1, gross=300, on=D + timedelta(days=3))
        cash.post_manual("Interest", D + timedelta(days=4), 5)

    def test_summary_tiles(self):
        self._seed()
        s = cash.summary(cash.load_ledger(), invested_value=3815.0)
        assert s["balance"] == 1185.0 and s["total"] == 5000.0
        assert s["cash_pct"] == pytest.approx(23.7)
        assert s["net_deposits"] == 500.0 and s["trade_flow"] == -300.0
        assert s["income"] == 5.0 and s["fees_corrections"] == -20.0   # opening excluded
        assert s["corrections"] == 0 and s["last_type"] == "Interest"

    def test_filter_groups(self):
        self._seed()
        rows = cash.replay(cash.load_ledger())
        assert {r["type"] for r in cash.filter_rows(rows, "Trades")} == {"Buy"}
        assert len(cash.filter_rows(rows, "All")) == len(rows)

    def test_export_columns_order_and_running_balance(self):
        self._seed()
        text = cash.export_csv().decode("utf-8")
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[0] == ["date", "type", "amount", "currency", "fx_rate", "amount_eur",
                           "note", "reference", "running_balance_eur", "fx_source"]
        body = rows[1:]
        assert body[0][1] == "Adjustment" and body[0][2] == "" and body[0][5] == "1000.00"
        assert body[1][6] == 'Salary, "March"'           # quoted correctly
        assert [r[8] for r in body] == [f"{r['bal']:.2f}" for r in cash.replay(cash.load_ledger())]
        assert body[3][7] == "TRD-0001 · X"

    def test_money_format(self):
        assert cash.money(-12.4) == "−€12.40"
        assert cash.signed_money(5) == "+€5.00"
        assert cash.money(1234.5, "CHF", 0) == "CHF 1,234"
