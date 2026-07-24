import errno
import logging
import stat as stat_m
from datetime import UTC, datetime

import pyfuse3
from pyfuse3 import FUSEError, Operations, RequestContext

from vaultfs.application.file_manager import FileManager
from vaultfs.domain.file_handle import FileHandle

logger = logging.getLogger(__name__)

ROOT_INODE = 1


class VaultFS(Operations):
    def __init__(self, file_manager: FileManager) -> None:
        super().__init__()
        self._fm = file_manager
        self._handles: dict[int, int] = {}

    def _map_inode(self, node_id: int) -> int:
        if node_id == self._fm.root_id:
            return ROOT_INODE
        return node_id + 1

    def _unmap_inode(self, inode: int) -> int:
        if inode == ROOT_INODE:
            return self._fm.root_id
        return inode - 1

    async def getattr(
        self,
        inode: int,
        ctx: RequestContext | None = None,
    ) -> pyfuse3.EntryAttributes:
        real_id = self._unmap_inode(inode)
        logger.debug("getattr: inode=%d -> real_id=%d", inode, real_id)
        try:
            node = await self._fm.stat(real_id)
        except KeyError:
            logger.debug("getattr: node %d not found", real_id)
            raise FUSEError(errno.ENOENT)

        attr = pyfuse3.EntryAttributes()
        attr.st_ino = self._map_inode(node.id)
        attr.generation = 0
        attr.entry_timeout = 300
        attr.attr_timeout = 300

        if node.type == "directory":
            attr.st_mode = stat_m.S_IFDIR | 0o755
            attr.st_nlink = 2
        else:
            attr.st_mode = stat_m.S_IFREG | 0o644
            attr.st_nlink = 1

        attr.st_size = node.size
        attr.st_uid = 1000
        attr.st_gid = 1000
        attr.st_blksize = 512
        attr.st_blocks = (node.size + 511) // 512

        created = node.created_at if node.created_at else datetime.now(UTC)
        modified = node.modified_at if node.modified_at else datetime.now(UTC)
        attr.st_atime_ns = int(modified.timestamp() * 1e9)
        attr.st_mtime_ns = int(modified.timestamp() * 1e9)
        attr.st_ctime_ns = int(created.timestamp() * 1e9)

        return attr

    async def lookup(
        self,
        parent_inode: int,
        name: bytes,
        ctx: RequestContext | None = None,
    ) -> pyfuse3.EntryAttributes:
        name_str = name.decode("utf-8")
        real_parent_id = self._unmap_inode(parent_inode)
        logger.debug(
            "lookup: parent_inode=%d -> real_parent_id=%d, name=%s",
            parent_inode,
            real_parent_id,
            name_str,
        )
        try:
            children = await self._fm.list_directory(real_parent_id)
        except KeyError:
            logger.debug("lookup: parent node %d not found", real_parent_id)
            raise FUSEError(errno.ENOENT)

        children_info = [(c.id, c.name) for c in children]
        logger.debug("lookup: found %d children: %s", len(children), children_info)
        for child in children:
            if child.name == name_str:
                result = await self.getattr(self._map_inode(child.id))
                logger.debug("lookup: matched child id=%d -> inode=%d", child.id, result.st_ino)
                return result
        logger.debug("lookup: name '%s' not found in children", name_str)
        raise FUSEError(errno.ENOENT)

    async def readdir(
        self,
        fh: int,
        start_id: int,
        token: pyfuse3.ReaddirToken,
    ) -> None:
        real_id = self._unmap_inode(fh)
        logger.debug("readdir: fh=%d -> real_id=%d, start_id=%d", fh, real_id, start_id)
        try:
            children = await self._fm.list_directory(real_id)
        except KeyError:
            logger.debug("readdir: parent node %d not found", real_id)
            raise FUSEError(errno.ENOENT)

        if start_id == 0:
            root_attr = await self.getattr(ROOT_INODE)
            ok = pyfuse3.readdir_reply(token, b".", root_attr, 1)
            if ok:
                pyfuse3.readdir_reply(token, b"..", root_attr, 2)

        idx = max(start_id, 3) - 3
        for child in children[idx:]:
            attr = await self.getattr(self._map_inode(child.id))
            next_id = idx + 4
            ok = pyfuse3.readdir_reply(token, child.name.encode(), attr, next_id)
            if not ok:
                break
            idx += 1

    async def open(
        self,
        inode: int,
        flags: int,
        ctx: RequestContext | None = None,
    ) -> pyfuse3.FileInfo:
        real_id = self._unmap_inode(inode)
        logger.debug("open: inode=%d -> real_id=%d, flags=%d", inode, real_id, flags)
        try:
            fh = await self._fm.open(real_id, flags)
        except KeyError:
            logger.debug("open: node %d not found", real_id)
            raise FUSEError(errno.ENOENT)
        except PermissionError:
            logger.debug("open: permission denied for node %d", real_id)
            raise FUSEError(errno.EACCES)
        self._handles[fh.node_id] = fh.node_id
        return pyfuse3.FileInfo(fh=self._map_inode(fh.node_id))

    async def opendir(
        self,
        inode: int,
        ctx: RequestContext | None = None,
    ) -> int:
        return inode

    async def read(
        self,
        fh: int,
        off: int,
        size: int,
    ) -> bytes:
        real_id = self._unmap_inode(fh)
        logger.debug("read: fh=%d -> real_id=%d, off=%d, size=%d", fh, real_id, off, size)
        try:
            result = await self._fm.read(FileHandle(node_id=real_id), off, size)
            logger.debug("read: returned %d bytes", len(result))
            return result
        except (KeyError, FileNotFoundError):
            logger.debug("read: node %d not found", real_id)
            raise FUSEError(errno.ENOENT)

    async def write(
        self,
        fh: int,
        off: int,
        buf: bytes,
    ) -> int:
        try:
            return await self._fm.write(FileHandle(node_id=self._unmap_inode(fh)), off, buf)
        except (KeyError, FileNotFoundError):
            raise FUSEError(errno.ENOENT)

    async def create(
        self,
        parent_inode: int,
        name: bytes,
        mode: int,
        flags: int,
        ctx: RequestContext | None = None,
    ) -> tuple[pyfuse3.FileInfo, pyfuse3.EntryAttributes]:
        name_str = name.decode("utf-8")
        try:
            node = await self._fm.create_file(self._unmap_inode(parent_inode), name_str)
        except KeyError:
            raise FUSEError(errno.ENOENT)
        attr = await self.getattr(self._map_inode(node.id))
        return pyfuse3.FileInfo(fh=self._map_inode(node.id)), attr

    async def unlink(
        self,
        parent_inode: int,
        name: bytes,
        ctx: RequestContext | None = None,
    ) -> None:
        name_str = name.decode("utf-8")
        try:
            children = await self._fm.list_directory(self._unmap_inode(parent_inode))
        except KeyError:
            raise FUSEError(errno.ENOENT)
        for child in children:
            if child.name == name_str:
                await self._fm.delete(child.id)
                return
        raise FUSEError(errno.ENOENT)

    async def mkdir(
        self,
        parent_inode: int,
        name: bytes,
        mode: int,
        ctx: RequestContext | None = None,
    ) -> pyfuse3.EntryAttributes:
        name_str = name.decode("utf-8")
        try:
            node = await self._fm.create_directory(self._unmap_inode(parent_inode), name_str)
        except KeyError:
            raise FUSEError(errno.ENOENT)
        return await self.getattr(self._map_inode(node.id))

    async def rmdir(
        self,
        parent_inode: int,
        name: bytes,
        ctx: RequestContext | None = None,
    ) -> None:
        name_str = name.decode("utf-8")
        try:
            children = await self._fm.list_directory(self._unmap_inode(parent_inode))
        except KeyError:
            raise FUSEError(errno.ENOENT)
        for child in children:
            if child.name == name_str:
                await self._fm.delete(child.id)
                return
        raise FUSEError(errno.ENOENT)

    async def rename(
        self,
        parent_inode_old: int,
        name_old: bytes,
        parent_inode_new: int,
        name_new: bytes,
        flags: int = 0,
        ctx: RequestContext | None = None,
    ) -> None:
        name_old_str = name_old.decode("utf-8")
        name_new_str = name_new.decode("utf-8")
        real_parent_old = self._unmap_inode(parent_inode_old)
        real_parent_new = self._unmap_inode(parent_inode_new)
        try:
            children = await self._fm.list_directory(real_parent_old)
        except KeyError:
            raise FUSEError(errno.ENOENT)
        for child in children:
            if child.name == name_old_str:
                await self._fm.rename(child.id, name_new_str, real_parent_new)
                return
        raise FUSEError(errno.ENOENT)

    async def statfs(
        self,
        ctx: RequestContext | None = None,
    ) -> pyfuse3.StatvfsData:
        stat = pyfuse3.StatvfsData()
        stat.f_bsize = 512
        stat.f_frsize = 512
        stat.f_blocks = 10**9
        stat.f_bfree = 10**9
        stat.f_bavail = 10**9
        stat.f_files = 10**9
        stat.f_ffree = 10**9
        stat.f_favail = 10**9
        return stat

    async def flush(self, fh: int, ctx: RequestContext | None = None) -> None:
        real_id = self._unmap_inode(fh)
        await self._fm.flush(FileHandle(node_id=real_id))

    async def release(self, fh: int, ctx: RequestContext | None = None) -> None:
        real_id = self._unmap_inode(fh)
        await self._fm.release(FileHandle(node_id=real_id))

    async def setattr(
        self,
        inode: int,
        attr: pyfuse3.EntryAttributes,
        fields: pyfuse3.SetattrFields,
        fh: int | None = None,
        ctx: RequestContext | None = None,
    ) -> pyfuse3.EntryAttributes:
        real_id = self._unmap_inode(inode)
        if fields.update_size:
            try:
                await self._fm.truncate(real_id, attr.st_size)
            except Exception:
                logger.exception("setattr: truncate failed")
                raise FUSEError(errno.EIO)
        return await self.getattr(inode)
