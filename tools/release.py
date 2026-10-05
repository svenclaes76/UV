"""Release helper for Uvalu's CalVer ``YYYY.MM.N`` versions (VM-01, VM-03, VM-07).

Usage:
    python tools/release.py next [--date 2026-10-12] [--no-fetch]
        The next version: N = highest v<YYYY.MM>.N tag of that month + 1 (or 1).
    python tools/release.py prepare [--version 2026.10.1] [--date 2026-10-12] [--no-fetch]
        Set pyproject.toml's version, turn "## [Unreleased]" into the release
        section, add a fresh "## [Unreleased]", check the changelog. Commits and
        tags nothing — prints the remaining checklist steps.
    python tools/release.py check-changelog
        VM-07 rules (uvalu/changelog.py). Exit 1 on any problem. Runs in CI.
    python tools/release.py verify-tag v2026.10.1 [--main-ref origin/master]
        The tag guard release CI runs: annotated, CalVer, equals the pyproject
        version at that commit, on the main branch, has a changelog section.
    python tools/release.py notes 2026.10.1
        Print the changelog section body (the GitHub Release text).
    python tools/release.py schema-of v2026.10.1
        The data schema that release expects (highest uvalu/migrations/m####_*.py
        at the tag; 1 for releases from before versioned migrations). Used by
        tools/rollback.py.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uvalu import buildinfo, changelog  # noqa: E402

PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
_PYPROJECT_VERSION_RE = re.compile(r'^(version\s*=\s*)"[^"]*"', re.MULTILINE)


class ReleaseError(Exception):
    pass


def _git(*args: str, root: Path = ROOT, check: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if check and out.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)}: {out.stderr.strip() or out.returncode}")
    return out.stdout.strip()


# ── next version ─────────────────────────────────────────────────────────────

def next_version(tags: "list[str]", today: _dt.date) -> str:
    prefix = f"{today.year:04d}.{today.month:02d}."
    used = []
    for t in tags:
        v = t.removeprefix("v")
        if buildinfo.is_calver(v) and v.startswith(prefix):
            used.append(int(v.rsplit(".", 1)[1]))
    return f"{prefix}{max(used, default=0) + 1}"


def _tags(root: Path, fetch: bool) -> "list[str]":
    if fetch:
        _git("fetch", "--tags", "--quiet", root=root, check=False)
    return _git("tag", "-l", "v*", root=root).split()


# ── prepare ──────────────────────────────────────────────────────────────────

def set_pyproject_version(text: str, version: str) -> str:
    new, n = _PYPROJECT_VERSION_RE.subn(rf'\g<1>"{version}"', text, count=1)
    if n != 1:
        raise ReleaseError("no version = \"...\" line in pyproject.toml")
    return new


def cut_changelog(text: str, version: str, date: str) -> str:
    releases = changelog.parse(text)
    if not releases or not releases[0].is_unreleased:
        raise ReleaseError("CHANGELOG.md has no '## [Unreleased]' section at the top")
    if changelog.find(releases, version):
        raise ReleaseError(f"CHANGELOG.md already has a [{version}] section")
    unrel = releases[0]
    if not unrel.groups or not any(body.strip() for _, body in unrel.groups):
        raise ReleaseError("[Unreleased] is empty — nothing to release")
    heading = re.compile(r"^## \[Unreleased\]\s*$", re.MULTILINE)
    return heading.sub(f"## [Unreleased]\n\n## [{version}] — {date}", text, count=1)


def prepare(version: "str | None", date: _dt.date, *, fetch: bool = True, root: Path = ROOT) -> str:
    version = version or next_version(_tags(root, fetch), date)
    if not buildinfo.is_calver(version):
        raise ReleaseError(f"{version} is not CalVer YYYY.MM.N")
    if not version.startswith(f"{date.year:04d}.{date.month:02d}."):
        raise ReleaseError(f"{version} does not match the release date {date.isoformat()}")
    if f"v{version}" in _tags(root, False):
        raise ReleaseError(f"tag v{version} already exists")
    pyproject, log = root / "pyproject.toml", root / "CHANGELOG.md"
    new_log = cut_changelog(log.read_text(encoding="utf-8"), version, date.isoformat())
    problems = changelog.check(new_log)
    if problems:
        raise ReleaseError("changelog problems:\n  " + "\n  ".join(problems))
    pyproject.write_text(set_pyproject_version(pyproject.read_text(encoding="utf-8"), version),
                         encoding="utf-8")
    log.write_text(new_log, encoding="utf-8")
    return version


# ── tag guard ────────────────────────────────────────────────────────────────

def verify_tag(tag: str, *, main_ref: str = "origin/master", root: Path = ROOT) -> "list[str]":
    problems: list[str] = []
    version = tag.removeprefix("v")
    if not tag.startswith("v") or not buildinfo.is_calver(version):
        problems.append(f"{tag}: tag must be vYYYY.MM.N")
    kind = _git("cat-file", "-t", tag, root=root, check=False)
    if kind != "tag":
        problems.append(f"{tag}: not an annotated tag (git tag -a)")
    try:
        py = tomllib.loads(_git("show", f"{tag}:pyproject.toml", root=root))
        if py.get("project", {}).get("version") != version:
            problems.append(f"{tag}: pyproject.toml at the tag says "
                            f"{py.get('project', {}).get('version')!r}, not {version!r}")
    except (ReleaseError, tomllib.TOMLDecodeError) as exc:
        problems.append(f"{tag}: cannot read pyproject.toml at the tag ({exc})")
    commit = _git("rev-parse", f"{tag}^{{commit}}", root=root, check=False)
    on_main = subprocess.run(["git", "merge-base", "--is-ancestor", commit, main_ref],
                             cwd=root, capture_output=True).returncode == 0
    if not commit or not on_main:
        problems.append(f"{tag}: commit is not on {main_ref}")
    try:
        text = _git("show", f"{tag}:CHANGELOG.md", root=root)
        rel = changelog.find(changelog.parse(text), version)
        if rel is None:
            problems.append(f"{tag}: CHANGELOG.md has no [{version}] section")
        problems += [f"{tag}: {p}" for p in changelog.check(text)]
    except ReleaseError as exc:
        problems.append(f"{tag}: cannot read CHANGELOG.md at the tag ({exc})")
    return problems


# ── schema of a release (VM-10) ──────────────────────────────────────────────

_MIGRATION_FILE_RE = re.compile(r"^m(\d{4})_\w+\.py$")


def schema_of(ref: str, *, root: Path = ROOT) -> int:
    """Data schema the code at ``ref`` expects. Before versioned migrations
    existed the layout was the baseline, schema 1."""
    _git("rev-parse", "--verify", f"{ref}^{{commit}}", root=root)
    listing = _git("ls-tree", "--name-only", f"{ref}:uvalu/migrations", root=root, check=False)
    numbers = [int(m.group(1)) for name in listing.split()
               if (m := _MIGRATION_FILE_RE.match(name))]
    return max(numbers, default=1)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _date(s: "str | None") -> _dt.date:
    return _dt.date.fromisoformat(s) if s else _dt.datetime.now(_dt.timezone.utc).date()


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Uvalu CalVer release helper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("next")
    p.add_argument("--date")
    p.add_argument("--no-fetch", action="store_true")
    p = sub.add_parser("prepare")
    p.add_argument("--version")
    p.add_argument("--date")
    p.add_argument("--no-fetch", action="store_true")
    sub.add_parser("check-changelog")
    p = sub.add_parser("verify-tag")
    p.add_argument("tag")
    p.add_argument("--main-ref", default="origin/master")
    p = sub.add_parser("notes")
    p.add_argument("version")
    p = sub.add_parser("schema-of")
    p.add_argument("ref")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "next":
            print(next_version(_tags(ROOT, not args.no_fetch), _date(args.date)))
        elif args.cmd == "prepare":
            v = prepare(args.version, _date(args.date), fetch=not args.no_fetch)
            print(f"Prepared {v}: pyproject.toml + CHANGELOG.md updated. Next:\n"
                  f"  python tools/i18n_update.py --check && python tools/i18n_compile.py --strict\n"
                  f"  git commit -am \"chore(release): {v}\"\n"
                  f"  git checkout master && git merge --no-ff <branch>\n"
                  f"  git tag -a v{v} -m \"v{v} — <one-line summary>\"\n"
                  f"  git push origin master v{v}   # release CI verifies the tag and publishes the Release")
        elif args.cmd == "check-changelog":
            problems = changelog.check(CHANGELOG.read_text(encoding="utf-8"))
            for pr in problems:
                print(f"CHANGELOG.md: {pr}", file=sys.stderr)
            return 1 if problems else 0
        elif args.cmd == "verify-tag":
            problems = verify_tag(args.tag, main_ref=args.main_ref)
            for pr in problems:
                print(pr, file=sys.stderr)
            if not problems:
                print(f"{args.tag}: ok")
            return 1 if problems else 0
        elif args.cmd == "schema-of":
            print(schema_of(args.ref))
        elif args.cmd == "notes":
            rel = changelog.find(changelog.parse(CHANGELOG.read_text(encoding="utf-8")), args.version)
            if rel is None:
                raise ReleaseError(f"no [{args.version}] section in CHANGELOG.md")
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            sys.stdout.write(rel.body_markdown())
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
