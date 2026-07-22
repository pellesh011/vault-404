import hashlib
from datetime import UTC, datetime

from vaultfs.storage.interface import ChunkCreateResult, ChunkId, ChunkInfo
from vaultfs.storage.provider import ProviderConfig, StorageProvider


class MemoryStorageProvider(StorageProvider):
    NAME = "memory"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._data: dict[ChunkId, bytes] = {}
        self._info: dict[ChunkId, ChunkInfo] = {}

    async def init(self, **kwargs: object) -> None:
        """Нет дополнительной инициализации для in-memory провайдера."""

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.NAME

    async def create_chunk(self, data: bytes) -> ChunkCreateResult:
        chunk_id = ChunkId(hashlib.sha256(data).hexdigest())
        if chunk_id not in self._data:
            self._data[chunk_id] = data
            self._info[chunk_id] = ChunkInfo(
                size=len(data),
                sha256=hashlib.sha256(data).digest(),
                created_at=datetime.now(UTC),
                storage_provider_id="memory",
            )
        return ChunkCreateResult(chunk_id=chunk_id, external_id=chunk_id)

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

    async def is_healthy(self) -> bool:
        return True

    async def close(self) -> None:
        self._data.clear()
        self._info.clear()
