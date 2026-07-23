from abc import ABC, abstractmethod

from vaultfs.storage.interface import ChunkId, ChunkInfo


class MetadataRepository(ABC):
    @abstractmethod
    async def save(self, chunk_id: ChunkId, message_id: int, info: ChunkInfo) -> None: ...

    @abstractmethod
    async def get_message_id(self, chunk_id: ChunkId) -> int: ...

    @abstractmethod
    async def get_info(self, chunk_id: ChunkId) -> ChunkInfo: ...

    @abstractmethod
    async def mark_deleted(self, chunk_id: ChunkId) -> None: ...
