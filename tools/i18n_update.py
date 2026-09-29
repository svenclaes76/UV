"""Extract UI strings from the code and merge them into every .po file.

Usage:
    python tools/i18n_update.py              # extract → messages.pot, update each .po, report changes
    python tools/i18n_update.py --check      # report only, write nothing (CI: fails if the .pot is stale)
    python tools/i18n_update.py --fix-flags  # only repair %-format flags in the existing files

Equivalent to `pybabel extract` + `pybabel update` with Uvalu's keywords and
exclusions, plus two things the plain commands don't do:

* The hand-written "Context:" notes (``#.`` comments) in messages.pot are kept
  for every msgid that still exists — `pybabel extract` would drop them, since
  they aren't in the code.
* New and changed msgids are listed, so they can be drafted and reviewed.

* Texts containing "%" are flagged ``no-python-format``. Babel adds
  ``python-format`` to any text with a "%" on its own, and Poedit then
  rejects translations like "25% bij" as bad %-directives — Uvalu only uses
  {name} placeholders, never %-formatting.

Existing translations and their fuzzy (unreviewed) status are preserved;
Babel marks a changed msgid fuzzy and keeps its old translation as a starting
point. Nothing here ever clears a fuzzy flag.
"""
from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.extract import extract_from_dir
from babel.messages.pofile import read_po, write_po

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "locales"
POT = LOCALES / "messages.pot"

KEYWORDS = {
    "_": None,
    "h_": None,
    "N_": None,
    "ngettext": (1, 2),
    "pgettext": ((1, "c"), 2),
    "lazy_": None,
    "lazy_ngettext": (1, 2),
    "lazy_pgettext": ((1, "c"), 2),
}

# Admin portal and logging stay English (spec §13, L-12); tests/tools/scripts
# have no UI.
EXCLUDE_DIRS = {".venv", ".git", "tests", "tools", "scripts", "docs", "locales", "logkit",
                "__pycache__", ".claude", "data", "logs", ".cache"}
EXCLUDE_FILES = {"uvalu/pages_/admin.py"}


def _key(msg) -> tuple:
    mid = msg.id[0] if isinstance(msg.id, (list, tuple)) else msg.id
    return (msg.context, mid)


def extract() -> Catalog:
    cat = Catalog(project="Uvalu", version="1.0", copyright_holder="Uvalu",
                  msgid_bugs_address="EMAIL@ADDRESS", charset="utf-8",
                  creation_date=datetime.now(timezone.utc))

    def callback(filename, method, options):  # noqa: ARG001
        pass

    def dir_filter(dirpath: str) -> bool:
        return Path(dirpath).name not in EXCLUDE_DIRS

    for filename, lineno, message, comments, context in extract_from_dir(
            str(ROOT), method_map=[("**.py", "python")], keywords=KEYWORDS,
            comment_tags=("Translators:",), callback=callback, strip_comment_tags=True,
            directory_filter=dir_filter):
        if filename.replace("\\", "/") in EXCLUDE_FILES:
            continue
        flags = set()
        text = message if isinstance(message, str) else message[0]
        if "{" in text:
            flags.add("python-brace-format")
        cat.add(message, None, [(filename.replace("\\", "/"), lineno)], auto_comments=comments,
                context=context, flags=flags)
    return cat


def merge_context_notes(new: Catalog, old: Catalog) -> None:
    old_by_key = {_key(m): m for m in old if m.id}
    for m in new:
        if not m.id:
            continue
        prev = old_by_key.get(_key(m))
        if prev is not None and prev.auto_comments:
            code_notes = [c for c in m.auto_comments if c not in prev.auto_comments]
            m.auto_comments = list(prev.auto_comments) + code_notes


def _read(path: Path, locale=None) -> Catalog:
    with path.open("rb") as fh:
        return read_po(fh, locale=locale)


def _normalize_format_flags(catalog: Catalog) -> None:
    """Drop Babel's automatic python-format flag; mark %-texts no-python-format."""
    for m in catalog:
        if not m.id:
            continue
        m.flags.discard("python-format")
        text = m.id if isinstance(m.id, str) else " ".join(m.id)
        if "%" in text:
            m.flags.add("no-python-format")


def fix_flags_text(path: Path) -> int:
    """Line-level repair of a .po/.pot file: every standalone ``python-format``
    flag becomes ``no-python-format``. Only "#," lines change, so Poedit's
    own formatting and every translation stay as they are."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"   # keep the file's own line endings
    lines = raw.split(newline)
    changed = 0
    for i, line in enumerate(lines):
        if not line.startswith("#,"):
            continue
        flags = [f.strip() for f in line[2:].split(",") if f.strip()]
        if "python-format" not in flags:
            continue
        new = [f for f in flags if f != "python-format"]
        if "no-python-format" not in new:
            new.append("no-python-format")
        lines[i] = "#, " + ", ".join(new)
        changed += 1
    if changed:
        path.write_bytes(newline.join(lines).encode("utf-8"))
    return changed


def _write(path: Path, catalog: Catalog) -> None:
    _normalize_format_flags(catalog)
    buf = io.BytesIO()
    write_po(buf, catalog, width=76, sort_output=False, include_previous=True)
    path.write_bytes(buf.getvalue())


def main(check: bool) -> int:
    old = _read(POT)
    new = extract()
    merge_context_notes(new, old)

    old_keys = {_key(m) for m in old if m.id}
    new_keys = {_key(m) for m in new if m.id}
    added = sorted(new_keys - old_keys, key=lambda k: (k[0] or "", k[1]))
    removed = sorted(old_keys - new_keys, key=lambda k: (k[0] or "", k[1]))

    print(f"{len(new_keys)} msgids in code ({len(added)} new, {len(removed)} no longer in code)")
    for ctx, mid in added:
        print(f"  + {('[' + ctx + '] ') if ctx else ''}{mid!r}")
    for ctx, mid in removed:
        print(f"  - {('[' + ctx + '] ') if ctx else ''}{mid!r}")
    if check:
        return 1 if (added or removed) else 0

    _write(POT, new)
    for po_path in sorted(LOCALES.glob("*/LC_MESSAGES/messages.po")):
        lang = po_path.parts[-3]
        cat = _read(po_path, locale=lang)
        cat.update(new, no_fuzzy_matching=False, update_header_comment=False, keep_user_comments=True)
        _write(po_path, cat)
        print(f"updated {po_path.relative_to(ROOT)}")
    return 0


def fix_flags() -> int:
    for path in [POT, *sorted(LOCALES.glob("*/LC_MESSAGES/messages.po"))]:
        print(f"{path.relative_to(ROOT)}: {fix_flags_text(path)} flag lines fixed")
    return 0


if __name__ == "__main__":
    # Before 3.12 the tokenizer hides calls inside f-strings from Babel, so
    # every _()/h_() in an f-string would be dropped as obsolete.
    if sys.version_info < (3, 12):
        sys.exit("tools/i18n_update.py needs Python 3.12+ (f-string extraction).")
    if "--fix-flags" in sys.argv:
        sys.exit(fix_flags())
    sys.exit(main("--check" in sys.argv))
