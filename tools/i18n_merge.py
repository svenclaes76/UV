"""Resolve translation-file conflicts after a merge, then rebuild the catalogs.

Usage (in the middle of a `git merge`, once every non-locale conflict is resolved):
    python tools/i18n_merge.py

Also safe to run after a clean merge that touched locales/ on both sides.

Why not "take ours" or "take theirs": each branch adds its own entries,
drafts and reviewed flags to the six .po files, so picking one side throws
the other branch's work away. Instead every entry is merged three-way
against the common ancestor (git stages 1/2/3):

* Entry only on one side, or changed on one side only → that side wins.
* Both sides made the same change → kept.
* Both sides changed it differently → our translation is kept, marked
  unreviewed (fuzzy), and theirs is added as a "# merge:" comment, so it
  shows in Poedit and must be re-approved before a release.
* messages.pot: Context notes from both sides are kept.

Then tools/i18n_update.py re-extracts from the merged code, tools/i18n_compile.py
rebuilds the .mo files, tools/i18n_review_csv.py rebuilds review.csv, and
everything under locales/ is staged.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from babel.messages.pofile import read_po  # noqa: E402

from tools import i18n_compile, i18n_review_csv, i18n_update  # noqa: E402

LOCALES = ROOT / "locales"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def _stage(path: str, n: int, locale=None):
    """The catalog at merge stage n (1 base, 2 ours, 3 theirs), or None if absent."""
    proc = subprocess.run(["git", "show", f":{n}:{path}"], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        return None
    return read_po(io.BytesIO(proc.stdout), locale=locale)


def _entries(catalog) -> dict:
    return {} if catalog is None else {i18n_update._key(m): m for m in catalog if m.id}


def _sig(msg, template: bool) -> tuple:
    if template:
        return tuple(msg.auto_comments)
    strings = msg.string if isinstance(msg.string, (list, tuple)) else (msg.string,)
    return tuple(strings), msg.fuzzy


def _text(msg) -> str:
    strings = msg.string if isinstance(msg.string, (list, tuple)) else (msg.string,)
    return " || ".join(s or "" for s in strings)


def _put(catalog, msg) -> None:
    catalog.delete(msg.id, context=msg.context)         # __setitem__ would merge flags, not replace
    catalog[msg.id] = msg


def merge_catalogs(base, ours, theirs, template: bool = False) -> tuple:
    """Three-way merge of two catalogs into `ours` (modified in place).
    Returns (ours, keys that both sides changed differently)."""
    b, o, t = _entries(base), _entries(ours), _entries(theirs)
    conflicts = []
    for key, theirs_msg in t.items():
        ours_msg, base_msg = o.get(key), b.get(key)
        if ours_msg is None:
            if base_msg is None or _sig(base_msg, template) != _sig(theirs_msg, template):
                _put(ours, theirs_msg)                  # added by them, or changed by them after we dropped it
            continue
        so, st = _sig(ours_msg, template), _sig(theirs_msg, template)
        if so == st:
            continue
        sb = _sig(base_msg, template) if base_msg is not None else None
        if sb == so:
            _put(ours, theirs_msg)                      # only they changed it
        elif sb == st:
            continue                                    # only we changed it
        elif template:
            ours_msg.auto_comments = list(ours_msg.auto_comments) + [
                c for c in theirs_msg.auto_comments if c not in ours_msg.auto_comments]
        else:
            ours_msg.flags.add("fuzzy")
            ours_msg.user_comments = [c for c in ours_msg.user_comments if not c.startswith("merge:")]
            ours_msg.user_comments.append(f"merge: other branch had: {_text(theirs_msg)}")
            conflicts.append(key)
    return ours, conflicts


def main() -> int:
    unmerged = [p for p in _git("diff", "--name-only", "--diff-filter=U").splitlines() if p]
    other = [p for p in unmerged if not p.startswith("locales/")]
    if other:
        print("Resolve these conflicts first (the catalogs are rebuilt from the merged code):")
        for p in other:
            print(f"  {p}")
        return 1

    total = 0
    for path in unmerged:
        if not path.endswith((".po", ".pot")):
            continue                                    # .mo and review.csv are rebuilt below
        template = path.endswith(".pot")
        locale = None if template else Path(path).parts[-3]
        ours = _stage(path, 2, locale)
        theirs = _stage(path, 3, locale)
        if ours is None or theirs is None:
            print(f"{path}: deleted on one side — resolve by hand")
            return 1
        merged, conflicts = merge_catalogs(_stage(path, 1, locale), ours, theirs, template)
        i18n_update._write(ROOT / path, merged)
        total += len(conflicts)
        print(f"{path}: merged" + (f", {len(conflicts)} changed on both sides (now unreviewed)" if conflicts else ""))
        for ctx, mid in conflicts:
            print(f"  ! {('[' + ctx + '] ') if ctx else ''}{mid!r}")

    if i18n_update.main(check=False) != 0:
        return 1
    compile_rc = i18n_compile.check_and_compile(strict=False)
    i18n_review_csv.main()
    _git("add", "--", "locales")
    print(f"\nlocales/ staged. {total} entries need re-review (search '# merge:' in Poedit)."
          if total else "\nlocales/ staged.")
    return compile_rc


if __name__ == "__main__":
    if sys.version_info < (3, 12):
        sys.exit("tools/i18n_merge.py needs Python 3.12+ (f-string extraction).")
    sys.exit(main())
