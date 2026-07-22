import hashlib
import uuid
from datetime import UTC, datetime

from vaultfs.storage.interface import ChunkInfo
from vaultfs.storage.provider import ProviderConfig, StorageProvider


class MemoryStorageProvider(StorageProvider):
    NAME = "memory"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._data: dict[str, bytes] = {}
        self._info: dict[str, ChunkInfo] = {}

    async def init(self, **kwargs: object) -> None:
        """Нет дополнительной инициализации для in-memory провайдера."""

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.NAME

    async def create_chunk(self, data: bytes) -> str:
        external_id = str(uuid.uuid4())
        self._data[external_id] = data
        self._info[external_id] = ChunkInfo(
            size=len(data),
            sha256=hashlib.sha256(data).digest(),
            created_at=datetime.now(UTC),
            storage_provider_id="memory",
        )
        return external_id

    async def get_chunk(self, external_id: str) -> bytes:
        if external_id not in self._data:
            raise KeyError(f"Chunk {external_id} not found")
        return self._data[external_id]

    async def delete_chunk(self, external_id: str) -> None:
        self._data.pop(external_id, None)
        self._info.pop(external_id, None)

    async def is_healthy(self) -> bool:
        return True

    async def close(self) -> None:
        self._data.clear()
        self._info.clear()
