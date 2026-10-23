"""uvalu/universe.py — home listings (V2, model M2) and the primary-listing rule (EX-W4)."""

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


# ── EX-W4: one line per company, its primary listing ──────────────────────

from datetime import date, timedelta

TODAY = date(2026, 10, 23)


def _stock(ticker, name, share_class=None):
    s = {"ticker": ticker, "name": name, "isin": ""}
    if share_class:
        s["share_class"] = share_class
    return s


def _info(country, value, shares=1e9, volume=1e5, **kw):
    return {"country": country, "traded_value_eur": value, "sharesOutstanding": shares,
            "averageVolume": volume, **kw}


def _choose(stocks, info, choices=None, today=TODAY, suffixes=None):
    return universe.choose_primary_lines(stocks, info, choices=choices or {},
                                         enabled_suffixes=suffixes, today=today)


def test_european_company_on_another_countrys_exchange_is_back():
    # F8: Airbus is Dutch and trades in Paris, Frankfurt and Madrid.
    stocks = [_stock("AIR.PA", "Airbus SE"), _stock("AIR.DE", "Airbus SE"), _stock("AIR.MC", "Airbus SE")]
    info = {"AIR.PA": _info("Netherlands", 200e6), "AIR.DE": _info("Netherlands", 40e6),
            "AIR.MC": _info("Netherlands", 5e6)}
    c = _choose(stocks, info, suffixes={".PA", ".DE", ".MC"})
    assert [s["ticker"] for s in c.kept] == ["AIR.PA"]
    assert c.excluded == {"AIR.DE": "secondary_listing", "AIR.MC": "secondary_listing"}
    assert c.choices["airbus|Netherlands|"]["chosen"] == "AIR.PA"


def test_home_line_wins_over_more_traded_lines_and_is_fixed():
    stocks = [_stock("NESN.SW", "Nestlé S.A."), _stock("NESR.DE", "Nestlé S.A.")]
    info = {"NESN.SW": _info("Switzerland", 1e6), "NESR.DE": _info("Switzerland", 9e9)}
    c = _choose(stocks, info)
    assert [s["ticker"] for s in c.kept] == ["NESN.SW"]
    assert c.choices["nestle|Switzerland|"]["reason"] == "home"


def test_non_european_lines_out_except_the_allow_list():
    stocks = [_stock("APC.DE", "Apple Inc."), _stock("1AAPL.MI", "Apple Inc."),
              _stock("HAFNI.OL", "Hafnia Limited")]
    info = {"APC.DE": _info("United States", 1e8), "1AAPL.MI": _info("United States", 1e6),
            "HAFNI.OL": _info("Singapore", 2e7)}
    c = _choose(stocks, info)
    assert [s["ticker"] for s in c.kept] == ["HAFNI.OL"]
    assert c.excluded == {"APC.DE": "not_european", "1AAPL.MI": "not_european"}
    assert universe.known_foreign("APC.DE", "United States")
    assert not universe.known_foreign("AIR.DE", "Netherlands")   # fetched: may be primary
    assert not universe.known_foreign("HAFNI.OL", "Singapore")


def test_d3_crown_dependencies_count_as_europe():
    assert universe.is_european("GLEN.L", "Jersey")
    assert not universe.is_european("X.OL", "Bermuda")


def test_every_left_out_line_has_a_reason():
    stocks = [_stock("A.PA", "A"), _stock("B.PA", "B"), _stock("C.PA", "C"), _stock("D.PA", "D")]
    info = {"A.PA": _info("France", 1e6, volume=0), "B.PA": _info(None, 1e6),
            "C.PA": _info("France", 1e6, quoteType="ETF"), "D.PA": _info("France", 1e6)}
    c = _choose(stocks, info)
    assert c.excluded == {"A.PA": "dormant", "B.PA": "country_unknown", "C.PA": "fund"}
    assert set(c.excluded.values()) <= set(universe.REASONS)
    assert c.counts() == {".PA": {"dormant": 1, "country_unknown": 1, "fund": 1}}


def test_share_classes_both_kept():
    stocks = [_stock("VOLV-A.ST", "AB Volvo (publ)", "A"), _stock("VOLV-B.ST", "AB Volvo (publ)", "B")]
    info = {"VOLV-A.ST": _info("Sweden", 1e6, shares=4.5e8), "VOLV-B.ST": _info("Sweden", 1e8, shares=1.6e9)}
    assert {s["ticker"] for s in _choose(stocks, info).kept} == {"VOLV-A.ST", "VOLV-B.ST"}


def test_different_share_counts_are_not_merged():
    stocks = [_stock("X.PA", "Same Name SA"), _stock("X.MI", "Same Name S.p.A.")]
    info = {"X.PA": _info("Belgium", 1e6, shares=1e8), "X.MI": _info("Belgium", 2e6, shares=3e8)}
    assert {s["ticker"] for s in _choose(stocks, info).kept} == {"X.PA", "X.MI"}


def test_disabled_exchange_uses_the_next_line_and_keeps_the_record():
    # EX-6: Shell's saved line is on an exchange switched off for now.
    saved = {"shell|United Kingdom|": {"chosen": "SHEL.L", "lines": ["SHEL.L", "SHELL.AS"],
                                        "reason": "home", "since": "2026-10-01"}}
    stocks = [_stock("SHELL.AS", "Shell plc")]
    c = _choose(stocks, {"SHELL.AS": _info("United Kingdom", 1e8)}, choices=saved, suffixes={".AS"})
    assert [s["ticker"] for s in c.kept] == ["SHELL.AS"]
    assert c.choices["shell|United Kingdom|"]["chosen"] == "SHEL.L"


def test_the_chosen_line_switches_only_after_two_checks_a_week_apart():
    # A3: STMicro trades about as much in Paris as in Milan.
    stocks = [_stock("STMPA.PA", "STMicroelectronics N.V."), _stock("STMMI.MI", "STMicroelectronics N.V.")]
    key = "stmicroelectronics|Netherlands|"
    close = {"STMPA.PA": _info("Netherlands", 100e6), "STMMI.MI": _info("Netherlands", 150e6)}
    c = _choose(stocks, close)
    assert c.choices[key]["chosen"] == "STMMI.MI"
    flipped = {"STMPA.PA": _info("Netherlands", 160e6), "STMMI.MI": _info("Netherlands", 150e6)}
    c = _choose(stocks, flipped, choices=c.choices)
    assert c.choices[key]["chosen"] == "STMMI.MI" and not c.switches   # not 2x more: stays

    much = {"STMPA.PA": _info("Netherlands", 400e6), "STMMI.MI": _info("Netherlands", 150e6)}
    c = _choose(stocks, much, choices=c.choices)
    assert c.choices[key]["chosen"] == "STMMI.MI" and c.choices[key]["challenger"] == "STMPA.PA"
    c = _choose(stocks, much, choices=c.choices, today=TODAY + timedelta(days=3))
    assert c.choices[key]["chosen"] == "STMMI.MI"                     # too soon
    c = _choose(stocks, much, choices=c.choices, today=TODAY + timedelta(days=7))
    assert c.choices[key]["chosen"] == "STMPA.PA"
    assert c.switches == [("STMMI.MI", "STMPA.PA")]


def test_a_challenge_that_fades_is_forgotten():
    stocks = [_stock("MT.AS", "ArcelorMittal S.A."), _stock("MT.PA", "ArcelorMittal S.A.")]
    key = "arcelormittal|Luxembourg|"
    saved = {key: {"chosen": "MT.AS", "lines": ["MT.AS", "MT.PA"], "reason": "most_traded",
                   "since": "2026-10-01", "challenger": "MT.PA", "challenger_since": "2026-10-10"}}
    info = {"MT.AS": _info("Luxembourg", 100e6), "MT.PA": _info("Luxembourg", 120e6)}
    c = _choose(stocks, info, choices=saved)
    assert "challenger" not in c.choices[key] and c.choices[key]["chosen"] == "MT.AS"


def test_choices_roundtrip_and_secondary_lines():
    stocks = [_stock("AIR.PA", "Airbus SE"), _stock("AIR.DE", "Airbus SE")]
    info = {"AIR.PA": _info("Netherlands", 200e6), "AIR.DE": _info("Netherlands", 40e6)}
    universe.save_choices(_choose(stocks, info).choices)
    assert universe.secondary_lines() == {"AIR.DE"}
    assert universe.secondary_lines_cached() == {"AIR.DE"}


def test_founder_holding_on_a_secondary_line_discloses_on_the_chosen_line():
    # P1: held as AIR.DE, shown as AIR.PA.
    choices = {"airbus|Netherlands|": {"chosen": "AIR.PA", "lines": ["AIR.DE", "AIR.PA"]}}
    assert universe.company_lines({"AIR.DE"}, choices) == {"AIR.DE", "AIR.PA"}
    assert universe.company_lines({"SAP.DE"}, choices) == {"SAP.DE"}


def test_normalised_names():
    assert universe.normalise_name("Stellantis N.V.") == universe.normalise_name("STELLANTIS NV")
    assert universe.normalise_name("Nestlé S.A.") == "nestle"
    assert universe.normalise_name("AB Volvo (publ)") == "volvo"


def test_thin_cross_lines_wait_for_the_home_exchange():
    # HSBC (UK) only on Xetra while London is planned: below the floor it
    # stays out; Medtronic (Ireland, US primary) on two thin lines stays out.
    stocks = [_stock("IJ8.DE", "ITM Power PLC"), _stock("HBC1.DE", "HSBC Holdings plc"),
              _stock("2M6.DE", "Medtronic plc"), _stock("1MDT.MI", "Medtronic plc")]
    info = {"IJ8.DE": _info("United Kingdom", 170e3), "HBC1.DE": _info("United Kingdom", 4.6e6),
            "2M6.DE": _info("Ireland", 130e3), "1MDT.MI": _info("Ireland", 20e3)}
    c = _choose(stocks, info, suffixes={".DE", ".MI"})
    assert [s["ticker"] for s in c.kept] == ["HBC1.DE"]
    assert c.excluded == {"IJ8.DE": "secondary_listing", "2M6.DE": "secondary_listing",
                          "1MDT.MI": "secondary_listing"}


def test_only_line_without_a_home_exchange_needs_no_floor():
    # Solutions 30 (Luxembourg: no exchange in the registry), Onward Medical
    # (Netherlands: Amsterdam enabled, not listed there).
    stocks = [_stock("S30.PA", "Solutions 30 SE"), _stock("ONWD.BR", "Onward Medical N.V.")]
    info = {"S30.PA": _info("Luxembourg", 180e3), "ONWD.BR": _info("Netherlands", 320e3)}
    c = _choose(stocks, info, suffixes={".PA", ".BR", ".AS"})
    assert {s["ticker"] for s in c.kept} == {"S30.PA", "ONWD.BR"}


def test_preference_shares_on_one_exchange_are_not_merged_but_second_lines_are_out():
    stocks = [_stock("SRT.DE", "Sartorius AG"), _stock("SRT3.DE", "Sartorius AG"),
              _stock("ABBN.SW", "ABB Ltd"), _stock("ABBNE.SW", "ABB Ltd")]
    info = {"SRT.DE": _info("Germany", 1e6), "SRT3.DE": _info("Germany", 50e6),
            "ABBN.SW": _info("Switzerland", 200e6), "ABBNE.SW": _info("Switzerland", 1e3, Name="ABB LTD N 2. LINIE")}
    c = _choose(stocks, info)
    assert {s["ticker"] for s in c.kept} == {"SRT.DE", "SRT3.DE", "ABBN.SW"}
    assert c.excluded == {"ABBNE.SW": "secondary_listing"}


def test_milan_global_equity_market_lines_are_secondary():
    stocks = [_stock("1G.MI", "GEA Group AG"), _stock("1BSP.MI", "Bending Spoons")]
    info = {"1G.MI": _info("Germany", 3e6), "1BSP.MI": _info("Italy", 2e6)}
    c = _choose(stocks, info, suffixes={".MI", ".DE"})
    assert not c.kept
    assert c.excluded == {"1G.MI": "secondary_listing", "1BSP.MI": "secondary_listing"}


def test_us_primary_companies_registered_in_europe_stay_out():
    # Chubb (Switzerland) and Ferrovial (Netherlands, primary Madrid) on a thin Xetra line.
    stocks = [_stock("AEX.DE", "Chubb Limited"), _stock("8ZQ.DE", "Ferrovial SE")]
    info = {"AEX.DE": _info("Switzerland", 300e3), "8ZQ.DE": _info("Netherlands", 50e3)}
    c = _choose(stocks, info, suffixes={".DE", ".SW", ".AS"})
    assert not c.kept
    assert set(c.excluded.values()) == {"secondary_listing"}


def test_a_planned_exchange_line_is_home_when_enabled():
    # Shadow build: a small Helsinki company on its own exchange is home,
    # not a secondary line held to the EUR 1M floor.
    stocks = [_stock("ASPO.HE", "Aspo Oyj")]
    c = _choose(stocks, {"ASPO.HE": _info("Finland", 50e3)}, suffixes={".HE"})
    assert [s["ticker"] for s in c.kept] == ["ASPO.HE"]
