"""Dividend withholding per country of the company (exchange expansion plan
D13, EX-33, §5b; decided 17 Oct 2026).

Withholding is charged by the country a company is registered in, not by the
exchange it trades on: Airbus is Dutch, so its dividends follow the
Netherlands rate although it trades in Paris. Each country starts at its
headline rate withheld at source on dividends paid to a non-resident
individual, before any treaty refund — what a broker statement shows. Every
rate stays editable in Settings, and a user's own rate always wins.

Belgium has no rate here: for Belgian residents the 30% roerende voorheffing
is applied as a separate layer (portfolio.BE_WITHHOLDING_RATE), and a second
Belgian rate would count it twice.

The rates come from general knowledge, not an official source; the tax
advisor checks them (open item L30) and they are reviewed every January with
the other tax rules (L28), dated by TAX_RULES_REVIEWED.

No Streamlit import; unit-tested in tests/test_withholding.py.
"""
from __future__ import annotations

# Country (as the data provider and the exchange registry write it) → (ISO
# 3166 code for the translated name, statutory rate in %).
STATUTORY: dict[str, tuple[str, float]] = {
    "Austria": ("AT", 27.5),
    "Bermuda": ("BM", 0.0),
    "Cyprus": ("CY", 0.0),
    "Denmark": ("DK", 27.0),
    "Estonia": ("EE", 0.0),
    "Finland": ("FI", 35.0),          # nominee-held shares (the usual broker account); 30% when identified
    "France": ("FR", 12.8),           # individuals; brokers that don't apply it withhold 25%
    "Germany": ("DE", 26.375),        # 25% + solidarity surcharge
    "Greece": ("GR", 5.0),
    "Guernsey": ("GG", 0.0),
    "Iceland": ("IS", 22.0),
    "Ireland": ("IE", 25.0),
    "Isle of Man": ("IM", 0.0),
    "Italy": ("IT", 26.0),
    "Jersey": ("JE", 0.0),
    "Latvia": ("LV", 0.0),
    "Liechtenstein": ("LI", 12.5),
    "Lithuania": ("LT", 15.0),
    "Luxembourg": ("LU", 15.0),
    "Netherlands": ("NL", 15.0),
    "Norway": ("NO", 25.0),
    "Poland": ("PL", 19.0),
    "Portugal": ("PT", 28.0),         # individuals (25% for companies)
    "Spain": ("ES", 19.0),
    "Sweden": ("SE", 30.0),
    "Switzerland": ("CH", 35.0),
    "United Kingdom": ("GB", 0.0),
}
HOME_COUNTRY = "Belgium"     # its withholding is the separate Belgian layer
SETTING_KEY = "withholding_by_country"     # the user's own rates: {country: %}


def default_rate(country: "str | None") -> float:
    """The statutory default for a country; 0% for Belgium (applied
    separately) and for a country not in the table."""
    if not country or country == HOME_COUNTRY:
        return 0.0
    return STATUTORY.get(country, ("", 0.0))[1]


def country_name(country: str, lang: "str | None" = None) -> str:
    """The country's name in the UI language, from the locale data."""
    code = STATUTORY.get(country, ("",))[0] or ("BE" if country == HOME_COUNTRY else "")
    if not code:
        return country
    try:
        from babel import Locale
        from uvalu.i18n import current
        return Locale.parse((lang or current().lang).replace("-", "_")).territories.get(code, country)
    except Exception:
        return country


def company_country(ticker: str, country: "str | None" = None) -> "str | None":
    """The company's country: the one given (a scored row's ``country``), else
    the fundamentals already in memory, else its exchange's country. Never
    loads a cache from disk."""
    if isinstance(country, str) and country.strip():
        return country.strip()
    try:
        import screener
        for fetcher in (screener.PORTFOLIO_FETCH, screener.SCREENER_FETCH):
            c = (fetcher.live_cache.get(str(ticker)) or {}).get("country")
            if isinstance(c, str) and c.strip():
                return c.strip()
    except Exception:
        pass
    from uvalu import exchanges
    ex = exchanges.for_ticker(ticker)
    return ex.country if ex else None


def rate_for(country: "str | None", user_rates: "dict | None") -> float:
    """The withholding % for a country: the user's own rate, else the
    default. Belgium is always 0 here (applied separately)."""
    if not country or country == HOME_COUNTRY:
        return 0.0
    rates = user_rates or {}
    if country in rates:
        try:
            return float(rates[country])
        except (TypeError, ValueError):
            pass
    return default_rate(country)


def countries() -> list[str]:
    """Every country with a default, in English (sort by translated name in the UI)."""
    return sorted(STATUTORY)
