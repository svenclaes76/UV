"""The demo doesn't use the uvalu.app domain (not held, 18 Oct 2026): its
footer contact and every legal page it shows point to the demo mailbox."""
import re

import pytest

from uvalu import datamode
from uvalu.compliance import disclosures as d

DOMAIN = re.compile(r"uvalu\.app(?!@gmail\.com)")


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv(datamode.ENV_VAR, "demo")


def test_contacts_in_demo_mode(demo):
    assert d.producer_contact() == d.DEMO_CONTACT == "uvalu.app@gmail.com"
    assert d.producer_privacy_contact() == d.DEMO_CONTACT


def test_contacts_in_personal_mode(monkeypatch):
    monkeypatch.delenv(datamode.ENV_VAR, raising=False)
    assert d.producer_contact() == d.PRODUCER_CONTACT
    assert d.producer_privacy_contact() == d.PRODUCER_PRIVACY_CONTACT


def test_footer_line_in_demo_mode(demo):
    from uvalu import shell
    line = shell.producer_line()
    assert d.DEMO_CONTACT in line and not DOMAIN.search(line)


@pytest.mark.parametrize("key, _title, file_name", d.LEGAL_DOCS)
def test_legal_pages_shown_in_demo_name_no_domain(demo, key, _title, file_name):
    from uvalu.pages_ import legal
    path, _translated = legal.resolve_doc_path(file_name, "en")
    assert path is not None, key
    text = legal.public_text(path)
    assert not DOMAIN.search(text), (key, DOMAIN.findall(text)[:3])


def test_top_bar_keeps_clear_of_community_cloud_buttons(demo):
    """Community Cloud draws its own buttons over the frame's top-right corner;
    the demo's top bar leaves that room free (personal mode doesn't)."""
    from uvalu import shell
    assert f"{shell.CLOUD_TOOLBAR_GAP_PX}px" in shell._cloud_toolbar_gap_css()


def test_top_bar_has_no_gap_in_personal_mode(monkeypatch):
    monkeypatch.delenv(datamode.ENV_VAR, raising=False)
    from uvalu import shell
    assert shell._cloud_toolbar_gap_css() == ""
