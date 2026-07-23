import uuid

from vaultfs.infrastructure.asyncio_bridge import AsyncioBridge
from vaultfs.infrastructure.database.repository import (
    Chunk,
    FileChunk,
    MetadataRepository,
    Node,
    SqlAlchemyMetadataRepository,
    StorageProviderModel,
)
from vaultfs.infrastructure.key_manager import DatabaseKeyManager
from vaultfs.storage.encryption import KeyManager
from vaultfs.storage.interface import ChunkId
from vaultfs.storage.provider import StorageProvider


class BridgedStorageProvider(StorageProvider):
    """Wraps a StorageProvider and routes all async calls through AsyncioBridge.

    Needed because Telethon (asyncio) cannot be called directly from trio context.
    """

    def __init__(self, provider: StorageProvider, bridge: AsyncioBridge) -> None:
        self._provider = provider
        self._bridge = bridge
        super().__init__(config=provider.config)

    async def init(self, **kwargs):  # type: ignore[override]
        await self._bridge.run(self._provider.init(**kwargs))

    async def create_chunk(self, data: bytes) -> str:
        return await self._bridge.run(self._provider.create_chunk(data))

    async def get_chunk(self, external_id: str) -> bytes:
        return await self._bridge.run(self._provider.get_chunk(external_id))

    async def delete_chunk(self, external_id: str) -> None:
        await self._bridge.run(self._provider.delete_chunk(external_id))

    async def is_healthy(self) -> bool:
        return await self._bridge.run(self._provider.is_healthy())

    async def close(self) -> None:
        try:
            await self._bridge.run(self._provider.close())
        except Exception:
            pass  # Provider may not be connected


class BridgedMetadataRepository(MetadataRepository):
    def __init__(
        self,
        repo: SqlAlchemyMetadataRepository,
        bridge: AsyncioBridge,
    ) -> None:
        self._repo = repo
        self._bridge = bridge

    async def create_node(
        self,
        parent_id: int | None,
        name: str,
        type: str,
        chunk_size: int | None = None,
    ) -> Node:
        return await self._bridge.run(self._repo.create_node(parent_id, name, type, chunk_size))

    async def get_node(self, node_id: int) -> Node:
        return await self._bridge.run(self._repo.get_node(node_id))

    async def get_root_node(self) -> Node | None:
        return await self._bridge.run(self._repo.get_root_node())

    async def list_children(self, parent_id: int) -> list[Node]:
        return await self._bridge.run(self._repo.list_children(parent_id))

    async def delete_node(self, node_id: int) -> None:
        return await self._bridge.run(self._repo.delete_node(node_id))

    async def update_node(
        self,
        node_id: int,
        name: str | None = None,
        parent_id: int | None = None,
    ) -> None:
        return await self._bridge.run(self._repo.update_node(node_id, name, parent_id))

    async def update_node_size(self, node_id: int, size: int) -> None:
        return await self._bridge.run(self._repo.update_node_size(node_id, size))

    async def get_message_id(self, chunk_id: ChunkId) -> int:
        return await self._bridge.run(self._repo.get_message_id(chunk_id))

    async def add_chunk(
        self,
        node_id: int,
        chunk_index: int,
        offset: int,
        chunk_id: uuid.UUID,
    ) -> None:
        return await self._bridge.run(self._repo.add_chunk(node_id, chunk_index, offset, chunk_id))

    async def get_chunks(self, node_id: int) -> list[FileChunk]:
        return await self._bridge.run(self._repo.get_chunks(node_id))

    async def update_chunk(self, file_chunk_id: int, new_chunk_id: uuid.UUID) -> None:
        return await self._bridge.run(self._repo.update_chunk(file_chunk_id, new_chunk_id))

    async def get_provider_name_for_chunk(self, chunk_id: uuid.UUID) -> str:
        return await self._bridge.run(self._repo.get_provider_name_for_chunk(chunk_id))

    async def get_orphaned_chunks(self, force: bool = False) -> list[Chunk]:
        return await self._bridge.run(self._repo.get_orphaned_chunks(force))

    async def get_or_create_storage_provider(
        self,
        name: str,
        type_: str,
        description: str = "",
        config: dict | None = None,
    ) -> StorageProviderModel:
        return await self._bridge.run(
            self._repo.get_or_create_storage_provider(name, type_, description, config)
        )

    async def save_chunk_with_external_id(
        self,
        chunk_id: uuid.UUID,
        size: int,
        sha256: bytes | None,
        external_id: str,
        storage_provider_id: int,
        nonce: bytes | None = None,
        auth_tag: bytes | None = None,
    ) -> Chunk:
        return await self._bridge.run(
            self._repo.save_chunk_with_external_id(
                chunk_id, size, sha256, external_id, storage_provider_id, nonce, auth_tag
            )
        )

    async def update_chunk_external_id(
        self,
        chunk_id: uuid.UUID,
        external_id: str,
    ) -> None:
        return await self._bridge.run(self._repo.update_chunk_external_id(chunk_id, external_id))

    async def get_chunk_by_external_id(
        self,
        external_id: str,
    ) -> Chunk | None:
        return await self._bridge.run(self._repo.get_chunk_by_external_id(external_id))

    async def get_chunk_by_id(self, chunk_id: uuid.UUID) -> Chunk | None:
        return await self._bridge.run(self._repo.get_chunk_by_id(chunk_id))

    async def hard_delete_chunk(self, chunk_id: uuid.UUID) -> None:
        return await self._bridge.run(self._repo.hard_delete_chunk(chunk_id))

    async def commit(self) -> None:
        return await self._bridge.run(self._repo.commit())

    async def flush(self) -> None:
        return await self._bridge.run(self._repo.flush())

    async def rollback(self) -> None:
        return await self._bridge.run(self._repo.rollback())


class BridgedKeyManager(KeyManager):
    def __init__(self, key_manager: DatabaseKeyManager, bridge: AsyncioBridge) -> None:
        self._key_manager = key_manager
        self._bridge = bridge

    async def get_key(self, node_id: int) -> bytes:
        return await self._bridge.run(self._key_manager.get_key(node_id))

    async def create_key(self, node_id: int) -> bytes:
        return await self._bridge.run(self._key_manager.create_key(node_id))

    async def get_or_create_key(self, node_id: int) -> bytes:
        return await self._bridge.run(self._key_manager.get_or_create_key(node_id))
