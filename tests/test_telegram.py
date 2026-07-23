import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vaultfs.storage.provider import ProviderConfig
from vaultfs.storage.telegram_provider import TelegramStorageProvider


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.upload_file = AsyncMock()
    client.send_file = AsyncMock()
    client.get_messages = AsyncMock()
    client.delete_messages = AsyncMock()
    return client


@pytest.fixture
def mock_channel() -> MagicMock:
    return MagicMock()


@pytest.fixture
def config() -> ProviderConfig:
    return ProviderConfig(name="test", type="telegram")


@pytest.fixture
async def provider(
    mock_client: MagicMock,
    mock_channel: MagicMock,
    config: ProviderConfig,
) -> TelegramStorageProvider:
    p = TelegramStorageProvider(config=config)
    p._client = mock_client
    p._channel = mock_channel
    p._semaphore = asyncio.Semaphore(10)
    return p


class TestTelegramStorageProvider:
    async def test_create_chunk_uploads_to_channel(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
        mock_channel: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=12345)

        await provider.create_chunk(b"test data")

        mock_client.upload_file.assert_awaited_once()
        mock_client.send_file.assert_awaited_once()

    async def test_create_chunk_returns_message_id(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=999)

        external_id = await provider.create_chunk(b"test data")

        assert external_id == "999"

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

        external_id = await provider.create_chunk(b"test data")
        await provider.get_chunk(external_id)

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

        external_id = await provider.create_chunk(b"test data")
        result_data = await provider.get_chunk(external_id)

        assert result_data == b"test data"

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

        external_id = await provider.create_chunk(large_data)
        result_data = await provider.get_chunk(external_id)

        assert result_data == large_data
        assert len(result_data) == 10 * 1024 * 1024

    async def test_delete_chunk_does_not_raise(
        self,
        provider: TelegramStorageProvider,
    ) -> None:
        await provider.delete_chunk("1")

    async def test_get_chunk_nonexistent_raises(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.get_messages.return_value = None
        with pytest.raises(KeyError):
            await provider.get_chunk("999")

    async def test_create_chunk_with_empty_data(
        self,
        provider: TelegramStorageProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.upload_file.return_value = MagicMock()
        mock_client.send_file.return_value = MagicMock(id=1)

        external_id = await provider.create_chunk(b"")

        assert external_id == "1"

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
            await p.get_chunk("1")

    async def test_not_initialized_delete_chunk_raises(self, config: ProviderConfig) -> None:
        p = TelegramStorageProvider(config=config)
        with pytest.raises(RuntimeError, match="not initialized"):
            await p.delete_chunk("1")

    async def test_init_sets_state(
        self,
        config: ProviderConfig,
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
                phone="+1234567890",
                channel_id="test_channel",
            )

        assert p._client is mock_client
        assert p._channel is mock_channel
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
        assert provider._semaphore is None
