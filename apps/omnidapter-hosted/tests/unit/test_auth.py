"""Unit tests for hosted API key generation and verification."""

from __future__ import annotations

from omnidapter_hosted.services.auth import generate_hosted_api_key, verify_hosted_api_key


def test_generate_live_key():
    raw_key, key_hash, key_prefix = generate_hosted_api_key(is_test=False)
    assert raw_key.startswith("omni_live_")
    assert len(raw_key) > 10


def test_generate_test_key():
    raw_key, key_hash, key_prefix = generate_hosted_api_key(is_test=True)
    assert raw_key.startswith("omni_test_")


def test_key_prefix_length():
    raw_key, _, key_prefix = generate_hosted_api_key()
    assert len(key_prefix) == 12
    assert raw_key.startswith(key_prefix)


def test_verify_correct_key():
    raw_key, key_hash, _ = generate_hosted_api_key()
    assert verify_hosted_api_key(raw_key, key_hash) is True


def test_verify_wrong_key():
    _, key_hash, _ = generate_hosted_api_key()
    assert verify_hosted_api_key("omni_live_wrongkeyvalue12345678901", key_hash) is False


def test_verify_tampered_hash():
    raw_key, key_hash, _ = generate_hosted_api_key()
    assert verify_hosted_api_key(raw_key, "tampered" + key_hash) is False


def test_verify_invalid_hash():
    assert verify_hosted_api_key("omni_live_anything", "not_a_valid_hash") is False


def test_verify_empty():
    assert verify_hosted_api_key("", "") is False


def test_unique_keys():
    keys = {generate_hosted_api_key()[0] for _ in range(20)}
    assert len(keys) == 20


def test_hash_differs_per_key():
    _, hash1, _ = generate_hosted_api_key()
    _, hash2, _ = generate_hosted_api_key()
    assert hash1 != hash2


def test_default_is_live():
    raw_key, _, _ = generate_hosted_api_key()
    assert raw_key.startswith("omni_live_")
