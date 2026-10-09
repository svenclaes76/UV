"""Update notices (VD-05, VD-09).

- **What's new notice** (VD-05): after an update, a one-time, dismissible notice
  on the user's next visit, linking to the release notes. Remembered per user
  in their settings (``last_seen_version``); dismissing it or opening the
  release notes marks it seen. A user with nothing recorded yet (a new account,
  or the first release with this feature) is recorded silently — no notice.
  Only versions that have a section in CHANGELOG.md count, so a dev build
  between releases never announces anything new.
- **Reload prompt** (VD-09): every session remembers the build it started on;
  a fragment checks ``build_info.json`` once a minute and, when a different
  build has been stamped, asks the user to reload. A fragment rerun never
  re-runs the page, so it can't close an open dialog.

  Limitation: today a deploy restarts the server (``run_app.py``), which ends
  every session — the reconnecting browser starts a new session on the new
  build, so there is nothing to prompt. The prompt covers a build stamped while
  the old process still serves (and a future zero-downtime deploy).
"""
from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from uvalu import buildinfo, changelog
from uvalu import nav as nav_registry
from uvalu.i18n import _

SESSION_BUILD_KEY = "_uv_session_build_id"
RELOAD_CHECK_S = 60


def _key(version: "str | None") -> tuple:
    try:
        return tuple(int(x) for x in str(version).split("."))
    except ValueError:
        return ()


def is_newer(version: str, last_seen: "str | None") -> bool:
    """CalVer ``version`` is newer than ``last_seen``; a pre-CalVer value
    (``2.1.1``) sorts below every CalVer release."""
    if not buildinfo.is_calver(version):
        return False
    if not last_seen or not buildinfo.is_calver(last_seen):
        return bool(last_seen)
    return _key(version) > _key(last_seen)


def pending_notice(settings: dict, info: "buildinfo.BuildInfo",
                   releases: "list[changelog.Release]") -> "str | None":
    """The version to announce to this user, or None."""
    version = info.version
    if changelog.find(releases, version) is None:
        return None
    return version if is_newer(version, settings.get("last_seen_version")) else None


def mark_seen(email: str, version: "str | None" = None) -> None:
    import settings as _settings
    if not email:
        return
    version = version or buildinfo.current().version
    s = _settings.load_settings(email)
    if s.get("last_seen_version") == version:
        return
    s["last_seen_version"] = version
    _settings.save_settings(s, email)


def render_whats_new_notice(email: str) -> None:
    """Under the beta banner, once per release, until dismissed."""
    import settings as _settings
    if not email:
        return
    s = _settings.load_settings(email)
    info = buildinfo.current()
    if s.get("last_seen_version") is None and buildinfo.is_calver(info.version):
        mark_seen(email, info.version)          # first record: nothing to announce
        return
    version = pending_notice(s, info, changelog.load())
    if version is None:
        return
    with st.container(key="uv_whats_new_notice", horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f'<div style="font-size:12.5px;color:var(--text);">'
                    f'<span style="font-weight:600;color:var(--up-txt);margin-right:6px;">●</span>'
                    f'{html.escape(_("Uvalu was updated to version {version}.", version=version))}</div>',
                    unsafe_allow_html=True, width="stretch")
        about = nav_registry.pages.get("about")
        if about is not None:
            st.page_link(about, label=_("See what’s new"), query_params={"v": version})
        # on_click runs before the next script run, so that run no longer finds
        # anything pending and the notice is simply gone — no extra rerun.
        st.button(_("Dismiss"), key="uv_whats_new_dismiss", type="tertiary",
                  on_click=mark_seen, args=(email, version))


# ── reload prompt (VD-09) ────────────────────────────────────────────────────

_disk_cache: "tuple[float, str | None] | None" = None


def stamped_build_id(path: "Path | None" = None) -> "str | None":
    """build_id of the stamp on disk (re-read only when the file changes)."""
    global _disk_cache
    p = path or buildinfo.STAMP_FILE
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    if path is None and _disk_cache is not None and _disk_cache[0] == mtime:
        return _disk_cache[1]
    info = buildinfo.load(p)
    bid = buildinfo.build_id(info) if info is not None else None
    if path is None:
        _disk_cache = (mtime, bid)
    return bid


def needs_reload(session_build: "str | None", stamped: "str | None") -> bool:
    return bool(session_build and stamped and session_build != stamped)


def remember_session_build() -> None:
    if SESSION_BUILD_KEY not in st.session_state:
        st.session_state[SESSION_BUILD_KEY] = stamped_build_id() or buildinfo.build_id()


@st.fragment(run_every=RELOAD_CHECK_S)
def render_reload_prompt() -> None:
    if not needs_reload(st.session_state.get(SESSION_BUILD_KEY), stamped_build_id()):
        return
    with st.container(key="uv_reload_prompt", horizontal=True, vertical_alignment="center"):
        st.markdown(f'<div style="font-size:12.5px;color:var(--text);">'
                    f'{html.escape(_("A new version of Uvalu is available. Reload the page to use it."))}'
                    f'</div>', unsafe_allow_html=True, width="stretch")
        st.markdown(f'<a href="" target="_self" class="uv-reload-link">'
                    f'{html.escape(_("Reload"))}</a>', unsafe_allow_html=True, width="content")
