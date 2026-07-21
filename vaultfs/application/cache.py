from typing import Protocol

from vaultfs.storage.interface import ChunkId


class CacheLayer(Protocol):
    async def get(self, key: ChunkId) -> bytes | None: ...

    async def set(self, key: ChunkId, value: bytes) -> None: ...

    async def clear(self) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._data: dict[ChunkId, bytes] = {}

    async def get(self, key: ChunkId) -> bytes | None:
        return self._data.get(key)

    async def set(self, key: ChunkId, value: bytes) -> None:
        self._data[key] = value

    async def clear(self) -> None:
        self._data.clear()
