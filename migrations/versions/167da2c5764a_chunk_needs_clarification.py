"""chunk needs_clarification (restored)

Revision ID: 167da2c5764a
Revises: 0001
"""
from alembic import op

revision = "167da2c5764a"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Схема уже применена в базе; файл восстановлен после потери.
    pass


def downgrade() -> None:
    op.drop_column("chunks", "needs_clarification")