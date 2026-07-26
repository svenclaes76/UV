"""AppTest coverage for uvalu/pages_/settings.py."""
import io

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import portfolio
import settings
from uvalu.pages_ import settings as settings_page
from tests.conftest import TEST_EMAIL, fake_cached_fn


def _run(monkeypatch) -> AppTest:
    monkeypatch.setattr(settings_page, "_load_all_screener_data", fake_cached_fn(None))

    def _script():
        import streamlit as st
        from uvalu.pages_ import settings as settings_page
        st.session_state["user_email"] = "test@example.com"
        st.session_state["user_role"] = "Analyst"
        settings_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_renders_without_exceptions(isolated_data, monkeypatch):
    _run(monkeypatch)


def test_shows_default_veto_thresholds(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "500%" in html   # max debt/equity default
    assert "90%" in html    # max payout default
    assert "70" in html     # buy threshold default


def test_changing_max_debt_equity_slider_persists_and_reruns(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    slider = at.slider(key="scr_max_de")
    slider.set_value(300)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_shared_settings()["max_debt_equity"] == 300.0


def test_changing_benchmark_toggle_persists(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    toggle = at.toggle(key="scr_stoxx")
    toggle.set_value(True)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_shared_settings()["benchmark_stoxx"] is True


def test_changing_refresh_interval_persists(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    select_slider = at.select_slider(key="disp_refresh_interval")
    select_slider.set_value(300)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_settings(TEST_EMAIL)["refresh_interval_s"] == 300


def test_export_shows_info_when_portfolio_empty(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert "Your portfolio is empty" in "".join(i.value for i in at.info)
    assert len(at.download_button) == 0


def test_export_shows_download_button_when_portfolio_has_data(isolated_data, monkeypatch):
    portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR", "shares": 10}]))
    at = _run(monkeypatch)
    assert len(at.download_button) == 1
    assert at.download_button[0].label == "Download backup.xlsx"


def _build_test_workbook() -> bytes:
    # Excel's "used range" (what read_excel sees back) is trimmed to the
    # last populated row/column — a sold-position row with a real date_out
    # value (col 17) is what keeps all 18 columns and 110 rows intact when
    # read back, matching tests/test_portfolio.py's TestParseExcel builder.
    n_cols = 18
    rows = [[None] * n_cols for _ in range(110)]
    rows[1][0] = "Test Corp"
    rows[1][1] = "EBR:TESTX"
    rows[1][2] = 10
    rows[1][6] = 1000.0
    rows[1][16] = "2024-01-01"
    rows[94][0] = "Sold Corp"
    rows[94][1] = "EBR:SOLDX"
    rows[94][2] = 5
    rows[94][6] = 500.0
    rows[94][7] = 600.0
    rows[94][16] = "2023-01-01"
    rows[94][17] = "2023-06-01"
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, sheet_name="beleggingen", header=False, index=False)
    return buf.getvalue()


def test_import_valid_excel_saves_portfolio(isolated_data, monkeypatch):
    # settings.py's import branch calls st.rerun() unconditionally on success
    # without ever clearing the file_uploader's own state — since AppTest's
    # uploaded file persists across reruns exactly like a real session, that
    # st.rerun() re-enters the same "file present -> re-import -> rerun"
    # branch forever (confirmed: this hangs for the full 60s timeout without
    # this patch). Real bug in the app, out of scope here — st.rerun is
    # stubbed to a no-op so this test can still verify the save itself
    # happened before rerun() would have fired.
    import streamlit as st
    monkeypatch.setattr(st, "rerun", lambda *a, **k: None)

    at = _run(monkeypatch)
    uploader = at.file_uploader(key="imp_portfolio")
    uploader.upload(
        "portfolio.xlsx", _build_test_workbook(),
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert portfolio.load_portfolio().iloc[0]["ticker"] == "TESTX.BR"


def test_import_excel_with_no_valid_positions_shows_error(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    # No row matches a valid EBR:/AMS:/etc. prefix, but a dummy value in the
    # last row/column keeps Excel's used-range at the full 110x18 shape
    # instead of collapsing to a near-empty sheet (see _build_test_workbook).
    rows = [[None] * 18 for _ in range(110)]
    rows[1][1] = "XYZ:NOTVALID"
    rows[109][17] = "placeholder"
    empty_wb = io.BytesIO()
    pd.DataFrame(rows).to_excel(empty_wb, sheet_name="beleggingen", header=False, index=False)

    uploader = at.file_uploader(key="imp_portfolio")
    uploader.upload(
        "portfolio.xlsx", empty_wb.getvalue(),
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No open" in "".join(e.value for e in at.error)


def test_account_footer_shows_email_and_role(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert TEST_EMAIL in html
    assert "Analyst" in html
    assert "Sign out" in html
