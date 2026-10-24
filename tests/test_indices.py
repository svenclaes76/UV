"""EX-W9: the index-member snapshot, uvalu/indices.py and the offline parts of
tools/refresh_index_members.py (no network)."""
import importlib.util
import json
from pathlib import Path

import pytest

from uvalu import exchanges, indices

ROOT = Path(__file__).resolve().parent.parent


def _tool():
    spec = importlib.util.spec_from_file_location("refresh_index_members",
                                                  ROOT / "tools" / "refresh_index_members.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSnapshot:
    def test_note_forbids_backtests(self):
        """Model review M9: today's members only, never a backtest."""
        note = json.loads(indices.SNAPSHOT.read_text(encoding="utf-8"))["_note"]
        assert "backtest" in note and "not point-in-time" in note

    def test_every_index_of_d7_is_there(self):
        data = json.loads(indices.SNAPSHOT.read_text(encoding="utf-8"))["indices"]
        assert set(data) == set(_tool().INDICES)
        assert len(data) == 21

    def test_entries_are_complete(self):
        data = json.loads(indices.SNAPSHOT.read_text(encoding="utf-8"))["indices"]
        for key, entry in data.items():
            assert entry["name"] and entry["owner"] and entry["source_url"].startswith("https://"), key
            assert entry["status"] in ("ok", "check", "to_fill"), key
            if entry["status"] == "to_fill":
                continue
            assert entry["as_of"] and entry["members"], key
            if entry["status"] == "ok" and entry.get("size"):
                assert len(entry["members"]) == entry["size"], key

    def test_every_member_is_a_known_exchange_line(self):
        for key in indices.keys():
            for m in indices.members(key):
                assert exchanges.for_ticker(m["ticker"]), (key, m["ticker"])
                assert "[" not in m["ticker"] and "[" not in m["name"], (key, m)   # no footnote marks


class TestLookups:
    def test_display_order_starts_with_the_stoxx_indices(self):
        keys = indices.keys()
        assert keys[:2] == ["euro_stoxx_50", "stoxx_europe_50"]
        assert "wig20" in keys and "omx_baltic_benchmark" in keys   # filled 24 Oct 2026 (EX8)
        rest = [indices.name(k).lower() for k in keys[2:]]
        assert rest == sorted(rest)

    def test_a_company_in_several_indices(self):
        """Airbus, a Dutch company on Paris, is in the DAX and the CAC 40 (EX-26)."""
        found = indices.indices_for("AIR.PA")
        assert {"euro_stoxx_50", "stoxx_europe_50", "cac_40", "dax"} <= set(found)
        assert indices.indices_for("NOT.A.MEMBER") == []

    def test_fallback_is_the_members_on_one_exchange(self):
        stocks = indices.fallback_stocks("cac_40", ".PA", "XPAR")
        assert all(s["ticker"].endswith(".PA") and s["mic"] == "XPAR" for s in stocks)
        assert "MT.AS" in indices.tickers("cac_40") and "MT.AS" not in {s["ticker"] for s in stocks}

    def test_names_and_dates(self):
        assert indices.name("euro_stoxx_50") == "EURO STOXX 50"
        assert indices.as_of("dax")
        assert indices.name("unknown") == "unknown"


class TestRefreshTool:
    @pytest.mark.parametrize("raw, suffix, ticker", [
        ("OSE: EQNR", ".OL", "EQNR.OL"),
        ("Euronext Dublin:\xa0A5G", ".IR", "A5G.IR"),
        ("MAERSK B", ".CO", "MAERSK-B.CO"),
        ("BT.A", ".L", "BT-A.L"),
        ("AIR.PA", ".DE", "AIR.PA"),          # a member listed elsewhere keeps its own suffix
        ("TITC[6]", ".AT", "TITC.AT"),        # Wikipedia footnote mark
        ("nan", ".SW", None),
    ])
    def test_to_yahoo(self, raw, suffix, ticker):
        assert _tool()._to_yahoo(raw, suffix) == ticker

    def test_fold_ignores_accents_quotes_and_legal_forms(self):
        tool = _tool()
        assert tool._fold("L’Oréal") == tool._fold("L'Oréal S.A.")
        assert tool._fold("Nestlé SA") == "nestle"

    def test_name_match_prefers_exact_then_the_home_exchange(self, monkeypatch):
        tool = _tool()
        monkeypatch.setattr(tool, "_RESOLVED", [
            {"ticker": "ENR.DE", "name": "Siemens Energy"}, {"ticker": "SIE.DE", "name": "Siemens"},
            {"ticker": "ABB.ST", "name": "ABB Ltd"}, {"ticker": "ABBN.SW", "name": "ABB Ltd"},
        ])
        assert tool._match_name("Siemens", "Germany")[0] == "SIE.DE"      # exact beats prefix
        assert tool._match_name("ABB", "Switzerland")[0] == "ABBN.SW"    # the home line
        assert tool._match_name("Münchener Rück", "Germany") == ("MUV2.DE", "manual fix")


# ── EX-W10: matching by company, tags ───────────────────────────────────────

@pytest.fixture
def _snapshot(tmp_path, monkeypatch):
    snap = tmp_path / "index_members.json"
    snap.write_text(json.dumps({"indices": {
        "euro_stoxx_50": {"name": "EURO STOXX 50", "as_of": "2026-09-30",
                          "members": [{"ticker": "AIR.PA", "name": "Airbus"}, {"ticker": "SAP.DE", "name": "SAP"}]},
        "dax": {"name": "DAX", "as_of": "2026-09-30",
                "members": [{"ticker": "AIR.DE", "name": "Airbus"}, {"ticker": "SAP.DE", "name": "SAP"},
                            {"ticker": "GONE.DE", "name": "Delisted"}]},
        "cac_40": {"name": "CAC 40", "as_of": "2026-09-30", "members": [{"ticker": "AIR.PA", "name": "Airbus"}]},
    }}), encoding="utf-8")
    monkeypatch.setattr(indices, "SNAPSHOT", snap)
    indices._data.cache_clear()
    yield
    indices._data.cache_clear()


def test_members_match_the_chosen_line_by_company(_snapshot):
    # EX-26: Airbus is a DAX member as AIR.DE; the universe shows AIR.PA.
    from datetime import date
    choices = {"airbus|Netherlands|": {"chosen": "AIR.PA", "lines": ["AIR.DE", "AIR.PA"]}}
    m = indices.match_universe({"AIR.PA", "SAP.DE"}, choices, today=date(2026, 10, 24))
    assert m.by_ticker["AIR.PA"] == ["euro_stoxx_50", "cac_40"] and m.by_ticker["SAP.DE"] == ["euro_stoxx_50"]
    assert m.unmatched == {"dax": ["GONE.DE"]}
    # The quality gate: 2 of 3 DAX members matched, under 90%, so no DAX tags.
    assert m.checks["dax"].visible is False and "2 of 3" in m.checks["dax"].reason


def test_a_renamed_member_matches_by_its_aka_name(_snapshot, monkeypatch):
    import json as _json
    from datetime import date
    snap = indices.SNAPSHOT
    d = _json.loads(snap.read_text(encoding="utf-8"))
    d["indices"]["omxh25"] = {"name": "OMX Helsinki 25", "as_of": "2026-09-30",
                             "members": [{"ticker": "KOJAMO.HE", "name": "Kojamo Oyj", "aka": ["Lumo Kodit"]}]}
    snap.write_text(_json.dumps(d), encoding="utf-8")
    indices._data.cache_clear()
    m = indices.match_universe({"LUMO.HE"}, {}, names={"LUMO.HE": "Lumo Kodit Oyj"}, today=date(2026, 10, 24))
    assert m.by_ticker == {"LUMO.HE": ["omxh25"]} and m.checks["omxh25"].visible


def test_a_stale_index_is_hidden(_snapshot):
    import json as _json
    from datetime import date
    d = _json.loads(indices.SNAPSHOT.read_text(encoding="utf-8"))
    d["indices"]["cac_40"]["review"] = {"months": [3, 6, 9, 12], "day": "third_friday"}
    d["indices"]["cac_40"]["as_of"] = "2026-07-01"          # after June's review, before the 18 Sep 2026 one
    indices.SNAPSHOT.write_text(_json.dumps(d), encoding="utf-8")
    indices._data.cache_clear()
    assert indices.review_dates("cac_40", 2026)[2] == date(2026, 9, 18)
    # Within the 30-day grace after the review the index still shows ...
    assert not indices.is_stale("cac_40", date(2026, 10, 10))
    # ... after it, it is hidden until its members are checked again.
    m = indices.match_universe({"AIR.PA"}, {}, today=date(2026, 10, 24))
    assert m.checks["cac_40"].stale and not m.checks["cac_40"].visible
    assert "cac_40" not in m.by_ticker.get("AIR.PA", [])


def test_an_index_with_no_member_on_an_enabled_exchange_is_hidden_quietly(_snapshot):
    from datetime import date
    m = indices.match_universe({"SAP.DE"}, {}, enabled_suffixes={".DE"}, today=date(2026, 10, 24))
    assert m.checks["cac_40"].expected == 0 and not m.checks["cac_40"].visible


def test_index_tags_show_two_and_the_rest_in_a_tooltip(_snapshot):
    from uvalu.components import index_tags_html
    html = index_tags_html(["euro_stoxx_50", "cac_40", "dax"])
    assert "EURO STOXX 50" in html and "CAC 40" in html and ">+1 more<" in html
    assert 'title="DAX"' in html and 'role="list"' in html
    assert index_tags_html([]) == "" and index_tags_html(None) == ""


def test_national_index_members_give_a_home_country_hint(_snapshot):
    # Michelin had no country from the provider and was left out; a CAC 40
    # member on Paris is French. The pan-European STOXX indices give no hint.
    hints = indices.home_country_hints()
    assert hints["AIR.PA"] == "France" and hints["AIR.DE"] == "Germany"
    assert "SAP.DE" in hints                     # via the DAX
    assert all(k in hints for k in ("GONE.DE",))


def test_members_left_out_on_purpose_do_not_count_against_an_index(_snapshot):
    # JBT Marel (OMX Iceland 15) has its primary listing in New York: our
    # coverage leaves it out by design, so it must not hide the index.
    from datetime import date
    m = indices.match_universe({"SAP.DE"}, {}, today=date(2026, 10, 24), enabled_suffixes={".DE"},
                               excluded={"AIR.DE": "secondary_listing", "GONE.DE": "not_european"})
    assert m.checks["dax"].expected == 1 and m.checks["dax"].visible
    # A data gap (dormant, no country) still counts.
    m = indices.match_universe({"SAP.DE"}, {}, today=date(2026, 10, 24), enabled_suffixes={".DE"},
                               excluded={"AIR.DE": "dormant", "GONE.DE": "country_unknown"})
    assert m.checks["dax"].expected == 3 and not m.checks["dax"].visible
