from unittest.mock import AsyncMock, MagicMock

import pytest

from vaultfs.storage.interface import ChunkId
from vaultfs.storage.metadata import InMemoryMetadataRepository
from vaultfs.storage.provider import ProviderConfig
from vaultfs.storage.telegram_provider import TelegramStorageProvider


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
def config() -> ProviderConfig:
    return ProviderConfig(name="test", type="telegram")


@pytest.fixture
def metadata() -> InMemoryMetadataRepository:
    return InMemoryMetadataRepository()


@pytest.fixture
async def provider(
    mock_client: MagicMock,
    mock_channel: MagicMock,
    config: ProviderConfig,
    metadata: InMemoryMetadataRepository,
) -> TelegramStorageProvider:
    return TelegramStorageProvider(
        config=config,
        client=mock_client,
        channel=mock_channel,
        metadata=metadata,
        max_concurrent=10,
    )


class TestTelegramStorageProvider:
    async def test_create_chunk_uploads_to_channel(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        mock_channel: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=12345)

        chunk_id = await provider.create_chunk(b"test data")

        mock_client.upload_file.assert_awaited_once_with(
            b"test data",
            file_name=f"chunk_{chunk_id}",
        )
        mock_client.send_file.assert_awaited_once()

    async def test_create_chunk_saves_message_id(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=999)

        chunk_id = await provider.create_chunk(b"test data")
        message_id = await metadata.get_message_id(chunk_id)

        assert message_id == 999

    async def test_create_chunk_returns_chunk_id(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = await provider.create_chunk(b"test data")

        assert isinstance(chunk_id, str)
        assert len(chunk_id) == 64

    async def test_get_chunk_downloads_from_channel(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        mock_channel: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=b"test data")
        mock_client.send_file.return_value = MagicMock(id=42)
        mock_client.get_messages.return_value = mock_message

        chunk_id = await provider.create_chunk(b"test data")
        await provider.get_chunk(chunk_id)

        mock_client.get_messages.assert_awaited_once_with(
            mock_channel,
            ids=42,
        )

    async def test_get_chunk_returns_correct_data(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=b"test data")
        mock_client.get_messages.return_value = mock_message

        chunk_id = await provider.create_chunk(b"test data")
        result = await provider.get_chunk(chunk_id)

        assert result == b"test data"

    async def test_get_chunk_large_data(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        large_data = b"x" * (10 * 1024 * 1024)
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=large_data)
        mock_client.get_messages.return_value = mock_message

        chunk_id = await provider.create_chunk(large_data)
        result = await provider.get_chunk(chunk_id)

        assert result == large_data
        assert len(result) == 10 * 1024 * 1024

    async def test_delete_chunk_marks_deleted(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = await provider.create_chunk(b"test data")
        await provider.delete_chunk(chunk_id)

        with pytest.raises(KeyError):
            await metadata.get_message_id(chunk_id)

    async def test_stat_returns_size_and_hash(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        import hashlib

        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = await provider.create_chunk(b"test data")
        info = await provider.stat(chunk_id)

        assert info.size == 9
        assert info.sha256 == hashlib.sha256(b"test data").digest()

    async def test_get_chunk_nonexistent_raises(
        self,
        provider: TelegramStorageProvider,
    ) -> None:
        with pytest.raises(KeyError):
            await provider.get_chunk(ChunkId("nonexistent"))

    async def test_stat_nonexistent_raises(
        self,
        provider: TelegramStorageProvider,
    ) -> None:
        with pytest.raises(KeyError):
            await provider.stat(ChunkId("nonexistent"))

    async def test_create_chunk_with_empty_data(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = await provider.create_chunk(b"")

        assert isinstance(chunk_id, str)
        assert len(chunk_id) == 64

    async def test_concurrent_uploads_respect_semaphore(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        import asyncio

        async def delayed_upload(*args: object, **kwargs: object) -> MagicMock:
            await asyncio.sleep(0.05)
            return MagicMock()

        mock_client.upload_file = AsyncMock(side_effect=delayed_upload)

        tasks = [provider.create_chunk(b"data") for _ in range(5)]
        await asyncio.gather(*tasks)

        assert mock_client.upload_file.await_count == 5

    async def test_is_healthy_returns_true(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.get_me = AsyncMock(return_value=MagicMock())
        assert await provider.is_healthy() is True

    async def test_is_healthy_returns_false_on_error(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.get_me = AsyncMock(side_effect=Exception("connection failed"))
        assert await provider.is_healthy() is False

    async def test_name_property(
        self,
        provider: TelegramStorageProvider,
    ) -> None:
        assert provider.name == TelegramStorageProvider.NAME
