from vaultfs.application.chunk_manager import ChunkManager
from vaultfs.domain.acl import PERM_WRITE, ACLSystem
from vaultfs.domain.chunk_policy import ChunkPolicy
from vaultfs.domain.exceptions import DirectoryNotEmptyError
from vaultfs.domain.file_handle import FileHandle
from vaultfs.infrastructure.database.repository import MetadataRepository, Node


class FileManager:
    def __init__(
        self,
        metadata: MetadataRepository,
        chunk_manager: ChunkManager,
        acl: ACLSystem,
        chunk_policy: ChunkPolicy,
    ) -> None:
        self._metadata = metadata
        self._chunk_manager = chunk_manager
        self._acl = acl
        self._chunk_policy = chunk_policy
        self._root_id: int | None = None

    async def initialize(self, chunk_size: int = 65536) -> None:
        self._default_chunk_size = chunk_size
        try:
            root = await self._metadata.get_node(1)
        except KeyError:
            root = await self._metadata.create_node(
                parent_id=None,
                name="/",
                type="directory",
                chunk_size=chunk_size,
            )
        self._root_id = root.id

    @property
    def root_id(self) -> int:
        if self._root_id is None:
            raise RuntimeError("FileManager not initialized")
        return self._root_id

    async def stat(self, node_id: int) -> Node:
        return await self._metadata.get_node(node_id)

    async def lookup(self, parent_id: int, name: str) -> Node:
        children = await self._metadata.list_children(parent_id)
        for child in children:
            if child.name == name:
                return child
        raise FileNotFoundError(f"Name not found: {name}")

    async def open(self, node_id: int, flags: int = 1) -> FileHandle:
        await self._acl.check_permission(node_id, flags)
        return FileHandle(node_id=node_id)

    async def read(self, fh: FileHandle, offset: int, size: int) -> bytes:
        node = await self._metadata.get_node(fh.node_id)
        if node.type != "file":
            raise IsADirectoryError("Cannot read a directory")
        if size == 0:
            return b""
        if offset >= node.size:
            return b""
        actual_size = min(size, node.size - offset)
        return await self._chunk_manager.read(fh.node_id, offset, actual_size)

    async def write(self, fh: FileHandle, offset: int, data: bytes) -> int:
        node = await self._metadata.get_node(fh.node_id)
        if node.type != "file":
            raise IsADirectoryError("Cannot write to a directory")
        if not data:
            return 0
        await self._chunk_manager.write(fh.node_id, offset, data)
        return len(data)

    async def create_file(self, parent_id: int, name: str) -> Node:
        await self._acl.check_permission(parent_id, PERM_WRITE)
        chunk_size = self._chunk_policy.choose_chunk_size(type="file", name=name)
        return await self._metadata.create_node(
            parent_id=parent_id,
            name=name,
            type="file",
            chunk_size=chunk_size,
        )

    async def create_directory(self, parent_id: int, name: str) -> Node:
        await self._acl.check_permission(parent_id, PERM_WRITE)
        return await self._metadata.create_node(
            parent_id=parent_id,
            name=name,
            type="directory",
        )

    async def mkdir(self, parent_id: int, name: str) -> Node:
        return await self.create_directory(parent_id, name)

    async def unlink(self, parent_id: int, name: str) -> None:
        await self._acl.check_permission(parent_id, PERM_WRITE)
        node = await self.lookup(parent_id, name)
        await self._metadata.delete_node(node.id)

    async def rmdir(self, parent_id: int, name: str) -> None:
        await self._acl.check_permission(parent_id, PERM_WRITE)
        node = await self.lookup(parent_id, name)
        children = await self._metadata.list_children(node.id)
        if children:
            raise DirectoryNotEmptyError(node.id)
        await self._metadata.delete_node(node.id)

    async def delete(self, node_id: int) -> None:
        node = await self._metadata.get_node(node_id)
        if node.type == "directory":
            children = await self._metadata.list_children(node_id)
            if children:
                raise OSError("Directory not empty")
        await self._metadata.delete_node(node_id)

    async def list_directory(self, parent_id: int) -> list[Node]:
        return await self._metadata.list_children(parent_id)

    async def resolve_path(self, path: str) -> int:
        if path == "/":
            return self.root_id
        parts = [p for p in path.split("/") if p]
        current_id = self.root_id
        for part in parts:
            children = await self._metadata.list_children(current_id)
            found = False
            for child in children:
                if child.name == part:
                    current_id = child.id
                    found = True
                    break
            if not found:
                raise FileNotFoundError(f"Path not found: {path}")
        return current_id

    async def rename(self, node_id: int, new_name: str) -> None:
        node = await self._metadata.get_node(node_id)
        node.name = new_name

    async def truncate(self, node_id: int, size: int) -> None:
        node = await self._metadata.get_node(node_id)
        if size < node.size:
            existing = await self._chunk_manager.read(node_id, 0, size)
            await self._metadata.delete_node(node_id)
            new_node = await self._metadata.create_node(
                parent_id=node.parent_id,
                name=node.name,
                type=node.type,
                chunk_size=node.chunk_size,
            )
            if existing:
                await self._chunk_manager.write(new_node.id, 0, existing)
