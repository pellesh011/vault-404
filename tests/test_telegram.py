from unittest.mock import AsyncMock, MagicMock

import pytest

from vaultfs.storage.interface import ChunkId
from vaultfs.storage.metadata import InMemoryMetadataRepository
from vaultfs.storage.telegram import TelegramChunkStorage


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.upload_file = AsyncMock()
    client.send_file = AsyncMock()
    client.get_messages = AsyncMock()
    return client


@pytest.fixture
def mock_channel() -> MagicMock:
    return MagicMock()


@pytest.fixture
def metadata() -> InMemoryMetadataRepository:
    return InMemoryMetadataRepository()


@pytest.fixture
async def storage(
    mock_client: MagicMock,
    mock_channel: MagicMock,
    metadata: InMemoryMetadataRepository,
) -> TelegramChunkStorage:
    return TelegramChunkStorage(
        client=mock_client,
        channel=mock_channel,
        metadata=metadata,
        max_concurrent=10,
    )


class TestTelegramChunkStorage:
    async def test_create_chunk_uploads_to_channel(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
        mock_channel: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=12345)

        chunk_id = await storage.create_chunk(b"test data")

        mock_client.upload_file.assert_awaited_once_with(
            b"test data",
            file_name=f"chunk_{chunk_id}",
        )
        mock_client.send_file.assert_awaited_once()

    async def test_create_chunk_saves_message_id(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=999)

        chunk_id = await storage.create_chunk(b"test data")

        message_id = await metadata.get_message_id(chunk_id)
        assert message_id == 999

    async def test_create_chunk_returns_chunk_id(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = await storage.create_chunk(b"test data")

        assert isinstance(chunk_id, str)
        assert len(chunk_id) == 64

    async def test_get_chunk_downloads_from_channel(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
        mock_channel: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=b"test data")
        mock_client.send_file.return_value = MagicMock(id=42)
        mock_client.get_messages.return_value = mock_message

        chunk_id = await storage.create_chunk(b"test data")
        await storage.get_chunk(chunk_id)

        mock_client.get_messages.assert_awaited_once_with(
            mock_channel,
            ids=42,
        )

    async def test_get_chunk_returns_correct_data(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=b"test data")
        mock_client.get_messages.return_value = mock_message

        chunk_id = await storage.create_chunk(b"test data")
        result = await storage.get_chunk(chunk_id)

        assert result == b"test data"

    async def test_get_chunk_large_data(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        large_data = b"x" * (10 * 1024 * 1024)
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=large_data)
        mock_client.get_messages.return_value = mock_message

        chunk_id = await storage.create_chunk(large_data)
        result = await storage.get_chunk(chunk_id)

        assert result == large_data
        assert len(result) == 10 * 1024 * 1024

    async def test_delete_chunk_marks_deleted(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = await storage.create_chunk(b"test data")
        await storage.delete_chunk(chunk_id)

        with pytest.raises(KeyError):
            await metadata.get_message_id(chunk_id)

    async def test_stat_returns_size_and_hash(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        import hashlib

        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = await storage.create_chunk(b"test data")
        info = await storage.stat(chunk_id)

        assert info.size == 9
        assert info.sha256 == hashlib.sha256(b"test data").digest()

    async def test_get_chunk_nonexistent_raises(
        self,
        storage: TelegramChunkStorage,
    ) -> None:
        with pytest.raises(KeyError):
            await storage.get_chunk(ChunkId("nonexistent"))

    async def test_stat_nonexistent_raises(
        self,
        storage: TelegramChunkStorage,
    ) -> None:
        with pytest.raises(KeyError):
            await storage.stat(ChunkId("nonexistent"))

    async def test_create_chunk_with_empty_data(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = await storage.create_chunk(b"")

        assert isinstance(chunk_id, str)
        assert len(chunk_id) == 64

    async def test_concurrent_uploads_respect_semaphore(
        self,
        storage: TelegramChunkStorage,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        import asyncio

        async def delayed_upload(*args: object, **kwargs: object) -> MagicMock:
            await asyncio.sleep(0.05)
            return MagicMock()

        mock_client.upload_file = AsyncMock(side_effect=delayed_upload)

        tasks = [storage.create_chunk(b"data") for _ in range(5)]
        await asyncio.gather(*tasks)

        assert mock_client.upload_file.await_count == 5

    async def test_telegram_chunk_storage_protocol(
        self,
        storage: TelegramChunkStorage,
    ) -> None:
        from vaultfs.storage.interface import ChunkStorage

        assert isinstance(storage, ChunkStorage)
