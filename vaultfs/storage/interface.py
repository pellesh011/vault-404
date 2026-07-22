from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import NewType

ChunkId = NewType("ChunkId", str)


@dataclass(frozen=True)
class ChunkInfo:
    size: int
    sha256: bytes
    created_at: datetime
    storage_provider_id: str


@dataclass(frozen=True)
class ChunkCreateResult:
    chunk_id: ChunkId
    external_id: str


@dataclass(frozen=True)
class ProviderStorageChunkCreateResult:
    external_id: str


class ChunkStorage(ABC):
    @abstractmethod
    async def create_chunk(self, data: bytes) -> ChunkCreateResult: ...

    @abstractmethod
    async def get_chunk(self, chunk_id: ChunkId) -> bytes: ...

    @abstractmethod
    async def delete_chunk(self, chunk_id: ChunkId) -> None: ...

    @abstractmethod
    async def stat(self, chunk_id: ChunkId) -> ChunkInfo: ...
