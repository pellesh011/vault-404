from datetime import UTC, datetime

from vaultfs.application.cache import CacheLayer
from vaultfs.infrastructure.database.repository import FileChunk, MetadataRepository
from vaultfs.storage.interface import ChunkId
from vaultfs.storage.provider import StorageProvider
from vaultfs.storage.provider_factory import StorageProviderRegistry


class ChunkManager:
    def __init__(
        self,
        registry: StorageProviderRegistry,
        metadata: MetadataRepository,
        cache: CacheLayer,
        default_provider: str = "memory",
    ) -> None:
        self._registry = registry
        self._metadata = metadata
        self._cache = cache
        self._default_provider = default_provider

    async def _resolve_provider(self, chunk_id: str) -> StorageProvider:
        name = await self._metadata.get_provider_name_for_chunk(chunk_id)
        return self._registry.get(name)

    async def read(self, node_id: int, offset: int, size: int) -> bytes:
        node = await self._metadata.get_node(node_id)
        if node.chunk_size is None:
            raise ValueError(f"Node {node_id} has no chunk_size configured")

        chunks = await self._metadata.get_chunks(node_id)
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
                break

            data = await self._load_chunk(file_chunk.chunk_id)
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
            new_chunk_id = await provider.create_chunk(merged)
            await self._cache.set(new_chunk_id, merged)

            if existing is not None:
                new_offset = (
                    existing.offset if chunk_offset == 0 else existing.offset + chunk_offset
                )
                await self._metadata.update_chunk(existing.id, new_chunk_id)
            else:
                new_offset = chunk_index * node.chunk_size
                await self._metadata.add_chunk(
                    node_id=node_id,
                    chunk_index=chunk_index,
                    offset=new_offset,
                    chunk_id=new_chunk_id,
                )

            chunks_by_index[chunk_index] = FileChunk(
                id=existing.id if existing else 0,
                node_id=node_id,
                chunk_index=chunk_index,
                offset=new_offset,
                chunk_id=new_chunk_id,
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
                    data = await provider.get_chunk(chunk_id)
                    await self._cache.set(chunk_id, data)

    def _find_chunk(self, chunks: list[FileChunk], index: int) -> FileChunk | None:
        for c in chunks:
            if c.chunk_index == index:
                return c
        return None

    async def _load_chunk(self, chunk_id: str) -> bytes:
        key = ChunkId(chunk_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached
        provider = await self._resolve_provider(chunk_id)
        data = await provider.get_chunk(key)
        await self._cache.set(key, data)
        return data
