"""
Legal guardrails across the whole app (Track G of
docs/legal/compliance-implementation-plan.md).

  • wording — no UI string uses the banned terms of DIS-5 / DIS-6 / PER-4 or
    the retired BUY/MONITOR/AVOID/VETO badge words (scans locales/messages.pot,
    so a new screen can't bring one back);
  • beta scope — the shipped config offers all six reviewed languages
    (decision B5, lifted Oct 4 2026);
  • legal pages — every page exists, the beta texts win while BETA is on, and
    the in-app page and the footer render.

The algorithm-level rules (PER-1/2, REC-*, DATA-6) are pinned in
tests/test_compliance_algorithms.py.
"""
import json
import re
from pathlib import Path

import pytest
from babel.messages.pofile import read_po
from streamlit.testing.v1 import AppTest

from uvalu.compliance import disclosures
from uvalu.pages_ import legal

ROOT = Path(__file__).resolve().parents[1]

# Case-sensitive: the retired badge words, as badges.
_BADGE_WORDS = re.compile(r"\b(Strong Buy|BUY|MONITOR|AVOID|VETO)\b")
# Case-insensitive: advice / promise / prescription wording. ("adviser" stays
# allowed: the full disclaimer's "consult an authorised adviser" is the
# requirements doc's own text.)
_BANNED = re.compile(
    r"recommended for you|\byour personal\b|consider (selling|reducing|buying|exiting)"
    r"|\brebalanc|beat the market|find winners|know when to buy|safe stocks|\bconviction\b"
    r"|hard[- ]veto|\btrim to\b|\bredeploy\b|guaranteed return",
    re.I)


def _pot_msgids() -> list[str]:
    with (ROOT / "locales" / "messages.pot").open("rb") as fh:
        catalog = read_po(fh)
    out = []
    for msg in catalog:
        if msg.id:
            out.extend(msg.id if isinstance(msg.id, tuple) else (msg.id,))
    return out


class TestWording:
    def test_no_ui_string_uses_a_retired_badge_word(self):
        hits = [t for t in _pot_msgids() if _BADGE_WORDS.search(t)]
        assert not hits, hits

    def test_no_ui_string_uses_banned_advice_wording(self):
        hits = [t for t in _pot_msgids() if _BANNED.search(t)]
        assert not hits, hits

    def test_disclosure_texts_are_clean(self):
        texts = [v for k, v in vars(disclosures).items() if k.isupper() and isinstance(v, str)]
        assert texts
        for text in texts:
            assert not _BADGE_WORDS.search(text) and not _BANNED.search(text), text


class TestBetaScope:
    def test_shipped_config_offers_the_six_reviewed_languages(self):
        raw = json.loads((ROOT / "i18n.config.json").read_text(encoding="utf-8"))
        assert raw["i18n"]["enabled_languages"] == ["en", "nl", "fr", "de", "it", "es"]

    def test_beta_is_on(self):
        assert disclosures.BETA is True


class TestLegalPages:
    @pytest.mark.parametrize("key,title,file_name", disclosures.LEGAL_DOCS)
    def test_every_launch_page_exists(self, key, title, file_name):
        assert (legal.POLICIES_DIR / file_name).exists()

    def test_beta_texts_win_while_beta_is_on(self):
        path, translated = legal.resolve_doc_path("terms-of-use.md", "en", beta=True)
        assert path.parent.name == "beta" and translated
        path, _t = legal.resolve_doc_path("terms-of-use.md", "en", beta=False)
        assert path.parent == legal.POLICIES_DIR
        # every page has a beta version (Complaints since Oct 5 2026: the launch
        # text cites the launch Terms' section numbers); the launch-page
        # fallback is covered by test_untranslated_language_falls_back_to_english
        for _key, _title, file_name in disclosures.LEGAL_DOCS:
            path, _t = legal.resolve_doc_path(file_name, "en", beta=True)
            assert path.parent.name == "beta", file_name

    @pytest.mark.parametrize("lang", ["nl", "fr", "de", "it", "es"])
    def test_every_page_is_available_in_english_for_every_language(self, lang):
        """English-only beta texts (Oct 5 2026): every enabled language gets
        the English version of every page, never "not available"."""
        for _key, _title, file_name in disclosures.LEGAL_DOCS:
            path, _t = legal.resolve_doc_path(file_name, lang, beta=True)
            assert path is not None and path.exists(), (lang, file_name)

    def test_untranslated_language_falls_back_to_english(self, tmp_path):
        (tmp_path / "beta").mkdir()
        (tmp_path / "x.md").write_text("# X", encoding="utf-8")
        path, translated = legal.resolve_doc_path("x.md", "nl", beta=True, root=tmp_path)
        assert path == tmp_path / "x.md" and translated is False
        (tmp_path / "nl").mkdir()
        (tmp_path / "nl" / "x.md").write_text("# X nl", encoding="utf-8")
        path, translated = legal.resolve_doc_path("x.md", "nl", beta=True, root=tmp_path)
        assert path == tmp_path / "nl" / "x.md" and translated is True

    def test_beta_texts_say_what_is_true_in_the_beta(self):
        beta = legal.POLICIES_DIR / "beta"
        def public(name):   # without the internal drafting comment
            return legal._strip_header((beta / name).read_text(encoding="utf-8"))

        terms = public("terms-of-use.md")
        assert "Mollie" not in terms and "withdraw" not in terms.lower()
        privacy = public("privacy-notice.md")
        assert "Mollie" not in privacy and "Brevo" not in privacy
        # Password sign-in only while providers are off (design reference v1.3).
        from uvalu import oauth
        if not oauth.providers_enabled():
            assert "Google" not in privacy and "_streamlit_user" not in privacy
        assert "Have I Been Pwned" in privacy                     # G36
        data = public("data-sources.md")
        assert "Yahoo Finance" in data and "EODHD" not in data

    def test_legal_page_renders_the_requested_document(self):
        def _script():
            import streamlit as st
            st.query_params["doc"] = "privacy"
            from uvalu.pages_ import legal as page
            page.render()

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        md = "".join(m.value for m in at.markdown)
        assert "Privacy notice — free beta" in md
        assert "<!--" not in md    # the drafting comment is not public
        # Header chips from the "**Version:** … · **Effective from:** …" line,
        # a section list, and the reference-language note only outside English.
        assert "beta 1.4" in md and "Effective from" in md
        assert 'href="#sec-1"' in md and 'id="sec-1"' in md
        assert "Reference language" not in md

    def test_reference_note_hidden_on_the_english_fallback(self, monkeypatch):
        """A Dutch user sees the English page with the not-yet-translated
        notice, without the "rely on the version in your own language" note."""
        def _script():
            import streamlit as st
            from uvalu import i18n
            st.session_state[i18n._SS_CTX] = i18n.with_(i18n._default_ctx(), lang="nl", region="nl-BE")
            st.query_params["doc"] = "terms"
            from uvalu.pages_ import legal as page
            page.render()

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        md = "".join(m.value for m in at.markdown)
        assert "Terms of use — free beta" in md
        assert "Reference language" not in md and "Referentietaal" not in md
        # …while the English-only note sits in the rail (rendered in Dutch,
        # LG-03) instead of a notice in the document card.
        assert 'class="uv-rail-note"' in md and "alleen in het Engels" in md
        assert "ⓘ" not in md

    def test_split_document_reads_title_meta_and_body(self):
        md = ("# Terms of use — free beta\n\n"
              "**Version:** beta 1.0 · **Effective from:** the opening of the free beta\n\n"
              "Intro.\n\n## 1. Who we are\n\nText.\n")
        title, meta, body = legal.split_document(md)
        assert title == "Terms of use — free beta"
        assert meta == [("Version", "beta 1.0"), ("Effective from", "the opening of the free beta")]
        assert body.startswith("Intro.") and "**Version:**" not in body
        assert legal.split_document("No heading here.") == ("", [], "No heading here.")

    def test_anchor_sections_builds_the_on_this_page_list(self):
        body, toc = legal.anchor_sections("Intro\n## 1. **Who** we are\nx\n## 2. The free beta\ny")
        assert toc == [("sec-1", "1. Who we are"), ("sec-2", "2. The free beta")]
        assert body.index('id="sec-1"') < body.index("## 1.") < body.index('id="sec-2"')

    def test_every_policy_file_has_a_title_and_version_line(self):
        for _key, _title, file_name in disclosures.LEGAL_DOCS:
            for beta in (True, False):
                path, _t = legal.resolve_doc_path(file_name, "en", beta=beta)
                title, meta, _body = legal.split_document(legal._strip_header(path.read_text(encoding="utf-8")))
                assert title, path
                assert meta and meta[0][0] == "Version", path


class TestFooter:
    def test_footer_carries_disclaimer_producer_and_supervision_note(self):
        def _script():
            from uvalu.shell import render_footer
            render_footer()

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        md = "".join(m.value for m in at.markdown)
        assert "Uvalu is an analysis tool." in md
        assert "Sven Claes" in md and "registration pending" in md
        assert "Not authorised or supervised by the FSMA" in md
        # INT-5/6 moved to the Terms (test below); the footer stays short.
        assert "Not directed at residents" not in md

    @pytest.mark.parametrize("terms", ["beta/terms-of-use.md", "terms-of-use.md", "demo/terms-of-use.md"])
    def test_terms_state_the_service_is_not_directed_at_uk_us_ch(self, terms):
        """INT-5 / INT-6: the Terms of use say the service is not directed at
        UK, US or Swiss residents (removed from the footer, Oct 4 2026)."""
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "docs" / "legal" / "policies" / terms).read_text(encoding="utf-8")
        assert ("Uvalu is not directed at residents of the United Kingdom, the United States "
                "or Switzerland.") in text
