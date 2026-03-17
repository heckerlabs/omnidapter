"""Unit tests for API key generation, hashing, and verification."""

from __future__ import annotations

from omnidapter_server.services.auth import generate_api_key, verify_api_key


def test_generate_live_key_format():
    raw_key, key_hash, key_prefix = generate_api_key(is_test=False)
    assert raw_key.startswith("omni_live_")
    assert len(raw_key) > 10


def test_generate_test_key_format():
    raw_key, key_hash, key_prefix = generate_api_key(is_test=True)
    assert raw_key.startswith("omni_test_")
    assert len(raw_key) > 10


def test_generate_api_key_prefix_matches_raw():
    raw_key, key_hash, key_prefix = generate_api_key()
    assert raw_key.startswith(key_prefix)


def test_api_key_hash_is_one_way():
    raw_key, key_hash, key_prefix = generate_api_key()
    assert raw_key not in key_hash
    _, key_hash2, _ = generate_api_key()
    assert key_hash != key_hash2


def test_api_key_verify_correct():
    raw_key, key_hash, _ = generate_api_key()
    assert verify_api_key(raw_key, key_hash) is True


def test_api_key_verify_wrong_key():
    _, key_hash, _ = generate_api_key()
    assert verify_api_key("omni_live_wrongkey1234567890123456", key_hash) is False


def test_api_key_verify_tampered_hash():
    raw_key, key_hash, _ = generate_api_key()
    assert verify_api_key(raw_key, "tampered" + key_hash) is False


def test_api_key_prefix_length():
    raw_key, _, key_prefix = generate_api_key()
    assert len(key_prefix) == 12  # "omni_live_" (10) + 2 chars


def test_generate_multiple_keys_are_unique():
    keys = {generate_api_key()[0] for _ in range(20)}
    assert len(keys) == 20


def test_verify_invalid_hash_returns_false():
    assert verify_api_key("omni_live_test", "invalid_hash") is False


def test_verify_empty_strings():
    assert verify_api_key("", "") is False


def test_live_key_is_not_test():
    raw_key, _, _ = generate_api_key(is_test=False)
    assert "test" not in raw_key.split("_")[1]


def test_key_default_is_live():
    raw_key, _, _ = generate_api_key()
    assert raw_key.startswith("omni_live_")
