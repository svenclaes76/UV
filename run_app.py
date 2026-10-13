"""Launch the Streamlit app: generate the localhost TLS cert, bring the stored
data up to this version's schema (uvalu/migrations — VM-08/VM-09), stamp the
build metadata (tools/stamp_build.py — VM-05), then start Streamlit.

Run with ``python run_app.py`` (or double-click ``run_app.bat`` on Windows).
"""
import datetime
import ipaddress
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SSL_DIR  = ROOT / ".ssl"
CERT_FILE = SSL_DIR / "cert.pem"
KEY_FILE  = SSL_DIR / "key.pem"


def _ensure_cert() -> None:
    """Generate a self-signed localhost cert if one doesn't exist yet."""
    if CERT_FILE.exists() and KEY_FILE.exists():
        return

    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    print("Generating self-signed TLS certificate for localhost…")
    SSL_DIR.mkdir(exist_ok=True)

    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )

    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    KEY_FILE.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    print(f"Certificate written to {CERT_FILE}")


def _migrate_data() -> "int | None":
    """Apply pending data migrations (after a snapshot) — plan decision D7.
    Downgrades are never automatic. Exits when the data can't be brought to
    this version's schema: the app would refuse to serve it anyway (VM-09)."""
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from uvalu import migrations
    try:
        applied = migrations.upgrade()
        if applied:
            print(f"Data migrated: {applied}")
        return migrations.ensure_compatible()
    except migrations.MigrationError as exc:
        print(f"\nUvalu cannot start: {exc}\n", file=sys.stderr)
        sys.exit(2)


def _check_passwordless_accounts() -> None:
    """T1: warn when an account can't sign in because it has no password and
    the beta offers password sign-in only. Never stops the app."""
    try:
        from uvalu import oauth
        if oauth.providers_enabled():
            return
        from auth import passwordless_accounts
        found = passwordless_accounts()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Password-account check skipped: {exc}")
        return
    if found:
        print()
        print(f"WARNING: {len(found)} account(s) have no password and can't sign in "
              "(the beta offers password sign-in only):")
        for email, _status, _providers in found:
            print(f"  {email}")
        print("Fix: Admin portal → Users → ⋯ → Send password reset → Generate reset link, "
              "and send each person the link.")
        print()


def _stamp_build(schema_version: "int | None") -> None:
    """Write build_info.json + static/version.json for this checkout. A failure
    here must never stop the app from starting — uvalu.buildinfo falls back to
    computing the same fields in-process."""
    try:
        sys.path.insert(0, str(ROOT))
        from tools.stamp_build import stamp
        info = stamp(schema_version=schema_version)
        print(f"Uvalu {info.display_version} ({info.commit}, {info.environment})")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Build stamp skipped: {exc}")


def _streamlit_args(port: str, behind_proxy: bool) -> list[str]:
    """Streamlit command line. Behind the reverse proxy (UVALU_BEHIND_PROXY=1,
    docs/deployment.md) the app listens on localhost only, over plain HTTP:
    Caddy terminates TLS with a real certificate, so the self-signed cert in
    .streamlit/config.toml is switched off."""
    args = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.port", port]
    if behind_proxy:
        args += ["--server.address", "127.0.0.1",
                 "--server.sslCertFile", "", "--server.sslKeyFile", "",
                 "--server.headless", "true",
                 "--server.enableXsrfProtection", "true",
                 "--browser.gatherUsageStats", "false"]
    return args


if __name__ == "__main__":
    _behind_proxy = os.environ.get("UVALU_BEHIND_PROXY") == "1"
    if not _behind_proxy:
        _ensure_cert()
    _schema = _migrate_data()
    _check_passwordless_accounts()
    _stamp_build(_schema)
    port = os.environ.get("PORT", "8501")
    subprocess.run(_streamlit_args(port, _behind_proxy), check=True)