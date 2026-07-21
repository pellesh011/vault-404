from typing import Protocol, runtime_checkable

NONCE_SIZE = 12
AUTH_TAG_SIZE = 16
KEY_SIZE = 32


@runtime_checkable
class KeyManager(Protocol):
    async def get_key(self, node_id: int) -> bytes: ...

    async def create_key(self, node_id: int) -> bytes: ...


@runtime_checkable
class EncryptionLayer(Protocol):
    async def encrypt_chunk(self, chunk_id: str, data: bytes) -> bytes: ...

    async def decrypt_chunk(self, chunk_id: str, data: bytes) -> bytes: ...


class InMemoryKeyManager:
    def __init__(self) -> None:
        self._keys: dict[int, bytes] = {}

    async def get_key(self, node_id: int) -> bytes:
        key = self._keys.get(node_id)
        if key is None:
            raise KeyError(f"No key for node {node_id}")
        return key

    async def create_key(self, node_id: int) -> bytes:
        import os

        key = os.urandom(KEY_SIZE)
        self._keys[node_id] = key
        return key
