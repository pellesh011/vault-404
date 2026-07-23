from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkPolicyConfig:
    video_chunk_size: int = 16 * 1024 * 1024
    audio_chunk_size: int = 8 * 1024 * 1024
    large_chunk_size: int = 32 * 1024 * 1024
    archive_chunk_size: int = 16 * 1024 * 1024
    document_chunk_size: int = 1 * 1024 * 1024
    default_chunk_size: int = 2 * 1024 * 1024
    large_file_threshold: int = 50 * 1024 * 1024 * 1024


class ChunkPolicy(ABC):
    @abstractmethod
    def choose_chunk_size(
        self,
        name: str = "",
        file_size: int = 0,
    ) -> int: ...


_VIDEO_EXTS = (".mp4", ".mkv")
_AUDIO_EXTS = (".mp3", ".flac", ".wav")
_ARCHIVE_EXTS = (".zip", ".tar.gz", ".tar", ".gz", ".7z", ".rar")
_DOCUMENT_EXTS = (".pdf", ".doc", ".docx")


class DefaultChunkPolicy(ChunkPolicy):
    def __init__(self, config: ChunkPolicyConfig | None = None) -> None:
        self._config = config or ChunkPolicyConfig()

    def choose_chunk_size(self, name: str = "", file_size: int = 0) -> int:
        lower = name.lower()

        if lower.endswith(_VIDEO_EXTS):
            return self._config.video_chunk_size
        if lower.endswith(_AUDIO_EXTS):
            return self._config.audio_chunk_size
        if file_size > self._config.large_file_threshold:
            return self._config.large_chunk_size
        if lower.endswith(_ARCHIVE_EXTS):
            return self._config.archive_chunk_size
        if lower.endswith(_DOCUMENT_EXTS):
            return self._config.document_chunk_size
        return self._config.default_chunk_size
