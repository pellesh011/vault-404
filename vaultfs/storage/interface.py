from dataclasses import dataclass
from datetime import datetime
from typing import NewType

ChunkId = NewType("ChunkId", str)


@dataclass(frozen=True)
class ChunkInfo:
    size: int
    sha256: bytes
    created_at: datetime
