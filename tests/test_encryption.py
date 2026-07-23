import pytest

from vaultfs.storage.encryption import (
    EncryptionLayer,
    InMemoryKeyManager,
    KeyManager,
)


@pytest.fixture
def key_manager() -> InMemoryKeyManager:
    return InMemoryKeyManager()


class TestKeyManagerProtocol:
    async def test_create_key_returns_32_bytes(self, key_manager: InMemoryKeyManager) -> None:
        key = await key_manager.create_key(1)
        assert isinstance(key, bytes)
        assert len(key) == 32

    async def test_get_key_returns_same_key(self, key_manager: InMemoryKeyManager) -> None:
        created = await key_manager.create_key(1)
        retrieved = await key_manager.get_key(1)
        assert retrieved == created

    async def test_get_key_raises_for_missing_node(self, key_manager: InMemoryKeyManager) -> None:
        with pytest.raises(KeyError):
            await key_manager.get_key(999)

    async def test_multiple_nodes_have_different_keys(
        self, key_manager: InMemoryKeyManager
    ) -> None:
        key1 = await key_manager.create_key(1)
        key2 = await key_manager.create_key(2)
        assert key1 != key2

    async def test_key_manager_is_protocol(self, key_manager: InMemoryKeyManager) -> None:
        assert isinstance(key_manager, KeyManager)


class TestEncryptionLayer:
    @pytest.fixture
    async def layer(self, key_manager: InMemoryKeyManager) -> EncryptionLayer:
        from vaultfs.infrastructure.encryption import AESGCMEncryptionLayer

        await key_manager.create_key(1)
        return AESGCMEncryptionLayer(key_manager)

    async def test_encrypt_decrypt_roundtrip(self, layer: EncryptionLayer) -> None:
        original = b"hello world this is test data"
        encrypted = await layer.encrypt_chunk(1, "chunk-1", original)
        decrypted = await layer.decrypt_chunk(1, "chunk-1", encrypted)
        assert decrypted == original

    async def test_different_chunks_different_nonces(self, layer: EncryptionLayer) -> None:
        data = b"same data"
        encrypted1 = await layer.encrypt_chunk(1, "chunk-1", data)
        encrypted2 = await layer.encrypt_chunk(1, "chunk-2", data)
        assert encrypted1[:12] != encrypted2[:12]

    async def test_decrypt_with_wrong_key_fails(self, key_manager: InMemoryKeyManager) -> None:
        from vaultfs.infrastructure.encryption import AESGCMEncryptionLayer

        await key_manager.create_key(1)
        layer1 = AESGCMEncryptionLayer(key_manager)

        encrypted = await layer1.encrypt_chunk(1, "chunk-1", b"secret data")

        await key_manager.create_key(2)
        layer2 = AESGCMEncryptionLayer(key_manager)

        with pytest.raises(Exception):
            await layer2.decrypt_chunk(2, "chunk-1", encrypted)

    async def test_decrypt_with_tampered_data_fails(self, layer: EncryptionLayer) -> None:
        encrypted = await layer.encrypt_chunk(1, "chunk-1", b"data")
        tampered = bytearray(encrypted)
        tampered[5] ^= 0xFF
        with pytest.raises(Exception):
            await layer.decrypt_chunk(1, "chunk-1", bytes(tampered))

    async def test_nonce_uniqueness(self, layer: EncryptionLayer) -> None:
        nonces: set[bytes] = set()
        for i in range(100):
            encrypted = await layer.encrypt_chunk(1, f"chunk-{i}", b"data")
            nonce = encrypted[:12]
            assert nonce not in nonces, f"Duplicate nonce at iteration {i}"
            nonces.add(nonce)

    async def test_empty_data_roundtrip(self, layer: EncryptionLayer) -> None:
        encrypted = await layer.encrypt_chunk(1, "chunk-1", b"")
        decrypted = await layer.decrypt_chunk(1, "chunk-1", encrypted)
        assert decrypted == b""

    async def test_large_data_roundtrip(self, layer: EncryptionLayer) -> None:
        data = b"x" * (1024 * 1024)
        encrypted = await layer.encrypt_chunk(1, "chunk-1", data)
        decrypted = await layer.decrypt_chunk(1, "chunk-1", encrypted)
        assert decrypted == data
        assert len(decrypted) == len(data)

    async def test_encrypted_format_has_nonce_and_tag(self, layer: EncryptionLayer) -> None:
        original = b"hello"
        encrypted = await layer.encrypt_chunk(1, "chunk-1", original)
        assert len(encrypted) >= 12 + len(original) + 16
        assert isinstance(encrypted, bytes)

    async def test_encryption_layer_is_protocol(self, layer: EncryptionLayer) -> None:
        assert isinstance(layer, EncryptionLayer)
