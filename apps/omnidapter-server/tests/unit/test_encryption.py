"""Unit tests for AES-256-GCM encryption."""

from __future__ import annotations

import pytest
from omnidapter_server.encryption import EncryptionService, decrypt, encrypt


@pytest.fixture
def key() -> str:
    return "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest.fixture
def key2() -> str:
    return "ZmVkY2JhOTg3NjU0MzIxMGZlZGNiYTk4NzY1NDMyMTA="


def test_encrypt_decrypt_roundtrip(key):
    plaintext = "hello, world!"
    token = encrypt(plaintext, key)
    recovered = decrypt(token, key)
    assert recovered == plaintext


def test_encryption_produces_different_ciphertext_each_time(key):
    plaintext = "same plaintext"
    token1 = encrypt(plaintext, key)
    token2 = encrypt(plaintext, key)
    # Different nonces → different ciphertext
    assert token1 != token2


def test_decryption_with_wrong_key_fails(key, key2):
    plaintext = "secret"
    token = encrypt(plaintext, key)
    with pytest.raises(ValueError):
        decrypt(token, key2)


def test_encrypted_value_not_plaintext(key):
    plaintext = "sensitive-password-123"
    token = encrypt(plaintext, key)
    assert plaintext not in token


def test_key_rotation_current_key(key, key2):
    """Values encrypted with key2 (current) can be decrypted."""
    plaintext = "rotate me"
    token = encrypt(plaintext, key2, key_version="v1")
    recovered = decrypt(token, current_key=key2, previous_key=key)
    assert recovered == plaintext


def test_key_rotation_previous_key(key, key2):
    """Values encrypted with key (previous v0) can be decrypted with previous_key set."""
    plaintext = "old value"
    token = encrypt(plaintext, key, key_version="v0")
    recovered = decrypt(token, current_key=key2, previous_key=key)
    assert recovered == plaintext


def test_invalid_token_format(key):
    with pytest.raises(ValueError):
        decrypt("not-a-valid-token", key)


def test_encryption_service_roundtrip():
    svc = EncryptionService(current_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    plaintext = "encrypt and decrypt me"
    token = svc.encrypt(plaintext)
    recovered = svc.decrypt(token)
    assert recovered == plaintext


def test_encryption_service_key_rotation():
    old_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    new_key = "ZmVkY2JhOTg3NjU0MzIxMGZlZGNiYTk4NzY1NDMyMTA="

    # Encrypt with old key using old service
    old_svc = EncryptionService(current_key=old_key)
    token = old_svc.encrypt("sensitive data")

    # New service with rotation support
    new_svc = EncryptionService(current_key=new_key, previous_key=old_key)
    # Token was encrypted with old key (v1), so we need to use previous key
    # Since both use key_version v1, new_svc should try new_key first (fail), then old_key
    # But token is v1 and new_key will fail → need to fall back to previous_key
    # Actually the decrypt logic tries current first (will fail tag), then previous
    recovered = new_svc.decrypt(token)
    assert recovered == "sensitive data"


def test_encryption_empty_key_raises():
    with pytest.raises(ValueError, match="Encryption key is not configured"):
        encrypt("data", "")


def test_encryption_unicode(key):
    plaintext = "Unicode: こんにちは 🎉"
    token = encrypt(plaintext, key)
    recovered = decrypt(token, key)
    assert recovered == plaintext


def test_encryption_long_string(key):
    plaintext = "x" * 10000
    token = encrypt(plaintext, key)
    recovered = decrypt(token, key)
    assert recovered == plaintext


def test_encryption_service_plaintext_fallback_without_key() -> None:
    svc = EncryptionService(current_key="", allow_plaintext_fallback=True)
    plaintext = '{"access_token":"abc"}'

    token = svc.encrypt(plaintext)
    recovered = svc.decrypt(token)

    assert token == plaintext
    assert recovered == plaintext


def test_encryption_service_plaintext_fallback_rejects_encrypted_tokens(key: str) -> None:
    svc = EncryptionService(current_key="", allow_plaintext_fallback=True)
    token = encrypt("sensitive", key)

    with pytest.raises(ValueError, match="Encrypted token detected"):
        svc.decrypt(token)


def test_encryption_service_plaintext_fallback_allows_non_encrypted_v1_prefix_text() -> None:
    svc = EncryptionService(current_key="", allow_plaintext_fallback=True)
    plaintext = "v1:not-base64-secret"

    assert svc.decrypt(plaintext) == plaintext
