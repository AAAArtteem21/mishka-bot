"""add needs_clarification to chunks

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: в рабочей базе колонка уже добавлена руками
    op.execute(
        "ALTER TABLE chunks "
        "ADD COLUMN IF NOT EXISTS needs_clarification BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS needs_clarification")