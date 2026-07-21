import asyncio
import hashlib
from datetime import UTC, datetime
from typing import cast

from telethon import TelegramClient
from telethon.tl.custom import Message
from telethon.tl.types import Channel

from vaultfs.storage.interface import ChunkId, ChunkInfo
from vaultfs.storage.metadata import MetadataRepository


class TelegramChunkStorage:
    def __init__(
        self,
        client: TelegramClient,
        channel: Channel,
        metadata: MetadataRepository,
        max_concurrent: int = 10,
    ) -> None:
        self._client = client
        self._channel = channel
        self._metadata = metadata
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def create_chunk(self, data: bytes) -> ChunkId:
        chunk_id = ChunkId(hashlib.sha256(data).hexdigest())
        async with self._semaphore:
            uploaded = await self._client.upload_file(
                data,
                file_name=f"chunk_{chunk_id}",
            )
            message = await self._client.send_file(
                self._channel,
                uploaded,
            )
            message = cast(Message, message)
        info = ChunkInfo(
            size=len(data),
            sha256=hashlib.sha256(data).digest(),
            created_at=datetime.now(UTC),
        )
        await self._metadata.save(chunk_id, message.id, info)
        return chunk_id

    async def get_chunk(self, chunk_id: ChunkId) -> bytes:
        message_id = await self._metadata.get_message_id(chunk_id)
        async with self._semaphore:
            message = await self._client.get_messages(
                self._channel,
                ids=message_id,
            )
            message = cast(Message | None, message)
            if message is None:
                raise KeyError(f"Message {message_id} not found in channel")
            data = await message.download_media(  # type: ignore[arg-type]
                file=bytes,  # type: ignore[arg-type]
            )
        if data is None:
            raise KeyError(f"Chunk {chunk_id} data not found")
        return data if isinstance(data, bytes) else data.encode()

    async def delete_chunk(self, chunk_id: ChunkId) -> None:
        await self._metadata.mark_deleted(chunk_id)

    async def stat(self, chunk_id: ChunkId) -> ChunkInfo:
        return await self._metadata.get_info(chunk_id)
