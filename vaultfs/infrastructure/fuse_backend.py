from abc import ABC, abstractmethod


class FUSEBackend(ABC):
    @abstractmethod
    async def mount(self) -> None: ...

    @abstractmethod
    async def run(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...
