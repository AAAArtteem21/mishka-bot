from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, SourceType

@dataclass
class ChunkData:
    text: str
    scope_level: int | None = None
    scope_label: str | None = None
    embedding: list[float] | None = None
    needs_clarification: bool = False


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_sha256(self, sha256: str) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.sha256 == sha256)
        )
        return result.unique().scalar_one_or_none()

    async def create(
        self,
        *,
        title: str,
        file_path: str,
        sha256: str,
        source_type: SourceType,
        uploaded_by: int | None = None,
    ) -> Document:
        document = Document(
            title=title,
            file_path=file_path,
            sha256=sha256,
            source_type=source_type.value,
            uploaded_by=uploaded_by,
        )
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def add_chunks(self, document_id: int, chunks: list[ChunkData]) -> list[Chunk]:
        rows = [
            Chunk(
                document_id=document_id,
                position=position,
                text=chunk.text,
                scope_level=chunk.scope_level,
                scope_label=chunk.scope_label,
                embedding=chunk.embedding,
                needs_clarification=chunk.needs_clarification,
            )
            for position, chunk in enumerate(chunks)
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows
