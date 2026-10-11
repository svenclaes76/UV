"""Top bar shell — logo, horizontal nav, theme toggle, avatar menu — plus the
legal footer and the beta banner.

Replaces the old st.sidebar navigation (see app.py) with the mockup's dark
top bar. Call render_topbar(nav) once per run, after st.navigation(...) is
built but before nav.run() so the bar renders above the page body;
render_beta_banner() right after it, and render_footer() after nav.run().
"""
import html

import streamlit as st

from settings import load_settings
from uvalu import nav as nav_registry
from uvalu.i18n import N_, _, fmt_time, h_, pgettext, tr
from uvalu.market_hours import is_market_hours, market_now
from uvalu.runtime import current_user, theme_colors


def _price_indicator() -> tuple[str, str]:
    """(text, hex color) for the topbar price-freshness pill.

    Reads the summary uvalu/data.py's _fetch_prices_cached() stashes in
    session state on the price-bearing pages (Dashboard / Portfolio / Risk).
    Falls back to the market clock alone on pages that never fetch prices, so
    the pill never asserts "Live" when the feed is actually a stale daily
    close (WP-DQ8).
    """
    _open = is_market_hours()
    try:
        status = st.session_state.get("_price_feed_status") or {}
    except Exception:
        status = {}
    as_of = status.get("as_of")
    _t = fmt_time(as_of if as_of is not None else market_now())

    if not _open:
        return _("Market closed · {time}", time=_t), "#8A8A8A"
    if status.get("stale"):
        return _("Feed stale · {time}", time=_t), "#C98A3A"
    if status.get("delayed"):
        return _("Delayed {delayed}/{total} · {time}", delayed=status["delayed"],
                 total=status.get("total", 0), time=_t), "#C98A3A"
    return _("Live · {time}", time=_t), "#1DD6A4"

_NAV_ITEMS = (
    ("dashboard", N_("Dashboard")),
    ("screener",  N_("Screener")),
    ("watchlist", N_("Watchlist")),
    ("portfolio", N_("Portfolio")),
    ("risk",      N_("Risk")),
)


# Top-bar column widths (px at the design width). The nav column is sized to
# its translated links — 13px/500 text + icon + padding per link — so longer
# labels ("Portefeuille", "Beobachtungsliste") take room from the gap on the
# right instead of running into the status pill.
_LOGO_PX, _RIGHT_PX = 190, 330
_NAV_CHAR_PX, _NAV_LINK_PX = 7.4, 54


def _topbar_widths(labels: list[str]) -> list[float]:
    nav_px = sum(len(label) * _NAV_CHAR_PX + _NAV_LINK_PX for label in labels)
    return [_LOGO_PX, max(nav_px, 420), _RIGHT_PX]


def _initials(email: str) -> str:
    local = (email or "").split("@")[0]
    parts = [p for p in local.replace(".", " ").replace("_", " ").replace("-", " ").split(" ") if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _display_name(email: str) -> str:
    """Title-cased name derived from the email local-part (e.g. "marek.k@uvalu.eu"
    -> "Marek K") — there's no real display-name field on the user record, so
    this is a readable stand-in rather than a fabricated one, same source data
    as _initials() above. Shared with uvalu/pages_/admin.py's Users table so
    both surfaces render a name the same way."""
    local = (email or "").split("@")[0]
    parts = [p for p in local.replace(".", " ").replace("_", " ").replace("-", " ").split(" ") if p]
    return " ".join(p.capitalize() for p in parts) if parts else email


def _password_strength(password: str) -> tuple[str, str]:
    """(label, css-tone) advisory indicator — NOT the security check itself
    (that's auth.validate_new_password()'s hard min-length/HIBP block).
    Length + character-class variety only, three tiers, no new dependency;
    tone is one of "down"/"amber"/"up" for the caller to render against the
    app's existing --down-txt/--amber-txt/--up-txt tokens (uvalu/styles.py)
    rather than a hardcoded color."""
    if not password:
        return "", ""
    variety = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ])
    if len(password) < 12 or variety <= 1:
        return _("Weak"), "down"
    if len(password) < 16 or variety <= 2:
        return _("Fair"), "amber"
    return _("Strong"), "up"


def apply_theme_script(light: bool) -> None:
    """Set data-theme on the parent document's <html> element from Streamlit's
    OWN active theme (st.context.theme, resolved via theme_colors()) so the
    mockup's [data-theme="light"] CSS override (uvalu/styles.py) always
    matches whatever native widgets (buttons, dataframes, Plotly charts) are
    already rendering in — a single source of truth. Streamlit's own theme
    preference (light/dark/system) is switched via the top bar's sun/moon
    toggle (see set_theme_script below), which writes the same localStorage
    key Streamlit's native app-menu theme picker used before that menu was
    hidden — st.context.theme itself is still the single point of truth this
    function reads from, only the UI for changing it moved. An earlier
    version of this function drove data-theme from an independent per-user
    setting instead; that let native widgets and the new raw-HTML cards
    disagree on light/dark, so it was dropped before the Dashboard rebuild
    (Phase 3.1) started leaning on these tokens too."""
    theme = "light" if light else "dark"
    st.iframe(f"""
<script>
(function(){{
  try {{ window.parent.document.documentElement.setAttribute('data-theme', {theme!r}); }} catch(e) {{}}
}})();
</script>
""", height=1)


def set_theme_script(target: str) -> None:
    """Persist `target` ("Light"/"Dark") to the same localStorage key
    Streamlit's own (now-hidden) app-menu theme picker writes to
    (`stActiveTheme-<base_path>-v2`), then reload. st.context.theme is only
    resolved from that value on a fresh server round-trip — a same-render
    st.rerun() would still see the OLD theme, so a full reload (not a
    lighter rerun) is what actually makes native widgets, Plotly charts and
    this custom toggle agree on the next paint.

    The key is namespaced per page path (`window.parent.location.pathname`,
    e.g. "/" or "/risk"), not hardcoded to root — each Streamlit page has its
    OWN `stActiveTheme-<path>-v2` entry, confirmed live (setting only the
    root key while on /risk did not flip that page's theme). Public (not
    module-private) since both the top bar's own toggle button below and
    uvalu/pages_/settings.py's Theme control call it.

    The reload itself is instant/abrupt (old page vanishes, blank tab, new
    page pops in) — measured with the browser's own Layout Instability API
    during development, which found zero real post-paint position shifts,
    so nothing is actually moving incorrectly; the cut just reads as a
    "flip" because there's no visual continuity across it. Fading the OLD
    page out first (instead of reloading instantly) turns that hard cut
    into a cross-fade with the NEW page's existing entry animation
    (.block-container's uvFadeIn, uvalu/styles.py) — same fix either way,
    but doing it here needs no theory about the reload's internals to work."""
    st.iframe(f"""
<script>
(function(){{
  try {{
    var path = window.parent.location.pathname;
    window.parent.localStorage.setItem('stActiveTheme-' + path + '-v2', JSON.stringify({target!r}));
    var docEl = window.parent.document.documentElement;
    docEl.style.transition = 'opacity 0.12s ease';
    docEl.style.opacity = '0';
    setTimeout(function(){{ window.parent.location.reload(); }}, 120);
  }} catch(e) {{ window.parent.location.reload(); }}
}})();
</script>
""", height=1)


def _close_stray_popover_script() -> None:
    """Force-close a leftover avatar popover after navigating here via one of
    its own entries (Settings/Help page_links inside the popover) — clicking
    a page_link INSIDE the popover doesn't fire the popover's own
    outside-click-to-close listener (the click target is inside its own DOM
    subtree, not outside it), and the destination page's fresh render_topbar()
    call doesn't reset that listener's state either, so the popover panel
    stays visibly open after the page switch. Dispatching a synthetic
    mousedown+click on the parent document's <body> triggers that same
    outside-click listener — confirmed live this reliably closes it, with no
    other side effect since plain body has no listeners of its own elsewhere
    in this app."""
    st.iframe("""
<script>
(function(){
  try {
    var body = window.parent.document.body;
    var opts = {bubbles: true, cancelable: true, view: window.parent};
    body.dispatchEvent(new MouseEvent('mousedown', opts));
    body.dispatchEvent(new MouseEvent('click', opts));
  } catch(e) {}
})();
</script>
""", height=1)


def _apply_density_script(density: str) -> None:
    """Set data-density on the parent document's <html> element from the
    per-user "density" setting (Settings → Display → Table density) — the
    CSS in uvalu/styles.py reads this to tighten dataframe row padding."""
    st.iframe(f"""
<script>
(function(){{
  try {{ window.parent.document.documentElement.setAttribute('data-density', {density!r}); }} catch(e) {{}}
}})();
</script>
""", height=1)


def _topbar_css(active_path: str) -> str:
    return f"""
.st-key-uv_topbar {{
  position: sticky; top: 0; z-index: 999;
  background: var(--panel); border-bottom: 0.5px solid var(--line);
  padding: 10px 24px; margin: 0 -1.5rem 0;
  width: calc(100% + 3rem) !important; max-width: calc(100% + 3rem) !important;
  flex: none !important; min-height: 61px !important; box-sizing: border-box !important;
}}
[data-theme="light"] .st-key-uv_topbar {{ background: var(--panel); }}
/* Streamlit's stMarkdownContainer carries a built-in -16px bottom margin
   (compensating for default <p> spacing in rendered markdown) that doesn't
   apply to our raw <div> HTML — left alone, it shrinks the box the outer
   row's vertical_alignment="center" centers against, visually pushing the
   logo/tagline and Live indicator ~8px below true center. */
.st-key-uv_topbar [data-testid="stMarkdownContainer"] {{ margin: 0 !important; }}
.st-key-uv_topbar_nav {{ flex-wrap: nowrap !important; }}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] {{
  border-radius: 8px !important; padding: 7px 13px !important;
  color: var(--muted) !important; white-space: nowrap !important;
}}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] p {{
  font-size: 13px !important; font-weight: 500 !important;
}}
/* Streamlit 1.60 wraps the label in a <span> with its own text colour, so
   the link's --muted / --text never reached the label or the icon. */
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] * {{ color: inherit !important; }}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] {{
  font-size: 16px !important;
}}
.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"]:hover {{
  background: var(--line-2) !important; color: var(--text) !important;
}}
.st-key-uv_topbar_nav a[href="{active_path}"] {{
  background: var(--soft) !important; color: var(--text) !important;
}}
div:has(> .st-key-uv_theme_toggle) {{ flex: none !important; width: auto !important; }}
/* Below ~1200px the nav links and the market-status text no longer fit side
   by side (they overlapped at 1024px): drop the status text (the dot keeps
   it as a tooltip) and the nav icons, tighten the link padding. */
.uv-pi-short {{ display: none; }}
/* The logo column is too narrow for the tagline beside the 22px logo. */
@media (max-width: 1100px) {{ .uv-logo-tag {{ display: none !important; }} }}
@media (max-width: 1200px) {{
  .uv-pi-text {{ display: none !important; }}
  .uv-pi-short {{ display: inline !important; }}
  /* The icon's own wrapper span, not just the glyph: a hidden glyph still
     left a 16px box plus the 8px gap in every link. */
  .st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] > span:has([data-testid="stIconMaterial"]) {{ display: none !important; }}
  .st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] {{ padding: 7px 9px !important; }}
}}
/* A plain outline control in both themes (the avatar chip stays the one
   navy + mint brand badge). */
.st-key-uv_theme_toggle button {{
  border-radius: 8px !important; background: transparent !important;
  color: var(--muted) !important; border: 0.5px solid var(--line) !important;
  padding: 0 !important; width: 34px !important; height: 34px !important;
  min-height: 34px !important; min-width: 34px !important;
}}
.st-key-uv_theme_toggle button:hover {{ border-color: var(--teal) !important; color: var(--text) !important; }}
div:has(> .st-key-uv_avatar_pop) {{ flex: none !important; width: auto !important; }}
/* The avatar control is two visually distinct zones — a navy initials pill
   plus a separate chevron — not one solid-color button. Streamlit renders
   label and chevron as sibling divs inside the button (chevron marked
   aria-hidden="true"), so style the outer button as the neutral "chip"
   shell and give just the label div its own pill treatment. */
.st-key-uv_avatar_pop button {{
  border-radius: 8px !important; background: transparent !important;
  border: 0.5px solid transparent !important;
  padding: 4px 6px !important; height: 40px !important; min-height: 40px !important;
}}
.st-key-uv_avatar_pop button:hover {{
  background: var(--panel-2) !important; border: 0.5px solid var(--line) !important;
}}
.st-key-uv_avatar_pop button > div {{ gap: 6px !important; height: 100% !important; }}
.st-key-uv_avatar_pop button > div > div:not([aria-hidden]) {{
  background: var(--navy) !important; color: var(--mint) !important;
  border-radius: 6px !important; padding: 0 8px !important;
  font-weight: 600 !important; font-size: 12px !important;
  height: 100% !important; display: flex !important; align-items: center !important;
}}
.st-key-uv_avatar_pop button [aria-hidden="true"] {{ color: var(--muted) !important; }}
.st-key-uv_avatar_menu a[data-testid="stPageLink-NavLink"] {{
  border-radius: 8px !important; padding: 8px 10px !important; gap: 10px !important;
}}
.st-key-uv_avatar_menu a[data-testid="stPageLink-NavLink"] p {{ font-size: 13px !important; color: var(--text) !important; }}
.st-key-uv_avatar_menu a[data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] {{
  font-size: 16px !important; color: var(--muted) !important;
}}
.st-key-uv_avatar_menu a[data-testid="stPageLink-NavLink"]:hover {{ background: var(--line-2) !important; }}
a.uv-menu-signout {{
  display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px;
  color: var(--down-txt) !important; font-size: 13px; text-decoration: none;
}}
a.uv-menu-signout:hover {{ background: var(--down-bg); }}
/* Notice strips (update notice, reload prompt): full width under the top bar,
   --panel with a --line-2 rule, flush with the bar and with each other (the
   negative top margin cancels the page's 18px section gap). */
.st-key-uv_whats_new_notice, .st-key-uv_reload_prompt {{
  margin: -18px -1.5rem 0 !important; width: calc(100% + 3rem) !important; max-width: none !important;
  padding: 8px 24px !important; background: var(--panel); border-bottom: 0.5px solid var(--line-2);
  gap: 8px 16px !important; flex-wrap: wrap !important; box-sizing: border-box;
}}
.st-key-uv_whats_new_notice [data-testid="stMarkdownContainer"],
.st-key-uv_reload_prompt [data-testid="stMarkdownContainer"] {{ margin: 0 !important; }}
.st-key-uv_whats_new_notice a[data-testid="stPageLink-NavLink"] {{
  padding: 0 !important; min-height: 0 !important; background: none !important;
}}
.st-key-uv_whats_new_notice a[data-testid="stPageLink-NavLink"] > span:has([data-testid="stIconMaterial"]) {{ display: none !important; }}
.st-key-uv_whats_new_notice a[data-testid="stPageLink-NavLink"] p {{ font-size: 12.5px !important; color: var(--link) !important; }}
.st-key-uv_whats_new_notice a[data-testid="stPageLink-NavLink"]:hover p {{ color: var(--text) !important; }}
.st-key-uv_whats_new_notice button {{ min-height: 0 !important; padding: 0 !important; }}
.st-key-uv_whats_new_notice button p {{ font-size: 12.5px !important; color: var(--muted) !important; }}
.st-key-uv_whats_new_notice button:hover p {{ color: var(--text) !important; }}
/* Beta box and peer strip: Streamlit's -1rem markdown margin would eat the
   gap below them (title 6px under the box instead of 22px). */
[data-testid="stMarkdownContainer"]:has(> .uv-beta-box),
[data-testid="stMarkdownContainer"]:has(> .uv-peer-strip) {{ margin-bottom: 0 !important; }}
.uv-reload-link {{ font-size: 12.5px; color: var(--link) !important; text-decoration: none; white-space: nowrap; }}
.uv-reload-link:hover {{ color: var(--text) !important; }}
"""


def render_topbar(nav) -> None:
    user = current_user()
    active_path = getattr(nav, "url_path", "") or ""

    # Theme/density sync scripts and the CSS injection below produce no
    # visible content, but each is still a Streamlit element and would
    # otherwise consume a full row-gap in the vertical block, pushing the
    # visible bar down the page. Collapsing them into one zero-size,
    # out-of-flow container keeps the bar flush with the top of the page.
    with st.container(key="uv_hidden_util_topbar"):
        _light = theme_colors().effective_light
        apply_theme_script(_light)
        _density = load_settings(user.email).get("density", "comfortable")
        _apply_density_script(_density)
        if active_path in ("settings", "help"):
            _close_stray_popover_script()
        st.markdown(f"<style>{_topbar_css(active_path)}</style>", unsafe_allow_html=True)

    with st.container(key="uv_topbar"):
        _nav_labels = [tr(label) for _key, label in _NAV_ITEMS]
        col_logo, col_nav, col_right = st.columns(_topbar_widths(_nav_labels), vertical_alignment="center")

        with col_logo:
            st.markdown(
                '<div style="display:flex;align-items:baseline;gap:9px;">'
                '<span style="font-size:22px;font-weight:500;letter-spacing:-0.03em;line-height:1;">'
                'uval<span style="color:var(--logo-accent)">u</span></span>'
                '<span class="uv-logo-tag" style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;'
                f'white-space:nowrap;color:var(--muted);">{_("value engine")}</span></div>',
                unsafe_allow_html=True,
            )

        with col_nav:
            with st.container(key="uv_topbar_nav", horizontal=True, gap="small"):
                for key, label in _NAV_ITEMS:
                    page = nav_registry.pages.get(key)
                    if page is not None:
                        st.page_link(page, label=tr(label))

        with col_right:
            with st.container(horizontal=True, gap="small", horizontal_alignment="right",
                              vertical_alignment="center"):
                # A dot + status pill matching Uvalu.dc.html's asOf indicator,
                # but driven by the real price feed (WP-DQ8): the time is the
                # feed's own `as_of` in CET/CEST (the market timezone —
                # meaningful here, unlike the app's naive-local timestamps
                # elsewhere), and the label/colour tell live vs delayed vs
                # market-closed instead of always claiming "Live".
                _pi_text, _pi_color = _price_indicator()
                # Only the genuinely-live state pulses (uvRing, uvalu/styles.py)
                # — an animated dot next to "Delayed"/"Feed stale"/"Market
                # closed" would read as "still updating" when it isn't.
                _pi_anim = "animation:uvRing 1.6s ease-out infinite;" if _pi_color == "#1DD6A4" else ""
                # One word for widths where the full text doesn't fit next to
                # the nav (below 1200px the dot used to stand alone).
                _pi_short = {"#8A8A8A": pgettext("market", "Closed"),
                             "#1DD6A4": pgettext("market", "Live")}.get(_pi_color, pgettext("market", "Delayed"))
                st.markdown(
                    f'<div title="{html.escape(_pi_text)}" style="display:flex;align-items:center;gap:7px;'
                    f'font-size:11px;color:var(--muted);font-family:var(--uv-mono);min-width:0;">'
                    f'<span style="width:6px;height:6px;border-radius:50%;background:{_pi_color};flex:none;'
                    f'box-shadow:0 0 0 3px {_pi_color}2E;{_pi_anim}"></span>'
                    f'<span class="uv-pi-text" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_pi_text}</span>'
                    f'<span class="uv-pi-short" style="white-space:nowrap;">{html.escape(_pi_short)}</span></div>',
                    unsafe_allow_html=True,
                )

                with st.container(key="uv_theme_toggle"):
                    _toggle_icon = ":material/dark_mode:" if _light else ":material/light_mode:"
                    if st.button("", icon=_toggle_icon, key="uv_theme_toggle_btn",
                                 help=_("Switch to dark theme") if _light else _("Switch to light theme")):
                        set_theme_script("Dark" if _light else "Light")

                with st.container(key="uv_avatar_pop"):
                    with st.popover(_initials(user.email)):
                        # Name, then the email as plain text (st.caption auto-linked it
                        # as a mailto link) and the plan as a chip (G27: "Free beta";
                        # the role is shown in the Admin portal).
                        st.markdown(
                            f'<div><div style="font-size:13px;font-weight:500;">{html.escape(_display_name(user.email))}</div>'
                            f'<div style="font-size:11px;color:var(--muted);margin-top:2px;font-family:var(--uv-mono);">'
                            f'{html.escape(user.email).replace("@", "&#64;")}</div>'
                            f'<span style="display:inline-block;margin-top:8px;font-size:10px;font-weight:500;'
                            f'color:var(--up-txt);background:var(--soft);border-radius:6px;padding:2px 8px;">'
                            f'{html.escape(_("Free beta"))}</span></div>',
                            unsafe_allow_html=True)
                        st.divider()
                        with st.container(key="uv_avatar_menu"):
                            _settings_page = nav_registry.pages.get("settings")
                            _help_page = nav_registry.pages.get("help")
                            _admin_page = nav_registry.pages.get("admin")
                            # Legal texts are reached from the footer and Settings › Legal.
                            if _settings_page is not None:
                                st.page_link(_settings_page, label=_("Settings"), icon=":material/settings:")
                            if _help_page is not None:
                                st.page_link(_help_page, label=_("Methodology"), icon=":material/info:")
                            _about_page = nav_registry.pages.get("about")
                            if _about_page is not None:
                                st.page_link(_about_page, label=_("About Uvalu"), icon=":material/layers:")
                            if user.is_admin and _admin_page is not None:
                                st.page_link(_admin_page, label=_("Admin portal"), icon=":material/shield:")
                        st.divider()
                        # A menu item like the links above (icon + label), not a small
                        # underlined link.
                        from uvalu.components import material_icon_html
                        st.markdown(
                            f'<a href="/?logout=1" target="_self" class="uv-menu-signout">'
                            f'{material_icon_html("logout", 16)}{html.escape(_("Sign out"))}</a>',
                            unsafe_allow_html=True,
                        )


# ── Beta banner (decision B7) and legal footer (DIS-1, REC-1, BIZ-3) ──────────

def producer_name() -> str:
    """"Sven Claes, trading as Uvalu" — who produces the output (REC-1)."""
    from uvalu.compliance import disclosures as d
    return _("{name}, trading as {trading_as}", name=d.PRODUCER_NAME, trading_as=d.PRODUCER_TRADING_AS)


def enterprise_number() -> str:
    """The enterprise number, or "enterprise number: registration pending"
    (decision B6)."""
    from uvalu.compliance import disclosures as d
    return d.PRODUCER_ENTERPRISE_NUMBER or tr(d.ENTERPRISE_NUMBER_PENDING)


def producer_line() -> str:
    """Producer identity for the footer, the sign-in panel and the
    Methodology page (REC-1, BIZ-3): name and trading name, address,
    enterprise number (or "registration pending") and contact."""
    from uvalu.compliance import disclosures as d
    return f"{producer_name()} · {d.PRODUCER_ADDRESS} · {enterprise_number()} · {d.PRODUCER_CONTACT}"


def render_beta_banner() -> None:
    """The beta notice: a rounded box inside the page gutter (brand §8, G01),
    text centred as in the design reference, with the Terms of use one click
    away."""
    from uvalu.compliance import disclosures as d
    if not d.BETA:
        return
    st.markdown(
        '<div class="uv-beta-box" style="display:flex;align-items:center;justify-content:center;flex-wrap:wrap;'
        'gap:4px 10px;font-size:11.5px;color:var(--muted);background:var(--soft);border:0.5px solid var(--line);'
        'border-radius:8px;padding:7px 14px;margin:-6px 0 4px;text-align:center;">'
        f'<span style="font-weight:600;color:var(--up-txt);">{html.escape(_("Beta"))}</span>'
        f'<span style="min-width:0;">{html.escape(tr(d.BETA_BANNER))}</span>'
        f'<a href="/legal?doc=terms" target="_self" style="white-space:nowrap;color:var(--link);'
        f'text-decoration:none;">{html.escape(_("Terms →"))}</a></div>',
        unsafe_allow_html=True)


def render_peer_rebuild_strip() -> None:
    """While the universe's peer reference is rebuilt after a restart, say why
    the signals read "No signal" (G10; the pages keep their skeletons)."""
    from uvalu.data import peer_reference_pending
    try:
        pending = peer_reference_pending()
    except Exception:
        pending = False
    if not pending:
        return
    # Translators: Strip under the beta notice while the app rebuilds its peer reference after a restart. “No signal” is the badge label.
    text = _("Rebuilding the peer reference after a restart. Signals show “No signal” until it finishes, "
             "usually within a few minutes.")
    st.markdown(
        '<div role="status" class="uv-peer-strip" style="display:flex;align-items:center;gap:10px;padding:8px 12px;'
        'background:var(--panel-2);border:0.5px solid var(--line);border-radius:8px;font-size:12.5px;'
        'color:var(--muted);margin:-6px 0 4px;">'
        '<span style="width:12px;height:12px;flex:none;border-radius:50%;border:1.5px solid var(--line);'
        'border-top-color:var(--teal);animation:uvSpin 0.9s linear infinite;"></span>'
        f'<span>{html.escape(text)}</span></div>',
        unsafe_allow_html=True)


# Environment marker (VD-03): fixed colours, the same in light and dark theme,
# white text on both (contrast ≥ 4.5:1). Production shows nothing.
ENV_COLORS = {"development": "#B45309", "test": "#6D28D9"}
_ENV_FALLBACK_COLOR = "#B91C1C"


def env_marker_html(info=None) -> str:
    """A 3px stripe across the top of the window plus a small label in the
    bottom-left corner (clear of the top bar's nav), so a non-production build
    can't be mistaken for production — not even on a screenshot. Empty for
    production."""
    from uvalu import buildinfo
    info = info or buildinfo.current()
    if info.is_production:
        return ""
    color = ENV_COLORS.get(info.environment, _ENV_FALLBACK_COLOR)
    label = html.escape(info.environment_label)
    title = html.escape(f"{info.environment} — {info.display_version}")
    return (f'<div class="uv-env-stripe" style="position:fixed;top:0;left:0;right:0;height:3px;'
            f'background:{color};z-index:1000000;pointer-events:none;"></div>'
            f'<div class="uv-env-badge" title="{title}" style="position:fixed;bottom:0;left:16px;'
            f'z-index:1000000;background:{color};color:#fff;'
            f'font:600 10px/1 var(--uv-mono, monospace);letter-spacing:0.12em;padding:4px 10px 4px;'
            f'border-radius:6px 6px 0 0;pointer-events:none;">{label}</div>')


def render_env_marker() -> None:
    marker = env_marker_html()
    if marker:
        with st.container(key="uv_hidden_util_env"):
            st.markdown(marker, unsafe_allow_html=True)


def error_reference() -> str:
    """``<correlation id> · v<version> (<commit>)`` — the same ids the log line
    for this run carries, so support can find it (VD-08)."""
    from uvalu import buildinfo, logkit
    info = buildinfo.current()
    cid = (logkit.correlation_id() or "-")[:12]
    return f"{cid} · v{info.display_version} ({info.commit})"


def render_error_reference() -> None:
    """The error box shown when a page fails to render (G11): a neutral
    message — the handler can't tell what failed — and the reference to quote
    to support, the same ids the log line carries (VD-08)."""
    try:
        ref = f'<span style="font-family:var(--uv-mono);">{html.escape(error_reference())}</span>'
        st.markdown(
            '<div style="padding:12px 16px;border-radius:8px;background:var(--down-bg);color:var(--down-txt);'
            f'font-size:13px;line-height:1.5;">{h_("Couldn’t load this page. Try again in a moment.")}</div>'
            '<div style="font-size:12px;color:var(--muted);margin-top:6px;">'
            # Translators: Shown under an error message; {ref} is a technical reference (id, version, commit) to quote to support.
            f'{h_("Something went wrong. Reference for support: {ref}", ref=ref)}</div>',
            unsafe_allow_html=True)
    except Exception:
        pass


def render_maintenance() -> None:
    """Shown instead of the app when the stored data doesn't match this version
    (VM-09). Deliberately neutral — the instruction for the operator is in the
    server log (event ``startup.schema_mismatch``) and on the console."""
    from uvalu import buildinfo
    info = buildinfo.current()
    # Translators: Maintenance screen › title, shown instead of the app while stored data waits for an update.
    title = _("Uvalu is being updated")
    # Translators: Maintenance screen › body text under "Uvalu is being updated".
    body = _("The app is waiting for a data update to finish. Please try again in a few minutes.")
    st.markdown(
        '<div style="max-width:560px;margin:12vh auto 0;padding:28px 32px;border:0.5px solid var(--line);'
        'border-radius:12px;background:var(--panel);">'
        f'<div style="font-size:20px;font-weight:600;margin-bottom:8px;">{html.escape(title)}</div>'
        f'<div style="font-size:14px;color:var(--muted);line-height:1.6;">{html.escape(body)}</div>'
        f'<div style="font-size:11.5px;color:var(--muted);margin-top:16px;font-family:var(--uv-mono);">'
        f'v{html.escape(info.display_version)} · {html.escape(info.commit)}</div></div>',
        unsafe_allow_html=True)


_FOOTER_CSS = """
.st-key-uv_footer { border-top: 0.5px solid var(--line); margin-top: 28px; padding: 16px 0 16px; gap: 8px !important; }
.st-key-uv_footer [data-testid="stMarkdownContainer"] { margin: 0 !important; }
/* Keeping the footer at the bottom of the screen is in the global stylesheet
   (uvalu/styles.py): this <style> leaves with the footer while a page loads. */
/* Legal links: one left-aligned row, no separators, no icons (st.page_link
   inherits the Legal page's gavel icon, which repeated six times). */
.st-key-uv_footer_links { justify-content: flex-start !important; gap: 6px 16px !important; flex-wrap: wrap !important; margin-top: 4px; }
.st-key-uv_footer_links > [data-testid="stElementContainer"] { display: flex; align-items: center; width: auto !important; }
.st-key-uv_footer_links a[data-testid="stPageLink-NavLink"] {
  padding: 0 !important; min-height: 0 !important; background: none !important; gap: 0 !important;
}
.st-key-uv_footer_links a[data-testid="stPageLink-NavLink"] > span:has([data-testid="stIconMaterial"]) { display: none !important; }
.st-key-uv_footer_links a[data-testid="stPageLink-NavLink"] p,
.st-key-uv_footer_links a[data-testid="stPageLink-NavLink"] span {
  font-size: 11px !important; color: var(--link) !important;
}
.st-key-uv_footer_links a[data-testid="stPageLink-NavLink"]:hover p { color: var(--text) !important; }
/* Version marker (VD-01): quieter than the legal links, monospace. */
.st-key-uv_footer_version { margin-top: 2px; }
.st-key-uv_footer_version a[data-testid="stPageLink-NavLink"] {
  padding: 0 !important; min-height: 0 !important; background: none !important; gap: 0 !important;
}
.st-key-uv_footer_version a[data-testid="stPageLink-NavLink"] > span:has([data-testid="stIconMaterial"]) { display: none !important; }
.st-key-uv_footer_version a[data-testid="stPageLink-NavLink"] p {
  font-size: 10.5px !important; color: var(--muted) !important; font-family: var(--uv-mono) !important;
}
.st-key-uv_footer_version a[data-testid="stPageLink-NavLink"]:hover p { color: var(--link) !important; }
"""


def render_footer() -> None:
    """Short disclaimer, producer identity and the legal page links, at the
    bottom of every screen, in the user's language (DIS-1, REC-1, TOU-8).
    The "not directed at the UK, US or Switzerland" statement (INT-5/6) lives
    in the Terms of use, where those requirements put it."""
    from uvalu.compliance import disclosures as d
    with st.container(key="uv_footer"):
        st.markdown(f"<style>{_FOOTER_CSS}</style>"
                    f'<div style="font-size:11.5px;color:var(--muted);line-height:1.6;text-wrap:pretty;">'
                    f'{html.escape(tr(d.SHORT_DISCLAIMER))}</div>'
                    f'<div style="display:flex;flex-wrap:wrap;gap:2px 12px;font-size:11px;color:var(--muted);'
                    f'line-height:1.6;margin-top:6px;"><span>{html.escape(producer_line())}</span>'
                    f'<span>{html.escape(tr(d.NOT_SUPERVISED))}</span></div>',
                    unsafe_allow_html=True)
        legal_page = nav_registry.pages.get("legal")
        with st.container(key="uv_footer_links", horizontal=True, vertical_alignment="center"):
            if legal_page is not None:
                for key, title, _file in d.LEGAL_DOCS:
                    st.page_link(legal_page, label=tr(d.FOOTER_LINK_LABELS.get(key, title)),
                                 query_params={"doc": key})
        render_version_marker()


def render_version_marker() -> None:
    """``v2026.10.1`` under the legal links on every page (VD-01), linking to
    What's new on the About page (VD-04). The text is read from the build
    metadata, never written in the UI (VD-10)."""
    from uvalu import buildinfo
    info = buildinfo.current()
    about = nav_registry.pages.get("about")
    with st.container(key="uv_footer_version", horizontal=True, horizontal_alignment="left"):
        label = f"v{info.display_version}"
        if about is not None:
            st.page_link(about, label=label, help=_("About this version and what's new"))
        else:
            st.markdown(f'<span style="font-size:11px;color:var(--muted);">{html.escape(label)}</span>',
                        unsafe_allow_html=True)
