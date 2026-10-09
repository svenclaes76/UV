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

Layout: the shared supporting-page frame (components.support_page,
proposal 1d) — the document list and an "On this page" list of the
document's sections in the sticky rail (a document select on a phone); the
document in a card with a header block (title, version/date chips, print)
and a readable measure; a print stylesheet that prints only the document.
"""
import html
import re
from pathlib import Path

import streamlit as st

from uvalu.components import support_page
from uvalu.compliance import disclosures as d
from uvalu.i18n import _, current, tr

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
            out.append(f'<a id="{anchor}" class="uv-anchor"></a>\n')
        out.append(line)
    return "\n".join(out), toc


_CSS = """
/* The document card. Long-form type comes from the frame (styles.py). */
.st-key-legal_doc_body {
  padding: 30px 44px 40px !important; background: var(--panel) !important; border-color: var(--line) !important;
  border-radius: 12px !important; box-shadow: var(--shadow) !important;
}
.st-key-legal_print iframe { display: block; }
/* The document select replaces the rail below 768px. Its wrapper goes too,
   or it still takes a row gap. */
.st-key-legal_doc_select, div:has(> .st-key-legal_doc_select) { display: none !important; }

@media (max-width: 767px) {
  .st-key-legal_doc_select { display: flex !important; }
  div:has(> .st-key-legal_doc_select) { display: block !important; }
  .st-key-legal_print, div:has(> .st-key-legal_print) { display: none !important; }
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
  .st-key-legal_doc_text p, .st-key-legal_doc_text li { max-width: none !important; }
  .st-key-legal_doc_select { display: none !important; }
}
"""


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
    from uvalu.runtime import SIGNAL_TEAL, theme_colors
    tc = theme_colors()
    label = html.escape(_("Print or save as PDF"))
    with st.container(key="legal_print", width="content"):
        st.iframe(f"""<!doctype html><html><head><style>
html,body{{margin:0;background:transparent;text-align:right;}}
button{{font:500 12.5px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:{tc.text};
background:transparent;border:0.5px solid {tc.axis};border-radius:8px;padding:6px 12px;cursor:pointer;
white-space:nowrap;}}
button:hover{{border-color:{SIGNAL_TEAL};}}
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

    # The footer's link to this document reads as "you are here". In a
    # hidden-util container, so the <style> block takes no row gap above the
    # back link (titles line up across the supporting pages).
    with st.container(key="uv_hidden_util_legal_css"):
        st.markdown(f"<style>{_CSS}"
                    # One attribute more than the footer's own link rule, which
                    # renders after this page and would otherwise win the tie.
                    f'.st-key-uv_footer_links a[data-testid="stPageLink-NavLink"][href$="doc={doc}"] p'
                    f' {{ color: var(--text) !important; }}'
                    "</style>", unsafe_allow_html=True)

    content = support_page(
        _("Legal & policies"), back_key="legal",
        rail=[(tr(doc_title), f"/legal?doc={key}") for key, doc_title, _f in d.LEGAL_DOCS],
        active=f"/legal?doc={doc}", toc=toc if len(toc) > 1 else None,
        rail_note=_("During the free beta these pages are available in English only.") if d.BETA else "")
    with content:
        _document(doc, path, translated, title, meta, body)


def _pick_document() -> None:
    """The phone's document select: open the picked document."""
    st.query_params["doc"] = st.session_state["legal_doc_pick"]


def _document(doc: str, path, translated: bool, title: str, meta, body: str) -> None:
    # Phone: the rail is hidden, so a select picks the document.
    with st.container(key="legal_doc_select"):
        st.session_state["legal_doc_pick"] = doc
        titles = {key: tr(doc_title) for key, doc_title, _f in d.LEGAL_DOCS}
        st.selectbox(_("Legal & policies"), options=_DOC_KEYS, format_func=titles.get,
                     key="legal_doc_pick", on_change=_pick_document, label_visibility="collapsed")
    with st.container(key="legal_doc_body", border=True):
        if path is None:
            st.warning(_("This document is not available yet."))
            return
        with st.container(key="legal_doc_eyebrow", horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute", gap="medium"):
            st.markdown(f'<div style="font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;'
                        f'color:var(--muted);">{html.escape(_("Uvalu · Legal"))}</div>',
                        unsafe_allow_html=True, width="content")
            _print_button()
        with st.container(key="legal_doc_head"):
            chips = "".join(_chip(f"{html.escape(label)}: <b style='font-weight:500;color:var(--text);'>"
                                  f"{html.escape(value)}</b>") for label, value in meta)
            ref_note = (f'<div style="font-size:12px;color:var(--muted);margin-top:10px;">'
                        f'{html.escape(tr(d.REFERENCE_LANGUAGE_NOTE))}</div>'
                        # Only over a real translation: on the English
                        # fallback (every page during the beta) the
                        # not-yet-translated notice says enough.
                        if translated and current().lang != "en" else "")
            st.markdown(f'<div style="font-size:20px;font-weight:500;letter-spacing:-0.01em;line-height:1.25;">'
                        f'{html.escape(title)}</div>'
                        f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;">{chips}</div>'
                        f'{ref_note}', unsafe_allow_html=True, width="stretch")
        # Outside the beta an untranslated page says so in the card; during
        # the beta the note in the rail covers every page (LG-03).
        if not translated and not d.BETA:
            with st.container(key="legal_notice"):
                st.markdown(_notice(tr(d.NOT_YET_TRANSLATED)), unsafe_allow_html=True)
        st.markdown('<div style="border-top:0.5px solid var(--line);margin:24px 0 6px;"></div>',
                    unsafe_allow_html=True)
        with st.container(key="legal_doc_text"):
            st.markdown(body, unsafe_allow_html=True)
