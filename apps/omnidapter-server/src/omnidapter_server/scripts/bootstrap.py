"""Bootstrap script for creating an API key.

Usage:
    omnidapter-bootstrap --name "production"
    omnidapter-bootstrap --name "test-key" --test
"""

from __future__ import annotations

import argparse
import asyncio
import uuid


async def create_api_key(key_name: str, is_test: bool) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from omnidapter_server.config import get_settings
    from omnidapter_server.models.api_key import APIKey
    from omnidapter_server.services.auth import generate_api_key

    settings = get_settings()
    engine = create_async_engine(settings.omnidapter_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        raw_key, key_hash, key_prefix = generate_api_key(is_test=is_test)
        api_key = APIKey(
            id=uuid.uuid4(),
            name=key_name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            is_active=True,
            is_test=is_test,
        )
        session.add(api_key)
        await session.commit()

        print(f"API Key (shown once): {raw_key}")
        print(f"Key prefix: {key_prefix}")
        print(f"is_test: {is_test}")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Omnidapter API key")
    parser.add_argument("--name", required=True, help="Key name (e.g., 'production')")
    parser.add_argument("--test", action="store_true", help="Create a test key (omni_test_ prefix)")
    args = parser.parse_args()
    asyncio.run(create_api_key(args.name, args.test))


if __name__ == "__main__":
    main()
