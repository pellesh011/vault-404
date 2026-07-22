import asyncio
import hashlib
from datetime import UTC, datetime
from typing import cast

from telethon import TelegramClient
from telethon.tl.custom import Message
from telethon.tl.types import Channel

from vaultfs.storage.interface import ChunkId, ChunkInfo
from vaultfs.storage.provider import ProviderConfig, StorageProvider


class TelegramStorageProvider(StorageProvider):
    NAME = "telegram"

    def __init__(
        self,
        config: ProviderConfig,
        client: TelegramClient,
        channel: Channel,
        max_concurrent: int = 10,
    ) -> None:
        super().__init__(config)
        self._client = client
        self._channel = channel
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._store: dict[ChunkId, ChunkInfo] = {}

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.NAME

    async def create_chunk(self, data: bytes) -> ChunkId:
        chunk_id = ChunkId(hashlib.sha256(data).hexdigest())
        async with self._semaphore:
            uploaded = await self._client.upload_file(data, file_name=f"chunk_{chunk_id}")
            message = await self._client.send_file(self._channel, uploaded)
            message = cast(Message, message)
        info = ChunkInfo(
            size=len(data),
            sha256=hashlib.sha256(data).digest(),
            created_at=datetime.now(UTC),
        )
        self._store[chunk_id] = info
        return chunk_id

    async def get_chunk(self, chunk_id: ChunkId) -> bytes:
        async with self._semaphore:
            message = await self._client.get_messages(self._channel, ids=chunk_id)
            message = cast(Message | None, message)
            if message is None:
                raise KeyError(f"Chunk {chunk_id} not found in channel")
            data = await message.download_media(file=bytes)  # type: ignore[arg-type]
        if data is None:
            raise KeyError(f"Chunk {chunk_id} data not found")
        return data if isinstance(data, bytes) else data.encode()

    async def delete_chunk(self, chunk_id: ChunkId) -> None:
        self._store.pop(chunk_id, None)

    async def stat(self, chunk_id: ChunkId) -> ChunkInfo:
        info = self._store.get(chunk_id)
        if info is None:
            raise KeyError(f"Chunk {chunk_id} not found")
        return info

    async def is_healthy(self) -> bool:
        try:
            await self._client.get_me()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        self._store.clear()
