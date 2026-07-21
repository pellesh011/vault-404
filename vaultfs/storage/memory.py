import hashlib
from datetime import UTC, datetime

from vaultfs.storage.interface import ChunkId, ChunkInfo


class InMemoryChunkStorage:
    def __init__(self) -> None:
        self._data: dict[ChunkId, bytes] = {}
        self._info: dict[ChunkId, ChunkInfo] = {}

    async def create_chunk(self, data: bytes) -> ChunkId:
        chunk_id = ChunkId(hashlib.sha256(data).hexdigest())
        if chunk_id not in self._data:
            self._data[chunk_id] = data
            self._info[chunk_id] = ChunkInfo(
                size=len(data),
                sha256=hashlib.sha256(data).digest(),
                created_at=datetime.now(UTC),
            )
        return chunk_id

    async def get_chunk(self, chunk_id: ChunkId) -> bytes:
        if chunk_id not in self._data:
            raise KeyError(f"Chunk {chunk_id} not found")
        return self._data[chunk_id]

    async def delete_chunk(self, chunk_id: ChunkId) -> None:
        self._data.pop(chunk_id, None)
        self._info.pop(chunk_id, None)

    async def stat(self, chunk_id: ChunkId) -> ChunkInfo:
        if chunk_id not in self._info:
            raise KeyError(f"Chunk {chunk_id} not found")
        return self._info[chunk_id]
