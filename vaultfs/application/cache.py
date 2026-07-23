from abc import ABC, abstractmethod

from vaultfs.storage.interface import ChunkId


class CacheLayer(ABC):
    @abstractmethod
    async def get(self, key: ChunkId) -> bytes | None: ...

    @abstractmethod
    async def set(self, key: ChunkId, value: bytes) -> None: ...

    @abstractmethod
    async def delete(self, key: ChunkId) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...


class InMemoryCache(CacheLayer):
    def __init__(self) -> None:
        self._data: dict[ChunkId, bytes] = {}

    async def get(self, key: ChunkId) -> bytes | None:
        return self._data.get(key)

    async def set(self, key: ChunkId, value: bytes) -> None:
        self._data[key] = value

    async def delete(self, key: ChunkId) -> None:
        self._data.pop(key, None)

    async def clear(self) -> None:
        self._data.clear()
