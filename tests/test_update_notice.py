"""uvalu/update_notice.py — one-time What's new notice (VD-05) and the reload
prompt when another build is stamped (VD-09)."""
import pytest
from streamlit.testing.v1 import AppTest

from uvalu import buildinfo, changelog, update_notice

NOTES = """## [Unreleased]

## [2031.07.4] — 2031-07-09

### Added

- Something.

## [2031.07.3] — 2031-07-02

### Fixed

- Something else.
"""
RELEASES = changelog.parse(NOTES)


def _info(version="2031.07.4", **kw):
    base = dict(version=version, display_version=version, commit="fedcba9", commit_full="f" * 40,
                built_at="2031-07-09T08:07:06Z", environment="production", is_release=True,
                dirty=False, source="stamp")
    base.update(kw)
    return buildinfo.BuildInfo(**base)


@pytest.mark.parametrize("version,last,want", [
    ("2031.07.4", "2031.07.3", True),
    ("2031.07.4", "2031.07.4", False),
    ("2031.07.4", "2031.08.1", False),
    ("2031.07.10", "2031.07.9", True),       # numeric, not string, order
    ("2031.07.4", "2.1.1", True),            # pre-CalVer last seen is older
    ("2031.07.4", None, False),              # nothing recorded: handled by first-record path
    ("2.1.1", "2.1.0", False),               # pre-CalVer builds announce nothing
])
def test_is_newer(version, last, want):
    assert update_notice.is_newer(version, last) is want


def test_pending_notice_needs_a_changelog_section():
    assert update_notice.pending_notice({"last_seen_version": "2031.07.3"}, _info(), RELEASES) == "2031.07.4"
    assert update_notice.pending_notice({"last_seen_version": "2031.07.3"}, _info("2031.07.5"), RELEASES) is None
    assert update_notice.pending_notice({"last_seen_version": "2031.07.4"}, _info(), RELEASES) is None


@pytest.fixture
def notice_env(isolated_data, monkeypatch, tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(NOTES, encoding="utf-8")
    monkeypatch.setattr(changelog, "CHANGELOG", p)
    monkeypatch.setattr(changelog, "_cache", None)
    monkeypatch.setattr(buildinfo, "_current", _info())
    yield
    buildinfo.reset()


def _run_notice():
    def _script():
        from uvalu import update_notice
        update_notice.render_whats_new_notice("test@example.com")

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def _notice_shown(at) -> bool:
    return any("updated to version" in m.value for m in at.markdown)


def test_first_visit_records_silently(notice_env):
    import settings
    at = _run_notice()
    assert not _notice_shown(at)
    assert settings.load_settings("test@example.com")["last_seen_version"] == "2031.07.4"


def test_notice_after_update_until_dismissed(notice_env):
    import settings
    s = settings.load_settings("test@example.com")
    s["last_seen_version"] = "2031.07.3"
    settings.save_settings(s, "test@example.com")
    at = _run_notice()
    assert _notice_shown(at)
    assert "2031.07.4" in "".join(m.value for m in at.markdown)
    at.button(key="uv_whats_new_dismiss").click().run()
    assert not _notice_shown(at)
    assert settings.load_settings("test@example.com")["last_seen_version"] == "2031.07.4"
    assert not _notice_shown(_run_notice())              # one-time


def test_mark_seen_is_a_no_op_when_unchanged(notice_env, monkeypatch):
    import settings
    update_notice.mark_seen("test@example.com", "2031.07.4")
    calls = []
    monkeypatch.setattr(settings, "save_settings", lambda *a, **k: calls.append(a))
    update_notice.mark_seen("test@example.com", "2031.07.4")
    assert calls == []


# ── reload prompt ────────────────────────────────────────────────────────────

def test_needs_reload():
    assert update_notice.needs_reload("a@1", "b@2")
    assert not update_notice.needs_reload("a@1", "a@1")
    assert not update_notice.needs_reload(None, "a@1")
    assert not update_notice.needs_reload("a@1", None)


def test_stamped_build_id_reads_file(tmp_path):
    p = tmp_path / "build_info.json"
    assert update_notice.stamped_build_id(p) is None
    buildinfo.write(_info(), p)
    assert update_notice.stamped_build_id(p) == "2031.07.4@2031-07-09T08:07:06Z"


def test_reload_prompt_appears_when_another_build_is_stamped(monkeypatch):
    stamped = {"id": "2031.07.4@2031-07-09T08:07:06Z"}
    monkeypatch.setattr(update_notice, "stamped_build_id", lambda path=None: stamped["id"])

    def _script():
        from uvalu import update_notice
        update_notice.remember_session_build()
        update_notice.render_reload_prompt()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not any("new version" in m.value for m in at.markdown)
    stamped["id"] = "2031.07.5@2031-07-20T08:00:00Z"
    at.run()
    assert any("A new version of Uvalu is available" in m.value for m in at.markdown)
