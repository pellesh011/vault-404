from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChunkSizeRule:
    pattern: str
    size: int


class ChunkPolicy(Protocol):
    def choose_chunk_size(
        self,
        type: str,
        name: str = "",
    ) -> int: ...


class DefaultChunkPolicy:
    def __init__(self, default_size: int = 65536) -> None:
        self._default_size = default_size
        self._rules: list[ChunkSizeRule] = [
            ChunkSizeRule(pattern=".mkv", size=16 * 1024 * 1024),
            ChunkSizeRule(pattern=".mp4", size=16 * 1024 * 1024),
            ChunkSizeRule(pattern=".iso", size=32 * 1024 * 1024),
            ChunkSizeRule(pattern=".dmg", size=32 * 1024 * 1024),
            ChunkSizeRule(pattern=".zip", size=16 * 1024 * 1024),
            ChunkSizeRule(pattern=".tar", size=32 * 1024 * 1024),
            ChunkSizeRule(pattern=".mp3", size=8 * 1024 * 1024),
            ChunkSizeRule(pattern=".flac", size=8 * 1024 * 1024),
            ChunkSizeRule(pattern=".wav", size=8 * 1024 * 1024),
            ChunkSizeRule(pattern=".pdf", size=2 * 1024 * 1024),
            ChunkSizeRule(pattern=".doc", size=2 * 1024 * 1024),
            ChunkSizeRule(pattern=".docx", size=2 * 1024 * 1024),
        ]

    def choose_chunk_size(self, type: str, name: str = "") -> int:
        if type == "directory":
            return 0
        for rule in self._rules:
            if name.lower().endswith(rule.pattern):
                return rule.size
        return self._default_size
