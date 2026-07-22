import pytest

from vaultfs.domain.acl import (
    PERM_ALL,
    PERM_NONE,
    PERM_READ,
    PERM_WRITE,
    InMemoryACL,
)
from vaultfs.domain.exceptions import PermissionDeniedError


@pytest.fixture
def acl() -> InMemoryACL:
    return InMemoryACL()


class TestInMemoryACL:
    async def test_default_allows_all(self, acl: InMemoryACL) -> None:
        await acl.check_permission(1, PERM_READ)
        await acl.check_permission(1, PERM_WRITE)
        await acl.check_permission(1, PERM_ALL)
        await acl.check_permission(2, PERM_READ)

    async def test_deny_when_no_permission(self, acl: InMemoryACL) -> None:
        await acl.set_permission(1, "alice", PERM_READ)
        with pytest.raises(PermissionDeniedError):
            await acl.check_permission(1, PERM_WRITE, "alice")

    async def test_check_with_default_principal(self, acl: InMemoryACL) -> None:
        await acl.set_permission(1, "", PERM_READ)
        with pytest.raises(PermissionDeniedError):
            await acl.check_permission(1, PERM_WRITE)

    async def test_set_permission_none_removes_entry(self, acl: InMemoryACL) -> None:
        await acl.set_permission(1, "bob", PERM_ALL)
        assert await acl.get_permissions(1, "bob") == PERM_ALL
        await acl.set_permission(1, "bob", PERM_NONE)
        assert await acl.get_permissions(1, "bob") == PERM_ALL

    async def test_multiple_nodes_independent(self, acl: InMemoryACL) -> None:
        await acl.set_permission(1, "alice", PERM_READ)
        await acl.set_permission(2, "alice", PERM_WRITE)
        await acl.check_permission(2, PERM_WRITE, "alice")
        with pytest.raises(PermissionDeniedError):
            await acl.check_permission(1, PERM_WRITE, "alice")

    async def test_different_principals_independent(self, acl: InMemoryACL) -> None:
        await acl.set_permission(1, "alice", PERM_READ)
        await acl.set_permission(1, "bob", PERM_WRITE)
        with pytest.raises(PermissionDeniedError):
            await acl.check_permission(1, PERM_WRITE, "alice")
        await acl.check_permission(1, PERM_WRITE, "bob")
