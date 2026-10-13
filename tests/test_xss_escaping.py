"""Script-injection regression test for the shared HTML builders (SR4,
docs/security-review.md #3).

The app renders much of its markup through st.markdown(unsafe_allow_html=True).
Company names, tickers and sectors come from the data provider, and notes and
display names from users, so each builder that embeds them must escape them.
This feeds a payload through every such builder and fails if a live tag
survives. Add a builder here when it starts embedding outside text.
"""

import pandas as pd
import pytest

from uvalu import components

PAYLOAD = '<img src=x onerror="alert(1)"><script>alert(2)</script>'


def _assert_escaped(html: str) -> None:
    assert "<img" not in html and "<script" not in html, html
    assert "&lt;img" in html or "&lt;script" in html, "payload text vanished instead of being escaped"


def test_dividend_row_escapes_the_company_name():
    _assert_escaped(components.dividend_row_html(
        name=PAYLOAD, ex_date="2026-11-12", pay_date="2026-11-20", net=19.0, gross=36.0))


def test_mover_row_escapes_ticker_and_name():
    html = components.mover_row_html(ticker=PAYLOAD, name=PAYLOAD, change_pct=3.2, max_abs=6.0)
    _assert_escaped(html)


@pytest.mark.parametrize("field", ["ticker", "sector", "name"])
def test_holdings_row_escapes_provider_text(field):
    kwargs = dict(ticker="ABC.BR", sector="Technology", name="ABC NV",
                  signal_code="neutral", veto=False, price=10.0, fair_value=12.0,
                  mos_pct=0.17, weight=0.05, value=1000.0, total_gain=50.0)
    kwargs[field] = PAYLOAD
    _assert_escaped(components.holdings_row_html(**kwargs))


def test_donut_escapes_category_names():
    _assert_escaped(components.donut_html(pd.Series({PAYLOAD: 100.0, "Technology": 50.0})))


def test_signal_badge_escapes_its_tooltip():
    _assert_escaped(components.signal_badge_html("neutral", "Mid score", tooltip=PAYLOAD))


def test_name_html_escapes():
    _assert_escaped(components._name_html(PAYLOAD))
