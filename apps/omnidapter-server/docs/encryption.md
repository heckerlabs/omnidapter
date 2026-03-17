# Encryption

All secrets stored in the database — OAuth access tokens, refresh tokens, PKCE
code verifiers, and OAuth app client secrets — are encrypted at rest using
**AES-256-GCM**.

Implementation: `src/omnidapter_server/encryption.py`

---

## Token Format

Encrypted values are stored as a versioned string:

```
{key_version}:{base64url(nonce || ciphertext || GCM_tag)}
```

- **`key_version`** — `v1` (current) or `v0` (previous, for rotation)
- **`nonce`** — 12 random bytes, unique per encryption operation
- **`ciphertext || GCM_tag`** — output of AES-256-GCM (tag is appended by the
  `cryptography` library)

Example stored value:

```
v1:dGhpcyBpcyBhbiBleGFtcGxlIG9mIHRoZSBlbmNyeXB0ZWQgZm9ybWF0Cg==
```

---

## Key Material

The encryption key is provided via `OMNIDAPTER_ENCRYPTION_KEY` as a
base64url-encoded 32-byte value.

### Generating a key

```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

### Key derivation fallback (development only)

If the key is not valid base64 or shorter than 32 bytes after decoding, the
API falls back to `SHA-256(key_string)` as the key bytes. This allows simple
string keys in development but is **not suitable for production**.

---

## Key Rotation

The API supports zero-downtime key rotation with one previous key in flight.

### Process

1. **Generate a new key:**

   ```bash
   python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
   # → new_key_base64
   ```

2. **Set both keys in the environment:**

   ```bash
   OMNIDAPTER_ENCRYPTION_KEY=<new_key_base64>
   OMNIDAPTER_ENCRYPTION_KEY_PREVIOUS=<old_key_base64>
   ```

3. **Deploy** — new encryptions use `v1` (current key). Old `v0` ciphertext is
   decrypted with the previous key.

4. **Migrate old data** (optional) — run a background job to re-encrypt all
   `v0` values with the new key.

5. **Remove the old key** once no `v0` values remain:

   ```bash
   OMNIDAPTER_ENCRYPTION_KEY=<new_key_base64>
   OMNIDAPTER_ENCRYPTION_KEY_PREVIOUS=
   ```

### How decryption selects the key

```python
def decrypt(token, current_key, previous_key=""):
    version, encoded = token.split(":", 1)
    nonce, ciphertext = raw[:12], raw[12:]

    if version == "v1":          # Current key first, then previous
        keys_to_try = [current_key, previous_key]
    elif version == "v0":        # Previous key first, then current
        keys_to_try = [previous_key, current_key]
    else:                        # Unknown: try all
        keys_to_try = [current_key, previous_key]

    for key in keys_to_try:
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, None)
        except InvalidTag:
            continue

    raise ValueError("Failed to decrypt")
```

---

## Authenticated Encryption

AES-256-GCM provides **authenticated encryption** — any tampering with the
ciphertext or tag causes `cryptography.exceptions.InvalidTag` to be raised on
decryption. This means the API cannot silently return corrupt credentials.

---

## Which Fields Are Encrypted

| Table | Column | Content |
|---|---|---|
| `connections` | `credentials_encrypted` | Full `StoredCredential` JSON (access_token, refresh_token, expiry, scopes) |
| `provider_configs` | `client_id_encrypted` | OAuth app client ID |
| `provider_configs` | `client_secret_encrypted` | OAuth app client secret |
| `oauth_states` | `pkce_verifier_encrypted` | PKCE code_verifier (temporary) |

---

## EncryptionService

The `EncryptionService` class wraps the low-level functions and reads keys from
settings:

```python
class EncryptionService:
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, token: str) -> str: ...

    @classmethod
    def from_settings(cls) -> EncryptionService: ...
```

In FastAPI, it is provided as a dependency:

```python
def get_encryption_service(settings: Settings = Depends(get_settings)) -> EncryptionService:
    return EncryptionService(
        current_key=settings.omnidapter_encryption_key,
        previous_key=settings.omnidapter_encryption_key_previous,
    )
```

---

## Security Notes

- Each encryption call generates a **fresh random 12-byte nonce** via
  `os.urandom(12)`. Nonce collisions are computationally negligible for this
  use case.
- Keys are never logged or included in error messages.
- In production, consider using a KMS (AWS KMS, GCP KMS) to manage the key
  material rather than storing it in environment variables.
