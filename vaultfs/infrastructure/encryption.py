from vaultfs.storage.encryption import NONCE_SIZE, EncryptionLayer, KeyManager


class AESGCMEncryptionLayer(EncryptionLayer):
    def __init__(self, key_manager: KeyManager, node_id: int) -> None:
        self._key_manager = key_manager
        self._node_id = node_id

    async def encrypt_chunk(self, chunk_id: str, data: bytes) -> bytes:
        import os

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = await self._key_manager.get_key(self._node_id)
        aesgcm = AESGCM(key)
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    async def decrypt_chunk(self, chunk_id: str, data: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = await self._key_manager.get_key(self._node_id)
        nonce = data[:NONCE_SIZE]
        ciphertext = data[NONCE_SIZE:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
