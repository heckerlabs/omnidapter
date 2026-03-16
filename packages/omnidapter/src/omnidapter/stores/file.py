"""
File-backed credential store with optional AES-256-GCM encryption.

Suitable for single-server self-hosted deployments. Not designed for
multi-process or distributed use (no file locking).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any

import anyio.to_thread

from omnidapter.stores.credentials import CredentialStore, StoredCredential

logger = logging.getLogger(__name__)

_KEY_VERSION = "v1"
_SEPARATOR = ":"


def _decode_key(key_str: str) -> bytes:
    """Decode a base64-encoded 32-byte key, or SHA-256 hash a raw string."""
    try:
        raw = base64.urlsafe_b64decode(key_str + "==")
        if len(raw) == 32:
            return raw
    except Exception:
        pass
    import hashlib

    return hashlib.sha256(key_str.encode()).digest()


def _encrypt(plaintext: str, key_str: str) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise ImportError(
            "cryptography is required for encrypted file storage. "
            "Install with: pip install 'omnidapter[encryption]'"
        ) from exc

    key = _decode_key(key_str)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode()
    return f"{_KEY_VERSION}{_SEPARATOR}{encoded}"


def _decrypt(token: str, key_str: str) -> str:
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise ImportError(
            "cryptography is required for encrypted file storage. "
            "Install with: pip install 'omnidapter[encryption]'"
        ) from exc

    if _SEPARATOR not in token:
        raise ValueError("Invalid encrypted token format")

    _, encoded = token.split(_SEPARATOR, 1)
    raw = base64.urlsafe_b64decode(encoded + "==")
    nonce, ciphertext = raw[:12], raw[12:]
    key = _decode_key(key_str)

    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode()
    except InvalidTag as exc:
        raise ValueError("Decryption failed: wrong key or corrupted data") from exc


class EncryptedFileCredentialStore(CredentialStore):
    """File-backed credential store with optional AES-256-GCM encryption.

    Credentials are persisted to a JSON file on disk. If an encryption key
    is available (via the ``encryption_key`` argument or the
    ``OMNIDAPTER_ENCRYPTION_KEY`` environment variable), each credential
    envelope is encrypted with AES-256-GCM before being written. If no key
    is configured, credentials are stored as plaintext JSON and a
    ``UserWarning`` is emitted at construction time.

    Suitable for single-server self-hosted deployments. Not safe for
    multi-process or distributed use — there is no file locking.

    Args:
        path: Path to the credential file. Parent directories are created
            automatically. The file is created on first write.
        encryption_key: AES-256 key as a base64-encoded 32-byte string, or
            any arbitrary string (which will be SHA-256 hashed to 32 bytes).
            If omitted, the value of ``OMNIDAPTER_ENCRYPTION_KEY`` is used.
            If neither is set, credentials are stored unencrypted.
    """

    def __init__(
        self,
        path: str | Path,
        encryption_key: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._key = encryption_key or os.environ.get("OMNIDAPTER_ENCRYPTION_KEY") or ""

        if not self._key:
            warnings.warn(
                "EncryptedFileCredentialStore: no encryption key configured — "
                "credentials will be stored as plaintext. "
                "Set OMNIDAPTER_ENCRYPTION_KEY or pass encryption_key= to enable encryption.",
                UserWarning,
                stacklevel=2,
            )

    # -- sync helpers (run in thread) ----------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        with open(self._path) as f:
            return json.load(f)

    def _flush(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(data, f)

    # -- CredentialStore interface --------------------------------------------

    async def get_credentials(self, connection_id: str) -> StoredCredential | None:
        data = await anyio.to_thread.run_sync(self._load)
        raw = data.get(connection_id)
        if raw is None:
            return None
        json_str = _decrypt(raw, self._key) if self._key else raw
        return StoredCredential.model_validate_json(json_str)

    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None:
        json_str = credentials.model_dump_json()
        value = _encrypt(json_str, self._key) if self._key else json_str

        def _write() -> None:
            data = self._load()
            data[connection_id] = value
            self._flush(data)

        await anyio.to_thread.run_sync(_write)

    async def delete_credentials(self, connection_id: str) -> None:
        def _remove() -> None:
            data = self._load()
            data.pop(connection_id, None)
            self._flush(data)

        await anyio.to_thread.run_sync(_remove)
