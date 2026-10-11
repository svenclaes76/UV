"""Release-notes parser + rules (VM-07), shared by the release tooling
(``tools/release.py``) and the in-app What's new view (VD-04).

Two files, one format:

- ``CHANGELOG.md`` — the internal record: every change in full, including
  operator and admin detail. It is the GitHub Release body.
- ``RELEASE_NOTES.md`` — the public notes the app shows under *What's new*:
  only what a subscriber notices, written as the value it brings them.
  Every CalVer release in the changelog has a section here with the same
  version and date.

Format (Keep a Changelog)::

    ## [Unreleased]

    ## [2026.10.1] — 2026-10-12

    Optional intro paragraph.

    ### Added
    - ...

Rules enforced for CalVer releases (older SemVer sections are history and are
only checked for order and duplicates):

- groups are only ``Added`` / ``Changed`` / ``Fixed`` / ``Removed`` (public
  notes: ``New`` / ``Improved`` / ``Fixed`` / ``Removed``), each used at most
  once and never empty, at least one group per release;
- a release date is present and falls in the version's year and month;
- ``## [Unreleased]`` exists and comes first; versions descend; no duplicates.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from uvalu.buildinfo import ROOT, is_calver

CHANGELOG = ROOT / "CHANGELOG.md"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"
GROUPS = ("Added", "Changed", "Fixed", "Removed")
PUBLIC_GROUPS = ("New", "Improved", "Fixed", "Removed")
UNRELEASED = "Unreleased"

_RELEASE_RE = re.compile(r"^## \[(?P<version>[^\]]+)\](?:\s*[—–-]\s*(?P<date>\S+))?\s*$")
_GROUP_RE = re.compile(r"^### (?P<name>.+?)\s*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Release:
    version: str
    date: "str | None"
    intro: str = ""
    groups: "list[tuple[str, str]]" = field(default_factory=list)   # (name, markdown body)
    line: int = 0

    @property
    def is_unreleased(self) -> bool:
        return self.version == UNRELEASED

    @property
    def is_calver(self) -> bool:
        return is_calver(self.version)

    def body_markdown(self) -> str:
        """The section without its ``## [x]`` heading — the GitHub Release body."""
        parts = [self.intro] if self.intro else []
        parts += [f"### {name}\n\n{body}".rstrip() for name, body in self.groups]
        return "\n\n".join(parts).strip() + "\n"


def parse(text: str) -> "list[Release]":
    releases: list[Release] = []
    cur: "Release | None" = None
    group: "str | None" = None
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        # a trailing "---" separator belongs to the file layout, not the section
        body = re.sub(r"\n*-{3,}\s*$", "", body).strip()
        if cur is not None:
            if group is None:
                cur.intro = body
            else:
                cur.groups.append((group, body))
        buf.clear()

    for n, line in enumerate(text.splitlines(), 1):
        m = _RELEASE_RE.match(line)
        if m:
            flush()
            cur = Release(m["version"].strip(), m["date"], line=n)
            releases.append(cur)
            group = None
            continue
        if cur is None:
            continue
        g = _GROUP_RE.match(line)
        if g:
            flush()
            group = g["name"]
            continue
        buf.append(line)
    flush()
    return releases


def _version_key(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return ()


def check(text: str, groups: "tuple[str, ...]" = GROUPS) -> "list[str]":
    problems: list[str] = []
    releases = parse(text)
    if not releases or not releases[0].is_unreleased:
        problems.append("the first section must be '## [Unreleased]'")
    seen: set[str] = set()
    prev: "tuple | None" = None
    for r in releases:
        where = f"line {r.line} [{r.version}]"
        if r.version in seen:
            problems.append(f"{where}: duplicate version")
        seen.add(r.version)
        if r.is_unreleased:
            if r.line != releases[0].line:
                problems.append(f"{where}: [Unreleased] must be the first section")
            continue
        key = _version_key(r.version)
        if not key:
            problems.append(f"{where}: not a version number")
        elif prev is not None and key >= prev:
            problems.append(f"{where}: versions must descend (newest first)")
        prev = key or prev
        if not r.is_calver:
            continue                      # pre-CalVer history: order/duplicates only
        if not r.date or not _DATE_RE.match(r.date):
            problems.append(f"{where}: release date 'YYYY-MM-DD' missing")
        else:
            y, m, _ = r.version.split(".")
            if r.date[:7] != f"{y}-{m}":
                problems.append(f"{where}: date {r.date} is not in {y}-{m}")
        names = [g for g, _ in r.groups]
        if not names:
            problems.append(f"{where}: no {'/'.join(groups)} group")
        for g in names:
            if g not in groups:
                problems.append(f"{where}: group '### {g}' — use only {', '.join(groups)}")
        for g in {g for g in names if names.count(g) > 1}:
            problems.append(f"{where}: group '### {g}' used twice")
        for g, body in r.groups:
            if not body.strip():
                problems.append(f"{where}: group '### {g}' is empty")
    return problems


def check_public(public_text: str, changelog_text: str) -> "list[str]":
    """The public notes' own rules, plus: the same CalVer releases (version and
    date) as the changelog — no release missing from What's new, none invented."""
    problems = check(public_text, PUBLIC_GROUPS)
    public = {r.version: r.date for r in parse(public_text) if r.is_calver}
    internal = {r.version: r.date for r in parse(changelog_text) if r.is_calver}
    for v, date in internal.items():
        if v not in public:
            problems.append(f"[{v}]: in CHANGELOG.md but has no public notes")
        elif public[v] != date:
            problems.append(f"[{v}]: date {public[v]} differs from CHANGELOG.md ({date})")
    for v in public.keys() - internal.keys():
        problems.append(f"[{v}]: public notes for a release CHANGELOG.md doesn't have")
    return problems


def find(releases: "list[Release]", version: str) -> "Release | None":
    version = version.removeprefix("v")
    return next((r for r in releases if r.version == version), None)


# ── cached load for the app ──────────────────────────────────────────────────

_lock = threading.Lock()
_cache: "tuple[float, list[Release]] | None" = None


def load(path: "Path | None" = None) -> "list[Release]":
    """Parsed public notes (RELEASE_NOTES.md), re-read only when the file changes."""
    global _cache
    p = path or RELEASE_NOTES
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return []
    with _lock:
        if path is None and _cache is not None and _cache[0] == mtime:
            return _cache[1]
        releases = parse(p.read_text(encoding="utf-8"))
        if path is None:
            _cache = (mtime, releases)
        return releases
