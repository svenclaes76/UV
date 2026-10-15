"""locales/glossary.csv (TR3, docs/translation-review.md T7): the file the
translators start from must say what the app says. A row whose English is a
UI string has the same translation as the .po file, and the retired signal
terms stay out."""
from __future__ import annotations

import csv
from pathlib import Path

from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parents[1]
LANGS = ("nl", "fr", "de", "it", "es")


def _rows():
    with open(ROOT / "locales" / "glossary.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["en", *LANGS, "rule"]
    return rows[1:]


def test_glossary_matches_the_app_translations():
    cats = {lang: read_po(open(ROOT / "locales" / lang / "LC_MESSAGES" / "messages.po", "rb"))
            for lang in LANGS}
    checked, wrong = 0, []
    for row in _rows():
        if cats["nl"].get(row[0]) is None:
            continue                        # a descriptive row ("Shares (count)"), not a UI string
        checked += 1
        for i, lang in enumerate(LANGS, 1):
            app = cats[lang].get(row[0]).string
            if row[i] != app:
                wrong.append(f"{row[0]} [{lang}]: glossary {row[i]!r}, app {app!r}")
    assert checked >= 20
    assert not wrong, "\n".join(wrong)


def test_retired_signal_terms_are_gone_and_current_ones_present():
    terms = {row[0] for row in _rows()}
    assert not {t for t in terms if "BUY" in t or "veto" in t.lower()}
    assert {"Model signal", "Undervalued", "Mid score", "Low score", "Screened out",
            "Model fair value", "Low risk", "Moderate risk", "Elevated risk", "High risk"} <= terms
