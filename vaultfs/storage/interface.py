from dataclasses import dataclass
from datetime import datetime
from typing import NewType, Protocol, runtime_checkable

ChunkId = NewType("ChunkId", str)


@dataclass(frozen=True)
class ChunkInfo:
    size: int
    sha256: bytes
    created_at: datetime


@runtime_checkable
class ChunkStorage(Protocol):
    async def create_chunk(self, data: bytes) -> ChunkId: ...

    async def get_chunk(self, chunk_id: ChunkId) -> bytes: ...

    async def delete_chunk(self, chunk_id: ChunkId) -> None: ...

    async def stat(self, chunk_id: ChunkId) -> ChunkInfo: ...
