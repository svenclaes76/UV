"""Unit tests for uvalu/oauth.py — the Streamlit st.login()/st.user glue.

The actual OIDC redirect (st.login()'s browser round-trip) can't be
exercised without real provider credentials; these tests cover everything
around it that's pure logic — provider-configured detection, issuer-label
matching, and current_identity()'s translation of st.user into the shape
auth.oauth_login() expects.
"""
import streamlit as st

from uvalu import oauth


class FakeUser(dict):
    """Minimal stand-in for streamlit.user_info.UserInfoProxy — real st.user
    is a read-only Mapping with attribute access; oauth.py only ever calls
    .is_logged_in and .get(...), both of which a plain dict subclass with an
    added attribute covers."""
    def __init__(self, is_logged_in: bool, **claims):
        super().__init__(**claims)
        self.is_logged_in = is_logged_in


class TestIsConfigured:
    def test_false_when_no_secrets_at_all(self, monkeypatch):
        monkeypatch.setattr(oauth, "_auth_secrets", lambda: {})
        assert oauth.is_configured("google") is False

    def test_false_when_section_missing_a_field(self, monkeypatch):
        monkeypatch.setattr(oauth, "_auth_secrets", lambda: {
            "google": {"client_id": "x", "client_secret": "y"}})  # no server_metadata_url
        assert oauth.is_configured("google") is False

    def test_true_when_fully_configured(self, monkeypatch):
        monkeypatch.setattr(oauth, "_auth_secrets", lambda: {
            "google": {"client_id": "x", "client_secret": "y",
                      "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}})
        assert oauth.is_configured("google") is True

    def test_unconfigured_provider_is_independent(self, monkeypatch):
        monkeypatch.setattr(oauth, "_auth_secrets", lambda: {
            "google": {"client_id": "x", "client_secret": "y",
                      "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}})
        assert oauth.is_configured("microsoft") is False


class TestConfiguredProviders:
    def test_lists_both_with_live_state(self, monkeypatch):
        monkeypatch.setattr(oauth, "_auth_secrets", lambda: {
            "google": {"client_id": "x", "client_secret": "y",
                      "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}})
        rows = {p["id"]: p for p in oauth.configured_providers()}
        assert rows["google"]["configured"] is True
        assert rows["google"]["label"] == "Google"
        assert rows["microsoft"]["configured"] is False
        assert rows["microsoft"]["label"] == "Microsoft Entra ID"


class TestLabelForIssuer:
    def test_google_issuer(self):
        assert oauth.label_for_issuer("https://accounts.google.com") == "Google"

    def test_microsoft_issuer(self):
        assert oauth.label_for_issuer(
            "https://login.microsoftonline.com/common/v2.0") == "Microsoft Entra ID"

    def test_unknown_issuer_falls_back(self):
        assert oauth.label_for_issuer("https://example.okta.com") == "your identity provider"

    def test_empty_issuer_falls_back(self):
        assert oauth.label_for_issuer("") == "your identity provider"


class TestCurrentIdentity:
    def test_none_when_not_logged_in(self, monkeypatch):
        monkeypatch.setattr(st, "user", FakeUser(False))
        assert oauth.current_identity() is None

    def test_none_when_auth_not_configured_at_all(self, monkeypatch):
        # Real st.user raises AttributeError for is_logged_in when secrets.toml
        # has no [auth] section at all -- simulate that exact failure mode.
        class NoAuthUser:
            def __getattr__(self, name):
                raise AttributeError(f'st.user has no attribute "{name}".')
        monkeypatch.setattr(st, "user", NoAuthUser())
        assert oauth.current_identity() is None

    def test_extracts_issuer_subject_email_and_label(self, monkeypatch):
        monkeypatch.setattr(st, "user", FakeUser(
            True, iss="https://accounts.google.com", sub="sub-123", email="Marek.K@Uvalu.eu"))
        identity = oauth.current_identity()
        assert identity == {
            "issuer": "https://accounts.google.com", "subject": "sub-123",
            "email": "marek.k@uvalu.eu", "label": "Google",
        }

    def test_missing_claims_default_to_empty(self, monkeypatch):
        monkeypatch.setattr(st, "user", FakeUser(True))
        identity = oauth.current_identity()
        assert identity == {"issuer": "", "subject": "", "email": "", "label": "your identity provider"}
