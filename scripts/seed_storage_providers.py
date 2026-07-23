"""Seed default storage providers (telegram, memory) into the database.

Usage:
    python -m scripts.seed_storage_providers
"""

import logging
import os
from datetime import UTC, datetime

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vaultfs.infrastructure.database.models import StorageProviderModel

logger = logging.getLogger(__name__)

PROVIDER_DEFS: list[tuple[int, str, str, str | None]] = [
    (1, "telegram", "telegram", "Telegram storage backend"),
    (2, "memory", "memory", "In-memory storage backend (testing)"),
]


async def seed() -> None:
    load_dotenv()
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://vault404:vault404@localhost:5432/vault404",
    )
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        now = datetime.now(UTC).replace(tzinfo=None)
        for provider_id, name, type_, description in PROVIDER_DEFS:
            result = await session.execute(
                select(StorageProviderModel).where(StorageProviderModel.name == name)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                logger.info("Already exists: %s (id=%s)", existing.name, existing.id)
                continue

            model = StorageProviderModel(
                id=provider_id,
                name=name,
                type=type_,
                description=description,
                created_at=now,
                updated_at=now,
                is_active=True,
            )
            session.add(model)
            await session.flush()
            logger.info("Created: %s (id=%s)", model.name, model.id)

        await session.commit()

    await engine.dispose()


def main() -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    import asyncio

    asyncio.run(seed())


if __name__ == "__main__":
    main()
