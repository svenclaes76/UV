"""Legal pages — Terms of use, Privacy notice, Methodology, Data sources,
Conflicts of interest, Complaints — rendered from docs/legal/policies/
(Uvalu.dc.html's "Legal" screen; TOU-9, GDPR-1, REC-3, REC-5, REC-8, TOU-8).

Linked from the footer on every screen (uvalu/shell.py), from the badges'
methodology link and from Settings. The document is chosen by the ``doc``
query parameter (a key of uvalu.compliance.disclosures.LEGAL_DOCS).

File lookup, most specific first: ``beta/<lang>/``, ``beta/``, ``<lang>/``,
then the English launch version. While disclosures.BETA is on, the beta
texts (decision B4) describe what is actually true during the free beta.
A language without its own reviewed translation falls back to English with
a notice (INT-1, INT-2).
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


def render() -> None:
    doc = st.query_params.get("doc", "terms")
    if doc not in _DOC_KEYS:
        doc = "terms"
    file_name = next(f for k, _t, f in d.LEGAL_DOCS if k == doc)

    _back = nav_registry.pages.get("dashboard")
    if _back is not None and st.button(_("← Back"), key="legal_back", type="tertiary"):
        st.switch_page(_back)

    nav_col, body_col = st.columns([1, 3.4], gap="large")
    with nav_col:
        st.markdown(f'<div style="font-size:10.5px;letter-spacing:0.08em;text-transform:uppercase;'
                    f'color:var(--faint);margin-bottom:8px;">{h_("Legal & policies")}</div>',
                    unsafe_allow_html=True)
        page = nav_registry.pages.get("legal")
        with st.container(key="legal_doc_list"):
            for key, doc_title, _f in d.LEGAL_DOCS:
                if page is not None:
                    st.page_link(page, label=("● " if key == doc else "") + tr(doc_title),
                                 query_params={"doc": key})
        st.caption(tr(d.REFERENCE_LANGUAGE_NOTE))

    with body_col, st.container(key="legal_doc_body", border=True):
        path, translated = resolve_doc_path(file_name, current().lang)
        if path is None:
            st.warning(_("This document is not available yet."))
            return
        if not translated:
            st.info(tr(d.NOT_YET_TRANSLATED))
        if d.BETA:
            st.markdown(f'<div style="font-size:10.5px;letter-spacing:0.08em;text-transform:uppercase;'
                        f'color:var(--faint);">{h_("Uvalu · Legal")} · {html.escape(_("Free beta"))}</div>',
                        unsafe_allow_html=True)
        st.markdown(_strip_header(path.read_text(encoding="utf-8")))
