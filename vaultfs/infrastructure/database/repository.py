import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaultfs.infrastructure.database.models import (
    ChunkModel,
    FileChunkModel,
    NodeModel,
    StorageProviderModel,
)
from vaultfs.storage.interface import ChunkId


class Node:
    def __init__(
        self,
        id: int,
        parent_id: int | None,
        name: str,
        type: str,
        created_at: datetime,
        modified_at: datetime,
        size: int = 0,
        chunk_size: int | None = None,
    ) -> None:
        self.id = id
        self.parent_id = parent_id
        self.name = name
        self.type = type
        self.created_at = created_at
        self.modified_at = modified_at
        self.size = size
        self.chunk_size = chunk_size


class FileChunk:
    def __init__(
        self,
        id: int,
        node_id: int,
        chunk_index: int,
        offset: int,
        chunk_id: uuid.UUID,
    ) -> None:
        self.id = id
        self.node_id = node_id
        self.chunk_index = chunk_index
        self.offset = offset
        self.chunk_id = chunk_id


class Chunk:
    def __init__(
        self,
        id: uuid.UUID,
        size: int,
        sha256: bytes | None = None,
        external_id: str | None = None,
        storage_provider_id: int | None = None,
        created_at: datetime | None = None,
        deleted_at: datetime | None = None,
        nonce: bytes | None = None,
        auth_tag: bytes | None = None,
    ) -> None:
        self.id = id
        self.size = size
        self.sha256 = sha256
        self.external_id = external_id
        self.storage_provider_id = storage_provider_id
        self.created_at = created_at
        self.deleted_at = deleted_at
        self.nonce = nonce
        self.auth_tag = auth_tag


class MetadataRepository(ABC):
    @abstractmethod
    async def create_node(
        self,
        parent_id: int | None,
        name: str,
        type: str,
        chunk_size: int | None = None,
    ) -> Node: ...

    @abstractmethod
    async def get_node(self, node_id: int) -> Node: ...

    @abstractmethod
    async def get_root_node(self) -> Node | None: ...

    @abstractmethod
    async def list_children(self, parent_id: int) -> list[Node]: ...

    @abstractmethod
    async def delete_node(self, node_id: int) -> None: ...

    @abstractmethod
    async def update_node_size(self, node_id: int, size: int) -> None: ...

    @abstractmethod
    async def add_chunk(
        self,
        node_id: int,
        chunk_index: int,
        offset: int,
        chunk_id: uuid.UUID,
    ) -> None: ...

    @abstractmethod
    async def get_chunks(self, node_id: int) -> list[FileChunk]: ...

    @abstractmethod
    async def update_chunk(self, file_chunk_id: int, new_chunk_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def get_provider_name_for_chunk(self, chunk_id: uuid.UUID) -> str: ...

    @abstractmethod
    async def get_orphaned_chunks(self, force: bool = False) -> list[Chunk]: ...

    @abstractmethod
    async def get_or_create_storage_provider(
        self,
        name: str,
        type_: str,
        description: str = "",
        config: dict | None = None,
    ) -> StorageProviderModel: ...

    @abstractmethod
    async def save_chunk_with_external_id(
        self,
        chunk_id: uuid.UUID,
        size: int,
        sha256: bytes | None,
        external_id: str,
        storage_provider_id: int,
        nonce: bytes | None = None,
        auth_tag: bytes | None = None,
    ) -> Chunk: ...

    @abstractmethod
    async def update_chunk_external_id(
        self,
        chunk_id: uuid.UUID,
        external_id: str,
    ) -> None: ...

    @abstractmethod
    async def get_chunk_by_external_id(
        self,
        external_id: str,
    ) -> Chunk | None: ...

    @abstractmethod
    async def get_chunk_by_id(self, chunk_id: uuid.UUID) -> Chunk | None: ...

    @abstractmethod
    async def get_message_id(self, chunk_id: ChunkId) -> int: ...

    @abstractmethod
    async def hard_delete_chunk(self, chunk_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def flush(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...


class SqlAlchemyMetadataRepository(MetadataRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_node(
        self,
        parent_id: int | None,
        name: str,
        type: str,
        chunk_size: int | None = None,
    ) -> Node:
        now = datetime.now(UTC).replace(tzinfo=None)
        model = NodeModel(
            parent_id=parent_id,
            name=name,
            type=type,
            created_at=now,
            modified_at=now,
            chunk_size=chunk_size,
        )
        self._session.add(model)
        await self._session.flush()
        return Node(
            id=model.id,
            parent_id=model.parent_id,
            name=model.name,
            type=model.type,
            created_at=model.created_at,
            modified_at=model.modified_at,
            size=model.size,
            chunk_size=model.chunk_size,
        )

    async def get_node(self, node_id: int) -> Node:
        model = await self._session.get(NodeModel, node_id)
        if model is None:
            raise KeyError(f"Node {node_id} not found")
        return Node(
            id=model.id,
            parent_id=model.parent_id,
            name=model.name,
            type=model.type,
            created_at=model.created_at,
            modified_at=model.modified_at,
            size=model.size,
            chunk_size=model.chunk_size,
        )

    async def get_root_node(self) -> Node | None:
        result = await self._session.execute(
            select(NodeModel).where(
                NodeModel.parent_id.is_(None),
                NodeModel.name == "/",
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return Node(
            id=model.id,
            parent_id=model.parent_id,
            name=model.name,
            type=model.type,
            created_at=model.created_at,
            modified_at=model.modified_at,
            size=model.size,
            chunk_size=model.chunk_size,
        )

    async def list_children(self, parent_id: int) -> list[Node]:
        result = await self._session.execute(
            select(NodeModel).where(NodeModel.parent_id == parent_id)
        )
        models = result.scalars().all()
        return [
            Node(
                id=m.id,
                parent_id=m.parent_id,
                name=m.name,
                type=m.type,
                created_at=m.created_at,
                modified_at=m.modified_at,
                size=m.size,
                chunk_size=m.chunk_size,
            )
            for m in models
        ]

    async def delete_node(self, node_id: int) -> None:
        model = await self._session.get(NodeModel, node_id)
        if model is None:
            raise KeyError(f"Node {node_id} not found")
        await self._session.delete(model)
        await self._session.flush()

    async def update_node_size(self, node_id: int, size: int) -> None:
        model = await self._session.get(NodeModel, node_id)
        if model is None:
            raise KeyError(f"Node {node_id} not found")
        model.size = size
        await self._session.flush()

    async def add_chunk(
        self,
        node_id: int,
        chunk_index: int,
        offset: int,
        chunk_id: uuid.UUID,
    ) -> None:
        model = FileChunkModel(
            node_id=node_id,
            chunk_index=chunk_index,
            offset=offset,
            chunk_id=chunk_id,
        )
        self._session.add(model)
        await self._session.flush()

    async def get_chunks(self, node_id: int) -> list[FileChunk]:
        result = await self._session.execute(
            select(FileChunkModel)
            .where(FileChunkModel.node_id == node_id)
            .order_by(FileChunkModel.chunk_index)
        )
        models = result.scalars().all()
        return [
            FileChunk(
                id=m.id,
                node_id=m.node_id,
                chunk_index=m.chunk_index,
                offset=m.offset,
                chunk_id=m.chunk_id,
            )
            for m in models
        ]

    async def update_chunk(self, file_chunk_id: int, new_chunk_id: uuid.UUID) -> None:
        model = await self._session.get(FileChunkModel, file_chunk_id)
        if model is None:
            raise KeyError(f"FileChunk {file_chunk_id} not found")
        old_chunk_id = model.chunk_id
        model.chunk_id = new_chunk_id
        if old_chunk_id != new_chunk_id:
            old_chunk = await self._session.get(ChunkModel, old_chunk_id)
            if old_chunk is not None and old_chunk.deleted_at is None:
                old_chunk.deleted_at = datetime.now(UTC).replace(tzinfo=None)
        await self._session.flush()

    async def get_provider_name_for_chunk(self, chunk_id: uuid.UUID) -> str:
        result = await self._session.execute(select(ChunkModel).where(ChunkModel.id == chunk_id))
        chunk_model = result.scalar_one_or_none()
        if chunk_model is None or chunk_model.storage_provider_id is None:
            return "memory"
        provider_result = await self._session.execute(
            select(StorageProviderModel).where(
                StorageProviderModel.id == chunk_model.storage_provider_id
            )
        )
        provider_model = provider_result.scalar_one_or_none()
        if provider_model is None:
            return "memory"
        return provider_model.name

    async def get_orphaned_chunks(self, force: bool = False) -> list[Chunk]:
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        stmt = (
            select(ChunkModel)
            .outerjoin(FileChunkModel, ChunkModel.id == FileChunkModel.chunk_id)
            .where(FileChunkModel.id.is_(None))
        )
        if not force:
            stmt = stmt.where(ChunkModel.created_at < cutoff)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [
            Chunk(
                id=m.id,
                size=m.size,
                sha256=m.sha256,
                external_id=m.external_id,
                storage_provider_id=m.storage_provider_id,
                created_at=m.created_at,
                deleted_at=m.deleted_at,
                nonce=m.nonce,
                auth_tag=m.auth_tag,
            )
            for m in models
        ]

    async def get_or_create_storage_provider(
        self,
        name: str,
        type_: str,
        description: str = "",
        config: dict | None = None,
    ) -> StorageProviderModel:
        result = await self._session.execute(
            select(StorageProviderModel).where(StorageProviderModel.name == name)
        )
        model = result.scalar_one_or_none()
        if model is not None:
            return model

        now = datetime.now(UTC).replace(tzinfo=None)
        model = StorageProviderModel(
            name=name,
            type=type_,
            description=description,
            config=config,
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def save_chunk_with_external_id(
        self,
        chunk_id: uuid.UUID,
        size: int,
        sha256: bytes | None,
        external_id: str,
        storage_provider_id: int,
        nonce: bytes | None = None,
        auth_tag: bytes | None = None,
    ) -> Chunk:
        now = datetime.now(UTC).replace(tzinfo=None)
        model = ChunkModel(
            id=chunk_id,
            size=size,
            sha256=sha256,
            external_id=external_id,
            storage_provider_id=storage_provider_id,
            created_at=now,
            nonce=nonce,
            auth_tag=auth_tag,
        )
        self._session.add(model)
        await self._session.flush()
        return Chunk(
            id=model.id,
            size=model.size,
            sha256=model.sha256,
            external_id=model.external_id,
            storage_provider_id=model.storage_provider_id,
            created_at=model.created_at,
            nonce=model.nonce,
            auth_tag=model.auth_tag,
        )

    async def update_chunk_external_id(
        self,
        chunk_id: uuid.UUID,
        external_id: str,
    ) -> None:
        model = await self._session.get(ChunkModel, chunk_id)
        if model is None:
            raise KeyError(f"Chunk {chunk_id} not found")
        model.external_id = external_id
        await self._session.flush()

    async def get_chunk_by_external_id(
        self,
        external_id: str,
    ) -> Chunk | None:
        result = await self._session.execute(
            select(ChunkModel).where(ChunkModel.external_id == external_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return Chunk(
            id=model.id,
            size=model.size,
            sha256=model.sha256,
            external_id=model.external_id,
            storage_provider_id=model.storage_provider_id,
            created_at=model.created_at,
            deleted_at=model.deleted_at,
            nonce=model.nonce,
            auth_tag=model.auth_tag,
        )

    async def get_chunk_by_id(self, chunk_id: uuid.UUID) -> Chunk | None:
        model = await self._session.get(ChunkModel, chunk_id)
        if model is None:
            return None
        return Chunk(
            id=model.id,
            size=model.size,
            sha256=model.sha256,
            external_id=model.external_id,
            storage_provider_id=model.storage_provider_id,
            created_at=model.created_at,
            deleted_at=model.deleted_at,
            nonce=model.nonce,
            auth_tag=model.auth_tag,
        )

    async def get_message_id(self, chunk_id: ChunkId) -> int:
        result = await self._session.execute(select(ChunkModel).where(ChunkModel.id == chunk_id))
        model = result.scalar_one_or_none()
        if model is None:
            raise KeyError(f"Chunk {chunk_id} not found")
        if model.deleted_at is not None:
            raise KeyError(f"Chunk {chunk_id} not found")
        if not model.external_id:
            raise KeyError(f"Chunk {chunk_id} has no message_id")
        return int(model.external_id)

    async def hard_delete_chunk(self, chunk_id: uuid.UUID) -> None:
        model = await self._session.get(ChunkModel, chunk_id)
        if model is None:
            return
        await self._session.delete(model)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def flush(self) -> None:
        await self._session.flush()

    async def rollback(self) -> None:
        await self._session.rollback()
