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
        assert "wig20" not in keys                      # nothing in it yet
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
