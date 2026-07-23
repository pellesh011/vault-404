from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    type: str
    description: str = ""
    config: dict[str, Any] | None = None


class StorageProvider(ABC):
    NAME: str = ""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def provider_type(self) -> str:
        return self.config.type

    async def init(self, **kwargs: Any) -> None:
        """Инициализация провайдера (авторизация, подключение и т.д.)."""

    @abstractmethod
    async def create_chunk(self, data: bytes) -> str: ...

    @abstractmethod
    async def get_chunk(self, external_id: str) -> bytes: ...

    @abstractmethod
    async def delete_chunk(self, external_id: str) -> None: ...

    @abstractmethod
    async def is_healthy(self) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...

    async def __aenter__(self) -> "StorageProvider":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
