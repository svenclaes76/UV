"""Rebuild locales/review.csv — every msgid with its context note, source
references and all six languages side by side, for a quick read in Excel.

Usage:
    python tools/i18n_review_csv.py

Semicolon-separated with a UTF-8 BOM (Excel opens it directly). Plural
entries show both forms joined with " || ". Run after tools/i18n_update.py.
"""
import csv
from pathlib import Path

from babel.messages.pofile import read_po

LOCALES = Path(__file__).resolve().parent.parent / "locales"
LANGS = ("en", "nl", "fr", "de", "it", "es")


def _text(value) -> str:
    if isinstance(value, (list, tuple)):
        return " || ".join(v or "" for v in value)
    return value or ""


def _key(msg) -> tuple:
    return (msg.context, msg.id if isinstance(msg.id, str) else msg.id[0])


def main() -> None:
    with (LOCALES / "messages.pot").open("rb") as fh:
        template = read_po(fh)
    catalogs = {}
    for lang in LANGS:
        with (LOCALES / lang / "LC_MESSAGES" / "messages.po").open("rb") as fh:
            catalogs[lang] = {_key(m): m for m in read_po(fh, locale=lang) if m.id}

    with (LOCALES / "review.csv").open("w", encoding="utf-8-sig", newline="") as out:
        w = csv.writer(out, delimiter=";")
        w.writerow(["#", "English (source)", "Where / what", "Source file", "Message context", *LANGS])
        n = 0
        for msg in template:
            if not msg.id:
                continue
            n += 1
            note = " ".join(c for c in msg.auto_comments).replace("Context: ", "", 1)
            refs = " ".join(f"{f}:{ln}" for f, ln in msg.locations)
            row = [n, _text(msg.id), note, refs, msg.context or ""]
            for lang in LANGS:
                m = catalogs[lang].get(_key(msg))
                row.append(_text(m.string) if m is not None else "")
            w.writerow(row)
    print(f"wrote {n} rows to {LOCALES / 'review.csv'}")


if __name__ == "__main__":
    main()
