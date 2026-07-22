import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class NodeModel(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("nodes.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    modified_at: Mapped[datetime] = mapped_column(nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    parent = relationship("NodeModel", remote_side="NodeModel.id", backref="children")
    file_chunks = relationship(
        "FileChunkModel", back_populates="node", cascade="all, delete-orphan"
    )
    encryption_keys = relationship(
        "EncryptionKeyModel", back_populates="node", cascade="all, delete-orphan"
    )
    acls = relationship("AclModel", back_populates="node", cascade="all, delete-orphan")


class FileChunkModel(Base):
    __tablename__ = "file_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    offset: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id"), nullable=False
    )

    node = relationship("NodeModel", back_populates="file_chunks")

    __table_args__ = (UniqueConstraint("node_id", "chunk_index", name="uq_node_chunk_index"),)


class StorageProviderModel(Base):
    __tablename__ = "storage_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, onupdate=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    chunks: Mapped[list["ChunkModel"]] = relationship(back_populates="storage_provider")


class ChunkModel(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    storage_provider_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("storage_providers.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    auth_tag: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    storage_provider: Mapped["StorageProviderModel"] = relationship(back_populates="chunks")


class EncryptionKeyModel(Base):
    __tablename__ = "encryption_keys"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    node_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("nodes.id"), nullable=True)
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    node = relationship("NodeModel", back_populates="encryption_keys")


class AclModel(Base):
    __tablename__ = "acl"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    principal: Mapped[str] = mapped_column(Text, nullable=False)
    permissions: Mapped[int] = mapped_column(Integer, nullable=False)

    node = relationship("NodeModel", back_populates="acls")
