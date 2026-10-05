"""About page (``/about``) — which version of Uvalu is running and what changed
(VD-02, VD-04).

Reached from the version marker in the footer and *About Uvalu* in the user
menu. Two cards:

- **About this version**: app version, commit, build date/time, environment,
  and the scoring-model version (``screener.MODEL_VERSION`` — independent of the
  app version, so labelled differently). A copyable one-line summary for
  support e-mails. All values come from ``uvalu.buildinfo`` — never hard-coded
  (VD-10).
- **What's new**: the CalVer sections of CHANGELOG.md, newest first. Release
  notes are English only (plan decision D6); the chrome around them is
  translated. ``?v=<version>`` opens one release. Non-production builds also
  show the ``[Unreleased]`` notes.
"""
import html
from datetime import datetime, timezone

import streamlit as st

from uvalu import buildinfo, changelog
from uvalu import nav as nav_registry
from uvalu.i18n import N_, _, current, fmt_datetime, h_, tr
from uvalu.runtime import current_user

# Translators: About › What's new › heading of a group of release notes (things added / changed / fixed / removed in a release).
GROUP_LABELS = {"Added": N_("Added"), "Changed": N_("Changed"),
                "Fixed": N_("Fixed"), "Removed": N_("Removed")}
SHOWN_EXPANDED = 1

_CSS = """
.st-key-about_build [data-testid="stMarkdownContainer"] { margin: 0 !important; }
.uv-about-grid { display: grid; grid-template-columns: max-content 1fr; gap: 8px 24px; font-size: 13.5px; }
.uv-about-grid dt { color: var(--muted); }
.uv-about-grid dd { margin: 0; font-family: var(--uv-mono); color: var(--text); overflow-wrap: anywhere; }
.st-key-about_notes [data-testid="stExpander"] details summary p { font-weight: 500; }
"""


def _parse_iso(ts: str) -> "datetime | None":
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def details_line(info: "buildinfo.BuildInfo | None" = None) -> str:
    """One line for support: ``Uvalu 2026.10.1 (a1b2c3d) · built … UTC · production``."""
    info = info or buildinfo.current()
    return (f"Uvalu {info.display_version} ({info.commit}) · built {info.built_at.replace('T', ' ').rstrip('Z')} UTC"
            f" · {info.environment}")


def _commit_html(info: "buildinfo.BuildInfo", is_admin: bool) -> str:
    text = html.escape(info.commit)
    url = buildinfo.commit_url(info)
    if is_admin and url:
        return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{text}</a>'
    return text


def _build_card(info: "buildinfo.BuildInfo") -> None:
    try:
        import screener
        model = screener.MODEL_VERSION
    except Exception:
        model = "?"
    built = _parse_iso(info.built_at)
    built_txt = f"{fmt_datetime(built)} · {info.built_at.replace('T', ' ').rstrip('Z')} UTC" if built else info.built_at
    env_txt = info.environment if info.is_production else f"{info.environment} ({info.environment_label})"
    # Translators: About › build details table. "Commit" = the code revision id; "Built" = when this build was made; "Scoring model" = version of the scoring method (e.g. M1), not the app.
    rows = [
        (_("App version"), html.escape(info.display_version)),
        (_("Commit"), _commit_html(info, current_user().is_admin)),
        (_("Built"), html.escape(built_txt)),
        (_("Environment"), html.escape(env_txt)),
        (_("Scoring model"), html.escape(model)),
    ]
    grid = "".join(f"<dt>{html.escape(k)}</dt><dd>{v}</dd>" for k, v in rows)
    with st.container(key="about_build", border=True):
        st.markdown(f'<div style="font-size:15px;font-weight:600;margin-bottom:12px;">'
                    f'{h_("About this version")}</div><dl class="uv-about-grid">{grid}</dl>',
                    unsafe_allow_html=True)
        st.caption(_("Copy these details when you contact support:"))
        st.code(details_line(info), language=None)


def visible_releases(releases: "list[changelog.Release]", *, production: bool) -> "list[changelog.Release]":
    """CalVer releases newest first; the [Unreleased] notes too outside production."""
    out = [r for r in releases if r.is_calver]
    if not production:
        unrel = next((r for r in releases if r.is_unreleased and r.groups), None)
        if unrel is not None:
            out.insert(0, unrel)
    return out


def _release_title(r: "changelog.Release") -> str:
    if r.is_unreleased:
        # Translators: About › What's new › title of the notes for changes not yet in a release (test builds only).
        return _("Not released yet")
    return f"{r.version} · {r.date}" if r.date else r.version


def _notes_card(info: "buildinfo.BuildInfo") -> None:
    releases = visible_releases(changelog.load(), production=info.is_production)
    wanted = st.query_params.get("v")
    with st.container(key="about_notes", border=True):
        st.markdown(f'<div id="whats-new" style="font-size:15px;font-weight:600;">{h_("What’s new")}</div>',
                    unsafe_allow_html=True)
        if current().lang != "en":
            st.caption(_("Release notes are written in English."))
        if not releases:
            st.markdown(_("No release notes yet."))
            return
        for i, r in enumerate(releases):
            open_ = (r.version == wanted) if wanted else i < SHOWN_EXPANDED
            # Translators: About › What's new › marker after the release the user is running.
            current_marker = "  ·  " + _("this version") if r.version == info.version else ""
            with st.expander(_release_title(r) + current_marker, expanded=open_):
                if r.intro:
                    st.markdown(r.intro)
                for name, body in r.groups:
                    st.markdown(f"**{tr(GROUP_LABELS.get(name, name))}**")
                    st.markdown(body)


def render() -> None:
    info = buildinfo.current()
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
    back, _key = nav_registry.back_target("about")
    if back is not None and st.button(_("← Back to {page}", page=back.title), key="about_back", type="tertiary"):
        st.switch_page(back)
    st.markdown(f'<div style="font-size:26px;font-weight:500;letter-spacing:-0.02em;margin-bottom:14px;">'
                f'{h_("About Uvalu")}</div>', unsafe_allow_html=True)
    _build_card(info)
    _notes_card(info)
