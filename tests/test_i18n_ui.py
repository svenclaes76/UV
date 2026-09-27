"""AppTest coverage for the i18n wiring (docs/i18n-spec.md §12): switching
language keeps the page and its filters, the Language & region settings
persist and apply, the sign-in choice carries into the profile, a profile
follows the user to another session, the one-time notice for a retired
language, and comma-decimal number entry."""
import pytest
from streamlit.testing.v1 import AppTest

import settings
from uvalu import i18n
from uvalu.pages_ import screener as screener_page
from uvalu.pages_ import settings as settings_page
from tests.conftest import (TEST_EMAIL, USER_SETUP_SRC, fake_cached_fn, make_scored_df, make_scored_row,
                            make_screener_data_tuple)


@pytest.fixture
def drafts(monkeypatch):
    """Show the unreviewed drafts, so translated labels are visible."""
    monkeypatch.setenv("UVALU_I18N_DRAFTS", "1")
    i18n._load_catalog.clear()
    yield
    i18n._load_catalog.clear()


def _translated(lang: str, msgid: str) -> str:
    cat = i18n._load_catalog(lang, True)
    return cat.messages.get(msgid) or msgid


def _activate_src(body: str) -> str:
    return USER_SETUP_SRC + f"""
import streamlit as st
from uvalu import i18n
i18n.activate({TEST_EMAIL!r})
{body}
"""


# ── L-06: a language switch keeps the screen and its filters ────────────────

def test_language_switch_keeps_screener_filters(isolated_data, monkeypatch, drafts):
    df = make_scored_df([make_scored_row(sector="Technology"),
                         make_scored_row(Ticker="BBB.BR", Name="Société Générale", sector="Financial Services")])
    monkeypatch.setattr(screener_page, "_load_all_screener_data",
                        lambda *a, **k: make_screener_data_tuple(exchange_df=df))
    monkeypatch.setattr(screener_page, "get_fetch_progress", lambda: {"running": False, "total": 0, "done": 0})
    at = AppTest.from_string(_activate_src(
        "from uvalu.pages_ import screener as screener_page\nscreener_page.render()"), default_timeout=60)
    at.run()
    at.text_input(key="scr_search").set_value("societe")
    at.selectbox(key="scr_sector").set_value("Financial Services")
    at.slider(key="scr_min_score").set_value(10)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    at.session_state["_uv_lang_choice"] = "de"      # the switcher's / ?lang= path
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["_uv_i18n"].lang == "de"
    assert at.text_input(key="scr_search").value == "societe"
    assert at.selectbox(key="scr_sector").value == "Financial Services"
    assert at.slider(key="scr_min_score").value == 10
    html = "".join(m.value for m in at.markdown)
    assert "Société Générale" in html                                  # accent-insensitive search still matches
    assert _translated("de", "Value screener") in html                 # the page is now German


# ── Settings › Language & region (S-02, S-03, S-05) ─────────────────────────

def _settings_app(monkeypatch) -> AppTest:
    monkeypatch.setattr(settings_page, "_load_all_screener_data", fake_cached_fn(None))
    at = AppTest.from_string(_activate_src(
        'st.session_state["user_role"] = "Analyst"\n'
        "from uvalu.pages_ import settings as settings_page\nsettings_page.render()"), default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_language_and_region_settings_persist_and_apply(isolated_data, monkeypatch):
    at = _settings_app(monkeypatch)
    at.selectbox(key="set_i18n_language").set_value("fr").run()
    at.selectbox(key="set_i18n_region").set_value("de-CH").run()
    at.radio(key="set_i18n_date_format").set_value("iso").run()
    assert not at.exception, [str(e.value) for e in at.exception]

    saved = settings.load_settings(TEST_EMAIL)
    assert (saved["language"], saved["region"], saved["date_format"]) == ("fr", "de-CH", "iso")
    assert saved["display_currency"] is None            # still following the region
    ctx = at.session_state["_uv_i18n"]
    assert (ctx.lang, ctx.region, ctx.currency, ctx.date_format) == ("fr", "de-CH", "CHF", "iso")
    assert at.selectbox(key="set_i18n_currency").value == "CHF"   # the widget follows the region too


def test_reset_to_defaults_asks_first(isolated_data, monkeypatch):
    at = _settings_app(monkeypatch)
    at.selectbox(key="set_i18n_language").set_value("es").run()
    at.button(key="set_i18n_reset").click().run()
    assert settings.load_settings(TEST_EMAIL)["language"] == "es"   # nothing reset yet
    at.button(key="set_i18n_reset_yes").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert all(settings.load_settings(TEST_EMAIL)[k] is None for k in i18n.PROFILE_KEYS)


# ── S-04: the sign-in choice carries into the profile ───────────────────────

def test_sign_in_language_choice_is_saved_to_an_empty_profile(isolated_data):
    at = AppTest.from_string(_activate_src("st.write(i18n.current().lang)"), default_timeout=60)
    at.session_state["_uv_lang_choice"] = "nl"
    at.session_state["_uv_lang_from_switcher"] = True
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_settings(TEST_EMAIL)["language"] == "nl"


def test_url_lang_param_is_never_saved(isolated_data):
    at = AppTest.from_string(_activate_src("st.write(i18n.current().lang)"), default_timeout=60)
    at.query_params["lang"] = "it"
    at.run()
    assert at.session_state["_uv_i18n"].lang == "it"
    assert settings.load_settings(TEST_EMAIL)["language"] is None


# ── S-03: settings follow the user to another device / session ──────────────

def test_saved_settings_apply_in_a_new_session(isolated_data):
    s = settings.load_settings(TEST_EMAIL)
    s.update(language="de", region="de-AT", date_format="medium")
    settings.save_settings(s, TEST_EMAIL)
    at = AppTest.from_string(_activate_src("st.write(i18n.current().lang)"), default_timeout=60)
    at.run()
    ctx = at.session_state["_uv_i18n"]
    assert (ctx.lang, ctx.region, ctx.date_format) == ("de", "de-AT", "medium")


# ── C-01: a language removed from config falls back with a one-time notice ──

def test_retired_language_falls_back_once(isolated_data, monkeypatch):
    s = settings.load_settings(TEST_EMAIL)
    s["language"] = "it"
    settings.save_settings(s, TEST_EMAIL)
    cfg = i18n.I18nConfig(enabled_languages=("en", "nl", "fr", "de", "es"))
    monkeypatch.setattr(i18n, "config", lambda: cfg)
    body = "n = i18n.pop_notice()\nst.write(n or 'no-notice')"
    at = AppTest.from_string(_activate_src(body), default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["_uv_i18n"].lang == "en"
    assert "no longer available" in at.markdown[0].value
    assert settings.load_settings(TEST_EMAIL)["language"] is None
    at.run()
    assert at.markdown[0].value == "no-notice"


# ── T-04 / F-10: comma-decimal number entry ─────────────────────────────────

_FIELD_BODY = """from uvalu.locale_ui import number_field
v = number_field("Amount", key="amt", value=0.0, min_value=0.0, step=0.01, format="%.2f")
st.write(f"value={v!r}")
"""


def test_number_field_reads_the_region_format(isolated_data):
    s = settings.load_settings(TEST_EMAIL)
    s["region"] = "nl-BE"
    settings.save_settings(s, TEST_EMAIL)
    at = AppTest.from_string(_activate_src(_FIELD_BODY), default_timeout=60)
    at.run()
    at.text_input(key="amt__txt").set_value("1234,5").run()
    assert "value=1234.5" in at.markdown[-1].value
    assert any("= 1.234,5" in c.value for c in at.caption)             # parsed value shown back
    at.text_input(key="amt__txt").set_value("1.234,5").run()
    assert "value=1234.5" in at.markdown[-1].value
    at.text_input(key="amt__txt").set_value("1,2,3").run()
    assert "value=None" in at.markdown[-1].value                       # rejected, not guessed
    assert any(i18n.number_example("nl-BE") in c.value for c in at.caption)


def test_number_field_is_the_native_widget_in_dot_decimal_regions(isolated_data):
    at = AppTest.from_string(_activate_src(_FIELD_BODY), default_timeout=60)
    at.run()
    assert at.number_input(key="amt") is not None
    at.number_input(key="amt").set_value(12.5).run()
    assert "value=12.5" in at.markdown[-1].value
