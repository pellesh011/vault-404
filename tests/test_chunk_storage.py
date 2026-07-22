from datetime import datetime

import pytest

from vaultfs.storage.interface import ChunkCreateResult, ChunkStorage
from vaultfs.storage.memory import InMemoryChunkStorage


@pytest.fixture
def storage() -> InMemoryChunkStorage:
    return InMemoryChunkStorage()


class TestChunkStorageProtocol:
    async def test_create_chunk_returns_id(self, storage: InMemoryChunkStorage) -> None:
        result = await storage.create_chunk(b"hello world")
        assert isinstance(result, ChunkCreateResult)
        chunk_id = result.chunk_id
        assert isinstance(chunk_id, str)
        assert len(chunk_id) > 0

    async def test_get_chunk_returns_same_data(self, storage: InMemoryChunkStorage) -> None:
        data = b"hello world"
        result = await storage.create_chunk(data)
        chunk_id = result.chunk_id
        retrieved = await storage.get_chunk(chunk_id)
        assert retrieved == data

    async def test_delete_chunk_removes_access(self, storage: InMemoryChunkStorage) -> None:
        result = await storage.create_chunk(b"data")
        chunk_id = result.chunk_id
        await storage.delete_chunk(chunk_id)
        with pytest.raises(KeyError):
            await storage.get_chunk(chunk_id)

    async def test_stat_returns_correct_size(self, storage: InMemoryChunkStorage) -> None:
        data = b"hello world"
        result = await storage.create_chunk(data)
        chunk_id = result.chunk_id
        info = await storage.stat(chunk_id)
        assert info.size == len(data)

    async def test_stat_returns_correct_sha256(self, storage: InMemoryChunkStorage) -> None:
        data = b"hello world"
        result = await storage.create_chunk(data)
        chunk_id = result.chunk_id
        info = await storage.stat(chunk_id)
        import hashlib

        expected = hashlib.sha256(data).digest()
        assert info.sha256 == expected

    async def test_stat_returns_valid_created_at(self, storage: InMemoryChunkStorage) -> None:
        data = b"test"
        result = await storage.create_chunk(data)
        chunk_id = result.chunk_id
        info = await storage.stat(chunk_id)
        assert isinstance(info.created_at, datetime)
        assert info.created_at.tzinfo is not None

    async def test_create_chunk_with_empty_data(self, storage: InMemoryChunkStorage) -> None:
        result = await storage.create_chunk(b"")
        chunk_id = result.chunk_id
        retrieved = await storage.get_chunk(chunk_id)
        assert retrieved == b""

    async def test_create_chunk_with_large_data(self, storage: InMemoryChunkStorage) -> None:
        data = b"x" * (10 * 1024 * 1024)
        result = await storage.create_chunk(data)
        chunk_id = result.chunk_id
        retrieved = await storage.get_chunk(chunk_id)
        assert retrieved == data
        assert len(retrieved) == len(data)

    async def test_stat_after_delete_raises(self, storage: InMemoryChunkStorage) -> None:
        result = await storage.create_chunk(b"data")
        chunk_id = result.chunk_id
        await storage.delete_chunk(chunk_id)
        with pytest.raises(KeyError):
            await storage.stat(chunk_id)

    async def test_duplicate_content_returns_same_id(self, storage: InMemoryChunkStorage) -> None:
        data = b"deduplicated content"
        result1 = await storage.create_chunk(data)
        id1 = result1.chunk_id
        result2 = await storage.create_chunk(data)
        id2 = result2.chunk_id
        assert id1 == id2

    async def test_chunk_storage_is_protocol(self) -> None:
        assert isinstance(InMemoryChunkStorage(), ChunkStorage)
