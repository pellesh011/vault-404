import importlib
import logging
from pathlib import Path

from vaultfs.application.file_manager import FileManager
from vaultfs.infrastructure.fuse_backend import FUSEBackend

logger = logging.getLogger(__name__)

BACKEND_PYFUSE3 = "pyfuse3"
BACKEND_WINFSP = "winfsp"

SUPPORTED_BACKENDS = frozenset({BACKEND_PYFUSE3, BACKEND_WINFSP})

BACKEND_MODULE_MAP: dict[str, tuple[str, str]] = {
    BACKEND_PYFUSE3: ("vaultfs.infrastructure.pyfuse3_backend", "PyFuse3Backend"),
    BACKEND_WINFSP: ("vaultfs.infrastructure.winfsp_backend", "WinFspBackend"),
}


class BackendFactory:
    @staticmethod
    def create(
        backend_type: str,
        file_manager: FileManager,
        mountpoint: Path,
        fuse_options: set[str] | None = None,
    ) -> FUSEBackend:
        if backend_type not in SUPPORTED_BACKENDS:
            supported = ", ".join(sorted(SUPPORTED_BACKENDS))
            msg = f"Unknown FUSE backend: {backend_type!r}. Supported: {supported}"
            raise ValueError(msg)

        module_path, class_name = BACKEND_MODULE_MAP[backend_type]

        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(
                f"Cannot load backend {backend_type!r}: {e}. "
                f"Make sure required dependencies are installed."
            ) from e

        cls = getattr(module, class_name)
        return cls(file_manager, mountpoint, fuse_options)
