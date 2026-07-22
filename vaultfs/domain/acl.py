from abc import ABC, abstractmethod

from vaultfs.domain.exceptions import PermissionDeniedError

PERM_NONE = 0
PERM_READ = 1
PERM_WRITE = 2
PERM_EXECUTE = 4
PERM_ALL = PERM_READ | PERM_WRITE | PERM_EXECUTE


class ACLSystem(ABC):
    @abstractmethod
    async def check_permission(
        self,
        node_id: int,
        required: int,
        principal: str = "",
    ) -> None: ...

    @abstractmethod
    async def set_permission(
        self,
        node_id: int,
        principal: str,
        permissions: int,
    ) -> None: ...

    @abstractmethod
    async def get_permissions(
        self,
        node_id: int,
        principal: str = "",
    ) -> int: ...


class InMemoryACL(ACLSystem):
    def __init__(self) -> None:
        self._acls: dict[tuple[int, str], int] = {}

    async def check_permission(
        self,
        node_id: int,
        required: int,
        principal: str = "",
    ) -> None:
        effective = await self.get_permissions(node_id, principal)
        if (effective & required) != required:
            raise PermissionDeniedError(node_id, principal)

    async def set_permission(
        self,
        node_id: int,
        principal: str,
        permissions: int,
    ) -> None:
        if permissions == PERM_NONE:
            self._acls.pop((node_id, principal), None)
        else:
            self._acls[(node_id, principal)] = permissions

    async def get_permissions(
        self,
        node_id: int,
        principal: str = "",
    ) -> int:
        key = (node_id, principal)
        if key in self._acls:
            return self._acls[key]
        return PERM_ALL
