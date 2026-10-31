from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk

RRF_K = 60

MIN_COSINE = 0.45
COSINE_MARGIN = 0.25
MIN_TRIGRAM = 0.2

class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class SearchHit:
    chunk_id: int
    text: str
    scope_level: int | None 
    scope_label: int | None
    document_title: str
    source_type: str
    uploader_name: str | None
    uploaded_at: datetime
    cosine: float
    trigram: float 
    score: float = 0.0


def fuse_rankings(*rankings: list[int], k: int = RRF_K) -> dict[int, float]:
    """Recipal Rank Fusion: об'єднує кілька впорядкованих списків id в один бал."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def prioritize(hits: list[SearchHit]) -> list[SearchHit]:
    """Конкретніше — раніше: рукавичка (1), частина лісу (2), увесь ліс (3).

    Шматки з невідомою областю (None) йдуть нарівні із загальними.
    Усередині одного рівня — за релевантністю.
    """
    return sorted(hits, key=lambda hit: (hit.scope_level or 3, -hit.score))


async def _candidates(
    session: AsyncSession,
    query_vec: list[float],
    question: str,
    *,
    by_vector: bool,
    limit: int,
):
    distance = Chunk.embedding.cosine_distance(query_vec)
    similarity = func.similarity(Chunk.text, question)
    stmt = select(Chunk, distance, similarity).where(Chunk.embedding.is_not(None))
    stmt = stmt.order_by(distance if by_vector else similarity.desc()).limit(limit)
    result = await session.execute(stmt)
    return result.unique().all()


async def find_candidates(
    session: AsyncSession, embeddings: Embedder, question: str, *, limit: int = 20
) -> list[SearchHit]:
    """Гібридний пошук: найближчі за змістом + схожі за словами, злиті через RRF."""
    [query_vec] = await embeddings.embed([question])
    by_vector = await _candidates(session, query_vec, question, by_vector=True, limit=limit)
    by_text = await _candidates(session, query_vec, question, by_vector=False, limit=limit)

    scores = fuse_rankings(
        [row[0].id for row in by_vector], [row[0].id for row in by_text]
    )
    hits: dict[int, SearchHit] = {}
    for chunk, distance, similarity in (*by_vector, *by_text):
        if chunk.id in hits:
            continue
        document = chunk.document
        hits[chunk.id] = SearchHit(
            chunk_id=chunk.id,
            text=chunk.text,
            scope_level=chunk.scope_level,
            scope_label=chunk.scope_label,
            document_title=document.title,
            source_type=document.source_type,
            uploader_name=document.uploader.real_name if document.uploader else None,
            uploaded_at=document.uploaded_at,
            cosine=1.0 - float(distance),
            trigram=float(similarity),
            score=scores[chunk.id],
        )
    return sorted(hits.values(), key=lambda hit: -hit.score)


def cosine_cutoff(hits: list[SearchHit]) -> float:
    best = max((hit.cosine for hit in hits), default=0.0)
    return max(MIN_COSINE, best - COSINE_MARGIN)


def is_relevant(hit: SearchHit, cutoff: float) -> bool:
    return hit.cosine >= cutoff or hit.trigram >= MIN_TRIGRAM


def select_relevant(hits: list[SearchHit], top_k: int = 8) -> list[SearchHit]:
    cutoff = cosine_cutoff(hits)
    relevant = [hit for hit in hits if is_relevant(hit, cutoff)]
    return prioritize(relevant[:top_k])


async def search(
    session: AsyncSession, embeddings: Embedder, question: str, *, top_k: int = 8
) -> list[SearchHit]:
    hits = await find_candidates(session, embeddings, question)
    return select_relevant(hits, top_k)
