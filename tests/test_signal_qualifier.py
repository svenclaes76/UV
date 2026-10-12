"""L14 (docs/legal/signal-label-review.md): a model-signal label such as
"Undervalued" must never appear without the "model signal" qualifier — in any
language, and in any export, email or share card.

Three layers:

1. Every code path that turns a signal into a label is on a reviewed list
   (`_QUALIFIED_SURFACES`). A new surface (an export, an email, a share card,
   another page) fails `test_signal_labels_only_reach_reviewed_surfaces` until
   it shows the qualifier and is added to the list.
2. Each reviewed surface really shows the qualifier: a "Model signal" column
   header or section title, or the visible label from
   `model_signal_badge_html(..., qualified=True)`; every badge also carries
   the BDG-2 tooltip.
3. Every offered language has a translation (draft or reviewed) of the
   qualifier, the tooltip and every signal label. Whether those drafts are
   reviewed is enforced at release time by `tools/i18n_compile.py --strict`.
"""
import ast
import dataclasses
import html
import inspect
from pathlib import Path

import pytest
from babel.messages.pofile import read_po

import screener
from uvalu import components, i18n

ROOT = Path(__file__).resolve().parent.parent

# The functions that turn a signal code into a visible label.
_LABEL_SOURCES = {"SIGNAL_LABELS", "signal_badge_for", "signal_share_label", "model_signal_badge_html"}

# (file, enclosing function) → how that surface shows the qualifier.
_QUALIFIED_SURFACES = {
    ("screener.py", "<module>"): "defines SIGNAL_LABELS",
    ("screener.py", "compute_scores"): "English 'Signal' column on the scored frame; never exported (see test below)",
    ("screener.py", "methodology"): "the methodology page, which defines the signals",
    ("uvalu/components.py", "signal_badge_for"): "badge helper",
    ("uvalu/components.py", "signal_share_label"): "Screener filter pills, under the 'Model signal' filter label",
    ("uvalu/components.py", "model_signal_badge_html"): "badge helper: tooltip, optional visible qualifier",
    ("uvalu/components.py", "holdings_row_html"): "Dashboard Holdings rows, under the 'Model signal' column header",
    ("uvalu/components.py", "stock_row"): "Screener and Watchlist rows, under the 'Model signal' column header",
    ("uvalu/drawer.py", "open_drawer"): "drawer header badge, qualified=True",
    ("uvalu/pages_/analysis.py", "render"): "Analysis header badge, qualified=True",
    ("uvalu/pages_/analysis.py", "_render_history_and_sensitivity"): "'Model signal history' card",
    ("uvalu/pages_/help.py", "_signal_legend"): "the methodology page, which defines the signals",
    ("uvalu/pages_/help.py", "_render_cards"): "the methodology page, which defines the signals",
    ("uvalu/pages_/screener.py", "render"): "'Model signal' filter label and column header",
    ("uvalu/locale_ui.py", "_preview"): "region preview, labelled 'Model signal'",
}

_SKIP_DIRS = {".venv", "venv", "tests", "tools", ".claude", "locales", "docs", ".git", ".cache", "data"}


def _label_references() -> set[tuple[str, str]]:
    found = set()
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in _SKIP_DIRS or "site-packages" in rel.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def walk(node, scope):
            for child in ast.iter_child_nodes(node):
                inner = scope
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    inner = child.name
                name = (child.id if isinstance(child, ast.Name) else
                        child.attr if isinstance(child, ast.Attribute) else None)
                if name in _LABEL_SOURCES:
                    found.add((rel.as_posix(), scope))
                walk(child, inner)

        walk(tree, "<module>")
    return found


def test_signal_labels_only_reach_reviewed_surfaces():
    new = _label_references() - set(_QUALIFIED_SURFACES)
    assert not new, (
        f"Signal labels reach new places: {sorted(new)}. Show the 'model signal' qualifier there "
        "(a 'Model signal' header or model_signal_badge_html(..., qualified=True)), then add each "
        "to _QUALIFIED_SURFACES with how it is qualified.")


def test_no_reviewed_surface_has_gone_stale():
    # Keeps the list honest: an entry whose code no longer exists is removed.
    stale = set(_QUALIFIED_SURFACES) - _label_references()
    assert not stale, f"Remove from _QUALIFIED_SURFACES: {sorted(stale)}"


def test_exports_carry_no_signal():
    # The Excel/CSV exports and backups have no qualifier, so no signal at all.
    for name in ("workbook.py", "backup.py"):
        src = (ROOT / name).read_text(encoding="utf-8").lower()
        assert "signal" not in src, f"{name} references signals; add the qualifier and a test first"


def test_list_columns_and_filters_are_headed_model_signal():
    from uvalu.pages_ import dashboard, screener as screener_page, watchlist
    assert dict((k, label) for k, label, _col in screener_page._SORT_COLUMNS)["signal"] == "Model signal"
    assert watchlist._HH_LABELS[1] == "Model signal"
    src = inspect.getsource(screener_page)
    assert '_filter_label(h_("Model signal"))' in src and 'st.pills(_("Model signal")' in src
    assert inspect.getsource(dashboard).count('h_("Model signal")') >= 1
    assert 'h_("Model signal history · 12 months")' in inspect.getsource(
        __import__("uvalu.pages_.analysis", fromlist=["x"]))


def _badge_calls(module) -> list[ast.Call]:
    tree = ast.parse(inspect.getsource(module))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and getattr(n.func, "id", getattr(n.func, "attr", None)) == "model_signal_badge_html"]


def test_header_badges_without_a_column_header_are_qualified():
    from uvalu import drawer
    from uvalu.pages_ import analysis
    for module, func in ((drawer, "open_drawer"), (analysis, "render")):
        tree = ast.parse(inspect.getsource(module))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func)
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and getattr(n.func, "id", getattr(n.func, "attr", None)) == "model_signal_badge_html"]
        assert calls, f"{module.__name__}.{func} no longer shows a badge; update _QUALIFIED_SURFACES"
        for call in calls:
            assert any(k.arg == "qualified" and getattr(k.value, "value", None) is True for k in call.keywords), \
                f"{module.__name__}.{func}: badge without qualified=True"


@pytest.fixture
def drafts(monkeypatch):
    monkeypatch.setenv("UVALU_I18N_DRAFTS", "1")
    i18n._load_catalog.clear()
    yield
    i18n._load_catalog.clear()


@pytest.mark.parametrize("lang", i18n.config().enabled_languages)
def test_every_badge_shows_the_qualifier_in_every_language(lang, drafts):
    ctx = dataclasses.replace(i18n._default_ctx(), lang=lang)
    with i18n.using(ctx):
        tooltip = components._html_attr(components.signal_tooltip())
        qualifier = i18n.h_("Model signal")
        for code in screener.SIGNAL_LABELS:
            label = i18n.tr(screener.SIGNAL_LABELS[code])
            plain = components.model_signal_badge_html(code)
            assert html.escape(label) in plain or label in plain
            assert f'title="{tooltip}"' in plain, (lang, code)
            qualified = components.model_signal_badge_html(code, qualified=True)
            assert qualifier in qualified and f'title="{tooltip}"' in qualified, (lang, code)


def _po(lang: str):
    with (ROOT / "locales" / lang / "LC_MESSAGES" / "messages.po").open("rb") as fh:
        return read_po(fh, locale=lang)


@pytest.mark.parametrize("lang", [l for l in i18n.config().enabled_languages if l != "en"])
def test_qualifier_and_labels_are_translated(lang):
    cat = _po(lang)
    needed = ["Model signal", str(screener.SIGNAL_TOOLTIP), *map(str, screener.SIGNAL_LABELS.values())]
    missing = [m for m in needed if not (cat.get(m) and cat.get(m).string)]
    assert not missing, f"{lang}: no translation for {missing}"
