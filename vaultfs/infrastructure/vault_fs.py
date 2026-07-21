import errno
import logging
import stat as stat_m
from datetime import UTC, datetime

import pyfuse3
from pyfuse3 import FUSEError, Operations, RequestContext

from vaultfs.application.file_manager import FileManager

logger = logging.getLogger(__name__)

ROOT_INODE = 1


class VaultFS(Operations):
    def __init__(self, file_manager: FileManager) -> None:
        super().__init__()
        self._fm = file_manager
        self._handles: dict[int, int] = {}

    async def getattr(
        self,
        inode: int,
        ctx: RequestContext | None = None,
    ) -> pyfuse3.EntryAttributes:
        try:
            node = await self._fm.stat(inode)
        except KeyError:
            raise FUSEError(errno.ENOENT)

        attr = pyfuse3.EntryAttributes()
        attr.st_ino = node.id
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
        try:
            children = await self._fm.list_directory(parent_inode)
        except KeyError:
            raise FUSEError(errno.ENOENT)

        for child in children:
            if child.name == name_str:
                return await self.getattr(child.id)
        raise FUSEError(errno.ENOENT)

    async def readdir(
        self,
        fh: int,
        start_id: int,
        token: pyfuse3.ReaddirToken,
    ) -> None:
        try:
            children = await self._fm.list_directory(fh)
        except KeyError:
            raise FUSEError(errno.ENOENT)

        if start_id == 0:
            pyfuse3.readdir_reply(token, b".", await self.getattr(fh), 1)
            pyfuse3.readdir_reply(
                token,
                b"..",
                await self.getattr(pyfuse3.ROOT_INODE),
                2,
            )
            start_id = 3

        for i, child in enumerate(children, start=start_id):
            attr = await self.getattr(child.id)
            pyfuse3.readdir_reply(token, child.name.encode(), attr, i + 1)

    async def open(
        self,
        inode: int,
        flags: int,
        ctx: RequestContext | None = None,
    ) -> pyfuse3.FileInfo:
        try:
            node = await self._fm.stat(inode)
        except KeyError:
            raise FUSEError(errno.ENOENT)
        if node.type == "directory":
            raise FUSEError(errno.EISDIR)
        return pyfuse3.FileInfo(fh=inode)

    async def read(
        self,
        fh: int,
        off: int,
        size: int,
    ) -> bytes:
        try:
            return await self._fm.read(fh, off, size)
        except (KeyError, FileNotFoundError):
            raise FUSEError(errno.ENOENT)

    async def write(
        self,
        fh: int,
        off: int,
        buf: bytes,
    ) -> int:
        try:
            return await self._fm.write(fh, off, buf)
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
            node = await self._fm.create_file(parent_inode, name_str)
        except KeyError:
            raise FUSEError(errno.ENOENT)
        attr = await self.getattr(node.id)
        return pyfuse3.FileInfo(fh=node.id), attr

    async def unlink(
        self,
        parent_inode: int,
        name: bytes,
        ctx: RequestContext | None = None,
    ) -> None:
        name_str = name.decode("utf-8")
        try:
            children = await self._fm.list_directory(parent_inode)
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
            node = await self._fm.create_directory(parent_inode, name_str)
        except KeyError:
            raise FUSEError(errno.ENOENT)
        return await self.getattr(node.id)

    async def rmdir(
        self,
        parent_inode: int,
        name: bytes,
        ctx: RequestContext | None = None,
    ) -> None:
        name_str = name.decode("utf-8")
        try:
            children = await self._fm.list_directory(parent_inode)
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
        try:
            children = await self._fm.list_directory(parent_inode_old)
        except KeyError:
            raise FUSEError(errno.ENOENT)
        for child in children:
            if child.name == name_old_str:
                await self._fm.rename(child.id, name_new.decode("utf-8"))
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

    async def flush(self, fh: int, ctx: RequestContext | None = None) -> None: ...

    async def release(self, fh: int, ctx: RequestContext | None = None) -> None: ...


async def mount_vaultfs(
    file_manager: FileManager,
    mountpoint: str,
    foreground: bool = True,
) -> None:
    await file_manager.initialize()
    fuse = VaultFS(file_manager)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add("fsname=vaultfs")
    pyfuse3.init(fuse, str(mountpoint), fuse_options)
    try:
        if foreground:
            await pyfuse3.main()
    finally:
        pyfuse3.close()
