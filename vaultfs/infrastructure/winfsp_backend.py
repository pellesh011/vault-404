import errno
import logging
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import trio

from vaultfs.application.file_manager import FileManager
from vaultfs.domain.file_handle import FileHandle
from vaultfs.infrastructure.fuse_backend import FUSEBackend

try:
    from refuse.high import FUSE, FuseOSError, LoggingMixIn, Operations

    refuse_available = True
except ImportError:
    refuse_available = False
    FUSE = None
    FuseOSError = OSError
    LoggingMixIn = object
    Operations = object

logger = logging.getLogger(__name__)


class VaultFSWinFsp(LoggingMixIn, Operations):  # type: ignore[misc]
    def __init__(self, file_manager: FileManager, trio_token: trio.lowlevel.TrioToken) -> None:
        self._fm = file_manager
        self._trio_token = trio_token
        self._next_fh = 100
        self._fh_to_node: dict[int, int] = {}

    def _run_async(self, coro):
        return trio.from_thread.run(coro, trio_token=self._trio_token)

    async def _resolve(self, path: str):
        if path == "/":
            return await self._fm.stat(self._fm.root_id)

        parts = path.strip("/").split("/")
        current_id = self._fm.root_id
        for part in parts:
            children = await self._fm.list_directory(current_id)
            found = False
            for child in children:
                if child.name == part:
                    current_id = child.id
                    found = True
                    break
            if not found:
                return None
        return await self._fm.stat(current_id)

    def getattr(self, path: str, fh: int | None = None) -> dict:
        node = self._run_async(self._resolve(path))
        if node is None:
            raise FuseOSError(errno.ENOENT)

        now = time.time()
        created = node.created_at.timestamp() if node.created_at else now
        modified = node.modified_at.timestamp() if node.modified_at else now

        return {
            "st_mode": stat.S_IFDIR | 0o755 if node.type == "directory" else stat.S_IFREG | 0o644,
            "st_nlink": 2 if node.type == "directory" else 1,
            "st_size": node.size,
            "st_ctime": created,
            "st_mtime": modified,
            "st_atime": modified,
            "st_uid": 1000,
            "st_gid": 1000,
        }

    def readdir(self, path: str, fh: int) -> list[str]:
        node = self._run_async(self._resolve(path))
        if node is None:
            raise FuseOSError(errno.ENOENT)

        entries: list[str] = [".", ".."]
        children = self._run_async(self._fm.list_directory(node.id))
        for child in children:
            entries.append(child.name)
        return entries

    def open(self, path: str, flags: int) -> int:
        node = self._run_async(self._resolve(path))
        if node is None:
            raise FuseOSError(errno.ENOENT)

        fh = self._next_fh
        self._next_fh += 1
        self._fh_to_node[fh] = node.id
        return fh

    def read(self, path: str, size: int, offset: int, fh: int) -> bytes:
        node_id = self._fh_to_node.get(fh)
        if node_id is None:
            raise FuseOSError(errno.EBADF)
        return self._run_async(self._fm.read(FileHandle(node_id=node_id), offset, size))

    def write(self, path: str, buf: bytes, offset: int, fh: int) -> int:
        node_id = self._fh_to_node.get(fh)
        if node_id is None:
            raise FuseOSError(errno.EBADF)
        return self._run_async(self._fm.write(FileHandle(node_id=node_id), offset, buf))

    def create(self, path: str, mode: int) -> int:
        parent_path = str(Path(path).parent)
        name = Path(path).name
        parent_node = self._run_async(self._resolve(parent_path))
        if parent_node is None:
            raise FuseOSError(errno.ENOENT)
        node = self._run_async(self._fm.create_file(parent_node.id, name))

        fh = self._next_fh
        self._next_fh += 1
        self._fh_to_node[fh] = node.id
        return fh

    def unlink(self, path: str) -> None:
        parent_path = str(Path(path).parent)
        name = Path(path).name
        parent_node = self._run_async(self._resolve(parent_path))
        if parent_node is None:
            raise FuseOSError(errno.ENOENT)
        children = self._run_async(self._fm.list_directory(parent_node.id))
        for child in children:
            if child.name == name:
                self._run_async(self._fm.delete(child.id))
                return
        raise FuseOSError(errno.ENOENT)

    def mkdir(self, path: str, mode: int) -> None:
        parent_path = str(Path(path).parent)
        name = Path(path).name
        parent_node = self._run_async(self._resolve(parent_path))
        if parent_node is None:
            raise FuseOSError(errno.ENOENT)
        self._run_async(self._fm.create_directory(parent_node.id, name))

    def rmdir(self, path: str) -> None:
        parent_path = str(Path(path).parent)
        name = Path(path).name
        parent_node = self._run_async(self._resolve(parent_path))
        if parent_node is None:
            raise FuseOSError(errno.ENOENT)
        children = self._run_async(self._fm.list_directory(parent_node.id))
        for child in children:
            if child.name == name:
                self._run_async(self._fm.delete(child.id))
                return
        raise FuseOSError(errno.ENOENT)

    def rename(self, old: str, new: str) -> None:
        old_parent_path = str(Path(old).parent)
        old_name = Path(old).name
        new_parent_path = str(Path(new).parent)
        new_name = Path(new).name

        old_parent = self._run_async(self._resolve(old_parent_path))
        new_parent = self._run_async(self._resolve(new_parent_path))

        if old_parent is None or new_parent is None:
            raise FuseOSError(errno.ENOENT)

        children = self._run_async(self._fm.list_directory(old_parent.id))
        for child in children:
            if child.name == old_name:
                self._run_async(self._fm.rename(child.id, new_name, new_parent.id))
                return
        raise FuseOSError(errno.ENOENT)

    def statfs(self, path: str) -> dict[str, int]:
        return {
            "f_bsize": 512,
            "f_frsize": 512,
            "f_blocks": 10**9,
            "f_bfree": 10**9,
            "f_bavail": 10**9,
            "f_files": 10**9,
            "f_ffree": 10**9,
            "f_favail": 10**9,
        }

    def flush(self, path: str, fh: int) -> None:
        node_id = self._fh_to_node.get(fh)
        if node_id is not None:
            self._run_async(self._fm.flush(FileHandle(node_id=node_id)))

    def release(self, path: str, fh: int) -> None:
        node_id = self._fh_to_node.pop(fh, None)
        if node_id is not None:
            self._run_async(self._fm.release(FileHandle(node_id=node_id)))

    def truncate(self, path: str, length: int, fh: int | None = None) -> None:
        node = self._run_async(self._resolve(path))
        if node is None:
            raise FuseOSError(errno.ENOENT)
        self._run_async(self._fm.truncate(node.id, length))


class WinFspBackend(FUSEBackend):
    def __init__(
        self,
        file_manager: FileManager,
        mountpoint: Path,
        fuse_options: set[str] | None = None,
    ) -> None:
        if not refuse_available:
            raise ImportError(
                "refuse is required for WinFsp backend. Install it with: pip install refuse"
            )
        self._fm = file_manager
        self._mountpoint = mountpoint
        self._fuse_options = fuse_options or set()
        self._thread: threading.Thread | None = None
        self._vault_fs: VaultFSWinFsp | None = None

    async def mount(self) -> None:
        trio_token = trio.lowlevel.current_trio_token()
        self._vault_fs = VaultFSWinFsp(self._fm, trio_token)

    async def run(self) -> None:
        self._thread = threading.Thread(target=self._run_fuse, daemon=True)
        self._thread.start()
        while self._thread.is_alive():
            await trio.sleep(1)

    def _run_fuse(self) -> None:
        try:
            FUSE(  # type: ignore[union-attr]
                self._vault_fs,
                str(self._mountpoint),
                foreground=True,
                nothreads=True,
                fsname="vaultfs",
            )
        except Exception:
            logger.exception("FUSE loop exited with error")

    async def close(self) -> None:
        self._unmount()

    @staticmethod
    def _unmount_linux(mountpoint: Path) -> None:
        subprocess.run(["fusermount", "-u", str(mountpoint)], capture_output=True)

    @staticmethod
    def _unmount_windows(mountpoint: Path) -> None:
        subprocess.run(
            ["net", "use", str(mountpoint), "/delete", "/y"],
            capture_output=True,
        )

    def _unmount(self) -> None:
        if sys.platform == "win32":
            self._unmount_windows(self._mountpoint)
        elif sys.platform == "linux":
            self._unmount_linux(self._mountpoint)
        else:
            subprocess.run(["umount", str(self._mountpoint)], capture_output=True)
