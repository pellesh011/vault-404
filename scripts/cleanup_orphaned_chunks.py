#!/usr/bin/env python3
"""Remove orphaned chunks from storage providers and database.

Orphaned chunks are `chunks` rows with `deleted_at IS NOT NULL` —
they were replaced by newer data but their old data still exists
in Telegram (or another provider).

Usage:

    python scripts/cleanup_orphaned_chunks.py

Requires the same environment variables as the main app
(DATABASE_URL, TELEGRAM_*, etc.).
"""

import argparse
import asyncio
import logging
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from vaultfs.application.garbage_collector import ChunkGarbageCollector
from vaultfs.infrastructure.database.repository import SqlAlchemyMetadataRepository
from vaultfs.storage.provider import ProviderConfig
from vaultfs.storage.provider_factory import StorageProviderRegistry
from vaultfs.storage.telegram_provider import TelegramStorageProvider

logger = logging.getLogger(__name__)


def _build_telegram_proxy() -> dict[str, str | int | bool] | None:
    proxy_type = os.getenv("TELEGRAM_PROXY_TYPE", "").strip()
    if not proxy_type:
        return None
    addr = os.getenv("TELEGRAM_PROXY_ADDR", "").strip()
    port = os.getenv("TELEGRAM_PROXY_PORT", "").strip()
    if not addr or not port:
        return None
    proxy: dict[str, str | int | bool] = {
        "proxy_type": proxy_type,
        "addr": addr,
        "port": int(port),
    }
    username = os.getenv("TELEGRAM_PROXY_USERNAME", "").strip()
    password = os.getenv("TELEGRAM_PROXY_PASSWORD", "").strip()
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password
    return proxy


async def _init_telegram(registry: StorageProviderRegistry) -> None:
    telegram_api_id = os.getenv("TELEGRAM_API_ID")
    telegram_api_hash = os.getenv("TELEGRAM_API_HASH")
    telegram_phone = os.getenv("TELEGRAM_PHONE")

    if not (telegram_api_id and telegram_api_hash and telegram_phone):
        logger.warning("Telegram not configured, skipping telegram provider")
        return

    telegram_config = ProviderConfig(name="telegram", type="telegram")
    telegram_provider = TelegramStorageProvider(config=telegram_config)
    channel_id_raw = os.getenv("TELEGRAM_CHANNEL_ID")
    await telegram_provider.init(
        api_id=int(telegram_api_id),
        api_hash=telegram_api_hash,
        phone=telegram_phone,
        channel_id=int(channel_id_raw) if channel_id_raw else None,
        session_name=os.getenv("TELEGRAM_SESSION_NAME", "vault_session"),
        max_concurrent=int(os.getenv("TELEGRAM_MAX_CONCURRENT", "10")),
        proxy=_build_telegram_proxy(),
    )
    registry.add(telegram_provider)


async def main() -> None:
    load_dotenv()

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://vault404:vault404@localhost:5432/vault404",
    )
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    metadata = SqlAlchemyMetadataRepository(session)

    registry = StorageProviderRegistry()
    try:
        await _init_telegram(registry)
    except Exception:
        logger.exception("Failed to init Telegram provider, will skip Telegram chunks")

    parser = argparse.ArgumentParser(description="Clean up orphaned chunks")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip 1-hour grace period — process all orphans regardless of age",
    )
    args, _ = parser.parse_known_args()

    collector = ChunkGarbageCollector(metadata=metadata, registry=registry)
    cleaned = await collector.collect(force=args.force)
    logger.info("Done. Cleaned up %d orphaned chunks.", cleaned)

    await session.close()
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("VAULTFS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(main())
