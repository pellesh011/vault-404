import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vaultfs.infrastructure.database.models import ChunkModel
from vaultfs.infrastructure.database.repository import SqlAlchemyMetadataRepository

CHUNK_1 = uuid.UUID(int=1)
CHUNK_2 = uuid.UUID(int=2)
CHUNK_3 = uuid.UUID(int=3)
CHUNK_4 = uuid.UUID(int=4)
CHUNK_5 = uuid.UUID(int=5)
CHUNK_6 = uuid.UUID(int=6)
CHUNK_7 = uuid.UUID(int=7)


class TestSqlAlchemyMetadataRepository:
    async def test_create_node_returns_id(self, repo: SqlAlchemyMetadataRepository) -> None:
        node = await repo.create_node(parent_id=None, name="root", type="directory")
        assert isinstance(node.id, int)
        assert node.id > 0

    async def test_create_node_with_parent(self, repo: SqlAlchemyMetadataRepository) -> None:
        parent = await repo.create_node(parent_id=None, name="parent", type="directory")
        child = await repo.create_node(parent_id=parent.id, name="child.txt", type="file")
        assert child.parent_id == parent.id

    async def test_get_node_returns_correct_data(self, repo: SqlAlchemyMetadataRepository) -> None:
        created = await repo.create_node(
            parent_id=None, name="test.txt", type="file", chunk_size=1024
        )
        fetched = await repo.get_node(created.id)
        assert fetched.name == "test.txt"
        assert fetched.type == "file"
        assert fetched.chunk_size == 1024
        assert fetched.parent_id is None

    async def test_get_node_nonexistent_raises(self, repo: SqlAlchemyMetadataRepository) -> None:
        with pytest.raises(KeyError):
            await repo.get_node(99999)

    async def test_list_children_returns_only_direct(
        self, repo: SqlAlchemyMetadataRepository
    ) -> None:
        parent = await repo.create_node(parent_id=None, name="folder", type="directory")
        child1 = await repo.create_node(parent_id=parent.id, name="a.txt", type="file")
        child2 = await repo.create_node(parent_id=parent.id, name="b.txt", type="file")
        await repo.create_node(parent_id=None, name="other", type="directory")

        children = await repo.list_children(parent.id)
        child_ids = {c.id for c in children}
        assert child_ids == {child1.id, child2.id}
        assert len(children) == 2

    async def test_delete_node_removes_node(self, repo: SqlAlchemyMetadataRepository) -> None:
        node = await repo.create_node(parent_id=None, name="delete_me", type="file")
        await repo.delete_node(node.id)
        with pytest.raises(KeyError):
            await repo.get_node(node.id)

    async def test_delete_node_nonexistent_raises(self, repo: SqlAlchemyMetadataRepository) -> None:
        with pytest.raises(KeyError):
            await repo.delete_node(99999)

    async def test_delete_node_cascades_to_file_chunks(
        self, repo: SqlAlchemyMetadataRepository, session: AsyncSession
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            insert(ChunkModel).values(id=CHUNK_1, size=0, sha256=None, created_at=now)
        )
        await session.commit()
        node = await repo.create_node(parent_id=None, name="file.bin", type="file")
        await repo.add_chunk(
            node_id=node.id,
            chunk_index=0,
            offset=0,
            chunk_id=CHUNK_1,
        )
        await repo.delete_node(node.id)

        chunks = await repo.get_chunks(node.id)
        assert chunks == []

    async def test_add_chunk_links_to_node(
        self, repo: SqlAlchemyMetadataRepository, session: AsyncSession
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            insert(ChunkModel).values(id=CHUNK_2, size=0, sha256=None, created_at=now)
        )
        await session.commit()
        node = await repo.create_node(parent_id=None, name="file.bin", type="file")
        await repo.add_chunk(
            node_id=node.id,
            chunk_index=0,
            offset=0,
            chunk_id=CHUNK_2,
        )
        chunks = await repo.get_chunks(node.id)
        assert len(chunks) == 1
        assert chunks[0].chunk_id == CHUNK_2
        assert chunks[0].chunk_index == 0

    async def test_get_chunks_ordered_by_index(
        self, repo: SqlAlchemyMetadataRepository, session: AsyncSession
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        for cid in (CHUNK_3, CHUNK_4, CHUNK_5):
            await session.execute(
                insert(ChunkModel).values(id=cid, size=0, sha256=None, created_at=now)
            )
        await session.commit()
        node = await repo.create_node(parent_id=None, name="large.bin", type="file")
        await repo.add_chunk(
            node_id=node.id,
            chunk_index=2,
            offset=200,
            chunk_id=CHUNK_3,
        )
        await repo.add_chunk(
            node_id=node.id,
            chunk_index=0,
            offset=0,
            chunk_id=CHUNK_4,
        )
        await repo.add_chunk(
            node_id=node.id,
            chunk_index=1,
            offset=100,
            chunk_id=CHUNK_5,
        )
        chunks = await repo.get_chunks(node.id)
        indices = [c.chunk_index for c in chunks]
        assert indices == [0, 1, 2]

    async def test_update_chunk_replaces_id(
        self, repo: SqlAlchemyMetadataRepository, session: AsyncSession
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await session.execute(
            insert(ChunkModel).values(id=CHUNK_1, size=0, sha256=None, created_at=now)
        )
        await session.execute(
            insert(ChunkModel).values(id=uuid.UUID(int=99), size=0, sha256=None, created_at=now)
        )
        await session.commit()
        node = await repo.create_node(parent_id=None, name="file.bin", type="file")
        await repo.add_chunk(
            node_id=node.id,
            chunk_index=0,
            offset=0,
            chunk_id=CHUNK_1,
        )
        chunks = await repo.get_chunks(node.id)
        file_chunk_id = chunks[0].id

        new_id = uuid.UUID(int=99)
        await repo.update_chunk(file_chunk_id, new_id)

        updated_chunks = await repo.get_chunks(node.id)
        assert updated_chunks[0].chunk_id == new_id
        assert updated_chunks[0].chunk_id != CHUNK_1

    async def test_update_chunk_nonexistent_raises(
        self, repo: SqlAlchemyMetadataRepository
    ) -> None:
        with pytest.raises(KeyError):
            await repo.update_chunk(99999, uuid.UUID(int=1))

    async def test_get_orphaned_chunks_returns_deleted(
        self, repo: SqlAlchemyMetadataRepository, session: AsyncSession
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        stmt = insert(ChunkModel).values(
            id=CHUNK_1,
            size=100,
            sha256=b"abc",
            created_at=now,
            deleted_at=now,
        )
        await session.execute(stmt)
        await session.commit()

        orphaned = await repo.get_orphaned_chunks()
        assert len(orphaned) == 1
        assert orphaned[0].id == CHUNK_1
        assert orphaned[0].size == 100

    async def test_get_orphaned_chunks_excludes_active(
        self, repo: SqlAlchemyMetadataRepository, session: AsyncSession
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        stmt = insert(ChunkModel)
        await session.execute(
            stmt.values(
                id=CHUNK_2,
                size=100,
                sha256=b"abc",
                created_at=now,
                deleted_at=now,
            )
        )
        await session.execute(
            stmt.values(
                id=CHUNK_3,
                size=200,
                sha256=b"def",
                created_at=now,
                deleted_at=None,
            )
        )
        await session.commit()

        orphaned = await repo.get_orphaned_chunks()
        orphaned_ids = {c.id for c in orphaned}
        assert CHUNK_2 in orphaned_ids
        assert CHUNK_3 not in orphaned_ids

    async def test_get_or_create_storage_provider_creates(
        self, repo: SqlAlchemyMetadataRepository
    ) -> None:
        provider = await repo.get_or_create_storage_provider(
            name="test_provider",
            type_="telegram",
            description="Test provider",
        )
        assert provider.name == "test_provider"
        assert provider.type == "telegram"
        assert provider.description == "Test provider"
        assert provider.is_active is True

    async def test_get_or_create_storage_provider_returns_existing(
        self, repo: SqlAlchemyMetadataRepository
    ) -> None:
        first = await repo.get_or_create_storage_provider(
            name="existing",
            type_="telegram",
        )
        second = await repo.get_or_create_storage_provider(
            name="existing",
            type_="telegram",
        )
        assert first.id == second.id

    async def test_save_chunk_with_external_id(self, repo: SqlAlchemyMetadataRepository) -> None:
        provider = await repo.get_or_create_storage_provider(
            name="test_save",
            type_="telegram",
        )
        chunk = await repo.save_chunk_with_external_id(
            chunk_id=CHUNK_1,
            size=256,
            sha256=b"hash",
            external_id="12345",
            storage_provider_id=provider.id,
        )
        assert chunk.id == CHUNK_1
        assert chunk.external_id == "12345"
        assert chunk.storage_provider_id == provider.id

    async def test_update_chunk_external_id(self, repo: SqlAlchemyMetadataRepository) -> None:
        provider = await repo.get_or_create_storage_provider(
            name="test_update",
            type_="telegram",
        )
        await repo.save_chunk_with_external_id(
            chunk_id=CHUNK_2,
            size=100,
            sha256=None,
            external_id="old_ext",
            storage_provider_id=provider.id,
        )
        await repo.update_chunk_external_id(CHUNK_2, "new_ext")
        chunk = await repo.get_chunk_by_external_id("new_ext")
        assert chunk is not None
        assert chunk.id == CHUNK_2

    async def test_get_chunk_by_external_id_found(self, repo: SqlAlchemyMetadataRepository) -> None:
        provider = await repo.get_or_create_storage_provider(
            name="test_find",
            type_="telegram",
        )
        await repo.save_chunk_with_external_id(
            chunk_id=CHUNK_3,
            size=50,
            sha256=None,
            external_id="ext_999",
            storage_provider_id=provider.id,
        )
        chunk = await repo.get_chunk_by_external_id("ext_999")
        assert chunk is not None
        assert chunk.id == CHUNK_3
        assert chunk.external_id == "ext_999"

    async def test_get_chunk_by_external_id_not_found(
        self, repo: SqlAlchemyMetadataRepository
    ) -> None:
        chunk = await repo.get_chunk_by_external_id("nonexistent")
        assert chunk is None
