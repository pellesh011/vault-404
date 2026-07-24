import uuid
from datetime import UTC, datetime

import pytest

from vaultfs.application.chunk_manager import ChunkManager
from vaultfs.application.file_manager import FileManager
from vaultfs.domain.acl import PERM_READ, PERM_WRITE, InMemoryACL
from vaultfs.domain.chunk_policy import DefaultChunkPolicy
from vaultfs.domain.exceptions import DirectoryNotEmptyError, PermissionDeniedError
from vaultfs.domain.file_handle import FileHandle
from vaultfs.infrastructure.database.repository import FileChunk, Node
from vaultfs.storage.interface import ChunkId
from vaultfs.storage.memory_provider import MemoryStorageProvider
from vaultfs.storage.provider import ProviderConfig
from vaultfs.storage.provider_factory import StorageProviderRegistry

PROVIDER_NAME = "memory"


class InMemoryMetadataRepo:
    def __init__(self) -> None:
        self._nodes: dict[int, Node] = {}
        self._children: dict[int | None, list[int]] = {}
        self._chunks: dict[int, list[FileChunk]] = {}
        self._next_id = 1

    async def create_node(
        self,
        parent_id: int | None,
        name: str,
        type: str,
        chunk_size: int | None = None,
    ) -> Node:
        now = datetime.now(UTC)
        node_id = self._next_id
        self._next_id += 1
        node = Node(
            id=node_id,
            parent_id=parent_id,
            name=name,
            type=type,
            created_at=now,
            modified_at=now,
            chunk_size=chunk_size,
        )
        self._nodes[node_id] = node
        if parent_id not in self._children:
            self._children[parent_id] = []
        self._children[parent_id].append(node_id)
        return node

    async def get_node(self, node_id: int) -> Node:
        node = self._nodes.get(node_id)
        if node is None:
            raise KeyError(f"Node {node_id} not found")
        return node

    async def get_root_node(self) -> Node | None:
        for node in self._nodes.values():
            if node.parent_id is None and node.name == "/":
                return node
        return None

    async def list_children(self, parent_id: int) -> list[Node]:
        child_ids = self._children.get(parent_id, [])
        return [self._nodes[cid] for cid in child_ids if cid in self._nodes]

    async def delete_node(self, node_id: int) -> None:
        node = self._nodes.pop(node_id, None)
        if node is None:
            raise KeyError(f"Node {node_id} not found")
        if node.parent_id in self._children:
            self._children[node.parent_id] = [
                cid for cid in self._children[node.parent_id] if cid != node_id
            ]
        self._chunks.pop(node_id, None)

    async def update_node_size(self, node_id: int, size: int) -> None:
        node = self._nodes.get(node_id)
        if node is None:
            raise KeyError(f"Node {node_id} not found")
        node.size = size

    async def update_node(
        self,
        node_id: int,
        name: str | None = None,
        parent_id: int | None = None,
    ) -> None:
        node = self._nodes.get(node_id)
        if node is None:
            raise KeyError(f"Node {node_id} not found")
        if name is not None:
            node.name = name
        if parent_id is not None:
            old_parent = node.parent_id
            node.parent_id = parent_id
            if old_parent in self._children and node_id in self._children[old_parent]:
                self._children[old_parent].remove(node_id)
            if parent_id not in self._children:
                self._children[parent_id] = []
            self._children[parent_id].append(node_id)

    async def add_chunk(
        self, node_id: int, chunk_index: int, offset: int, chunk_id: uuid.UUID
    ) -> None:
        if node_id not in self._chunks:
            self._chunks[node_id] = []
        fc = FileChunk(
            id=len(self._chunks[node_id]) + 1,
            node_id=node_id,
            chunk_index=chunk_index,
            offset=offset,
            chunk_id=chunk_id,
        )
        self._chunks[node_id].append(fc)

    async def get_chunks(self, node_id: int) -> list[FileChunk]:
        return self._chunks.get(node_id, [])

    async def update_chunk(self, file_chunk_id: int, new_chunk_id: uuid.UUID) -> None:
        for chunks in self._chunks.values():
            for fc in chunks:
                if fc.id == file_chunk_id:
                    fc.chunk_id = new_chunk_id
                    return

    async def get_orphaned_chunks(self, force: bool = False) -> list:
        used: set[uuid.UUID] = set()
        for chunks in self._chunks.values():
            for fc in chunks:
                used.add(fc.chunk_id)
        return [cid for cid in self._data if cid not in used]

    async def get_provider_name_for_chunk(self, chunk_id: uuid.UUID) -> str:
        return PROVIDER_NAME

    async def get_or_create_storage_provider(
        self, name: str, type_: str, description: str = "", config: dict | None = None
    ) -> object:
        from dataclasses import dataclass

        @dataclass
        class FakeProviderModel:
            id: int
            name: str
            type: str

        return FakeProviderModel(id=1, name=name, type=type_)

    async def save_chunk_with_external_id(
        self,
        chunk_id: uuid.UUID,
        size: int,
        sha256: bytes | None,
        external_id: str,
        storage_provider_id: int,
        nonce: bytes | None = None,
        auth_tag: bytes | None = None,
    ) -> object:
        pass  # No-op for tests

    async def commit(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    _data: dict[uuid.UUID, bytes] = {}


class InMemoryCache:
    def __init__(self) -> None:
        self._data: dict[ChunkId, bytes] = {}

    async def get(self, key: ChunkId) -> bytes | None:
        return self._data.get(key)

    async def set(self, key: ChunkId, value: bytes) -> None:
        self._data[key] = value

    async def delete(self, key: ChunkId) -> None:
        self._data.pop(key, None)

    async def clear(self) -> None:
        self._data.clear()


@pytest.fixture
def metadata() -> InMemoryMetadataRepo:
    return InMemoryMetadataRepo()


@pytest.fixture
def acl() -> InMemoryACL:
    return InMemoryACL()


@pytest.fixture
def chunk_policy() -> DefaultChunkPolicy:
    return DefaultChunkPolicy()


@pytest.fixture
def provider() -> MemoryStorageProvider:
    return MemoryStorageProvider(config=ProviderConfig(name=PROVIDER_NAME, type="memory"))


@pytest.fixture
def registry(provider: MemoryStorageProvider) -> StorageProviderRegistry:
    r = StorageProviderRegistry()
    r.add(provider)
    return r


@pytest.fixture
def chunk_manager(
    metadata: InMemoryMetadataRepo,
    registry: StorageProviderRegistry,
) -> ChunkManager:
    cache = InMemoryCache()
    return ChunkManager(
        registry=registry, metadata=metadata, cache=cache, default_provider=PROVIDER_NAME
    )


@pytest.fixture
async def fm(
    metadata: InMemoryMetadataRepo,
    chunk_manager: ChunkManager,
    acl: InMemoryACL,
    chunk_policy: DefaultChunkPolicy,
) -> FileManager:
    fm = FileManager(
        metadata=metadata,
        chunk_manager=chunk_manager,
        acl=acl,
        chunk_policy=chunk_policy,
    )
    await fm.initialize()
    return fm


class TestFileManager:
    async def test_initialize_creates_root(self, fm: FileManager) -> None:
        root = await fm.stat(fm.root_id)
        assert root.name == "/"
        assert root.type == "directory"

    async def test_create_file(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "test.txt")
        assert node.name == "test.txt"
        assert node.type == "file"

    async def test_create_directory(self, fm: FileManager) -> None:
        node = await fm.create_directory(fm.root_id, "subdir")
        assert node.name == "subdir"
        assert node.type == "directory"

    async def test_list_directory(self, fm: FileManager) -> None:
        await fm.create_file(fm.root_id, "a.txt")
        await fm.create_file(fm.root_id, "b.txt")
        children = await fm.list_directory(fm.root_id)
        names = [c.name for c in children]
        assert "a.txt" in names
        assert "b.txt" in names

    async def test_stat(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "test.txt")
        result = await fm.stat(node.id)
        assert result.name == "test.txt"
        assert result.type == "file"
        assert result.parent_id == fm.root_id

    async def test_stat_nonexistent_raises(self, fm: FileManager) -> None:
        with pytest.raises(KeyError):
            await fm.stat(9999)

    async def test_lookup_finds_child(self, fm: FileManager) -> None:
        await fm.create_file(fm.root_id, "file.txt")
        result = await fm.lookup(fm.root_id, "file.txt")
        assert result.name == "file.txt"

    async def test_lookup_raises_not_found(self, fm: FileManager) -> None:
        with pytest.raises(FileNotFoundError):
            await fm.lookup(fm.root_id, "nonexistent")

    async def test_open_returns_handle(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "test.txt")
        fh = await fm.open(node.id)
        assert isinstance(fh, FileHandle)
        assert fh.node_id == node.id

    async def test_read_delegates_to_chunk_manager(self, fm: FileManager, metadata) -> None:
        node = await fm.create_file(fm.root_id, "test.txt")
        data = b"hello world"
        await fm.write(FileHandle(node_id=node.id), 0, data)
        result = await fm.read(FileHandle(node_id=node.id), 0, 5)
        assert result == b"hello"

    async def test_write_delegates_to_chunk_manager(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "test.txt")
        data = b"test data"
        written = await fm.write(FileHandle(node_id=node.id), 0, data)
        assert written == len(data)

    async def test_read_directory_raises(self, fm: FileManager) -> None:
        fh = FileHandle(node_id=fm.root_id)
        with pytest.raises(IsADirectoryError):
            await fm.read(fh, 0, 10)

    async def test_write_to_directory_raises(self, fm: FileManager) -> None:
        fh = FileHandle(node_id=fm.root_id)
        with pytest.raises(IsADirectoryError):
            await fm.write(fh, 0, b"data")

    async def test_mkdir_creates_node(self, fm: FileManager) -> None:
        node = await fm.mkdir(fm.root_id, "subdir")
        assert node.name == "subdir"
        assert node.type == "directory"

    async def test_unlink_removes_node(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "test.txt")
        await fm.unlink(fm.root_id, "test.txt")
        with pytest.raises(KeyError):
            await fm.stat(node.id)

    async def test_rmdir_fails_if_not_empty(self, fm: FileManager) -> None:
        subdir = await fm.mkdir(fm.root_id, "subdir")
        await fm.create_file(subdir.id, "file.txt")
        with pytest.raises(DirectoryNotEmptyError):
            await fm.rmdir(fm.root_id, "subdir")

    async def test_rmdir_succeeds_if_empty(self, fm: FileManager) -> None:
        subdir = await fm.mkdir(fm.root_id, "subdir")
        await fm.rmdir(fm.root_id, "subdir")
        with pytest.raises(KeyError):
            await fm.stat(subdir.id)

    async def test_create_file_uses_chunk_policy(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "video.mp4")
        assert node.chunk_size == 16 * 1024 * 1024

    async def test_delete_file(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "test.txt")
        await fm.delete(node.id)
        with pytest.raises(KeyError):
            await fm.stat(node.id)

    async def test_delete_nonexistent_raises(self, fm: FileManager) -> None:
        with pytest.raises(KeyError):
            await fm.delete(9999)

    async def test_delete_nonempty_directory_raises(self, fm: FileManager) -> None:
        subdir = await fm.create_directory(fm.root_id, "subdir")
        await fm.create_file(subdir.id, "file.txt")
        with pytest.raises(OSError):
            await fm.delete(subdir.id)

    async def test_resolve_path_root(self, fm: FileManager) -> None:
        node_id = await fm.resolve_path("/")
        assert node_id == fm.root_id

    async def test_resolve_path_nested(self, fm: FileManager) -> None:
        subdir = await fm.create_directory(fm.root_id, "subdir")
        node = await fm.create_file(subdir.id, "file.txt")
        result = await fm.resolve_path("/subdir/file.txt")
        assert result == node.id

    async def test_resolve_path_nonexistent_raises(self, fm: FileManager) -> None:
        with pytest.raises(FileNotFoundError):
            await fm.resolve_path("/nonexistent")

    async def test_rename(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "old.txt")
        await fm.rename(node.id, "new.txt")
        stat = await fm.stat(node.id)
        assert stat.name == "new.txt"

    async def test_rename_overwrite(self, fm: FileManager) -> None:
        src = await fm.create_file(fm.root_id, "src.txt")
        dst = await fm.create_file(fm.root_id, "dst.txt")
        await fm.rename(src.id, "dst.txt")
        with pytest.raises(KeyError):
            await fm.stat(dst.id)
        renamed = await fm.lookup(fm.root_id, "dst.txt")
        assert renamed.id == src.id
        assert renamed.name == "dst.txt"

    async def test_rename_move_to_subdir(self, fm: FileManager) -> None:
        subdir = await fm.mkdir(fm.root_id, "subdir")
        node = await fm.create_file(fm.root_id, "file.txt")
        await fm.rename(node.id, "moved.txt", subdir.id)
        with pytest.raises(FileNotFoundError):
            await fm.lookup(fm.root_id, "file.txt")
        moved = await fm.lookup(subdir.id, "moved.txt")
        assert moved.id == node.id

    async def test_rename_checks_acl(self, acl: InMemoryACL, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "old.txt")
        await acl.set_permission(fm.root_id, "", PERM_READ)
        with pytest.raises(PermissionDeniedError):
            await fm.rename(node.id, "new.txt")

    async def test_truncate(
        self,
        metadata: InMemoryMetadataRepo,
        chunk_manager: ChunkManager,
    ) -> None:
        acl = InMemoryACL()
        policy = DefaultChunkPolicy()
        fm = FileManager(
            metadata=metadata,
            chunk_manager=chunk_manager,
            acl=acl,
            chunk_policy=policy,
        )
        await fm.initialize(chunk_size=65536)
        node = await fm.create_file(fm.root_id, "file.txt")
        data = b"x" * 1000
        await fm.write(FileHandle(node_id=node.id), 0, data)
        children = await fm.list_directory(fm.root_id)
        assert children[0].size == 1000
        await fm.truncate(node.id, 100)
        children = await fm.list_directory(fm.root_id)
        assert len(children) == 1
        assert children[0].size == 100

    async def test_initialize_idempotent(self, metadata: InMemoryMetadataRepo) -> None:
        acl = InMemoryACL()
        policy = DefaultChunkPolicy()
        registry = StorageProviderRegistry()
        provider = MemoryStorageProvider(config=ProviderConfig(name=PROVIDER_NAME, type="memory"))
        registry.add(provider)
        cache = InMemoryCache()
        cm = ChunkManager(registry=registry, metadata=metadata, cache=cache)
        fm1 = FileManager(metadata=metadata, chunk_manager=cm, acl=acl, chunk_policy=policy)
        await fm1.initialize()
        root_id1 = fm1.root_id

        fm2 = FileManager(metadata=metadata, chunk_manager=cm, acl=acl, chunk_policy=policy)
        await fm2.initialize()
        assert fm2.root_id == root_id1

    async def test_create_file_checks_acl(
        self,
        acl: InMemoryACL,
        fm: FileManager,
    ) -> None:
        await acl.set_permission(fm.root_id, "", PERM_READ)
        with pytest.raises(PermissionDeniedError):
            await fm.create_file(fm.root_id, "test.txt")

    async def test_unlink_checks_acl(
        self,
        acl: InMemoryACL,
        fm: FileManager,
    ) -> None:
        await fm.create_file(fm.root_id, "test.txt")
        await acl.set_permission(fm.root_id, "", PERM_READ)
        with pytest.raises(PermissionDeniedError):
            await fm.unlink(fm.root_id, "test.txt")

    async def test_open_checks_acl(
        self,
        acl: InMemoryACL,
        fm: FileManager,
    ) -> None:
        node = await fm.create_file(fm.root_id, "test.txt")
        await acl.set_permission(node.id, "", PERM_WRITE)
        with pytest.raises(PermissionDeniedError):
            await fm.open(node.id, 0)  # O_RDONLY → PERM_READ, but only PERM_WRITE granted
