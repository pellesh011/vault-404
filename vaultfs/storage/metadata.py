from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from vaultfs.storage.interface import ChunkId, ChunkInfo


@dataclass
class ChunkRecord:
    chunk_id: ChunkId
    message_id: int
    info: ChunkInfo
    deleted_at: datetime | None = None


class MetadataRepository(Protocol):
    async def save(self, chunk_id: ChunkId, message_id: int, info: ChunkInfo) -> None: ...

    async def get_message_id(self, chunk_id: ChunkId) -> int: ...

    async def get_info(self, chunk_id: ChunkId) -> ChunkInfo: ...

    async def mark_deleted(self, chunk_id: ChunkId) -> None: ...


class InMemoryMetadataRepository:
    def __init__(self) -> None:
        self._store: dict[ChunkId, ChunkRecord] = {}

    async def save(self, chunk_id: ChunkId, message_id: int, info: ChunkInfo) -> None:
        self._store[chunk_id] = ChunkRecord(
            chunk_id=chunk_id,
            message_id=message_id,
            info=info,
        )

    async def get_message_id(self, chunk_id: ChunkId) -> int:
        record = self._store.get(chunk_id)
        if record is None or record.deleted_at is not None:
            raise KeyError(f"Chunk {chunk_id} not found")
        return record.message_id

    async def get_info(self, chunk_id: ChunkId) -> ChunkInfo:
        record = self._store.get(chunk_id)
        if record is None or record.deleted_at is not None:
            raise KeyError(f"Chunk {chunk_id} not found")
        return record.info

    async def mark_deleted(self, chunk_id: ChunkId) -> None:
        record = self._store.get(chunk_id)
        if record is not None:
            record.deleted_at = datetime.now()
