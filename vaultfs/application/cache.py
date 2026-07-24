import logging
from abc import ABC, abstractmethod

from vaultfs.storage.interface import ChunkId

logger = logging.getLogger(__name__)


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
        self._hits = 0
        self._misses = 0

    async def get(self, key: ChunkId) -> bytes | None:
        value = self._data.get(key)
        if value is None:
            self._misses += 1
        else:
            self._hits += 1
        logger.debug(
            "InMemoryCache.get: key=%s, hit=%s, total hits=%d, total misses=%d",
            key,
            value is not None,
            self._hits,
            self._misses,
        )
        return value

    async def set(self, key: ChunkId, value: bytes) -> None:
        self._data[key] = value

    async def delete(self, key: ChunkId) -> None:
        self._data.pop(key, None)

    async def clear(self) -> None:
        self._data.clear()
        self._hits = 0
        self._misses = 0
