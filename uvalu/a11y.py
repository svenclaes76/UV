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
_SS_TABLES = "_uv_tables"


def css_key(key: str) -> str:
    """The class Streamlit gives a keyed element: ``st-key-`` + the key with
    anything outside [A-Za-z0-9_-] replaced (a ticker's "." becomes "-")."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", key)


def begin_run() -> None:
    """Start a fresh set of names for this run (app.py, before the page)."""
    st.session_state[_SS_KEY] = {}
    st.session_state[_SS_TABLES] = []


def table(key: str, name: str, *, header: str, rows: "list[str] | None" = None,
          row_prefix: "str | None" = None, header_names: "dict[int, str] | None" = None,
          sorted_by: "str | None" = None, descending: bool = False) -> None:
    """Mark a grid of rows as a table for screen readers (AC2).

    ``key`` is the container holding it, ``header`` the column-header row's
    container, ``rows`` the row containers' keys, or ``row_prefix`` the
    start they share (every keyed container inside the table whose key
    starts with it). The page script finds the cells itself: the columns of
    a row's st.columns block, or else the children of the row's CSS grid
    (the HTML rows); a column holding a grid of several cells (the dividend
    log's [grid | pencil] split) counts as those cells. A row button outside
    the cells (the full-row "View" overlay) becomes a cell of its own, and
    the header gets a visually hidden "Details" column for it.
    ``header_names`` names header columns that show no text, by index
    (negative counts from the end); ``sorted_by`` is the widget key of the
    sorted column's header button."""
    st.session_state.setdefault(_SS_TABLES, []).append({
        "key": css_key(key), "name": name, "header": css_key(header),
        "rows": [css_key(r) for r in rows or []],
        "prefix": css_key(row_prefix) if row_prefix else None,
        "names": {str(i): n for i, n in (header_names or {}).items()},
        "sort": [css_key(sorted_by), "descending" if descending else "ascending"] if sorted_by else None,
    })


def label(key: str, text: str, *, pressed: bool | None = None) -> None:
    """Name the button with widget key ``key`` for screen readers.
    ``pressed`` makes it a toggle (``aria-pressed``), e.g. a watchlist star."""
    st.session_state.setdefault(_SS_KEY, {})[css_key(key)] = [text, pressed]


def current(key: str) -> None:
    """Mark the button with widget key ``key`` as the current page or
    section (``aria-current="page"``), e.g. the Admin sidebar's open
    section; the mark moves when another key is registered instead."""
    st.session_state.setdefault(_SS_KEY, {})[css_key(key)] = [None, None, "current"]


def image(key: str, text: str) -> None:
    """Make the keyed container one image named ``text`` for screen readers
    (AC6): a chart's summary sentence instead of its axis ticks and points."""
    st.session_state.setdefault(_SS_KEY, {})[css_key(key)] = [text, None, "img"]


def labels() -> dict[str, list]:
    return dict(st.session_state.get(_SS_KEY, {}))


def tables() -> list[dict]:
    return list(st.session_state.get(_SS_TABLES, []))


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
    // The Admin portal has its own sidebar inside the page body: the sidebar
    // is its navigation and only its content area is main.
    var adminMain = d.querySelector('.st-key-admin_content');
    if (adminMain) {
      mark('.st-key-admin_sidebar', 'navigation', 'Admin');
      var um = d.querySelector('.st-key-uv_main');
      if (um && um.getAttribute('role') === 'main') um.removeAttribute('role');
      mark('.st-key-admin_content', 'main');
    } else {
      mark('.st-key-uv_main', 'main');
    }
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
    var currentKeys = {};
    for (var ck in cfg.aria) if (cfg.aria[ck][2] === 'current') currentKeys[ck] = 1;
    var marked = d.querySelectorAll('button[aria-current]');
    for (var q = 0; q < marked.length; q++) {
      var holder = marked[q].closest('[class*="st-key-"]');
      var hk = holder ? (holder.className.match(/st-key-(\S+)/) || [])[1] : null;
      if (!hk || !currentKeys[hk]) marked[q].removeAttribute('aria-current');
    }
    for (var k in cfg.aria) {
      var v = cfg.aria[k], els = d.getElementsByClassName('st-key-' + k);
      if (v[2] === 'current') {
        for (var cc = 0; cc < els.length; cc++) {
          var cbs = els[cc].tagName === 'BUTTON' ? [els[cc]] : els[cc].querySelectorAll('button');
          for (var cb = 0; cb < cbs.length; cb++)
            if (cbs[cb].getAttribute('aria-current') !== 'page') cbs[cb].setAttribute('aria-current', 'page');
        }
        continue;
      }
      if (v[2] === 'img') {
        for (var g = 0; g < els.length; g++) {
          if (els[g].getAttribute('role') !== 'img') els[g].setAttribute('role', 'img');
          if (els[g].getAttribute('aria-label') !== v[0]) els[g].setAttribute('aria-label', v[0]);
        }
        continue;
      }
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
    (cfg.tables || []).forEach(function(t){ applyTable(t, cfg.labels.details); });
  }
  function cellsOf(el){
    // The columns of the row's st.columns block, or the children of its
    // CSS grid (HTML rows), in order.
    var hb = el.querySelector('[data-testid="stHorizontalBlock"]');
    if (hb) {
      var out = [];
      for (var i = 0; i < hb.children.length; i++) {
        var col = hb.children[i];
        if (col.getAttribute('data-testid') !== 'stColumn') continue;
        var cg = gridOf(col);
        if (cg && cg.children.length > 1) out = out.concat(Array.prototype.slice.call(cg.children));
        else out.push(col);
      }
      return out;
    }
    var g = gridOf(el);
    return g ? Array.prototype.slice.call(g.children) : [];
  }
  // React re-serialises inline styles ("display: grid"), so match both.
  function gridOf(el){ return el.querySelector('[style*="display:grid"], [style*="display: grid"]'); }
  function rowsOf(t, box){
    var out = [];
    t.rows.forEach(function(k){ var r = one(k); if (r) out.push(r); });
    if (t.prefix) {
      var c = box.querySelectorAll('[data-testid="stVerticalBlock"][class*="st-key-' + t.prefix + '"]');
      for (var i = 0; i < c.length; i++) {
        var ks = (c[i].className.match(/st-key-\S+/g) || []);
        if (ks.some(function(x){ return x.indexOf('st-key-' + t.prefix) === 0; })) out.push(c[i]);
      }
    }
    return out;
  }
  function one(cls){ var e = d.getElementsByClassName('st-key-' + cls); return e.length ? e[0] : null; }
  function setRole(e, role){ if (e.getAttribute('role') !== role) e.setAttribute('role', role); }
  function applyTable(t, details){
    var box = one(t.key), head = one(t.header);
    if (!box || !head) return;
    setRole(box, 'table');
    if (box.getAttribute('aria-label') !== t.name) box.setAttribute('aria-label', t.name);
    setRole(head, 'row');
    var hcells = cellsOf(head).filter(function(c){ return !c.classList.contains('uv-sr-only'); });
    hcells.forEach(function(c, i){
      setRole(c, 'columnheader');
      // Only a header column that shows no text of its own gets a name.
      var n = t.names[String(i)] || t.names[String(i - hcells.length)];
      if (n && !c.textContent.trim() && c.getAttribute('aria-label') !== n) c.setAttribute('aria-label', n);
      var sorted = t.sort && c.getElementsByClassName('st-key-' + t.sort[0]).length;
      if (sorted) { if (c.getAttribute('aria-sort') !== t.sort[1]) c.setAttribute('aria-sort', t.sort[1]); }
      else if (c.hasAttribute('aria-sort')) c.removeAttribute('aria-sort');
    });
    var most = 0;
    rowsOf(t, box).forEach(function(r){
      setRole(r, 'row');
      var cells = cellsOf(r);
      cells.forEach(function(c){ setRole(c, 'cell'); });
      // A button outside the cells (the row-wide "View" overlay) is a cell too.
      var bs = r.querySelectorAll('button'), extra = 0;
      for (var i = 0; i < bs.length; i++) {
        if (bs[i].closest('[role="cell"]')) continue;
        var w = bs[i].closest('[data-testid="stElementContainer"]');
        if (w && r.contains(w)) { setRole(w, 'cell'); extra++; }
      }
      most = Math.max(most, cells.length + extra);
    });
    // Hidden header cells for those extra row cells, so the columns line up.
    var hidden = head.querySelectorAll(':scope > .uv-sr-only[role="columnheader"]');
    for (var m = hcells.length + hidden.length; m < most; m++) {
      var h = d.createElement('div');
      h.className = 'uv-sr-only'; h.setAttribute('role', 'columnheader'); h.textContent = details;
      head.appendChild(h);
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
    cfg = _js({"skip": _("Skip to content"), "nav": pgettext("landmark", "Main"),
               # Translators: screen readers only: the hidden header of a table's "View" button column.
               "details": _("Details")})
    aria = _js(labels()) if names else "null"
    tabs = _js(tables()) if names else "null"
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
    var aria = {aria}, tabs = {tabs};
    if (aria !== null) c.aria = aria;
    if (tabs !== null) c.tables = tabs;
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
