"""About page (``/about``) — which version of Uvalu is running and what changed
(VD-02, VD-04).

Reached from the version marker in the footer and *About Uvalu* in the user
menu. The shared supporting-page frame (components.support_page, proposal
1e) with two cards:

- **This version**: app version, commit, build date/time, environment,
  and the scoring-model version (``screener.MODEL_VERSION`` — independent of the
  app version, so labelled differently). A copyable one-line summary for
  support e-mails. All values come from ``uvalu.buildinfo`` — never hard-coded
  (VD-10).
- **What's new**: the CalVer sections of the public RELEASE_NOTES.md (what a
  subscriber notices; the full detail stays in CHANGELOG.md), newest first.
  Release notes are English only (plan decision D6); the chrome around them is
  translated. ``?v=<version>`` opens one release. Non-production builds also
  show the ``[Unreleased]`` notes.
"""
import html
from datetime import datetime, timezone

import streamlit as st

from uvalu import buildinfo, changelog
from uvalu.components import support_page
from uvalu.i18n import N_, _, current, fmt_datetime, h_, tr
from uvalu.runtime import current_user

# Translators: About › What's new › heading of a group of release notes: new features, improvements to existing ones, fixed problems, and things taken out in a release.
GROUP_LABELS = {"New": N_("New"), "Improved": N_("Improved"),
                "Fixed": N_("Fixed"), "Removed": N_("Removed")}
SHOWN_EXPANDED = 1

_CSS = """
.st-key-about_build, .st-key-about_notes {
  background: var(--panel) !important; border-color: var(--line) !important; border-radius: 12px !important;
  box-shadow: var(--shadow) !important; overflow: hidden !important; padding: 0 !important; gap: 0 !important;
}
/* Streamlit pulls markdown blocks up by 16px; here that slid the footer over
   the last data row. */
.st-key-about_build [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* Same pull-up slid the first release row under the "What's new" heading. */
.st-key-about_notes > [data-testid="stElementContainer"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* What's new lead-ins ("Find new ideas faster …"): 500 in --text (design
   reference); the long-form rule in styles.py gives legal lead-ins 600. */
.st-key-about_notes [data-testid="stMarkdownContainer"] strong { font-weight: 500 !important; color: var(--text) !important; }
.uv-about-rows { display: grid; grid-template-columns: 140px minmax(0, 1fr); margin: 0; }
.uv-about-rows > * { padding: 10px 20px; font-size: 13px; border-bottom: 0.5px solid var(--line-2); margin: 0; }
.uv-about-rows > dt { color: var(--muted); }
.uv-about-rows > dd { font-family: var(--uv-mono); color: var(--text); overflow-wrap: anywhere; }
.uv-about-rows > :nth-last-child(-n+2) { border-bottom: none; }
.st-key-about_support {
  background: var(--panel-2); border-top: 0.5px solid var(--line-2); padding: 12px 20px !important;
  align-items: center !important; flex-wrap: nowrap !important;
}
/* The support line takes the room left of the button and wraps inside it. */
.st-key-about_support > [data-testid="stElementContainer"]:first-child { flex: 1 1 0 !important; min-width: 0 !important; }
.uv-about-support { font-family: var(--uv-mono); font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
.st-key-about_copy iframe { display: block; }
.st-key-about_notes [data-testid="stExpander"] details { border: none !important; border-radius: 0 !important;
  border-top: 0.5px solid var(--line-2) !important; }
.st-key-about_notes [data-testid="stExpander"] summary p { font-size: 14px !important; font-weight: 500 !important; }
.st-key-about_notes [data-testid="stExpander"] [data-testid="stMarkdownContainer"] p,
.st-key-about_notes [data-testid="stExpander"] [data-testid="stMarkdownContainer"] li {
  font-size: 13.5px !important; line-height: 1.6 !important; max-width: none !important;
}
.uv-notes-group { font-size: 12px; font-weight: 500; color: var(--muted); margin-top: 8px; }
.st-key-about_notes_caption { padding: 8px 20px 0; }
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


def _copy_button(text: str) -> None:
    """"Copy for support": copies the one-line summary. An iframe button,
    because markdown can't carry an onclick (same as Legal's print button)."""
    import json
    from uvalu.runtime import SIGNAL_TEAL, theme_colors
    tc = theme_colors()
    # Translators: About › button that copies the one-line build details for a support e-mail.
    label = _("Copy for support")
    # Translators: About › the "Copy for support" button's label for a moment after a click.
    done = _("Copied")
    with st.container(key="about_copy", width="content"):
        st.iframe(f"""<!doctype html><html><head><style>
html,body{{margin:0;background:transparent;text-align:right;}}
button{{font:500 12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:{tc.text};
background:transparent;border:0.5px solid {tc.axis};border-radius:8px;padding:5px 10px;cursor:pointer;
white-space:nowrap;}}
button:hover{{border-color:{SIGNAL_TEAL};}}
</style></head><body><button id="b">{html.escape(label)}</button><script>
const text = {json.dumps(text)}, label = {json.dumps(label)}, done = {json.dumps(done)};
document.getElementById("b").onclick = async (e) => {{
  try {{ await navigator.clipboard.writeText(text); }}
  catch (err) {{ const a = document.createElement("textarea"); a.value = text; document.body.appendChild(a);
                 a.select(); document.execCommand("copy"); a.remove(); }}
  e.target.textContent = done; setTimeout(() => {{ e.target.textContent = label; }}, 1600);
}};
</script></body></html>""", height=32, width=max(len(label), len(done)) * 7 + 40)


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
    line = details_line(info)
    with st.container(key="about_build", border=True):
        st.markdown(f'<div><span id="version" class="uv-anchor"></span><div class="uv-card-head">{h_("This version")}</div>'
                    f'<dl class="uv-about-rows">{grid}</dl></div>', unsafe_allow_html=True)
        with st.container(key="about_support", horizontal=True, horizontal_alignment="distribute",
                          vertical_alignment="center", gap="small"):
            st.markdown(f'<div class="uv-about-support" title="{html.escape(_("Copy these details when you contact support:"))}">'
                        f'{html.escape(line)}</div>', unsafe_allow_html=True, width="stretch")
            _copy_button(line)


def visible_releases(releases: "list[changelog.Release]", *, production: bool) -> "list[changelog.Release]":
    """CalVer releases newest first; the [Unreleased] notes too outside production."""
    out = [r for r in releases if r.is_calver]
    if not production:
        unrel = next((r for r in releases if r.is_unreleased and r.groups), None)
        if unrel is not None:
            out.insert(0, unrel)
    return out


def _release_title(r: "changelog.Release", info: "buildinfo.BuildInfo") -> str:
    """Expander label (Markdown): the version in the data font, the date, and
    a positive "This version" badge on the release that is running."""
    if r.is_unreleased:
        # Translators: About › What's new › title of the notes for changes not yet in a release (test builds only).
        return _("Not released yet")
    title = f"`{r.version}` · {r.date}" if r.date else f"`{r.version}`"
    if r.version == info.version:
        # Translators: About › What's new › badge on the release the user is running; also the heading of the build-details card and an entry in the page's section list.
        title += f" :green-badge[{_('This version')}]"
    return title


def _notes_card(info: "buildinfo.BuildInfo") -> None:
    releases = visible_releases(changelog.load(), production=info.is_production)
    wanted = st.query_params.get("v")
    # Open: the release asked for (?v=), else the running one, else the newest.
    running = any(r.version == info.version for r in releases)
    with st.container(key="about_notes", border=True):
        st.markdown(f'<div><span id="whats-new" class="uv-anchor"></span>'
                    f'<div class="uv-card-head">{h_("What’s new")}</div></div>', unsafe_allow_html=True)
        if current().lang != "en" or not releases:
            with st.container(key="about_notes_caption"):
                st.caption(_("Release notes are written in English.") if releases else _("No release notes yet."))
        for i, r in enumerate(releases):
            if wanted:
                open_ = r.version == wanted
            else:
                open_ = r.version == info.version if running else i < SHOWN_EXPANDED
            with st.expander(_release_title(r, info), expanded=open_):
                if r.intro:
                    st.markdown(r.intro)
                for name, body in r.groups:
                    st.markdown(f'<div class="uv-notes-group">{html.escape(tr(GROUP_LABELS.get(name, name)))}</div>',
                                unsafe_allow_html=True)
                    st.markdown(body)


def render() -> None:
    info = buildinfo.current()
    with st.container(key="uv_hidden_util_about_css"):
        st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
    content = support_page(_("About Uvalu"), back_key="about", rail=[
        (_("This version"), "#version"),
        (_("What’s new"), "#whats-new"),
        (_("Legal & policies"), "/legal"),
    ])
    with content:
        _build_card(info)
        _notes_card(info)
    # Reading the notes counts as having seen the update notice (VD-05).
    if changelog.find(changelog.load(), info.version) is not None:
        from uvalu import update_notice
        update_notice.mark_seen(current_user().email, info.version)
