from vaultfs.storage.provider import StorageProvider


class StorageProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, StorageProvider] = {}

    def add(self, provider: StorageProvider) -> None:
        self._providers[provider.name] = provider

    def has(self, name: str) -> bool:
        return name in self._providers

    def get(self, name: str) -> StorageProvider:
        if name not in self._providers:
            available = ", ".join(sorted(self._providers))
            raise ValueError(f"Provider '{name}' not registered. Available: {available}")
        return self._providers[name]

    async def close_all(self) -> None:
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
