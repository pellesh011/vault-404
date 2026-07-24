import asyncio
from typing import Any, cast

from telethon import TelegramClient
from telethon.tl.custom import Message
from telethon.tl.types import Channel

from vaultfs.storage.provider import ProviderConfig, StorageProvider

ProxyConfig = dict[str, str | int | bool] | None


class TelegramStorageProvider(StorageProvider):
    NAME = "telegram"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client: TelegramClient | None = None
        self._channel: Channel | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def init(
        self,
        api_id: int,
        api_hash: str,
        phone: str | None = None,
        channel_id: int | str | None = None,
        session_name: str = "vault_session",
        max_concurrent: int = 10,
        proxy: ProxyConfig = None,
        **kwargs: Any,
    ) -> None:
        self._client = TelegramClient(session_name, api_id, api_hash, proxy=proxy)
        await self._client.start(phone=phone)
        if channel_id is not None:
            self._channel = await self._client.get_entity(channel_id)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.NAME

    def _ensure_initialized(self) -> None:
        if self._client is None or self._channel is None or self._semaphore is None:
            raise RuntimeError("TelegramStorageProvider not initialized. Call init() first.")

    async def create_chunk(self, data: bytes) -> str:
        self._ensure_initialized()
        async with self._semaphore:
            uploaded = await self._client.upload_file(data, file_name=f"chunk_{id(data)}")
            message = await self._client.send_file(self._channel, uploaded)
            message = cast(Message, message)

        return str(message.id)

    async def get_chunk(self, external_id: str) -> bytes:
        self._ensure_initialized()
        async with self._semaphore:
            message = await self._client.get_messages(self._channel, ids=int(external_id))
            message = cast(Message | None, message)
            if message is None:
                raise KeyError(f"Message {external_id} not found in channel")
            data = await message.download_media(file=bytes)
        if data is None:
            raise KeyError(f"Chunk external_id={external_id} data not found")
        return data if isinstance(data, bytes) else data.encode()

    async def delete_chunk(self, external_id: str) -> None:
        self._ensure_initialized()
        async with self._semaphore:
            await self._client.delete_messages(self._channel, [int(external_id)])

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
        self._semaphore = None
