"""Unit tests for uvalu/store.py — the off-thread scored-universe store (WP-5).

The store hands pages the last successfully computed 7-tuple immediately and
recomputes on a background daemon thread when the fundamentals-cache token
moves. These tests drive it with a fake builder (no real scoring / HTTP).
"""
import threading
import time

import pandas as pd

from uvalu import store as store_mod
from uvalu.store import _UniverseStore


def _wait(pred, timeout=3.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def _frame(tag: str) -> tuple:
    return tuple(pd.DataFrame({"Ticker": [f"{tag}{i}"]}) for i in range(7))


class TestUniverseStore:
    def test_cold_get_serves_empty_and_kicks_worker(self):
        s = _UniverseStore()
        built = []
        frame, version, is_stale = s.get(("k",), "t1", lambda: built.append(1) or _frame("a"))
        assert version == 0 and is_stale is True
        assert all(d.empty for d in frame)                      # the empty placeholder
        assert _wait(lambda: s._entries[("k",)]["version"] == 1)
        assert built == [1]

    def test_get_after_build_serves_the_built_frame(self):
        s = _UniverseStore()
        s.get(("k",), "t1", lambda: _frame("a"))
        assert _wait(lambda: s._entries[("k",)]["version"] == 1)
        frame, version, is_stale = s.get(("k",), "t1", lambda: _frame("b"))
        assert version == 1 and is_stale is False
        assert frame[0].iloc[0]["Ticker"] == "a0"               # not rebuilt

    def test_new_token_triggers_a_rebuild(self):
        s = _UniverseStore()
        s.get(("k",), "t1", lambda: _frame("a"))
        assert _wait(lambda: s._entries[("k",)]["version"] == 1)
        s._entries[("k",)]["attempt_at"] = 0.0                  # skip the interval guard
        s.get(("k",), "t2", lambda: _frame("b"))
        assert _wait(lambda: s._entries[("k",)]["version"] == 2)
        assert s.get(("k",), "t2", lambda: _frame("c"))[0][0].iloc[0]["Ticker"] == "b0"

    def test_min_interval_blocks_an_immediate_respawn(self):
        s = _UniverseStore()
        calls = []
        s.get(("k",), "t1", lambda: calls.append(1) or _frame("a"))
        assert _wait(lambda: s._entries[("k",)]["version"] == 1)
        s.get(("k",), "t2", lambda: calls.append(1) or _frame("b"))   # < _MIN_RECOMPUTE_INTERVAL_S
        time.sleep(0.1)
        assert calls == [1]

    def test_builder_exception_leaves_the_previous_frame(self):
        s = _UniverseStore()
        def boom():
            raise RuntimeError("nope")
        s.get(("k",), "t1", boom)
        assert _wait(lambda: not s._entries[("k",)]["thread"].is_alive())
        assert s._entries[("k",)]["version"] == 0
        assert all(d.empty for d in s._entries[("k",)]["frame"])

    def test_recomputing_reflects_a_live_worker(self):
        s = _UniverseStore()
        gate = threading.Event()
        s.get(("k",), "t1", lambda: gate.wait(2.0) or _frame("a"))
        assert _wait(s.recomputing)
        gate.set()
        assert _wait(lambda: not s.recomputing())

    def test_clear_drops_all_entries(self):
        s = _UniverseStore()
        s.get(("k",), "t1", lambda: _frame("a"))
        assert _wait(lambda: s._entries[("k",)]["version"] == 1)
        s.clear()
        assert s._entries == {}

    def test_version_sums_per_key_frame_versions(self):
        s = _UniverseStore()
        assert s.version() == 0
        s.get(("k",), "t1", lambda: _frame("a"))
        assert _wait(lambda: s.version() == 1)
        s._entries[("k",)]["attempt_at"] = 0.0
        s.get(("k",), "t2", lambda: _frame("b"))
        assert _wait(lambda: s.version() == 2)


class TestGetScoredUniverse:
    def test_serves_copies_the_caller_can_mutate(self, monkeypatch):
        store_mod._STORE.clear()
        monkeypatch.setattr("uvalu.data._build_all_screener_data", lambda *a, **k: _frame("x"))
        from uvalu.store import get_scored_universe

        assert _wait(lambda: get_scored_universe(("brussels",), token="t1")[1] == 1)
        frame, _v, _s = get_scored_universe(("brussels",), token="t1")
        frame[0].loc[0, "Ticker"] = "MUTATED"
        frame2, _v2, _s2 = get_scored_universe(("brussels",), token="t1")
        assert frame2[0].iloc[0]["Ticker"] == "x0"

    def test_default_token_comes_from_cache_version(self, monkeypatch):
        store_mod._STORE.clear()
        monkeypatch.setattr("uvalu.data._cache_version", lambda: "tok-xyz")
        monkeypatch.setattr("uvalu.data._build_all_screener_data", lambda *a, **k: _frame("y"))
        from uvalu.store import get_scored_universe

        get_scored_universe(("brussels",))                       # no explicit token
        assert _wait(lambda: get_scored_universe(("brussels",))[2] is False)  # is_stale clears

    def test_clear_scored_universe_forces_a_rebuild(self, monkeypatch):
        store_mod._STORE.clear()
        seen = []
        monkeypatch.setattr("uvalu.data._build_all_screener_data",
                            lambda *a, **k: seen.append(1) or _frame("z"))
        from uvalu.store import get_scored_universe, clear_scored_universe

        assert _wait(lambda: get_scored_universe(("brussels",), token="t1")[1] == 1)
        assert seen == [1]
        clear_scored_universe()
        assert _wait(lambda: get_scored_universe(("brussels",), token="t1")[1] == 1)
        assert seen == [1, 1]
