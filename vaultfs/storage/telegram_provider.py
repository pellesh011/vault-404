import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any, cast

from telethon import TelegramClient
from telethon.tl.custom import Message
from telethon.tl.types import Channel

from vaultfs.storage.interface import ChunkId, ChunkInfo
from vaultfs.storage.metadata import MetadataRepository
from vaultfs.storage.provider import ProviderConfig, StorageProvider


class TelegramStorageProvider(StorageProvider):
    NAME = "telegram"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client: TelegramClient | None = None
        self._channel: Channel | None = None
        self._metadata: MetadataRepository | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def init(
        self,
        api_id: int,
        api_hash: str,
        metadata: MetadataRepository,
        phone: str | None = None,
        channel_id: int | str | None = None,
        session_name: str = "vault_session",
        max_concurrent: int = 10,
        **kwargs: Any,
    ) -> None:
        self._metadata = metadata
        self._client = TelegramClient(session_name, api_id, api_hash)
        await self._client.start(phone=phone)
        if channel_id is not None:
            self._channel = await self._client.get_entity(channel_id)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.NAME

    def _ensure_initialized(self) -> None:
        if (
            self._client is None
            or self._channel is None
            or self._metadata is None
            or self._semaphore is None
        ):
            raise RuntimeError("TelegramStorageProvider not initialized. Call init() first.")

    async def create_chunk(self, data: bytes) -> ChunkId:
        self._ensure_initialized()
        chunk_id = ChunkId(hashlib.sha256(data).hexdigest())
        async with self._semaphore:
            uploaded = await self._client.upload_file(data, file_name=f"chunk_{chunk_id}")  # type: ignore[union-attr]
            message = await self._client.send_file(self._channel, uploaded)  # type: ignore[union-attr]
            message = cast(Message, message)
        info = ChunkInfo(
            size=len(data),
            sha256=hashlib.sha256(data).digest(),
            created_at=datetime.now(UTC),
        )
        await self._metadata.save(chunk_id, message.id, info)  # type: ignore[union-attr]
        return chunk_id

    async def get_chunk(self, chunk_id: ChunkId) -> bytes:
        self._ensure_initialized()
        message_id = await self._metadata.get_message_id(chunk_id)  # type: ignore[union-attr]
        async with self._semaphore:
            message = await self._client.get_messages(self._channel, ids=message_id)  # type: ignore[union-attr]
            message = cast(Message | None, message)
            if message is None:
                raise KeyError(f"Message {message_id} not found in channel")
            data = await message.download_media(file=bytes)  # type: ignore[arg-type]
        if data is None:
            raise KeyError(f"Chunk {chunk_id} data not found")
        return data if isinstance(data, bytes) else data.encode()

    async def delete_chunk(self, chunk_id: ChunkId) -> None:
        self._ensure_initialized()
        await self._metadata.mark_deleted(chunk_id)  # type: ignore[union-attr]

    async def stat(self, chunk_id: ChunkId) -> ChunkInfo:
        self._ensure_initialized()
        return await self._metadata.get_info(chunk_id)  # type: ignore[union-attr]

    async def is_healthy(self) -> bool:
        if self._client is None:
            return False
        try:
            await self._client.get_me()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
        self._channel = None
        self._metadata = None
        self._semaphore = None
