import asyncio
import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vaultfs.storage.interface import ChunkId, ChunkInfo, ProviderStorageChunkCreateResult
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
    p = TelegramStorageProvider(config=config)
    p._client = mock_client
    p._channel = mock_channel
    p._metadata = metadata
    p._semaphore = asyncio.Semaphore(10)
    return p


async def _save_chunk(
    metadata: InMemoryMetadataRepository,
    provider: TelegramStorageProvider,
    data: bytes,
    result: ProviderStorageChunkCreateResult,
) -> ChunkId:
    chunk_id = hashlib.sha256(data).hexdigest()
    info = ChunkInfo(
        size=len(data),
        sha256=hashlib.sha256(data).digest(),
        created_at=datetime.now(UTC),
        storage_provider_id=provider.name,
    )
    await metadata.save(ChunkId(chunk_id), int(result.external_id), info)
    return ChunkId(chunk_id)


class TestTelegramStorageProvider:
    async def test_create_chunk_uploads_to_channel(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        mock_channel: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=12345)

        chunk_id = hashlib.sha256(b"test data").hexdigest()
        await provider.create_chunk(b"test data")

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

        result = await provider.create_chunk(b"test data")
        chunk_id = await _save_chunk(metadata, provider, b"test data", result)
        message_id = await metadata.get_message_id(chunk_id)

        assert message_id == 999

    async def test_create_chunk_returns_chunk_id(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = hashlib.sha256(b"test data").hexdigest()
        await provider.create_chunk(b"test data")

        assert isinstance(chunk_id, str)
        assert len(chunk_id) == 64

    async def test_get_chunk_downloads_from_channel(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        mock_channel: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=b"test data")
        mock_client.send_file.return_value = MagicMock(id=42)
        mock_client.get_messages.return_value = mock_message

        result = await provider.create_chunk(b"test data")
        chunk_id = await _save_chunk(metadata, provider, b"test data", result)
        await provider.get_chunk(chunk_id)

        mock_client.get_messages.assert_awaited_once_with(
            mock_channel,
            ids=42,
        )

    async def test_get_chunk_returns_correct_data(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=b"test data")
        mock_client.get_messages.return_value = mock_message

        result = await provider.create_chunk(b"test data")
        chunk_id = await _save_chunk(metadata, provider, b"test data", result)
        result_data = await provider.get_chunk(chunk_id)

        assert result_data == b"test data"

    async def test_get_chunk_large_data(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        large_data = b"x" * (10 * 1024 * 1024)
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        mock_message = MagicMock()
        mock_message.download_media = AsyncMock(return_value=large_data)
        mock_client.get_messages.return_value = mock_message

        result = await provider.create_chunk(large_data)
        chunk_id = await _save_chunk(metadata, provider, large_data, result)
        result_data = await provider.get_chunk(chunk_id)

        assert result_data == large_data
        assert len(result_data) == 10 * 1024 * 1024

    async def test_delete_chunk_marks_deleted(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        chunk_id = hashlib.sha256(b"test data").hexdigest()
        await provider.create_chunk(b"test data")
        await provider.delete_chunk(chunk_id)

        with pytest.raises(KeyError):
            await metadata.get_message_id(chunk_id)

    async def test_stat_returns_size_and_hash(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        result = await provider.create_chunk(b"test data")
        chunk_id = await _save_chunk(metadata, provider, b"test data", result)
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

        chunk_id = hashlib.sha256(b"").hexdigest()
        await provider.create_chunk(b"")

        assert isinstance(chunk_id, str)
        assert len(chunk_id) == 64

    async def test_concurrent_uploads_respect_semaphore(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

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

    async def test_is_healthy_returns_false_when_not_initialized(
        self,
        config: ProviderConfig,
    ) -> None:
        p = TelegramStorageProvider(config=config)
        assert await p.is_healthy() is False

    async def test_name_property(
        self,
        provider: TelegramStorageProvider,
    ) -> None:
        assert provider.name == TelegramStorageProvider.NAME

    async def test_not_initialized_raises(self, config: ProviderConfig) -> None:
        p = TelegramStorageProvider(config=config)
        with pytest.raises(RuntimeError, match="not initialized"):
            await p.create_chunk(b"data")

    async def test_not_initialized_get_chunk_raises(self, config: ProviderConfig) -> None:
        p = TelegramStorageProvider(config=config)
        with pytest.raises(RuntimeError, match="not initialized"):
            await p.get_chunk(ChunkId("test"))

    async def test_not_initialized_delete_chunk_raises(self, config: ProviderConfig) -> None:
        p = TelegramStorageProvider(config=config)
        with pytest.raises(RuntimeError, match="not initialized"):
            await p.delete_chunk(ChunkId("test"))

    async def test_not_initialized_stat_raises(self, config: ProviderConfig) -> None:
        p = TelegramStorageProvider(config=config)
        with pytest.raises(RuntimeError, match="not initialized"):
            await p.stat(ChunkId("test"))

    async def test_init_sets_state(
        self,
        config: ProviderConfig,
        metadata: InMemoryMetadataRepository,
    ) -> None:
        p = TelegramStorageProvider(config=config)
        mock_client = MagicMock()
        mock_channel = MagicMock()

        with patch(
            "vaultfs.storage.telegram_provider.TelegramClient",
            return_value=mock_client,
        ):
            mock_client.start = AsyncMock()
            mock_client.get_entity = AsyncMock(return_value=mock_channel)
            await p.init(
                api_id=12345,
                api_hash="test_hash",
                metadata=metadata,
                phone="+1234567890",
                channel_id="test_channel",
            )

        assert p._client is mock_client
        assert p._channel is mock_channel
        assert p._metadata is metadata
        assert p._semaphore is not None

    async def test_close_resets_state(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.disconnect = AsyncMock()
        await provider.close()

        assert provider._client is None
        assert provider._channel is None
        assert provider._metadata is None
        assert provider._semaphore is None
