"""seed default storage providers: telegram and memory

Revision ID: 0003
Revises: 1564fe9c4198
Create Date: 2026-07-23 12:00:00.000000
"""

from alembic import op

revision: str = "0003"
down_revision: str = "1564fe9c4198"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO storage_providers
            (id, name, type, description, created_at, updated_at, is_active)
        VALUES
            (1, 'telegram', 'telegram', 'Telegram storage backend', NOW(), NOW(), TRUE),
            (2, 'memory', 'memory', 'In-memory storage backend (testing)', NOW(), NOW(), TRUE)
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM storage_providers WHERE id IN (1, 2)")
