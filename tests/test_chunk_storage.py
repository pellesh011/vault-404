from datetime import datetime

import pytest

from vaultfs.storage.interface import ChunkStorage
from vaultfs.storage.memory import InMemoryChunkStorage


@pytest.fixture
def storage() -> InMemoryChunkStorage:
    return InMemoryChunkStorage()


class TestChunkStorageProtocol:
    async def test_create_chunk_returns_id(self, storage: InMemoryChunkStorage) -> None:
        chunk_id = await storage.create_chunk(b"hello world")
        assert isinstance(chunk_id, str)
        assert len(chunk_id) > 0

    async def test_get_chunk_returns_same_data(self, storage: InMemoryChunkStorage) -> None:
        data = b"hello world"
        chunk_id = await storage.create_chunk(data)
        result = await storage.get_chunk(chunk_id)
        assert result == data

    async def test_delete_chunk_removes_access(self, storage: InMemoryChunkStorage) -> None:
        chunk_id = await storage.create_chunk(b"data")
        await storage.delete_chunk(chunk_id)
        with pytest.raises(KeyError):
            await storage.get_chunk(chunk_id)

    async def test_stat_returns_correct_size(self, storage: InMemoryChunkStorage) -> None:
        data = b"hello world"
        chunk_id = await storage.create_chunk(data)
        info = await storage.stat(chunk_id)
        assert info.size == len(data)

    async def test_stat_returns_correct_sha256(self, storage: InMemoryChunkStorage) -> None:
        data = b"hello world"
        chunk_id = await storage.create_chunk(data)
        info = await storage.stat(chunk_id)
        import hashlib

        expected = hashlib.sha256(data).digest()
        assert info.sha256 == expected

    async def test_stat_returns_valid_created_at(self, storage: InMemoryChunkStorage) -> None:
        data = b"test"
        chunk_id = await storage.create_chunk(data)
        info = await storage.stat(chunk_id)
        assert isinstance(info.created_at, datetime)
        assert info.created_at.tzinfo is not None

    async def test_create_chunk_with_empty_data(self, storage: InMemoryChunkStorage) -> None:
        chunk_id = await storage.create_chunk(b"")
        result = await storage.get_chunk(chunk_id)
        assert result == b""

    async def test_create_chunk_with_large_data(self, storage: InMemoryChunkStorage) -> None:
        data = b"x" * (10 * 1024 * 1024)
        chunk_id = await storage.create_chunk(data)
        result = await storage.get_chunk(chunk_id)
        assert result == data
        assert len(result) == len(data)

    async def test_stat_after_delete_raises(self, storage: InMemoryChunkStorage) -> None:
        chunk_id = await storage.create_chunk(b"data")
        await storage.delete_chunk(chunk_id)
        with pytest.raises(KeyError):
            await storage.stat(chunk_id)

    async def test_duplicate_content_returns_same_id(self, storage: InMemoryChunkStorage) -> None:
        data = b"deduplicated content"
        id1 = await storage.create_chunk(data)
        id2 = await storage.create_chunk(data)
        assert id1 == id2

    async def test_chunk_storage_is_protocol(self) -> None:
        assert isinstance(InMemoryChunkStorage(), ChunkStorage)
