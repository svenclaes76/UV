"""AppTest coverage for uvalu/pages_/legal.py's frame (supporting-screens
proposal 1d). The document contents are covered by tests/test_legal_guards.py."""
import pytest
from streamlit.testing.v1 import AppTest

from uvalu import nav as nav_registry


@pytest.fixture(autouse=True)
def _clean_nav_registry():
    # uvalu.nav.pages is process-global (tests/test_app_smoke.py fills it).
    saved = dict(nav_registry.pages)
    nav_registry.pages.clear()
    yield
    nav_registry.pages.clear()
    nav_registry.pages.update(saved)


def _run(doc: str = "terms") -> AppTest:
    script = f"""
import streamlit as st
from uvalu import nav as nav_registry
from uvalu.pages_ import legal as page
nav_registry.pages["dashboard"] = st.Page(lambda: None, title="Dashboard", url_path="dashboard", default=True)
nav_registry.pages["legal"] = st.Page(page.render, title="Legal", url_path="legal")
if "doc" not in st.query_params:
    st.query_params["doc"] = {doc!r}
page.render()
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_title_back_link_and_document_heading():
    at = _run()
    md = "".join(m.value for m in at.markdown)
    assert 'class="uv-support-title"' in md and "Legal &amp; policies" in md
    assert [b.label for b in at.button] == ["← Back to Dashboard"]
    assert at.button[0].key == "legal_back"
    # The document title inside the card is 20px (was 26px).
    assert "font-size:20px" in md and "font-size:26px" not in md


def test_rail_lists_every_document_and_marks_the_open_one():
    from uvalu.compliance.disclosures import LEGAL_DOCS
    at = _run("privacy")
    links = at.get("page_link")
    assert len(links) == len(LEGAL_DOCS)
    md = "".join(m.value for m in at.markdown)
    # "On this page" lists the document's sections.
    assert "On this page" in md and 'href="#sec-1"' in md


def test_phone_document_select_opens_the_picked_document():
    at = _run("terms")
    select = at.selectbox(key="legal_doc_pick")
    assert select.value == "terms"
    select.set_value("privacy").run()
    assert not at.exception
    assert at.query_params["doc"] == ["privacy"]
    assert "Privacy notice — free beta" in "".join(m.value for m in at.markdown)
