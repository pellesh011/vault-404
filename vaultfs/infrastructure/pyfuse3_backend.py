import logging
from pathlib import Path

import pyfuse3

from vaultfs.application.file_manager import FileManager
from vaultfs.infrastructure.fuse_backend import FUSEBackend
from vaultfs.infrastructure.vault_fs import VaultFS

logger = logging.getLogger(__name__)


class PyFuse3Backend(FUSEBackend):
    def __init__(
        self,
        file_manager: FileManager,
        mountpoint: Path,
        fuse_options: set[str] | None = None,
    ) -> None:
        self._fm = file_manager
        self._mountpoint = mountpoint
        self._fuse_options = fuse_options or set()
        self._vault_fs = VaultFS(file_manager)

    async def mount(self) -> None:
        options = set(pyfuse3.default_options)
        options.add("fsname=vaultfs")
        options.add("allow_other")
        options.update(self._fuse_options)
        pyfuse3.init(self._vault_fs, str(self._mountpoint), options)

    async def run(self) -> None:
        await pyfuse3.main()

    async def close(self) -> None:
        pyfuse3.close()
