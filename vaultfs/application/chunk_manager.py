import hashlib
import logging
import uuid
from datetime import UTC, datetime

from vaultfs.application.cache import CacheLayer
from vaultfs.infrastructure.database.repository import FileChunk, MetadataRepository
from vaultfs.storage.interface import ChunkId
from vaultfs.storage.provider import StorageProvider
from vaultfs.storage.provider_factory import StorageProviderRegistry

logger = logging.getLogger(__name__)


class ChunkManager:
    def __init__(
        self,
        registry: StorageProviderRegistry,
        metadata: MetadataRepository,
        cache: CacheLayer,
        default_provider: str = "telegram",
    ) -> None:
        self._registry = registry
        self._metadata = metadata
        self._cache = cache
        self._default_provider = default_provider

    async def _resolve_provider(self, chunk_id: uuid.UUID) -> StorageProvider:
        logger.debug("_resolve_provider: chunk_id=%s", chunk_id)
        name = await self._metadata.get_provider_name_for_chunk(chunk_id)
        logger.debug("_resolve_provider: provider name=%s", name)
        return self._registry.get(name)

    async def read(self, node_id: int, offset: int, size: int) -> bytes:
        logger.debug("ChunkManager.read: node_id=%d, offset=%d, size=%d", node_id, offset, size)
        node = await self._metadata.get_node(node_id)
        logger.debug("ChunkManager.read: got node %s, chunk_size=%s", node.id, node.chunk_size)
        if node.chunk_size is None:
            raise ValueError(f"Node {node_id} has no chunk_size configured")

        chunks = await self._metadata.get_chunks(node_id)
        logger.debug("ChunkManager.read: got %d chunks", len(chunks))
        if not chunks:
            raise ValueError(f"Node {node_id} has no chunks")

        result = bytearray()
        current_offset = offset
        remaining = size

        while remaining > 0:
            chunk_index = current_offset // node.chunk_size
            chunk_offset = current_offset % node.chunk_size

            file_chunk = self._find_chunk(chunks, chunk_index)
            if file_chunk is None:
                logger.debug("ChunkManager.read: chunk_index %d not found", chunk_index)
                break

            logger.debug("ChunkManager.read: loading chunk %s", file_chunk.chunk_id)
            data = await self._load_chunk(file_chunk.chunk_id)
            logger.debug("ChunkManager.read: loaded chunk, %d bytes", len(data))
            bytes_to_read = min(remaining, len(data) - chunk_offset)
            result.extend(data[chunk_offset : chunk_offset + bytes_to_read])

            current_offset += bytes_to_read
            remaining -= bytes_to_read

        return bytes(result)

    async def write(self, node_id: int, offset: int, data: bytes) -> None:
        node = await self._metadata.get_node(node_id)
        if node.chunk_size is None:
            raise ValueError(f"Node {node_id} has no chunk_size configured")

        chunks = await self._metadata.get_chunks(node_id)
        chunks_by_index = {c.chunk_index: c for c in chunks}

        data_offset = 0
        while data_offset < len(data):
            chunk_index = (offset + data_offset) // node.chunk_size
            chunk_offset = (offset + data_offset) % node.chunk_size

            existing = chunks_by_index.get(chunk_index)
            if existing is not None:
                existing_data = await self._load_chunk(existing.chunk_id)
            else:
                existing_data = b""

            write_size = min(
                len(data) - data_offset,
                node.chunk_size - chunk_offset,
            )

            merged = (
                existing_data[:chunk_offset]
                + data[data_offset : data_offset + write_size]
                + existing_data[chunk_offset + write_size :]
            )

            provider = self._registry.get(self._default_provider)
            chunk_id = ChunkId(uuid.uuid4())
            external_id = await provider.create_chunk(merged)
            await self._cache.set(chunk_id, merged)

            chunk_sha256 = hashlib.sha256(merged).digest()
            provider_model = await self._metadata.get_or_create_storage_provider(
                name=provider.name,
                type_=provider.provider_type,
            )
            await self._metadata.save_chunk_with_external_id(
                chunk_id=chunk_id,
                size=len(merged),
                sha256=chunk_sha256,
                external_id=external_id,
                storage_provider_id=provider_model.id,
            )

            if existing is not None:
                new_offset = (
                    existing.offset if chunk_offset == 0 else existing.offset + chunk_offset
                )
                await self._cache.delete(ChunkId(existing.chunk_id))
                await self._metadata.update_chunk(existing.id, chunk_id)
            else:
                new_offset = chunk_index * node.chunk_size
                await self._metadata.add_chunk(
                    node_id=node_id,
                    chunk_index=chunk_index,
                    offset=new_offset,
                    chunk_id=chunk_id,
                )

            chunks_by_index[chunk_index] = FileChunk(
                id=existing.id if existing else 0,
                node_id=node_id,
                chunk_index=chunk_index,
                offset=new_offset,
                chunk_id=chunk_id,
            )

            data_offset += write_size

        new_size = max(node.size, offset + len(data))
        node.size = new_size
        node.modified_at = datetime.now(UTC)

    async def prefetch(self, node_id: int, start_chunk: int, count: int) -> None:
        chunks = await self._metadata.get_chunks(node_id)
        target_indices = set(range(start_chunk, start_chunk + count))

        for fc in chunks:
            if fc.chunk_index in target_indices:
                chunk_id = ChunkId(fc.chunk_id)
                cached = await self._cache.get(chunk_id)
                if cached is None:
                    provider = await self._resolve_provider(fc.chunk_id)
                    message_id = await self._metadata.get_message_id(chunk_id)
                    data = await provider.get_chunk(str(message_id))
                    await self._cache.set(chunk_id, data)

    def _find_chunk(self, chunks: list[FileChunk], index: int) -> FileChunk | None:
        for c in chunks:
            if c.chunk_index == index:
                return c
        return None

    async def _load_chunk(self, chunk_id: uuid.UUID) -> bytes:
        logger.debug("_load_chunk: chunk_id=%s", chunk_id)
        key = ChunkId(chunk_id)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("_load_chunk: cache hit")
            return cached
        logger.debug("_load_chunk: cache miss, resolving provider")
        provider = await self._resolve_provider(chunk_id)
        try:
            message_id = await self._metadata.get_message_id(ChunkId(chunk_id))
            data = await provider.get_chunk(str(message_id))
            logger.debug("_load_chunk: got %d bytes from provider", len(data))
            await self._cache.set(key, data)
            return data
        except Exception as e:
            logger.exception("_load_chunk: failed to get chunk from provider: %s", e)
            raise
