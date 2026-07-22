"""add storage_providers and update chunks

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21 15:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str = "593b5a0f26a0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "storage_providers",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_providers")),
    )
    op.add_column("chunks", sa.Column("external_id", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "chunks",
        sa.Column(
            "storage_provider_id",
            sa.Text(),
            sa.ForeignKey(
                "storage_providers.id", name=op.f("fk_chunks_storage_provider_id_storage_providers")
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("chunks", "storage_provider_id")
    op.drop_column("chunks", "external_id")
    op.drop_table("storage_providers")
