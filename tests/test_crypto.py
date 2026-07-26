"""
Unit tests for crypto.py — Fernet-based encryption used for cache files at rest.

All tests set ENCRYPTION_KEY explicitly via monkeypatch rather than relying on
the developer's real .env secret, so they are deterministic and don't touch
any real encrypted data.
"""

import pytest
from cryptography.fernet import InvalidToken

import crypto


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")


class TestEncryptDecryptText:
    def test_roundtrip_returns_original_string(self):
        plain = "hello, world! 日本語 too"
        assert crypto.decrypt_text(crypto.encrypt_text(plain)) == plain

    def test_ciphertext_is_bytes_and_differs_from_plaintext(self):
        ciphertext = crypto.encrypt_text("secret value")
        assert isinstance(ciphertext, bytes)
        assert ciphertext != b"secret value"

    def test_same_plaintext_encrypted_twice_differs(self):
        # Fernet includes a random IV/timestamp, so ciphertexts should not
        # be identical even for identical plaintext.
        c1 = crypto.encrypt_text("same input")
        c2 = crypto.encrypt_text("same input")
        assert c1 != c2
        assert crypto.decrypt_text(c1) == crypto.decrypt_text(c2) == "same input"

    def test_decrypt_with_wrong_key_raises_invalid_token(self, monkeypatch):
        ciphertext = crypto.encrypt_text("top secret")
        monkeypatch.setenv("ENCRYPTION_KEY", "a-different-key")
        with pytest.raises(InvalidToken):
            crypto.decrypt_text(ciphertext)

    def test_missing_key_raises_environment_error(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        with pytest.raises(EnvironmentError):
            crypto.encrypt_text("anything")

    def test_blank_key_raises_environment_error(self, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "   ")
        with pytest.raises(EnvironmentError):
            crypto.encrypt_text("anything")

    def test_key_derivation_is_deterministic_across_calls(self):
        # Simulates a process restart: two independent _fernet() instances
        # built from the same env key must be interoperable.
        ciphertext = crypto.encrypt_text("persisted across restarts")
        assert crypto.decrypt_text(ciphertext) == "persisted across restarts"


class TestReadWriteEncryptedFile:
    def test_roundtrip_via_file(self, tmp_path):
        path = tmp_path / "data.enc"
        crypto.write_encrypted(path, "file contents")
        assert crypto.read_encrypted(path) == "file contents"

    def test_write_creates_missing_parent_directory(self, tmp_path):
        path = tmp_path / ".cache" / "data.enc"
        assert not path.parent.exists()
        crypto.write_encrypted(path, "nested")
        assert path.parent.exists()
        assert crypto.read_encrypted(path) == "nested"

    def test_file_contents_are_not_plaintext_on_disk(self, tmp_path):
        path = tmp_path / "data.enc"
        crypto.write_encrypted(path, "do not leak me")
        assert b"do not leak me" not in path.read_bytes()

    def test_read_encrypted_with_wrong_key_raises(self, tmp_path, monkeypatch):
        path = tmp_path / "data.enc"
        crypto.write_encrypted(path, "sensitive")
        monkeypatch.setenv("ENCRYPTION_KEY", "wrong-key")
        with pytest.raises(InvalidToken):
            crypto.read_encrypted(path)
