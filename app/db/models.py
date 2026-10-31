from datetime import datetime
from enum import IntEnum, StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


EMBEDDING_DIM = 384


class SourceType(StrEnum):
    USER = "user"
    ARCHIVE = "archive"


class ScopeLevel(IntEnum):
    """Наскільки конкретна порада: чим більше число тим загальніш"""

    GLOVE = 1 #одна рукавичка
    FOREST_PART = 2 #для част лісу
    WHOLE_FOREST = 3 # для всього лісу


class Base(DeclarativeBase):
    pass 


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    real_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "source_type in ('user', 'archive')", name="ck_documents_source_type"
        ),
        CheckConstraint(
            "(source_type = 'user') = (uploaded_by IS NOT NULL)",
            name="ck_documents_uploader",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(16))
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    file_path: Mapped[str] = mapped_column(String(1000))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)

    uploader: Mapped[User | None] = relationship(lazy="joined")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "position", name="uq_chunks_document_position"),
        CheckConstraint(
            "scope_level is null or scope_level between 1 and 3",
            name="ck_chunks_scope_level",
        ),
        Index(
            "ix_chunks_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "gin_trgm_ops"},
        ),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)
    scope_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    scope_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    document: Mapped[Document] = relationship(lazy="joined")
    needs_clarification: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
