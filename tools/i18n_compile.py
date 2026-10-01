"""Check and compile Uvalu's translation files.

Usage:
    python tools/i18n_compile.py            # check + compile, drafts (fuzzy) fall back to English
    python tools/i18n_compile.py --strict   # also fail if any entry is still unreviewed (for release CI)

Why not plain `pybabel compile`: Babel guesses "python-format" from any '%' in
the English text (e.g. "BE 30% only") and then reports false errors. Uvalu uses
{name} placeholders, not %-formatting, so this script checks those instead.
Poedit and GNU msgfmt respect the no-python-format flag and are fine to use.
"""
import re
import sys
from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

LOCALES = Path(__file__).resolve().parent.parent / "locales"
BRACES = re.compile(r"\{(\w+)\}")
MARKUP = re.compile(r"</?\w+>|\*\*")


def _placeholders(text: str) -> set[str]:
    return set(BRACES.findall(text or ""))


def check_and_compile(strict: bool) -> int:
    errors, drafts = [], 0
    for po_path in sorted(LOCALES.glob("*/LC_MESSAGES/messages.po")):
        lang = po_path.parts[-3]
        with po_path.open("rb") as fh:
            catalog = read_po(fh, locale=lang)
        for msg in catalog:
            if not msg.id:
                continue
            ids = msg.id if isinstance(msg.id, (list, tuple)) else (msg.id,)
            strs = msg.string if isinstance(msg.string, (list, tuple)) else (msg.string,)
            wanted = set().union(*(_placeholders(i) for i in ids))
            for s in strs:
                if not s:
                    continue
                got = _placeholders(s)
                if not got <= wanted:
                    errors.append(f"{lang}: unknown placeholder {got - wanted} in {ids[0]!r}")
                if len(ids) == 1 and got != wanted:
                    errors.append(f"{lang}: placeholders {sorted(got)} != {sorted(wanted)} in {ids[0]!r}")
                if sorted(MARKUP.findall(s)) != sorted(MARKUP.findall(ids[0])):
                    errors.append(f"{lang}: markup differs in {ids[0]!r}")
            if msg.fuzzy:
                drafts += 1
        # Fuzzy (unreviewed) entries are left out of the .mo, so they show in English.
        with (po_path.with_suffix(".mo")).open("wb") as fh:
            write_mo(fh, catalog, use_fuzzy=False)
    for e in errors:
        print("ERROR", e)
    print(f"{drafts} unreviewed entries across all languages")
    if errors or (strict and drafts):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(check_and_compile("--strict" in sys.argv))
