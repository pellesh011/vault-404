from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from vaultfs.application.cache_layer import LRUCache, MultiLevelCache, SSDDirectoryCache
from vaultfs.storage.interface import ChunkId
from vaultfs.storage.provider_factory import StorageProviderRegistry


@pytest.fixture
def chunk_id() -> ChunkId:
    return ChunkId("test-chunk")


class TestLRUCache:
    @pytest.fixture
    def cache(self) -> LRUCache:
        return LRUCache(max_size=100)

    async def test_set_and_get(self, cache: LRUCache) -> None:
        await cache.set("key1", b"data")
        assert await cache.get("key1") == b"data"

    async def test_get_missing_returns_none(self, cache: LRUCache) -> None:
        assert await cache.get("missing") is None

    async def test_eviction_when_full(self, cache: LRUCache) -> None:
        await cache.set("key1", b"x" * 60)
        await cache.set("key2", b"x" * 60)
        assert await cache.get("key1") is None
        assert await cache.get("key2") == b"x" * 60

    async def test_lru_promotion(self, cache: LRUCache) -> None:
        await cache.set("key1", b"x" * 60)
        await cache.set("key2", b"y" * 30)
        await cache.get("key1")
        await cache.set("key3", b"z" * 40)
        assert await cache.get("key1") == b"x" * 60
        assert await cache.get("key2") is None

    async def test_invalidate_removes_key(self, cache: LRUCache) -> None:
        await cache.set("key1", b"data")
        await cache.invalidate("key1")
        assert await cache.get("key1") is None

    async def test_invalidate_releases_size(self, cache: LRUCache) -> None:
        await cache.set("key1", b"x" * 60)
        await cache.invalidate("key1")
        await cache.set("key2", b"y" * 60)
        assert await cache.get("key2") == b"y" * 60

    async def test_clear_removes_all(self, cache: LRUCache) -> None:
        await cache.set("key1", b"data1")
        await cache.set("key2", b"data2")
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    async def test_empty_data(self, cache: LRUCache) -> None:
        await cache.set("key1", b"")
        assert await cache.get("key1") == b""

    async def test_zero_max_size(self) -> None:
        cache = LRUCache(max_size=0)
        await cache.set("key1", b"data")
        assert await cache.get("key1") is None


class TestSSDDirectoryCache:
    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "cache"

    @pytest.fixture
    def cache(self, cache_dir: Path) -> SSDDirectoryCache:
        return SSDDirectoryCache(path=cache_dir, max_size=200)

    async def test_set_and_get(self, cache: SSDDirectoryCache) -> None:
        await cache.set("key1", b"data")
        result = await cache.get("key1")
        assert result == b"data"

    async def test_get_missing_returns_none(self, cache: SSDDirectoryCache) -> None:
        assert await cache.get("missing") is None

    async def test_data_persists_on_disk(self, cache: SSDDirectoryCache, cache_dir: Path) -> None:
        await cache.set("key1", b"persistent")
        file_path = cache_dir / "key1"
        assert file_path.exists()
        assert file_path.read_bytes() == b"persistent"

    async def test_eviction_when_full(self, cache: SSDDirectoryCache) -> None:
        await cache.set("key1", b"x" * 150)
        await cache.set("key2", b"y" * 150)
        assert await cache.get("key1") is None
        assert await cache.get("key2") == b"y" * 150

    async def test_invalidate_removes_key(self, cache: SSDDirectoryCache) -> None:
        await cache.set("key1", b"data")
        await cache.invalidate("key1")
        assert await cache.get("key1") is None

    async def test_invalidate_deletes_file(self, cache: SSDDirectoryCache, cache_dir: Path) -> None:
        await cache.set("key1", b"data")
        await cache.invalidate("key1")
        assert not (cache_dir / "key1").exists()

    async def test_clear_removes_all(self, cache: SSDDirectoryCache, cache_dir: Path) -> None:
        await cache.set("key1", b"data1")
        await cache.set("key2", b"data2")
        await cache.clear()
        assert not cache_dir.exists()

    async def test_create_dir_if_not_exists(self, cache_dir: Path) -> None:
        cache = SSDDirectoryCache(path=cache_dir)
        await cache.set("key1", b"data")
        assert cache_dir.exists()

    async def test_empty_data(self, cache: SSDDirectoryCache) -> None:
        await cache.set("key1", b"")
        assert await cache.get("key1") == b""

    async def test_unlimited_cache(self, cache_dir: Path) -> None:
        cache = SSDDirectoryCache(path=cache_dir)
        for i in range(100):
            await cache.set(f"key{i}", b"x" * 1000)
        assert await cache.get("key0") == b"x" * 1000


class TestMultiLevelCache:
    @pytest.fixture
    def storage(self) -> AsyncMock:
        mock = AsyncMock()

        async def get_chunk(chunk_id: ChunkId) -> bytes:
            if chunk_id == "chunk-in-storage":
                return b"from-storage"
            if chunk_id == "chunk-error":
                raise KeyError("not found")
            raise KeyError("not found")

        mock.get_chunk = AsyncMock(side_effect=get_chunk)
        return mock

    @pytest.fixture
    def metadata(self) -> AsyncMock:
        mock = AsyncMock()

        async def get_provider_name_for_chunk(chunk_id: str) -> str:
            return "test-provider"

        mock.get_provider_name_for_chunk = AsyncMock(side_effect=get_provider_name_for_chunk)
        return mock

    @pytest.fixture
    def registry(self, storage: AsyncMock) -> StorageProviderRegistry:
        r = StorageProviderRegistry()
        r._providers["test-provider"] = storage
        return r

    @pytest.fixture
    def cache(
        self,
        registry: StorageProviderRegistry,
        metadata: AsyncMock,
    ) -> MultiLevelCache:
        return MultiLevelCache(
            registry=registry,
            metadata=metadata,
            l1_max_size=100,
            l2_path="/tmp/test-cache",
            l2_max_size=200,
        )

    async def test_hit_l1_returns_data(self, cache: MultiLevelCache) -> None:
        await cache.l1.set("chunk-1", b"l1-data")
        result = await cache.get_chunk("chunk-1")
        assert result == b"l1-data"

    async def test_hit_l2_returns_data_and_promotes(self, cache: MultiLevelCache) -> None:
        await cache.l2.set("chunk-1", b"l2-data")
        result = await cache.get_chunk("chunk-1")
        assert result == b"l2-data"
        assert await cache.l1.get("chunk-1") == b"l2-data"

    async def test_miss_loads_from_storage(self, cache: MultiLevelCache) -> None:
        result = await cache.get_chunk("chunk-in-storage")
        assert result == b"from-storage"

    async def test_miss_caches_in_l2_and_l1(self, cache: MultiLevelCache) -> None:
        await cache.get_chunk("chunk-in-storage")
        assert await cache.l2.get("chunk-in-storage") == b"from-storage"
        assert await cache.l1.get("chunk-in-storage") == b"from-storage"

    async def test_invalidate_removes_from_both(self, cache: MultiLevelCache) -> None:
        await cache.l1.set("chunk-1", b"data")
        await cache.l2.set("chunk-1", b"data")
        await cache.invalidate("chunk-1")
        assert await cache.l1.get("chunk-1") is None
        assert await cache.l2.get("chunk-1") is None

    async def test_get_nonexistent_raises(self, cache: MultiLevelCache) -> None:
        with pytest.raises(KeyError):
            await cache.get_chunk("nonexistent")

    async def test_l1_eviction_promotes_from_l2(self, cache: MultiLevelCache) -> None:
        await cache.l2.set("chunk-l2", b"from-l2")
        await cache.l1.set("fill", b"x" * 90)
        result = await cache.get_chunk("chunk-l2")
        assert result == b"from-l2"
        assert await cache.l1.get("chunk-l2") == b"from-l2"
