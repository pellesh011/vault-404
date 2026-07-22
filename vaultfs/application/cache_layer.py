from __future__ import annotations

import os
import shutil
from collections import OrderedDict
from pathlib import Path

from vaultfs.infrastructure.database.repository import MetadataRepository
from vaultfs.storage.interface import ChunkId
from vaultfs.storage.provider import StorageProvider
from vaultfs.storage.provider_factory import StorageProviderRegistry


class LRUCache:
    def __init__(self, max_size: int) -> None:
        self._max_size = max_size
        self._data: OrderedDict[str, bytes] = OrderedDict()
        self._current_size = 0

    async def get(self, key: str) -> bytes | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    async def set(self, key: str, value: bytes) -> None:
        if self._max_size == 0:
            return
        if key in self._data:
            self._current_size -= len(self._data[key])
            del self._data[key]
        while self._current_size + len(value) > self._max_size and self._data:
            oldest, old_val = self._data.popitem(last=False)
            self._current_size -= len(old_val)
        self._data[key] = value
        self._current_size += len(value)
        self._data.move_to_end(key)

    async def invalidate(self, key: str) -> None:
        if key in self._data:
            self._current_size -= len(self._data[key])
            del self._data[key]

    async def clear(self) -> None:
        self._data.clear()
        self._current_size = 0


class SSDDirectoryCache:
    def __init__(self, path: str | Path, max_size: int = 0) -> None:
        self._path = Path(path)
        self._max_size = max_size

    async def get(self, key: str) -> bytes | None:
        file_path = self._path / key
        if not file_path.exists():
            return None
        return file_path.read_bytes()

    async def set(self, key: str, value: bytes) -> None:
        self._path.mkdir(parents=True, exist_ok=True)
        if self._max_size > 0:
            await self._evict_if_needed(len(value))
        file_path = self._path / key
        file_path.write_bytes(value)

    async def invalidate(self, key: str) -> None:
        file_path = self._path / key
        if file_path.exists():
            file_path.unlink()

    async def clear(self) -> None:
        if self._path.exists():
            shutil.rmtree(self._path)

    async def _evict_if_needed(self, needed_space: int) -> None:
        files = sorted(self._path.iterdir(), key=lambda f: f.stat().st_atime)
        total = sum(os.path.getsize(f) for f in self._path.iterdir())
        while total + needed_space > self._max_size and files:
            f = files.pop(0)
            total -= os.path.getsize(f)
            f.unlink()


class MultiLevelCache:
    def __init__(
        self,
        registry: StorageProviderRegistry,
        metadata: MetadataRepository,
        l1_max_size: int,
        l2_path: str | Path,
        l2_max_size: int = 0,
    ) -> None:
        self._registry = registry
        self._metadata = metadata
        self.l1 = LRUCache(max_size=l1_max_size)
        self.l2 = SSDDirectoryCache(path=l2_path, max_size=l2_max_size)

    async def _resolve_provider(self, chunk_id: str) -> StorageProvider:
        name = await self._metadata.get_provider_name_for_chunk(chunk_id)
        return self._registry.get(name)

    async def get_chunk(self, chunk_id: str) -> bytes:
        cached = await self.l1.get(chunk_id)
        if cached is not None:
            return cached

        cached = await self.l2.get(chunk_id)
        if cached is not None:
            await self.l1.set(chunk_id, cached)
            return cached

        provider = await self._resolve_provider(chunk_id)
        data = await provider.get_chunk(ChunkId(chunk_id))
        await self.l2.set(chunk_id, data)
        await self.l1.set(chunk_id, data)
        return data

    async def invalidate(self, chunk_id: str) -> None:
        await self.l1.invalidate(chunk_id)
        await self.l2.invalidate(chunk_id)
