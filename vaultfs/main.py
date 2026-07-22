import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vaultfs.application.cache import InMemoryCache
from vaultfs.application.chunk_manager import ChunkManager
from vaultfs.application.file_manager import FileManager
from vaultfs.domain.acl import InMemoryACL
from vaultfs.domain.chunk_policy import DefaultChunkPolicy
from vaultfs.infrastructure.database.repository import SqlAlchemyMetadataRepository
from vaultfs.infrastructure.vault_fs import mount_vaultfs
from vaultfs.storage.memory_provider import MemoryStorageProvider
from vaultfs.storage.metadata import InMemoryMetadataRepository
from vaultfs.storage.provider import ProviderConfig
from vaultfs.storage.provider_factory import StorageProviderRegistry
from vaultfs.storage.telegram_provider import TelegramStorageProvider

logger = logging.getLogger(__name__)


def _load_env() -> None:
    load_dotenv()
    required = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_PHONE"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        logger.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _env_str(key: str, default: str) -> str:
    return os.getenv(key, default)


async def _run() -> None:
    _load_env()

    database_url = _env_str(
        "DATABASE_URL",
        "postgresql+asyncpg://vault404:vault404@localhost:5432/vault404",
    )
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()

    db_metadata = SqlAlchemyMetadataRepository(session)

    registry = StorageProviderRegistry()

    telegram_metadata = InMemoryMetadataRepository()
    telegram_config = ProviderConfig(name="telegram", type="telegram")
    telegram_provider = TelegramStorageProvider(config=telegram_config)
    await telegram_provider.init(
        api_id=_env_int("TELEGRAM_API_ID", 0),
        api_hash=_env_str("TELEGRAM_API_HASH", ""),
        metadata=telegram_metadata,
        phone=_env_str("TELEGRAM_PHONE", ""),
        channel_id=os.getenv("TELEGRAM_CHANNEL_ID"),
        session_name=_env_str("TELEGRAM_SESSION_NAME", "vault_session"),
        max_concurrent=_env_int("TELEGRAM_MAX_CONCURRENT", 10),
    )
    registry.add(telegram_provider)

    memory_config = ProviderConfig(name="memory", type="memory")
    memory_provider = MemoryStorageProvider(config=memory_config)
    await memory_provider.init()
    registry.add(memory_provider)

    cache = InMemoryCache()

    chunk_manager = ChunkManager(
        registry=registry,
        metadata=db_metadata,
        cache=cache,
        default_provider="telegram",
    )

    file_manager = FileManager(
        metadata=db_metadata,
        chunk_manager=chunk_manager,
        acl=InMemoryACL(),
        chunk_policy=DefaultChunkPolicy(),
    )

    mountpoint = _env_str("MOUNTPOINT", "/mnt/vault")
    logger.info("Mounting vaultfs at %s", mountpoint)

    loop = asyncio.get_running_loop()

    async def shutdown() -> None:
        logger.info("Shutting down...")
        await registry.close_all()
        await session.close()
        await engine.dispose()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    await mount_vaultfs(file_manager, mountpoint, foreground=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
