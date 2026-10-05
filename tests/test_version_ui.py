"""Version surfaces in the UI: footer marker (VD-01), environment marker
(VD-03), About + What's new page (VD-02, VD-04) — always fed by
uvalu.buildinfo, never hard-coded (VD-10)."""
import pytest
from streamlit.testing.v1 import AppTest

from uvalu import buildinfo, changelog, shell
from uvalu import nav as nav_registry
from uvalu.pages_ import about


def _info(**kw) -> buildinfo.BuildInfo:
    base = dict(version="2031.07.4", display_version="2031.07.4-dev+fedcba9", commit="fedcba9",
                commit_full="fedcba9" + "0" * 33, built_at="2031-07-09T08:07:06Z",
                environment="test", is_release=False, dirty=False, source="stamp")
    base.update(kw)
    return buildinfo.BuildInfo(**base)


@pytest.fixture
def fake_build(monkeypatch):
    """A recognisable build no source file contains — proves the UI reads it."""
    def use(**kw):
        info = _info(**kw)
        monkeypatch.setattr(buildinfo, "_current", info)
        return info
    yield use
    buildinfo.reset()


@pytest.fixture(autouse=True)
def _clean_nav_registry():
    saved = dict(nav_registry.pages)
    nav_registry.pages.clear()
    yield
    nav_registry.pages.clear()
    nav_registry.pages.update(saved)


NOTES = """# Changelog

## [Unreleased]

### Added

- Coming soon.

## [2031.07.4] — 2031-07-09

You only need to restart.

### Added

- Version in the footer.

### Fixed

- A wrong number.

## [2031.07.3] — 2031-07-02

### Removed

- An old screen.

## [2.1.1] — 2026-10-05

### Docs

- legacy
"""


# ── environment marker ───────────────────────────────────────────────────────

@pytest.mark.parametrize("env,label,color", [("development", "DEV", "#B45309"), ("test", "TEST", "#6D28D9"),
                                             ("qa", "QA", "#B91C1C")])
def test_env_marker_for_non_production(env, label, color):
    html = shell.env_marker_html(_info(environment=env))
    assert f">{label}</div>" in html and color in html and "uv-env-stripe" in html


def test_no_env_marker_in_production():
    assert shell.env_marker_html(_info(environment="production")) == ""


# ── footer version marker ────────────────────────────────────────────────────

def test_footer_shows_build_version_linking_to_about(fake_build):
    fake_build()

    def _script():
        import streamlit as st
        from uvalu import nav as nav_registry, shell
        from uvalu.pages_ import about as about_page
        nav_registry.pages["about"] = st.Page(about_page.render, title="About Uvalu", url_path="about")
        shell.render_version_marker()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    links = at.get("page_link")
    assert [l.proto.label for l in links] == ["v2031.07.4-dev+fedcba9"]
    assert links[0].proto.page.endswith("about")


def test_footer_marker_without_about_page_is_plain_text(fake_build):
    fake_build(display_version="2031.07.4", is_release=True)

    def _script():
        from uvalu import shell
        shell.render_version_marker()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert "v2031.07.4" in "".join(m.value for m in at.markdown)


# ── About page ───────────────────────────────────────────────────────────────

def test_details_line():
    assert about.details_line(_info()) == \
        "Uvalu 2031.07.4-dev+fedcba9 (fedcba9) · built 2031-07-09 08:07:06 UTC · test"


def test_visible_releases_calver_only_plus_unreleased_outside_production():
    rels = changelog.parse(NOTES)
    assert [r.version for r in about.visible_releases(rels, production=True)] == ["2031.07.4", "2031.07.3"]
    assert [r.version for r in about.visible_releases(rels, production=False)] == \
        ["Unreleased", "2031.07.4", "2031.07.3"]


def _run_about(monkeypatch, tmp_path, query=None, role="Viewer"):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(NOTES, encoding="utf-8")
    monkeypatch.setattr(changelog, "CHANGELOG", p)
    monkeypatch.setattr(changelog, "_cache", None)

    def _script():
        import streamlit as st
        from uvalu.pages_ import about as about_page
        about_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.session_state["user_email"] = "viewer@example.com"
    at.session_state["user_role"] = role
    if query:
        at.query_params.update(query)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_about_shows_build_details(monkeypatch, tmp_path, fake_build):
    fake_build()
    at = _run_about(monkeypatch, tmp_path)
    html = "".join(m.value for m in at.markdown)
    for text in ("2031.07.4-dev+fedcba9", "fedcba9", "2031-07-09 08:07:06 UTC", "test (TEST)", "M1"):
        assert text in html
    assert "/commit/" not in html                     # commit link is for admins only
    assert at.code[0].value == about.details_line(_info())


def test_about_commit_links_for_admin(monkeypatch, tmp_path, fake_build):
    fake_build()
    at = _run_about(monkeypatch, tmp_path, role="Admin")
    assert "/commit/fedcba9" in "".join(m.value for m in at.markdown)


def test_whats_new_lists_releases_newest_first(monkeypatch, tmp_path, fake_build):
    fake_build(environment="production", display_version="2031.07.4", is_release=True)
    at = _run_about(monkeypatch, tmp_path)
    labels = [e.label for e in at.expander]
    assert labels[0].startswith("2031.07.4 · 2031-07-09") and "this version" in labels[0]
    assert labels[1] == "2031.07.3 · 2031-07-02"
    assert not any("Not released" in l for l in labels)
    text = "".join(m.value for m in at.markdown)
    assert "Version in the footer." in text and "legacy" not in text


def test_whats_new_shows_unreleased_outside_production(monkeypatch, tmp_path, fake_build):
    fake_build(environment="development")
    at = _run_about(monkeypatch, tmp_path)
    assert at.expander[0].label == "Not released yet"


def test_whats_new_deep_link_opens_that_release(monkeypatch, tmp_path, fake_build):
    fake_build(environment="production")
    at = _run_about(monkeypatch, tmp_path, query={"v": "2031.07.3"})
    opened = [e.label for e in at.expander if e.proto.expanded]
    assert opened == ["2031.07.3 · 2031-07-02"]


# ── machine-readable version + error reference (VD-07, VD-08) ───────────────

def test_static_serving_enabled_and_static_dir_holds_only_version_json():
    import subprocess
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    cfg = tomllib.loads((root / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["server"]["enableStaticServing"] is True
    # nothing tracked under static/: it is public without sign-in
    assert subprocess.run(["git", "ls-files", "static"], cwd=root, capture_output=True,
                          text=True).stdout.strip() == ""
    if (root / "static").is_dir():
        assert {p.name for p in (root / "static").iterdir()} <= {"version.json", "version.json.tmp"}


def test_error_reference_names_run_version_and_commit(fake_build):
    from uvalu import logkit
    fake_build()
    logkit.begin_run()
    ref = shell.error_reference()
    assert ref == f"{logkit.correlation_id()[:12]} · v2031.07.4-dev+fedcba9 (fedcba9)"


def test_render_failure_shows_reference(fake_build):
    fake_build()

    def _script():
        from uvalu import shell
        shell.render_error_reference()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert "Reference for support:" in at.caption[0].value
    assert "v2031.07.4-dev+fedcba9 (fedcba9)" in at.caption[0].value
