"""uvalu/i18n.py — formatting snapshots per region, parse round-trips,
language/region resolution, config validation, catalogs and fallbacks,
deferred messages, collation and search (docs/i18n-spec.md §12).

Format snapshots live in tests/snapshots/i18n_formats.json and come from the
pinned Babel/CLDR version (spec T-07). After an intentional Babel upgrade,
regenerate them with ``UVALU_UPDATE_SNAPSHOTS=1 pytest tests/test_i18n.py``
and review the diff.
"""
import datetime as dt
import json
import os
import pickle
import time
from pathlib import Path

import pytest

from uvalu import i18n

SNAPSHOT = Path(__file__).parent / "snapshots" / "i18n_formats.json"
REGIONS = list(i18n.I18nConfig().enabled_regions)
NBSP, NNBSP = " ", " "


# ── fmt_* snapshots (every enabled region) ───────────────────────────────────

def _snapshot_values() -> dict:
    d = dt.date(2026, 9, 27)
    out = {}
    for r in REGIONS:
        out[r] = {
            "num": i18n.fmt_num(1234.56, locale=r),
            "num_neg": i18n.fmt_num(-1234.5, locale=r),
            "num_zero": i18n.fmt_num(0, locale=r),
            "num_large": i18n.fmt_num(9876543210.987, locale=r),
            "num_small": i18n.fmt_num(0.000123, 6, locale=r),
            "num_4dp_trim": i18n.fmt_num(12.5, 4, min_decimals=0, locale=r),
            "int_4digit": i18n.fmt_int(1234, locale=r),
            "money_eur": i18n.fmt_money(1234.56, "EUR", locale=r),
            "money_neg_chf": i18n.fmt_money(-1234.5, "CHF", locale=r),
            "money_signed": i18n.fmt_money(42, "EUR", 0, signed=True, locale=r),
            "money_approx_usd": i18n.fmt_money(99.5, "USD", approx=True, locale=r),
            "pct": i18n.fmt_pct(12.5, locale=r),
            "pct_signed_pos": i18n.fmt_pct(3.2, signed=True, locale=r),
            "pct_signed_neg": i18n.fmt_pct(-1.4, signed=True, locale=r),
            "pct_signed_zero": i18n.fmt_pct(0, 0, signed=True, locale=r),
            "pct_fraction": i18n.fmt_pct(0.0345, 2, fraction=True, locale=r),
            "compact": i18n.fmt_compact(1.2e9, locale=r),
            "compact_eur": i18n.fmt_compact(3.4e6, currency="EUR", locale=r),
            "date_short": i18n.fmt_date(d, "short", locale=r),
            "date_medium": i18n.fmt_date(d, "medium", locale=r),
            "date_iso": i18n.fmt_date(d, "iso", locale=r),
            "plotly_separators": i18n.plotly_separators(r),
        }
    return out


def test_format_snapshots_per_region():
    actual = _snapshot_values()
    if os.environ.get("UVALU_UPDATE_SNAPSHOTS") == "1" or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert actual == expected


@pytest.mark.parametrize("region", ["de-CH", "it-CH"])
def test_swiss_negative_money_puts_the_minus_where_the_plus_goes(region):
    """CLDR's "¤-#" read "CHF-4’390" next to a signed "+CHF 155.72"."""
    neg = i18n.fmt_money(-4390, "CHF", 0, locale=region)
    pos = i18n.fmt_money(4390, "CHF", 0, signed=True, locale=region)
    assert neg == f"-CHF{NBSP}4’390"
    assert neg[1:] == pos[1:]


def test_money_never_shows_minus_zero():
    assert i18n.fmt_money(-0.0, "EUR", locale="en-GB") == "€0.00"
    assert i18n.fmt_money(-0.0, "CHF", locale="de-CH") == f"CHF{NBSP}0.00"


@pytest.mark.parametrize("region, plain, eur", [
    ("en-GB", "12.8K", "€12.8K"),
    ("nl-BE", "12,8K", f"€{NBSP}12,8K"),
    ("fr-FR", f"12,8{NBSP}k", f"12,8{NBSP}k{NBSP}€"),
    ("es-ES", f"12,8{NBSP}mil", f"12,8{NBSP}mil{NBSP}€"),
    # CLDR has no short form for German/Italian thousands: full grouped amount,
    # never Babel's raw "12752,2".
    ("de-DE", "12.752", f"12.752{NBSP}€"),
    ("de-CH", "12’752", f"EUR{NBSP}12’752"),
    ("it-IT", "12.752", f"12.752{NBSP}€"),
])
def test_compact_thousands(region, plain, eur):
    assert i18n.fmt_compact(12752.2, locale=region) == plain
    assert i18n.fmt_compact(12752.2, currency="EUR", locale=region) == eur


def test_lowercase_noun_keeps_german_capitals():
    assert _in("de", i18n.lowercase_noun, "Dividende") == "Dividende"
    assert _in("nl", i18n.lowercase_noun, "Dividend") == "dividend"


@pytest.mark.parametrize("region, number, money, date", [
    ("en-GB", "1,234.56", "€1,234.56", "27/09/2026"),
    ("nl-BE", "1.234,56", f"€{NBSP}1.234,56", "27/09/2026"),
    ("fr-BE", f"1{NNBSP}234,56", f"1{NNBSP}234,56{NBSP}€", "27/09/26"),
    ("de-DE", "1.234,56", f"1.234,56{NBSP}€", "27.09.26"),
    ("de-CH", "1’234.56", f"EUR{NBSP}1’234.56", "27.09.26"),
    ("it-IT", "1.234,56", f"1.234,56{NBSP}€", "27/09/26"),
])
def test_reference_formats_from_spec_table(region, number, money, date):
    """Spec §2's reference table — the de-CH apostrophe and the French
    narrow no-break space in particular."""
    assert i18n.fmt_num(1234.56, locale=region) == number
    assert i18n.fmt_money(1234.56, "EUR", locale=region) == money
    assert i18n.fmt_date(dt.date(2026, 9, 27), "short", locale=region) == date


def test_missing_values_render_as_dash():
    for fn in (i18n.fmt_num, i18n.fmt_money, i18n.fmt_pct, i18n.fmt_compact, i18n.fmt_date):
        assert fn(None) == i18n.MISSING
        assert fn(float("nan")) == i18n.MISSING


def test_formatting_never_changes_the_value():
    """N-03: rounding is display-only."""
    v = 1234.5678
    i18n.fmt_num(v, 1)
    assert v == 1234.5678


def test_formatting_500_rows_is_fast():
    """N-02: a 500-row table's formatting stays well under 50 ms."""
    values = [i * 1234.567 for i in range(500)]
    t = time.perf_counter()
    for v in values:
        i18n.fmt_money(v, "EUR", locale="fr-BE")
    assert (time.perf_counter() - t) < 0.05


# ── parse_num (F-10, round trip) ─────────────────────────────────────────────

@pytest.mark.parametrize("region", REGIONS)
@pytest.mark.parametrize("value", [0.0, 1.5, 12.34, 1234.5, -1234.56, 1234567.89, 0.07])
def test_parse_round_trip(region, value):
    for decimals in (2, 4):
        text = i18n.fmt_num(value, decimals, locale=region)
        assert i18n.parse_num(text, locale=region) == pytest.approx(round(value, decimals), abs=1e-12)


def test_parse_follows_the_region_not_guessing():
    assert i18n.parse_num("1.234", locale="nl-BE") == 1234
    assert i18n.parse_num("1.234", locale="en-GB") == 1.234
    assert i18n.parse_num("1 234,5", locale="fr-BE") == 1234.5      # plain space typed for NNBSP
    assert i18n.parse_num("1'234.5", locale="de-CH") == 1234.5      # ASCII apostrophe
    assert i18n.parse_num("12,5 %", locale="nl-BE") == 12.5
    assert i18n.parse_num("  ", locale="nl-BE") is None
    for bad, region in (("1,5", "en-GB"), ("1.23", "nl-BE"), ("abc", "de-DE"), ("1..2", "en-GB")):
        with pytest.raises(i18n.NumberParseError) as exc:
            i18n.parse_num(bad, locale=region)
        assert exc.value.example == i18n.number_example(region)


# ── Resolution (spec §6) ─────────────────────────────────────────────────────

def _resolve(profile=None, session_lang=None, tags=()):
    return i18n.resolve(profile, session_lang=session_lang, browser_tags=list(tags))


def test_profile_language_wins_over_session_and_browser():
    ctx, dropped = _resolve({"language": "fr"}, "de", ["nl-BE"])
    assert (ctx.lang, dropped) == ("fr", None)


def test_session_choice_then_browser_then_default():
    assert _resolve(session_lang="de", tags=["nl-BE"])[0].lang == "de"
    assert _resolve(tags=["nl-NL", "en"])[0].lang == "nl"
    assert _resolve(tags=["de-AT"])[0].lang == "de"
    assert _resolve(tags=["pt-PT", "es"])[0].lang == "es"     # pt falls through
    assert _resolve(tags=["pt-PT"])[0].lang == "en"


def test_accept_language_ordering_by_q():
    assert i18n._parse_accept_language("en;q=0.5, fr-BE, nl;q=0.9") == ["fr-BE", "nl", "en"]


def test_region_resolution():
    assert _resolve(tags=["fr-BE"])[0].region == "fr-BE"                # full browser locale
    assert _resolve(tags=["de-AT"])[0].region == "de-AT"
    assert _resolve(tags=["nl"])[0].region == "nl-BE"                   # language default
    assert _resolve({"language": "de", "region": "same"})[0].region == "de-DE"
    assert _resolve({"region": "de-CH"})[0].region == "de-CH"


def test_display_currency_follows_region_until_chosen():
    assert _resolve({"region": "de-CH"})[0].currency == "CHF"
    assert _resolve({"region": "fr-BE"})[0].currency == "EUR"
    assert _resolve({"region": "de-CH", "display_currency": "USD"})[0].currency == "USD"


def test_corrupt_saved_values_fall_back_silently():
    """D-03."""
    ctx, _dropped = _resolve({"language": None, "region": "xx-YY", "display_currency": "BTC",
                              "date_format": "weird", "time_zone": "Mars/Base", "week_start": "friday"})
    assert (ctx.region, ctx.currency, ctx.date_format, ctx.time_zone, ctx.week_start) == \
           ("en-GB", "EUR", "short", "Europe/Brussels", "monday")


def test_disabled_language_is_reported_for_the_one_time_notice(monkeypatch):
    """C-01: a profile language that config no longer enables."""
    cfg = i18n.I18nConfig(enabled_languages=("en", "nl", "fr", "de", "es"))
    monkeypatch.setattr(i18n, "config", lambda: cfg)
    ctx, dropped = _resolve({"language": "it"}, tags=["it-IT"])
    assert dropped == "it" and ctx.lang == "en"


# ── Config validation (C-02) ─────────────────────────────────────────────────

def test_shipped_config_is_valid():
    i18n.config.cache_clear()
    cfg = i18n.config()
    assert cfg.default_language == "en" and "de-CH" in cfg.enabled_regions


@pytest.mark.parametrize("patch, key", [
    ({"default_language": "pt"}, "default_language"),
    ({"enabled_languages": ["en", "xx"]}, "enabled_languages"),
    ({"enabled_regions": ["en-GB", "nl"]}, "enabled_regions"),
    ({"default_region": "fr-FR", "enabled_regions": ["en-GB"]}, "default_region"),
    ({"enabled_display_currencies": ["EUR", "ZZZ"]}, "enabled_display_currencies"),
    ({"display_currency_by_region": {"de-CH": "JPY"}}, "display_currency_by_region"),
    ({"default_time_zone": "Mars/Base"}, "default_time_zone"),
    ({"allow_url_lang_param": "yes"}, "allow_url_lang_param"),
    ({"surprise": 1}, "surprise"),
])
def test_invalid_config_names_the_key(patch, key):
    with pytest.raises(i18n.I18nConfigError) as exc:
        i18n.validate_config(patch)
    assert f"'{key}'" in str(exc.value)


# ── Catalogs, fallback, plurals (T-01, D-01) ─────────────────────────────────

@pytest.fixture
def drafts(monkeypatch):
    """Load the unreviewed drafts so lookups return translations."""
    monkeypatch.setenv("UVALU_I18N_DRAFTS", "1")
    i18n._load_catalog.clear()
    yield
    i18n._load_catalog.clear()


def _in(lang, fn, *a, region=None, **k):
    ctx = i18n.with_(i18n._default_ctx(), lang=lang, **({"region": region} if region else {}))
    orig = i18n.current
    i18n.current = lambda: ctx
    try:
        return fn(*a, **k)
    finally:
        i18n.current = orig


def test_compiled_catalog_serves_reviewed_translations(monkeypatch):
    """Without the drafts switch the app reads only the compiled .mo files,
    which hold the reviewed (non-fuzzy) entries."""
    monkeypatch.delenv("UVALU_I18N_DRAFTS", raising=False)
    i18n._load_catalog.clear()
    assert _in("nl", i18n._, "Portfolio") == "Portefeuille"


def test_unreviewed_entries_are_left_out_of_the_compiled_catalog(tmp_path):
    """W-04: a fuzzy entry never reaches the .mo (shows in English)."""
    import io
    from babel.messages.catalog import Catalog
    from babel.messages.mofile import write_mo
    cat = Catalog(locale="nl")
    cat.add("Reviewed", "Nagekeken")
    cat.add("Draft", "Ontwerp", flags=["fuzzy"])
    buf = io.BytesIO()
    write_mo(buf, cat, use_fuzzy=False)
    import gettext
    t = gettext.GNUTranslations(io.BytesIO(buf.getvalue()))
    assert t.gettext("Reviewed") == "Nagekeken" and t.gettext("Draft") == "Draft"


def test_translation_plurals_and_context(drafts):
    assert _in("nl", i18n._, "Portfolio") == "Portefeuille"
    assert _in("de", i18n.ngettext, "{count} position", "{count} positions", 1) == "1 Position"
    assert _in("de", i18n.ngettext, "{count} position", "{count} positions", 3) == "3 Positionen"
    assert _in("nl", i18n.pgettext, "button", "Deposit") == "Storten"
    assert _in("nl", i18n._, "Deposit") == "Storting"


def test_missing_translation_falls_back_to_english(drafts):
    assert _in("fr", i18n._, "A text nobody extracted {x}", x=1) == "A text nobody extracted 1"


def test_broken_placeholder_in_a_translation_never_crashes(drafts, monkeypatch):
    cat = i18n._load_catalog("de", True)
    monkeypatch.setitem(cat.messages, "Live · {time}", "Live · {zeit}")
    assert _in("de", i18n._, "Live · {time}", time="10:00") == "Live · 10:00"


def test_every_catalog_compiles_with_matching_placeholders():
    """T-06: the same check CI runs (tools/i18n_compile.py, non-strict)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18n_compile", Path(__file__).parents[1] / "tools" / "i18n_compile.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.check_and_compile(strict=False) == 0


def test_code_and_template_are_in_sync():
    """Every wrapped string is in messages.pot and vice versa — run
    tools/i18n_update.py after changing UI text."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18n_update", Path(__file__).parents[1] / "tools" / "i18n_update.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(check=True) == 0


def test_update_keeps_poedit_wrapping_of_unchanged_entries():
    """i18n_update.py rewrote hundreds of unchanged lines after every Poedit
    save because Babel wraps differently: unchanged entries keep their text,
    only moved source references and real changes come through."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18n_update", Path(__file__).parents[1] / "tools" / "i18n_update.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    header = 'msgid ""\nmsgstr ""\n"Language: nl\\n"\n"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n'
    poedit = (header + '"X-Generator: Poedit 3.9\\n"\n\n'
              '#. Context: a note\n#: a.py:1 b.py:2\n#: c.py:3\nmsgid ""\n"Long text that Poedit wraps "\n'
              '"here."\nmsgstr "Lange tekst."\n\n'
              '#: a.py:5\nmsgid "Old"\nmsgstr "Oud"\n')
    babel = (header.replace('"Language: nl\\n"\n', '') + '"Language: nl\\n"\n\n'
             '#. Context: a note\n#: a.py:1 b.py:2 c.py:3\nmsgid "Long text that Poedit wraps here."\n'
             'msgstr "Lange tekst."\n\n'
             '#: a.py:9\nmsgid "Old"\nmsgstr "Oud"\n\n'
             '#: d.py:1\nmsgid "New"\nmsgstr ""\n')
    out = mod._preserve_layout(poedit, babel)
    assert out.startswith(poedit.split("\n\n")[0])          # header: Poedit's order and X-Generator kept
    assert '"Long text that Poedit wraps "\n"here."' in out     # unchanged entry: Poedit's wrapping kept
    assert "#: a.py:1 b.py:2\n#: c.py:3" in out                # same references: their lines kept too
    assert '#: a.py:9\nmsgid "Old"' in out                      # moved reference comes through
    assert 'msgid "New"' in out                                  # new entry added
    assert mod._preserve_layout(out, babel) == out               # a second run changes nothing


# ── Deferred messages ────────────────────────────────────────────────────────

def test_msg_is_english_text_that_retranslates_and_pickles(drafts):
    m = i18n.lazy_("Portfolio beta {beta} exceeds 1.5 — amplified drawdown risk",
                   beta=i18n.Fmt("num", 1.62, decimals=2))
    assert m == "Portfolio beta 1.62 exceeds 1.5 — amplified drawdown risk"
    again = pickle.loads(pickle.dumps(m))
    assert again == m
    nl = _in("nl", i18n.tr, again, region="nl-BE")   # numbers follow the region
    assert "1,62" in nl and nl != str(m)


def test_tr_translates_known_values_and_passes_unknown_through(drafts):
    assert _in("nl", i18n.tr, "Financial Services") != "Financial Services"
    assert _in("nl", i18n.tr, "Some Company NV") == "Some Company NV"
    assert i18n.tr(None) == i18n.MISSING


# ── Collation and search (F-13, F-14) ────────────────────────────────────────

def test_accented_names_sort_with_their_base_letter():
    names = ["Zurich Insurance", "Ørsted", "Électricité de France", "Eni", "Apple", "ageas"]
    assert sorted(names, key=i18n.sort_key) == [
        "ageas", "Apple", "Électricité de France", "Eni", "Ørsted", "Zurich Insurance"]


def test_search_ignores_accents_case_and_punctuation():
    assert i18n.search_match("societe", "Société Générale")
    assert i18n.search_match("loreal", "L'Oréal")
    assert i18n.search_match("ORSTED", "Ørsted A/S")
    assert i18n.search_match("anheuserbusch", "Anheuser-Busch InBev")
    assert not i18n.search_match("nestle", "Société Générale")


# ── Charts, tables, pickers ──────────────────────────────────────────────────

def test_plotly_figures_get_region_separators_and_numeric_dates():
    import plotly.graph_objects as go
    fig = _in_region("de-DE", lambda: i18n.localize_fig(go.Figure()))
    assert fig.layout.separators == ",."
    stops = [s.value for s in fig.layout.xaxis.tickformatstops]
    assert stops == ["%d.%m.%y", "%m.%Y", "%Y"]


def _in_region(region, fn):
    ctx = i18n.with_(i18n._default_ctx(), region=region)
    orig = i18n.current
    i18n.current = lambda: ctx
    try:
        return fn()
    finally:
        i18n.current = orig


def test_date_input_format_follows_region():
    assert _in_region("en-US", i18n.date_input_format) == "MM/DD/YYYY"
    assert _in_region("de-DE", i18n.date_input_format) == "DD.MM.YYYY"
    assert _in_region("nl-BE", i18n.date_input_format) == "DD/MM/YYYY"


def test_styler_keeps_numbers_sortable():
    import pandas as pd
    df = pd.DataFrame({"v": [1234.5, 10.0]})
    styler = i18n.style_table(df, {"v": lambda x: i18n.fmt_num(x)})
    assert styler.data["v"].tolist() == [1234.5, 10.0]          # sorting uses the numbers
    assert "1.234,50" in _in_region("nl-BE", styler.to_html)   # display uses the region


def test_language_names_are_in_their_own_language():
    assert [i18n.language_name(code) for code in ("en", "nl", "fr", "de", "it", "es")] == \
           ["English", "Nederlands", "Français", "Deutsch", "Italiano", "Español"]


# ── Column widths fit translated headers ─────────────────────────────────────

def _table_widths():
    from uvalu.components import HOLDINGS_GRID_COLS, fit_grid_cols
    from uvalu.pages_ import portfolio, risk, screener, watchlist
    return {
        "open": portfolio._layout(portfolio._OPEN_COLUMNS)[0],
        "closed": portfolio._layout(portfolio._CLOSED_COLUMNS)[0],
        "watchlist": watchlist._fitted_widths(),
        "risk": risk._rh_grid(),
        "holdings": fit_grid_cols(HOLDINGS_GRID_COLS, [i18n._(label) for label in
                                  ("Position", "Signal", "", "MoS %", "Weight", "Value", "P&L")]),
    }


def test_english_tables_keep_their_design_widths():
    from uvalu.components import HOLDINGS_GRID_COLS, RISK_HOLDINGS_GRID_COLS
    from uvalu.pages_ import portfolio, watchlist
    w = _in("en", _table_widths)
    assert w["open"] == [px for _l, px, _r in portfolio._OPEN_COLUMNS]
    assert w["closed"] == [px for _l, px, _r in portfolio._CLOSED_COLUMNS]
    assert w["watchlist"] == watchlist._HH_WIDTHS
    assert w["risk"] == RISK_HOLDINGS_GRID_COLS
    assert w["holdings"] == HOLDINGS_GRID_COLS


@pytest.mark.parametrize("lang", ["nl", "fr", "de", "it", "es"])
def test_translated_tables_only_ever_widen(lang):
    en, tr_ = _in("en", _table_widths), _in(lang, _table_widths)
    for key in ("open", "closed", "watchlist"):
        assert all(t >= e for t, e in zip(tr_[key], en[key])), key


def test_header_width_estimate_matches_measured_text():
    from uvalu.components import header_width_px
    # measured in the browser at 10px uppercase + 0.06em tracking
    for label, measured in [("Gewichtung", 69.7), ("Nettodividende", 88.9),
                            ("Niet-gerealiseerde W/V", 130.1), ("Marge de sécurité", 103.3)]:
        assert measured <= header_width_px(label) <= measured * 1.12


# ── Dialogs and drawer keep their shape in every language ───────────────────

_FIELD_ROWS = [
    (2, ("Buy date *", "Fees (opt.)")),
    (3, ("Shares *", "Total cost (€) *", "Price / share (opt.)")),
    (2, ("Sell date *", "Fees (opt.)")),
    (2, ("Shares to sell *", "Sell price *")),
    (2, ("Ex-dividend date *", "Payment date *")),
    (3, ("Shares held *", "Per share ({currency}) *", "Foreign WH (%)")),
    (2, ("Sell date *", "Sector")),
    (3, ("Shares *", "Buy price *", "Sell price *")),
]


def _row_lines(spec, msgids):
    from uvalu.dialogs import label_lines
    return label_lines(spec, [i18n._(m, currency="EUR") if "{currency}" in m else i18n._(m) for m in msgids])


def test_english_dialog_rows_need_no_label_slot():
    assert all(_in("en", _row_lines, spec, msgids) == 1 for spec, msgids in _FIELD_ROWS)


@pytest.mark.parametrize("lang", ["nl", "fr", "de", "it", "es"])
def test_translated_dialog_labels_fit_a_three_line_slot(lang):
    assert all(_in(lang, _row_lines, spec, msgids) <= 3 for spec, msgids in _FIELD_ROWS)


def test_german_amount_row_gets_a_label_slot():
    # "Preis / Aktie (optional)" is ~137px in a 113px column (live-measured)
    assert _in("de", _row_lines, 3, ("Shares *", "Total cost (€) *", "Price / share (opt.)")) == 2


def test_button_rows_keep_english_proportions_and_fit_long_labels():
    from uvalu.dialogs import _button_cols, _col_px
    from uvalu.components import text_width_px
    assert _button_cols([1, 1], ["Cancel", "Save"]) == _col_px([1, 1])
    assert _button_cols([0.8, 1, 1], ["Delete", "Cancel", "Save"]) == _col_px([0.8, 1, 1])
    cols = _button_cols([1, 1], ["Abbrechen", "Dividendenprotokoll öffnen"])
    assert cols[1] >= text_width_px("Dividendenprotokoll öffnen") + 24
    assert abs(sum(cols) - sum(_col_px([1, 1]))) < 0.01


def test_drawer_stays_at_design_width_in_english_and_widens_for_german():
    from uvalu.drawer import _DRAWER_CHROME_PX, _DRAWER_PX, _hero_row_px
    en = [("Price", "€12.24"), ("Fair value", "€23.55"), ("Margin of safety", "+48.0%"), ("Total return", "+113.7%")]
    de = [("Kurs", "12,24 €"), ("Fairer Wert", "23,55 €"), ("Sicherheitsmarge", "+48,0 %"), ("Gesamtrendite", "+113,7 %")]
    assert _hero_row_px(en) + _DRAWER_CHROME_PX <= _DRAWER_PX
    assert 470 <= _hero_row_px(de) <= 480   # live-measured 473px
