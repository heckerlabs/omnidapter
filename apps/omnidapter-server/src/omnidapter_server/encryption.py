"""AES-256-GCM encryption for credentials at rest.

Each encrypted value is stored as: {key_version}:{base64(nonce + ciphertext + tag)}

Key rotation: when OMNIDAPTER_ENCRYPTION_KEY_PREVIOUS is set, the previous key
can still decrypt values encrypted with that key. New values are always encrypted
with the current key.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_VERSION_CURRENT = "v1"
_KEY_VERSION_PREVIOUS = "v0"
_SEPARATOR = ":"


def _decode_urlsafe_base64(value: str) -> bytes:
    padding = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding))


def _decode_key(key_str: str) -> bytes:
    """Decode a URL-safe base64 encoded 32-byte key."""
    normalized = key_str.strip()
    if not normalized:
        raise ValueError("Encryption key is not configured")

    try:
        raw = _decode_urlsafe_base64(normalized)
    except Exception as exc:
        raise ValueError("Encryption key must be URL-safe base64") from exc

    if len(raw) != 32:
        raise ValueError("Encryption key must decode to exactly 32 bytes")

    return raw


def encrypt(plaintext: str, encryption_key: str, key_version: str = _KEY_VERSION_CURRENT) -> str:
    """Encrypt a plaintext string.

    Returns a versioned, base64-encoded ciphertext string.
    """
    key = _decode_key(encryption_key)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode()
    return f"{key_version}{_SEPARATOR}{encoded}"


def decrypt(
    token: str,
    current_key: str,
    previous_key: str = "",
) -> str:
    """Decrypt a versioned ciphertext token.

    Tries current key first, falls back to previous key for rotation.
    """
    if _SEPARATOR not in token:
        raise ValueError("Invalid encrypted token format")

    version, encoded = token.split(_SEPARATOR, 1)
    raw = _decode_urlsafe_base64(encoded)
    nonce, ciphertext = raw[:12], raw[12:]

    # Determine which key to try based on version
    if version == _KEY_VERSION_CURRENT:
        keys_to_try = [(current_key, version)]
        if previous_key:
            keys_to_try.append((previous_key, _KEY_VERSION_PREVIOUS))
    elif version == _KEY_VERSION_PREVIOUS:
        keys_to_try = []
        if previous_key:
            keys_to_try.append((previous_key, version))
        keys_to_try.append((current_key, _KEY_VERSION_CURRENT))
    else:
        # Unknown version, try all available keys
        keys_to_try = [(current_key, _KEY_VERSION_CURRENT)]
        if previous_key:
            keys_to_try.append((previous_key, _KEY_VERSION_PREVIOUS))

    last_err: Exception | None = None
    for key_str, _ in keys_to_try:
        if not key_str:
            continue
        try:
            key = _decode_key(key_str)
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode()
        except (InvalidTag, ValueError) as e:
            last_err = e
            continue

    raise ValueError(f"Failed to decrypt token: {last_err}")


class EncryptionService:
    """Encryption service that reads keys from settings."""

    def __init__(self, current_key: str, previous_key: str = "") -> None:
        self._current_key = current_key
        self._previous_key = previous_key

    def encrypt(self, plaintext: str) -> str:
        return encrypt(plaintext, self._current_key)

    def decrypt(self, token: str) -> str:
        return decrypt(token, self._current_key, self._previous_key)

    @classmethod
    def from_settings(cls) -> EncryptionService:
        from omnidapter_server.config import get_settings

        s = get_settings()
        return cls(
            current_key=s.omnidapter_encryption_key,
            previous_key=s.omnidapter_encryption_key_previous,
        )
