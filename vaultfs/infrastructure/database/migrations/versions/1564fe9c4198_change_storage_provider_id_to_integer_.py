"""change storage_provider_id to integer in chunks table

Revision ID: 1564fe9c4198
Revises: bc3584e79ff6
Create Date: 2026-07-22 09:44:19.661753

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1564fe9c4198'
down_revision: Union[str, Sequence[str], None] = 'bc3584e79ff6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop foreign key constraint first
    op.drop_constraint('fk_chunks_storage_provider_id_storage_providers', 'chunks', type_='foreignkey')
    
    # Change chunks.storage_provider_id from text to integer
    op.alter_column(
        'chunks',
        'storage_provider_id',
        type_=sa.Integer,
        postgresql_using="CASE storage_provider_id "
                          "WHEN 'telegram' THEN 1 "
                          "WHEN 'memory' THEN 2 "
                          "ELSE NULL END",
        existing_type=sa.Text,
        existing_nullable=True
    )
    
    # Change storage_providers.id from text to integer
    op.alter_column(
        'storage_providers',
        'id',
        type_=sa.Integer,
        postgresql_using="id::integer",
        existing_type=sa.Text,
        existing_nullable=False
    )
    
    # Recreate foreign key constraint
    op.create_foreign_key(
        'fk_chunks_storage_provider_id_storage_providers',
        'chunks', 'storage_providers',
        ['storage_provider_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop foreign key constraint first
    op.drop_constraint('fk_chunks_storage_provider_id_storage_providers', 'chunks', type_='foreignkey')
    
    # Change storage_providers.id from integer to text
    op.alter_column(
        'storage_providers',
        'id',
        type_=sa.Text,
        postgresql_using="id::text",
        existing_type=sa.Integer,
        existing_nullable=False
    )
    
    # Change chunks.storage_provider_id from integer to text
    op.alter_column(
        'chunks',
        'storage_provider_id',
        type_=sa.Text,
        postgresql_using="storage_provider_id::text",
        existing_type=sa.Integer,
        existing_nullable=True
    )
    
    # Recreate foreign key constraint
    op.create_foreign_key(
        'fk_chunks_storage_provider_id_storage_providers',
        'chunks', 'storage_providers',
        ['storage_provider_id'], ['id']
    )
