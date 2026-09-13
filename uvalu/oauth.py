"""Google/Microsoft OAuth glue between Streamlit's built-in st.login()/
st.user (Authlib-based OIDC, configured via secrets.toml's [auth] /
[auth.<provider>] sections) and auth.py's user store.

Kept separate from auth.py so that module can stay framework-agnostic (plain
pytest, no live Streamlit script context needed) — everything here needs one.

No real provider credentials exist in this deployment yet (see docs/
uvalu-auth-implementation-plan.md's Phase 1 and Auth GUI Impact.dc.html) — the
whole point of is_configured() is that every caller here already degrades
gracefully to "not configured" rather than assuming Google is live.
"""
import streamlit as st

# Phase 1 ships Google; Microsoft is drawn everywhere as the unconfigured
# second entry so adding it later is a secrets.toml + one more line here, not
# a new screen anywhere in the app (Uvalu Auth.dc.html's whole point).
PROVIDERS = (
    {"id": "google", "label": "Google"},
    {"id": "microsoft", "label": "Microsoft Entra ID"},
)

# Matched against st.user's `iss` claim to render a human label for an
# already-linked identity (Settings -> Linked accounts, Admin -> Users).
# Identities themselves are keyed on the raw issuer URL, never on this label
# — see auth.py's "Provider identities (OAuth)" section.
_ISSUER_LABELS = (
    ("accounts.google.com", "Google"),
    ("microsoftonline.com", "Microsoft Entra ID"),
    ("windows.net", "Microsoft Entra ID"),
)


def _auth_secrets() -> dict:
    try:
        auth = st.secrets.get("auth")
    except Exception:
        # No secrets.toml at all (StreamlitSecretNotFoundError) or any other
        # issue reading it — treated the same as "auth not configured" rather
        # than surfacing an error on every render of the sign-in wall.
        return {}
    return dict(auth) if auth else {}


def is_configured(provider_id: str) -> bool:
    """True if secrets.toml has a usable [auth.<provider_id>] section —
    client_id, client_secret and server_metadata_url all present."""
    section = _auth_secrets().get(provider_id)
    return bool(isinstance(section, dict) and section.get("client_id")
               and section.get("client_secret") and section.get("server_metadata_url"))


def configured_providers() -> list[dict]:
    """Every entry in PROVIDERS with its live configured state — the list
    the sign-in screen's provider buttons render from (Uvalu Auth.dc.html
    frame 01's `sc-for list="{{ providers }}"`)."""
    return [{**p, "configured": is_configured(p["id"])} for p in PROVIDERS]


def label_for_issuer(issuer: str) -> str:
    for needle, label in _ISSUER_LABELS:
        if needle in (issuer or ""):
            return label
    return "your identity provider"


def start_login(provider_id: str) -> None:
    st.login(provider_id)


def current_identity() -> dict | None:
    """{issuer, subject, email, label} for the OIDC session Streamlit is
    already holding via its own identity cookie, or None if nobody's
    completed one right now (including: no [auth] section configured at
    all, in which case st.user itself raises rather than reading False)."""
    try:
        logged_in = st.user.is_logged_in
    except AttributeError:
        return None
    if not logged_in:
        return None
    issuer = st.user.get("iss", "") or ""
    return {
        "issuer":  issuer,
        "subject": st.user.get("sub", "") or "",
        "email":   (st.user.get("email", "") or "").strip().lower(),
        "label":   label_for_issuer(issuer),
    }


def sign_out() -> None:
    st.logout()
