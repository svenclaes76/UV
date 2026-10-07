"""Brand tooltips for the app's own markup.

Raw-HTML elements (signal badges, provenance times, the stale-price chip,
truncated column headers, …) carry their tooltip text in a plain ``title``
attribute. The browser draws those itself, in the operating system's style:
Chrome on Windows follows the OS dark mode, not the app theme, so a light
page showed dark tooltips — and CSS can't reach them.

This script, injected once per page (app.py), takes over: on hover or focus
it moves an element's ``title`` into ``data-uv-tip`` (so the native tooltip
never shows) and shows one shared ``position:fixed`` tooltip (styles.py
``.uv-tip``), which a card's ``overflow:hidden`` can't clip. Call sites keep
writing ``title=`` — nothing to change there, and if the script doesn't run
the native tooltip still appears.

Scope: text the app renders through st.markdown / st.caption only, not
Streamlit's own widgets (their ``help=`` tooltips are styled in styles.py)
and not iframes. Plotly hover labels use runtime.brand_hoverlabel().
"""
import streamlit as st

# Elements whose title becomes a brand tooltip.
SCOPE = ('[data-testid="stMarkdownContainer"] [title], [data-testid="stMarkdownContainer"] [data-uv-tip], '
         '[data-testid="stCaptionContainer"] [title], [data-testid="stCaptionContainer"] [data-uv-tip]')

SCRIPT = """
(() => {
  if (window.__uvTip) return;
  window.__uvTip = true;
  const SCOPE = %(scope)s;
  const GAP = 8, EDGE = 8;
  const tip = document.createElement("div");
  tip.className = "uv-tip"; tip.id = "uv-tip"; tip.setAttribute("role", "tooltip");
  document.body.appendChild(tip);
  let current = null;

  const target = (node) => (node && node.closest) ? node.closest(SCOPE) : null;

  function show(el) {
    const own = el.getAttribute("title");
    if (own) { el.setAttribute("data-uv-tip", own); el.removeAttribute("title"); }
    const text = el.getAttribute("data-uv-tip");
    if (!text) return;
    current = el;
    el.setAttribute("aria-describedby", "uv-tip");
    tip.textContent = text;
    tip.classList.add("uv-tip-on");
    const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
    let top = r.bottom + GAP;
    if (top + t.height > window.innerHeight - EDGE) top = Math.max(EDGE, r.top - GAP - t.height);
    let left = r.left + r.width / 2 - t.width / 2;
    left = Math.min(Math.max(EDGE, left), window.innerWidth - t.width - EDGE);
    tip.style.top = top + "px"; tip.style.left = left + "px";
  }

  function hide() {
    if (current) current.removeAttribute("aria-describedby");
    current = null;
    tip.classList.remove("uv-tip-on");
  }

  document.addEventListener("mouseover", (e) => {
    const el = target(e.target);
    if (el === current) return;
    if (el) show(el); else hide();
  }, true);
  document.addEventListener("focusin", (e) => { const el = target(e.target); if (el) show(el); }, true);
  document.addEventListener("focusout", hide, true);
  document.addEventListener("scroll", hide, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); }, true);
  window.addEventListener("blur", hide);
})();
"""


def script() -> str:
    """The tooltip script, with its selector filled in."""
    import json
    return SCRIPT % {"scope": json.dumps(SCOPE)}


def inject() -> None:
    """Install the tooltip script on the page (idempotent across reruns)."""
    with st.container(key="uv_hidden_util_tooltips"):
        st.html(f"<script>{script()}</script>", unsafe_allow_javascript=True)
