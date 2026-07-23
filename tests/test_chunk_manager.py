import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from vaultfs.application.cache import CacheLayer, InMemoryCache
from vaultfs.application.chunk_manager import ChunkManager
from vaultfs.infrastructure.database.repository import FileChunk, Node
from vaultfs.infrastructure.database.repository import MetadataRepository as FileMetadataRepository
from vaultfs.storage.interface import ChunkId
from vaultfs.storage.memory_provider import MemoryStorageProvider
from vaultfs.storage.provider import ProviderConfig
from vaultfs.storage.provider_factory import StorageProviderRegistry

PROVIDER_NAME = "memory"

CHUNK_IDS = [
    uuid.UUID(int=1),
    uuid.UUID(int=2),
    uuid.UUID(int=3),
]


class _FakeMetadata:  # type: ignore[no-untyped-def]
    def __init__(self, node: Node, chunks: list[FileChunk]) -> None:
        self.node = node
        self._chunks = {c.chunk_index: c for c in chunks}
        self._next_id = len(chunks) + 1
        self._provider_map: dict[uuid.UUID, str] = {}
        self._message_ids: dict[uuid.UUID, str] = {}
        self.add_chunk = AsyncMock(side_effect=self._add_chunk_impl)
        self.update_chunk = AsyncMock(side_effect=self._update_chunk_impl)
        self.get_node = AsyncMock(return_value=node)
        self.get_root_node = AsyncMock(return_value=node)
        self.create_node = AsyncMock()
        self.list_children = AsyncMock(return_value=[])
        self.delete_node = AsyncMock()
        self.get_orphaned_chunks = AsyncMock(return_value=[])

    async def get_chunks(self, node_id: int) -> list[FileChunk]:
        return list(self._chunks.values())

    async def get_provider_name_for_chunk(self, chunk_id: uuid.UUID) -> str:
        return self._provider_map.get(chunk_id, PROVIDER_NAME)

    async def get_message_id(self, chunk_id: ChunkId) -> int:
        val = self._message_ids.get(chunk_id)
        if val is None:
            return 0
        return int(val)

    def set_provider(self, chunk_id: uuid.UUID, provider_name: str) -> None:
        self._provider_map[chunk_id] = provider_name

    def set_message_id(self, chunk_id: uuid.UUID, external_id: str) -> None:
        self._message_ids[chunk_id] = external_id

    async def _add_chunk_impl(
        self, node_id: int, chunk_index: int, offset: int, chunk_id: uuid.UUID
    ) -> None:
        fc = FileChunk(
            id=self._next_id,
            node_id=node_id,
            chunk_index=chunk_index,
            offset=offset,
            chunk_id=chunk_id,
        )
        self._next_id += 1
        self._chunks[chunk_index] = fc

    async def _update_chunk_impl(self, file_chunk_id: int, new_chunk_id: uuid.UUID) -> None:
        for fc in self._chunks.values():
            if fc.id == file_chunk_id:
                fc.chunk_id = new_chunk_id
                break

    async def get_or_create_storage_provider(
        self, name: str, type_: str, description: str = "", config: dict | None = None
    ) -> object:
        from dataclasses import dataclass

        @dataclass
        class FakeProviderModel:
            id: int
            name: str
            type: str

        return FakeProviderModel(id=1, name=name, type=type_)

    async def save_chunk_with_external_id(
        self,
        chunk_id: uuid.UUID,
        size: int,
        sha256: bytes | None,
        external_id: str,
        storage_provider_id: int,
        nonce: bytes | None = None,
        auth_tag: bytes | None = None,
    ) -> object:
        pass


@pytest.fixture
def chunk_size() -> int:
    return 10


@pytest.fixture
def node(chunk_size: int) -> Node:
    return Node(
        id=1,
        parent_id=None,
        name="test.bin",
        type="file",
        created_at=datetime.now(),
        modified_at=datetime.now(),
        size=30,
        chunk_size=chunk_size,
    )


@pytest.fixture
def chunks() -> list[FileChunk]:
    return [
        FileChunk(id=1, node_id=1, chunk_index=0, offset=0, chunk_id=CHUNK_IDS[0]),
        FileChunk(id=2, node_id=1, chunk_index=1, offset=10, chunk_id=CHUNK_IDS[1]),
        FileChunk(id=3, node_id=1, chunk_index=2, offset=20, chunk_id=CHUNK_IDS[2]),
    ]


@pytest.fixture
def chunk_data() -> dict[str, bytes]:
    return {}


@pytest.fixture
def provider() -> MemoryStorageProvider:
    return MemoryStorageProvider(config=ProviderConfig(name=PROVIDER_NAME, type="memory"))


@pytest.fixture
def registry(provider: MemoryStorageProvider) -> StorageProviderRegistry:
    r = StorageProviderRegistry()
    r.add(provider)
    return r


@pytest.fixture
def metadata(
    node: Node,
    chunks: list[FileChunk],
    provider: MemoryStorageProvider,
) -> _FakeMetadata:
    m = _FakeMetadata(node, chunks)
    for i, c in enumerate(chunks):
        m.set_provider(c.chunk_id, PROVIDER_NAME)
        m.set_message_id(c.chunk_id, str(i + 1))
    return m


@pytest.fixture
def cache() -> CacheLayer:
    return InMemoryCache()


@pytest.fixture
def manager(
    registry: StorageProviderRegistry,
    metadata: _FakeMetadata,
    cache: CacheLayer,
    chunk_data: dict[str, bytes],
    chunks: list[FileChunk],
    provider: MemoryStorageProvider,
) -> ChunkManager:
    chunk_data[str(CHUNK_IDS[0])] = b"AAAABBBBBB"
    chunk_data[str(CHUNK_IDS[1])] = b"CCCCCDDDDD"
    chunk_data[str(CHUNK_IDS[2])] = b"EEEEEFFFFF"

    for i, c in enumerate(chunks):
        data = chunk_data[str(c.chunk_id)]
        provider._data[str(i + 1)] = data

    mgr = ChunkManager(
        registry=registry, metadata=metadata, cache=cache, default_provider=PROVIDER_NAME
    )
    return mgr


class TestChunkManager:
    async def test_read_single_chunk(self, manager: ChunkManager) -> None:
        result = await manager.read(node_id=1, offset=0, size=5)
        assert result == b"AAAAB"

    async def test_read_partial_middle(self, manager: ChunkManager) -> None:
        result = await manager.read(node_id=1, offset=3, size=4)
        assert result == b"ABBB"

    async def test_read_spans_two_chunks(self, manager: ChunkManager, chunk_size: int) -> None:
        result = await manager.read(node_id=1, offset=7, size=6)
        assert result == b"BBBCCC"

    async def test_read_spans_three_chunks(self, manager: ChunkManager) -> None:
        result = await manager.read(node_id=1, offset=5, size=20)
        assert result == b"BBBBBCCCCCDDDDDEEEEE"

    async def test_read_full_file(self, manager: ChunkManager) -> None:
        result = await manager.read(node_id=1, offset=0, size=30)
        assert result == b"AAAABBBBBBCCCCCDDDDDEEEEEFFFFF"

    async def test_read_empty_result(self, manager: ChunkManager) -> None:
        result = await manager.read(node_id=1, offset=30, size=5)
        assert result == b""

    async def test_read_beyond_file(self, manager: ChunkManager) -> None:
        result = await manager.read(node_id=1, offset=25, size=10)
        assert result == b"FFFFF"

    async def test_write_updates_existing_chunk(
        self,
        manager: ChunkManager,
        metadata: FileMetadataRepository,
        chunks: list[FileChunk],
    ) -> None:
        await manager.write(node_id=1, offset=2, data=b"ZZZZ")

        metadata.update_chunk.assert_called_once()
        call_args = metadata.update_chunk.call_args
        assert call_args is not None
        assert call_args[0][0] == chunks[0].id

    async def test_write_read_cycle(self, manager: ChunkManager) -> None:
        await manager.write(node_id=1, offset=2, data=b"XYZ")

        result = await manager.read(node_id=1, offset=0, size=10)
        assert result == b"AAXYZBBBBB"

    async def test_write_spans_two_chunks(self, manager: ChunkManager) -> None:
        await manager.write(node_id=1, offset=8, data=b"XXXXYYYY")

        result = await manager.read(node_id=1, offset=0, size=20)
        assert result == b"AAAABBBBXXXXYYYYDDDD"

    async def test_prefetch_loads_chunks(
        self,
        manager: ChunkManager,
        cache: CacheLayer,
        chunks: list[FileChunk],
    ) -> None:
        await manager.prefetch(node_id=1, start_chunk=0, count=2)

        cached_0 = await cache.get(ChunkId(chunks[0].chunk_id))
        cached_1 = await cache.get(ChunkId(chunks[1].chunk_id))
        cached_2 = await cache.get(ChunkId(chunks[2].chunk_id))

        assert cached_0 == b"AAAABBBBBB"
        assert cached_1 == b"CCCCCDDDDD"
        assert cached_2 is None

    async def test_read_uses_cache(
        self,
        manager: ChunkManager,
        cache: CacheLayer,
        chunks: list[FileChunk],
    ) -> None:
        await manager.read(node_id=1, offset=0, size=5)

        cached_0 = await cache.get(ChunkId(chunks[0].chunk_id))
        assert cached_0 is not None

        await manager.read(node_id=1, offset=0, size=5)
        cached_0_again = await cache.get(ChunkId(chunks[0].chunk_id))
        assert cached_0_again == cached_0
