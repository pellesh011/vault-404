import logging
import os

import pyfuse3
import trio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from vaultfs.application.cache import InMemoryCache
from vaultfs.application.chunk_manager import ChunkManager
from vaultfs.application.file_manager import FileManager
from vaultfs.domain.acl import InMemoryACL
from vaultfs.domain.chunk_policy import DefaultChunkPolicy
from vaultfs.infrastructure.asyncio_bridge import AsyncioBridge
from vaultfs.infrastructure.bridged_repository import (
    BridgedMetadataRepository,
    BridgedStorageProvider,
)
from vaultfs.infrastructure.database.repository import SqlAlchemyMetadataRepository
from vaultfs.infrastructure.vault_fs import VaultFS
from vaultfs.storage.memory_provider import MemoryStorageProvider
from vaultfs.storage.provider import ProviderConfig
from vaultfs.storage.provider_factory import StorageProviderRegistry
from vaultfs.storage.telegram_provider import TelegramStorageProvider

logger = logging.getLogger(__name__)


def _load_env() -> None:
    load_dotenv()


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _env_str(key: str, default: str) -> str:
    return os.getenv(key, default)


async def _setup_database(
    database_url: str,
) -> tuple[SqlAlchemyMetadataRepository, AsyncSession, AsyncEngine]:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    repo = SqlAlchemyMetadataRepository(session)
    return repo, session, engine


def _build_telegram_proxy() -> dict[str, str | int | bool] | None:
    proxy_type = os.getenv("TELEGRAM_PROXY_TYPE", "").strip()
    if not proxy_type:
        return None
    addr = os.getenv("TELEGRAM_PROXY_ADDR", "").strip()
    port = os.getenv("TELEGRAM_PROXY_PORT", "").strip()
    if not addr or not port:
        logger.warning(
            "TELEGRAM_PROXY_TYPE is set but TELEGRAM_PROXY_ADDR or TELEGRAM_PROXY_PORT is missing"
        )
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


async def _init_telegram(registry: StorageProviderRegistry, session: AsyncSession) -> None:
    telegram_api_id = os.getenv("TELEGRAM_API_ID")
    telegram_api_hash = os.getenv("TELEGRAM_API_HASH")
    telegram_phone = os.getenv("TELEGRAM_PHONE")

    if not (telegram_api_id and telegram_api_hash and telegram_phone):
        logger.warning("Telegram not configured, skipping telegram provider")
        return

    telegram_config = ProviderConfig(name="telegram", type="telegram")
    telegram_provider = TelegramStorageProvider(config=telegram_config)
    channel_id_raw = os.getenv("TELEGRAM_CHANNEL_ID")
    try:
        await telegram_provider.init(
            api_id=int(telegram_api_id),
            api_hash=telegram_api_hash,
            phone=telegram_phone,
            channel_id=int(channel_id_raw) if channel_id_raw else None,
            session_name=_env_str("TELEGRAM_SESSION_NAME", "vault_session"),
            max_concurrent=_env_int("TELEGRAM_MAX_CONCURRENT", 10),
            proxy=_build_telegram_proxy(),
        )
        registry.add(telegram_provider)
    except Exception:
        logger.exception("Failed to initialize Telegram provider")


def main() -> None:
    log_level = os.getenv("VAULTFS_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _load_env()

    bridge = AsyncioBridge()

    database_url = _env_str(
        "DATABASE_URL",
        "postgresql+asyncpg://vault404:vault404@localhost:5432/vault404",
    )
    db_metadata, session, engine = bridge.run_sync(_setup_database(database_url))

    registry = StorageProviderRegistry()

    mountpoint = _env_str("MOUNTPOINT", "/mnt/vault")
    logger.info("Mounting vaultfs at %s", mountpoint)

    async def _mount() -> None:
        await bridge.run(_init_telegram(registry, session))

        memory_config = ProviderConfig(name="memory", type="memory")
        memory_provider = MemoryStorageProvider(config=memory_config)
        await memory_provider.init()
        registry.add(memory_provider)

        bridged_metadata = BridgedMetadataRepository(db_metadata, bridge)

        # Wrap providers with BridgedStorageProvider for trio compatibility
        for name in list(registry._providers.keys()):
            provider = registry._providers[name]
            registry._providers[name] = BridgedStorageProvider(provider, bridge)

        cache = InMemoryCache()
        default_provider = "telegram" if registry.has("telegram") else "memory"
        chunk_manager = ChunkManager(
            registry=registry,
            metadata=bridged_metadata,
            cache=cache,
            default_provider=default_provider,
        )
        file_manager = FileManager(
            metadata=bridged_metadata,
            chunk_manager=chunk_manager,
            acl=InMemoryACL(),
            chunk_policy=DefaultChunkPolicy(),
        )
        await file_manager.initialize()

        fuse = VaultFS(file_manager)
        fuse_options = set(pyfuse3.default_options)
        fuse_options.add("fsname=vaultfs")
        fuse_options.add("allow_other")

        # Clean up stale mount if exists
        import subprocess

        subprocess.run(["fusermount", "-u", str(mountpoint)], capture_output=True)

        pyfuse3.init(fuse, str(mountpoint), fuse_options)
        try:
            await pyfuse3.main()
        finally:
            try:
                pyfuse3.close()
            except Exception:
                pass
            try:
                await registry.close_all()
            except Exception:
                pass
            try:
                await bridge.run(session.close())
            except Exception:
                pass
            try:
                await bridge.run(engine.dispose())
            except Exception:
                pass
            bridge.close()

    try:
        trio.run(_mount)
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down")
    except BaseException as e:
        if isinstance(e, BaseExceptionGroup):
            matched = e.subgroup(KeyboardInterrupt)
            if matched:
                logger.info("Interrupted, shutting down")
            else:
                logger.exception("Fatal error")
        else:
            logger.exception("Fatal error")
    finally:
        # Ensure mount is cleaned up
        import subprocess

        subprocess.run(["fusermount", "-u", str(mountpoint)], capture_output=True)
        bridge.close()


if __name__ == "__main__":
    main()
