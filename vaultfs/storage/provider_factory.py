from vaultfs.storage.memory_provider import MemoryStorageProvider
from vaultfs.storage.provider import ProviderConfig, StorageProvider
from vaultfs.storage.telegram_provider import TelegramStorageProvider

_PROVIDER_REGISTRY: dict[str, type[StorageProvider]] = {
    TelegramStorageProvider.NAME: TelegramStorageProvider,
    MemoryStorageProvider.NAME: MemoryStorageProvider,
}


class StorageProviderFactory:
    def __init__(self) -> None:
        self._providers: dict[str, type[StorageProvider]] = dict(_PROVIDER_REGISTRY)
        self._cache: dict[str, StorageProvider] = {}

    def register(self, provider_class: type[StorageProvider]) -> None:
        self._providers[provider_class.NAME] = provider_class

    async def get_provider(
        self,
        name: str,
        **kwargs: object,
    ) -> StorageProvider:
        if name in self._cache:
            return self._cache[name]

        if name not in self._providers:
            available = ", ".join(sorted(self._providers))
            raise ValueError(f"Provider '{name}' not registered. Available: {available}")

        provider_class = self._providers[name]
        config = ProviderConfig(name=name, type=name)
        provider = provider_class(config=config, **kwargs)  # type: ignore[arg-type]
        self._cache[name] = provider
        return provider

    async def close_all(self) -> None:
        for provider in self._cache.values():
            await provider.close()
        self._cache.clear()
