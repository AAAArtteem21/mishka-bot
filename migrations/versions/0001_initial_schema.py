"""initial schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('telegram_id', sa.BigInteger(), nullable=False),
    sa.Column('real_name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('telegram_id')
    )
    op.create_table('documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('uploaded_by', sa.Integer(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('file_path', sa.String(length=1000), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.CheckConstraint("(source_type = 'user') = (uploaded_by IS NOT NULL)", name='ck_documents_uploader'),
    sa.CheckConstraint("source_type in ('user', 'archive')", name='ck_documents_source_type'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sha256')
    )
    op.create_table('chunks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('scope_level', sa.SmallInteger(), nullable=True),
    sa.Column('scope_label', sa.String(length=255), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.CheckConstraint('scope_level is null or scope_level between 1 and 3', name='ck_chunks_scope_level'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'position', name='uq_chunks_document_position')
    )
    op.create_index(op.f('ix_chunks_document_id'), 'chunks', ['document_id'], unique=False)
    op.create_index('ix_chunks_embedding_hnsw', 'chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_chunks_text_trgm', 'chunks', ['text'], unique=False, postgresql_using='gin', postgresql_ops={'text': 'gin_trgm_ops'})


def downgrade() -> None:
    op.drop_index('ix_chunks_text_trgm', table_name='chunks', postgresql_using='gin', postgresql_ops={'text': 'gin_trgm_ops'})
    op.drop_index('ix_chunks_embedding_hnsw', table_name='chunks', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_chunks_document_id'), table_name='chunks')
    op.drop_table('chunks')
    op.drop_table('documents')
    op.drop_table('users')