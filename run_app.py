"""Launch the Streamlit app — run this file directly from PyCharm."""
import datetime
import ipaddress
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


if __name__ == "__main__":
    _ensure_cert()
    venv_streamlit = ROOT / ".venv" / "Scripts" / "streamlit.exe"
    subprocess.run([str(venv_streamlit), "run", str(ROOT / "app.py")], check=True)
