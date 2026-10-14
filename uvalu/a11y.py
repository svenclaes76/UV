"""Screen-reader names, landmarks and the skip link (AC1–AC3,
docs/accessibility-review.md).

Streamlit can't put an ``aria-label`` on a button or a role on a container,
so this module works in two halves:

* During a run, row code calls ``label(key, text, pressed=…)`` for a button
  whose visible text says nothing on its own ("★", "View", "✎", an icon).
* ``render()``, called by app.py after the footer, hands those names to the
  page together with the translated landmark labels. A small script, put
  into the page once, applies them: navigation / main / contentinfo roles,
  a "Skip to content" link first in the document, ``aria-hidden`` on
  Material icon ligatures (they'd otherwise be read as "light_mode",
  "expand_more"), and the registered names and pressed states. A
  MutationObserver re-applies all of it whenever Streamlit redraws a part of
  the page (a fragment rerun, a dialog), so nothing depends on timing.

The deployment's Content-Security-Policy allows inline scripts
(deploy/Caddyfile), which Streamlit itself needs as well.
"""
from __future__ import annotations

import html
import json
import re

import streamlit as st

from uvalu.i18n import _, pgettext

_SS_KEY = "_uv_aria"


def css_key(key: str) -> str:
    """The class Streamlit gives a keyed element: ``st-key-`` + the key with
    anything outside [A-Za-z0-9_-] replaced (a ticker's "." becomes "-")."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", key)


def begin_run() -> None:
    """Start a fresh set of names for this run (app.py, before the page)."""
    st.session_state[_SS_KEY] = {}


def label(key: str, text: str, *, pressed: bool | None = None) -> None:
    """Name the button with widget key ``key`` for screen readers.
    ``pressed`` makes it a toggle (``aria-pressed``), e.g. a watchlist star."""
    st.session_state.setdefault(_SS_KEY, {})[css_key(key)] = [text, pressed]


def labels() -> dict[str, list]:
    return dict(st.session_state.get(_SS_KEY, {}))


def stock_name(ticker: str, name: str | None = None) -> str:
    """How a row's stock is named in a button label: "Investor AB (INVE-B.ST)",
    or just the ticker when there's no name."""
    name = (name or "").strip()
    return f"{name} ({ticker})" if name and name != ticker else ticker


# Runs in the page (not in the helper iframe), installed once; reads
# window.__uvA11y, which each run's iframe refreshes.
_PAGE_SCRIPT = r"""
(function(){
  var d = document, pending = false;
  function mark(sel, role, label){
    var e = d.querySelector(sel);
    if (!e) return;
    if (e.getAttribute('role') !== role) e.setAttribute('role', role);
    if (label && e.getAttribute('aria-label') !== label) e.setAttribute('aria-label', label);
  }
  function apply(){
    pending = false;
    var cfg = window.__uvA11y || {labels: {}, aria: {}};
    mark('.st-key-uv_topbar_nav', 'navigation', cfg.labels.nav);
    mark('.st-key-uv_main', 'main');
    mark('.st-key-uv_footer', 'contentinfo');
    var a = d.getElementById('uv-skip');
    if (!a) {
      a = d.createElement('a');
      a.id = 'uv-skip'; a.className = 'uv-skip'; a.href = '#';
      a.addEventListener('click', function(ev){
        ev.preventDefault();
        var t = d.querySelector('.st-key-uv_main [role="heading"][aria-level="1"]')
                || d.querySelector('.st-key-uv_main');
        if (t) { t.setAttribute('tabindex', '-1'); t.focus(); t.scrollIntoView({block: 'start'}); }
      });
      d.body.insertBefore(a, d.body.firstChild);
    }
    if (cfg.labels.skip && a.textContent !== cfg.labels.skip) a.textContent = cfg.labels.skip;
    var icons = d.querySelectorAll('[data-testid="stIconMaterial"]:not([aria-hidden])');
    for (var i = 0; i < icons.length; i++) icons[i].setAttribute('aria-hidden', 'true');
    for (var k in cfg.aria) {
      var v = cfg.aria[k], els = d.getElementsByClassName('st-key-' + k);
      for (var j = 0; j < els.length; j++) {
        // Every button in the keyed element: Streamlit draws a button with a
        // tooltip twice (one per layout) and sets aria-label="" on an icon one.
        var bs = els[j].tagName === 'BUTTON' ? [els[j]] : els[j].querySelectorAll('button');
        for (var n = 0; n < bs.length; n++) {
          var b = bs[n];
          if (b.getAttribute('aria-label') !== v[0]) b.setAttribute('aria-label', v[0]);
          if (v[1] === null) { if (b.hasAttribute('aria-pressed')) b.removeAttribute('aria-pressed'); }
          else if (b.getAttribute('aria-pressed') !== String(v[1])) b.setAttribute('aria-pressed', String(v[1]));
        }
      }
    }
  }
  function schedule(){ if (!pending) { pending = true; setTimeout(apply, 60); } }
  window.__uvA11yApply = schedule;
  new MutationObserver(schedule).observe(d.body, {childList: true, subtree: true});
  schedule();
})();
"""


def _js(value) -> str:
    return json.dumps(value).replace("<", "\\u003c")


def render(page_path: str, *, names: bool = True) -> None:
    """Install the page script (once per page load) and hand it this run's
    labels. app.py calls it twice: before the page body with ``names=False``,
    so landmarks and icons are handled even while a page is still loading
    (a loading page reruns before it reaches the end), and after the footer
    with the button names the page registered. ``page_path`` and the names
    are part of the iframe, so it reloads, and the names update, whenever
    they change."""
    # "<" escaped: a stock name can't close the <script> it sits in.
    cfg = _js({"skip": _("Skip to content"), "nav": pgettext("landmark", "Main")})
    aria = _js(labels()) if names else "null"
    page_script = _js(_PAGE_SCRIPT)
    with st.container(key="uv_hidden_util_a11y" if names else "uv_hidden_util_a11y_early"):
        st.iframe(f"""
<script>
/* page: {html.escape(page_path)} */
(function(){{
  try {{
    var w = window.parent, d = w.document;
    var c = w.__uvA11y || {{labels: {{}}, aria: {{}}}};
    c.labels = {cfg};
    var aria = {aria};
    if (aria !== null) c.aria = aria;
    w.__uvA11y = c;
    if (!d.getElementById('uv-a11y-script')) {{
      var s = d.createElement('script');
      s.id = 'uv-a11y-script';
      s.textContent = {page_script};
      d.head.appendChild(s);
    }} else if (w.__uvA11yApply) {{
      w.__uvA11yApply();
    }}
  }} catch(e) {{}}
}})();
</script>
""", height=1)
