"""uvalu/universe.py — home listings only (V2, model M2)."""

from uvalu import universe


def test_home_listing_matches_the_exchange_country():
    assert universe.is_home_listing("SOLB.BR", "Belgium")
    assert universe.is_home_listing("NESN.SW", "Switzerland")
    assert not universe.is_home_listing("1AAPL.MI", "United States")
    assert not universe.is_home_listing("1INVEB.MI", "Sweden")   # the V1 currency case
    assert not universe.is_home_listing("APC.DE", "United States")


def test_unknown_country_is_not_a_home_listing_but_not_known_foreign_either():
    for country in (None, "", float("nan")):
        assert not universe.is_home_listing("XYZ.PA", country)
        assert not universe.known_foreign("XYZ.PA", country)


def test_known_foreign():
    assert universe.known_foreign("1EOG.MI", "United States")
    assert not universe.known_foreign("ENI.MI", "Italy")


def test_uncovered_suffix_is_never_home():
    assert universe.exchange_country("VOD.L") is None
    assert not universe.is_home_listing("VOD.L", "United Kingdom")


def test_home_listings_filters_a_list():
    stocks = [{"ticker": "ENI.MI"}, {"ticker": "1EOG.MI"}, {"ticker": "NEW.MI"}]
    countries = {"ENI.MI": "Italy", "1EOG.MI": "United States"}
    assert universe.home_listings(stocks, countries) == [{"ticker": "ENI.MI"}]


def test_dormant_lines_are_left_out_but_missing_volume_is_not_dormant():
    assert universe.is_dormant(0) and universe.is_dormant(0.0)
    assert not universe.is_dormant(None) and not universe.is_dormant(float("nan"))
    assert not universe.is_dormant(1200)
    stocks = [{"ticker": "NAI.AS"}, {"ticker": "NAITR.AS"}]
    countries = {"NAI.AS": "Netherlands", "NAITR.AS": "Netherlands"}
    assert universe.home_listings(stocks, countries, {"NAITR.AS": 0}) == [{"ticker": "NAI.AS"}]
