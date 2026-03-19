# Encryption

Server uses `EncryptionService` for sensitive fields.

## Environment keys

- `OMNIDAPTER_ENCRYPTION_KEY` (active key)
- `OMNIDAPTER_ENCRYPTION_KEY_PREVIOUS` (optional fallback for rotation)

## Behavior

- New writes use current key.
- Reads can decrypt with current or previous key when configured.
- Provider client credentials and stored tokens are encrypted at rest.

## Rotation approach

1. Set new key as current, old key as previous.
2. Run traffic and migration/backfill paths.
3. Re-encrypt older rows where needed.
4. Remove previous key after completion.
