"""Extract UI strings from the code and merge them into every .po file.

Usage:
    python tools/i18n_update.py              # extract → messages.pot, update each .po, report changes
    python tools/i18n_update.py --check      # report only, write nothing (CI: fails if the .pot is stale)
    python tools/i18n_update.py --fix-flags  # only repair %-format flags in the existing files
    python tools/i18n_update.py --since master  # Markdown summary for a PR: texts added/removed
                                                # since that ref, unreviewed entries per language

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

* Entries that didn't change keep their existing line wrapping (Poedit's),
  so a run after a Poedit save only touches what really changed.

Existing translations and their fuzzy (unreviewed) status are preserved;
Babel marks a changed msgid fuzzy and keeps its old translation as a starting
point. Nothing here ever clears a fuzzy flag.
"""
from __future__ import annotations

import io
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.extract import extract_from_dir
from babel.messages.pofile import normalize, read_po, unescape, write_po

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


# Poedit saves through GNU msgcat, whose layout equals `msgcat --width=83`
# (checked against Poedit 3.9 files). Babel's wrapper differs in details (it
# breaks only at spaces and puts the space at the start of the next line), so
# _write also keeps the existing text of every unchanged entry, see
# _preserve_layout.
PO_WIDTH = 83


def _block_key(block: str) -> tuple:
    """What an entry says, independent of how it is wrapped: flags, comments
    and the concatenated contents of every msg* keyword. Source references
    are left out; _preserve_layout swaps those in separately."""
    flags, auto, other = set(), [], []
    strings: dict[str, str] = {}
    cur = None
    for line in block.split("\n"):
        prefix = ""
        if line.startswith(("#|", "#~")):
            prefix, line = line[:2], line[2:].lstrip()
        if line.startswith("#,"):
            flags |= {prefix + f.strip() for f in line[2:].split(",") if f.strip()}
        elif line.startswith("#."):
            auto.append(line[2:].strip())
        elif line.startswith("#:"):
            continue
        elif line.startswith("#"):
            other.append(prefix + line)
        elif line.startswith('"') and cur is not None:
            strings[cur] += line[1:-1]
        elif line:
            kw, _sep, rest = line.partition(" ")
            cur = prefix + kw
            strings[cur] = rest.strip()[1:-1]
    return (frozenset(flags), " ".join(auto), tuple(other), tuple(sorted(strings.items())))


def _refs(block: str) -> list[str]:
    return [ln for ln in block.split("\n") if ln.startswith("#:")]


def _with_refs(old: str, new: str) -> str:
    """The old entry text with the new entry's "#:" source-reference lines."""
    if [t for r in _refs(old) for t in r[2:].split()] == [t for r in _refs(new) for t in r[2:].split()]:
        return old
    lines = old.split("\n")
    at = next((i for i, ln in enumerate(lines) if ln.startswith("#:")), None)
    kept = [ln for ln in lines if not ln.startswith("#:")]
    if at is None:   # no refs before: they go after the comments, before the flags/msg lines
        at = next(i for i, ln in enumerate(kept) if not (ln.startswith(("#.", "# ")) or ln == "#"))
    return "\n".join(kept[:at] + _refs(new) + kept[at:])


def _header_fields(block: str) -> list[tuple[str, str]]:
    lines = [ln[1:-1] for ln in block.split("\n") if ln.startswith('"')]
    fields = []
    for raw in "".join(lines).split("\\n"):
        key, sep, value = raw.partition(":")
        if sep:
            fields.append((key.strip(), value.strip()))
    return fields


def _merge_header(old: str, new: str) -> str:
    """The old header block (Poedit's field order, X-Generator, comments) with
    any field value Babel changed brought in; new fields go at the end."""
    new_fields = dict(_header_fields(new))
    old_fields = dict(_header_fields(old))
    if all(old_fields.get(k) == v for k, v in new_fields.items()):
        return old
    out, seen = [], set()
    for line in old.split("\n"):
        if line.startswith('"'):
            key = line[1:].partition(":")[0].strip()
            if key in new_fields and key not in seen:
                seen.add(key)
                line = f'"{key}: {new_fields[key]}\\n"'
        out.append(line)
    out += [f'"{k}: {v}\\n"' for k, v in new_fields.items() if k not in old_fields]
    return "\n".join(out)


def _preserve_layout(old_text: str, new_text: str) -> str:
    """Babel's output, but every entry that is unchanged apart from line
    wrapping keeps its existing text. Poedit (and hand edits) wrap
    differently from Babel; without this each run after a Poedit save
    rewrote hundreds of unchanged lines."""
    old_blocks = old_text.replace("\r\n", "\n").strip("\n").split("\n\n")
    new_blocks = new_text.replace("\r\n", "\n").strip("\n").split("\n\n")
    by_key = {}
    for b in old_blocks[1:]:
        by_key.setdefault(_block_key(b), b)
    out = [_merge_header(old_blocks[0], new_blocks[0])]
    for b in new_blocks[1:]:
        old = by_key.get(_block_key(b))
        out.append(b if old is None else _with_refs(old, b))
    return "\n\n".join(out) + "\n"


def _previous_lines(previous_id) -> list[str]:
    """'#| msgid …' lines in gettext's layout. Babel's own include_previous
    runs the quoted text through its comment wrapper, which breaks a long
    msgid mid-string ('#| msgid "" "Each track …')."""
    ids = previous_id if isinstance(previous_id, (list, tuple)) else [previous_id]
    out = []
    for kw, text in zip(("msgid", "msgid_plural"), ids):
        for i, ln in enumerate(normalize(text, width=PO_WIDTH).split("\n")):
            out.append(f"#| {kw} {ln}" if i == 0 else f"#| {ln}")
    return out


def _add_previous(text: str, previous: dict) -> str:
    """Insert each fuzzy entry's previous msgid before its msgctxt/msgid line."""
    if not previous:
        return text
    blocks = text.split("\n\n")
    for n, block in enumerate(blocks):
        lines = block.split("\n")
        at = next((i for i, ln in enumerate(lines) if ln.startswith(("msgctxt ", "msgid "))), None)
        if at is None:
            continue
        strings, cur = {}, None
        for ln in lines[at:]:
            if ln.startswith('"') and cur:
                strings[cur] += ln[1:-1]
            elif ln.startswith(("msgctxt ", "msgid ")):
                cur, _sep, rest = ln.partition(" ")
                strings[cur] = rest[1:-1]
            else:
                cur = None
        key = (unescape(f'"{strings["msgctxt"]}"') if "msgctxt" in strings else None,
               unescape(f'"{strings.get("msgid", "")}"'))
        if key in previous:
            blocks[n] = "\n".join(lines[:at] + _previous_lines(previous[key]) + lines[at:])
    return "\n\n".join(blocks)


def _write(path: Path, catalog: Catalog) -> None:
    _normalize_format_flags(catalog)
    previous = {_key(m): m.previous_id for m in catalog if m.id and m.previous_id}
    buf = io.BytesIO()
    write_po(buf, catalog, width=PO_WIDTH, sort_output=False, include_previous=False)
    text = _add_previous(buf.getvalue().decode("utf-8"), previous)
    if path.exists():
        raw = path.read_bytes().decode("utf-8")
        text = _preserve_layout(raw, text)
        if "\r\n" in raw:   # keep the file's own line endings (Poedit on Windows writes CRLF)
            text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


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

    if not (added or removed):
        new.creation_date = old.creation_date   # same msgids: don't touch 7 headers for a timestamp
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


def since(ref: str) -> int:
    """Print a Markdown summary of messages.pot against `ref`, for a PR description."""
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=ROOT, capture_output=True).returncode:
        print(f"unknown ref: {ref}")
        return 1
    proc = subprocess.run(["git", "show", f"{ref}:locales/messages.pot"], cwd=ROOT, capture_output=True)
    old_keys = {_key(m) for m in read_po(io.BytesIO(proc.stdout)) if m.id} if proc.returncode == 0 else set()
    new_keys = {_key(m) for m in _read(POT) if m.id}
    added = sorted(new_keys - old_keys, key=lambda k: (k[0] or "", k[1]))
    removed = sorted(old_keys - new_keys, key=lambda k: (k[0] or "", k[1]))
    unreviewed = {}
    for po_path in sorted(LOCALES.glob("*/LC_MESSAGES/messages.po")):
        n = sum(1 for m in _read(po_path) if m.id and m.fuzzy)
        if n:
            unreviewed[po_path.parts[-3]] = n
    per_lang = ", ".join(f"{lang} {n}" for lang, n in unreviewed.items())
    print(f"**{len(added)} new, {len(removed)} removed** since `{ref}` · "
          + (f"**{sum(unreviewed.values())} unreviewed** ({per_lang})" if unreviewed else "all reviewed"))
    lines = [f"- {sign} `{mid}`" + (f" _({ctx})_" if ctx else "")
             for sign, keys in (("+", added), ("−", removed)) for ctx, mid in keys]
    print("\n".join(lines[:30]))
    if len(lines) > 30:
        print(f"- … and {len(lines) - 30} more")
    return 0


if __name__ == "__main__":
    # Before 3.12 the tokenizer hides calls inside f-strings from Babel, so
    # every _()/h_() in an f-string would be dropped as obsolete.
    if sys.version_info < (3, 12):
        sys.exit("tools/i18n_update.py needs Python 3.12+ (f-string extraction).")
    if "--since" in sys.argv:
        i = sys.argv.index("--since")
        sys.exit(since(sys.argv[i + 1] if i + 1 < len(sys.argv) else "master"))
    if "--fix-flags" in sys.argv:
        sys.exit(fix_flags())
    sys.exit(main("--check" in sys.argv))
