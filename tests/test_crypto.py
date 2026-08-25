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

    def test_key_derivation_is_cached_not_repeated_per_call(self, monkeypatch):
        # PBKDF2 at 200k iterations is deliberately slow -- _fernet() used to
        # re-derive it from scratch on every single encrypt/decrypt call
        # despite ENCRYPTION_KEY never changing mid-process. Reset the
        # module-level cache first so an earlier test's cached key (this
        # fixture uses the same "unit-test-key-123" value throughout the
        # file) doesn't make this assert against a call that already
        # happened before this test ran.
        monkeypatch.setattr(crypto, "_cached_key", None)
        monkeypatch.setattr(crypto, "_cached_fernet", None)
        calls = []
        real_pbkdf2 = crypto.pbkdf2_hmac
        monkeypatch.setattr(crypto, "pbkdf2_hmac",
                            lambda *a, **k: (calls.append(1), real_pbkdf2(*a, **k))[1])
        crypto.encrypt_text("first")
        crypto.encrypt_text("second")
        crypto.decrypt_text(crypto.encrypt_text("third"))
        assert len(calls) == 1

    def test_key_derivation_re_runs_when_the_key_actually_changes(self, monkeypatch):
        monkeypatch.setattr(crypto, "_cached_key", None)
        monkeypatch.setattr(crypto, "_cached_fernet", None)
        calls = []
        real_pbkdf2 = crypto.pbkdf2_hmac
        monkeypatch.setattr(crypto, "pbkdf2_hmac",
                            lambda *a, **k: (calls.append(1), real_pbkdf2(*a, **k))[1])
        crypto.encrypt_text("under key one")
        monkeypatch.setenv("ENCRYPTION_KEY", "a-different-key")
        crypto.encrypt_text("under key two")
        assert len(calls) == 2


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

    def test_write_creates_multiple_missing_parent_directories(self, tmp_path):
        # mkdir(exist_ok=True) alone (no parents=True) only creates ONE
        # missing level -- raises FileNotFoundError when the parent's own
        # parent is missing too. tmp_path/".cache"/"data.enc" above only
        # exercises the one-level case (tmp_path itself always exists), so
        # it wouldn't have caught this; this path is missing two levels.
        path = tmp_path / "data" / "settings" / "data.enc"
        assert not path.parent.exists()
        crypto.write_encrypted(path, "deeply nested")
        assert crypto.read_encrypted(path) == "deeply nested"

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
