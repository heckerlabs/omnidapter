"""Bootstrap script for creating organizations and API keys.

Usage:
    omnidapter-bootstrap --name "My Org"
    omnidapter-bootstrap --name "My Org" --key-name "production"
"""

from __future__ import annotations

import argparse
import asyncio
import uuid


async def create_org_and_key(org_name: str, key_name: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from omnidapter_api.config import get_settings
    from omnidapter_api.models.api_key import APIKey
    from omnidapter_api.models.organization import Organization
    from omnidapter_api.services.auth import generate_api_key

    settings = get_settings()
    engine = create_async_engine(settings.omnidapter_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        # Create organization
        org = Organization(
            id=uuid.uuid4(),
            name=org_name,
            plan="free",
            is_active=True,
        )
        session.add(org)
        await session.flush()

        # Create API key
        raw_key, key_hash, key_prefix = generate_api_key()
        api_key = APIKey(
            id=uuid.uuid4(),
            organization_id=org.id,
            name=key_name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            is_active=True,
        )
        session.add(api_key)
        await session.commit()

        print(f"Organization created: {org.id}")
        print(f"API Key (shown once): {raw_key}")
        print(f"Key prefix: {key_prefix}")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Omnidapter org and API key")
    parser.add_argument("--name", required=True, help="Organization name")
    parser.add_argument("--key-name", default="default", help="API key name (e.g., 'production')")
    args = parser.parse_args()
    asyncio.run(create_org_and_key(args.name, args.key_name))


if __name__ == "__main__":
    main()
