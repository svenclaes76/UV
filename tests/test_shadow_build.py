"""tools/shadow_build.py: the report helpers (no network, no fetch)."""
import json

import pandas as pd

from tools import shadow_build as sb


def _scored(rows):
    return pd.DataFrame([{"Ticker": t, "signal_code": s, "fair_value": fv, "trailingPE": pe,
                          "data_flags": flags} for t, s, fv, pe, flags in rows])


def test_exchange_and_region():
    assert sb.exchange_key("AIR.PA") == "paris"
    assert sb.exchange_key("VOLV-B.ST") == "stockholm"
    assert sb.region_of("stockholm") == "Nordics"
    assert sb.region_of("london") == "UK & Ireland"
    assert sb.region_of("warsaw") == "Southern & Central Europe"


def test_exchange_stats_and_go_no_go():
    scored = _scored([
        ("A.PA", "undervalued", 10.0, 12.0, []),
        ("B.PA", "neutral", 10.0, 14.0, []),
        ("C.ST", "undervalued", None, None, ["currency_unverified"]),
        ("D.ST", "pending", None, None, []),
    ])
    stats = sb.exchange_stats(scored, {"paris": 3, "stockholm": 5}, {"X.PA": "dormant"})
    assert stats["paris"]["in_universe"] == 2 and stats["paris"]["fair_value"] == 1.0
    assert stats["paris"]["excluded"] == {"dormant": 1} and stats["paris"]["median_pe"] == 13.0
    assert stats["stockholm"]["currency_unverified"] == 0.5
    go = sb.go_no_go(stats, universe_undervalued=0.1)
    assert go["paris"]["go"] is True             # 50% > 3 x 10%, but only 1 Undervalued stock (< 5)
    assert any("fair value" in f for f in go["stockholm"]["fails"])
    assert any("currency_unverified" in f for f in go["stockholm"]["fails"])


def test_london_needs_the_golden_sample():
    stats = {"london": {"in_universe": 10, "fair_value": 0.9, "currency_unverified": 0.0, "undervalued": 0.05}}
    assert sb.go_no_go(stats, 0.05, golden_ok=None)["london"]["go"] is False
    assert sb.go_no_go(stats, 0.05, golden_ok=True)["london"]["go"] is True


def test_golden_sample_checks_pe_against_net_income_and_fair_value():
    # V7: Yahoo's P/E (11.9) is not the reference; price / net income per share is.
    scored = pd.DataFrame([
        {"Ticker": "SHEL.L", "Price": 40.33, "trailingEps": 2.54, "fair_value": 30.0,
         "sharesOutstanding": 5.684e9, "netIncomeHistory": [13.38e9, 12.0e9]},
        {"Ticker": "BP.L", "Price": 4.0, "trailingEps": 0.4, "fair_value": 40.0,
         "sharesOutstanding": 1e9, "netIncomeHistory": [0.4e9]},
        {"Ticker": "HSBA.L", "Price": 9.0, "trailingEps": 0.7, "fair_value": 10.0,
         "sharesOutstanding": 1e9, "netIncomeHistory": [0.7e9 * 0.75]}])      # EPS left in USD
    raw = pd.DataFrame([{"Ticker": "SHEL.L", "trailingPE": 11.93}, {"Ticker": "BP.L", "trailingPE": 10.0}])
    g = sb.golden_sample(scored, raw)
    assert g["rows"]["SHEL.L"]["ok"] is True and g["rows"]["SHEL.L"]["yahoo_pe"] == 11.93
    assert g["rows"]["BP.L"]["ok"] is False      # fair value 10x the price
    assert g["rows"]["HSBA.L"]["ok"] is False    # P/E off by the USD/GBP rate
    assert g["ok"] is False and "GLEN.L" in g["missing"]


def test_signal_changes_and_peer_group():
    assert sb.signal_changes({"A.PA": "neutral", "B.ST": "low_score", "N.PA": "neutral"},
                             {"A.PA": "undervalued", "B.ST": "low_score"}) == {"paris": 1}
    six = pd.DataFrame({"Ticker": ["A.PA", "B.PA"], "signal_code": ["undervalued", "neutral"]})
    full = pd.DataFrame({"Ticker": ["A.PA", "B.PA", "C.ST"], "signal_code": ["neutral", "neutral", "neutral"]})
    pg = sb.peer_group_effect(full, six)
    assert pg == {"stocks": 2, "changed": 1, "moves": {"undervalued -> neutral": 1}}


def test_regional_tilt_flags_a_market_above_3x():
    rt = sb.regional_tilt({"paris": 0.02, "milan": 0.02, "athens": 0.02, "warsaw": 0.30}, {"warsaw": 0.05})
    assert rt["flagged"] == ["warsaw"]
    assert rt["by_exchange"]["warsaw"] == {"pooled": 0.3, "regional": 0.05}


def test_seed_copies_only_newer_rows(tmp_path):
    app, mine = tmp_path / "app.json", tmp_path / "shadow" / "f.json"
    app.write_text(json.dumps({"A.PA": {"fetched_at": "2026-10-23"}, "B.PA": {"fetched_at": "2026-10-01"}}))
    mine.parent.mkdir()
    mine.write_text(json.dumps({"B.PA": {"fetched_at": "2026-10-20"}, "C.ST": {"fetched_at": "2026-10-22"}}))
    assert sb.seed_from_app(mine, app) == 1
    data = json.loads(mine.read_text())
    assert data["A.PA"]["fetched_at"] == "2026-10-23" and data["B.PA"]["fetched_at"] == "2026-10-20"
    assert "C.ST" in data


def test_markdown_and_summary(tmp_path):
    report = {"date": "2026-10-24", "model_version": "M5", "universe": 2, "universe_undervalued": 0.5,
              "fetch": "none", "exchanges": {"paris": {"listed": 3, "in_universe": 2, "fair_value": 1.0,
                                                       "currency_unverified": 0.0, "rate_missing": 0.0,
                                                       "median_pe": 13.0, "undervalued": 0.5, "signals": {}}},
              "go_no_go": {"paris": {"go": True, "fails": []}}, "changes": {"paris": 1},
              "peer_group": {"stocks": 2, "changed": 0, "moves": {}},
              "regional": {"average": 0.5, "flagged": [], "by_exchange": {"paris": {"pooled": 0.5, "regional": 0.4}}},
              "golden": {"ok": None, "rows": {}, "missing": []}}
    md = sb.render_markdown(report)
    assert "| paris | 3 | 2 | 100% |" in md and "not checked" in md
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "2026-10-24.json").write_text(json.dumps(report))
    assert "| paris | 50.0% · 1 | yes |" in sb.summary(tmp_path)


def test_the_3x_rule_needs_five_undervalued_stocks():
    one = {"dublin": {"in_universe": 20, "fair_value": 1.0, "currency_unverified": 0.0,
                      "undervalued": 0.05, "signals": {"undervalued": 1}}}
    assert sb.go_no_go(one, 0.014)["dublin"]["go"] is True
    five = {"brussels": {"in_universe": 100, "fair_value": 1.0, "currency_unverified": 0.0,
                         "undervalued": 0.05, "signals": {"undervalued": 5}}}
    assert sb.go_no_go(five, 0.014)["brussels"]["go"] is False
    assert sb.regional_tilt({"a": 0.01, "b": 0.01, "c": 0.2}, {}, {"c": 1})["flagged"] == []
