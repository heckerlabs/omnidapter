"""Unit tests for API key generation, hashing, and verification."""

from __future__ import annotations

from omnidapter_api.services.auth import generate_api_key, verify_api_key


def test_generate_api_key_format():
    raw_key, key_hash, key_prefix = generate_api_key()
    assert raw_key.startswith("omni_sk_")
    assert len(raw_key) > 10


def test_generate_api_key_prefix_matches_raw():
    raw_key, key_hash, key_prefix = generate_api_key()
    assert raw_key.startswith(key_prefix)


def test_api_key_hash_is_one_way():
    raw_key, key_hash, key_prefix = generate_api_key()
    # The hash should not contain the raw key
    assert raw_key not in key_hash
    # And it should be different each time (bcrypt adds salt)
    _, key_hash2, _ = generate_api_key()
    assert key_hash != key_hash2  # Different keys → different hashes


def test_api_key_verify_correct():
    raw_key, key_hash, _ = generate_api_key()
    assert verify_api_key(raw_key, key_hash) is True


def test_api_key_verify_wrong_key():
    _, key_hash, _ = generate_api_key()
    assert verify_api_key("omni_sk_wrongkey123456789012345678", key_hash) is False


def test_api_key_verify_tampered_hash():
    raw_key, key_hash, _ = generate_api_key()
    # Tamper with the hash
    assert verify_api_key(raw_key, "tampered" + key_hash) is False


def test_api_key_prefix_length():
    raw_key, _, key_prefix = generate_api_key()
    assert len(key_prefix) == 12  # "omni_sk_" (8) + 4 chars


def test_generate_multiple_keys_are_unique():
    keys = {generate_api_key()[0] for _ in range(20)}
    assert len(keys) == 20  # All unique


def test_verify_invalid_hash_returns_false():
    assert verify_api_key("omni_sk_test", "invalid_hash") is False


def test_verify_empty_strings():
    assert verify_api_key("", "") is False
