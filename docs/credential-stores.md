# Credential Stores

Omnidapter separates credential management from calendar logic. Your application owns persistence — Omnidapter calls into two abstract interfaces at runtime.

## Interfaces

### `CredentialStore`

Stores and retrieves `StoredCredential` envelopes keyed by a `connection_id`.

```python
from omnidapter.stores.credentials import CredentialStore, StoredCredential

class CredentialStore(ABC):
    async def get_credentials(self, connection_id: str) -> StoredCredential | None: ...
    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None: ...
    async def delete_credentials(self, connection_id: str) -> None: ...
```

Omnidapter calls `save_credentials` automatically after every successful token refresh, so your store always holds the current access token.

### `OAuthStateStore`

Temporarily persists OAuth state between the authorization redirect and the callback.

```python
from omnidapter.stores.oauth_state import OAuthStateStore

class OAuthStateStore(ABC):
    async def save_state(self, state_id: str, payload: dict, expires_at: datetime) -> None: ...
    async def load_state(self, state_id: str) -> dict | None: ...
    async def delete_state(self, state_id: str) -> None: ...
```

State is deleted automatically after a successful OAuth completion.

---

## `connection_id`

A `connection_id` is an **opaque, caller-managed string** — Omnidapter never generates, validates, or interprets it. Your app creates it and controls the mapping to users.

Common patterns:

```python
# UUID per connected account (recommended)
connection_id = str(uuid.uuid4())

# Composite key
connection_id = f"{user_id}:{provider}"

# Your DB row ID
connection_id = str(db_connection_row.id)
```

You're responsible for storing the `connection_id → user` mapping in your own database. Omnidapter only uses it as a lookup key.

---

## `StoredCredential`

The envelope Omnidapter reads from and writes to your store:

```python
class StoredCredential(BaseModel):
    provider_key: str                                            # "google", "microsoft", etc.
    auth_kind: AuthKind                                          # OAUTH2, BASIC, API_KEY
    credentials: OAuth2Credentials | BasicCredentials | ApiKeyCredentials
    granted_scopes: list[str] | None = None
    provider_account_id: str | None = None                       # provider's user ID if available
    provider_config: dict[str, Any] | None = None                # e.g. {"server_url": "..."}
```

`OAuth2Credentials` contains `access_token`, `refresh_token`, `expires_at`, and a `raw` dict for any non-standard provider fields.

---

## In-Memory Stores (development only)

`InMemoryCredentialStore` and `InMemoryOAuthStateStore` are the defaults when you don't provide stores:

```python
omni = Omnidapter()  # uses in-memory stores
```

**Do not use in-memory stores in production.** Their limitations:

| Problem | Impact |
|---|---|
| **Process restart** | All credentials lost — users must re-authenticate |
| **Multiple instances** | Each process has its own isolated store. Instance A saves a token; Instance B can't find it. Breaks OAuth callbacks (state saved on A, callback hits B) and refreshes |
| **No durability** | Credentials vanish on crash, deploy, scale-down |
| **No encryption** | Tokens sit in plaintext in Python heap memory |

In-memory stores are appropriate for: local development, automated tests, CLIs that store credentials for a single session.

---

## Encryption

OAuth tokens are sensitive credentials. If an attacker obtains a valid refresh token, they have long-lived access to a user's calendar. **Always encrypt tokens at rest.**

Install the `cryptography` package:

```bash
pip install cryptography
```

Derive a Fernet key from a secret (store the secret in your environment, not in code):

```python
import base64
import os
from cryptography.fernet import Fernet
import hashlib

def _fernet_from_secret(secret: str) -> Fernet:
    # Derive a 32-byte key from your secret using SHA-256
    key = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))
```

---

## Example: Encrypted SQLAlchemy Store

A production-ready credential store backed by a relational database with Fernet encryption.

```python
import json
import base64
import hashlib
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase

from omnidapter.stores.credentials import CredentialStore, StoredCredential


class Base(DeclarativeBase):
    pass


class CredentialRow(Base):
    __tablename__ = "omnidapter_credentials"

    connection_id = Column(String(255), primary_key=True)
    encrypted_payload = Column(Text, nullable=False)
    provider_key = Column(String(64), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class EncryptedSQLCredentialStore(CredentialStore):
    """SQLAlchemy credential store with Fernet encryption.

    Args:
        session_factory: Async SQLAlchemy session factory (e.g. async_sessionmaker).
        encryption_secret: Secret used to derive the Fernet encryption key.
            Load this from an environment variable, never hardcode it.
    """

    def __init__(self, session_factory, encryption_secret: str) -> None:
        self._session_factory = session_factory
        key = hashlib.sha256(encryption_secret.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key))

    def _encrypt(self, credential: StoredCredential) -> str:
        plaintext = credential.model_dump_json()
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, encrypted: str) -> StoredCredential:
        plaintext = self._fernet.decrypt(encrypted.encode()).decode()
        return StoredCredential.model_validate_json(plaintext)

    async def get_credentials(self, connection_id: str) -> StoredCredential | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(CredentialRow).where(CredentialRow.connection_id == connection_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._decrypt(row.encrypted_payload)

    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None:
        async with self._session_factory() as session:
            encrypted = self._encrypt(credentials)
            row = await session.get(CredentialRow, connection_id)
            if row is None:
                row = CredentialRow(connection_id=connection_id)
                session.add(row)
            row.encrypted_payload = encrypted
            row.provider_key = credentials.provider_key
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()

    async def delete_credentials(self, connection_id: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(CredentialRow, connection_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
```

Usage:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/mydb")
session_factory = async_sessionmaker(engine, expire_on_commit=False)

omni = Omnidapter(
    credential_store=EncryptedSQLCredentialStore(
        session_factory=session_factory,
        encryption_secret=os.environ["OMNIDAPTER_ENCRYPTION_KEY"],
    ),
    oauth_state_store=...,
)
```

---

## Example: Redis OAuth State Store

OAuth state needs to be visible across all instances — Redis is a natural fit since it's shared and supports TTL-based expiry.

```python
import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

from omnidapter.stores.oauth_state import OAuthStateStore


class RedisOAuthStateStore(OAuthStateStore):
    """Redis-backed OAuth state store.

    Automatically expires state entries using Redis TTL,
    matching the expiry set by Omnidapter (default: 15 minutes).
    """

    def __init__(self, redis_url: str, key_prefix: str = "omnidapter:oauth:") -> None:
        self._redis = aioredis.from_url(redis_url)
        self._prefix = key_prefix

    def _key(self, state_id: str) -> str:
        return f"{self._prefix}{state_id}"

    async def save_state(self, state_id: str, payload: dict, expires_at: datetime) -> None:
        ttl_seconds = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        await self._redis.setex(
            self._key(state_id),
            ttl_seconds,
            json.dumps(payload),
        )

    async def load_state(self, state_id: str) -> dict | None:
        data = await self._redis.get(self._key(state_id))
        if data is None:
            return None
        return json.loads(data)

    async def delete_state(self, state_id: str) -> None:
        await self._redis.delete(self._key(state_id))
```

Usage:

```python
omni = Omnidapter(
    credential_store=EncryptedSQLCredentialStore(...),
    oauth_state_store=RedisOAuthStateStore(redis_url=os.environ["REDIS_URL"]),
)
```

---

## Production checklist

- [ ] Implement `CredentialStore` backed by your database
- [ ] Encrypt tokens at rest (Fernet example above)
- [ ] Load encryption key from environment, never commit it
- [ ] Implement `OAuthStateStore` backed by shared storage (Redis, database) — not in-memory
- [ ] Set appropriate TTLs on OAuth state (Omnidapter defaults to 15 minutes)
- [ ] Rotate encryption keys periodically (re-encrypt stored credentials after rotation)
- [ ] Audit log credential saves and deletes
