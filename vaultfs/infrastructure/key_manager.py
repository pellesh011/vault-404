import os
from base64 import urlsafe_b64encode

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaultfs.infrastructure.database.models import EncryptionKeyModel
from vaultfs.storage.encryption import KEY_SIZE, KeyManager


class DatabaseKeyManager(KeyManager):
    def __init__(self, session: AsyncSession, master_key: bytes | None = None) -> None:
        self._session = session
        if master_key is None:
            master_key = os.urandom(KEY_SIZE)
        self._fernet = Fernet(urlsafe_b64encode(master_key))

    async def get_key(self, node_id: int) -> bytes:
        result = await self._session.execute(
            select(EncryptionKeyModel).where(EncryptionKeyModel.id == str(node_id))
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise KeyError(f"No encryption key for node {node_id}")
        return self._fernet.decrypt(model.encrypted_key)

    async def create_key(self, node_id: int) -> bytes:
        key = os.urandom(KEY_SIZE)
        encrypted = self._fernet.encrypt(key)
        model = EncryptionKeyModel(
            id=str(node_id),
            node_id=node_id,
            encrypted_key=encrypted,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()
        return key
