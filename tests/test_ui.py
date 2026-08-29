"""Tests for uvalu/ui.py — static Plotly charts, donut breakdown, treemap
color mapping, click-to-select dataframe, and the timed auto-rerun helper."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from uvalu import ui


# ── _hm_color (pure) ──────────────────────────────────────────────────────

class TestHmColor:
    def test_positive_end_is_mint(self):
        assert ui._hm_color(1.0) == "rgb(29,214,164)"

    def test_negative_end_is_danger_red(self):
        assert ui._hm_color(-1.0) == "rgb(163,45,45)"

    def test_zero_is_surface_color(self):
        # Falls back to the dark-theme zero point when no real theme is set.
        result = ui._hm_color(0.0)
        assert result.startswith("rgb(")

    def test_interpolates_between_zero_and_end(self):
        full = ui._hm_color(1.0)
        half = ui._hm_color(0.5)
        assert half != full


# ── _static_bar ────────────────────────────────────────────────────────────

def _run(fn) -> AppTest:
    at = AppTest.from_function(fn, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


class TestStaticBar:
    def test_renders_chart_for_valid_series(self):
        def _script():
            import pandas as pd
            from uvalu.ui import _static_bar
            _static_bar(pd.Series({"Tech": 10.0, "Health": -5.0}), title="Sectors")

        at = _run(_script)
        assert len(at.get("plotly_chart")) == 1

    def test_filters_bad_index_labels_without_crashing(self):
        def _script():
            import pandas as pd
            from uvalu.ui import _static_bar
            _static_bar(pd.Series({"Tech": 10.0, "": 5.0, "nan": 3.0, "None": 2.0}))

        at = _run(_script)
        assert len(at.get("plotly_chart")) == 1

    def test_empty_after_filtering_renders_nothing(self):
        def _script():
            import pandas as pd
            import streamlit as st
            from uvalu.ui import _static_bar
            _static_bar(pd.Series({"": 5.0, "nan": 3.0}))
            st.text("done")

        at = _run(_script)
        assert len(at.get("plotly_chart")) == 0
        assert at.text[0].value == "done"

    def test_all_nan_values_renders_nothing(self):
        def _script():
            import pandas as pd
            import streamlit as st
            from uvalu.ui import _static_bar
            _static_bar(pd.Series({"Tech": float("nan")}))
            st.text("done")

        at = _run(_script)
        assert len(at.get("plotly_chart")) == 0


# ── _donut_chart ───────────────────────────────────────────────────────────

class TestDonutChart:
    def test_shows_info_when_empty(self):
        def _script():
            import pandas as pd
            from uvalu.ui import _donut_chart
            _donut_chart(pd.Series(dtype=float))

        at = _run(_script)
        assert "No data available" in "".join(i.value for i in at.info)

    def test_shows_info_when_only_bad_or_nonpositive_values(self):
        def _script():
            import pandas as pd
            from uvalu.ui import _donut_chart
            _donut_chart(pd.Series({"Unknown": 0.0, "n/a": 5.0, "": 3.0}))

        at = _run(_script)
        assert "No data available" in "".join(i.value for i in at.info)

    def test_renders_chart_for_valid_series(self):
        def _script():
            import pandas as pd
            from uvalu.ui import _donut_chart
            _donut_chart(pd.Series({"Technology": 700.0, "Healthcare": 300.0}))

        at = _run(_script)
        assert len(at.get("plotly_chart")) == 1


# ── _row_select_table ──────────────────────────────────────────────────────

class TestRowSelectTable:
    # AppTest's Dataframe element is read-only (a plain Element, not a
    # Widget subclass — confirmed in streamlit's own element_tree.py, no
    # set_value/select_row or similar) — it has no API to simulate a row
    # click, so only the "nothing selected yet" branch is reachable here.
    # The nonce-increment/selected-row branches need a real browser.

    def test_returns_none_when_nothing_selected(self):
        def _script():
            import pandas as pd
            import streamlit as st
            from uvalu.ui import _row_select_table
            result = _row_select_table(pd.DataFrame({"a": [1, 2, 3]}), key="tbl")
            st.text(result)

        at = _run(_script)
        assert at.text[0].value == "None"

    def test_widget_key_embeds_nonce(self):
        def _script():
            import pandas as pd
            from uvalu.ui import _row_select_table
            _row_select_table(pd.DataFrame({"a": [1, 2, 3]}), key="tbl")

        at = _run(_script)
        assert at.dataframe[0].key == "tbl_0"


# ── _auto_rerun ────────────────────────────────────────────────────────────

class TestAutoRerun:
    def test_initial_arm_consumes_its_own_flag_without_rerunning(self):
        # _auto_rerun sets the flag then immediately calls _tick() once to
        # assemble the fragment — on this very first call, _tick() itself
        # pops that SAME flag (True) and returns without calling
        # st.rerun(), so by the time _auto_rerun() returns the flag is
        # already gone again, not left sitting at True. It only actually
        # calls st.rerun() on a LATER, real timer-driven fragment rerun,
        # which requires real elapsed time — not reachable via AppTest.
        def _script():
            from uvalu.ui import _auto_rerun
            _auto_rerun(30, "test_refresh")

        at = _run(_script)
        assert "_auto_rerun_test_refresh" not in at.session_state


# ── consumed_tick ─────────────────────────────────────────────────────────

class TestConsumedTick:
    def test_false_when_no_marker(self):
        def _script():
            import streamlit as st
            from uvalu.ui import consumed_tick
            st.text(consumed_tick("portfolio_refresh"))

        at = _run(_script)
        assert at.text[0].value == "False"

    def test_true_once_then_cleared(self):
        def _script():
            import streamlit as st
            from uvalu.ui import consumed_tick
            st.session_state["_tick_portfolio_refresh"] = True
            st.text(consumed_tick("portfolio_refresh"))   # True
            st.text(consumed_tick("portfolio_refresh"))   # popped → False

        at = _run(_script)
        assert [t.value for t in at.text] == ["True", "False"]


# ── price_autorefresh ─────────────────────────────────────────────────────

class TestPriceAutorefresh:
    def _capture(self, monkeypatch, *, market_open: bool, interval_s: int) -> dict:
        captured: dict = {}
        monkeypatch.setattr(ui, "is_market_hours", lambda: market_open)
        monkeypatch.setattr(ui, "load_settings", lambda _email: {"refresh_interval_s": interval_s})
        monkeypatch.setattr(ui, "current_user",
                            lambda: type("U", (), {"email": "x@y.z"})())
        monkeypatch.setattr(ui, "_auto_rerun",
                            lambda secs, key: captured.update(secs=secs, key=key))
        return captured

    def test_uses_user_interval_during_market_hours(self, monkeypatch):
        captured = self._capture(monkeypatch, market_open=True, interval_s=30)
        ui.price_autorefresh("portfolio_refresh")
        assert captured == {"secs": 30, "key": "portfolio_refresh"}

    def test_stretches_to_15min_off_hours(self, monkeypatch):
        captured = self._capture(monkeypatch, market_open=False, interval_s=60)
        ui.price_autorefresh("dashboard_refresh")
        assert captured["secs"] == 900

    def test_off_hours_keeps_a_longer_user_interval(self, monkeypatch):
        captured = self._capture(monkeypatch, market_open=False, interval_s=1800)
        ui.price_autorefresh("risk_refresh")
        assert captured["secs"] == 1800   # max(user, 900)
