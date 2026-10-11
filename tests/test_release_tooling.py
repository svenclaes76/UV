"""uvalu/changelog.py + tools/release.py — changelog rules (VM-07), next
CalVer number (VM-01) and the release-tag guard (VM-03)."""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import release
from uvalu import changelog

ROOT = Path(__file__).resolve().parents[1]
HAS_GIT = shutil.which("git") is not None

GOOD = """# Changelog

Intro text.

---

## [Unreleased]

### Added

- Something new.

## [2026.10.1] — 2026-10-12

You only need to restart.

### Added

- A version marker in the footer.

### Fixed

- The thing that was wrong.

---

## [2.1.1] — 2026-10-05

PATCH — legal texts.

### Docs

- legacy groups are history and are not checked.
"""


PUBLIC = """# Release notes

---

## [Unreleased]

### New

- Something you'll like.

## [2026.10.1] — 2026-10-12

See which version you're on.

### New

- The version at the bottom of every page.

### Fixed

- The thing that was wrong.
"""


# ── changelog parser + rules ─────────────────────────────────────────────────

def test_parse_sections_groups_and_intro():
    rels = changelog.parse(GOOD)
    assert [r.version for r in rels] == ["Unreleased", "2026.10.1", "2.1.1"]
    r = rels[1]
    assert r.date == "2026-10-12" and r.is_calver
    assert r.intro == "You only need to restart."
    assert [g for g, _ in r.groups] == ["Added", "Fixed"]
    assert r.groups[1][1] == "- The thing that was wrong."     # trailing '---' stripped
    assert r.body_markdown().startswith("You only need to restart.\n\n### Added")


def test_good_changelog_has_no_problems():
    assert changelog.check(GOOD) == []


def test_real_changelog_passes():
    assert changelog.check((ROOT / "CHANGELOG.md").read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda s: s.replace("### Fixed", "### Bugfixes"), "use only"),
    (lambda s: s.replace("— 2026-10-12", ""), "date"),
    (lambda s: s.replace("2026-10-12", "2026-11-02"), "not in 2026-10"),
    (lambda s: s.replace("- The thing that was wrong.", ""), "is empty"),
    (lambda s: s.replace("### Fixed", "### Added"), "used twice"),
    (lambda s: s.replace("## [Unreleased]\n", ""), "Unreleased"),
    (lambda s: s.replace("## [2.1.1]", "## [2026.11.1]"), "descend"),
    (lambda s: s.replace("## [2.1.1] — 2026-10-05", "## [2026.10.1] — 2026-10-05"), "duplicate"),
])
def test_check_reports(mutate, needle):
    problems = changelog.check(mutate(GOOD))
    assert any(needle in p for p in problems), problems


def test_release_without_groups_is_reported():
    text = "## [Unreleased]\n\n## [2026.10.1] — 2026-10-12\n\nJust prose.\n"
    assert any("no Added" in p for p in changelog.check(text))


def test_real_release_notes_pass():
    assert changelog.check_public((ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8"),
                                  (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")) == []


def test_public_notes_pair_with_changelog():
    assert changelog.check_public(PUBLIC, GOOD) == []
    missing = PUBLIC.split("## [2026.10.1]")[0]
    assert any("has no public notes" in p for p in changelog.check_public(missing, GOOD))
    redated = PUBLIC.replace("2026-10-12", "2026-10-13")
    assert any("differs from CHANGELOG.md" in p for p in changelog.check_public(redated, GOOD))
    extra = PUBLIC.replace("## [2026.10.1] — 2026-10-12", "## [2026.10.2] — 2026-10-12")
    assert any("doesn't have" in p for p in changelog.check_public(extra, GOOD))


def test_public_notes_use_their_own_groups():
    assert any("use only New" in p for p in changelog.check_public(GOOD, GOOD))


def test_load_reads_the_public_notes_and_caches_until_file_changes(tmp_path, monkeypatch):
    p = tmp_path / "RELEASE_NOTES.md"
    p.write_text(GOOD, encoding="utf-8")
    monkeypatch.setattr(changelog, "RELEASE_NOTES", p)
    monkeypatch.setattr(changelog, "_cache", None)
    first = changelog.load()
    assert changelog.load() is first
    import os
    p.write_text(GOOD.replace("Something new.", "Else."), encoding="utf-8")
    os.utime(p, (10**9, 10**9))
    assert changelog.load() is not first


# ── next version / prepare ───────────────────────────────────────────────────

def test_next_version_counts_within_month():
    d = dt.date(2026, 10, 20)
    assert release.next_version([], d) == "2026.10.1"
    assert release.next_version(["v2.1.1", "v2026.09.4"], d) == "2026.10.1"
    assert release.next_version(["v2026.10.1", "v2026.10.2", "v2026.11.1"], d) == "2026.10.3"
    assert release.next_version(["v2026.10.9", "v2026.10.10"], d) == "2026.10.11"
    assert release.next_version([], dt.date(2027, 1, 3)) == "2027.01.1"


def test_set_pyproject_version_only_touches_project_version():
    text = '[project]\nname = "uv"\nversion = "2.1.1"\n\n[tool.x]\nversion = "9"\n'
    out = release.set_pyproject_version(text, "2026.10.1")
    assert 'version = "2026.10.1"' in out and 'version = "9"' in out


def test_cut_changelog_moves_unreleased_into_release():
    out = release.cut_changelog(GOOD, "2026.10.2", "2026-10-20")
    rels = changelog.parse(out)
    assert [r.version for r in rels[:3]] == ["Unreleased", "2026.10.2", "2026.10.1"]
    assert rels[0].groups == []
    assert rels[1].groups == [("Added", "- Something new.")]
    assert changelog.check(out) == []


def test_cut_changelog_keeps_intro_paragraph_separate():
    text = GOOD.replace("## [Unreleased]\n\n### Added", "## [Unreleased]\n\nRestart only.\n\n### Added")
    out = release.cut_changelog(text, "2026.10.2", "2026-10-20")
    assert "## [2026.10.2] — 2026-10-20\n\nRestart only." in out
    assert changelog.parse(out)[1].intro == "Restart only."


def test_cut_changelog_refuses_empty_unreleased():
    empty = GOOD.replace("### Added\n\n- Something new.\n\n## [2026.10.1]", "## [2026.10.1]", 1)
    with pytest.raises(release.ReleaseError, match="empty"):
        release.cut_changelog(empty, "2026.10.2", "2026-10-20")


def test_cut_changelog_refuses_existing_version():
    with pytest.raises(release.ReleaseError, match="already"):
        release.cut_changelog(GOOD, "2026.10.1", "2026-10-20")


# ── against a throw-away git repo ────────────────────────────────────────────

def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    if not HAS_GIT:
        pytest.skip("git not installed")
    _git(tmp_path, "init", "-q", "-b", "master")
    for k, v in (("user.email", "t@example.com"), ("user.name", "t"),
                 ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        _git(tmp_path, "config", k, v)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "uv"\nversion = "2.1.1"\n')
    (tmp_path / "CHANGELOG.md").write_text(GOOD.replace("## [2026.10.1] — 2026-10-12", "## [2.2.0] — 2026-10-06"),
                                           encoding="utf-8")
    (tmp_path / "RELEASE_NOTES.md").write_text(PUBLIC.split("## [2026.10.1]")[0], encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_prepare_bumps_and_cuts(repo):
    v = release.prepare(None, dt.date(2026, 10, 20), fetch=False, root=repo)
    assert v == "2026.10.1"
    assert 'version = "2026.10.1"' in (repo / "pyproject.toml").read_text()
    for name in ("CHANGELOG.md", "RELEASE_NOTES.md"):
        rels = changelog.parse((repo / name).read_text(encoding="utf-8"))
        assert rels[0].is_unreleased and rels[1].version == "2026.10.1" and rels[1].date == "2026-10-20"


def test_prepare_refuses_empty_public_notes(repo):
    (repo / "RELEASE_NOTES.md").write_text("## [Unreleased]\n", encoding="utf-8")
    with pytest.raises(release.ReleaseError, match=r"RELEASE_NOTES.md: \[Unreleased\] is empty"):
        release.prepare(None, dt.date(2026, 10, 20), fetch=False, root=repo)
    assert 'version = "2.1.1"' in (repo / "pyproject.toml").read_text()


def test_prepare_rejects_version_outside_date_month(repo):
    with pytest.raises(release.ReleaseError, match="does not match"):
        release.prepare("2026.09.1", dt.date(2026, 10, 20), fetch=False, root=repo)


def _release(repo: Path, version: str, *, annotated=True) -> str:
    release.prepare(version, dt.date(2026, 10, 20), fetch=False, root=repo)
    _git(repo, "commit", "-qam", f"chore(release): {version}")
    tag = f"v{version}"
    if annotated:
        _git(repo, "tag", "-a", tag, "-m", f"{tag} — test")
    else:
        _git(repo, "tag", tag)
    return tag


def test_verify_tag_accepts_good_release(repo):
    tag = _release(repo, "2026.10.1")
    assert release.verify_tag(tag, main_ref="master", root=repo) == []


def test_verify_tag_rejects_lightweight(repo):
    tag = _release(repo, "2026.10.1", annotated=False)
    assert any("annotated" in p for p in release.verify_tag(tag, main_ref="master", root=repo))


def test_verify_tag_rejects_version_mismatch(repo):
    _git(repo, "tag", "-a", "v2026.10.5", "-m", "wrong")
    problems = release.verify_tag("v2026.10.5", main_ref="master", root=repo)
    assert any("pyproject" in p for p in problems)
    assert any("no [2026.10.5] section" in p for p in problems)


def test_verify_tag_rejects_non_calver(repo):
    _git(repo, "tag", "-a", "v2.1.1", "-m", "old style")
    assert any("vYYYY.MM.N" in p for p in release.verify_tag("v2.1.1", main_ref="master", root=repo))


def test_verify_tag_rejects_commit_off_main(repo):
    _git(repo, "checkout", "-q", "-b", "side")
    tag = _release(repo, "2026.10.1")
    _git(repo, "checkout", "-q", "master")
    assert any("not on master" in p for p in release.verify_tag(tag, main_ref="master", root=repo))


def test_notes_cli_prints_section(capsys, monkeypatch, tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(GOOD, encoding="utf-8")
    monkeypatch.setattr(release, "CHANGELOG", p)
    assert release.main(["notes", "2026.10.1"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("You only need to restart.") and "### Fixed" in out
    assert release.main(["notes", "2099.01.1"]) == 1


def test_notes_cli_public(capsys, monkeypatch, tmp_path):
    p = tmp_path / "RELEASE_NOTES.md"
    p.write_text(PUBLIC, encoding="utf-8")
    monkeypatch.setattr(release, "RELEASE_NOTES", p)
    assert release.main(["notes", "2026.10.1", "--public"]) == 0
    assert capsys.readouterr().out.startswith("See which version you're on.")
