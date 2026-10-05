"""Legal pages — Terms of use, Privacy notice, Methodology, Data sources,
Conflicts of interest, Complaints — rendered from docs/legal/policies/
(Uvalu.dc.html's "Legal" screen; TOU-9, GDPR-1, REC-3, REC-5, REC-8, TOU-8).

Linked from the footer on every screen (uvalu/shell.py), from the badges'
methodology link, the user menu and Settings. The document is chosen by the
``doc`` query parameter (a key of uvalu.compliance.disclosures.LEGAL_DOCS).

File lookup, most specific first: ``beta/<lang>/``, ``beta/``, ``<lang>/``,
then the English launch version. While disclosures.BETA is on, the beta
texts (decision B4) describe what is actually true during the free beta.
A language without its own reviewed translation falls back to English with
a notice (INT-1, INT-2).

Layout (visual review 2026-10-04, §1.3): a sticky left column with the
document list and an "On this page" list of the document's sections; the
document in a card with a header block (title, version/date chips, print)
and a readable measure; a print stylesheet that prints only the document.
"""
import html
import re
from pathlib import Path

import streamlit as st

from uvalu import nav as nav_registry
from uvalu.compliance import disclosures as d
from uvalu.i18n import _, current, h_, tr

POLICIES_DIR = Path(__file__).resolve().parents[2] / "docs" / "legal" / "policies"
_DOC_KEYS = [key for key, _title, _file in d.LEGAL_DOCS]

def resolve_doc_path(file_name: str, lang: str, *, beta: bool | None = None,
                     root: Path | None = None) -> tuple[Path | None, bool]:
    """(path, translated) for a policy file: the most specific existing
    version, and whether it is in ``lang`` (False = English fallback)."""
    root = root or POLICIES_DIR
    beta = d.BETA if beta is None else beta
    dirs = ([root / "beta" / lang, root / "beta"] if beta else []) + [root / lang, root]
    for folder in dirs:
        path = folder / file_name
        if path.exists():
            in_lang = folder.name == lang or lang == "en"
            return path, in_lang
    return None, False


def _strip_header(md: str) -> str:
    """Drop the leading HTML drafting comment (internal notes, not public)."""
    return re.sub(r"\A\s*<!--.*?-->\s*", "", md, count=1, flags=re.S)


def split_document(md: str) -> tuple[str, list[tuple[str, str]], str]:
    """(title, [(label, value), …], body) of a policy file: the ``# Title``
    line, the ``**Version:** … · **Last updated:** …`` line under it as chip
    pairs, and the rest. Missing parts come back empty, never raise."""
    lines = md.splitlines()
    title, meta, i = "", [], 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].startswith("# "):
        title = lines[i][2:].strip()
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines) and lines[i].lstrip().startswith("**") and ":**" in lines[i]:
            meta = [(m.group(1).strip(), m.group(2).strip())
                    for m in re.finditer(r"\*\*(.+?):\*\*\s*([^·]+)", lines[i])]
            i += 1
    return title, meta, "\n".join(lines[i:]).strip()


def anchor_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    """The body with an anchor before every ``## `` heading, and the
    [(anchor id, heading text)] list for the "On this page" navigation."""
    toc, out = [], []
    for line in body.splitlines():
        if line.startswith("## "):
            anchor = f"sec-{len(toc) + 1}"
            toc.append((anchor, re.sub(r"[*_`]", "", line[3:]).strip()))
            out.append(f'<a id="{anchor}" class="uv-legal-anchor"></a>\n')
        out.append(line)
    return "\n".join(out), toc


_CSS = """
/* Left column: sticky, so the document list and the section list stay in
   reach while reading a 4 000 px Terms page. */
[data-testid="stColumn"]:has(.st-key-legal_nav) {
  position: sticky; top: 16px; align-self: flex-start;
}
.st-key-legal_doc_list { gap: 2px !important; }
.st-key-legal_doc_list a[data-testid="stPageLink-NavLink"] {
  height: auto !important; min-height: 0 !important; background: none !important;
  padding: 6px 10px !important; border-radius: 0 6px 6px 0 !important;
  border-left: 2px solid transparent; gap: 0 !important;
}
.st-key-legal_doc_list a[data-testid="stPageLink-NavLink"] > span:has([data-testid="stIconMaterial"]) { display: none !important; }
.st-key-legal_doc_list a[data-testid="stPageLink-NavLink"] p {
  font-size: 13px !important; color: var(--muted) !important; line-height: 1.35 !important;
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
}
.st-key-legal_doc_list a[data-testid="stPageLink-NavLink"]:hover p { color: var(--text) !important; }
[class*="st-key-legal_nav_active"] a[data-testid="stPageLink-NavLink"] {
  border-left-color: var(--teal); background: var(--soft) !important;
}
[class*="st-key-legal_nav_active"] a[data-testid="stPageLink-NavLink"] p {
  color: var(--text) !important; font-weight: 500 !important;
}
.uv-legal-toc a { display: block; padding: 3px 0 3px 12px; font-size: 12px; line-height: 1.4;
  color: var(--muted); text-decoration: none; border-left: 0.5px solid var(--line); }
.uv-legal-toc a:hover { color: var(--teal); }

/* The document: readable measure and heading rhythm. */
.st-key-legal_doc_body { padding: 24px 28px 28px !important; }
.st-key-legal_doc_text [data-testid="stMarkdownContainer"] { max-width: 72ch; }
.st-key-legal_doc_text h2 { font-size: 18px !important; font-weight: 500 !important;
  margin: 32px 0 8px !important; padding: 0 !important; }
.st-key-legal_doc_text li { margin-bottom: 6px; }
.uv-legal-anchor { display: block; scroll-margin-top: 16px; }
.st-key-legal_print iframe { display: block; }

/* Phone: the columns stack, the document list sits above the document; the
   section list (long, and the document follows) and the print button
   (wrapped onto its own line) are hidden. */
@media (max-width: 640px) {
  [data-testid="stColumn"]:has(.st-key-legal_nav) { position: static; }
  .st-key-legal_toc, .st-key-legal_print { display: none !important; }
  .st-key-legal_doc_body { padding: 18px 16px !important; }
}

/* Print / save as PDF: only the document, black on white, full length
   (the app scrolls inside stMain, which would otherwise clip the page). */
@media print {
  html, body, .stApp, [data-testid="stAppViewContainer"], section.stMain,
  [data-testid="stMainBlockContainer"] {
    height: auto !important; overflow: visible !important; background: #fff !important;
  }
  body * { visibility: hidden !important; }
  .st-key-legal_doc_body, .st-key-legal_doc_body * { visibility: visible !important; color: #000 !important; }
  .st-key-legal_doc_body { position: absolute !important; left: 0; top: 0; width: 100% !important;
    border: none !important; box-shadow: none !important; background: #fff !important; padding: 0 !important; }
  .st-key-legal_print, .st-key-legal_notice { display: none !important; }
  .st-key-legal_doc_text [data-testid="stMarkdownContainer"] { max-width: none; }
}
"""


def _back_target():
    """(page, label) for "← Back": the page the user came from in this
    session (uvalu/nav.py), the Dashboard otherwise."""
    page, _key = nav_registry.back_target("legal")
    if page is None:
        return None, ""
    return page, _("← Back to {page}", page=page.title)


def _chip(text: str) -> str:
    return (f'<span style="display:inline-flex;align-items:center;gap:4px;font-size:11.5px;color:var(--muted);'
            f'background:var(--soft);border:0.5px solid var(--line);border-radius:6px;padding:2px 9px;'
            f'white-space:nowrap;">{text}</span>')


def _notice(text: str) -> str:
    """The app's info notice (Risk page style), not Streamlit's blue st.info."""
    return ('<div style="display:flex;gap:10px;align-items:flex-start;padding:10px 14px;margin:14px 0 4px;'
            'border:0.5px solid var(--line);border-radius:8px;font-size:12.5px;color:var(--muted);'
            'line-height:1.5;"><span style="flex:none;">ⓘ</span>'
            f'<span>{html.escape(text)}</span></div>')


def _print_button() -> None:
    """Print / save as PDF: the browser's print dialog for this page, which
    the print stylesheet narrows to the document. An iframe button, because
    markdown can't carry an onclick."""
    from uvalu.runtime import theme_colors
    tc = theme_colors()
    label = html.escape(_("Print or save as PDF"))
    with st.container(key="legal_print", width="content"):
        st.iframe(f"""<!doctype html><html><head><style>
html,body{{margin:0;background:transparent;text-align:right;}}
button{{font:500 12.5px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:{tc.text};
background:transparent;border:0.5px solid {tc.axis};border-radius:8px;padding:6px 12px;cursor:pointer;
white-space:nowrap;}}
button:hover{{border-color:#1A8C6E;}}
</style></head><body><button onclick="window.parent.print()">⎙ {label}</button></body></html>""",
                  height=34, width=len(label) * 7 + 56)


def render() -> None:
    doc = st.query_params.get("doc", "terms")
    if doc not in _DOC_KEYS:
        doc = "terms"
    file_name = next(f for k, _t, f in d.LEGAL_DOCS if k == doc)
    path, translated = resolve_doc_path(file_name, current().lang)
    title, meta, body = split_document(_strip_header(path.read_text(encoding="utf-8"))) if path else ("", [], "")
    body, toc = anchor_sections(body)

    # The footer's link to this document reads as "you are here".
    st.markdown(f"<style>{_CSS}"
                # One attribute more than the footer's own link rule, which
                # renders after this page and would otherwise win the tie.
                f'.st-key-uv_footer_links a[data-testid="stPageLink-NavLink"][href$="doc={doc}"] p'
                f' {{ color: var(--text) !important; }}'
                "</style>", unsafe_allow_html=True)

    _back, _back_label = _back_target()
    if _back is not None and st.button(_back_label, key="legal_back", type="tertiary"):
        st.switch_page(_back)

    nav_col, body_col = st.columns([1, 3.4], gap="large")
    with nav_col, st.container(key="legal_nav"):
        st.markdown(f'<div style="font-size:10.5px;letter-spacing:0.08em;text-transform:uppercase;'
                    f'color:var(--faint);margin-bottom:6px;">{h_("Legal & policies")}</div>',
                    unsafe_allow_html=True)
        page = nav_registry.pages.get("legal")
        with st.container(key="legal_doc_list"):
            for key, doc_title, _f in d.LEGAL_DOCS:
                if page is not None:
                    with st.container(key=f"legal_nav_active_{key}" if key == doc else f"legal_nav_{key}"):
                        st.page_link(page, label=tr(doc_title), query_params={"doc": key})
        if len(toc) > 1:
            with st.container(key="legal_toc"):
                links = "".join(f'<a href="#{a}" target="_self">{html.escape(t)}</a>' for a, t in toc)
                st.markdown(f'<div style="font-size:10.5px;letter-spacing:0.08em;text-transform:uppercase;'
                            f'color:var(--faint);margin:14px 0 6px;">{h_("On this page")}</div>'
                            f'<nav class="uv-legal-toc">{links}</nav>', unsafe_allow_html=True)

    with body_col, st.container(key="legal_doc_body", border=True):
        if path is None:
            st.warning(_("This document is not available yet."))
            return
        with st.container(key="legal_doc_head", horizontal=True, vertical_alignment="top",
                          horizontal_alignment="distribute", gap="medium"):
            chips = "".join(_chip(f"{html.escape(label)}: <b style='font-weight:500;color:var(--text);'>"
                                  f"{html.escape(value)}</b>") for label, value in meta)
            ref_note = (f'<div style="font-size:11.5px;color:var(--faint);margin-top:10px;">'
                        f'{html.escape(tr(d.REFERENCE_LANGUAGE_NOTE))}</div>'
                        # Only over a real translation: on the English
                        # fallback (every page during the beta) the
                        # not-yet-translated notice says enough.
                        if translated and current().lang != "en" else "")
            st.markdown(f'<div style="font-size:26px;font-weight:500;letter-spacing:-0.02em;line-height:1.2;">'
                        f'{html.escape(title)}</div>'
                        f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;">{chips}</div>'
                        f'{ref_note}', unsafe_allow_html=True, width="stretch")
            _print_button()
        if not translated:
            with st.container(key="legal_notice"):
                st.markdown(_notice(tr(d.NOT_YET_TRANSLATED)), unsafe_allow_html=True)
        st.markdown('<div style="border-top:0.5px solid var(--line);margin:18px 0 4px;"></div>',
                    unsafe_allow_html=True)
        with st.container(key="legal_doc_text"):
            st.markdown(body, unsafe_allow_html=True)
