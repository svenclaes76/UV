"""Cross-page regression locks for the invariants in docs/data-contracts.md.

Each assertion here corresponds to a real inconsistency that existed between
two screens at some point in the dq/* work: the same portfolio showing two
risk scores, a dataless holding rendering as VETO, "nan" leaking into a
sector label, a Holdings row whose printed price / fair value / MoS% didn't
reconcile. The per-helper unit tests live next to each helper; this file is
the "do the screens actually agree" layer.
"""
import re

import numpy as np
import pandas as pd
import pytest

import portfolio
import screener
from tests.conftest import make_portfolio_df, make_scored_df, make_scored_row
from tests.test_pages_dashboard import _run as _run_dashboard
from tests.test_pages_risk import _run as _run_risk
from uvalu import data as uv_data
from uvalu import nav as nav_registry


@pytest.fixture(autouse=True)
def _clean_nav_registry():
    saved = dict(nav_registry.pages)
    nav_registry.pages.clear()
    yield
    nav_registry.pages.clear()
    nav_registry.pages.update(saved)


_SHARED_CACHE = {"AAA.BR": {"Price": 100.0}}


def _gauge_score(html: str) -> "int | None":
    m = re.search(r"font-size:34px[^>]*?>\s*(\d+)\s*</span>", html)
    return int(m.group(1)) if m else None


def _dashboard_score(html: str) -> "int | None":
    m = re.search(r">\s*(\d+)\s*</span>\s*·\s*(?:Low|Moderate|Elevated)", html)
    return int(m.group(1)) if m else None


def test_risk_score_matches_between_dashboard_and_risk_page(isolated_data, monkeypatch):
    """docs/data-contracts.md → Portfolio risk report: the composite score on
    the Dashboard equals the one on the Risk page for the same portfolio."""
    portfolio.save_portfolio(make_portfolio_df())

    at_r = _run_risk(monkeypatch, risk_cache=_SHARED_CACHE)
    risk_score = _gauge_score("".join(m.value for m in at_r.markdown))

    at_d = _run_dashboard(monkeypatch, with_risk_cache=True)
    assert not at_d.exception, [str(e.value) for e in at_d.exception]
    dash_score = _dashboard_score("".join(m.value for m in at_d.markdown))

    assert risk_score is not None, "risk gauge score not found in markup"
    assert dash_score is not None, "dashboard risk score not found in markup"
    assert risk_score == dash_score


def test_dataless_holding_reads_nodata_not_veto_and_no_phantom_vetoes(isolated_data, monkeypatch):
    """docs/data-contracts.md → Signal badge: a held ticker with no scored row
    is NO DATA, never VETO (bool(nan) is True), and the veto count stays 0
    across pages."""
    portfolio.save_portfolio(make_portfolio_df(rows=[
        dict(ticker="AAA.BR", name="Alpha Corp", google_ticker="EBR:AAA", shares=10,
             purchase_value=1000.0, purchase_price=100.0, target_price=130.0,
             dividends=0.0, date_in="2023-01-01", date_out=""),
        dict(ticker="BBB.BR", name="Beta Corp", google_ticker="EBR:BBB", shares=5,
             purchase_value=500.0, purchase_price=100.0, target_price=130.0,
             dividends=0.0, date_in="2023-01-01", date_out=""),
    ]))
    only_aaa = make_scored_df([make_scored_row(Ticker="AAA.BR", Name="Alpha Corp")])

    at_d = _run_dashboard(monkeypatch, scored=only_aaa, with_risk_cache=True)
    assert not at_d.exception, [str(e.value) for e in at_d.exception]
    d_html = "".join(m.value for m in at_d.markdown)
    assert "NO DATA" in d_html
    assert "uv-badge-veto" not in d_html          # no phantom veto from bool(nan)

    at_r = _run_risk(monkeypatch, risk_cache=_SHARED_CACHE, portfolio_scored=only_aaa)
    r_html = "".join(m.value for m in at_r.markdown)
    assert "remain(s) under a hard veto" not in r_html


def test_missing_sector_never_renders_as_nan_and_labels_agree(isolated_data, monkeypatch):
    """docs/data-contracts.md → Sectors: a NaN sector collapses to "Unknown",
    identically on the Dashboard donut and the Risk-page concentration."""
    no_sector = make_scored_df([make_scored_row(Ticker="AAA.BR", Name="Alpha Corp",
                                                sector=float("nan"))])

    portfolio.save_portfolio(make_portfolio_df())
    at_d = _run_dashboard(monkeypatch, scored=no_sector, with_risk_cache=True)
    assert not at_d.exception, [str(e.value) for e in at_d.exception]
    d_html = "".join(m.value for m in at_d.markdown)
    assert ">nan<" not in d_html and "— nan" not in d_html

    at_r = _run_risk(monkeypatch, risk_cache=_SHARED_CACHE, portfolio_scored=no_sector)
    r_html = "".join(m.value for m in at_r.markdown)
    # The Risk page's concentration card renders the label as markdown.
    assert "Largest sector — Unknown" in r_html
    assert "— nan" not in r_html and ">nan<" not in r_html


class TestHoldingsRowReconciles:
    """docs/data-contracts.md → Margin of safety: after apply_live_mos, a
    Holdings row's printed price / fair value / MoS% reconcile — the
    "at fair value" label next to a -39.5% bar can't recur."""

    def _numbers(self, html: str):
        price = float(re.search(r">€([\d,]+\.\d\d)<", html).group(1).replace(",", ""))
        fv = float(re.search(r"fv €([\d,]+\.\d\d)<", html).group(1).replace(",", ""))
        mos = float(re.search(r">([+-]\d+\.\d)%<", html).group(1))
        return price, fv, mos

    def _render(self, batch_price, fair_value, live_price):
        from uvalu.components import holdings_row_html
        scored = pd.DataFrame([{"Ticker": "X.BR", "Price": batch_price,
                                "fair_value": fair_value, "MoS %": 99.9,
                                "margin_of_safety": 0.999}])
        row = uv_data.apply_live_mos(
            scored, {"X.BR": {"price": live_price, "quote_source": "intraday"}}).iloc[0]
        return holdings_row_html(
            ticker="X.BR", sector=None, name="X", decision="Monitor", veto=False,
            price=row["live_price"], fair_value=row["fair_value"], mos_pct=row["MoS %"],
            weight=0.1, value=1000.0, day_change_pct=0.0)

    def test_stale_cache_price_does_not_desync_the_row(self):
        # Porsche case: €40 cached price, €28 fair value, €28.21 live.
        price, fv, mos = self._numbers(self._render(40.0, 28.0, 28.21))
        assert price == pytest.approx(28.21)
        assert fv == pytest.approx(28.0)
        assert mos == pytest.approx((fv - price) / fv * 100, abs=0.15)

    def test_undervalued_row_reconciles(self):
        price, fv, mos = self._numbers(self._render(12.0, 13.44, 12.0))
        assert mos == pytest.approx((fv - price) / fv * 100, abs=0.15)
        assert mos > 0


def test_sector_hhi_and_position_hhi_are_distinct(isolated_data):
    """docs/data-contracts.md → Concentration: the Risk page's "Sector HHI"
    is the sector-level Herfindahl, not the position-count one."""
    from risk import _stage2_concentration
    pf = pd.DataFrame([
        {"ticker": "A", "current_value": 40.0, "sector": "Tech", "country": "BE"},
        {"ticker": "B", "current_value": 30.0, "sector": "Tech", "country": "BE"},
        {"ticker": "C", "current_value": 30.0, "sector": "Energy", "country": "FR"},
    ])
    c = _stage2_concentration(pf, 100.0)
    assert c.hhi == pytest.approx(0.16 + 0.09 + 0.09)        # position-count
    assert c.sector_hhi == pytest.approx(0.49 + 0.09)        # Tech 0.70, Energy 0.30
    assert c.hhi != c.sector_hhi


def test_the_two_fetch_lanes_agree_on_whether_a_held_ticker_has_a_fair_value():
    """docs/data-contracts.md → Fair value: a held ticker never shows a fair
    value on the Screener page and a blank ladder on the Dashboard. When the
    portfolio lane's own row came back too thin, it borrows the screener lane's
    (screener.backfill_thin_rows_from_screener_lane), then both run the same
    scorer — so the composite fair value matches."""
    saved = dict(screener.SCREENER_FETCH.live_cache)
    try:
        healthy = {"Ticker": "HELD.BR", "Name": "Held", "Price": 50.0,
                   "trailingEps": 4.0, "bookValue": 30.0, "targetMeanPrice": 72.0,
                   "fetched_at": "2026-09-02T00:00:00+00:00"}
        screener.SCREENER_FETCH.live_cache.clear()
        screener.SCREENER_FETCH.live_cache["HELD.BR"] = healthy
        thin = pd.DataFrame([{"Ticker": "HELD.BR", "Name": "Held", "Price": 50.0,
                              "fetched_at": "2026-09-01T00:00:00+00:00"}])

        borrowed = screener.backfill_thin_rows_from_screener_lane(thin)
        lane_fv = screener.run_screener_from_df(borrowed).iloc[0]["fair_value"]
        direct_fv = screener.run_screener_from_df(pd.DataFrame([healthy])).iloc[0]["fair_value"]

        assert pd.notna(lane_fv) and lane_fv > 0
        assert lane_fv == pytest.approx(direct_fv)
    finally:
        screener.SCREENER_FETCH.live_cache.clear()
        screener.SCREENER_FETCH.live_cache.update(saved)
