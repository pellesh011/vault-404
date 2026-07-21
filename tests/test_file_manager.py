from datetime import UTC, datetime

import pytest

from vaultfs.application.chunk_manager import ChunkManager
from vaultfs.application.file_manager import FileManager
from vaultfs.infrastructure.database.repository import FileChunk, Node
from vaultfs.storage.interface import ChunkId, ChunkInfo


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

    async def add_chunk(self, node_id: int, chunk_index: int, offset: int, chunk_id: str) -> None:
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

    async def update_chunk(self, file_chunk_id: int, new_chunk_id: str) -> None:
        for chunks in self._chunks.values():
            for fc in chunks:
                if fc.id == file_chunk_id:
                    fc.chunk_id = new_chunk_id
                    return

    async def get_orphaned_chunks(self) -> list:
        used: set[str] = set()
        for chunks in self._chunks.values():
            for fc in chunks:
                used.add(fc.chunk_id)
        return [cid for cid in self._data if cid not in used]

    _data: dict[str, bytes] = {}


class InMemoryChunkStorage:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._next_id = 1

    async def create_chunk(self, data: bytes) -> ChunkId:
        cid = f"chunk_{self._next_id}"
        self._next_id += 1
        self._data[cid] = data
        return ChunkId(cid)

    async def get_chunk(self, chunk_id: ChunkId) -> bytes:
        data = self._data.get(chunk_id)
        if data is None:
            raise KeyError(f"Chunk {chunk_id} not found")
        return data

    async def delete_chunk(self, chunk_id: ChunkId) -> None:
        self._data.pop(chunk_id, None)

    async def stat(self, chunk_id: ChunkId) -> ChunkInfo:
        data = self._data.get(chunk_id)
        if data is None:
            raise KeyError(f"Chunk {chunk_id} not found")
        return ChunkInfo(size=len(data), sha256=b"", created_at=datetime.now(UTC))


class InMemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

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
def chunk_manager(metadata: InMemoryMetadataRepo) -> ChunkManager:
    storage = InMemoryChunkStorage()
    cache = InMemoryCache()
    return ChunkManager(storage=storage, metadata=metadata, cache=cache)


@pytest.fixture
async def fm(metadata: InMemoryMetadataRepo, chunk_manager: ChunkManager) -> FileManager:
    fm = FileManager(metadata=metadata, chunk_manager=chunk_manager)
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
        stat = await fm.stat(node.id)
        assert stat.name == "test.txt"
        assert stat.type == "file"
        assert stat.parent_id == fm.root_id

    async def test_stat_nonexistent_raises(self, fm: FileManager) -> None:
        with pytest.raises(KeyError):
            await fm.stat(9999)

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

    async def test_read_directory_raises(self, fm: FileManager) -> None:
        with pytest.raises(IsADirectoryError):
            await fm.read(fm.root_id, 0, 10)

    async def test_write_to_directory_raises(self, fm: FileManager) -> None:
        with pytest.raises(IsADirectoryError):
            await fm.write(fm.root_id, 0, b"data")

    async def test_rename(self, fm: FileManager) -> None:
        node = await fm.create_file(fm.root_id, "old.txt")
        await fm.rename(node.id, "new.txt")
        # The Node object should be updated via reference
        stat = await fm.stat(node.id)
        assert stat.name == "new.txt"

    async def test_truncate(
        self, metadata: InMemoryMetadataRepo, chunk_manager: ChunkManager
    ) -> None:
        fm = FileManager(metadata=metadata, chunk_manager=chunk_manager)
        await fm.initialize(chunk_size=65536)
        node = await fm.create_file(fm.root_id, "file.txt")
        data = b"x" * 1000
        await fm.write(node.id, 0, data)
        children = await fm.list_directory(fm.root_id)
        assert children[0].size == 1000
        await fm.truncate(node.id, 100)
        children = await fm.list_directory(fm.root_id)
        assert len(children) == 1
        assert children[0].size == 100

    async def test_initialize_idempotent(self, metadata: InMemoryMetadataRepo) -> None:
        storage = InMemoryChunkStorage()
        cache = InMemoryCache()
        cm = ChunkManager(storage=storage, metadata=metadata, cache=cache)
        fm1 = FileManager(metadata=metadata, chunk_manager=cm)
        await fm1.initialize()
        root_id1 = fm1.root_id

        fm2 = FileManager(metadata=metadata, chunk_manager=cm)
        await fm2.initialize()
        assert fm2.root_id == root_id1
